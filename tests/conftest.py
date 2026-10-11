import json
from pathlib import Path

import numpy as np
import pytest


def pytest_addoption(parser):
    parser.addoption("--pilot-fixture", help="Private fixture directory from reproduce_pilot.py")
    parser.addoption("--candidate-fixture", help="Private Step 2 candidate fixture directory")


@pytest.fixture(scope="session")
def pilot_fixture(request):
    folder = request.config.getoption("--pilot-fixture")
    if not folder:
        pytest.skip("Private pilot fixture is opt-in; never included in Git/CI")
    return load_private_fixture(folder)


@pytest.fixture(scope="session")
def candidate_fixture(request):
    folder = request.config.getoption("--candidate-fixture")
    if not folder:
        pytest.skip("Private Step 2 candidate is opt-in; never included in Git/CI")
    return load_private_fixture(folder)


def load_private_fixture(folder):
    from hashlib import file_digest

    folder = Path(folder)
    metadata = json.loads((folder / "fixture.json").read_text())
    with (folder / "frames.npz").open("rb") as stream:
        assert file_digest(stream, "sha256").hexdigest() == metadata["fixture_sha256"]
    with np.load(folder / "frames.npz", allow_pickle=False) as archive:
        arrays = {k: archive[k] for k in archive.files}
    return metadata, arrays
