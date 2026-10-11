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
