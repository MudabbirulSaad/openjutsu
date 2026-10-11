"""Unmarked local tracking contracts; original and Step 2 fixtures remain immutable."""

from hashlib import file_digest

import numpy as np
import pytest
from openjutsu.tracking import intervals, tracking_report
from test_pilot_baseline import (
    test_quality_conditioning_face_is_structural_guide as assert_structural_face,
)
from test_pilot_baseline import test_quality_person_mask_covers_face as assert_face_coverage
from test_segmentation_candidate import roi


@pytest.mark.parametrize("frame", range(160, 192))
def test_entrance_visibility_is_explicit_and_visible_frames_have_the_right_id(
    tracking_fixture, frame
):
    metadata, arrays = tracking_fixture
    subject = next(s for s in metadata["recipe"]["subjects"] if s["id"] == 3)
    index = metadata["frame_ids"].index(frame)
    mask = arrays["masks"][index]
    assert set(np.unique(mask)) <= {0, 3}
    if frame < 167:
        assert not mask.any()
        assert any(
            n["start"] <= frame < n["end"] and n["state"] == "fully_occluded" and n["reason"]
            for n in subject["visibility"]
        )
    else:
        assert (mask == 3).any(), f"Visible subject missing at {frame}"


@pytest.mark.parametrize("defect", ["car-pillar-169", "hair-186"])
def test_known_entrance_defects_are_corrected(tracking_fixture, defect):
    metadata, arrays = tracking_fixture
    if defect == "car-pillar-169":
        index = metadata["frame_ids"].index(169)
        contamination = float((arrays["masks"][index, 438:445, 257:262] == 3).mean())
        assert contamination == 0, f"Car pillar labelled as person: {contamination:.2%}"
    else:
        index = metadata["frame_ids"].index(186)
        box = metadata["anatomy_probes"]["186"]["hair"]
        coverage = float((arrays["masks"][index][roi(arrays["masks"].shape[1:], box)] == 3).mean())
        assert coverage == 1, f"Seed hair interior missing: {coverage:.2%}"


@pytest.mark.parametrize("frame", [167, 169, 171, 174, 180, 185, 186])
def test_visible_anatomy_interiors_and_occluders(tracking_fixture, frame):
    metadata, arrays = tracking_fixture
    mask = arrays["masks"][metadata["frame_ids"].index(frame)] == 3
    for name, box in metadata["anatomy_probes"][str(frame)].items():
        actual = float(mask[roi(mask.shape, box)].mean())
        expected = 0 if name in {"car_panel", "car_pillar", "bag"} else 1
        assert actual == expected, f"f{frame} {name}: {actual:.2%} (expected {expected:.0%})"
    # These are interior/exclusion probes, not full-body ground truth. Native-source,
    # silhouette and conditioning review are required, especially before f186.


@pytest.mark.parametrize("frame", [230, 260])
def test_step2_face_and_conditioning_contracts_remain_satisfied(tracking_fixture, frame):
    assert_face_coverage(tracking_fixture, frame)
    assert_structural_face(tracking_fixture, frame)


def test_all_masks_outside_entrance_are_byte_identical_to_step2(tracking_fixture):
    metadata, _ = tracking_fixture
    with open(metadata["candidate_mask_path"], "rb") as stream:
        assert (
            file_digest(stream, "sha256").hexdigest() == metadata["candidate_hashes"]["mask_data"]
        )
    current = np.load(metadata["candidate_mask_path"], mmap_mode="r", allow_pickle=False)
    step2 = np.load(metadata["original_mask_path"], mmap_mode="r", allow_pickle=False)
    assert np.array_equal(current[:160], step2[:160])
    assert np.array_equal(current[192:], step2[192:])
    for frame in (230, 242, 260, 280):
        assert np.array_equal(current[frame], step2[frame])
    report = tracking_report(current, metadata["recipe"]["subjects"])
    assert report["unassigned_frames"] == [374, 375, 376, 377]
    assert all(s["missing_frames"] == [] for s in report["subjects"].values())


def test_boundary_sides_are_in_evidence_and_no_labels_escape_binding(tracking_fixture):
    metadata, arrays = tracking_fixture
    subjects = metadata["recipe"]["subjects"]
    for subject in subjects:
        for span in intervals(subject, 432):
            for frame in (span["start"] - 1, span["start"], span["end"] - 1, span["end"]):
                if 0 <= frame < 432:
                    assert frame in metadata["frame_ids"], f"Boundary evidence absent: {frame}"
    for index, frame in enumerate(metadata["frame_ids"]):
        allowed = {
            0,
            *[
                s["id"]
                for s in subjects
                if any(i["start"] <= frame < i["end"] for i in intervals(s, 432))
            ],
        }
        assert set(np.unique(arrays["masks"][index])) <= allowed


def test_detectable_entrance_faces_are_covered_and_blind_spots_are_recorded(tracking_fixture):
    metadata, _ = tracking_fixture
    records = metadata["face_hull_audit"]
    assert metadata["face_audit_crop"] == [200, 380, 400, 650]
    assert [r["frame"] for r in records] == list(range(160, 192))
    assert [r["frame"] for r in records if r["face"]] == list(range(186, 192))
    assert all(r["face"]["coverage"] == 1 for r in records if r["face"])
    # Detection failure before 186 is not absence evidence and does not waive review.
