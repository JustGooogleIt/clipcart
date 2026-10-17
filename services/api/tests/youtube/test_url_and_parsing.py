import json

import httpx
import pytest

from app.providers.gemini.client import GeminiClient, GeminiError
from app.providers.gemini.garments import SCHEMA, build_prompt, parse_ts, validate_garments
from app.youtube.url import YouTubeUrlError, parse_youtube_url

VID = "jNQXAC9IVRw"


@pytest.mark.parametrize("url", [
    f"https://www.youtube.com/watch?v={VID}",
    f"https://youtube.com/watch?v={VID}&t=12s",
    f"youtube.com/watch?feature=share&v={VID}",
    f"https://m.youtube.com/watch?v={VID}",
    f"https://music.youtube.com/watch?v={VID}",
    f"https://youtu.be/{VID}?si=abc",
    f"https://www.youtube.com/shorts/{VID}",
    f"https://www.youtube.com/embed/{VID}",
    f"https://www.youtube-nocookie.com/embed/{VID}",
])
def test_valid_urls_canonicalize(url):
    ref = parse_youtube_url(url)
    assert ref.video_id == VID and ref.canonical_url == f"https://www.youtube.com/watch?v={VID}"


@pytest.mark.parametrize("url,code", [
    ("", "invalid_url"),
    ("not a url at all", "invalid_url"),
    ("https://www.youtube.com/watch?v=short", "invalid_url"),
    ("https://www.youtube.com/watch", "invalid_url"),
    ("ftp://youtube.com/watch?v=jNQXAC9IVRw", "invalid_url"),
    ("https://user:pw@youtube.com/watch?v=jNQXAC9IVRw", "invalid_url"),
    ("https://evil.example/watch?v=jNQXAC9IVRw", "unsupported_url"),
    ("https://youtube.com.evil.example/watch?v=jNQXAC9IVRw", "unsupported_url"),
    ("https://vimeo.com/123", "unsupported_url"),
    ("https://www.youtube.com/playlist?list=PL123", "unsupported_url"),
    ("https://www.youtube.com/@somechannel", "unsupported_url"),
    ("https://www.youtube.com/live/jNQXAC9IVRw", "unsupported_url"),
    ("https://www.youtube.com/clip/UgkxABC", "unsupported_url"),
])
def test_invalid_and_unsupported_urls(url, code):
    with pytest.raises(YouTubeUrlError) as e:
        parse_youtube_url(url)
    assert e.value.code == code


def test_timestamp_parsing():
    assert parse_ts("01:15") == 75 and parse_ts("1:02:03") == 3723 and parse_ts(12) == 12
    assert parse_ts("1:75") is None and parse_ts("soon") is None and parse_ts(-3) is None


def test_validation_rejects_instead_of_repairing():
    payload = {"garments": [
        {"category": "jacket", "description": "Dark zip jacket", "timestamps": ["00:05", "00:07", "09:00"],
         "person_label": "person_1", "colors": ["black", "Black"], "visible_text": ["ACME"]},
        {"category": "shoes", "description": "sneakers", "timestamps": ["00:03"]},
        {"category": "top", "description": "", "timestamps": ["00:03"]},
        {"category": "bag", "description": "tote", "timestamps": ["05:00"]},
        {"category": "top", "description": "grey tee", "timestamps": ["00:10"], "person_label": "Jawed Karim"},
    ]}
    gs, dropped = validate_garments(payload, start_s=0, end_s=19, video_id=VID)
    assert [g.category for g in gs] == ["jacket", "top"] and dropped == 3
    assert [t.seconds for t in gs[0].timestamps] == [5, 7] and gs[0].colors == ["black"]
    assert gs[1].person_label is None  # names are never stored as person labels
    assert all(g.source == "gemini_youtube" for g in gs)
    with pytest.raises(ValueError):
        validate_garments({"items": []}, start_s=0, end_s=10, video_id=VID)


def _client(handler):
    return GeminiClient(model="gemini-test", api_key="k-test", http=httpx.Client(transport=httpx.MockTransport(handler)))


def ok_body(text, status="completed"):
    return {"id": "int_123", "status": status, "model": "gemini-test", "usage": {"total_tokens": 900},
            "steps": [{"type": "thought", "signature": "x"},
                      {"type": "model_output", "content": [{"type": "text", "text": text}]}]}


def test_client_request_shape_and_parsing():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["headers"] = dict(req.headers)
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=ok_body('{"garments": []}'))

    r = _client(handler).analyze_youtube(f"https://www.youtube.com/watch?v={VID}", build_prompt(0, 19), SCHEMA,
                                         start_s=0, end_s=19)
    assert r.text == '{"garments": []}' and r.interaction_id == "int_123"
    b = seen["body"]
    assert seen["url"].endswith("/interactions") and "k-test" not in seen["url"]
    assert seen["headers"]["x-goog-api-key"] == "k-test" and seen["headers"]["api-revision"]
    video = b["input"][0]
    assert video["type"] == "video" and video["uri"].endswith(VID) and video["resolution"] == "low"
    assert video["processing"] == {"type": "static", "fps": 0.5, "start_offset": 0, "end_offset": 19}
    assert b["store"] is False and b["response_format"]["mime_type"] == "application/json"
    assert b["generation_config"]["max_output_tokens"] <= 2048


@pytest.mark.parametrize("status,body,code", [
    (400, {"error": {"code": 400, "message": "The YouTube video is private or unavailable.", "status": "INVALID_ARGUMENT"}}, "video_inaccessible"),
    (403, {"error": {"code": 403, "message": "Video not public", "status": "PERMISSION_DENIED"}}, "video_inaccessible"),
    (401, {"error": {"code": 401, "message": "API key not valid", "status": "UNAUTHENTICATED"}}, "auth_error"),
    (403, {"error": {"code": 403, "message": "API key not valid. Please pass a valid API key.", "status": "PERMISSION_DENIED"}}, "auth_error"),
    (429, {"error": {"code": 429, "message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}}, "rate_limited"),
    (500, {"error": {"code": 500, "message": "internal", "status": "INTERNAL"}}, "unavailable"),
    (400, {"error": {"code": 400, "message": "Invalid JSON payload received", "status": "INVALID_ARGUMENT"}}, "invalid_request"),
])
def test_client_error_mapping(status, body, code):
    with pytest.raises(GeminiError) as e:
        _client(lambda req: httpx.Response(status, json=body)).analyze_youtube("u", "p", SCHEMA, start_s=0, end_s=10)
    assert e.value.code == code


def test_client_incomplete_and_failed_interactions():
    with pytest.raises(GeminiError) as e:
        _client(lambda r: httpx.Response(200, json=ok_body("{", status="incomplete"))).analyze_youtube("u", "p", SCHEMA, start_s=0, end_s=5)
    assert e.value.code == "invalid_response"
    failed = {"id": "int_9", "status": "failed", "errors": [{"code": "x", "message": "Cannot fetch the video from YouTube"}]}
    with pytest.raises(GeminiError) as e:
        _client(lambda r: httpx.Response(200, json=failed)).analyze_youtube("u", "p", SCHEMA, start_s=0, end_s=5)
    assert e.value.code == "video_inaccessible" and e.value.request_id == "int_9"


def test_client_timeout():
    def boom(req):
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(GeminiError) as e:
        _client(boom).analyze_youtube("u", "p", SCHEMA, start_s=0, end_s=5)
    assert e.value.code == "timeout" and e.value.retryable
