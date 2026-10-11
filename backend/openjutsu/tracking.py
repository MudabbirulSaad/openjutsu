"""Frame intervals are local to the normalized clip; ends are exclusive."""


def intervals(subject, count):
    return subject.get("intervals") or [{"start": 0, "end": count}]


def visible_spans(subject, count):
    """Split state at declared absence/full occlusion; keep the cast intervals intact."""
    excluded = [
        note
        for note in subject.get("visibility", [])
        if note["state"] in {"absent", "fully_occluded"}
    ]
    result = []
    for span in intervals(subject, count):
        begin = span["start"]
        for note in excluded:
            if span["start"] <= note["start"] < note["end"] <= span["end"]:
                if begin < note["start"]:
                    result.append({"start": begin, "end": note["start"]})
                begin = note["end"]
        if begin < span["end"]:
            result.append({"start": begin, "end": span["end"]})
    return result


def validate_bindings(recipe):
    count = round((recipe["end"] - recipe["start"]) * 24)
    for subject in recipe["subjects"]:
        spans = visible_spans(subject, count)
        anchors = [a for a in subject["annotations"] if a["points"] or a.get("box")]
        for span in spans:
            if not any(span["start"] <= a["frame"] < span["end"] for a in anchors):
                raise ValueError(
                    f"Anchor {subject['name']} inside every tracking interval's visible span"
                )
        if any(not any(s["start"] <= a["frame"] < s["end"] for s in spans) for a in anchors):
            raise ValueError(
                "A correction anchor is outside its subject's visible tracking intervals"
            )
        seed = subject.get("seed_frame")
        if seed is not None and not any(a["frame"] == seed for a in anchors):
            raise ValueError("The seed frame must have a visible subject annotation")


MASK_COLORS = [[0, 0, 0], [230, 190, 40], [40, 150, 250], [185, 100, 230]]


def sam2_track_interval(predictor, shot, subject, span, width, height):
    """Seed one person, track, then apply later prompts as contextual corrections.

    The predictor must retain correction frames as conditioning frames. Keeping all
    prompts as independent initial predictions discards the tracked person's context.
    No mask growth, semantic inference, or cross-interval state reuse happens here.
    """
    import numpy as np

    grouped = {}
    for annotation in subject["annotations"]:
        if not span["start"] <= annotation["frame"] < span["end"]:
            continue
        if not annotation["points"] and not annotation.get("box"):
            continue
        anchor = grouped.setdefault(annotation["frame"], {"points": [], "box": None})
        anchor["points"].extend(annotation["points"])
        if annotation.get("box"):
            if anchor["box"] and list(anchor["box"]) != list(annotation["box"]):
                raise ValueError("Conflicting boxes on the same correction frame")
            anchor["box"] = annotation["box"]
    if not grouped:
        raise ValueError("Anchor the person inside each SAM tracking interval")
    anchors = sorted(grouped)
    seed = subject.get("seed_frame")
    if seed is None or not span["start"] <= seed < span["end"]:
        seed = anchors[0]
    if seed not in grouped:
        raise ValueError("The seed frame must have a visible subject annotation")
    first = seed - span["start"]
    state = predictor.init_state(str(shot), offload_video_to_cpu=True, offload_state_to_cpu=True)
    if state.get("num_frames", span["end"] - span["start"]) != span["end"] - span["start"]:
        raise ValueError("SAM input frame count does not match the tracking interval")

    def add(frame):
        annotation = grouped[frame]
        points = np.array(
            [[p["x"] * width, p["y"] * height] for p in annotation["points"]],
            dtype=np.float32,
        )
        box = (
            np.array(annotation["box"]) * [width, height, width, height]
            if annotation["box"]
            else None
        )
        predictor.add_new_points_or_box(
            state,
            frame - span["start"],
            subject["id"],
            points=points if len(points) else None,
            labels=np.array([int(p["include"]) for p in annotation["points"]])
            if len(points)
            else None,
            box=box,
        )

    def propagate():
        for reverse in (False, True):
            if reverse and first == 0:
                continue
            for index, ids, logits in predictor.propagate_in_video(
                state, start_frame_idx=first, reverse=reverse
            ):
                if not 0 <= index < span["end"] - span["start"]:
                    raise ValueError("SAM frame index is outside its tracking interval")
                if list(ids) != [subject["id"]] or len(logits) != 1:
                    raise ValueError("SAM returned an unexpected subject identity")
                yield index, ids, logits

    add(seed)
    # Reach every correction frame in both directions before adding its prompts.
    # The warm-up predictions stay in SAM state, not in the exported label plane.
    if len(anchors) > 1:
        for _ in propagate():
            pass
        for frame in [a for a in anchors if a != seed]:
            add(frame)
    yield from propagate()


def merge_subject_mask(plane, selected, subject_id, frame):
    """Replace this subject atomically; ambiguous overlap needs an annotation correction."""
    import numpy as np

    selected = np.asarray(selected, dtype=bool)
    if selected.shape != plane.shape or not 1 <= subject_id <= 3:
        raise ValueError("Invalid subject mask shape or identity")
    collision = selected & (plane != 0) & (plane != subject_id)
    if collision.any():
        others = np.unique(plane[collision]).tolist()
        raise ValueError(
            f"Mask collision on frame {frame}: subject {subject_id} overlaps subjects {others} "
            f"on {int(collision.sum())} pixels; correct the annotations"
        )
    plane[plane == subject_id] = 0
    plane[selected] = subject_id


def tracking_report(masks, subjects):
    """Check each expected visible cast member, even when another label is present."""
    import numpy as np

    count = len(masks)
    details = {}
    assigned = np.zeros(count, dtype=bool)
    for subject in subjects:
        expected = np.zeros(count, dtype=bool)
        for span in visible_spans(subject, count):
            expected[span["start"] : span["end"]] = True
        for span in intervals(subject, count):
            assigned[span["start"] : span["end"]] = True
        present = (masks == subject["id"]).reshape(count, -1).any(axis=1)
        missing = np.flatnonzero(expected & ~present).tolist()
        if missing:
            raise ValueError(
                f"No subject mask on frames {missing[:20]} for subject {subject['id']}; "
                "add correction anchors or evidence of absence/occlusion"
            )
        if (present & ~expected).any():
            raise ValueError(f"Subject {subject['id']} mask outside visible tracking intervals")
        details[str(subject["id"])] = {
            "visible_spans": visible_spans(subject, count),
            "visibility": subject.get("visibility", []),
            "missing_frames": missing,
        }
    if not np.isin(masks, [0, *[s["id"] for s in subjects]]).all():
        raise ValueError("Mask contains an unbound subject identity")
    return {
        "frames": count,
        "empty_frames": np.flatnonzero(~masks.reshape(count, -1).any(axis=1)).tolist(),
        "unassigned_frames": np.flatnonzero(~assigned).tolist(),
        "intervals": {str(s["id"]): intervals(s, count) for s in subjects},
        "subjects": details,
    }


def save_masks(folder, masks):
    import os

    import numpy as np

    path = folder / "masks.npy"
    temporary = folder / ".masks.tmp"
    with temporary.open("wb") as stream:
        np.save(stream, masks, allow_pickle=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    return path


def load_masks(path):
    from pathlib import Path

    import numpy as np

    if Path(path).suffix == ".npy":
        return np.load(path, mmap_mode="r", allow_pickle=False)
    with np.load(path, allow_pickle=False) as archive:
        return archive["masks"]
