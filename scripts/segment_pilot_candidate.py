"""Locally segment one saved pilot interval into a new private candidate; no Engine/API."""

import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from openjutsu import worker
from openjutsu.tracking import load_masks, sam2_track_interval, save_masks, validate_bindings
from openjutsu.types import Recipe
from PIL import Image, ImageDraw
from preserve_pilot import private_destination, sha256
from reproduce_pilot import decode_frames


def rectangle(shape, box):
    height, width = shape
    x0, y0, x1, y1 = box
    result = np.zeros(shape, dtype=bool)
    result[int(y0 * height) : int(y1 * height), int(x0 * width) : int(x1 * width)] = True
    return result


def overlay(bgr, selected):
    rgb = bgr[..., ::-1].copy()
    rgb[selected] = (rgb[selected] * 0.35 + np.array([185, 100, 230]) * 0.65).astype(np.uint8)
    return Image.fromarray(rgb)


def face_audit(source_frames, candidate, begin, model_path, subject_id):
    """Measure face hulls only; detector misses still require silhouette review."""
    import cv2
    import mediapipe as mp

    options = mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(
            model_asset_path=str(model_path), delegate=mp.tasks.BaseOptions.Delegate.CPU
        ),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_faces=3,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    records = []
    with mp.tasks.vision.FaceLandmarker.create_from_options(options) as model:
        for index, bgr in enumerate(source_frames):
            frame = begin + index
            result = model.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=bgr[..., ::-1].copy()),
                round(frame * 1000 / 24),
            )
            faces = []
            for points in result.face_landmarks:
                xy = np.array(
                    [[p.x * candidate.shape[2], p.y * candidate.shape[1]] for p in points],
                    np.float32,
                )
                hull = np.zeros(candidate.shape[1:], np.uint8)
                cv2.fillConvexPoly(hull, cv2.convexHull(xy.astype(np.int32)), 1)
                faces.append(
                    {
                        "area": int(hull.sum()),
                        "coverage": float((candidate[frame][hull > 0] == subject_id).mean()),
                    }
                )
            faces.sort(key=lambda face: face["area"], reverse=True)
            records.append({"frame": frame, "face": faces[0] if faces else None})
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--probes", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--subject", type=int, required=True)
    parser.add_argument("--interval", type=int, required=True)
    parser.add_argument("--audit-faces", action="store_true")
    args = parser.parse_args()
    saved = json.loads(args.manifest.read_text())
    root = Path(saved["runtime"])
    out = private_destination(
        args.out, [root, Path(saved["evidence"]), Path(saved["exports"]), args.manifest.parent]
    )
    out.mkdir(parents=True, exist_ok=False)
    records = saved["ledger"]["records"]
    job = records[f"job:{saved['job']}"]
    attempt = records[f"attempt:{saved['attempt']}"]
    artifacts = {k: records[f"artifact:{id}"] for k, id in job["artifacts"].items()}
    recipe = Recipe.model_validate_json(args.recipe.read_text()).model_dump(mode="json")
    validate_bindings(recipe)
    original_recipe = attempt["recipe_snapshot"]
    unchanged = copy.deepcopy(recipe)
    for s, original in zip(unchanged["subjects"], original_recipe["subjects"]):
        if s["id"] == args.subject:
            s["annotations"] = original["annotations"]
    assert unchanged == original_recipe, "Only the selected subject's annotations may change"
    subject = next(s for s in recipe["subjects"] if s["id"] == args.subject)
    span = subject["intervals"][args.interval]
    begin, end = span["start"], span["end"]
    original_subject = next(s for s in original_recipe["subjects"] if s["id"] == args.subject)
    assert [a for a in subject["annotations"] if not begin <= a["frame"] < end] == [
        a for a in original_subject["annotations"] if not begin <= a["frame"] < end
    ], "Annotations outside the selected interval changed"
    for name in ("mask_data", "normalized", "depth", "conditioning"):
        assert sha256(artifacts[name]["path"]) == artifacts[name]["hash"], (
            f"Changed original {name}"
        )
    version = artifacts["mask_data"]["model_version"]
    checkpoint = root / "models" / "sam2.1_hiera_large.pt"
    assert recipe["segmentation"] == "sam2-large"
    assert sha256(checkpoint) == version["sha256"], "Changed SAM checkpoint"
    commit = subprocess.check_output(
        ["git", "-C", str(root / "models" / "sam2"), "rev-parse", "HEAD"], text=True
    ).strip()
    assert commit == version["source_commit"], "Changed SAM source"
    sys.path.insert(0, str(root / "models" / "sam2"))
    import torch
    from sam2.build_sam import build_sam2_video_predictor

    original = load_masks(artifacts["mask_data"]["path"])
    candidate = np.array(original)
    assert not ((candidate[begin:end] != 0) & (candidate[begin:end] != args.subject)).any(), (
        "Overlapping subjects require separate review"
    )
    candidate[begin:end] = 0
    predictor = build_sam2_video_predictor(
        "configs/sam2.1/sam2.1_hiera_l.yaml",
        str(checkpoint),
        device="cuda",
        hydra_overrides_extra=["++model.add_all_frames_to_correct_as_cond=true"],
    )
    shot = (
        Path(artifacts["mask_data"]["path"]).parent
        / f"subject-{args.subject}-interval-{args.interval}"
    )
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        for index, ids, logits in sam2_track_interval(
            predictor, shot, subject, span, original.shape[2], original.shape[1]
        ):
            assert list(ids) == [args.subject], "Unexpected SAM subject ID"
            candidate[begin + index] = (logits[0, 0] > 0).cpu().numpy().astype(
                np.uint8
            ) * args.subject
    assert np.array_equal(candidate[:begin], original[:begin])
    assert np.array_equal(candidate[end:], original[end:])
    assert (candidate[begin:end].reshape(end - begin, -1).max(axis=1) == args.subject).all(), (
        "New interval gap"
    )
    mask_path = save_masks(out, candidate)
    (out / "recipe.json").write_text(json.dumps(recipe, indent=2))
    task = {
        "recipe": recipe,
        "models": str(root / "models"),
        "source": artifacts["normalized"]["path"],
    }
    composite = worker.stage(
        {
            **task,
            "stage": "composite",
            "output": str(out / "composite"),
            "mask_data": str(mask_path),
            "depth": artifacts["depth"]["path"],
        }
    )
    conditioning = worker.stage(
        {
            **task,
            "stage": "conditioning",
            "source": composite["composite"],
            "output": str(out / "conditioning"),
            "audio": artifacts["conditioning_audio"]["path"],
        }
    )
    # The nine Step 1 frames plus requested controls and immediate neighbors.
    probes = json.loads(args.probes.read_text())
    indices = sorted(
        set(
            [
                *range(160, 167),
                *range(226, 235),
                *range(256, 265),
                192,
                199,
                200,
                201,
                209,
                210,
                211,
                241,
                242,
                243,
                279,
                280,
                281,
                294,
                295,
                *(int(f) for f in probes),
            ]
        )
    )
    fixture_dir = out / "fixture"
    fixture_dir.mkdir()
    arrays = {"masks": candidate[indices], "previous_masks": np.array(original[indices])}
    for key, path in [
        ("normalized", artifacts["normalized"]["path"]),
        ("depth", artifacts["depth"]["path"]),
        ("conditioning", conditioning["conditioning"]),
    ]:
        arrays[key] = decode_frames(path, indices, original.shape[2], original.shape[1])
    np.savez(fixture_dir / "frames.npz", **arrays)
    baseline = json.loads((args.manifest.parent / "fixture-verified" / "fixture.json").read_text())
    fixture = {
        **baseline,
        "frame_ids": indices,
        "fixture_sha256": sha256(fixture_dir / "frames.npz"),
        "candidate": True,
        "corrected_interval": span,
        "anatomy_probes": probes,
        "model_version": version,
        "unchanged_outside_interval": True,
        "candidate_mask_path": str(mask_path.resolve()),
        "original_mask_path": artifacts["mask_data"]["path"],
        "candidate_hashes": {
            "mask_data": sha256(mask_path),
            "conditioning": sha256(conditioning["conditioning"]),
        },
    }
    (fixture_dir / "fixture.json").write_text(json.dumps(fixture, indent=2))
    measured = []
    for frame, regions in probes.items():
        frame = int(frame)
        index = indices.index(frame)
        mask = candidate[frame] == args.subject
        item = {
            "frame": frame,
            "regions": {},
            "previous_iou": float(
                ((original[frame] == args.subject) & mask).sum()
                / ((original[frame] == args.subject) | mask).sum()
            ),
        }
        for name, box in regions.items():
            roi = rectangle(mask.shape, box)
            item["regions"][name] = float(mask[roi].mean())
        face = rectangle(mask.shape, regions["face"])
        item["face_depth_mae"] = float(
            np.abs(
                arrays["conditioning"][index][face].astype(float) - arrays["depth"][index][face]
            ).mean()
        )
        item["face_source_mae"] = float(
            np.abs(
                arrays["conditioning"][index][face].astype(float)
                - arrays["normalized"][index][face]
            ).mean()
        )
        measured.append(item)
    (out / "measurements.json").write_text(json.dumps(measured, indent=2))
    sheets = out / "sheets"
    sheets.mkdir()
    for frame in [229, 230, 231, 242, 259, 260, 261, 280]:
        index = indices.index(frame)
        images = [
            Image.fromarray(arrays["normalized"][index][..., ::-1]),
            overlay(arrays["normalized"][index], original[frame] == args.subject),
            overlay(arrays["normalized"][index], candidate[frame] == args.subject),
            Image.fromarray(arrays["conditioning"][index][..., ::-1]),
        ]
        sheet = Image.new("RGB", (2160, 990), (22, 22, 22))
        draw = ImageDraw.Draw(sheet)
        for col, (label, image) in enumerate(
            zip(("Original", "Previous mask", "Corrected mask", "Candidate conditioning"), images)
        ):
            sheet.paste(image, (col * 540, 0))
            draw.text((col * 540 + 8, 968), f"{label} / frame {frame}", fill="white")
        sheet.save(sheets / f"frame-{frame}.png")
    # Review every frame in the changed interval, including profiles/detector blind spots.
    source_frames = decode_frames(
        artifacts["normalized"]["path"], list(range(begin, end)), 540, 960
    )
    if args.audit_faces:
        records = face_audit(
            source_frames, candidate, begin, root / "models" / "face_landmarker.task", args.subject
        )
        (out / "face-hull-audit.json").write_text(json.dumps(records, indent=2))
        fixture["face_hull_audit"] = records
        (fixture_dir / "fixture.json").write_text(json.dumps(fixture, indent=2))
    for first in range(begin, end, 24):
        frames = list(range(first, min(first + 24, end)))
        sheet = Image.new("RGB", (1296, 1652), (22, 22, 22))
        draw = ImageDraw.Draw(sheet)
        for slot, frame in enumerate(frames):
            rgb = source_frames[frame - begin]
            images = [
                Image.fromarray(rgb[..., ::-1]),
                overlay(rgb, original[frame] == args.subject),
                overlay(rgb, candidate[frame] == args.subject),
            ]
            x, y = (slot % 4) * 324, (slot // 4) * 275
            for col, image in enumerate(images):
                sheet.paste(image.resize((108, 192)), (x + col * 108, y))
            draw.text((x + 4, y + 196), f"f{frame}: original / old / new", fill="white")
        sheet.save(sheets / f"interval-{first}-{frames[-1]}.png")
    print(json.dumps(measured, indent=2))
    print(
        f"Candidate complete: {begin}:{end}; outside interval unchanged; {len(indices)} fixture frames"
    )


if __name__ == "__main__":
    main()
