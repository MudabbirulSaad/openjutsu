"""Preparation checks over exact frames. Detector evidence supplements source review.

This module never changes masks, fills anatomy, chooses a cast, or submits media.
PASS findings describe specific measured contracts, not semantic certification of a person.
"""

import hashlib
import json
from collections import Counter

import numpy as np
from PIL import Image, ImageDraw

from .tracking import intervals, visible_spans
from .types import QualityPolicy

REPORT_VERSION = 3
PARTS = {"head", "hair", "neck", "torso", "arm", "hand", "leg"}


def region_mask(shape, box):
    height, width = shape
    x0, y0, x1, y1 = box
    result = np.zeros(shape, bool)
    result[int(y0 * height) : int(y1 * height), int(x0 * width) : int(x1 * width)] = True
    return result


def polygon_mask(shape, points):
    height, width = shape
    image = Image.new("1", (width, height))
    ImageDraw.Draw(image).polygon([(int(x * width), int(y * height)) for x, y in points], fill=1)
    return np.asarray(image, dtype=bool)


def visible(subject, frame, count):
    return any(s["start"] <= frame < s["end"] for s in visible_spans(subject, count))


def finding(
    code,
    status,
    start,
    end,
    subject_id,
    message,
    *,
    measurements=None,
    confidence=None,
    box=None,
    reviewable=False,
    resolutions=None,
    refs=None,
):
    return {
        "id": f"{code}:{subject_id}:{start}:{end}",
        "code": code,
        "status": status,
        "start": start,
        "end": end,
        "timestamp": start / 24,
        "subject_id": subject_id,
        "message": message,
        "measurements": measurements or {},
        "confidence": confidence,
        "box": box,
        "reviewable": reviewable,
        "resolutions": resolutions or [],
        "artifacts": refs or {},
    }


def summarize(findings):
    counts = Counter(f["status"] for f in findings)
    status = next((s for s in ("BLOCKED", "WARNING", "REVIEWED") if counts[s]), "PASS")
    return {
        "status": status,
        "counts": {s: counts[s] for s in ("PASS", "WARNING", "BLOCKED", "REVIEWED")},
        "approval_ready": not counts["BLOCKED"] and not counts["WARNING"],
    }


