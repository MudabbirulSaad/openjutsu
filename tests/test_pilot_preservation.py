"""Synthetic negative controls for the private evidence preservation command."""

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "preserve_pilot.py"


@pytest.fixture
def baseline(tmp_path):
    runtime, evidence, exports = [tmp_path / name for name in ("runtime", "evidence", "exports")]
    for folder in (runtime, evidence, exports):
        folder.mkdir()
    source = runtime / "synthetic.bin"
    source.write_bytes(b"nonidentifiable test input")
    (evidence / "report.txt").write_text("synthetic diagnostic")
    (exports / "output.bin").write_bytes(b"synthetic output")
    recipe = {"subjects": []}
    records = [
        (
            "job",
            "job",
            {
                "id": "job",
                "source": "source",
                "revision": 3,
                "recipe": recipe,
                "approval": {"revision": 3, "artifact": "conditioning"},
            },
        ),
        (
            "attempt",
            "attempt",
            {
                "id": "attempt",
                "job": "job",
                "revision": 3,
                "conditioning": "conditioning",
                "recipe_snapshot": recipe,
            },
        ),
        (
            "asset",
            "source",
            {
                "id": "source",
                "path": str(source),
                "hash": hashlib.sha256(source.read_bytes()).hexdigest(),
            },
        ),
    ]
    database = runtime / "jobs.sqlite"
    with sqlite3.connect(database) as db:
        db.executescript(
            "CREATE TABLE records(kind, id, data); CREATE TABLE events(id, job, data); "
            "CREATE TABLE tasks(id, job, kind, data, state);"
        )
        db.executemany(
            "INSERT INTO records VALUES(?,?,?)", [(k, id, json.dumps(d)) for k, id, d in records]
        )
    before = database.read_bytes()
    out = tmp_path / "baseline"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "capture",
            "--runtime",
            str(runtime),
            "--evidence",
            str(evidence),
            "--exports",
            str(exports),
            "--job",
            "job",
            "--attempt",
            "attempt",
            "--revision",
            "3",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert database.read_bytes() == before, "Capture modified SQLite bytes"
    return out / "preservation.json", database, source


def verify(manifest):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "verify", str(manifest)], capture_output=True, text=True
    )


def test_capture_and_verify_are_read_only(baseline):
    manifest, database, _ = baseline
    before = database.read_bytes()
    result = verify(manifest)
    assert result.returncode == 0, result.stderr
    assert "unchanged" in result.stdout
    assert database.read_bytes() == before


def test_verify_detects_changed_source_bytes(baseline):
    manifest, _, source = baseline
    source.write_bytes(b"altered input")
    result = verify(manifest)
    assert result.returncode != 0
    assert "Saved ledger hash mismatch" in result.stderr


def test_verify_detects_changed_attempt_revision(baseline):
    manifest, database, _ = baseline
    with sqlite3.connect(database) as db:
        data = json.loads(db.execute("SELECT data FROM records WHERE kind='attempt'").fetchone()[0])
        data["revision"] = 4
        db.execute("UPDATE records SET data=? WHERE kind='attempt'", (json.dumps(data),))
    result = verify(manifest)
    assert result.returncode != 0
    assert "Pilot records/events/tasks changed" in result.stderr


def test_capture_cannot_overwrite_manifest(baseline):
    manifest, _, _ = baseline
    saved = json.loads(manifest.read_text())
    before = manifest.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "capture",
            "--runtime",
            saved["runtime"],
            "--evidence",
            saved["evidence"],
            "--exports",
            saved["exports"],
            "--job",
            "job",
            "--attempt",
            "attempt",
            "--revision",
            "3",
            "--out",
            str(manifest.parent),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "FileExistsError" in result.stderr
    assert manifest.read_bytes() == before
