import httpx
import pytest
from openjutsu.providers import Ambiguous, Provider, Rejected, estimate


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
