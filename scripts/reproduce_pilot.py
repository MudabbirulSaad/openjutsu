"""Build private fixtures from a preservation manifest; optionally replay local SAM anchors."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from openjutsu.artifacts import write_json, write_npz
from openjutsu.media import probe
from openjutsu.tracking import load_masks
from preserve_pilot import private_destination, sha256


def decode_frames(path, indices, width, height):
    selection = "+".join(f"eq(n,{i})" for i in indices)
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"select='{selection}'",
            "-fps_mode",
            "passthrough",
            "-pix_fmt",
            "bgr24",
            "-f",
            "rawvideo",
            "pipe:1",
        ],
        capture_output=True,
        check=True,
    )
    frames = np.frombuffer(result.stdout, dtype=np.uint8).reshape(-1, height, width, 3)
    assert len(frames) == len(indices), "Frame selection/decode mismatch"
    return frames


def replay_sam(runtime, folder, recipe, saved, out, version):
    # Matches the pinned diagnostic's synchronized initial-logit procedure. No propagation,
    # upload, application Engine, or writes to the original interval/JPEG directories.
    import torch

    checkpoint = runtime / "models" / "sam2.1_hiera_large.pt"
    assert sha256(checkpoint) == version["sha256"], "SAM checkpoint changed"
    commit = subprocess.check_output(
        ["git", "-C", str(runtime / "models" / "sam2"), "rev-parse", "HEAD"], text=True
    ).strip()
    assert commit == version["source_commit"], "SAM source commit changed"
    sys.path.insert(0, str(runtime / "models" / "sam2"))
    from sam2.build_sam import build_sam2_video_predictor

    subject = next(s for s in recipe["subjects"] if s["id"] == 3)
    span = subject["intervals"][1]
    anchors = [a for a in subject["annotations"] if span["start"] <= a["frame"] < span["end"]]
    predictor = build_sam2_video_predictor(
        "configs/sam2.1/sam2.1_hiera_l.yaml",
        str(checkpoint),
        device="cuda",
    )
    results = []
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        state = predictor.init_state(
            str(folder / "subject-3-interval-1"),
            offload_video_to_cpu=True,
            offload_state_to_cpu=True,
        )
        for anchor in anchors:
            index = anchor["frame"] - span["start"]
            points = np.array(
                [[p["x"] * saved.shape[2], p["y"] * saved.shape[1]] for p in anchor["points"]],
                dtype=np.float32,
            )
            assert not anchor.get("box"), "This diagnostic replay is for the saved point anchors"
            predictor.add_new_points_or_box(
                state,
                index,
                3,
                points=points,
                labels=np.array([int(p["include"]) for p in anchor["points"]]),
            )
            torch.cuda.synchronize()
            internal = state["temp_output_dict_per_obj"][0]["cond_frame_outputs"][index][
                "pred_masks"
            ]
            _, logits = predictor._get_orig_video_res_output(state, internal)
            predicted = (logits[0, 0] > 0).cpu().numpy()
            existing = saved[anchor["frame"]] == 3
            union = int((predicted | existing).sum())
            results.append(
                {
                    "frame": anchor["frame"],
                    "initial_not_tracked": not bool(state["frames_tracked_per_obj"][0]),
                    "initial_mask_pixels": int(predicted.sum()),
                    "changed_pixels": int((predicted != existing).sum()),
                    "replayed_initial_iou_to_saved": float(
                        (predicted & existing).sum() / max(union, 1)
                    ),
                }
            )
    (out / "sam-replay.json").write_text(json.dumps(results, indent=2))
    (out / "sam-version.json").write_text(
        json.dumps({"checkpoint_sha256": version["sha256"], "source_commit": commit}, indent=2)
    )
    assert all(r["changed_pixels"] == 0 for r in results), "SAM differs from the saved baseline"
    print(f"SAM replay: {len(results)} initial masks match exactly (IoU 1.0, zero changed pixels)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--replay-sam", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    root, evidence, exports = [Path(manifest[k]) for k in ("runtime", "evidence", "exports")]
    out = private_destination(args.out, [root, evidence, exports])
    # Exclusive directory creation prevents accidentally replacing an earlier fixture.
    out.mkdir(parents=True, exist_ok=False)
    records = manifest["ledger"]["records"]
    job = records[f"job:{manifest['job']}"]
    attempt = records[f"attempt:{manifest['attempt']}"]
    artifacts = {k: records[f"artifact:{id}"] for k, id in job["artifacts"].items()}
    for key in ("normalized", "mask_data", "depth", "conditioning", "tracking"):
        assert sha256(artifacts[key]["path"]) == artifacts[key]["hash"], f"Changed {key}"
    saved = load_masks(artifacts["mask_data"]["path"])
    assert saved.shape == (432, 960, 540) and saved.dtype == np.uint8
    indices = [*range(160, 167), 230, 260]
    probes = json.loads((evidence / "face-leak-probes.json").read_text())
    metadata = probe(artifacts["normalized"]["path"])
    arrays = {"masks": np.array(saved[indices])}
    for key in ("normalized", "depth", "conditioning"):
        assert probe(artifacts[key]["path"])["frames"] == 432
        arrays[key] = decode_frames(artifacts[key]["path"], indices, 540, 960)
    write_npz(out / "frames.npz", arrays, compressed=False)
    fixture = {
        "frame_ids": indices,
        "subject_id": 3,
        "revision": manifest["revision"],
        "attempt": manifest["attempt"],
        "metadata": metadata,
        "face_probes": probes,
        "intervals": next(
            s["intervals"] for s in attempt["recipe_snapshot"]["subjects"] if s["id"] == 3
        ),
        "original_tracking": json.loads(Path(artifacts["tracking"]["path"]).read_text()),
        "original_sam_replay": json.loads((evidence / "sam-anchor-replay.json").read_text()),
        "artifact_hashes": {k: a["hash"] for k, a in artifacts.items()},
        "fixture_sha256": sha256(out / "frames.npz"),
    }
    write_json(out / "fixture.json", fixture)
    print(f"Private fixture: {len(indices)} exact indexed frames, revision {manifest['revision']}")
    if args.replay_sam:
        replay_sam(
            root,
            Path(artifacts["mask_data"]["path"]).parent,
            attempt["recipe_snapshot"],
            saved,
            out,
            artifacts["mask_data"]["model_version"],
        )


if __name__ == "__main__":
    main()
