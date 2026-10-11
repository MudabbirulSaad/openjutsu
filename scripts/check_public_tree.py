"""Check staged or tracked paths before publishing; never print secret values."""

import argparse
import re
import subprocess
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument("--staged", action="store_true")
args = p.parse_args()
command = (
    ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"]
    if args.staged
    else ["git", "ls-files"]
)
paths = subprocess.check_output(command, text=True).splitlines()
bad = []
for name in paths:
    path = Path(name)
    if name.startswith(("source/", "models/", "data/", "outputs/")) or path.suffix in {
        ".mkv",
        ".mp4",
        ".mov",
        ".webm",
        ".avi",
        ".wav",
        ".mp3",
        ".flac",
        ".m4a",
        ".ogg",
        ".sqlite",
        ".db",
        ".sqlite-wal",
        ".sqlite-shm",
        ".pt",
        ".pth",
        ".th",
        ".safetensors",
    }:
        bad.append((name, "private/generated media or runtime file"))
    if name.startswith("docs/transcripts/") and path.name != "README.md":
        bad.append((name, "full source transcript"))
    if path.name.startswith(".env") and path.name != ".env.example":
        bad.append((name, "environment secrets"))
    if path.name == "secrets.json":
        bad.append((name, "runtime credentials"))
    content_bytes = (
        subprocess.check_output(["git", "show", f":{name}"])
        if args.staged
        else (path.read_bytes() if path.exists() else b"")
    )
    if len(content_bytes) > 5_000_000:
        bad.append((name, "large file"))
    if path.suffix in {
        ".py",
        ".ts",
        ".tsx",
        ".json",
        ".md",
        ".yml",
        ".yaml",
        ".sh",
        ".toml",
        ".lock",
    }:
        content = content_bytes.decode("utf-8-sig")
        if re.search(
            r"(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            content,
        ):
            bad.append((name, "possible credential"))
for name, reason in bad:
    print(f"BLOCKED: {name}: {reason}")
raise SystemExit(bool(bad))
