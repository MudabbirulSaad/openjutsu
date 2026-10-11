import httpx
import pytest
from openjutsu.providers import Ambiguous, Provider, Rejected, estimate, qualification_profile


def test_payloads_use_distinct_contracts():
    r = {"prompt": "Replace", "subjects": [], "start": 0, "end": 5}
    for name in ("byteplus", "segmind", "argolink"):
        p = Provider(name, {"api_key": "test"})
        payload = p.payload(r, "https://example.com/video.mp4", ["https://example.com/image.png"])
        if name == "argolink":
            assert payload["duration"] == 5
            assert "omni_reference_task_type" not in payload
            assert payload["reference_videos"] == [{"url": "https://example.com/video.mp4"}]
            with pytest.raises(Rejected):
                p.payload(r, "", [], {"draft_id": "draft"})
        else:
            assert payload["duration"] == -1
            assert payload["draft"]
            final = p.payload(r, "", [], {"draft_id": "draft"})
            assert "prompt" not in final
        p.close()


def test_portrait_reference_payload_has_three_ordered_casts_and_portrait_ratio():
    recipe = {
        "prompt": "Keep the original camera moves",
        "start": 0,
        "end": 18,
        "argolink_mode": "reference",
        "subjects": [
            {
                "id": i,
                "name": f"Cast {i}",
                "references": [f"photo-{i}"],
                "intervals": [{"start": (i - 1) * 100, "end": i * 100}],
            }
            for i in [3, 1, 2]
        ],
    }
    provider = Provider("argolink", {"api_key": "test"})
    payload = provider.payload(
        recipe,
        "https://media.example/clip",
        ["https://media.example/1", "https://media.example/2", "https://media.example/3"],
        media={"width": 540, "height": 960},
    )
    assert payload["duration"] == 18 and payload["aspect_ratio"] == "9:16"
    assert payload["resolution"] == "480p" and payload["generate_audio"] is False
    assert (
        payload["prompt"].index("Cast 1")
        < payload["prompt"].index("Cast 2")
        < payload["prompt"].index("Cast 3")
    )
    assert "@Image 3" in payload["prompt"] and "8.333" in payload["prompt"]
    with pytest.raises(Rejected, match="disputed"):
        provider.payload(
            {**recipe, "argolink_mode": "edit"},
            "https://media.example/clip",
            ["https://media.example/1"],
        )
    provider.close()


def test_direct_upload_uses_real_size_expiry_and_no_account_header_at_storage(tmp_path):
    import json
    import time

    from openjutsu.config import Secrets
    from openjutsu.providers import Uploads
    from openjutsu.store import Store

    path = tmp_path / "reference.png"
    path.write_bytes(b"synthetic-image")
    requests = []

    def respond(request):
        requests.append(request)
        if request.method == "POST":
            body = json.loads(request.content)
            assert body["size_bytes"] == path.stat().st_size
            assert body["type"] == "image" and body["content_type"] == "image/png"
            assert request.headers["authorization"] == "Bearer test-only"
            return httpx.Response(
                200,
                json={
                    "upload_url": "https://objects.example/put",
                    "media_url": "https://objects.example/read",
                    "upload_expires_at": time.time() + 900,
                    "expires_at": time.time() + 604800,
                },
            )
        assert request.method == "PUT" and request.content == b"synthetic-image"
        assert "authorization" not in request.headers
        assert request.headers["content-type"] == "image/png"
        return httpx.Response(200)

    provider = Provider("argolink", {"api_key": "test-only"}, httpx.MockTransport(respond))
    store = Store(tmp_path)
    uploads = Uploads(Secrets(tmp_path), store)
    assert uploads.put(path, "pilot", provider) == "https://objects.example/read"
    record = store.list("upload")[0]
    assert record["deletable"] is False and record["expires"] > time.time() + 600000
    store.update("upload", record["id"], {"expires": 0})
    uploads.cleanup()  # Provider-managed expiry must never invoke S3 deletion.
    assert len(requests) == 2
    provider.close()


def test_expired_upload_never_puts_or_generates(tmp_path):
    calls = []
    path = tmp_path / "clip.mp4"
    path.write_bytes(b"synthetic-video")

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "upload_url": "https://objects.example/put",
                "media_url": "https://objects.example/read",
                "upload_expires_at": 0,
                "expires_at": 1,
            },
        )

    provider = Provider("argolink", {"api_key": "test"}, httpx.MockTransport(respond))
    with pytest.raises(Rejected, match="expired"):
        provider.upload(path)
    assert len(calls) == 1
    provider.close()


