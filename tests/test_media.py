from openjutsu.config import Config
from openjutsu.media import Media, normalize, probe, run
from openjutsu.store import Store


def test_normalization_and_exact_frames(tmp_path):
    source = tmp_path / "synthetic.mp4"
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100",
            "-t",
            "6",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-y",
            str(source),
        ]
    )
    root = tmp_path / "runtime"
    c = Config(root, root / "models")
    c.initialize()
    m = Media(c, Store(root))
    asset = m.import_file(source)
    output = root / "cache" / "normalized.mp4"
    normalized = normalize(asset["path"], output, 1, 5)
    assert normalized["fps"] == 24
    assert normalized["frames"] == 96
    assert normalized["has_audio"]
    assert probe(source)["fps"] == 30
    item = m.artifact({"id": "job", "revision": 1}, "normalized", output, "ffmpeg")
    assert m.frame(item, 95).is_file()


def test_rotation_and_variable_timestamps_normalize_to_exact_frames(tmp_path):
    source = tmp_path / "vfr.mp4"
    rotated = tmp_path / "rotated.mp4"
    output = tmp_path / "normalized.mp4"
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=30:duration=6",
            "-vf",
            "select='if(lt(t,3),not(mod(n,2)),not(mod(n,3)))'",
            "-fps_mode",
            "vfr",
            "-c:v",
            "libx264",
            "-y",
            str(source),
        ]
    )
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-display_rotation",
            "90",
            "-i",
            str(source),
            "-c",
            "copy",
            "-y",
            str(rotated),
        ]
    )
    normalize(rotated, output, 1, 5)
    metadata = probe(output)
    assert (metadata["width"], metadata["height"]) == (180, 320)
    assert metadata["frames"] == 96
    assert metadata["fps"] == 24
