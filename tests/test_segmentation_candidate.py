"""Real candidate contracts, deliberately unmarked; immutable Step 1 failures remain separate."""

from hashlib import file_digest

import numpy as np
import pytest
from test_pilot_baseline import (
    test_quality_conditioning_face_is_structural_guide as assert_structural_face,
)
from test_pilot_baseline import test_quality_person_mask_covers_face as assert_face_coverage


def roi(shape, box):
    height, width = shape
    x0, y0, x1, y1 = box
    return np.s_[int(y0 * height) : int(y1 * height), int(x0 * width) : int(x1 * width)]


@pytest.mark.parametrize("frame", [230, 260])
def test_step1_face_and_conditioning_contracts_pass_on_candidate(candidate_fixture, frame):
    assert_face_coverage(candidate_fixture, frame)
    assert_structural_face(candidate_fixture, frame)


@pytest.mark.parametrize("frame", [230, 242, 260, 280])
def test_anatomical_interiors_covered_and_background_probe_excluded(candidate_fixture, frame):
    metadata, arrays = candidate_fixture
    index = metadata["frame_ids"].index(frame)
    mask = arrays["masks"][index] == 3
    for name, box in metadata["anatomy_probes"][str(frame)].items():
        coverage = float(mask[roi(mask.shape, box)].mean())
        if name == "background":
            assert coverage < 0.005, f"f{frame}: background contamination {coverage:.2%}"
        else:
            assert coverage == 1, f"f{frame}: {name} interior coverage {coverage:.2%}"
    # Interior probes supplement the full silhouette review; they cannot certify flyaway
    # strands, occluded/off-frame limbs, or pixel-accurate ground truth by themselves.


@pytest.mark.parametrize("frame", [242, 280])
def test_previously_correct_control_masks_remain_close(candidate_fixture, frame):
    metadata, arrays = candidate_fixture
    index = metadata["frame_ids"].index(frame)
    current, previous = arrays["masks"][index] == 3, arrays["previous_masks"][index] == 3
    iou = float((current & previous).sum() / (current | previous).sum())
    assert iou >= 0.99, f"f{frame}: previously correct mask changed substantially (IoU {iou:.6f})"


def test_full_candidate_preserves_other_intervals_and_has_no_new_label_gap(candidate_fixture):
    metadata, _ = candidate_fixture
    with open(metadata["candidate_mask_path"], "rb") as stream:
        assert (
            file_digest(stream, "sha256").hexdigest() == metadata["candidate_hashes"]["mask_data"]
        )
    current = np.load(metadata["candidate_mask_path"], mmap_mode="r", allow_pickle=False)
    previous = np.load(metadata["original_mask_path"], mmap_mode="r", allow_pickle=False)
    begin, end = metadata["corrected_interval"]["start"], metadata["corrected_interval"]["end"]
    assert np.array_equal(current[:begin], previous[:begin])
    assert np.array_equal(current[end:], previous[end:])
    assert set(np.unique(current[begin:end])) == {0, 3}
    assert (current[begin:end].reshape(end - begin, -1).max(axis=1) == 3).all()
    assert not current[160:167].any(), "Step 3's original gap must remain separately documented"


def test_detected_face_hulls_remain_covered_across_changed_interval(candidate_fixture):
    metadata, _ = candidate_fixture
    records = metadata["face_hull_audit"]
    assert len(records) == 104
    detected = [r for r in records if r["face"]]
    assert len(detected) == 100
    assert all(r["face"]["coverage"] >= 0.995 for r in detected)
    # The detected convex hull crosses background gaps between hair and cheek. In f260,
    # the 28 excluded hull pixels were inspected at x492..511/y419..457 and are background,
    # not leaked facial pixels. Filling that polygon to 100% would contaminate the mask.
    assert all(
        next(r for r in detected if r["frame"] == frame)["face"]["coverage"] >= 0.999
        for frame in (230, 260)
    )
    assert [r["frame"] for r in records if not r["face"]] == [218, 219, 220, 221]
