"""Preparation approval must reject absent or stale quality evidence at the API/Store seam."""

from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest
from openjutsu.quality import finding
from openjutsu.quality_runtime import check_required_files
from openjutsu.store import Conflict
from quality_test_utils import attach_quality
from test_api import client as client


def test_api_cannot_approve_conditioning_without_a_quality_report(client, tmp_path):
    api, store = client
    job = api.post("/api/jobs", json={"source": "source"}).json()
    conditioning = tmp_path / "unvalidated.mp4"
    conditioning.write_bytes(b"synthetic unvalidated conditioning")
    store.put(
        "artifact",
        {
            "id": "conditioning",
            "job": job["id"],
            "revision": 1,
            "kind": "conditioning",
            "path": str(conditioning),
            "hash": sha256(conditioning.read_bytes()).hexdigest(),
            "metadata": {},
        },
    )
    store.update(
        "job",
        job["id"],
        {
            "status": "review",
            "stage": "review",
            "artifacts": {"conditioning": "conditioning"},
        },
    )
    response = api.post(f"/api/jobs/{job['id']}/approve", json={"revision": 1})
    assert response.status_code == 409, "Conditioning approved without quality validation"
    assert store.get("job", job["id"])["approval"] is None
    assert not api.get(f"/api/jobs/{job['id']}").json()["available_actions"]["approve"]


def test_api_requires_reasoned_review_and_binds_receipt(client):
    api, store = client
    job = api.post("/api/jobs", json={"source": "source"}).json()
    attach_quality(store, job["id"], reviewed=False)
    report = api.get(f"/api/jobs/{job['id']}/quality").json()
    assert api.post(f"/api/jobs/{job['id']}/approve", json={"revision": 1}).status_code == 409
    target = report["findings"][0]
    body = {
        "revision": 1,
        "report_id": report["report_id"],
        "finding_id": target["id"],
        "resolution": "preserve_background",
        "reason": "Synthetic background only; no intended person",
    }
    assert (
        api.post(f"/api/jobs/{job['id']}/quality-review", json={**body, "reason": ""}).status_code
        == 422
    )
    assert api.post(f"/api/jobs/{job['id']}/quality-review", json=body).status_code == 200
    approved = api.post(f"/api/jobs/{job['id']}/approve", json={"revision": 1})
    assert approved.status_code == 200
    assert approved.json()["approval"]["quality"]["report_hash"] == report["report_hash"]


@pytest.mark.parametrize("kind", ["conditioning", "mask_data", "depth_data", "quality"])
def test_mutated_or_unreadable_artifact_invalidates_approval(client, kind):
    api, store = client
    job = api.post("/api/jobs", json={"source": "source"}).json()
    prepared = attach_quality(store, job["id"])
    assert api.post(f"/api/jobs/{job['id']}/approve", json={"revision": 1}).status_code == 200
    record = store.get("artifact", prepared["artifacts"][kind])
    Path(record["path"]).write_bytes(b"changed unreadable artifact")
    assert not api.get(f"/api/jobs/{job['id']}").json()["available_actions"]["generate"]
    from test_store import quote

    with pytest.raises(Conflict, match="stale"):
        store.reserve_attempt(job["id"], 1, quote(job["id"]), "must-not-reserve")
    assert store.get("job", job["id"])["reserved"] == 0


def test_recipe_quality_threshold_and_region_changes_invalidate_review(client):
    api, store = client
    job = api.post("/api/jobs", json={"source": "source"}).json()
    attach_quality(store, job["id"])
    assert api.post(f"/api/jobs/{job['id']}/approve", json={"revision": 1}).status_code == 200
    recipe = store.get("job", job["id"])["recipe"]
    recipe["quality_policy"]["structural_mae"] = 10
    updated = api.put(f"/api/jobs/{job['id']}/recipe", json={"revision": 1, "recipe": recipe})
    assert updated.status_code == 200 and updated.json()["approval"] is None
    assert store.get("job", job["id"])["quality_reviews"] == []
    assert api.post(f"/api/jobs/{job['id']}/approve", json={"revision": 2}).status_code == 409


def test_api_cannot_waive_confirmed_critical_defects(client):
    api, store = client
    job = api.post("/api/jobs", json={"source": "source"}).json()
    defect = finding("source_face_rgb", "BLOCKED", 2, 3, 1, "Synthetic original face remains")
    attach_quality(store, job["id"], findings=[defect], reviewed=False)
    response = api.post(
        f"/api/jobs/{job['id']}/quality-review",
        json={
            "revision": 1,
            "report_id": "quality",
            "finding_id": defect["id"],
            "resolution": "inspected",
            "reason": "Trying to waive a confirmed defect",
        },
    )
    assert response.status_code == 409 and "cannot be manually waived" in response.text
    assert api.post(f"/api/jobs/{job['id']}/approve", json={"revision": 1}).status_code == 409


