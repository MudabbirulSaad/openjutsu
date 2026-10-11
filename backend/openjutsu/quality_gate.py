"""Immutable report and reasoned-review binding at the approval boundary."""

import json
from pathlib import Path

from .media import digest
from .quality import REPORT_VERSION, apply_reviews
from .store import Conflict, fingerprint


def evidence(record):
    path = Path(record["path"])
    stat = path.stat()
    return {
        "id": record["id"],
        "hash": record["hash"],
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def make_binding(job, source, artifacts):
    return {
        "job": job["id"],
        "revision": job["revision"],
        "recipe_hash": fingerprint(job["recipe"]),
        "source": evidence(source),
        "artifacts": {kind: evidence(record) for kind, record in artifacts.items()},
    }


def read_quality(job, get, *, strict=True):
    try:
        record = get("artifact", job["artifacts"]["quality"])
        if record["job"] != job["id"] or record["revision"] != job["revision"]:
            raise ValueError("Quality report belongs to a different preparation")
        if digest(record["path"]) != record["hash"]:
            raise ValueError("Quality report bytes changed")
        report = json.loads(Path(record["path"]).read_text())
        binding = report["binding"]
        if report["version"] != REPORT_VERSION or (
            binding["job"],
            binding["revision"],
            binding["recipe_hash"],
        ) != (job["id"], job["revision"], fingerprint(job["recipe"])):
            raise ValueError("Quality report is stale for this recipe revision")
        expected = {"normalized", "timeline", "conditioning"}
        if job["recipe"]["mode"] != "fast":
            expected |= {"mask", "mask_data", "tracking", "depth", "depth_data", "composite"}
        if not expected <= binding["artifacts"].keys():
            raise ValueError("Quality report omits required preparation artifacts")
        if len(report["frames"]) != round((job["recipe"]["end"] - job["recipe"]["start"]) * 24):
            raise ValueError("Quality report does not validate the complete frame sequence")
        pairs = [(binding["source"], get("asset", job["source"]))]
        for kind, bound in binding["artifacts"].items():
            artifact = get("artifact", job["artifacts"][kind])
            if artifact["job"] != job["id"] or artifact["revision"] != job["revision"]:
                raise ValueError("Preparation artifact belongs to a different job or revision")
            pairs.append((bound, artifact))
        for bound, current in pairs:
            if evidence(current) != bound or strict and digest(current["path"]) != bound["hash"]:
                raise ValueError("Preparation artifact changed; prepare and review it again")
        reviews = job.get("quality_reviews", [])
        if any(
            r["report_id"] != record["id"] or r["report_hash"] != record["hash"] for r in reviews
        ):
            raise ValueError("Review decisions belong to a stale report")
        effective = apply_reviews(report, reviews)
        effective["report_id"] = record["id"]
        effective["report_hash"] = record["hash"]
        return effective
    except (KeyError, OSError, ValueError, TypeError) as exc:
        raise Conflict(
            "Preparation quality evidence is missing, unreadable or stale: " + str(exc)
        ) from exc


def receipt(report):
    return {
        "report_id": report["report_id"],
        "report_hash": report["report_hash"],
        "binding_hash": fingerprint(report["binding"]),
        "review_hash": fingerprint(
            [f.get("review") for f in report["findings"] if f.get("review")]
        ),
    }


def require_quality(job, get, *, approved=False):
    report = read_quality(job, get)
    if not report["approval_ready"]:
        counts = report["counts"]
        raise Conflict(
            f"Preparation quality blocks approval: {counts['BLOCKED']} critical/required "
            f"findings and {counts['WARNING']} warnings need correction or explicit review"
        )
    result = receipt(report)
    if approved and (job.get("approval") or {}).get("quality") != result:
        raise Conflict("Approve the current quality report before generation")
    return result
