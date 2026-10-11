"""Opt-in tests of the immutable failed pilot. --runxfail exposes the quality failures."""

import numpy as np
import pytest


def face_mask(fixture, frame):
    metadata, arrays = fixture
    index = metadata["frame_ids"].index(frame)
    probe = next(p for p in metadata["face_probes"] if p["frame"] == frame)
    height, width = arrays["masks"].shape[1:]
    x0, y0, x1, y1 = probe["manual_face_roi"]
    roi = np.zeros((height, width), dtype=bool)
    roi[int(y0 * height) : int(y1 * height), int(x0 * width) : int(x1 * width)] = True
    return index, roi


@pytest.mark.parametrize("frame,pixels", [(230, 203379), (260, 205727)])
def test_saved_initial_clothing_masks_match_diagnostic(pilot_fixture, frame, pixels):
    metadata, arrays = pilot_fixture
    index, roi = face_mask(pilot_fixture, frame)
    selected = arrays["masks"][index] == metadata["subject_id"]
    replay = next(r for r in metadata["original_sam_replay"] if r["frame"] == frame)
    assert selected.sum() == pixels == replay["initial_mask_pixels"]
    assert replay["changed_pixels"] == 0 and replay["replayed_initial_iou_to_saved"] == 1
    assert replay["initial_not_tracked"]
    assert not selected[roi].any(), "Known clothing-only mask no longer reproduced"


def test_saved_seven_frame_gap_matches_tracking_report(pilot_fixture):
    metadata, arrays = pilot_fixture
    for frame in range(160, 167):
        index = metadata["frame_ids"].index(frame)
        assert any(s["start"] <= frame < s["end"] for s in metadata["intervals"])
        assert frame in metadata["original_tracking"]["empty_frames"]
        assert not arrays["masks"][index].any()


def test_saved_empty_masks_leave_whole_source_frame_in_conditioning(pilot_fixture):
    metadata, arrays = pilot_fixture
    for frame in range(160, 167):
        index = metadata["frame_ids"].index(frame)
        source = arrays["normalized"][index].astype(np.float32)
        conditioning = arrays["conditioning"][index].astype(np.float32)
        error = float(np.abs(conditioning - source).mean())
        assert error < 5, f"frame {frame}: source RGB no longer reproduced, MAE={error:.4f}"


@pytest.mark.parametrize("frame", [230, 260])
def test_saved_conditioning_contains_source_face_rgb(pilot_fixture, frame):
    _, arrays = pilot_fixture
    index, roi = face_mask(pilot_fixture, frame)
    source = arrays["normalized"][index].astype(np.float32)
    conditioning = arrays["conditioning"][index].astype(np.float32)
    depth = arrays["depth"][index].astype(np.float32)
    source_error = float(np.abs(conditioning[roi] - source[roi]).mean())
    depth_error = float(np.abs(conditioning[roi] - depth[roi]).mean())
    print(f"frame {frame}: source RGB MAE={source_error:.4f}/255, depth MAE={depth_error:.4f}/255")
    assert source_error < 5, "Source appearance no longer reproduced (codec tolerance 5/255)"
    assert depth_error > 20, "ROI does not distinguish leaked RGB from the depth guide"


@pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="Baseline: clothing excludes the face"
)
@pytest.mark.parametrize("frame", [230, 260])
def test_quality_person_mask_covers_face(pilot_fixture, frame):
    metadata, arrays = pilot_fixture
    index, roi = face_mask(pilot_fixture, frame)
    coverage = float((arrays["masks"][index][roi] == metadata["subject_id"]).mean())
    assert coverage >= 0.95, f"frame {frame}: face coverage {coverage:.1%}, require >=95%"


@pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="Baseline: visible subject has no mask"
)
def test_quality_active_subject_has_masks_at_entrance(pilot_fixture):
    metadata, arrays = pilot_fixture
    missing = [
        f for f in range(160, 167) if not arrays["masks"][metadata["frame_ids"].index(f)].any()
    ]
    assert not missing, f"Visible selected subject has no mask on frames {missing}"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Baseline: original face survives")
@pytest.mark.parametrize("frame", [230, 260])
def test_quality_conditioning_face_is_structural_guide(pilot_fixture, frame):
    _, arrays = pilot_fixture
    index, roi = face_mask(pilot_fixture, frame)
    conditioning = arrays["conditioning"][index].astype(np.float32)
    depth = arrays["depth"][index].astype(np.float32)
    error = float(np.abs(conditioning[roi] - depth[roi]).mean())
    assert error < 5, f"frame {frame}: face/depth MAE {error:.4f}/255, original RGB leaked"
