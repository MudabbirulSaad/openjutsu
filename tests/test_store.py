from concurrent.futures import ThreadPoolExecutor

import pytest
from openjutsu.store import Conflict, Store, money
from openjutsu.types import CreateJob


@pytest.fixture
def prepared(tmp_path):
    s = Store(tmp_path)
    s.put("asset", {"id": "source"})
    j = s.create_job(CreateJob(source="source", budget_usd=1))
    s.update("job", j["id"], {"status": "review", "artifacts": {"conditioning": "clip"}})
    s.approve(j["id"], 1)
    return s, j["id"]


def quote(job, id="q"):
    return {
        "id": id,
        "job": job,
        "revision": 1,
        "expires": 9999999999,
        "eligible": True,
        "qualified": True,
        "reserve": money(0.7),
        "estimate": 0.6,
        "provider": "test",
        "account": "account",
    }


def test_duplicate_operations_reserve_once(prepared):
    s, job = prepared
    with ThreadPoolExecutor(2) as pool:
        attempts = list(
            pool.map(lambda _: s.reserve_attempt(job, 1, quote(job), "same-operation"), range(2))
        )
    assert attempts[0]["id"] == attempts[1]["id"]
    assert s.get("job", job)["reserved"] == money(0.7)


def test_uncertain_submission_survives_restart(prepared):
    s, job = prepared
    a = s.reserve_attempt(job, 1, quote(job), "operation-one")
    s.recover()
    assert s.get("attempt", a["id"])["status"] == "unknown_submission"
    with pytest.raises(Conflict):
        s.reserve_attempt(job, 1, quote(job), "operation-two")
    assert s.get("job", job)["reserved"] == money(0.7)


def test_settlement_is_idempotent(prepared):
    s, job = prepared
    a = s.reserve_attempt(job, 1, quote(job), "operation-one")
    s.settle(a["id"], 0.42)
    s.settle(a["id"], 0.42)
    assert s.get("job", job)["spent"] == money(0.42)
    assert s.get("job", job)["reserved"] == 0


def test_recipe_invalidates_approval_and_stale_revision(prepared):
    s, job = prepared
    old = s.get("job", job)
    new = s.recipe(job, 1, {**old["recipe"], "pitch": 0})
    assert new["approval"] is None
    assert new["revision"] == 2
    with pytest.raises(Conflict):
        s.recipe(job, 1, old["recipe"])


def test_overspending_rejected(prepared):
    s, job = prepared
    q = quote(job)
    q["reserve"] = money(2)
    with pytest.raises(Conflict, match="spending"):
        s.reserve_attempt(job, 1, q, "operation-one")


def test_paid_operation_cannot_race_repreparation_or_use_stale_conditioning(prepared):
    s, job = prepared
    s.update("job", job, {"status": "preparing"})
    with pytest.raises(Conflict):
        s.reserve_attempt(job, 1, quote(job), "operation-one")
    s.update("job", job, {"status": "approved"})
    with pytest.raises(Conflict, match="quote"):
        s.reserve_attempt(job, 1, {**quote(job), "artifact": "different-clip"}, "operation-two")


def test_one_generation_limit_survives_failure_revision_and_restart(prepared):
    s, job = prepared
    s.budget(job, money(10), generation_limit=1)
    a = s.reserve_attempt(job, 1, quote(job), "one-authorized-generation")
    s.update("attempt", a["id"], {"status": "failed"})
    s.settle(a["id"], failed=True)
    s.update("job", job, {"status": "approved"})
    assert s.reserve_attempt(job, 1, quote(job), "one-authorized-generation")["id"] == a["id"]
    reopened = Store(s.root)
    with pytest.raises(Conflict, match="submission limit"):
        reopened.reserve_attempt(job, 1, quote(job), "another-generation")
    with pytest.raises(Conflict, match="tightened"):
        reopened.budget(job, money(10), generation_limit=2)
