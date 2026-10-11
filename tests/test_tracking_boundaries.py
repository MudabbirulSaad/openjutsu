"""Synthetic worker regressions for interval visibility and cast-label collisions."""

import numpy as np
import pytest
from openjutsu import worker
from openjutsu.tracking import (
    load_masks,
    merge_subject_mask,
    sam2_track_interval,
    tracking_report,
    validate_bindings,
    visible_spans,
)
from openjutsu.types import Recipe
from test_preparation_baseline import COUNT, predicted_masks, run_mask
from test_preparation_baseline import worker_io as worker_io


def run_cast(
    tmp_path, monkeypatch, *, collision=False, missing=False, visibility=None, order=(1, 2)
):
    # Install the same offline model/I/O doubles as the existing preparation regressions.
    run_mask(tmp_path / "bootstrap", monkeypatch, predicted_masks())

    def predictions(predictor, shot, subject, span, width, height):
        selected = np.zeros((height, width), bool)
        if subject["id"] == 1:
            selected[20:40, 10:25] = True
        else:
            selected[20:40, 22 if collision else 25 : 40] = True
        from test_preparation_baseline import Tensor

        for index in range(span["end"] - span["start"]):
            current = (
                np.zeros_like(selected)
                if missing and subject["id"] == 2 and span["start"] + index == 50
                else selected
            )
            yield index, [subject["id"]], [[Tensor(np.where(current, 1.0, -1.0))]]

    monkeypatch.setattr(worker, "sam2_track_interval", predictions)
    subjects = [
        {
            "id": id,
            "name": f"Cast {id}",
            "intervals": [{"start": 0, "end": COUNT}],
            "annotations": [
                {"frame": 25, "points": [{"x": 0.5, "y": 0.5, "include": True}], "box": None}
            ],
            "visibility": visibility if id == 1 and visibility else [],
        }
        for id in order
    ]
    return worker.stage(
        {
            "stage": "mask",
            "source": str(tmp_path / "source.mp4"),
            "output": str(tmp_path / "cast"),
            "models": str(tmp_path / "models"),
            "recipe": {
                "segmentation": "sam2-large",
                "allow_empty_frames": True,
                "subjects": subjects,
            },
        }
    )


def test_another_subject_mask_cannot_hide_a_tracking_gap(tmp_path, monkeypatch, worker_io):
    with pytest.raises(ValueError, match="No subject mask.*subject 2"):
        run_cast(tmp_path, monkeypatch, missing=True)


def test_colliding_subject_predictions_are_not_last_writer_wins(tmp_path, monkeypatch, worker_io):
    with pytest.raises(ValueError, match="overlap|collision"):
        run_cast(tmp_path, monkeypatch, collision=True)


def test_fully_occluded_subject_is_not_painted_from_prediction(tmp_path, monkeypatch, worker_io):
    note = [
        {
            "start": 0,
            "end": 20,
            "state": "fully_occluded",
            "reason": "Hidden behind the synthetic car",
        }
    ]
    result = run_cast(tmp_path, monkeypatch, visibility=note)
    masks = load_masks(result["mask_data"])
    assert not (masks[:20] == 1).any(), "Ghost subject painted during declared full occlusion"
    assert (masks[:20] == 2).any(), "Other visible subject must remain labelled"


def test_overlapping_intervals_with_disjoint_masks_keep_both_ids(tmp_path, monkeypatch, worker_io):
    result = run_cast(tmp_path, monkeypatch)
    masks = load_masks(result["mask_data"])
    assert (masks[:, 20:40, 10:25] == 1).all()
    assert (masks[:, 20:40, 25:40] == 2).all()


def test_disjoint_overlap_is_independent_of_cast_processing_order(tmp_path, monkeypatch, worker_io):
    first = load_masks(run_cast(tmp_path / "first", monkeypatch)["mask_data"])
    second = load_masks(run_cast(tmp_path / "second", monkeypatch, order=(2, 1))["mask_data"])
    assert np.array_equal(first, second)


def test_collision_does_not_clear_either_subject_before_rejection():
    plane = np.array([[1, 0, 2], [1, 1, 2]], dtype=np.uint8)
    before = plane.copy()
    with pytest.raises(ValueError, match="collision"):
        merge_subject_mask(plane, np.ones_like(plane), 1, 7)
    assert np.array_equal(plane, before)
    merge_subject_mask(plane, np.array([[False, True, False], [True, False, False]]), 1, 7)
    assert np.array_equal(plane, [[0, 1, 2], [1, 0, 2]])


