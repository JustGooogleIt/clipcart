"""Secrets in Settings never show up in its repr (logs, tracebacks)."""

from app.config import load_settings


def test_settings_repr_hides_secrets(monkeypatch):
    monkeypatch.setenv("CLIPCART_SKIP_DOTENV", "1")
    monkeypatch.setenv("MONGODB_URI", "mongodb+srv://clipcart:s3cret-pw@cluster0.example.mongodb.net/?retryWrites=true")
    monkeypatch.setenv("STYLE_REMOTE_API_KEY", "sk-test-hidden")
    s = load_settings()
    assert s.mongodb_uri and s.style_remote_api_key  # still available to the app
    text = repr(s)
    assert "s3cret-pw" not in text and "sk-test-hidden" not in text and "mongodb+srv" not in text
    assert s.db_mode == "atlas"
