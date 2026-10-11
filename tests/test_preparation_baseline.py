"""Synthetic replay of bad predictions at the real worker seam; no SAM/GPU/network required.

The SAM double supplies documented failure-shaped masks, not model inference. The private
pilot tests and fresh checkpoint replay establish that SAM actually produced this failure.
Only video I/O and model inference are doubled; worker materialization, storage, validation,
and compositing execute unchanged. --runxfail makes the desired contracts fail visibly.
"""

import sys
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest
from openjutsu import worker
from openjutsu.tracking import load_masks, save_masks

COUNT, HEIGHT, WIDTH = 261, 96, 54
FACE = np.s_[27:43, 21:35]
BODY = np.s_[43:91, 12:43]


def explicit_quality_rejection(error):
    message = str(error).lower()
    if not any(
        term in message
        for term in (
            "coverage",
            "incomplete person",
            "uncovered",
            "no subject mask",
            "source appearance",
            "source rgb",
        )
    ):
        raise error  # Unrelated exceptions must fail, not satisfy a quality contract.


class Tensor:
    def __init__(self, values):
        self.values = values

    def __gt__(self, threshold):
        return Tensor(self.values > threshold)

    def cpu(self):
        return self

    def numpy(self):
        return self.values


def predicted_masks(*, clothing=False, gap=False):
    masks = np.zeros((COUNT, HEIGHT, WIDTH), dtype=np.uint8)
    masks[160:, FACE[0], FACE[1]] = 3
    masks[160:, BODY[0], BODY[1]] = 3
    if clothing:
        for frame in (230, 260):
            masks[frame, FACE[0], FACE[1]] = 0
    if gap:
        masks[160:167] = 0
    return masks


@pytest.fixture
def worker_io(monkeypatch):
    encoded = {}
    metadata = {"frames": COUNT, "width": WIDTH, "height": HEIGHT, "fps": 24}
    monkeypatch.setattr(worker, "probe", lambda path: metadata)
    monkeypatch.setattr(worker, "emit", lambda **event: None)

    def encode(frames, path, width, height):
        encoded[str(path)] = np.stack(list(frames))

    monkeypatch.setattr(worker, "encode_frames", encode)

    def imwrite(path, frame):
        Path(path).write_bytes(b"synthetic-jpeg-placeholder")
        return True

    def resize(frame, size):
        assert frame.shape[:2] == (size[1], size[0])
        return frame

    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(imwrite=imwrite, resize=resize))
    return encoded


def run_mask(tmp_path, monkeypatch, masks, allow_empty=True, context_aware=False, event_log=None):
    spans = [{"start": 160, "end": 192}, {"start": 192, "end": COUNT}]

    class Predictor:
        def __init__(self):
            self.spans = iter(spans)

        def init_state(self, path, **kwargs):
            return {**next(self.spans), "tracked": set(), "anchors": {}}

        def add_new_points_or_box(self, state, index, id, **kwargs):
            assert id == 3 and 0 <= index < state["end"] - state["start"]
            if event_log is not None:
                event_log.append((state["start"] + index, index in state["tracked"], kwargs))
            if context_aware:
                state["anchors"][index] = (
                    predicted_masks()[state["start"] + index]
                    if index in state["tracked"]
                    else masks[state["start"] + index]
                )

        def propagate_in_video(self, state, start_frame_idx, reverse):
            begin, end = state["start"], state["end"]
            indices = (
                range(start_frame_idx, -1, -1) if reverse else range(start_frame_idx, end - begin)
            )
            for index in indices:
                state["tracked"].add(index)
                selected = state["anchors"].get(index, masks[begin + index])
                logits = np.where(selected == 3, 1.0, -1.0)
                yield index, [3], [[Tensor(logits)]]

    torch = ModuleType("torch")
    torch.inference_mode = nullcontext
    torch.autocast = lambda *args, **kwargs: nullcontext()
    torch.bfloat16 = "test-dtype"
    torch.cuda = SimpleNamespace(empty_cache=lambda: None)
    sam = ModuleType("sam2.build_sam")
    sam.build_sam2_video_predictor = lambda *args, **kwargs: Predictor()
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "sam2", ModuleType("sam2"))
    monkeypatch.setitem(sys.modules, "sam2.build_sam", sam)
    monkeypatch.setattr(worker, "video_frames", lambda path: iter(np.zeros_like(masks)))
    anchors = [(186, 0.53, 0.67), (200, 0.52, 0.76), (230, 0.48, 0.80), (260, 0.53, 0.82)]
    return worker.stage(
        {
            "stage": "mask",
            "source": str(tmp_path / "source.mp4"),
            "output": str(tmp_path),
            "models": str(tmp_path / "models"),
            "recipe": {
                "segmentation": "sam2-large",
                "allow_empty_frames": allow_empty,
                "subjects": [
                    {
                        "id": 3,
                        "intervals": spans,
                        "annotations": [
                            {"frame": f, "points": [{"x": x, "y": y, "include": True}], "box": None}
                            for f, x, y in anchors
                        ],
                    }
                ],
            },
        }
    )


