"""Capture/verify a private, read-only pilot baseline. Never starts the application."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def ledger(root, job_id):
    # Store.get() uses write transactions; deliberately do not instantiate Store/Engine.
    with sqlite3.connect((root / "jobs.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        rows = {
            (kind, id): json.loads(data) for kind, id, data in db.execute("SELECT * FROM records")
        }
        job = rows["job", job_id]
        attempts = [d for (k, _), d in rows.items() if k == "attempt" and d.get("job") == job_id]
        assets = {job["source"]}
        for recipe in [job["recipe"], *(a["recipe_snapshot"] for a in attempts)]:
            for subject in recipe["subjects"]:
                assets.update(subject["references"])
                if subject.get("portrait_asset"):
                    assets.add(subject["portrait_asset"])
        records = {
            f"{k}:{id}": d
            for (k, id), d in rows.items()
            if (k == "job" and id == job_id)
            or (d.get("job") == job_id)
            or (k == "asset" and id in assets)
        }
        events = [
            list(r) for r in db.execute("SELECT * FROM events WHERE job=? ORDER BY id", (job_id,))
        ]
        tasks = [
            list(r) for r in db.execute("SELECT * FROM tasks WHERE job=? ORDER BY id", (job_id,))
        ]
    return {"records": records, "events": events, "tasks": tasks}


def inventory(state, evidence, exports):
    paths = {}

    def add(path, expected=None):
        path = Path(path).resolve()
        value = {"bytes": path.stat().st_size, "sha256": sha256(path)}
        if expected and value["sha256"] != expected:
            raise ValueError(f"Saved ledger hash mismatch: {path}")
        paths[str(path)] = value

    folders = {evidence, exports}
    for key, data in state["records"].items():
        if key.startswith(("artifact:", "asset:")):
            add(data["path"], data["hash"])
            for field in ("reference", "poster"):
                if data.get(field):
                    add(data[field])
            if key.startswith("artifact:") and "/cache/" in data["path"]:
                folder = Path(data["path"]).parent
                # Include cache tasks/manifests and the exact SAM JPEG inputs used by replay.
                for name in ("task.json", "manifest.json", "tracking.json"):
                    if (folder / name).is_file():
                        add(folder / name)
                if data["kind"] == "mask_data" and data["revision"] == 3:
                    folders.add(folder / "frames")
    for folder in folders:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                add(path)
    return paths


def private_destination(path, protected):
    path = path.resolve()
    repo = Path(__file__).resolve().parents[1]
    if path.is_relative_to(repo) and not path.is_relative_to(repo / "outputs"):
        raise ValueError("Private evidence must be outside Git or under ignored outputs/")
    if any(path.is_relative_to(p.resolve()) for p in protected):
        raise ValueError("Output must not be inside an original evidence/runtime directory")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--runtime", type=Path, required=True)
    capture.add_argument("--evidence", type=Path, required=True)
    capture.add_argument("--exports", type=Path, required=True)
    capture.add_argument("--job", required=True)
    capture.add_argument("--attempt", required=True)
    capture.add_argument("--revision", type=int, required=True)
    capture.add_argument("--out", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("manifest", type=Path)
    args = parser.parse_args()
    if args.command == "capture":
        root, evidence, exports = [p.resolve() for p in (args.runtime, args.evidence, args.exports)]
        out = private_destination(args.out, [root, evidence, exports])
        state = ledger(root, args.job)
        job = state["records"][f"job:{args.job}"]
        attempt = state["records"][f"attempt:{args.attempt}"]
        assert job["revision"] == attempt["revision"] == args.revision
        assert job["approval"] == {
            "revision": args.revision,
            "artifact": attempt["conditioning"],
        }
        assert job["recipe"] == attempt["recipe_snapshot"]
        paths = inventory(state, evidence, exports)
        out.mkdir(parents=True, exist_ok=True)
        manifest = out / "preservation.json"
        with manifest.open("x") as stream:
            json.dump(
                {
                    "runtime": str(root),
                    "job": args.job,
                    "attempt": args.attempt,
                    "revision": args.revision,
                    "evidence": str(evidence),
                    "exports": str(exports),
                    "ledger": state,
                    "files": paths,
                },
                stream,
                indent=2,
            )
        print(
            f"Captured {len(paths)} unchanged/hash-matching files and {len(state['records'])} records"
        )
    else:
        saved = json.loads(args.manifest.read_text())
        state = ledger(Path(saved["runtime"]), saved["job"])
        assert state == saved["ledger"], "Pilot records/events/tasks changed"
        current = inventory(state, Path(saved["evidence"]), Path(saved["exports"]))
        assert current == saved["files"], "Original file inventory/bytes/SHA-256 changed"
        print(
            f"PASS: all {len(current)} file hashes and {len(state['records'])} records unchanged; "
            f"revision {saved['revision']} preserved"
        )


if __name__ == "__main__":
    main()
