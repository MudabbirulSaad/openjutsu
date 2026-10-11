"""Synthetic source/anatomy evidence exercises real quality checks without private media."""

import numpy as np
import pytest
from openjutsu.quality import PreparationAudit, apply_reviews, finding, group_warnings, region_mask

SHAPE = (96, 64)
FACE = [0.35, 0.12, 0.65, 0.30]
PERSON = [0.2, 0.05, 0.8, 0.95]


def test_grouped_anatomy_warnings_have_distinct_review_identities():
    evidence = [
        finding(
            "landmark",
            "WARNING",
            frame,
            frame + 1,
            1,
            "Uncertain anatomy",
            measurements={"part": part},
            reviewable=True,
            resolutions=["inspected"],
        )
        for frame in range(3)
        for part in ("hand", "leg")
    ]
    grouped = group_warnings(evidence)
    assert len(grouped) == 2 and len({f["id"] for f in grouped}) == 2
    assert all((f["start"], f["end"], len(f["evidence"])) == (0, 3, 3) for f in grouped)
    reviewed = apply_reviews(
        {"findings": grouped},
        [
            {
                "finding_id": grouped[0]["id"],
                "resolution": "inspected",
                "reason": "Hand evidence inspected",
            }
        ],
    )
    assert [f["status"] for f in reviewed["findings"]] == ["REVIEWED", "WARNING"]
    with pytest.raises(ValueError, match="duplicate"):
        apply_reviews({"findings": [grouped[0], grouped[0]]}, [])


def synthetic(*, clothing=False, gap=None, visibility=None, intervals=None, regions=None):
    recipe = {
        "subjects": [
            {
                "id": 1,
                "intervals": intervals or [{"start": 0, "end": 4}],
                "annotations": [],
                "visibility": visibility or [],
            }
        ],
        "quality_regions": regions
        if regions is not None
        else [
            {
                "start": 0,
                "end": 4,
                "subject_id": 1,
                "part": "face",
                "disposition": "replace",
                "box": FACE,
                "reason": "Known visible synthetic face interior",
            }
        ],
        "quality_policy": {"critical_frames": [{"subject_id": 1, "frame": 2}]},
    }
    source = np.full((4, *SHAPE, 3), [17, 83, 151], np.uint8)
    source[:, region_mask(SHAPE, FACE)] = [211, 127, 61]
    depth = np.full_like(source, [5, 233, 47])
    masks = np.zeros((4, *SHAPE), np.uint8)
    masks[:, region_mask(SHAPE, PERSON)] = 1
    if clothing:
        masks[:, region_mask(SHAPE, FACE)] = 0
    if gap is not None:
        masks[gap] = 0
    composite = np.where((masks > 0)[..., None], depth, source)
    return recipe, source, masks, depth, composite


def audit(data, *, observations=None, conditioning=None):
    recipe, source, masks, depth, composite = data
    checker = PreparationAudit(recipe, 4, SHAPE, {"artifacts": {}})
    for frame in range(4):
        checker.frame(
            frame,
            source[frame],
            masks[frame],
            depth[frame],
            composite[frame],
            (conditioning if conditioning is not None else composite)[frame],
            observations,
        )
    return checker.finish()


def codes(report, status="BLOCKED"):
    return {f["code"] for f in report["findings"] if f["status"] == status}


@pytest.mark.parametrize("frame", [2, 3])
def test_clothing_only_person_and_source_face_are_blocked(frame):
    data = synthetic(clothing=True)
    report = audit(data)
    assert {"incomplete_face", "source_face_rgb"} <= codes(report)
    assert any(f["start"] == frame and f["code"] == "source_face_rgb" for f in report["findings"])
    assert report["status"] == "BLOCKED" and not report["approval_ready"]


def test_corrected_coverage_has_no_false_critical_and_still_requires_silhouette_review():
    report = audit(synthetic())
    assert not codes(report)
    assert report["status"] == "WARNING" and not report["approval_ready"]
    assert "whole_person_visual_review" in codes(report, "WARNING")


def test_small_source_face_patch_is_not_hidden_by_whole_face_average():
    data = synthetic()
    conditioning = data[4].copy()
    conditioning[2, 15:18, 26:32] = data[1][2, 15:18, 26:32]
    report = audit(data, conditioning=conditioning)
    assert "source_face_patch" in codes(report)
    defect = next(f for f in report["findings"] if f["code"] == "source_face_patch")
    assert defect["measurements"]["conditioning_depth_mae"] < 12
    assert defect["measurements"]["source_like_pixels"] == 18
    assert not defect["reviewable"]


def test_closeup_pose_face_association_does_not_certify_whole_person():
    points = [
        {"part": "face", "x": x, "y": 0.2, "confidence": 0.99} for x in [0.4, 0.45, 0.5, 0.55]
    ]
    report = audit(synthetic(), observations={"faces": [], "poses": [{"points": points}]})
    assert "unbound_person" not in codes(report, "WARNING")
    assert "whole_person_visual_review" in codes(report, "WARNING")


def test_broad_profile_hull_uncertainty_needs_review_without_false_critical():
    face = {
        "hull": [[0.35, 0.12], [0.65, 0.12], [0.95, 0.22], [0.65, 0.3], [0.35, 0.3]],
        "box": [0.35, 0.12, 0.95, 0.3],
        "confidence": None,
    }
    data = synthetic(regions=[])
    data[0]["quality_policy"]["critical_frames"] = []
    report = audit(data, observations={"faces": [face], "poses": []})
    assert "face_hull_coverage" in codes(report, "WARNING")
    assert not codes(report) and not report["approval_ready"]


