import pytest
from fastapi.testclient import TestClient
from openjutsu.api import create_app
from openjutsu.config import Config
from openjutsu.store import money


@pytest.fixture
def client(tmp_path):
    app = create_app(Config(tmp_path, tmp_path / "models"), start_workers=False)
    s = app.state.store
    s.put(
        "asset",
        {
            "id": "source",
            "kind": "video",
            "path": "private",
            "metadata": {"duration": 5, "has_audio": False},
        },
    )
    with TestClient(app) as c:
        yield c, s


def test_origin_and_credentials(client):
    c, _ = client
    assert (
        c.post(
            "/api/settings/argolink",
            json={"values": {"api_key": "private-value"}},
            headers={"origin": "https://other.example"},
        ).status_code
        == 403
    )
    assert (
        c.post("/api/settings/argolink", json={"values": {"api_key": "private-value"}}).status_code
        == 200
    )
    assert "private-value" not in c.get("/api/system").text


def test_reusable_template_does_not_reuse_another_portraits_consent_or_intervals(client):
    c, _ = client
    response = c.post(
        "/api/jobs",
        json={
            "source": "source",
            "recipe": {
                "end": 4,
                "subjects": [
                    {
                        "id": 1,
                        "kind": "human",
                        "consent_confirmed": True,
                        "references": ["reference"],
                        "intervals": [{"start": 0, "end": 96}],
                        "visibility": [
                            {
                                "start": 0,
                                "end": 20,
                                "state": "fully_occluded",
                                "reason": "Synthetic occluder",
                            }
                        ],
                        "seed_frame": 30,
                    }
                ],
            },
        },
    )
    assert response.status_code == 200
    saved = c.post(f"/api/jobs/{response.json()['id']}/save-recipe").json()
    subject = saved["recipe"]["subjects"][0]
    assert subject["consent_confirmed"] is False
    assert subject["references"] == [] and subject["intervals"] == []
    assert subject["visibility"] == [] and subject["seed_frame"] is None


def test_revision_conflict_and_budget(client):
    c, s = client
    j = c.post("/api/jobs", json={"source": "source"}).json()
    id = j["id"]
    assert (
        c.put(f"/api/jobs/{id}/recipe", json={"revision": 1, "recipe": {"end": 4}}).status_code
        == 200
    )
    assert (
        c.put(f"/api/jobs/{id}/recipe", json={"revision": 1, "recipe": {"end": 4}}).status_code
        == 409
    )
    s.update("job", id, {"reserved": money(1)})
    assert c.put(f"/api/jobs/{id}/budget", json={"budget_usd": 0.5}).status_code == 409


def test_approval_cannot_be_forged(client):
    c, _ = client
    j = c.post("/api/jobs", json={"source": "source"}).json()
    assert c.post(f"/api/jobs/{j['id']}/approve", json={"revision": 1}).status_code == 409
    assert c.post(f"/api/jobs/{j['id']}/prepare", json={"revision": 1}).status_code == 409


def test_annotation_validation(client):
    c, _ = client
    j = c.post("/api/jobs", json={"source": "source"}).json()
    response = c.put(
        f"/api/jobs/{j['id']}/recipe",
        json={
            "revision": 1,
            "recipe": {
                "subjects": [
                    {"id": 1, "annotations": [{"frame": 0, "points": [{"x": 1.2, "y": 0.5}]}]}
                ]
            },
        },
    )
    assert response.status_code == 422