class PreparationAudit:
    def __init__(self, recipe, count, shape, binding, detectors=None):
        self.recipe, self.count, self.shape = recipe, count, shape
        self.policy = {**QualityPolicy().model_dump(), **recipe.get("quality_policy", {})}
        self.binding, self.detectors = binding, detectors or {}
        self.findings, self.frames = [], []
        self.previous_areas = {}
        self.parts_seen = {s["id"]: set() for s in recipe["subjects"]}
        self.refs = {k: a["id"] for k, a in binding.get("artifacts", {}).items()}

    def add(self, code, status, start, end, subject_id, message, **kwargs):
        entry = finding(code, status, start, end, subject_id, message, refs=self.refs, **kwargs)
        # Independent face/component detections on one frame must keep distinct evidence IDs.
        if any(f["id"] == entry["id"] for f in self.findings):
            entry["id"] += f":{len(self.findings)}"
        self.findings.append(entry)
        return entry

    def pixel_evidence(
        self,
        frame,
        subject_id,
        selected,
        source,
        depth,
        composite,
        conditioning,
        part,
        roi,
        threshold,
        *,
        confidence=None,
        box=None,
        provenance="detector",
    ):
        area = int(roi.sum())
        if not area:
            self.add(
                "empty_evidence_region",
                "WARNING",
                frame,
                frame + 1,
                subject_id,
                "Evidence has no observable pixels at this resolution; inspect it.",
                reviewable=True,
                resolutions=["inspected"],
                box=box,
            )
            return {}
        coverage = float(selected[roi].mean()) if selected is not None else None
        metrics = {
            "part": part,
            "area": area,
            "coverage": coverage,
            "threshold": threshold,
            "provenance": provenance,
        }
        # Pixel attribution uses inner-face/manual source evidence, not a convex-hull
        # background gap. The broad hull measurement is checked separately.
        if coverage is not None and coverage < threshold:
            uncertain = provenance == "detector"
            self.add(
                "incomplete_" + part,
                "WARNING" if uncertain else "BLOCKED",
                frame,
                frame + 1,
                subject_id,
                f"Visible {part} evidence is not covered by this subject's mask.",
                measurements=metrics,
                confidence=confidence,
                box=box,
                reviewable=uncertain,
                resolutions=["inspected", "false_detection", "requires_replacement"]
                if uncertain
                else [],
            )
        if depth is not None:
            delta = np.abs(conditioning[roi].astype(float) - depth[roi].astype(float))
            metrics["conditioning_depth_mae"] = float(delta.mean())
            metrics["composite_depth_mae"] = float(
                np.abs(composite[roi].astype(float) - depth[roi].astype(float)).mean()
            )
        metrics["conditioning_source_mae"] = float(
            np.abs(conditioning[roi].astype(float) - source[roi].astype(float)).mean()
        )
        if part == "face" and depth is not None:
            source_error = np.abs(conditioning[roi].astype(float) - source[roi].astype(float)).mean(
                axis=1
            )
            guide_error = np.abs(conditioning[roi].astype(float) - depth[roi].astype(float)).mean(
                axis=1
            )
            source_like = (source_error <= self.policy["source_similarity_mae"]) & (
                guide_error > self.policy["structural_mae"]
            )
            metrics["source_like_pixels"] = int(source_like.sum())
            metrics["source_like_fraction"] = float(source_like.mean())
            # Regional averages can hide an original eye/face patch in an otherwise
            # correct structural face. Only source-reviewed face interiors establish
            # pixel truth; detector hull/background uncertainty cannot confirm this.
            if (
                provenance != "detector"
                and source_like.sum() >= 16
                and source_like.mean() > (1 - self.policy["critical_hull_coverage"])
            ):
                self.add(
                    "source_face_patch",
                    "BLOCKED",
                    frame,
                    frame + 1,
                    subject_id,
                    "A localized original RGB patch remains in a source-reviewed face interior.",
                    measurements=metrics,
                    box=box,
                )
        if part == "face":
            source_mae = metrics["conditioning_source_mae"]
            depth_mae = metrics.get("conditioning_depth_mae")
            if source_mae <= self.policy["source_similarity_mae"] and (
                depth_mae is None or depth_mae > self.policy["structural_mae"]
            ):
                self.add(
                    "source_face_rgb",
                    "BLOCKED",
                    frame,
                    frame + 1,
                    subject_id,
                    "Original RGB facial appearance remains in designated replacement pixels.",
                    measurements=metrics,
                    confidence=confidence,
                    box=box,
                )
            elif depth_mae is not None and depth_mae > self.policy["structural_mae"]:
                uncertain = provenance == "detector"
                self.add(
                    "face_conditioning_mismatch",
                    "WARNING" if uncertain else "BLOCKED",
                    frame,
                    frame + 1,
                    subject_id,
                    "Exact conditioning face pixels differ from the expected structural guide.",
                    measurements=metrics,
                    confidence=confidence,
                    box=box,
                    reviewable=uncertain,
                    resolutions=["inspected", "false_detection", "requires_replacement"]
                    if uncertain
                    else [],
                )
            elif source_mae <= self.policy["source_similarity_mae"]:
                self.add(
                    "face_attribution_uncertain",
                    "WARNING",
                    frame,
                    frame + 1,
                    subject_id,
                    "Source and guide colors are too similar to establish facial RGB attribution.",
                    measurements=metrics,
                    reviewable=True,
                    resolutions=["inspected"],
                    box=box,
                )
        return metrics

    def frame(self, frame, source, labels, depth, composite, conditioning, observations=None):
        observations = observations or {"faces": [], "poses": []}
        if any(image.shape != source.shape for image in (composite, conditioning)):
            raise ValueError("Quality frame dimensions differ from normalized source")
        if labels is not None and (labels.shape != self.shape or labels.dtype != np.uint8):
            raise ValueError("Subject labels must be aligned uint8 masks")
        if depth is not None and depth.shape != source.shape:
            raise ValueError("Depth visualization dimensions differ from normalized source")
        active = [s["id"] for s in self.recipe["subjects"] if visible(s, frame, self.count)]
        permitted = {0, *active}
        present = set(map(int, np.unique(labels))) if labels is not None else set()
        if labels is not None and not present <= permitted:
            self.add(
                "interval_identity",
                "BLOCKED",
                frame,
                frame + 1,
                None,
                "Mask labels occur outside their visible cast intervals or contain an unbound ID.",
                measurements={"labels": sorted(present), "permitted": sorted(permitted)},
            )
        for subject_id in active:
            selected = labels == subject_id if labels is not None else None
            if selected is not None and not selected.any():
                self.add(
                    "visible_subject_gap",
                    "BLOCKED",
                    frame,
                    frame + 1,
                    subject_id,
                    "An intended visible subject has no mask; another label cannot excuse this gap.",
                )
            if selected is not None:
                area = int(selected.sum())
                previous = self.previous_areas.get(subject_id)
                # Compare only consecutive frames within one permitted visible span.
                if (
                    previous
                    and previous[0] == frame - 1
                    and not any(
                        span["start"] == frame
                        for s in self.recipe["subjects"]
                        if s["id"] == subject_id
                        for span in visible_spans(s, self.count)
                    )
                    and min(area, previous[1]) > 0
                    and max(area, previous[1]) / min(area, previous[1]) > 3
                ):
                    self.add(
                        "mask_area_transition",
                        "WARNING",
                        frame,
                        frame + 1,
                        subject_id,
                        "Mask area changes abruptly; inspect motion, occlusion and background edges.",
                        measurements={"previous_area": previous[1], "area": area},
                        reviewable=True,
                        resolutions=["inspected"],
                    )
                self.previous_areas[subject_id] = frame, area

        for subject in self.recipe["subjects"]:
            for annotation in subject.get("annotations", []):
                if annotation["frame"] != frame or labels is None:
                    continue
                for point in annotation.get("points", []):
                    y = min(int(point["y"] * self.shape[0]), self.shape[0] - 1)
                    x = min(int(point["x"] * self.shape[1]), self.shape[1] - 1)
                    expected = subject["id"] if point["include"] else 0
                    if int(labels[y, x]) != expected:
                        self.add(
                            "annotation_mask_conflict",
                            "WARNING",
                            frame,
                            frame + 1,
                            subject["id"],
                            "Source annotation and final mask disagree; inspect the indicated point.",
                            measurements={
                                "point": [point["x"], point["y"]],
                                "expected_label": expected,
                                "actual_label": int(labels[y, x]),
                            },
                            reviewable=True,
                            resolutions=["inspected", "requires_replacement"],
                        )

        # Pose evidence is conservative: visible landmarks are interior probes, and the
        # independent person segmentation is uncertain boundary evidence, never a mask fill.
        associated_poses = []
        for pose in observations.get("poses", []):
            points = [
                p
                for p in pose["points"]
                if p["confidence"] >= self.policy["landmark_confidence"]
                and 0 <= p["x"] < 1
                and 0 <= p["y"] < 1
            ]
            votes = (
                Counter(
                    int(labels[int(p["y"] * self.shape[0]), int(p["x"] * self.shape[1])])
                    for p in points
                    if p["part"] != "face"
                )
                if labels is not None
                else Counter()
            )
            subject_id, score = max(
                ((id, votes[id]) for id in active), key=lambda x: x[1], default=(None, 0)
            )
            # Close-ups often put every body landmark outside the image. Reliable face
            # landmark agreement can associate the pose with an already selected ID;
            # it does not establish body/hair coverage or suppress silhouette review.
            if score < 2 and labels is not None:
                face_points = [p for p in points if p["part"] == "face"]
                face_votes = Counter(
                    int(labels[int(p["y"] * self.shape[0]), int(p["x"] * self.shape[1])])
                    for p in face_points
                )
                best, face_score = max(
                    ((id, face_votes[id]) for id in active), key=lambda x: x[1], default=(None, 0)
                )
                if face_score >= 3 and face_score / len(face_points) >= 0.95:
                    subject_id, score = best, 2
            if subject_id is None or score < 2:
                self.add(
                    "unbound_person",
                    "WARNING",
                    frame,
                    frame + 1,
                    None,
                    "A detected person is not reliably bound to a cast mask. Decide whether to replace or preserve it.",
                    confidence=pose.get("confidence"),
                    box=pose.get("box"),
                    reviewable=True,
                    resolutions=["preserve_background", "false_detection", "requires_replacement"],
                )
                continue
            associated_poses.append((subject_id, pose))
            for point in points:
                part = point["part"]
                self.parts_seen[subject_id].add(part)
                x, y = int(point["x"] * self.shape[1]), int(point["y"] * self.shape[0])
                if labels[y, x] != subject_id:
                    self.add(
                        "landmark_coverage_uncertain",
                        "WARNING",
                        frame,
                        frame + 1,
                        subject_id,
                        f"A high-confidence {part} landmark is outside the mask; confirm visibility and mask coverage.",
                        confidence=point["confidence"],
                        box=pose.get("box"),
                        measurements={"part": part, "point": [point["x"], point["y"]]},
                        reviewable=True,
                        resolutions=["inspected", "false_detection", "requires_replacement"],
                    )

        face_metrics = []
        for face in observations.get("faces", []):
            hull = polygon_mask(self.shape, face["hull"])
            if not hull.any():
                continue
            subject_id = None
            if labels is not None:
                votes = Counter(labels[hull].tolist())
                best, total = max(
                    ((id, votes[id]) for id in active), key=lambda x: x[1], default=(None, 0)
                )
                if total / hull.sum() >= 0.5:
                    subject_id = best
                else:
                    x0, y0, x1, y1 = face["box"]
                    matched = {
                        id
                        for id, pose in associated_poses
                        if any(
                            p["part"] == "face"
                            and p["confidence"] >= self.policy["landmark_confidence"]
                            and x0 <= p["x"] <= x1
                            and y0 <= p["y"] <= y1
                            for p in pose["points"]
                        )
                    }
                    if len(matched) == 1:
                        subject_id = matched.pop()
            if subject_id is None:
                self.add(
                    "unbound_face",
                    "WARNING",
                    frame,
                    frame + 1,
                    None,
                    "Face evidence has no reliable cast association; detector output does not choose a character.",
                    confidence=face.get("confidence"),
                    box=face["box"],
                    reviewable=True,
                    resolutions=["preserve_background", "false_detection", "requires_replacement"],
                )
                continue
            selected = labels == subject_id
            critical = any(
                e["subject_id"] == subject_id and e["frame"] == frame
                for e in self.policy["critical_frames"]
            )
            threshold = self.policy["critical_hull_coverage" if critical else "face_hull_coverage"]
            coverage = float(selected[hull].mean())
            self.parts_seen[subject_id].add("face")
            metrics = {
                "subject_id": subject_id,
                "hull_area": int(hull.sum()),
                "hull_coverage": coverage,
                "hull_threshold": threshold,
                "population": "critical" if critical else "broad",
            }
            if coverage < threshold:
                self.add(
                    "face_hull_coverage",
                    "BLOCKED" if critical else "WARNING",
                    frame,
                    frame + 1,
                    subject_id,
                    "Detected face-hull coverage is below its configured population threshold.",
                    measurements=metrics,
                    confidence=face.get("confidence"),
                    box=face["box"],
                    reviewable=not critical,
                    resolutions=["inspected", "false_detection", "requires_replacement"]
                    if not critical
                    else [],
                )
            # Shrink the measurement polygon, not the subject mask, to avoid interpreting
            # convex-hull background gaps as confirmed facial RGB. This never edits media.
            center = np.mean(face["hull"], axis=0)
            core = polygon_mask(
                self.shape,
                [(center + 0.75 * (np.array(p) - center)).tolist() for p in face["hull"]],
            )
            metrics.update(
                self.pixel_evidence(
                    frame,
                    subject_id,
                    selected,
                    source,
                    depth,
                    composite,
                    conditioning,
                    "face",
                    core,
                    threshold,
                    confidence=face.get("confidence"),
                    box=face["box"],
                )
            )
            face_metrics.append(metrics)

        region_metrics = []
        for region in self.recipe.get("quality_regions", []):
            if not region["start"] <= frame < region["end"]:
                continue
            roi = region_mask(self.shape, region["box"])
            id, part = region["subject_id"], region["part"]
            if region["disposition"] == "uncertain":
                continue  # One explicit required decision is added for the entire source range.
            if region["disposition"] == "preserve":
                covered = (
                    float((labels[roi] != 0).mean()) if labels is not None and roi.any() else 0
                )
                region_metrics.append(
                    {
                        "part": part,
                        "subject_id": id,
                        "box": region["box"],
                        "disposition": "preserve",
                        "selection": covered,
                    }
                )
                if covered > self.policy["background_selection"]:
                    self.add(
                        "background_contamination",
                        "BLOCKED",
                        frame,
                        frame + 1,
                        id,
                        "A source-reviewed background/preserved region is selected as foreground.",
                        measurements={
                            "selection": covered,
                            "threshold": self.policy["background_selection"],
                        },
                        box=region["box"],
                    )
                continue
            if id not in active:
                self.add(
                    "unassigned_replacement",
                    "BLOCKED",
                    frame,
                    frame + 1,
                    id,
                    "Source evidence requires replacement, but its cast is not assigned and visible here.",
                    box=region["box"],
                )
            selected = labels == id if labels is not None else None
            measurements = self.pixel_evidence(
                frame,
                id,
                selected,
                source,
                depth,
                composite,
                conditioning,
                "face" if part == "reflection" else part,
                roi,
                self.policy["critical_hull_coverage"]
                if part in {"face", "reflection"}
                else self.policy["anatomy_coverage"],
                box=region["box"],
                provenance="source-reviewed reference region",
            )
            region_metrics.append(
                {**measurements, "subject_id": id, "box": region["box"], "disposition": "replace"}
            )
            if id in self.parts_seen:
                self.parts_seen[id].add(part)

        # Compositing attribution is measured on exact output, including non-face anatomy.
        if labels is not None and depth is not None:
            for selected, target, code in [
                (labels > 0, depth, "foreground_guide_mismatch"),
                (labels == 0, source, "background_rgb_mismatch"),
            ]:
                if selected.any():
                    mae = float(
                        np.abs(
                            composite[selected].astype(float) - target[selected].astype(float)
                        ).mean()
                    )
                    if mae > self.policy["structural_mae"]:
                        self.add(
                            code,
                            "BLOCKED",
                            frame,
                            frame + 1,
                            None,
                            "Composite pixels differ from their expected source/guide attribution.",
                            measurements={"mae": mae, "threshold": self.policy["structural_mae"]},
                        )
        self.frames.append(
            {
                "frame": frame,
                "timestamp": frame / 24,
                "active_subjects": active,
                "mask_areas": {id: int((labels == id).sum()) for id in active}
                if labels is not None
                else {},
                "present_labels": sorted(present),
                "faces": face_metrics,
                "source_regions": region_metrics,
                "detected_faces": len(observations.get("faces", [])),
                "detected_poses": len(observations.get("poses", [])),
            }
        )

    def finish(self):
        if len(self.frames) != self.count:
            self.add(
                "incomplete_frame_audit",
                "BLOCKED",
                0,
                self.count,
                None,
                "Not every normalized frame was decoded and validated.",
                measurements={"expected": self.count, "audited": len(self.frames)},
            )
        assigned = np.zeros(self.count, bool)
        for subject in self.recipe["subjects"]:
            for span in intervals(subject, self.count):
                assigned[span["start"] : span["end"]] = True
            for note in subject.get("visibility", []):
                if note["state"] in {"absent", "fully_occluded"}:
                    self.add(
                        "reviewed_visibility",
                        "REVIEWED",
                        note["start"],
                        note["end"],
                        subject["id"],
                        note["reason"],
                        measurements={"state": note["state"]},
                    )
            for span in visible_spans(subject, self.count):
                seen = sorted(self.parts_seen[subject["id"]])
                self.add(
                    "whole_person_visual_review",
                    "WARNING",
                    span["start"],
                    span["end"],
                    subject["id"],
                    "Inspect head, hair, neck, torso, arms, hands and visible limbs across this span. "
                    "Face/pose interiors cannot certify the whole silhouette or occlusion edges.",
                    measurements={
                        "parts_observed_by_checks": seen,
                        "requires_visual_review": sorted(PARTS),
                    },
                    reviewable=True,
                    resolutions=["inspected", "requires_replacement"],
                )
        for start, end in contiguous_ranges(np.flatnonzero(~assigned).tolist()):
            self.add(
                "unassigned_span",
                "BLOCKED",
                start,
                end,
                None,
                "No cast is assigned here. Review source visibility and decide whether appearance needs replacement.",
                reviewable=True,
                resolutions=["preserve_background", "inspected", "requires_replacement"],
            )
        for region in self.recipe.get("quality_regions", []):
            if region["disposition"] == "uncertain":
                self.add(
                    "appearance_decision",
                    "BLOCKED",
                    region["start"],
                    region["end"],
                    region["subject_id"],
                    region["reason"],
                    box=region["box"],
                    reviewable=True,
                    resolutions=["preserve_background", "requires_replacement"],
                )
        self.findings = group_warnings(self.findings)
        return {
            "version": REPORT_VERSION,
            "binding": self.binding,
            "policy": self.policy,
            "detectors": self.detectors,
            "frames": self.frames,
            "findings": self.findings,
            **summarize(self.findings),
        }


