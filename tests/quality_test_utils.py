"""Small report/artifact doubles for transaction tests, never production evidence."""

import json

from openjutsu.media import digest
from openjutsu.quality import PreparationAudit
from openjutsu.quality_gate import make_binding


def attach_quality(store, job_id, *, findings=None, reviewed=True):
    job = store.get("job", job_id)
    root = store.root / "synthetic-preparation"
    root.mkdir(exist_ok=True)
    source = root / "source.mp4"
    source.write_bytes(b"synthetic source evidence double")
    store.put(
        "asset", {**store.get("asset", job["source"]), "path": str(source), "hash": digest(source)}
    )
    kinds = [
        "normalized",
        "timeline",
        "conditioning",
        "mask",
        "mask_data",
        "tracking",
        "depth",
        "depth_data",
        "composite",
    ]
    records = {}
    for kind in kinds:
        path = root / kind
        path.write_bytes(("synthetic artifact double: " + kind).encode())
        records[kind] = store.put(
            "artifact",
            {
                "id": "clip" if kind == "conditioning" else kind,
                "job": job_id,
                "revision": job["revision"],
                "kind": kind,
                "path": str(path),
                "hash": digest(path),
                "metadata": {},
                "producer": "unit-test double",
            },
        )
    binding = make_binding(job, store.get("asset", job["source"]), records)
    count = round((job["recipe"]["end"] - job["recipe"]["start"]) * 24)
    audit = PreparationAudit(job["recipe"], count, (4, 4), binding)
    audit.frames = [{"frame": frame} for frame in range(count)]
    report = audit.finish()
    if findings is not None:
        report["findings"] = findings
    path = root / "quality.json"
    path.write_text(json.dumps(report))
    record = store.put(
        "artifact",
        {
            "id": "quality",
            "job": job_id,
            "revision": job["revision"],
            "kind": "quality",
            "path": str(path),
            "hash": digest(path),
            "metadata": {},
            "producer": "unit-test double",
        },
    )
    store.update(
        "job",
        job_id,
        {
            "status": "review",
            "stage": "review",
            "quality_reviews": [],
            "artifacts": {**{k: r["id"] for k, r in records.items()}, "quality": record["id"]},
        },
    )
    if reviewed:
        for entry in report["findings"]:
            if entry["reviewable"]:
                store.review_quality(
                    job_id,
                    job["revision"],
                    "quality",
                    entry["id"],
                    "inspected" if "inspected" in entry["resolutions"] else entry["resolutions"][0],
                    "Synthetic test fixture inspected; no intended appearance outside cast",
                )
    return store.get("job", job_id)
