import httpx
import pytest
from openjutsu.providers import Ambiguous, Provider, Rejected, estimate, qualification_profile


def test_edit_payloads_use_distinct_contracts():
    r = {"prompt": "Replace", "subjects": []}
    for name in ("byteplus", "segmind", "argolink"):
        p = Provider(name, {"api_key": "test"})
        payload = p.payload(r, "https://example.com/video.mp4", ["https://example.com/image.png"])
        if name == "argolink":
            assert "duration" not in payload
            assert payload["reference_videos"] == [{"url": "https://example.com/video.mp4"}]
            with pytest.raises(Rejected):
                p.payload(r, "", [], {"draft_id": "draft"})
        else:
            assert payload["duration"] == -1
            assert payload["draft"]
            final = p.payload(r, "", [], {"draft_id": "draft"})
            assert "prompt" not in final
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
