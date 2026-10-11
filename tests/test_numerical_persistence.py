"""Corruption, interruption and complete readback with nonidentifiable numerical data."""

import io
import json
import os
import subprocess
import sys
from zipfile import BadZipFile, ZipFile

import numpy as np
import pytest
from openjutsu import artifacts
from test_artifact_integrity import corrupt_member


@pytest.mark.parametrize("compressed", [False, True])
def test_every_member_is_read_back_repeatedly(tmp_path, compressed):
    arrays = {
        "depths": np.arange(120, dtype=np.float32).reshape(4, 5, 6),
        "previous_conditioning": np.ones((4, 5, 6, 3), np.uint8),
    }
    path = artifacts.write_npz(tmp_path / "data.npz", arrays, compressed=compressed)
    for _ in range(10):
        checked = artifacts.verify_npz(path, arrays)
        assert checked["depths"]["shape"] == [4, 5, 6]
    assert not list(tmp_path.glob("*.pending-*"))


def test_unused_member_crc_failure_is_rejected(tmp_path):
    arrays = {
        "depths": np.ones((4, 5, 6), np.float32),
        "previous_conditioning": np.ones((4, 5, 6, 3), np.uint8),
    }
    path = artifacts.write_npz(tmp_path / "data.npz", arrays, compressed=False)
    corrupt_member(path, "previous_conditioning.npy")
    with pytest.raises(BadZipFile, match="previous_conditioning"):
        artifacts.verify_depth(path, 4)


def test_incomplete_compressed_archive_is_rejected(tmp_path):
    path = artifacts.write_npz(tmp_path / "data.npz", {"depths": np.ones((4, 5, 6), np.float32)})
    path.write_bytes(path.read_bytes()[: path.stat().st_size // 2])
    with pytest.raises(BadZipFile):
        artifacts.verify_npz(path)


def test_wrong_shape_and_dtype_are_not_valid_depth(tmp_path):
    path = artifacts.write_npz(tmp_path / "data.npz", {"depths": np.ones((4, 5, 6), np.float32)})
    with pytest.raises(ValueError, match="frame count"):
        artifacts.verify_depth(path, 5)
    with pytest.raises(ValueError, match="dimensions"):
        artifacts.verify_depth(path, 4, (4, 6, 5))
    artifacts.write_npz(path, {"depths": np.ones((4, 5, 6), np.uint8)})
    with pytest.raises(ValueError, match="floating"):
        artifacts.verify_depth(path)


def test_duplicate_archive_names_are_rejected(tmp_path):
    buffer = io.BytesIO()
    np.save(buffer, np.ones((4, 5, 6), np.float32), allow_pickle=False)
    path = tmp_path / "duplicate.npz"
    with ZipFile(path, "w") as archive:
        archive.writestr("depths.npy", buffer.getvalue())
        with pytest.warns(UserWarning, match="Duplicate"):
            archive.writestr("depths.npy", buffer.getvalue())
    with pytest.raises(ValueError, match="duplicate"):
        artifacts.verify_npz(path)


def test_nonfinite_write_retains_failed_evidence_without_replacing_valid_array(tmp_path):
    path = artifacts.write_npz(tmp_path / "data.npz", {"depths": np.ones((4, 5, 6), np.float32)})
    previous = path.read_bytes()
    with pytest.raises(ValueError, match="non-finite"):
        artifacts.write_npz(path, {"depths": np.full((4, 5, 6), np.nan, np.float32)})
    assert path.read_bytes() == previous
    assert list(tmp_path.glob(".data.npz.pending-*"))


def test_readback_detects_changed_values_before_publication(tmp_path, monkeypatch):
    original = np.savez_compressed

    def wrong(stream, **arrays):
        original(stream, **{key: value + 1 for key, value in arrays.items()})

    monkeypatch.setattr(np, "savez_compressed", wrong)
    with pytest.raises(ValueError, match="depths differs"):
        artifacts.write_npz(tmp_path / "data.npz", {"depths": np.ones((4, 5, 6), np.float32)})
    assert not (tmp_path / "data.npz").exists()


def test_npy_complete_readback_rejects_truncation_and_trailing_data(tmp_path):
    values = np.ones((4, 5, 6), np.uint8)
    path = artifacts.write_npy(tmp_path / "masks.npy", values)
    assert artifacts.verify_npy(path, values)["dtype"] == "uint8"
    previous = path.read_bytes()
    path.write_bytes(previous[:-1])
    with pytest.raises(ValueError):
        artifacts.verify_npy(path)
    path.write_bytes(previous + b"unexpected")
    with pytest.raises(ValueError, match="payload length"):
        artifacts.verify_npy(path)


def test_interrupted_process_cannot_replace_previous_artifact(tmp_path):
    path = artifacts.write_npz(tmp_path / "data.npz", {"depths": np.ones((4, 5, 6), np.float32)})
    previous = path.read_bytes()
    code = """
import sys,time
from pathlib import Path
from openjutsu.artifacts import atomic_write
def partial(stream):
    stream.write(b'PK-partial-unverified-archive');stream.flush()
    print('writing',flush=True);time.sleep(300)
atomic_write(Path(sys.argv[1]),partial,lambda path:None)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(path)],
        stdout=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONPATH": "backend"},
    )
    try:
        assert process.stdout.readline().strip() == "writing"
    finally:
        process.kill()
        process.wait(timeout=10)
    assert path.read_bytes() == previous
    assert list(tmp_path.glob(".data.npz.pending-*"))
    artifacts.verify_depth(path, 4)
    artifacts.write_npz(path, {"depths": np.zeros((4, 5, 6), np.float32)})
    artifacts.verify_depth(path, 4)


def test_failed_manifest_replace_keeps_previous_complete_receipt(tmp_path, monkeypatch):
    path = artifacts.write_json(tmp_path / "manifest.json", {"paths": {"depths": "valid"}})
    previous = path.read_bytes()

    def interrupted(*args):
        raise OSError("Synthetic interruption before replace")

    monkeypatch.setattr(artifacts.os, "replace", interrupted)
    with pytest.raises(OSError, match="interruption"):
        artifacts.write_json(path, {"paths": {"depths": "new"}})
    assert path.read_bytes() == previous
    assert json.loads(previous)["paths"]["depths"] == "valid"


def test_json_preserves_the_serialized_form_of_tuple_model_stamps(tmp_path):
    path = artifacts.write_json(
        tmp_path / "manifest.json", {"model_stamp": (123, 456), "box": (0.1, 0.2, 0.3, 0.4)}
    )
    assert artifacts.read_json(path) == {"model_stamp": [123, 456], "box": [0.1, 0.2, 0.3, 0.4]}


def test_numpy_palette_path_in_fresh_processes():
    # Exercises the observed native fault operation; does not claim its cause is isolated.
    code = """
import numpy as np
from openjutsu.tracking import MASK_COLORS
colors=np.array(MASK_COLORS,dtype=np.uint8)
labels=np.random.default_rng(5).integers(0,4,size=(261,96,54),dtype=np.uint8)
for i in range(100):
    result=np.stack([colors[plane] for plane in labels])
    assert result.shape == (261,96,54,3)
    assert np.array_equal(result[labels==3],np.broadcast_to(colors[3],result[labels==3].shape))
print('100 exact palette passes')
"""
    for _ in range(3):
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "PYTHONPATH": "backend"},
        )
        assert result.returncode == 0, result.stderr
        assert "100 exact palette passes" in result.stdout