def cast_with_visibility(state="fully_occluded"):
    return {
        "id": 1,
        "name": "Synthetic cast",
        "intervals": [{"start": 0, "end": 20}],
        "visibility": [{"start": 7, "end": 12, "state": state, "reason": "Synthetic occluder"}],
        "annotations": [
            {"frame": f, "points": [{"x": 0.5, "y": 0.5, "include": True}]} for f in (3, 15)
        ],
    }


@pytest.mark.parametrize("state", ["absent", "fully_occluded"])
def test_reappearance_keeps_identity_but_requires_a_new_visible_anchor(state):
    cast = cast_with_visibility(state)
    recipe = Recipe(end=4, subjects=[cast]).model_dump()
    validate_bindings(recipe)
    assert visible_spans(cast, 96) == [{"start": 0, "end": 7}, {"start": 12, "end": 20}]
    masks = np.zeros((96, 4, 4), np.uint8)
    masks[:7, 1:3, 1:3] = masks[12:20, 1:3, 1:3] = 1
    report = tracking_report(masks, [cast])
    assert report["subjects"]["1"]["missing_frames"] == []
    assert report["unassigned_frames"] == list(range(20, 96))
    cast["annotations"].pop()
    with pytest.raises(ValueError, match="visible span"):
        validate_bindings({"start": 0, "end": 4, "subjects": [cast]})


def test_partial_occlusion_still_requires_visible_parts():
    cast = cast_with_visibility("partially_occluded")
    assert visible_spans(cast, 96) == [{"start": 0, "end": 20}]
    masks = np.ones((20, 4, 4), np.uint8)
    masks[9] = 0
    with pytest.raises(ValueError, match="frames \\[9\\].*subject 1"):
        tracking_report(masks, [cast])


@pytest.mark.parametrize(
    "note",
    [
        {"start": 6, "end": 21, "state": "absent", "reason": "outside binding"},
        {"start": 6, "end": 10, "state": "absent", "reason": " "},
    ],
)
def test_visibility_cannot_exempt_unbound_frames_or_have_no_evidence(note):
    cast = cast_with_visibility()
    cast["visibility"] = [note]
    with pytest.raises(ValueError):
        Recipe(end=4, subjects=[cast])


def test_an_anchor_in_full_occlusion_is_rejected():
    cast = cast_with_visibility()
    cast["annotations"].append({"frame": 9, "points": [{"x": 0.5, "y": 0.5}]})
    with pytest.raises(ValueError, match="outside"):
        validate_bindings(Recipe(end=4, subjects=[cast]).model_dump())


@pytest.mark.parametrize("bad", ["count", "frame", "identity"])
def test_sam_cannot_escape_its_shot_frame_indices_or_cast_identity(bad):
    class Predictor:
        def init_state(self, path, **kwargs):
            return {"num_frames": 8 if bad == "count" else 7}

        def add_new_points_or_box(self, *args, **kwargs):
            pass

        def propagate_in_video(self, *args, **kwargs):
            yield 7 if bad == "frame" else 3, [2 if bad == "identity" else 1], [None]

    with pytest.raises(ValueError, match="frame|identity"):
        list(
            sam2_track_interval(
                Predictor(), "synthetic", cast_with_visibility(), {"start": 0, "end": 7}, 4, 4
            )
        )


def test_later_seed_tracks_backwards_before_earlier_contextual_correction():
    events = []

    class Predictor:
        def init_state(self, path, **kwargs):
            return {"num_frames": 20, "tracked": set()}

        def add_new_points_or_box(self, state, index, id, **kwargs):
            events.append((index, index in state["tracked"]))

        def propagate_in_video(self, state, start_frame_idx, reverse):
            indices = range(start_frame_idx, -1, -1) if reverse else range(start_frame_idx, 20)
            for index in indices:
                state["tracked"].add(index)
                yield index, [1], [None]

    cast = {**cast_with_visibility(), "seed_frame": 15}
    outputs = list(
        sam2_track_interval(Predictor(), "synthetic", cast, {"start": 0, "end": 20}, 4, 4)
    )
    assert events == [(15, False), (3, True)]
    assert {index for index, _, _ in outputs} == set(range(20))
