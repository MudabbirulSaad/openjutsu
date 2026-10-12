"""Actual Engine persistence/cache seam with synthetic worker outputs, never model/media uploads."""

import io
import json
import shutil
from pathlib import Path
from subprocess import PIPE
from types import SimpleNamespace
from zipfile import BadZipFile, ZipFile

import numpy as np
import pytest
from openjutsu.config import Config
from openjutsu.engine import Engine
from openjutsu.media import Media, digest, probe, run
from openjutsu.store import Store
from openjutsu.types import CreateJob


def corrupt_member(path, member="depths.npy"):
    with ZipFile(path) as archive:
        info = archive.getinfo(member)
    data = bytearray(path.read_bytes())
    name = int.from_bytes(data[info.header_offset + 26 : info.header_offset + 28], "little")
    extra = int.from_bytes(data[info.header_offset + 28 : info.header_offset + 30], "little")
    data[info.header_offset + 30 + name + extra + info.compress_size - 1] ^= 1
    path.write_bytes(data)


@pytest.fixture
def stage_runtime(tmp_path, monkeypatch):
    config = Config(tmp_path, tmp_path / "models")
    config.initialize()
    store = Store(tmp_path)
    source = tmp_path / "synthetic.mp4"
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=32x24:rate=24:duration=4",
            "-c:v",
            "libx264",
            "-y",
            str(source),
        ]
    )
    asset = Media(config, store).import_file(source)
    job = store.create_job(CreateJob(source=asset["id"]))
    engine = Engine(config, store)
    state = {"calls": 0, "corrupt": False, "cancel": False}
    metadata = probe(source)

    class Process:
        returncode = 0

        def __init__(self, command, **kwargs):
            state["calls"] += 1
            task = json.loads(Path(command[-1]).read_text())
            folder = Path(task["output"])
            depth = folder / "depths.npz"
            np.savez(
                depth,
                depths=np.ones(
                    (metadata["frames"], metadata["height"], metadata["width"]), np.float32
                ),
            )
            if state["corrupt"]:
                corrupt_member(depth)
            preview = folder / "depth.mp4"
            shutil.copyfile(source, preview)
            self.stdout = io.StringIO(
                json.dumps(
                    {
                        "result": {"depth_data": str(depth), "depth": str(preview)},
                        "seconds": 1,
                        "peak_mb": 0,
                    }
                )
                + "\n"
            )
            if state["cancel"]:
                store.update("job", job["id"], {"cancel": True})

        def poll(self):
            return 0

    monkeypatch.setattr("openjutsu.engine.subprocess", SimpleNamespace(Popen=Process, PIPE=PIPE))
    return engine, config, store, job, source, state


def execute(runtime, engine=None):
    original, _, _, job, source, _ = runtime
    return (engine or original).run_stage(job, "depth", source, {})


def test_corrupt_worker_output_is_never_published(stage_runtime):
    _, config, _, _, _, state = stage_runtime
    state["corrupt"] = True
    with pytest.raises((BadZipFile, ValueError)):
        execute(stage_runtime)
    assert not list(config.root.glob("cache/*/manifest.json"))
    assert list(config.root.rglob("depths.npz")), "Retain failed output as diagnostic evidence"


def test_crc_bad_cache_with_matching_hash_is_recomputed_after_restart(stage_runtime):
    _, config, _, _, _, state = stage_runtime
    previous = execute(stage_runtime)
    manifest = next(config.root.glob("cache/*/manifest.json"))
    corrupt_member(Path(previous["depth_data"]))
    corrupt_bytes = Path(previous["depth_data"]).read_bytes()
    data = json.loads(manifest.read_text())
    data["hashes"]["depth_data"] = digest(previous["depth_data"])
    manifest.write_text(json.dumps(data))
    restarted = Engine(config, Store(config.root))
    current = execute(stage_runtime, restarted)
    assert state["calls"] == 2, "A matching hash cannot certify an unreadable archive"
    assert current != previous, "Regeneration must not overwrite failing evidence"
    assert Path(previous["depth_data"]).read_bytes() == corrupt_bytes
    with np.load(current["depth_data"], allow_pickle=False) as archive:
        assert np.isfinite(archive["depths"]).all()


def test_truncated_manifest_does_not_prevent_safe_regeneration(stage_runtime):
    _, config, _, _, _, state = stage_runtime
    previous = execute(stage_runtime)
    manifest = next(config.root.glob("cache/*/manifest.json"))
    manifest.write_text('{"paths":')
    current = execute(stage_runtime, Engine(config, Store(config.root)))
    assert state["calls"] == 2 and current != previous
    assert Path(previous["depth_data"]).is_file()


def test_cancelled_output_cannot_publish_manifest(stage_runtime):
    _, config, _, _, _, state = stage_runtime
    state["cancel"] = True
    with pytest.raises(InterruptedError):
        execute(stage_runtime)
    assert not list(config.root.glob("cache/*/manifest.json"))


def test_valid_legacy_cache_remains_readable_and_reusable(stage_runtime):
    _, config, store, job, _, state = stage_runtime
    previous = execute(stage_runtime)
    manifest = next(config.root.glob("cache/*/manifest.json"))
    data = json.loads(manifest.read_text())
    data.pop("integrity_version", None)
    data.pop("verification", None)
    manifest.write_text(json.dumps(data))
    stamp = manifest.stat().st_mtime_ns
    assert execute(stage_runtime, Engine(config, Store(config.root))) == previous
    assert state["calls"] == 1 and manifest.stat().st_mtime_ns == stamp
    assert store.get("job", job["id"])["progress"]["cached"] is True


def test_failed_run_without_manifest_is_not_adopted_after_restart(stage_runtime):
    _, config, _, _, _, state = stage_runtime
    state["corrupt"] = True
    with pytest.raises(BadZipFile):
        execute(stage_runtime)
    failed = next(config.root.rglob("depths.npz"))
    failed_bytes = failed.read_bytes()
    state["corrupt"] = False
    current = execute(stage_runtime, Engine(config, Store(config.root)))
    assert state["calls"] == 2 and current["depth_data"] != str(failed)
    assert failed.read_bytes() == failed_bytes
    assert next(config.root.glob("cache/*/manifest.json")).is_file()
