"""Locally segment one saved pilot interval into a new private candidate; no Engine/API."""

import argparse
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from openjutsu import worker
from openjutsu.artifacts import verify_npz, write_json, write_npz
from openjutsu.tracking import (
    load_masks,
    merge_subject_mask,
    sam2_track_interval,
    save_masks,
    tracking_report,
    validate_bindings,
    visible_spans,
)
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


def verify_fixture_readback(path, arrays):
    """Do not label a candidate fixture complete until every saved member is readable/exact."""
    verify_npz(path, arrays)


def face_audit(source_frames, candidate, begin, model_path, subject_id, crop=None):
    """Measure face hulls only; detector misses still require silhouette review."""
    import cv2
    import mediapipe as mp

    options = mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(
            model_asset_path=str(model_path), delegate=mp.tasks.BaseOptions.Delegate.CPU
        ),
        running_mode=mp.tasks.vision.RunningMode.IMAGE
        if crop
        else mp.tasks.vision.RunningMode.VIDEO,
        num_faces=3,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    records = []
    with mp.tasks.vision.FaceLandmarker.create_from_options(options) as model:
        for index, bgr in enumerate(source_frames):
            frame = begin + index
            x0, y0, x1, y1 = crop or (0, 0, candidate.shape[2], candidate.shape[1])
            rgb = bgr[y0:y1, x0:x1, ::-1].copy()
            if crop:
                rgb = cv2.resize(rgb, ((x1 - x0) * 4, (y1 - y0) * 4))
            input_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = (
                model.detect(input_image)
                if crop
                else model.detect_for_video(input_image, round(frame * 1000 / 24))
            )
            faces = []
            for points in result.face_landmarks:
                xy = np.array(
                    [[x0 + p.x * (x1 - x0), y0 + p.y * (y1 - y0)] for p in points],
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
    parser.add_argument("--face-audit-crop", type=int, nargs=4)
    parser.add_argument("--base-candidate", type=Path)
    parser.add_argument("--review-frames", type=int, nargs="+")
    args = parser.parse_args()
    saved = json.loads(args.manifest.read_text())
    root = Path(saved["runtime"])
    out = private_destination(
        args.out,
        [
            root,
            Path(saved["evidence"]),
            Path(saved["exports"]),
            args.manifest.parent,
            *([args.base_candidate] if args.base_candidate else []),
        ],
    )
    out.mkdir(parents=True, exist_ok=False)
    records = saved["ledger"]["records"]
    job = records[f"job:{saved['job']}"]
    attempt = records[f"attempt:{saved['attempt']}"]
    artifacts = {k: records[f"artifact:{id}"] for k, id in job["artifacts"].items()}
    recipe = Recipe.model_validate_json(args.recipe.read_text()).model_dump(mode="json")
    validate_bindings(recipe)
    original_recipe = Recipe.model_validate(attempt["recipe_snapshot"]).model_dump(mode="json")
    base_mask_path = artifacts["mask_data"]["path"]
    if args.base_candidate:
        original_recipe = Recipe.model_validate_json(
            (args.base_candidate / "recipe.json").read_text()
        ).model_dump(mode="json")
        base_mask_path = args.base_candidate / "masks.npy"
        base_fixture = json.loads((args.base_candidate / "fixture/fixture.json").read_text())
        assert sha256(base_mask_path) == base_fixture["candidate_hashes"]["mask_data"]
    unchanged = copy.deepcopy(recipe)
    for s, original in zip(unchanged["subjects"], original_recipe["subjects"]):
        if s["id"] == args.subject:
            s["annotations"] = original["annotations"]
            s["visibility"] = original["visibility"]
            s["seed_frame"] = original["seed_frame"]
    assert unchanged == original_recipe, "Only the selected subject's prompts/visibility may change"
    subject = next(s for s in recipe["subjects"] if s["id"] == args.subject)
    span = subject["intervals"][args.interval]
    begin, end = span["start"], span["end"]
    original_subject = next(s for s in original_recipe["subjects"] if s["id"] == args.subject)
    if subject["seed_frame"] != original_subject["seed_frame"]:
        assert subject["seed_frame"] is None or begin <= subject["seed_frame"] < end, (
            "New seed must belong to the selected interval"
        )
    assert [a for a in subject["annotations"] if not begin <= a["frame"] < end] == [
        a for a in original_subject["annotations"] if not begin <= a["frame"] < end
    ], "Annotations outside the selected interval changed"
    assert [n for n in subject["visibility"] if not begin <= n["start"] < n["end"] <= end] == [
        n for n in original_subject["visibility"] if not begin <= n["start"] < n["end"] <= end
    ], "Visibility outside the selected interval changed"
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

    original = load_masks(base_mask_path)
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
    inputs = Path(artifacts["mask_data"]["path"]).parent / "frames"
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        for visible in visible_spans(subject, len(original)):
            if not begin <= visible["start"] < visible["end"] <= end:
                continue
            shot = out / f"inputs-{visible['start']}-{visible['end']}"
            shot.mkdir()
            for frame in range(visible["start"], visible["end"]):
                shutil.copyfile(
                    inputs / f"{frame:06}.jpg", shot / f"{frame - visible['start']:06}.jpg"
                )
            for index, ids, logits in sam2_track_interval(
                predictor, shot, subject, visible, original.shape[2], original.shape[1]
            ):
                frame = visible["start"] + index
                merge_subject_mask(
                    candidate[frame], (logits[0, 0] > 0).cpu().numpy(), args.subject, frame
                )
    assert np.array_equal(candidate[:begin], original[:begin])
    assert np.array_equal(candidate[end:], original[end:])
    (out / "tracking.json").write_text(
        json.dumps(tracking_report(candidate, recipe["subjects"]), indent=2)
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
                *(args.review_frames or []),
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
        (
            "previous_conditioning",
            args.base_candidate / "conditioning/conditioning.mp4"
            if args.base_candidate
            else artifacts["conditioning"]["path"],
        ),
    ]:
        arrays[key] = decode_frames(path, indices, original.shape[2], original.shape[1])
    write_npz(fixture_dir / "frames.npz", arrays)
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
        "original_mask_path": str(Path(base_mask_path).resolve()),
        "recipe": recipe,
        "candidate_hashes": {
            "mask_data": sha256(mask_path),
            "conditioning": sha256(conditioning["conditioning"]),
        },
    }
    write_json(fixture_dir / "fixture.json", fixture)
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
                / max(1, ((original[frame] == args.subject) | mask).sum())
            ),
        }
        for name, box in regions.items():
            roi = rectangle(mask.shape, box)
            item["regions"][name] = float(mask[roi].mean())
        face = rectangle(mask.shape, regions["face"]) if "face" in regions else mask
        if not face.any():
            measured.append(item)
            continue
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
    for frame in args.review_frames or [229, 230, 231, 242, 259, 260, 261, 280]:
        index = indices.index(frame)
        images = [
            Image.fromarray(arrays["normalized"][index][..., ::-1]),
            overlay(arrays["normalized"][index], original[frame] == args.subject),
            overlay(arrays["normalized"][index], candidate[frame] == args.subject),
            Image.fromarray(arrays["previous_conditioning"][index][..., ::-1]),
            Image.fromarray(arrays["conditioning"][index][..., ::-1]),
        ]
        sheet = Image.new("RGB", (2700, 990), (22, 22, 22))
        draw = ImageDraw.Draw(sheet)
        for col, (label, image) in enumerate(
            zip(
                (
                    "Original",
                    "Previous mask",
                    "Corrected mask",
                    "Previous conditioning",
                    "Candidate conditioning",
                ),
                images,
            )
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
            source_frames,
            candidate,
            begin,
            root / "models" / "face_landmarker.task",
            args.subject,
            args.face_audit_crop,
        )
        (out / "face-hull-audit.json").write_text(json.dumps(records, indent=2))
        fixture["face_hull_audit"] = records
        fixture["face_audit_crop"] = args.face_audit_crop
        write_json(fixture_dir / "fixture.json", fixture)
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