def contiguous_ranges(frames):
    if not frames:
        return []
    result, start, previous = [], frames[0], frames[0]
    for frame in frames[1:]:
        if frame != previous + 1:
            result.append((start, previous + 1))
            start = frame
        previous = frame
    return [*result, (start, previous + 1)]


def group_warnings(findings):
    """Keep per-frame evidence while making contiguous inspection decisions practical."""
    groups, result = {}, []
    for entry in findings:
        if entry["status"] != "WARNING" or entry["code"] == "whole_person_visual_review":
            result.append(entry)
            continue
        box = entry.get("box")
        location = tuple(round((box[i] + box[i + 2]) / 2, 1) for i in (0, 1)) if box else None
        key = (entry["code"], entry["subject_id"], entry["measurements"].get("part"), location)
        previous = groups.get(key)
        detail = {k: entry[k] for k in ("start", "end", "box", "confidence", "measurements")}
        if previous and entry["start"] <= previous["end"]:
            previous["end"] = max(previous["end"], entry["end"])
            previous["evidence"].append(detail)
        else:
            entry["evidence"] = [detail]
            groups[key] = entry
            result.append(entry)
        grouped = groups[key]
        identity = hashlib.sha256(json.dumps(key).encode()).hexdigest()[:16]
        grouped["id"] = (
            f"{grouped['code']}:{grouped['subject_id']}:{grouped['start']}:{grouped['end']}:{identity}"
        )
    return result


def apply_reviews(report, reviews):
    """Review overlays are immutable-report-bound; confirmed defects cannot be waived."""
    import copy

    result = copy.deepcopy(report)
    ids = [entry["id"] for entry in result["findings"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Quality evidence contains duplicate finding identities")
    for entry in result["findings"]:
        review = next((r for r in reviews if r["finding_id"] == entry["id"]), None)
        if not review:
            continue
        if not entry["reviewable"] or review["resolution"] not in entry["resolutions"]:
            raise ValueError("This finding needs correction; it cannot be manually waived")
        entry["original_status"] = entry["status"]
        entry["review"] = review
        entry["status"] = (
            "BLOCKED" if review["resolution"] == "requires_replacement" else "REVIEWED"
        )
    result.update(summarize(result["findings"]))
    return result
