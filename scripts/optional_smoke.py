"""Benchmark optional local stages without cloud submissions. All media stays in runtime storage."""

import argparse
import json
import time
from pathlib import Path

from openjutsu.config import Config
from openjutsu.engine import Engine
from openjutsu.media import normalize, probe
from openjutsu.store import Store
from openjutsu.types import CreateJob


def main(args):
    config = Config(args.root, args.models)
    config.initialize()
    store = Store(config.root)
    engine = Engine(config, store)
    source = config.root / "input.mp4"
    normalize(args.source, source, 0, args.seconds)
    asset = engine.media.import_file(source)
    job = store.create_job(CreateJob(source=asset["id"]))
    report = {"input": probe(source), "gpu": engine.model_state["gpu"], "stages": {}}
    for name in args.stages:
        started = time.monotonic()
        print(f"Running {name}", flush=True)
        try:
            outputs = engine.run_stage(
                job, name, source, {"batch_size": args.batch_size}, batch_size=args.batch_size
            )
            report["stages"][name] = {
                "seconds": round(time.monotonic() - started, 3),
                "outputs": {
                    k: probe(v) if Path(v).suffix == ".mp4" else {} for k, v in outputs.items()
                },
                "benchmarks": [b for b in store.list("benchmark") if b["stage"] == name],
            }
        except Exception as e:
            report["stages"][name] = {"error": str(e)}
        (config.root / "optional-report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report["stages"][name]), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--root", type=Path, default=Path.home() / ".local/share/openjutsu-optional-validation"
    )
    parser.add_argument(
        "--models", type=Path, default=Path.home() / ".local/share/openjutsu/models"
    )
    parser.add_argument(
        "--stages",
        nargs="+",
        choices=["describe", "seedvr2", "realesrgan"],
        default=["describe", "seedvr2", "realesrgan"],
    )
    parser.add_argument("--seconds", type=float, default=1)
    parser.add_argument("--batch-size", type=int, default=5)
    main(parser.parse_args())
