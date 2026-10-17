"""Bounded live Gemini check: one public garment video and one no-garment case.

    CLIPCART_LIVE_GEMINI=1 services/api/.venv/bin/python -m pytest services/api/tests/youtube/test_youtube_live.py -s

Reads GEMINI_API_KEY from the environment or the root .env. Two Gemini calls in
total, each on a short clipped window at low resolution and 0.5 fps.
"""

import os

import pytest

from app.config import load_settings

S = load_settings()  # loads the root .env (names only, values never printed)
pytestmark = pytest.mark.skipif(
    not (os.getenv("CLIPCART_LIVE_GEMINI") == "1" and os.getenv("GEMINI_API_KEY")),
    reason="live Gemini check disabled (set CLIPCART_LIVE_GEMINI=1 and GEMINI_API_KEY)",
)


def analyze(url, start, end):
    from app.providers.gemini.client import GeminiClient, parse_json_text
    from app.providers.gemini.garments import SCHEMA, build_prompt, validate_garments
    from app.youtube.oembed import probe
    from app.youtube.url import parse_youtube_url

    ref = parse_youtube_url(url)
    meta = probe(ref.canonical_url)
    assert meta.state == "ok", meta
    reply = GeminiClient(model=S.gemini_model, base_url=S.gemini_base_url).analyze_youtube(
        ref.canonical_url, build_prompt(start, end), SCHEMA, start_s=start, end_s=end, fps=S.gemini_fps,
        max_output_tokens=S.gemini_max_output_tokens, timeout_s=S.gemini_timeout_s,
    )
    garments, dropped = validate_garments(parse_json_text(reply.text), start_s=start, end_s=end, video_id=ref.video_id)
    print(f"\n{meta.title!r} [{start}-{end}s] interaction={reply.interaction_id} usage={reply.usage} dropped={dropped}")
    for g in garments:
        print("  ", g.category, "|", g.description, "|", [t.label for t in g.timestamps], g.person_label)
    return garments


def test_public_video_with_a_visible_garment():
    garments = analyze("https://www.youtube.com/watch?v=jNQXAC9IVRw", 0, 19)  # "Me at the zoo", man on camera
    assert garments and all(g.source == "gemini_youtube" for g in garments)
    assert any(g.category in ("jacket", "top") for g in garments)
    assert all(0 <= t.seconds <= 21 for g in garments for t in g.timestamps)


def test_no_garment_case():
    garments = analyze("https://www.youtube.com/watch?v=aqz-KE-bpKQ", 0, 30)  # Big Buck Bunny opening: landscape, no clothing
    assert garments == []
