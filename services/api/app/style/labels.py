"""How the style-note reader is described: from configuration and the latest real call, never assumed."""

from __future__ import annotations


def remote_style_label(s) -> str:
    """Display label for a hosted style model, from configuration. Never names a model or host that isn't configured."""
    return s.style_remote_label or f"{s.style_remote_model or 'Style model'} · hosted endpoint (not local)"


def style_model_mode(status) -> str:
    """live only while the most recent call succeeded; a model that has since failed reads as unverified."""
    mode = status.mode
    if mode == "live" and status.recent and not status.recent[0].get("ok"):
        return "unverified"
    return mode
