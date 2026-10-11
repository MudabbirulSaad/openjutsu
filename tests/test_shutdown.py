import os
import socket
import subprocess
import sys
import time

import httpx
import pytest


@pytest.mark.skipif(os.name == "nt", reason="Exercises Linux SIGTERM and WSL server lifecycle")
def test_cli_releases_port_with_open_event_stream(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    env = {
        **os.environ,
        "OPENJUTSU_DATA_DIR": str(tmp_path),
        "OPENJUTSU_MODEL_DIR": str(tmp_path / "models"),
        "OPENJUTSU_ML_PYTHON": sys.executable,
    }
    url = f"http://127.0.0.1:{port}"

    def start():
        process = subprocess.Popen(
            [sys.executable, "-c", f"from openjutsu.cli import serve; serve(port={port})"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                pytest.fail("CLI stopped before startup")
            try:
                if httpx.get(url + "/api/system", timeout=0.5).status_code == 200:
                    return process
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        process.kill()
        process.wait()
        pytest.fail("CLI did not start")

    process = start()
    try:
        with httpx.stream("GET", url + "/api/events", timeout=10) as events:
            assert events.status_code == 200
            process.terminate()
            process.wait(timeout=12)
        process = start()
        process.terminate()
        process.wait(timeout=12)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
