"""Process-wide application state: settings, database, media, providers, jobs."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.config import Settings
from app.media.service import MediaService
from app.media.storage import LocalAssetStore
from app.providers.catalog import get_catalog_provider
from app.providers.status import ProviderStatus
from app.storage.db import connect


@dataclass
class AppState:
    settings: Settings
    db: Any
    media: MediaService
    catalog: Any
    catalog_error: str | None
    status: dict[str, ProviderStatus]
    executor: ThreadPoolExecutor
    counters: dict[str, int] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    _perception: Any = None
    research_url_checker: Any = None

    def bump(self, key: str) -> None:
        with self.lock:
            self.counters[key] = self.counters.get(key, 0) + 1

    def style_model(self):
        """Ollama-backed Gemma client, or None when style memory or the model provider is off."""
        s = self.settings
        if not s.feature_style_memory:
            return None
        if s.style_model_provider == "openai_compatible":
            if not (s.style_remote_base_url and s.style_remote_api_key and s.style_remote_model):
                return None
            from app.style.model import OpenAICompatibleStyleModel

            return OpenAICompatibleStyleModel(
                base_url=s.style_remote_base_url, api_key=s.style_remote_api_key, model=s.style_remote_model,
                label=s.style_remote_label, timeout_s=max(s.style_model_timeout_s, 20.0),
                json_mode=s.style_remote_json_mode, max_tokens=s.style_remote_max_tokens,
            )
        if s.style_model_provider == "ollama":
            from app.style.model import OllamaStyleModel

            return OllamaStyleModel(base_url=s.ollama_base_url, model=s.style_model, timeout_s=s.style_model_timeout_s)
        return None

    def perception_provider(self):
        """Return (provider | None, detection_mode)."""
        mode = self.settings.perception_provider
        if mode == "perceptron" and self.settings.perceptron_key_present:
            with self.lock:
                if self._perception is None:
                    import perceptron

                    from app.providers.perceptron.adapter import PerceptronPerceptionProvider
                    from app.providers.perceptron.sdk import SdkBackend

                    s = self.settings
                    backend = SdkBackend(model=s.perceptron_model, request_timeout_s=30.0)
                    # Bound paid output per call; the SDK only exposes this as a global setting.
                    perceptron.configure(max_tokens=s.perceptron_max_tokens)
                    self._perception = PerceptronPerceptionProvider(
                        self.media,
                        backend,
                        mode="live",
                        model_id=s.perceptron_model,
                        max_frames=s.perception_max_frames,
                        max_attribute_calls=s.perception_max_attribute_calls,
                    )
            return self._perception, self.status["perceptron"].mode  # unverified until a call succeeds
        if mode == "fixture":
            from app.config import API_ROOT
            from app.providers.perceptron.adapter import PerceptronPerceptionProvider
            from app.providers.perceptron.fixture import FixtureBackend

            fx = API_ROOT / "tests" / "perception" / "fixtures" / "perceptron_dev_fixture.json"
            return PerceptronPerceptionProvider(self.media, FixtureBackend(fx), mode="fixture", model_id="fixture"), "fixture"
        return None, "unavailable"


def build_state(settings: Settings) -> AppState:
    db = connect(settings)
    media = MediaService(LocalAssetStore(settings.media_root))
    catalog, err = None, None
    try:
        catalog = get_catalog_provider(settings.catalog_provider)
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
    status = {
        "perceptron": ProviderStatus("perceptron", settings.perception_provider == "perceptron" and settings.perceptron_key_present),
        "grok": ProviderStatus("grok", settings.xai_key_present),
        "style_model": ProviderStatus("style_model", settings.feature_style_memory and (
            settings.style_model_provider == "ollama"
            or (settings.style_model_provider == "openai_compatible" and bool(settings.style_remote_base_url
                and settings.style_remote_api_key and settings.style_remote_model)))),
        "catalog": ProviderStatus(
            settings.catalog_provider,
            catalog is not None,
            mode_when_unconfigured="unavailable",
        ),
    }
    if settings.perception_provider == "fixture":
        status["perceptron"] = ProviderStatus("perceptron", False, mode_when_unconfigured="fixture")
    if settings.catalog_provider in ("fixture", "catalog", "demo") and catalog is not None:
        status["catalog"] = ProviderStatus("fixture", False, mode_when_unconfigured="fixture")
    from functools import partial

    from app.research.urlsafety import check_url

    url_checker = partial(check_url, resolve=settings.research_resolve_dns)
    return AppState(
        settings=settings,
        db=db,
        media=media,
        catalog=catalog,
        catalog_error=err,
        status=status,
        executor=ThreadPoolExecutor(max_workers=3, thread_name_prefix="job"),
        research_url_checker=url_checker,
    )
