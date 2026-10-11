# Local transcript package

Full transcripts are local research artifacts, not public application content.

For a new CUDA pass, use the model environment:

```bash
"$HOME/.local/share/openjutsu/venv/bin/python" scripts/transcribe_local.py /path/to/video.mkv
# Optional slower independent pass:
"$HOME/.local/share/openjutsu/venv/bin/python" scripts/transcribe_local.py /path/to/video.mkv --model large-v3 --output docs/transcripts/verification
```

The supplied recording was transcribed with large-v3-turbo and compared against a large-v3 pass. The local package preserves original words/timing and marks uncertain audio. It is an edited machine transcript, not a certified quotation or a caption extraction. Do not commit it when publishing the project.

Run `python scripts/transcript_package.py /path/to/whisper-result.json` to write
timestamped Markdown, text, SRT and word JSON here. The files are ignored by Git.
The generator normalizes established technical names, preserves raw ASR words,
and marks the pitch-distorted song excerpt as uncertain. Review against the
recording before treating the text as an edited quotation.
