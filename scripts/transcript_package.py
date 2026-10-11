"""Publish an ASR analysis into ignored local research files."""

import argparse
import json
import re
from pathlib import Path

TERMS = {
    r"\b(?:c[- ]?dens?e?|cdance|c-dens|see dance|seedance)\s*2\.5\b": "Seedance 2.5",
    r"\b(?:hicksfield|higgs field)(?:'s)?\b": "Higgsfield",
    r"\b(?:ganjutsu|scan jutsu|genjutsu|again,?\s*jitsu)\b": "Genjutsu",
    r"\b(?:enhancer|enhancor)\b": "Enhancor",
    r"\b(?:demacus|demicus|demucs)\b": "Demucs",
    r"\b(?:face mash|face match)\b": "face mesh",
    r"\b(?:syrio|suryo|sirio)\b": "Sirio",
    r"\bteen\b": "TEIN",
    r"\bfoul\b": "fal",
}


def clean(text):
    for pattern, term in TERMS.items():
        text = re.sub(pattern, term, text, flags=re.I)
    return text.strip()


def stamp(seconds, srt=False):
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02}{',' if srt else '.'}{ms:03}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", type=Path)
    p.add_argument("--output", type=Path, default=Path("docs/transcripts"))
    args = p.parse_args()
    result = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    lines, subtitles = [], []
    for i, segment in enumerate(result["segments"], 1):
        segment["raw_text"] = segment["text"]
        segment["text"] = clean(segment["text"])
        segment["uncertain"] = (
            (segment["start"] < 390 and segment["end"] > 382)
            or segment.get("avg_logprob", 0) < -0.7
            or segment.get("no_speech_prob", 0) > 0.7
        )
        for word in segment.get("words", []):
            word["raw_word"] = word["word"]
            word["word"] = clean(word["word"])
            word["uncertain"] = segment["uncertain"] or word.get("probability", 1) < 0.5
        annotation = " [uncertain audio; listening review required]" if segment["uncertain"] else ""
        lines.append(f"[{stamp(segment['start'])}] {segment['text']}{annotation}")
        subtitles.append(
            f"{i}\n{stamp(segment['start'], True)} --> {stamp(segment['end'], True)}\n{segment['text']}{annotation}\n"
        )
    text = "\n".join(lines) + "\n"
    result["raw_text"] = result["text"]
    result["text"] = " ".join(s["text"] for s in result["segments"])
    result["caption_source"] = (
        "On-screen text is separate evidence in docs/research/video-findings.md, not inserted as spoken words."
    )
    (args.output / "video-transcript.txt").write_text(text, encoding="utf-8")
    (args.output / "video-transcript.md").write_text(
        "# Video transcript\n\nMachine transcription with terminology normalization. Raw words retained in JSON; uncertain passages require listening review. On-screen captions are documented separately in the research note.\n\n"
        + text,
        encoding="utf-8",
    )
    (args.output / "video-transcript.srt").write_text("\n".join(subtitles), encoding="utf-8")
    (args.output / "video-transcript.words.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
