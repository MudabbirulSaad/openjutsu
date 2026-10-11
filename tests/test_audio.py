import subprocess

import numpy as np
from openjutsu.media import mux, probe, run
from openjutsu.worker import stage


def test_custom_speech_and_export_share_unpitched_timing(tmp_path):
    speech = tmp_path / "speech.wav"
    source = tmp_path / "source.mp4"
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4",
            "-y",
            str(speech),
        ]
    )
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=size=160x96:rate=24:duration=4",
            "-c:v",
            "libx264",
            "-y",
            str(source),
        ]
    )
    prepared = stage(
        {
            "stage": "custom",
            "source": str(speech),
            "output": str(tmp_path / "custom"),
            "models": str(tmp_path),
            "recipe": {"custom_mix_background": False},
            "duration": 4,
        }
    )
    assert prepared["custom_voice"] == prepared["final_audio"]
    delivery = tmp_path / "delivery.mp4"
    mux(source, prepared["final_audio"], delivery, browser=True)
    assert abs(probe(delivery)["duration"] - 4) < 1 / 24
    samples = np.frombuffer(
        subprocess.check_output(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(delivery),
                "-vn",
                "-ar",
                "8000",
                "-ac",
                "1",
                "-f",
                "f32le",
                "-",
            ]
        ),
        dtype=np.float32,
    )
    peak = np.fft.rfftfreq(len(samples), 1 / 8000)[np.argmax(np.abs(np.fft.rfft(samples)))]
    assert abs(peak - 440) < 2  # Final audio is not the +3-semitone conditioning voice.


def test_streaming_webm_recording_has_recoverable_duration(tmp_path):
    recorded = tmp_path / "recorded.webm"
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=4",
            "-c:a",
            "libopus",
            "-live",
            "1",
            "-y",
            str(recorded),
        ]
    )
    assert abs(probe(recorded)["duration"] - 4) < 1 / 24
    result = stage(
        {
            "stage": "custom",
            "source": str(recorded),
            "output": str(tmp_path / "custom"),
            "models": str(tmp_path),
            "recipe": {"custom_mix_background": False},
            "duration": 4,
        }
    )
    assert abs(probe(result["final_audio"])["duration"] - 4) < 1 / 24