def test_missing_visible_subject_is_not_excused_by_another_label():
    data = synthetic(gap=2)
    data[0]["subjects"].append({"id": 2, "annotations": [], "intervals": [{"start": 0, "end": 4}]})
    data[2][:, :5, :5] = 2
    report = audit(data)
    assert "visible_subject_gap" in codes(report)
    assert any(
        f["subject_id"] == 1 and f["start"] == 2 and f["code"] == "visible_subject_gap"
        for f in report["findings"]
    )


def test_reviewed_full_occlusion_is_valid_but_partial_occlusion_is_not_an_empty_exemption():
    note = {
        "start": 0,
        "end": 2,
        "state": "fully_occluded",
        "reason": "Synthetic person behind a car",
    }
    data = synthetic(visibility=[note], regions=[])
    data[2][:2] = 0
    data[4][:2] = data[1][:2]
    report = audit(data)
    assert not codes(report)
    assert any(
        f["code"] == "reviewed_visibility"
        and f["status"] == "REVIEWED"
        and f["message"] == note["reason"]
        for f in report["findings"]
    )
    note["state"] = "partially_occluded"
    assert "visible_subject_gap" in codes(audit(data))


def test_wrong_cast_id_and_mask_outside_interval_are_blocked():
    data = synthetic(intervals=[{"start": 0, "end": 3}], regions=[])
    data[2][1, 20:30, 20:30] = 3
    assert "interval_identity" in codes(audit(data))


def test_unassigned_span_is_a_required_casting_decision_not_physical_absence():
    data = synthetic(intervals=[{"start": 0, "end": 1}], regions=[])
    data[2][1:] = 0
    report = audit(data)
    unresolved = next(f for f in report["findings"] if f["code"] == "unassigned_span")
    assert unresolved["status"] == "BLOCKED" and unresolved["reviewable"]
    assert (unresolved["start"], unresolved["end"]) == (1, 4)
    reviewed = apply_reviews(
        report,
        [
            {
                "finding_id": unresolved["id"],
                "resolution": "preserve_background",
                "reason": "Only a synthetic background prop is visible",
            }
        ],
    )
    assert "unassigned_span" not in codes(reviewed)
    replacement = apply_reviews(
        report,
        [
            {
                "finding_id": unresolved["id"],
                "resolution": "requires_replacement",
                "reason": "Visible intended synthetic character needs binding",
            }
        ],
    )
    assert "unassigned_span" in codes(replacement)


def test_confirmed_face_defects_cannot_be_manually_waived():
    report = audit(synthetic(clothing=True))
    defect = next(f for f in report["findings"] if f["code"] == "source_face_rgb")
    with pytest.raises(ValueError, match="cannot be manually waived"):
        apply_reviews(
            report,
            [{"finding_id": defect["id"], "resolution": "inspected", "reason": "Just accept it"}],
        )


def test_background_face_detection_is_uncertain_and_does_not_assign_foreground_by_default():
    data = synthetic(regions=[])
    observations = {
        "poses": [],
        "faces": [
            {
                "box": [0.01, 0.01, 0.1, 0.1],
                "hull": [[0.01, 0.01], [0.1, 0.01], [0.1, 0.1], [0.01, 0.1]],
                "confidence": None,
            }
        ],
    }
    report = audit(data, observations=observations)
    assert not codes(report)
    unbound = [f for f in report["findings"] if f["code"] == "unbound_face"]
    assert unbound and all(f["subject_id"] is None for f in unbound)
    assert all(f["confidence"] is None for f in unbound), "Do not invent detector confidence"


def test_explicit_background_region_catches_wrong_selection():
    data = synthetic(
        regions=[
            {
                "start": 0,
                "end": 4,
                "subject_id": None,
                "part": "background",
                "disposition": "preserve",
                "box": [0.01, 0.01, 0.1, 0.1],
                "reason": "Verified synthetic background",
            }
        ]
    )
    data[2][:, region_mask(SHAPE, [0.01, 0.01, 0.1, 0.1])] = 1
    assert "background_contamination" in codes(audit(data))


def test_corrupt_conditioning_cannot_pass_even_with_complete_face_mask():
    data = synthetic()
    assert "source_face_rgb" in codes(audit(data, conditioning=data[1]))


def test_face_detection_does_not_certify_hair_neck_or_limbs():
    face = {
        "box": FACE,
        "hull": [[0.35, 0.12], [0.65, 0.12], [0.65, 0.30], [0.35, 0.30]],
        "confidence": None,
    }
    report = audit(synthetic(), observations={"faces": [face], "poses": []})
    assert not codes(report)
    assert not report["approval_ready"]
    anatomy = next(f for f in report["findings"] if f["code"] == "whole_person_visual_review")
    assert {"hair", "neck", "arm", "hand", "leg"} <= set(
        anatomy["measurements"]["requires_visual_review"]
    )


def test_non_face_anatomy_missing_is_blocked_by_source_reference_evidence():
    data = synthetic(
        regions=[
            {
                "start": 0,
                "end": 4,
                "subject_id": 1,
                "part": "hand",
                "disposition": "replace",
                "box": [0.25, 0.7, 0.35, 0.75],
                "reason": "Visible synthetic hand",
            }
        ]
    )
    data[2][:, region_mask(SHAPE, [0.25, 0.7, 0.35, 0.75])] = 0
    assert "incomplete_hand" in codes(audit(data))
