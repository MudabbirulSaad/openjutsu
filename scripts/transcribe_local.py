"""Transcribe local media on CUDA and create the ignored, editable transcript package."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--model", choices=["large-v3-turbo", "large-v3"], default="large-v3-turbo")
    parser.add_argument(
        "--model-directory",
        type=Path,
        default=Path.home() / ".local/share/openjutsu/models/whisper",
    )
    parser.add_argument("--output", type=Path, default=Path("docs/transcripts"))
    args = parser.parse_args()
    import torch
    import whisper

    if not torch.cuda.is_available():
        raise SystemExit("CUDA is unavailable in this Python environment")
    model = whisper.load_model(args.model, download_root=str(args.model_directory), device="cuda")
    result = model.transcribe(
        str(args.video), word_timestamps=True, condition_on_previous_text=False
    )
    args.output.mkdir(parents=True, exist_ok=True)
    raw = args.output / "machine-transcript.json"
    raw.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("transcript_package.py")),
            str(raw),
            "--output",
            str(args.output),
        ],
        check=True,
    )
