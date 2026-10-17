"""Runtime configuration from environment variables. Secrets never leave the server."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]  # services/api
REPO_ROOT = API_ROOT.parents[1]


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _ensure_ca_bundle() -> None:
    """python.org macOS builds ship without a CA store; use certifi's bundle."""
    if os.getenv("SSL_CERT_FILE"):
        return
    try:
        import certifi

        os.environ["SSL_CERT_FILE"] = certifi.where()
    except ImportError:  # pragma: no cover
        pass


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str | None
    mongodb_db: str
    media_root: Path
    catalog_provider: str
    perception_provider: str  # perceptron | fixture | none
    perceptron_key_present: bool
    perceptron_model: str
    perception_max_frames: int
    perception_max_attribute_calls: int
    perceptron_max_tokens: int
    xai_key_present: bool
    xai_model: str
    xai_base_url: str
    feature_photon: bool
    feature_voice: bool
    feature_solana: bool
    cookie_secure: bool
    search_deadline_s: float
    analysis_deadline_s: float
    max_tool_calls: int
    max_detail_calls: int
    web_dist: Path
    extra: dict = field(default_factory=dict)

    @property
    def db_mode(self) -> str:
        if not self.mongodb_uri:
            return "local_memory"
        return "atlas" if "mongodb.net" in self.mongodb_uri else "mongodb"


def _load_dotenv(path: Path) -> list[str]:
    """Load KEY=VALUE lines from the repo .env without overriding the real environment.
    Returns the names loaded (never values)."""
    loaded: list[str] = []
    if not path.is_file():
        return loaded
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.split(" #", 1)[0].strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v
            loaded.append(k)
    return loaded


def load_settings() -> Settings:
    if not _flag("CLIPCART_SKIP_DOTENV"):
        _load_dotenv(REPO_ROOT / ".env")
    _ensure_ca_bundle()
    perceptron_key = bool(os.getenv("PERCEPTRON_API_KEY"))
    perception = (os.getenv("PERCEPTION_PROVIDER") or ("perceptron" if perceptron_key else "none")).lower()
    return Settings(
        mongodb_uri=os.getenv("MONGODB_URI") or None,
        mongodb_db=os.getenv("MONGODB_DB", "clipcart"),
        media_root=Path(os.getenv("CLIPCART_MEDIA_ROOT") or (API_ROOT / ".data" / "media")),
        catalog_provider=(os.getenv("CATALOG_PROVIDER") or "solescout").lower(),
        perception_provider=perception,
        perceptron_key_present=perceptron_key,
        perceptron_model=os.getenv("PERCEPTRON_MODEL", "perceptron-mk1"),
        perception_max_frames=int(os.getenv("PERCEPTION_MAX_FRAMES", "6")),
        perception_max_attribute_calls=int(os.getenv("PERCEPTION_MAX_ATTRIBUTE_CALLS", "3")),
        perceptron_max_tokens=int(os.getenv("PERCEPTRON_MAX_TOKENS", "1200")),
        xai_key_present=bool(os.getenv("XAI_API_KEY")),
        xai_model=os.getenv("XAI_MODEL", "grok-4.3"),
        xai_base_url=os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").rstrip("/"),
        feature_photon=_flag("FEATURE_PHOTON"),
        feature_voice=_flag("FEATURE_VOICE"),
        feature_solana=_flag("FEATURE_SOLANA"),
        cookie_secure=_flag("COOKIE_SECURE"),
        search_deadline_s=float(os.getenv("SEARCH_DEADLINE_S", "60")),
        analysis_deadline_s=float(os.getenv("ANALYSIS_DEADLINE_S", "60")),
        max_tool_calls=int(os.getenv("SEARCH_MAX_TOOL_CALLS", "12")),
        max_detail_calls=int(os.getenv("SEARCH_MAX_DETAIL_CALLS", "6")),
        web_dist=Path(os.getenv("CLIPCART_WEB_DIST") or (REPO_ROOT / "apps" / "web" / "dist")),
    )