def run_composite(tmp_path, monkeypatch, masks):
    source = np.full((COUNT, HEIGHT, WIDTH, 3), [17, 83, 151], dtype=np.uint8)
    source[:, FACE[0], FACE[1]] = [211, 127, 61]
    depth = np.full_like(source, [5, 233, 47])
    monkeypatch.setattr(
        worker, "video_frames", lambda path: iter(depth if path == "depth" else source)
    )
    result = worker.stage(
        {
            "stage": "composite",
            "source": "source",
            "depth": "depth",
            "output": str(tmp_path),
            "models": str(tmp_path / "models"),
            "recipe": {},
            "mask_data": str(save_masks(tmp_path, masks)),
        }
    )
    return result, source, depth


def test_worker_preserves_complete_subject_predictions(tmp_path, monkeypatch, worker_io):
    masks = predicted_masks()
    result = run_mask(tmp_path, monkeypatch, masks)
    assert np.array_equal(load_masks(result["mask_data"]), masks)
    assert not load_masks(result["mask_data"])[:160].any()


def test_worker_rejects_tracking_gap_without_global_allowance(tmp_path, monkeypatch, worker_io):
    with pytest.raises(ValueError, match="No subject mask on frames"):
        run_mask(tmp_path, monkeypatch, predicted_masks(gap=True), allow_empty=False)


@pytest.mark.parametrize("frame", [230, 260])
def test_correction_uses_tracked_person_context(tmp_path, monkeypatch, worker_io, frame):
    events = []
    result = run_mask(
        tmp_path, monkeypatch, predicted_masks(clothing=True), context_aware=True, event_log=events
    )
    assert next(tracked for f, tracked, _ in events if f == frame), (
        "Correction added before tracking"
    )
    assert (load_masks(result["mask_data"])[frame][FACE] == 3).all()


def test_correction_replaces_stale_background_pixels(tmp_path, monkeypatch, worker_io):
    masks = predicted_masks(clothing=True)
    masks[230, :8, :8] = 3
    result = run_mask(tmp_path, monkeypatch, masks, context_aware=True)
    assert not load_masks(result["mask_data"])[230, :8, :8].any(), (
        "Old positive pixels survived correction"
    )


def test_complete_mask_removes_source_face_and_preserves_background(
    tmp_path, monkeypatch, worker_io
):
    masks = predicted_masks()
    result, source, depth = run_composite(tmp_path, monkeypatch, masks)
    actual = worker_io[result["composite"]]
    selected = masks > 0
    assert np.array_equal(actual[selected], depth[selected])
    assert np.array_equal(actual[~selected], source[~selected])
    assert not np.array_equal(actual[230][FACE], source[230][FACE])


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="Worker accepts clothing-only masks")
@pytest.mark.parametrize("frame", [230, 260])
def test_quality_worker_refuses_or_completes_clothing_mask(tmp_path, monkeypatch, worker_io, frame):
    try:
        result = run_mask(tmp_path, monkeypatch, predicted_masks(clothing=True))
    except ValueError as error:
        return explicit_quality_rejection(error)
    actual = load_masks(result["mask_data"])
    assert (actual[frame][FACE] == 3).mean() >= 0.95, (
        f"frame {frame}: clothing accepted without head"
    )


def test_quality_worker_refuses_visible_subject_gap(tmp_path, monkeypatch, worker_io):
    try:
        result = run_mask(tmp_path, monkeypatch, predicted_masks(gap=True))
    except ValueError as error:
        return explicit_quality_rejection(error)
    actual = load_masks(result["mask_data"])
    missing = [f for f in range(160, 167) if not actual[f].any()]
    assert not missing, f"Visible subject missing on frames {missing}"


@pytest.mark.xfail(
    strict=True, raises=AssertionError, reason="Compositor copies uncovered face RGB"
)
@pytest.mark.parametrize("frame", [160, 230, 260])
def test_quality_composite_refuses_or_removes_source_face(tmp_path, monkeypatch, worker_io, frame):
    try:
        result, source, depth = run_composite(
            tmp_path, monkeypatch, predicted_masks(clothing=True, gap=True)
        )
    except ValueError as error:
        return explicit_quality_rejection(error)
    actual = worker_io[result["composite"]]
    assert not np.array_equal(actual[frame][FACE], source[frame][FACE]), (
        f"frame {frame}: original RGB leaked"
    )
    assert np.array_equal(actual[frame][FACE], depth[frame][FACE])
