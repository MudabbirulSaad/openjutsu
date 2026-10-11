"""CPU browser fixture server. Synthetic media and provider completions, never a paid request."""

import argparse
import tempfile
import time
from pathlib import Path

import uvicorn
from openjutsu.api import create_app
from openjutsu.config import Config
from openjutsu.media import audio, run
from openjutsu.providers import account, qualification_profile
from openjutsu.types import Annotation, CreateJob, Point, Recipe, Subject
from PIL import Image, ImageDraw


def fixture(port=9781):
    root = Path(tempfile.mkdtemp(prefix="openjutsu-browser-"))
    config = Config(root, root / "models")
    app = create_app(config, start_workers=False)
    engine, store = app.state.engine, app.state.store
    source = root / "synthetic.mp4"
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=0x273955:size=960x540:rate=24:duration=4",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4",
            "-vf",
            "drawbox=x=290+40*sin(t):y=110:w=130:h=310:color=0x93c5fd:t=fill,drawbox=x=500:y=110:w=130:h=310:color=0xfb923c:t=fill",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-y",
            str(source),
        ]
    )
    image = root / "reference.png"
    im = Image.new("RGB", (150, 200), "#273955")
    draw = ImageDraw.Draw(im)
    draw.ellipse((40, 20, 110, 90), fill="#93c5fd")
    draw.rounded_rectangle((25, 90, 125, 185), radius=20, fill="#93c5fd")
    im.save(image)
    asset = engine.media.import_file(source, "Two synthetic subjects.mp4")
    reference = engine.media.import_file(image)
    subjects = [
        Subject(
            id=i,
            name=f"Subject {i}",
            kind="fictional",
            references=[reference["id"]],
            annotations=[Annotation(frame=0, points=[Point(x=x, y=0.5)])],
        )
        for i, x in [(1, 0.37), (2, 0.59)]
    ]
    job = store.create_job(
        CreateJob(
            source=asset["id"],
            name="Two subjects · synthetic demo",
            budget_usd=10,
            recipe=Recipe(end=4, subjects=subjects),
        )
    )
    wave = root / "original.wav"
    audio(source, wave)
    artifacts = {
        k: engine.media.artifact(job, k, source, "synthetic browser fixture")["id"]
        for k in ["normalized", "mask", "depth", "composite", "conditioning"]
    }
    artifacts["final_audio"] = engine.media.artifact(job, "final_audio", wave, "synthetic tone")[
        "id"
    ]
    store.update("job", job["id"], {"status": "review", "stage": "review", "artifacts": artifacts})
    for provider in ["argolink", "segmind", "byteplus"]:
        settings = {"api_key": "test-only", "account": "synthetic-fixture"}
        engine.secrets.update(provider, settings)
        store.put(
            "qualification",
            {
                "id": provider,
                "provider": provider,
                "account": account(settings),
                "profile": qualification_profile(provider, job["recipe"]),
                "pilot": "synthetic",
                "time": time.time(),
            },
        )
    engine.secrets.update("storage", {"bucket": "test-only"})
    engine.model_state = {
        "gpu": {"available": False, "name": "CPU browser fixture"},
        "models": {
            k: {"ready": False, "reason": "Synthetic tests do not install CUDA models"}
            for k in engine.model_state["models"]
        },
    }

    def synthetic_submit(attempt):
        # Exercise the real durable reservation, approval and event paths only.
        time.sleep(0.2)
        j = store.get("job", attempt["job"])
        art = engine.media.artifact(j, "generation", source, "synthetic provider result")
        preview = engine.media.artifact(j, "preview", source, "synthetic soundtrack restored")
        store.update(
            "attempt",
            attempt["id"],
            {
                "status": "succeeded",
                "remote_id": "synthetic-request",
                "artifact": art["id"],
                "preview": preview["id"],
                "downloaded": True,
            },
        )
        store.settle(attempt["id"], 0.42)
        store.update("job", j["id"], {"status": "preview", "stage": "generate"})

    engine.submit_attempt = synthetic_submit

    @app.get("/api/test-fixture")
    def describe():
        nonlocal job
        job = store.create_job(
            CreateJob(
                source=asset["id"],
                name="Two subjects · synthetic demo",
                budget_usd=10,
                recipe=Recipe(end=4, subjects=subjects),
            )
        )
        outputs = {
            k: engine.media.artifact(job, k, source, "synthetic browser fixture")["id"]
            for k in ["normalized", "mask", "depth", "composite", "conditioning"]
        }
        outputs["final_audio"] = engine.media.artifact(job, "final_audio", wave, "synthetic tone")[
            "id"
        ]
        store.update(
            "job", job["id"], {"status": "review", "stage": "review", "artifacts": outputs}
        )
        return {"job": job["id"], "root": str(root)}

    @app.post("/api/test-fixture/stale")
    def stale():
        j = store.get("job", job["id"])
        store.recipe(j["id"], j["revision"], {**j["recipe"], "pitch": 0})
        return {"revision": j["revision"] + 1}

    catchall = next((r for r in app.routes if getattr(r, "path", "") == "/{path:path}"), None)
    if catchall:
        app.routes.remove(catchall)
        app.routes.append(catchall)
    engine.start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    finally:
        engine.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=9781)
    fixture(parser.parse_args().port)
