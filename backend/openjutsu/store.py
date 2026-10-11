import hashlib
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class Conflict(Exception):
    pass


def identifier():
    return uuid.uuid4().hex


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def money(value):
    from decimal import Decimal

    return int(Decimal(str(value)) * 1_000_000)


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / "jobs.sqlite"
        self.lock = threading.RLock()
        with self.transaction() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS records(kind TEXT, id TEXT, data TEXT, PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, job TEXT, data TEXT);
            CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, job TEXT, kind TEXT, data TEXT, state TEXT);
            CREATE UNIQUE INDEX IF NOT EXISTS operation ON records(kind, json_extract(data,'$.operation_id')) WHERE kind='attempt';
            """)

    @contextmanager
    def transaction(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=30)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA journal_mode=WAL")
            try:
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    @staticmethod
    def _get(db, kind, id):
        row = db.execute("SELECT data FROM records WHERE kind=? AND id=?", (kind, id)).fetchone()
        if row is None:
            raise KeyError(f"{kind} not found")
        return json.loads(row[0])

    @staticmethod
    def _put(db, kind, data):
        db.execute(
            "INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET data=excluded.data",
            (kind, data["id"], json.dumps(data)),
        )

    @staticmethod
    def _event(db, job, kind, **data):
        db.execute(
            "INSERT INTO events(job,data) VALUES(?,?)",
            (job, json.dumps({"kind": kind, "time": time.time(), **data})),
        )

    def get(self, kind, id):
        with self.transaction() as db:
            return self._get(db, kind, id)

    def put(self, kind, data):
        with self.transaction() as db:
            self._put(db, kind, data)
        return data

    def list(self, kind):
        with self.transaction() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT data FROM records WHERE kind=? ORDER BY rowid DESC", (kind,)
                )
            ]

    def update(self, kind, id, changes):
        with self.transaction() as db:
            data = self._get(db, kind, id)
            data.update(changes)
            data["updated"] = time.time()
            self._put(db, kind, data)
            if kind in {"job", "attempt"}:
                self._event(
                    db, id if kind == "job" else data["job"], "updated", record=kind, record_id=id
                )
            return data

    def create_job(self, request):
        self.get("asset", request.source)
        job = {
            "id": identifier(),
            "name": request.name,
            "source": request.source,
            "recipe": request.recipe.model_dump(),
            "revision": 1,
            "status": "imported",
            "stage": "prepare",
            "budget": money(request.budget_usd),
            "generation_limit": request.generation_limit,
            "spent": 0,
            "reserved": 0,
            "approval": None,
            "preview_approval": None,
            "artifacts": {},
            "progress": None,
            "error": None,
            "cancel": False,
            "created": time.time(),
        }
        with self.transaction() as db:
            self._put(db, "job", job)
            self._event(db, job["id"], "created")
        return job

    def budget(self, id, limit, generation_limit=None):
        with self.transaction() as db:
            job = self._get(db, "job", id)
            if limit < job["spent"] + job["reserved"]:
                raise Conflict("Limit cannot be below existing spend and reservations")
            job["budget"] = limit
            if generation_limit is not None:
                if job.get("generation_limit") and generation_limit > job["generation_limit"]:
                    raise Conflict("An existing generation limit can only be tightened")
                job["generation_limit"] = generation_limit
            self._put(db, "job", job)
            self._event(db, id, "budget", limit=limit)

    def recipe(self, id, revision, recipe):
        with self.transaction() as db:
            job = self._get(db, "job", id)
            self.check_revision(job, revision)
            if job["status"] in {"queued", "preparing", "generating", "exporting"}:
                raise Conflict("Wait for the active operation before editing")
            if self._unknown(db, id):
                raise Conflict("Reconcile the uncertain submission first")
            job.update(
                recipe=recipe,
                revision=revision + 1,
                approval=None,
                preview_approval=None,
                status="imported",
                stage="prepare",
                error=None,
            )
            self._put(db, "job", job)
            self._event(db, id, "revision", revision=job["revision"])
            return job

    @staticmethod
    def check_revision(job, revision):
        if job["revision"] != revision:
            raise Conflict("This job changed. Reload its latest revision.")

    @staticmethod
    def _unknown(db, job):
        return db.execute(
            "SELECT 1 FROM records WHERE kind='attempt' AND json_extract(data,'$.job')=? AND json_extract(data,'$.status') IN ('submitting','unknown_submission')",
            (job,),
        ).fetchone()

    def approve(self, id, revision, attempt=None):
        with self.transaction() as db:
            job = self._get(db, "job", id)
            self.check_revision(job, revision)
            if attempt:
                a = self._get(db, "attempt", attempt)
                if a["job"] != id or a["revision"] != revision or a["status"] != "succeeded":
                    raise Conflict("Select a successful preview from this revision")
                job["preview_approval"] = attempt
            else:
                if job["status"] != "review" or "conditioning" not in job["artifacts"]:
                    raise Conflict("Prepare and review the conditioning clip first")
                job["approval"] = {
                    "revision": revision,
                    "artifact": job["artifacts"]["conditioning"],
                }
                job["status"] = "approved"
                job["stage"] = "generate"
            self._put(db, "job", job)
            self._event(db, id, "approved", attempt=attempt)
            return job

    def reserve_attempt(self, job_id, revision, quote, operation, pilot=False, parent=None):
        with self.transaction() as db:
            existing = db.execute(
                "SELECT data FROM records WHERE kind='attempt' AND json_extract(data,'$.operation_id')=?",
                (operation,),
            ).fetchone()
            if existing:
                a = json.loads(existing[0])
                if a["job"] != job_id or a["quote"] != quote["id"]:
                    raise Conflict("Operation identifier belongs to a different request")
                return a
            job = self._get(db, "job", job_id)
            self.check_revision(job, revision)
            if not parent and job.get("generation_limit"):
                count = db.execute(
                    "SELECT count(*) FROM records WHERE kind='attempt' AND json_extract(data,'$.job')=? AND json_extract(data,'$.parent') IS NULL",
                    (job_id,),
                ).fetchone()[0]
                if count >= job["generation_limit"]:
                    raise Conflict("This project's generation submission limit has been reached")
            if (
                quote["job"] != job_id
                or quote["revision"] != revision
                or quote["expires"] <= time.time()
            ):
                raise Conflict("Refresh the expired or stale quote")
            if not job["approval"] or job["approval"]["revision"] != revision:
                raise Conflict("Approve this preparation first")
            if quote.get("artifact") and quote["artifact"] != job["approval"]["artifact"]:
                raise Conflict("Refresh the quote after preparation changes")
            if not quote["eligible"] or (not quote["qualified"] and not pilot):
                raise Conflict(quote.get("reason") or "A qualification pilot is required")
            if self._unknown(db, job_id) or job["status"] in {
                "queued",
                "preparing",
                "generating",
                "exporting",
            }:
                raise Conflict("An existing generation must be reconciled first")
            if parent and job["preview_approval"] != parent:
                raise Conflict("Approve the selected preview first")
            amount = quote["reserve"]
            if job["spent"] + job["reserved"] + amount > job["budget"]:
                raise Conflict("Increase the spending limit before this operation")
            attempt = {
                "id": identifier(),
                "job": job_id,
                "revision": revision,
                "operation_id": operation,
                "quote": quote["id"],
                "provider": quote["provider"],
                "account": quote["account"],
                "status": "submitting",
                "reservation": amount,
                "estimated": quote["estimate"],
                "actual": None,
                "remote_id": None,
                "draft_id": None,
                "draft_expires": None,
                "parent": parent,
                "pilot": pilot,
                "recipe_snapshot": job["recipe"],
                "conditioning": job["approval"]["artifact"],
                "artifact": None,
                "created": time.time(),
            }
            job["reserved"] += amount
            job.update(status="exporting" if parent else "generating", error=None)
            self._put(db, "job", job)
            self._put(db, "attempt", attempt)
            self._event(db, job_id, "submission_intent", attempt=attempt["id"])
            return attempt

    def settle(self, id, cost=None, failed=False):
        with self.transaction() as db:
            a = self._get(db, "attempt", id)
            if a.get("settled"):
                return a
            if cost is None and not failed:
                return a
            job = self._get(db, "job", a["job"])
            actual = 0 if failed else money(cost)
            job["reserved"] -= a["reservation"]
            job["spent"] += actual
            a.update(actual=actual, settled=True)
            self._put(db, "attempt", a)
            self._put(db, "job", job)
            self._event(db, a["job"], "settled", attempt=id, actual=actual)
            return a

    def enqueue(self, job_id, kind, payload):
        with self.transaction() as db:
            job = self._get(db, "job", job_id)
            if self._unknown(db, job_id):
                raise Conflict("Reconcile the uncertain paid submission first")
            if job["status"] in {"queued", "preparing", "generating", "exporting"}:
                raise Conflict("This job already has an active operation")
            id = identifier()
            db.execute(
                "INSERT INTO tasks VALUES(?,?,?,?,?)",
                (id, job_id, kind, json.dumps(payload), "queued"),
            )
            job.update(status="queued", cancel=False, error=None)
            self._put(db, "job", job)
            self._event(db, job_id, "queued", task=id)
            return id

    def claim(self):
        with self.transaction() as db:
            row = db.execute(
                "SELECT * FROM tasks WHERE state='queued' ORDER BY rowid LIMIT 1"
            ).fetchone()
            if not row:
                return None
            db.execute("UPDATE tasks SET state='running' WHERE id=?", (row["id"],))
            return {**dict(row), "data": json.loads(row["data"])}

    def task_done(self, id, state="done"):
        with self.transaction() as db:
            db.execute("UPDATE tasks SET state=? WHERE id=?", (state, id))

    def local_active(self, job):
        with self.transaction() as db:
            return (
                db.execute(
                    "SELECT 1 FROM tasks WHERE job=? AND state IN ('queued','running')", (job,)
                ).fetchone()
                is not None
            )

    def recover(self):
        with self.transaction() as db:
            db.execute("UPDATE tasks SET state='queued' WHERE state='running'")
            for row in db.execute("SELECT data FROM records WHERE kind='attempt'").fetchall():
                a = json.loads(row[0])
                if a["status"] == "submitting":
                    a["status"] = "unknown_submission"
                    self._put(db, "attempt", a)
                    self._event(db, a["job"], "submission_uncertain", attempt=a["id"])

    def events(self, after=0, job=None):
        with self.transaction() as db:
            sql = (
                "SELECT * FROM events WHERE id>?"
                + (" AND job=?" if job else "")
                + " ORDER BY id LIMIT 100"
            )
            args = (after, job) if job else (after,)
            return [
                {**json.loads(r["data"]), "id": r["id"], "job": r["job"]}
                for r in db.execute(sql, args)
            ]
