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
