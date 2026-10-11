"""Synthetic quality evidence for the local browser fixture; no detector/network calls."""

import json
import subprocess

import numpy as np
from openjutsu.quality import PreparationAudit
from openjutsu.quality_gate import make_binding
from openjutsu.tracking import MASK_COLORS
from openjutsu.worker import encode_frames


def decode(path):
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
        check=True,
    )
    return np.frombuffer(result.stdout, np.uint8).reshape(-1, 540, 960, 3)


def prepare_quality(engine, store, job, source, artifacts):
    root = engine.config.root / job["id"]
    root.mkdir()
    frames = decode(source)
    blue = (frames[..., 2] > 200) & (frames[..., 0] > 100)
    orange = (frames[..., 0] > 220) & (frames[..., 1] > 90) & (frames[..., 2] < 120)
    labels = np.where(blue, 1, np.where(orange, 2, 0)).astype(np.uint8)
    depth = np.full_like(frames, [30, 210, 70])
    composite = np.where((labels > 0)[..., None], depth, frames)
    files = {}
    for kind, data in [
        ("mask", np.asarray(MASK_COLORS, np.uint8)[labels][..., ::-1]),
        ("depth", depth[..., ::-1]),
        ("composite", composite[..., ::-1]),
        ("conditioning", composite[..., ::-1]),
    ]:
        path = root / (kind + ".mp4")
        encode_frames((f.copy() for f in data), path, 960, 540)
        files[kind] = path
    files["mask_data"] = root / "masks.npy"
    np.save(files["mask_data"], labels)
    files["depth_data"] = root / "depth.npz"
    np.savez_compressed(files["depth_data"], depths=depth[..., 0].astype(np.float32))
    files["tracking"] = root / "tracking.json"
    files["tracking"].write_text(
        json.dumps({"collision_policy": "reject_before_mutation", "collisions": 0})
    )
    files["timeline"] = root / "timeline.json"
    files["timeline"].write_text(
        json.dumps({"fps": 24, "frames": [{"frame": f} for f in range(len(frames))]})
    )
    for kind, path in files.items():
        artifacts[kind] = engine.media.artifact(
            job, kind, path, "synthetic browser quality fixture"
        )["id"]
    records = {k: store.get("artifact", id) for k, id in artifacts.items()}
    binding = make_binding(job, store.get("asset", job["source"]), records)
    audit = PreparationAudit(
        job["recipe"],
        len(frames),
        (540, 960),
        binding,
        {"source_evidence": "Synthetic rectangles; no human identity or ML detector"},
    )
    exact = decode(files["conditioning"])
    guide = decode(files["depth"])
    comp = decode(files["composite"])
    for frame in range(len(frames)):
        audit.frame(frame, frames[frame], labels[frame], guide[frame], comp[frame], exact[frame])
    report = audit.finish()
    path = root / "quality.json"
    path.write_text(json.dumps(report))
    artifacts["quality"] = engine.media.artifact(
        job, "quality", path, "synthetic measured quality"
    )["id"]
    store.update("job", job["id"], {"status": "review", "stage": "review", "artifacts": artifacts})
    # The fixture intentionally starts with warnings: browser tests must exercise real review.
