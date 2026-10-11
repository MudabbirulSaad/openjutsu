"""Local source detectors and exact artifact decoding. Never alters source or masks."""

import json
from contextlib import ExitStack
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import numpy as np

from .media import digest, probe
from .quality import PreparationAudit


class SourceDetectors:
    def __init__(self, models, policy):
        import mediapipe as mp

        self.mp = mp
        vision = mp.tasks.vision
        base = mp.tasks.BaseOptions
        # Independent IMAGE detections cannot carry a tracking identity over a shot cut.
        self.face = vision.FaceLandmarker.create_from_options(
            vision.FaceLandmarkerOptions(
                base_options=base(model_asset_path=str(models / "face_landmarker.task")),
                running_mode=vision.RunningMode.IMAGE,
                num_faces=3,
                min_face_detection_confidence=policy["detection_confidence"],
                min_face_presence_confidence=policy["detection_confidence"],
            )
        )
        self.pose = vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(
                base_options=base(model_asset_path=str(models / "pose_landmarker.task")),
                running_mode=vision.RunningMode.IMAGE,
                num_poses=3,
                min_pose_detection_confidence=policy["detection_confidence"],
                min_pose_presence_confidence=policy["detection_confidence"],
            )
        )

    def close(self):
        self.face.close()
        self.pose.close()

    def detect(self, rgb):
        import cv2

        image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        faces = []
        for face in self.face.detect(image).face_landmarks:
            points = np.array([[p.x, p.y] for p in face], np.float32)
            hull = cv2.convexHull(points).reshape(-1, 2)
            faces.append(
                {
                    "hull": hull.tolist(),
                    "box": [*points.min(0).tolist(), *points.max(0).tolist()],
                    "confidence": None,
                }
            )
        poses = []
        for pose in self.pose.detect(image).pose_landmarks:
            points = [
                {
                    "x": p.x,
                    "y": p.y,
                    "confidence": min(p.visibility, p.presence),
                    "part": "face"
                    if i <= 10
                    else "arm"
                    if i <= 14
                    else "hand"
                    if i <= 22
                    else "torso"
                    if i <= 24
                    else "leg",
                }
                for i, p in enumerate(pose)
            ]
            reliable = [p for p in points if p["confidence"] >= 0.9]
            box = (
                [
                    min(p["x"] for p in reliable),
                    min(p["y"] for p in reliable),
                    max(p["x"] for p in reliable),
                    max(p["y"] for p in reliable),
                ]
                if reliable
                else None
            )
            poses.append({"points": points, "box": box, "confidence": None})
        return {"faces": faces, "poses": poses}


def check_required_files(recipe, binding, paths, count):
    required = {"normalized", "timeline", "conditioning"}
    if recipe["mode"] != "fast":
        required |= {"mask", "mask_data", "tracking", "depth", "depth_data", "composite"}
    if not required <= paths.keys() or not required <= binding["artifacts"].keys():
        raise ValueError("Missing a required preparation artifact")
    for kind, bound in binding["artifacts"].items():
        if digest(paths[kind]) != bound["hash"]:
            raise ValueError(f"Artifact bytes changed: {kind}")
    timing = json.loads(Path(paths["timeline"]).read_text())
    if timing.get("fps") != 24 or [f["frame"] for f in timing["frames"]] != list(range(count)):
        raise ValueError("Unreadable or misaligned frame timeline")
    # Readability is a gate; repairing the storage mechanism is a later stage.
    if "depth_data" in required:
        with ZipFile(paths["depth_data"]) as archive:
            if archive.testzip() is not None:
                raise ValueError("Depth archive CRC validation failed")
        with np.load(paths["depth_data"], allow_pickle=False) as archive:
            for name in archive.files:
                values = archive[name]
                if not np.isfinite(values).all():
                    raise ValueError("Depth archive contains non-finite values")
            if "depths" not in archive.files or len(archive["depths"]) != count:
                raise ValueError("Depth archive frame count differs from normalized source")
    return required


def audit_artifacts(recipe, binding, paths, models, progress=lambda **_: None, detectors=None):
    import cv2

    meta = probe(paths["normalized"])
    count, shape = meta["frames"], (meta["height"], meta["width"])
    audit = PreparationAudit(
        recipe,
        count,
        shape,
        binding,
        {
            "face": "MediaPipe FaceLandmarker IMAGE; confidence unavailable in result",
            "pose": "MediaPipe PoseLandmarker IMAGE; point confidence=min(visibility,presence)",
            "model_hashes": {
                name: digest(models / name)
                for name in ("face_landmarker.task", "pose_landmarker.task")
                if (models / name).is_file()
            },
        },
    )
    try:
        check_required_files(recipe, binding, paths, count)
        if recipe["mode"] != "advanced":
            audit.add(
                "mode_requires_validation",
                "BLOCKED",
                0,
                count,
                None,
                "Whole-person structural attribution currently validates advanced mode. "
                "Fast/combined mesh output needs its own attribution validator before approval.",
            )
        masks = np.load(paths["mask_data"], allow_pickle=False) if "mask_data" in paths else None
        if masks is not None and (masks.shape != (count, *shape) or masks.dtype != np.uint8):
            raise ValueError("Mask shape/dtype differs from the normalized source")
        if "tracking" in paths:
            tracking = json.loads(Path(paths["tracking"]).read_text())
            if tracking.get("collisions", 0) > 0:
                audit.add(
                    "subject_collision",
                    "BLOCKED",
                    0,
                    count,
                    None,
                    "Tracking reports overlapping subject pixels.",
                    measurements=tracking,
                )
            elif tracking.get("collision_policy") != "reject_before_mutation":
                audit.add(
                    "collision_evidence_missing",
                    "WARNING",
                    0,
                    count,
                    None,
                    "Tracking artifact lacks an atomic collision check receipt; inspect labels.",
                    reviewable=True,
                    resolutions=["inspected"],
                )
        with ExitStack() as stack:
            if detectors is None:
                detectors = SourceDetectors(models, audit.policy)
                stack.callback(detectors.close)
            streams = {}
            for kind in ("normalized", "mask", "depth", "composite", "conditioning"):
                if kind not in paths:
                    continue
                cap = cv2.VideoCapture(str(paths[kind]))
                stack.callback(cap.release)
                if not cap.isOpened() or probe(paths[kind])["frames"] != count:
                    raise ValueError(f"Unreadable or misaligned video: {kind}")
                streams[kind] = cap
            for frame in range(count):
                images = {}
                for kind, cap in streams.items():
                    ok, bgr = cap.read()
                    if not ok:
                        raise ValueError(f"Video decode ended early: {kind}, frame {frame}")
                    images[kind] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                audit.frame(
                    frame,
                    images["normalized"],
                    masks[frame] if masks is not None else None,
                    images.get("depth"),
                    images.get("composite", images["normalized"]),
                    images["conditioning"],
                    detectors.detect(images["normalized"]),
                )
                progress(completed=frame + 1, total=count)
            if any(cap.read()[0] for cap in streams.values()):
                raise ValueError("Video contains extra frames beyond the normalized source")
        audit.add(
            "artifact_readability",
            "PASS",
            0,
            count,
            None,
            "All required artifact hashes, depth members and exact video frames were read successfully.",
            measurements={"decoded_frames": count, "dimensions": list(shape)},
        )
    except (OSError, ValueError, KeyError, RuntimeError, BadZipFile) as exc:
        audit.add(
            "artifact_validation_failed",
            "BLOCKED",
            0,
            count,
            None,
            "Required local evidence could not be validated: " + str(exc),
        )
    return audit.finish()
