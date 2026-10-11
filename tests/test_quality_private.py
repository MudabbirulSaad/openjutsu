"""Opt-in measurements from immutable old evidence and the normal isolated Engine path."""

from pathlib import Path

import numpy as np
import pytest
from openjutsu.media import digest
from openjutsu.quality import REPORT_VERSION, PreparationAudit, region_mask


@pytest.mark.parametrize("frame", [230, 260])
def test_original_clothing_only_evidence_is_blocked_by_real_validator(pilot_fixture, frame):
    meta, arrays = pilot_fixture
    index = meta["frame_ids"].index(frame)
    probe = next(p for p in meta["face_probes"] if p["frame"] == frame)
    recipe = {
        "subjects": [{"id": 3, "intervals": meta["intervals"]}],
        "quality_regions": [
            {
                "start": frame,
                "end": frame + 1,
                "subject_id": 3,
                "part": "face",
                "disposition": "replace",
                "box": probe["manual_face_roi"],
                "reason": "Preserved source-reviewed diagnostic face interior",
            }
        ],
    }
    checker = PreparationAudit(recipe, 432, arrays["masks"].shape[1:], {})
    checker.frame(
        frame,
        arrays["normalized"][index],
        arrays["masks"][index],
        arrays["depth"][index],
        arrays["conditioning"][index],
        arrays["conditioning"][index],
    )
    defects = {f["code"] for f in checker.findings if f["status"] == "BLOCKED"}
    assert {"incomplete_face", "source_face_rgb"} <= defects


@pytest.mark.parametrize("frame", [230, 242, 260, 280])
def test_corrected_step2_evidence_has_no_false_critical_errors(candidate_fixture, frame):
    meta, arrays = candidate_fixture
    index = meta["frame_ids"].index(frame)
    regions = []
    for part, box in meta["anatomy_probes"][str(frame)].items():
        regions.append(
            {
                "start": frame,
                "end": frame + 1,
                "subject_id": 3,
                "part": "arm" if "sleeve" in part else part,
                "disposition": "preserve" if part == "background" else "replace",
                "box": box,
                "reason": "Source-reviewed anatomical interior from Step 2",
            }
        )
    recipe = {"subjects": [{"id": 3, "intervals": meta["intervals"]}], "quality_regions": regions}
    checker = PreparationAudit(recipe, 432, arrays["masks"].shape[1:], {})
    checker.frame(
        frame,
        arrays["normalized"][index],
        arrays["masks"][index],
        arrays["depth"][index],
        arrays["conditioning"][index],
        arrays["conditioning"][index],
    )
    assert not [f for f in checker.findings if f["status"] == "BLOCKED"]


def test_normal_engine_audits_all_frames_and_blocks_unassigned_replacement(quality_fixture):
    report, records = quality_fixture
    assert report["version"] == REPORT_VERSION
    assert len({f["id"] for f in report["findings"]}) == len(report["findings"])
    assert [f["frame"] for f in report["frames"]] == list(range(432))
    assert not report["approval_ready"]
    assert any(f["code"] == "appearance_decision" and f["start"] == 374 for f in report["findings"])
    assert any(
        f["code"] == "reviewed_visibility" and f["start"] == 160 and f["end"] == 167
        for f in report["findings"]
    )
    for kind, bound in report["binding"]["artifacts"].items():
        assert digest(records[kind]["path"]) == bound["hash"]


@pytest.mark.parametrize("frame", [167, 169, 171, 174, 180, 185, 186, 191, 230, 242, 260, 280])
def test_normal_engine_preserves_accepted_step3_masks_and_anatomical_probes(
    quality_fixture, tracking_fixture, frame
):
    report, records = quality_fixture
    meta, arrays = tracking_fixture
    masks = np.load(Path(records["mask_data"]["path"]), mmap_mode="r", allow_pickle=False)
    index = meta["frame_ids"].index(frame)
    np.testing.assert_array_equal(masks[frame], arrays["masks"][index])
    for part, box in meta["anatomy_probes"].get(str(frame), {}).items():
        selected = masks[frame][region_mask(masks.shape[1:], box)] == 3
        if part == "background":
            assert selected.mean() < report["policy"]["background_selection"]
        else:
            assert selected.mean() == (0 if part in {"bag", "car_panel", "car_pillar"} else 1)
    assert not any(
        f["status"] == "BLOCKED" and f["subject_id"] == 3 and f["start"] <= frame < f["end"]
        for f in report["findings"]
    )


@pytest.mark.parametrize("frame", [230, 260])
def test_critical_face_population_passes_in_exact_normal_conditioning(quality_fixture, frame):
    report, _ = quality_fixture
    metrics = next(f for f in report["frames"][frame]["faces"] if f["subject_id"] == 3)
    assert metrics["population"] == "critical" and metrics["hull_threshold"] == 0.999
    assert metrics["hull_coverage"] >= 0.999 and metrics["coverage"] == 1
    assert metrics["conditioning_depth_mae"] < 5 < metrics["conditioning_source_mae"]
