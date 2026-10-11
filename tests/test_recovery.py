import pytest
from openjutsu.config import Config
from openjutsu.engine import Engine
from openjutsu.media import Media, probe, run
from openjutsu.store import Store
from openjutsu.types import CreateJob


@pytest.fixture
def local(tmp_path):
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
            "testsrc2=size=160x96:rate=24:duration=5",
            "-c:v",
            "libx264",
            "-y",
            str(source),
        ]
    )
    asset = Media(config, store).import_file(source)
    job = store.create_job(CreateJob(source=asset["id"]))
    return config, store, job, source


def test_stage_cache_survives_new_engine_and_changes_invalidate(local):
    config, store, job, source = local
    first = Engine(config, store)
    paths = first.run_stage(job, "normalize", source, {"start": 0, "end": 5})
    manifest = next(config.root.glob("cache/*/manifest.json"))
    stamp = manifest.stat().st_mtime_ns
    second = Engine(config, Store(config.root))
    assert second.run_stage(job, "normalize", source, {"start": 0, "end": 5}) == paths
    assert manifest.stat().st_mtime_ns == stamp
    assert store.get("job", job["id"])["progress"]["cached"] is True
    changed = {**job, "recipe": {**job["recipe"], "end": 4}}
    new = second.run_stage(changed, "normalize", source, {"start": 0, "end": 4})
    assert new != paths
    assert probe(new["normalized"])["frames"] == 96


def test_preparation_includes_visibility_and_seed_in_mask_cache_inputs(local, monkeypatch):
    import copy

    config, store, job, source = local
    engine = Engine(config, store)
    job["recipe"]["subjects"] = [
        {
            "id": 1,
            "annotations": [{"frame": 30, "points": [{"x": 0.5, "y": 0.5}]}],
            "intervals": [{"start": 0, "end": 120}],
            "seed_frame": 30,
            "visibility": [
                {
                    "start": 0,
                    "end": 20,
                    "state": "fully_occluded",
                    "reason": "Synthetic foreground object",
                }
            ],
        }
    ]
    captured = []

    def stage(job, name, source_path, parameters, **kwargs):
        if name == "mask":
            captured.append(copy.deepcopy(parameters))
            return {"mask_data": str(source)}
        return (
            {name if name != "normalize" else "normalized": str(source)} if name != "audio" else {}
        )

    monkeypatch.setattr(engine, "run_stage", stage)
    monkeypatch.setattr(engine.media, "artifact", lambda *args: {"id": "synthetic"})
    engine.preparation(job)
    subject = job["recipe"]["subjects"][0]
    assert captured[0]["subjects"][0]["visibility"] == subject["visibility"]
    assert captured[0]["subjects"][0]["seed_frame"] == 30
    subject["visibility"][0]["end"] = 21
    engine.preparation(job)
    subject["seed_frame"] = 31
    engine.preparation(job)
    assert captured[0] != captured[1] != captured[2]


def test_claimed_task_is_requeued_on_restart(local):
    config, store, job, _ = local
    task = store.enqueue(job["id"], "prepare", {"revision": 1})
    assert store.claim()["id"] == task
    restarted = Store(config.root)
    restarted.recover()
    assert restarted.claim()["id"] == task
    assert restarted.claim() is None
    ids = [e["id"] for e in restarted.events()]
    assert ids == sorted(set(ids))


def test_event_cursors_cannot_be_overwritten_by_record_ids(local):
    _, store, job, _ = local
    store.update("job", job["id"], {"status": "review"})
    rows = store.events()
    assert all(isinstance(e["id"], int) for e in rows)
    assert rows[-1]["record_id"] == job["id"]
    assert store.events(rows[-1]["id"]) == []


def test_cancel_prevents_worker_stage(local):
    config, store, job, source = local
    engine = Engine(config, store)
    store.update("job", job["id"], {"cancel": True})
    with pytest.raises(InterruptedError):
        engine.run_stage(job, "normalize", source, {"start": 0, "end": 5})
    assert engine.process is None


def test_original_export_preserves_unpitched_audio_and_provenance(local):
    config, store, job, source = local
    voice = config.root / "voice.wav"
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=5",
            "-y",
            str(voice),
        ]
    )
    media = Media(config, store)
    art = media.artifact(job, "generation", source, "synthetic test provider")
    sound = media.artifact(job, "final_audio", voice, "original soundtrack")
    store.put("attempt", {"id": "accepted", "artifact": art["id"]})
    job["artifacts"] = {"final_audio": sound["id"]}
    engine = Engine(config, store)
    engine.export(job, {"attempt_id": "accepted", "route": "original"})
    completed = store.get("job", job["id"])
    master = store.get("artifact", completed["artifacts"]["master"])
    assert completed["export_route"] == "original"
    assert master["producer"] == "original generation"
    assert abs(master["metadata"]["duration"] - 5) < 1 / 24
    assert master["metadata"]["has_audio"]
