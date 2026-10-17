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

    def bump(self, key: str) -> None:
        with self.lock:
            self.counters[key] = self.counters.get(key, 0) + 1

    def perception_provider(self):
        """Return (provider | None, detection_mode)."""
        mode = self.settings.perception_provider
        if mode == "perceptron" and self.settings.perceptron_key_present:
            from app.providers.perceptron.adapter import PerceptronPerceptionProvider
            from app.providers.perceptron.sdk import SdkBackend

            backend = SdkBackend(model=self.settings.perceptron_model, request_timeout_s=30.0)
            prov = PerceptronPerceptionProvider(
                self.media,
                backend,
                mode="live",
                model_id=self.settings.perceptron_model,
                max_frames=12,
                max_attribute_calls=4,
            )
            return prov, self.status["perceptron"].mode  # unverified until a call succeeds
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
    return AppState(
        settings=settings,
        db=db,
        media=media,
        catalog=catalog,
        catalog_error=err,
        status=status,
        executor=ThreadPoolExecutor(max_workers=3, thread_name_prefix="job"),
    )