def test_argolink_humans_need_consent_but_not_s3_or_quality_qualification(tmp_path):
    from openjutsu.config import Secrets
    from openjutsu.providers import make_quotes
    from openjutsu.store import Store

    store, secrets = Store(tmp_path), Secrets(tmp_path)
    secrets.update("argolink", {"api_key": "test-only"})
    clip, photo = tmp_path / "conditioning.mp4", tmp_path / "reference.png"
    clip.write_bytes(b"synthetic-video")
    photo.write_bytes(b"synthetic-image")
    store.put("asset", {"id": "ref", "path": str(photo)})
    store.put(
        "artifact",
        {
            "id": "clip",
            "path": str(clip),
            "metadata": {"duration": 18, "width": 540, "height": 960},
        },
    )
    job = {
        "id": "job",
        "revision": 1,
        "artifacts": {"conditioning": "clip"},
        "recipe": {
            "mode": "advanced",
            "argolink_mode": "reference",
            "subjects": [{"id": 1, "kind": "human", "references": ["ref"]}],
        },
    }

    def quote():
        return next(q for q in make_quotes(store, secrets, job) if q["provider"] == "argolink")

    assert not quote()["eligible"]
    job["recipe"]["subjects"][0]["consent_confirmed"] = True
    q = quote()
    assert q["eligible"] and not q["qualified"]
    assert q["estimate"] == pytest.approx(1.8828)
    assert q["upload_retention_days"] == 7


def test_usage_estimate_is_not_a_settled_receipt():
    p = Provider(
        "argolink",
        {"api_key": "test"},
        httpx.MockTransport(
            lambda _: httpx.Response(200, json={"status": "done", "usage": {"billed_seconds": 36}})
        ),
    )
    result = p.poll("one-request")
    assert result["cost"] is None and result["usage_estimate_usd"] == pytest.approx(1.8828)
    p.close()


def test_transport_failure_is_ambiguous_and_not_retried():
    calls = []

    def fail(request):
        calls.append(request)
        raise httpx.ReadTimeout("uncertain")

    p = Provider("argolink", {"api_key": "test"}, httpx.MockTransport(fail))
    with pytest.raises(Ambiguous):
        p.submit({"model": "seedance-2.5"})
    assert len(calls) == 1
    p.close()


def test_prices_include_reference_and_separate_final():
    assert estimate("argolink", 5, 1920, 1080) == pytest.approx(0.523)
    assert estimate("segmind", 5, 1920, 1080, True) < estimate("byteplus", 5, 1920, 1080, True)


def test_status_download_contract_preserves_draft_and_reported_charge():
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "completed"})
        return httpx.Response(
            200,
            json={
                "video": {
                    "url": "https://results.example/video.mp4",
                    "draft_task_id": "native-draft",
                },
                "cost": 0.42,
            },
        )

    provider = Provider("segmind", {"api_key": "test"}, httpx.MockTransport(respond))
    result = provider.poll("existing-request")
    assert result["draft_id"] == "native-draft"
    assert result["cost"] == 0.42
    assert len(requests) == 2 and all(r.method == "GET" for r in requests)
    provider.close()


def test_remote_refusal_does_not_assume_zero_billing():
    provider = Provider(
        "byteplus",
        {"api_key": "test"},
        httpx.MockTransport(lambda _: httpx.Response(200, json={"status": "failed"})),
    )
    result = provider.poll("existing-request")
    assert result["status"] == "failed" and result["cost"] is None
    provider.close()


def test_qualifications_distinguish_native_and_subject_profiles():
    recipe = {"mode": "advanced", "subjects": [{"id": 1, "kind": "fictional"}]}
    preview = qualification_profile("segmind", recipe)
    assert preview != qualification_profile("segmind", recipe, True)
    assert preview != qualification_profile(
        "segmind", {**recipe, "subjects": [{"id": 1, "kind": "human"}]}
    )


def test_finished_native_quotes_include_final_cost_and_exclude_noncontinuing_route(tmp_path):
    from openjutsu.config import Secrets
    from openjutsu.providers import account, make_quotes
    from openjutsu.store import Store

    store = Store(tmp_path)
    secrets = Secrets(tmp_path)
    clip = tmp_path / "conditioning.mp4"
    clip.write_bytes(b"synthetic contract fixture")
    store.put(
        "artifact",
        {
            "id": "conditioning",
            "path": str(clip),
            "metadata": {"duration": 5, "width": 960, "height": 540},
        },
    )
    recipe = {"mode": "advanced", "subjects": [{"id": 1, "kind": "fictional"}]}
    job = {
        "id": "job",
        "revision": 1,
        "recipe": recipe,
        "artifacts": {"conditioning": "conditioning"},
    }
    secrets.update(
        "storage",
        {
            "bucket": "synthetic",
            "endpoint": "https://storage.example",
            "access_key": "test",
            "secret_key": "test",
        },
    )
    for name in ("argolink", "segmind", "byteplus"):
        config = {"api_key": "test-only"}
        secrets.update(name, config)
        for native in (False, True):
            store.put(
                "qualification",
                {
                    "id": name + str(native),
                    "provider": name,
                    "account": account(config),
                    "profile": qualification_profile(name, recipe, native),
                },
            )
    quotes = make_quotes(store, secrets, job, finish="native")
    eligible = [q for q in quotes if q["eligible"]]
    assert eligible[0]["provider"] == "segmind"
    assert all(q["finished_estimate"] > q["estimate"] for q in eligible)
    assert not next(q for q in quotes if q["provider"] == "argolink")["eligible"]
