"""Run local preparation only; keep all source media and artifacts outside Git."""

import argparse
import json
import threading
import time
from pathlib import Path

from openjutsu.config import Config
from openjutsu.engine import Engine
from openjutsu.store import Store
from openjutsu.types import Annotation, CreateJob, Point, Recipe, Subject
from PIL import Image, ImageDraw


def main(source, modes, root, models, segmentation="sam2-large"):
    config = Config(root, models)
    config.initialize()
    store = Store(root)
    engine = Engine(config, store)
    asset = engine.media.import_file(source)
    reference = root / "synthetic-reference.png"
    im = Image.new("RGB", (128, 192), "#143464")
    ImageDraw.Draw(im).ellipse((30, 12, 98, 80), fill="#93c5fd")
    im.save(reference)
    ref = engine.media.import_file(reference)
    recipe = Recipe(
        segmentation=segmentation,
        end=4,
        transcribe=True,
        subjects=[
            Subject(
                id=1,
                name="Synthetic replacement",
                kind="fictional",
                references=[ref["id"]],
                annotations=[
                    Annotation(frame=0, points=[Point(x=0.5, y=0.35), Point(x=0.5, y=0.65)])
                ],
            )
        ],
    )
    job = store.create_job(
        CreateJob(source=asset["id"], recipe=recipe, name="Local preparation validation")
    )
    report = {"gpu": engine.model_state["gpu"], "clip_seconds": 4, "modes": {}}
    for mode in modes:
        if mode != job["recipe"]["mode"]:
            job = store.recipe(job["id"], job["revision"], {**job["recipe"], "mode": mode})
        if segmentation != "sam3":
            engine.prepare(job["id"], job["revision"])
        else:
            store.enqueue(job["id"], "prepare", {"revision": job["revision"]})
        task = store.claim()
        store.update("job", job["id"], {"status": "preparing"})
        error = []

        def run():
            try:
                engine.preparation(job)
            except Exception as e:
                error.append(str(e))

        thread = threading.Thread(target=run)
        start = time.monotonic()
        thread.start()
        last = None
        while thread.is_alive():
            progress = store.get("job", job["id"])["progress"]
            if progress != last:
                print(json.dumps({"mode": mode, "progress": progress}), flush=True)
                last = progress
            time.sleep(1)
        if error:
            raise RuntimeError(error[0])
        store.task_done(task["id"])
        job = store.get("job", job["id"])
        report["modes"][mode] = {
            "seconds": round(time.monotonic() - start, 2),
            "artifacts": {
                k: store.get("artifact", v)["metadata"] for k, v in job["artifacts"].items()
            },
            "stages": store.list("benchmark"),
        }
        (root / "smoke-report.json").write_text(json.dumps(report, indent=2))
        print(
            json.dumps({"completed": mode, "seconds": report["modes"][mode]["seconds"]}), flush=True
        )
    print(f"Local report: {root / 'smoke-report.json'}", flush=True)
    if segmentation == "sam3":
        checkpoint = models / "sam3.pt"
        (models / "sam3-readiness.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "gpu": engine.model_state["gpu"]["name"],
                    "checkpoint_stamp": [checkpoint.stat().st_size, checkpoint.stat().st_mtime_ns],
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--segmentation", choices=["sam2-large", "sam2-small", "sam3"], default="sam2-large"
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["advanced", "combined", "fast"],
        choices=["advanced", "combined", "fast"],
    )
    parser.add_argument(
        "--root", type=Path, default=Path.home() / ".local/share/openjutsu-validation"
    )
    parser.add_argument(
        "--models", type=Path, default=Path.home() / ".local/share/openjutsu/models"
    )
    args = parser.parse_args()
    main(args.source, args.modes, args.root, args.models, args.segmentation)
