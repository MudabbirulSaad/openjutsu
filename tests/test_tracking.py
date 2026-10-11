import pytest
from openjutsu.tracking import MASK_COLORS, intervals, validate_bindings
from openjutsu.types import Recipe


def subject(id, spans, anchors):
    return {
        "id": id,
        "name": f"Cast {id}",
        "intervals": spans,
        "annotations": [
            {"frame": f, "points": [{"x": 0.5, "y": 0.5}], "box": None} for f in anchors
        ],
    }


def test_three_cast_members_reappear_and_overlap_at_transitions():
    cast = [
        subject(1, [{"start": 0, "end": 110}], [0]),
        subject(2, [{"start": 100, "end": 160}, {"start": 374, "end": 432}], [110, 383]),
        subject(3, [{"start": 160, "end": 374}], [186, 300]),
    ]
    recipe = Recipe(end=18, subjects=cast, allow_empty_frames=True).model_dump()
    validate_bindings(recipe)
    assert len(recipe["subjects"]) == 3
    assert len(MASK_COLORS) == 4
    assert intervals({"id": 1}, 432) == [{"start": 0, "end": 432}]


def test_exclusive_boundaries_and_anchor_required_in_each_interval():
    recipe = {"start": 0, "end": 18, "subjects": [subject(1, [{"start": 0, "end": 100}], [100])]}
    with pytest.raises(ValueError, match="every tracking interval"):
        validate_bindings(recipe)
    recipe["subjects"][0] = subject(1, [{"start": 0, "end": 100}], [20, 110])
    with pytest.raises(ValueError, match="outside"):
        validate_bindings(recipe)
    for spans in [
        [{"start": 5, "end": 5}],
        [{"start": 0, "end": 500}],
        [{"start": 10, "end": 40}, {"start": 30, "end": 50}],
    ]:
        with pytest.raises(ValueError):
            Recipe(end=18, subjects=[subject(1, spans, [20])])


def test_mesh_does_not_claim_three_person_support():
    with pytest.raises(ValueError, match="one subject"):
        Recipe(mode="fast", subjects=[{"id": 1}, {"id": 2}])


def test_long_mask_storage_survives_exact_roundtrip(tmp_path):
    import numpy as np
    from openjutsu.tracking import load_masks, save_masks

    for count in (1, 8, 32, 64, 128, 432):
        masks = np.zeros((count, 960, 540), dtype=np.uint8)
        masks[:, 200:800, 100:400] = 1
        path = save_masks(tmp_path, masks)
        assert np.array_equal(load_masks(path), masks)


def test_sam_prompts_merge_same_frame_points_and_box_with_correct_scale():
    import numpy as np
    from openjutsu.tracking import sam2_track_interval

    events = []

    class Predictor:
        def init_state(self, path, **kwargs):
            return {"tracked": set()}

        def add_new_points_or_box(self, state, index, id, **kwargs):
            events.append((index, id, index in state["tracked"], kwargs))

        def propagate_in_video(self, state, start_frame_idx, reverse):
            order = range(start_frame_idx, -1, -1) if reverse else range(start_frame_idx, 10)
            for index in order:
                state["tracked"].add(index)
                yield index, [2], None

    cast = {
        "id": 2,
        "annotations": [
            {
                "frame": 16,
                "points": [{"x": 0.9, "y": 0.1, "include": False}],
                "box": [0.1, 0.2, 0.8, 0.9],
            },
            {"frame": 12, "points": [{"x": 0.25, "y": 0.5, "include": True}], "box": None},
            {"frame": 16, "points": [{"x": 0.5, "y": 0.4, "include": True}], "box": None},
            {"frame": 20, "points": [{"x": 0.5, "y": 0.4, "include": True}], "box": None},
        ],
    }
    outputs = list(
        sam2_track_interval(Predictor(), "synthetic", cast, {"start": 10, "end": 20}, 200, 80)
    )
    assert [(index, id, tracked) for index, id, tracked, _ in events] == [
        (2, 2, False),
        (6, 2, True),
    ]
    assert np.array_equal(events[0][3]["points"], [[50, 40]])
    assert np.allclose(events[1][3]["points"], [[180, 8], [100, 32]])
    assert np.array_equal(events[1][3]["labels"], [0, 1])
    assert np.allclose(events[1][3]["box"], [20, 16, 160, 72])
    assert {index for index, ids, _ in outputs} == set(range(10))
    assert all(ids == [2] for _, ids, _ in outputs)


def test_conflicting_same_frame_boxes_are_explicit_error():
    from openjutsu.tracking import sam2_track_interval

    cast = {
        "id": 1,
        "annotations": [
            {"frame": 0, "points": [], "box": [0, 0, 0.5, 0.5]},
            {"frame": 0, "points": [], "box": [0.1, 0.1, 0.8, 0.8]},
        ],
    }
    with pytest.raises(ValueError, match="Conflicting boxes"):
        list(sam2_track_interval(None, "synthetic", cast, {"start": 0, "end": 4}, 20, 10))