def test_changed_bytes_after_reservation_are_rejected_before_provider_or_upload(
    client, monkeypatch
):
    from test_store import quote

    api, store = client
    job = api.post("/api/jobs", json={"source": "source", "budget_usd": 1}).json()
    prepared = attach_quality(store, job["id"])
    store.approve(job["id"], 1)
    attempt = store.reserve_attempt(job["id"], 1, quote(job["id"]), "local-reservation-test")
    path = Path(store.get("artifact", prepared["artifacts"]["conditioning"])["path"])
    path.write_bytes(b"changed after approval and reservation")

    def forbidden(*args, **kwargs):
        raise AssertionError("Provider/upload boundary reached with stale evidence")

    engine = api.app.state.engine
    monkeypatch.setattr("openjutsu.engine.Provider", forbidden)
    monkeypatch.setattr(engine.uploads, "put", forbidden)
    engine.submit_attempt(attempt)
    failed = store.get("attempt", attempt["id"])
    assert failed["status"] == "failed" and failed["remote_id"] is None
    assert "stale" in failed["error"] and store.get("job", job["id"])["reserved"] == 0


def test_collision_report_cannot_be_waived(client):
    api, store = client
    job = api.post("/api/jobs", json={"source": "source"}).json()
    defect = finding("subject_collision", "BLOCKED", 0, 120, 1, "Synthetic IDs overlap")
    attach_quality(store, job["id"], findings=[defect], reviewed=False)
    assert api.post(f"/api/jobs/{job['id']}/approve", json={"revision": 1}).status_code == 409


def test_new_preparation_clears_previous_receipt_even_at_same_revision(client):
    api, store = client
    job = api.post("/api/jobs", json={"source": "source"}).json()
    attach_quality(store, job["id"])
    store.approve(job["id"], 1)
    store.enqueue(job["id"], "prepare", {"revision": 1})
    assert store.get("job", job["id"])["approval"] is None
    assert store.get("job", job["id"])["quality_reviews"] == []


def test_unreadable_required_depth_archive_fails_safely(tmp_path):
    kinds = {
        "normalized",
        "timeline",
        "conditioning",
        "mask",
        "mask_data",
        "tracking",
        "depth",
        "depth_data",
        "composite",
    }
    paths, artifacts = {}, {}
    for kind in kinds:
        path = tmp_path / kind
        path.write_bytes(b"synthetic invalid required artifact")
        paths[kind] = path
        artifacts[kind] = {"hash": sha256(path.read_bytes()).hexdigest()}
    import json
    from zipfile import BadZipFile

    paths["timeline"].write_text(
        json.dumps({"fps": 24, "frames": [{"frame": f} for f in range(4)]})
    )
    artifacts["timeline"]["hash"] = sha256(paths["timeline"].read_bytes()).hexdigest()

    with pytest.raises(BadZipFile):
        check_required_files({"mode": "advanced"}, {"artifacts": artifacts}, paths, 4)
    np.savez(tmp_path / "readable.npz", depths=np.ones((4, 3, 3)))
    paths["depth_data"] = tmp_path / "readable.npz"
    artifacts["depth_data"]["hash"] = sha256(paths["depth_data"].read_bytes()).hexdigest()
    assert "depth_data" in check_required_files(
        {"mode": "advanced"}, {"artifacts": artifacts}, paths, 4
    )


def test_unreadable_artifact_produces_a_blocked_incomplete_audit(tmp_path, monkeypatch):
    import json
    import sys
    from types import SimpleNamespace

    from openjutsu.quality_runtime import audit_artifacts

    # No model or decoder is entered: the actual preflight fails before inference.
    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace())
    monkeypatch.setattr(
        "openjutsu.quality_runtime.probe",
        lambda _: {
            "frames": 4,
            "height": 3,
            "width": 3,
        },
    )
    paths, artifacts = {}, {}
    for kind in {
        "normalized",
        "timeline",
        "conditioning",
        "mask",
        "mask_data",
        "tracking",
        "depth",
        "depth_data",
        "composite",
    }:
        path = tmp_path / kind
        path.write_bytes(b"unreadable artifact")
        if kind == "timeline":
            path.write_text(json.dumps({"fps": 24, "frames": [{"frame": f} for f in range(4)]}))
        paths[kind] = path
        artifacts[kind] = {"id": kind, "hash": sha256(path.read_bytes()).hexdigest()}
    report = audit_artifacts(
        {"mode": "advanced", "subjects": []}, {"artifacts": artifacts}, paths, tmp_path
    )
    assert report["status"] == "BLOCKED" and not report["approval_ready"]
    assert {"artifact_validation_failed", "incomplete_frame_audit"} <= {
        f["code"] for f in report["findings"] if f["status"] == "BLOCKED"
    }
