# Local transcript package

Full transcripts are local research artifacts, not public application content.

Run `python scripts/transcript_package.py /path/to/whisper-result.json` to write
timestamped Markdown, text, SRT and word JSON here. The files are ignored by Git.
The generator normalizes established technical names, preserves raw ASR words,
and marks the pitch-distorted song excerpt as uncertain. Review against the
recording before treating the text as an edited quotation.
