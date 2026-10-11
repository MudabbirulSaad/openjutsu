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
