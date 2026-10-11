"""Frame intervals are local to the normalized clip; ends are exclusive."""


def intervals(subject, count):
    return subject.get("intervals") or [{"start": 0, "end": count}]


def validate_bindings(recipe):
    count = round((recipe["end"] - recipe["start"]) * 24)
    for subject in recipe["subjects"]:
        spans = intervals(subject, count)
        anchors = [a for a in subject["annotations"] if a["points"] or a.get("box")]
        for span in spans:
            if not any(span["start"] <= a["frame"] < span["end"] for a in anchors):
                raise ValueError(f"Anchor {subject['name']} inside every tracking interval")
        if any(not any(s["start"] <= a["frame"] < s["end"] for s in spans) for a in anchors):
            raise ValueError("A correction anchor is outside its subject's tracking intervals")


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
    first = anchors[0] - span["start"]
    state = predictor.init_state(str(shot), offload_video_to_cpu=True, offload_state_to_cpu=True)

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
            yield from predictor.propagate_in_video(state, start_frame_idx=first, reverse=reverse)

    add(anchors[0])
    # Reach every correction frame in both directions before adding its prompts.
    # The warm-up predictions stay in SAM state, not in the exported label plane.
    if len(anchors) > 1:
        for _ in propagate():
            pass
        for frame in anchors[1:]:
            add(frame)
    yield from propagate()


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
