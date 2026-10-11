"""The local evidence tool must detect bad fixture materialization before claiming success."""

import importlib.util
import zipfile
from pathlib import Path

import numpy as np
import pytest


def test_candidate_readback_checks_every_member_including_previous_conditioning(
    tmp_path, monkeypatch
):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "segment_candidate", scripts / "segment_pilot_candidate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    arrays = {
        "masks": np.zeros((2, 4, 3), np.uint8),
        "previous_conditioning": np.full((2, 4, 3, 3), 19, np.uint8),
    }
    path = tmp_path / "frames.npz"
    np.savez_compressed(path, **arrays)
    module.verify_fixture_readback(path, arrays)
    changed = {**arrays, "previous_conditioning": arrays["previous_conditioning"] + 1}
    np.savez_compressed(path, **changed)
    with pytest.raises(ValueError, match="previous_conditioning differs"):
        module.verify_fixture_readback(path, arrays)
    np.savez_compressed(path, masks=arrays["masks"])
    with pytest.raises(ValueError, match="members differ"):
        module.verify_fixture_readback(path, arrays)
    np.savez(path, **arrays)
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("previous_conditioning.npy")
    data = bytearray(path.read_bytes())
    name_length = int.from_bytes(data[info.header_offset + 26 : info.header_offset + 28], "little")
    extra_length = int.from_bytes(data[info.header_offset + 28 : info.header_offset + 30], "little")
    last_payload_byte = (
        info.header_offset + 30 + name_length + extra_length + info.compress_size - 1
    )
    data[last_payload_byte] ^= 1
    path.write_bytes(data)
    with pytest.raises(zipfile.BadZipFile, match="CRC.*previous_conditioning"):
        module.verify_fixture_readback(path, arrays)
