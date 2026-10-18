"""Perceptron perception adapter (SRS FR04, T02).

    PerceptionProvider.analyze(frame_refs, categories, request_context)
        -> AnalysisResult (GarmentObservation[] + provider request metadata)

Policy:
* One detect call per frame, at most ``max_frames`` frames, bounded
  concurrency, every call inside the request deadline.
* Boxes are converted from the provider's 0..1000 grid to box01 exactly once
  (``geometry.perceptron_box_to_box01``) and validated; bad boxes are dropped
  and counted, never clamped into a plausible-looking crop.
* Optional attribute calls on the largest crops, capped by
  ``max_attribute_calls``. Only visible attributes are kept: brand,
  fiber composition, size and identity fields are never requested or
  stored. Fabric *appearance* words (denim weave, leather sheen) may
  appear in details for shopping search.
* Transient failures retry once with jitter if the deadline allows.
  Authentication failures stop the whole analysis and are not retried.
* An empty detection list is a valid ``ok`` result, distinct from failure.
"""

from __future__ import annotations

import hashlib
import random
import time
from collections.abc import Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event

from app.media.context import RequestContext
from app.media.errors import InvalidBoxError
from app.media.geometry import iou, perceptron_box_to_box01
from app.media.service import MediaService
from app.media.types import (
    AnalysisResult,
    Category,
    FrameRef,
    GarmentObservation,
    ProviderIssue,
    ProviderRequestMeta,
)

from .errors import NormalizedError, normalize_exception
from .sdk import AttributeResponse, DetectResponse, PerceptronBackend

PROVIDER = "perceptron"

# What we ask the model to find, per SRS category.
CATEGORY_PROMPTS: dict[str, str] = {
    "jacket": "jacket or coat",
    "top": "top or shirt or sweater",
    "pants": "pants or jeans or trousers",
    "bag": "bag or handbag or backpack",
}

_LABEL_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("jacket", ("jacket", "coat", "blazer", "parka", "windbreaker", "bomber", "puffer", "vest", "gilet")),
    ("bag", ("bag", "handbag", "backpack", "purse", "tote", "clutch", "satchel", "crossbody")),
    ("pants", ("pants", "jeans", "trousers", "chinos", "shorts", "leggings", "skirt")),
    (
        "top",
        ("top", "shirt", "t-shirt", "tee", "blouse", "sweater", "hoodie", "sweatshirt", "cardigan", "polo", "tank"),
    ),
]
_ALLOWED_ATTRIBUTE_KEYS = ("color", "pattern", "cut", "details")
_MAX_ATTR_LEN = 60


def category_from_label(label: str | None) -> Category:
    text = (label or "").lower()
    for category, words in _LABEL_KEYWORDS:
        if any(w in text for w in words):
            return category  # type: ignore[return-value]
    return "other"


def _clean_list(values: object, limit: int) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for v in values:
        if isinstance(v, str):
            s = " ".join(v.split())[:_MAX_ATTR_LEN]
            if s and s.lower() not in {x.lower() for x in out}:
                out.append(s)
    return out[:limit]


def _obs_id(frame_asset_id: str, box01: Sequence[float], label: str | None, salt: str | None) -> str:
    key = f"{frame_asset_id}|{','.join(f'{v:.4f}' for v in box01)}|{label}|{salt}"
    return "obs_" + hashlib.sha256(key.encode()).hexdigest()[:24]


@dataclass
class _FrameOutcome:
    frame: FrameRef
    response: DetectResponse | None
    error: NormalizedError | None
    metas: list[ProviderRequestMeta]


class PerceptronPerceptionProvider:
    def __init__(
        self,
        media: MediaService,
        backend: PerceptronBackend,
        *,
        mode: str = "live",
        model_id: str = "perceptron-mk1.5",
        max_frames: int = 24,
        max_outputs_per_frame: int = 8,
        max_attribute_calls: int = 6,
        max_concurrency: int = 3,
        retry_base_delay_s: float = 0.4,
        min_call_budget_s: float = 2.0,
    ):
        if mode not in ("live", "fixture"):
            raise ValueError("mode must be 'live' or 'fixture'")
        self.media = media
        self.backend = backend
        self.mode = mode
        self.model_id = model_id
        self.max_frames = max_frames
        self.max_outputs_per_frame = max_outputs_per_frame
        self.max_attribute_calls = max_attribute_calls
        # Fixture replay is order-based, so keep it deterministic.
        self.max_concurrency = 1 if mode == "fixture" else max_concurrency
        self.retry_base_delay_s = retry_base_delay_s
        self.min_call_budget_s = min_call_budget_s

    # ---------------------------------------------------------------- calls
    def _call_with_policy(self, fn, ctx: RequestContext, abort: Event, meta_base: dict):
        """Run ``fn`` with one jittered retry for transient errors.

        Returns (result | None, NormalizedError | None, [ProviderRequestMeta]).
        """
        metas: list[ProviderRequestMeta] = []
        last_err: NormalizedError | None = None
        for attempt in (1, 2):
            if abort.is_set() or ctx.cancelled:
                return None, NormalizedError("cancelled", "analysis cancelled", False, None), metas
            if ctx.remaining() < self.min_call_budget_s:
                return None, NormalizedError("timeout", "request deadline reached", True, None), metas
            started = datetime.now(timezone.utc)
            t0 = time.monotonic()
            try:
                result = fn()
            except Exception as exc:  # noqa: BLE001 - normalized below
                err = normalize_exception(exc)
                metas.append(
                    ProviderRequestMeta(
                        **meta_base,
                        provider=PROVIDER,
                        model_id=self.model_id,
                        provider_request_id=err.request_id,
                        started_at=started,
                        elapsed_ms=int((time.monotonic() - t0) * 1000),
                        outcome="error",
                        error_code=err.code,
                        attempt=attempt,
                    )
                )
                last_err = err
                if err.code == "auth_error" or (err.code == "rate_limited" and not err.retryable):
                    abort.set()
                    return None, err, metas
                if not err.retryable or attempt == 2:
                    return None, err, metas
                delay = (err.retry_after or self.retry_base_delay_s) * (1 + random.random() * 0.5)
                if ctx.remaining() - delay < self.min_call_budget_s:
                    return None, err, metas
                time.sleep(delay)
                continue
            empty = isinstance(result, DetectResponse) and not result.detections
            metas.append(
                ProviderRequestMeta(
                    **meta_base,
                    provider=PROVIDER,
                    model_id=getattr(result, "model", None) or self.model_id,
                    provider_request_id=getattr(result, "request_id", None),
                    started_at=started,
                    elapsed_ms=int((time.monotonic() - t0) * 1000),
                    outcome="empty" if empty else "ok",
                    usage=getattr(result, "usage", None),
                    attempt=attempt,
                )
            )
            return result, None, metas
        return None, last_err, metas

    def _run_bounded(self, jobs: list[tuple[object, callable]], ctx: RequestContext) -> dict[object, object]:
        """Run callables concurrently; return finished results keyed by job key.

        Jobs still running at the deadline are abandoned (their results are
        discarded) so the caller always returns within the deadline.
        """
        results: dict[object, object] = {}
        if not jobs:
            return results
        pool = ThreadPoolExecutor(max_workers=self.max_concurrency, thread_name_prefix="perceptron")
        try:
            futures: dict[Future, object] = {pool.submit(fn): key for key, fn in jobs}
            pending = set(futures)
            while pending:
                remaining = ctx.remaining()
                if remaining <= 0 or ctx.cancelled:
                    break
                done, pending = wait(pending, timeout=min(remaining, 0.5), return_when=FIRST_COMPLETED)
                for f in done:
                    results[futures[f]] = f.result()
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        return results

    # -------------------------------------------------------------- analyze
    def analyze(
        self,
        frame_refs: Sequence[FrameRef],
        categories: Sequence[str],
        request_context: RequestContext,
    ) -> AnalysisResult:
        ctx = request_context
        cats = [c for c in categories if c in CATEGORY_PROMPTS or c == "other"]
        if not cats:
            raise ValueError("at least one of jacket/top/pants/bag must be requested")
        classes = [CATEGORY_PROMPTS[c] for c in cats if c in CATEGORY_PROMPTS]
        # Drop repeated frame IDs so a frame is never paid for twice.
        frames = list({f.asset_id: f for f in frame_refs}.values())[: self.max_frames]
        issues: list[ProviderIssue] = []
        metas: list[ProviderRequestMeta] = []
        abort = Event()

        # Ownership check and byte load happen before any paid call.
        frame_bytes = {f.asset_id: self.media.store.read_bytes(f.asset_id, ctx.owner_id) for f in frames}

        def detect_job(frame: FrameRef):
            def call():
                return self.backend.detect(
                    frame_bytes[frame.asset_id], classes, max_outputs=self.max_outputs_per_frame
                )

            res, err, m = self._call_with_policy(
                call, ctx, abort, {"frame_asset_id": frame.asset_id, "crop_asset_id": None, "purpose": "detect"}
            )
            return _FrameOutcome(frame, res, err, m)

        outcomes = self._run_bounded([(f.asset_id, (lambda f=f: detect_job(f))) for f in frames], ctx)

        observations: list[GarmentObservation] = []
        dropped = 0
        ok_frames = 0
        for frame in frames:
            out = outcomes.get(frame.asset_id)
            if out is None:
                code = "cancelled" if ctx.cancelled else "timeout"
                issues.append(
                    ProviderIssue(
                        code=code,
                        message="frame not analyzed before the deadline" if code == "timeout" else "analysis cancelled",
                        retryable=code == "timeout",
                        frame_asset_id=frame.asset_id,
                    )
                )
                continue
            metas.extend(out.metas)
            if out.error is not None:
                issues.append(
                    ProviderIssue(
                        code=out.error.code,
                        message=out.error.message,
                        retryable=out.error.retryable,
                        frame_asset_id=frame.asset_id,
                        provider_request_id=out.error.request_id,
                    )
                )
                continue
            resp = out.response
            ok_frames += 1
            if resp.parse_errors or not resp.complete:
                issues.append(
                    ProviderIssue(
                        code="invalid_response",
                        message=f"provider markup incomplete or malformed ({resp.parse_errors} parse errors)",
                        retryable=False,
                        frame_asset_id=frame.asset_id,
                        provider_request_id=resp.request_id,
                    )
                )
            kept: list[GarmentObservation] = []
            for det in resp.detections:
                category = category_from_label(det.label)
                if category not in cats:
                    continue
                try:
                    box = perceptron_box_to_box01(det.x1, det.y1, det.x2, det.y2)
                    crop = self.media.crop(frame.asset_id, box, ctx.owner_id)
                except InvalidBoxError:
                    dropped += 1
                    continue
                if any(k.category == category and iou(k.box01, box) > 0.9 for k in kept):
                    dropped += 1  # provider repeated the same box
                    continue
                kept.append(
                    GarmentObservation(
                        id=_obs_id(frame.asset_id, box, det.label, resp.request_id),
                        media_id=frame.media_id,
                        frame_asset_id=frame.asset_id,
                        timestamp_ms=frame.timestamp_ms,
                        box01=box,
                        crop_asset_id=crop.crop_asset_id,
                        category=category,
                        person_track_id=None,
                        observed_attributes={},
                        visible_text=[],
                        provider_request_id=resp.request_id,
                        model_id=resp.model or self.model_id,
                        edited_by_user=False,
                        raw_label=det.label,
                        model_generated_fields=["box01", "category"],
                    )
                )
            observations.extend(kept)

        observations = self._attach_attributes(observations, ctx, abort, metas, issues)

        if frames and ok_frames == 0:
            status = "failed"
        elif ok_frames < len(frames) or any(i.code != "invalid_response" for i in issues):
            status = "partial"
        else:
            status = "ok"
        if not frames:
            status = "failed"
            issues.append(ProviderIssue(code="invalid_response", message="no frames supplied", retryable=False))
        return AnalysisResult(
            status=status,
            mode=self.mode,
            observations=observations,
            requests=metas,
            issues=issues,
            dropped_detections=dropped,
        )

    def _attach_attributes(
        self,
        observations: list[GarmentObservation],
        ctx: RequestContext,
        abort: Event,
        metas: list[ProviderRequestMeta],
        issues: list[ProviderIssue],
    ) -> list[GarmentObservation]:
        if self.max_attribute_calls <= 0 or not observations or abort.is_set():
            return observations

        def size(o: GarmentObservation) -> float:
            return (o.box01[2] - o.box01[0]) * (o.box01[3] - o.box01[1])

        chosen = sorted(observations, key=size, reverse=True)[: self.max_attribute_calls]

        def attr_job(o: GarmentObservation):
            crop_bytes = self.media.store.read_bytes(o.crop_asset_id, ctx.owner_id)
            return self._call_with_policy(
                lambda: self.backend.describe(crop_bytes, o.category),
                ctx,
                abort,
                {"frame_asset_id": o.frame_asset_id, "crop_asset_id": o.crop_asset_id, "purpose": "attributes"},
            )

        results = self._run_bounded([(o.id, (lambda o=o: attr_job(o))) for o in chosen], ctx)
        updated = {}
        for o in chosen:
            if o.id not in results:
                continue
            res, err, m = results[o.id]
            metas.extend(m)
            if err is not None:
                issues.append(
                    ProviderIssue(
                        code=err.code,
                        message=f"attributes unavailable: {err.message}",
                        retryable=err.retryable,
                        frame_asset_id=o.frame_asset_id,
                        provider_request_id=err.request_id,
                    )
                )
                continue
            assert isinstance(res, AttributeResponse)
            limits = {"color": 5, "pattern": 4, "cut": 6, "details": 10}
            attrs = {k: _clean_list(res.attributes.get(k), limits.get(k, 6)) for k in _ALLOWED_ATTRIBUTE_KEYS}
            attrs = {k: v for k, v in attrs.items() if v}
            text = _clean_list(res.attributes.get("visible_text"), 6)
            updated[o.id] = o.model_copy(
                update={
                    "observed_attributes": attrs,
                    "visible_text": text,
                    "model_generated_fields": o.model_generated_fields
                    + list(attrs)
                    + (["visible_text"] if text else []),
                }
            )
        return [updated.get(o.id, o) for o in observations]

    def find_open_vocab(
        self,
        frame_refs: Sequence[FrameRef],
        query: str,
        request_context: RequestContext,
    ) -> AnalysisResult:
        """Open-vocabulary find: detect ``query`` on frames, describe the best crop richly."""
        from app.jobs.find_query import detect_classes_for_query

        ctx = request_context
        q = " ".join((query or "").split())
        if len(q) < 2:
            raise ValueError("query must be non-empty")
        classes = detect_classes_for_query(q) or [q]
        frames = list({f.asset_id: f for f in frame_refs}.values())[: self.max_frames]
        issues: list[ProviderIssue] = []
        metas: list[ProviderRequestMeta] = []
        abort = Event()
        frame_bytes = {f.asset_id: self.media.store.read_bytes(f.asset_id, ctx.owner_id) for f in frames}

        def detect_job(frame: FrameRef, class_list: list[str]):
            def call():
                return self.backend.detect(
                    frame_bytes[frame.asset_id], class_list, max_outputs=self.max_outputs_per_frame
                )

            res, err, m = self._call_with_policy(
                call, ctx, abort, {"frame_asset_id": frame.asset_id, "crop_asset_id": None, "purpose": "detect"}
            )
            return _FrameOutcome(frame, res, err, m)

        def collect(class_list: list[str]) -> tuple[list[GarmentObservation], int, int]:
            outcomes = self._run_bounded(
                [(f.asset_id, (lambda f=f: detect_job(f, class_list))) for f in frames], ctx
            )
            cands: list[GarmentObservation] = []
            dropped_n = 0
            ok_n = 0
            for frame in frames:
                out = outcomes.get(frame.asset_id)
                if out is None:
                    code = "cancelled" if ctx.cancelled else "timeout"
                    issues.append(
                        ProviderIssue(
                            code=code,
                            message="frame not analyzed before the deadline" if code == "timeout" else "analysis cancelled",
                            retryable=code == "timeout",
                            frame_asset_id=frame.asset_id,
                        )
                    )
                    continue
                metas.extend(out.metas)
                if out.error is not None:
                    issues.append(
                        ProviderIssue(
                            code=out.error.code,
                            message=out.error.message,
                            retryable=out.error.retryable,
                            frame_asset_id=frame.asset_id,
                            provider_request_id=out.error.request_id,
                        )
                    )
                    continue
                resp = out.response
                ok_n += 1
                for det in resp.detections or []:
                    try:
                        box = perceptron_box_to_box01(det.x1, det.y1, det.x2, det.y2)
                    except InvalidBoxError:
                        dropped_n += 1
                        continue
                    x0, y0, x1, y1 = box
                    area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
                    # Reject dust specs and near-full-frame "detections" (usually wrong).
                    if area < 0.004 or area > 0.88:
                        dropped_n += 1
                        continue
                    try:
                        crop = self.media.crop(frame.asset_id, box, ctx.owner_id)
                    except InvalidBoxError:
                        dropped_n += 1
                        continue
                    # Dedup near-identical boxes within this pass.
                    if any(iou(k.box01, box) > 0.85 and k.frame_asset_id == frame.asset_id for k in cands):
                        dropped_n += 1
                        continue
                    cands.append(
                        GarmentObservation(
                            id=_obs_id(frame.asset_id, box, det.label or q, resp.request_id),
                            media_id=frame.media_id,
                            frame_asset_id=frame.asset_id,
                            timestamp_ms=frame.timestamp_ms,
                            box01=box,
                            crop_asset_id=crop.crop_asset_id,
                            category="other",
                            person_track_id=None,
                            observed_attributes={},
                            visible_text=[],
                            provider_request_id=resp.request_id,
                            model_id=resp.model or self.model_id,
                            edited_by_user=False,
                            raw_label=det.label or q,
                            model_generated_fields=["box01", "category"],
                        )
                    )
            return cands, dropped_n, ok_n

        candidates, dropped, ok_frames = collect(classes)
        # Recall pass only when the shortest class wasn't already tried (avoids a 2× bill).
        shortest = classes[-1]
        if not candidates and len(classes) > 1 and shortest != classes[0] and ctx.remaining() > 12:
            # Only re-hit frames if the first pass used a long multi-class list that may have
            # diluted open-vocab attention — try the shortest class alone once.
            more, d2, ok2 = collect([shortest])
            candidates, dropped, ok_frames = more, dropped + d2, max(ok_frames, ok2)

        if not candidates:
            return AnalysisResult(
                status="failed" if frames and ok_frames == 0 else "ok",
                mode=self.mode,
                observations=[],
                requests=metas,
                issues=issues,
                dropped_detections=dropped,
            )

        # Prefer mid-size sharp crops (full-frame and tiny boxes already filtered).
        def score(o: GarmentObservation) -> float:
            x0, y0, x1, y1 = o.box01
            area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
            # Sweet spot ~4–45% of the frame for product-like objects.
            size_score = 1.0 - abs(area - 0.18) / 0.18
            try:
                c = self.media.get_crop(o.crop_asset_id, ctx.owner_id)
                sharp = c.sharpness
            except Exception:  # noqa: BLE001
                sharp = 0.0
            return size_score * 5 + min(sharp / 200.0, 3.0) + area

        best = max(candidates, key=score)
        crop_bytes = self.media.store.read_bytes(best.crop_asset_id, ctx.owner_id)

        def attr_call():
            return self.backend.describe_object(crop_bytes, q)

        res, err, attr_metas = self._call_with_policy(
            attr_call,
            ctx,
            abort,
            {"frame_asset_id": best.frame_asset_id, "crop_asset_id": best.crop_asset_id, "purpose": "attributes"},
        )
        metas.extend(attr_metas)
        attrs: dict[str, list[str]] = {}
        visible: list[str] = []
        what = q
        search_desc = q
        if err is None and isinstance(res, AttributeResponse):
            raw = res.attributes if isinstance(res.attributes, dict) else {}
            what = str(raw.get("what") or q).strip()[:120] or q
            search_desc = str(raw.get("search_description") or what).strip()[:400] or what
            color = _clean_list(raw.get("color"), 6)
            pattern = _clean_list(raw.get("pattern"), 4)
            # Map form → cut so existing shopping profile aggregation picks it up.
            form = _clean_list(raw.get("form"), 8)
            details = _clean_list(raw.get("details"), 12)
            if color:
                attrs["color"] = color
            if pattern:
                attrs["pattern"] = pattern
            if form:
                attrs["cut"] = form
            # Put the dense catalog line first in details — never discard it.
            detail_list = [search_desc] if search_desc else []
            detail_list.extend(d for d in details if d != search_desc)
            if detail_list:
                attrs["details"] = detail_list[:12]
            visible = _clean_list(raw.get("visible_text"), 6)
            best = best.model_copy(
                update={
                    "observed_attributes": attrs,
                    "visible_text": visible,
                    "raw_label": what,
                    "model_generated_fields": list(
                        dict.fromkeys(
                            best.model_generated_fields
                            + list(attrs)
                            + (["visible_text"] if visible else [])
                            + ["search_description"]
                        )
                    ),
                    "provider_request_id": res.request_id or best.provider_request_id,
                }
            )
        elif err is not None:
            issues.append(
                ProviderIssue(
                    code=err.code,
                    message=f"object describe unavailable: {err.message}",
                    retryable=err.retryable,
                    frame_asset_id=best.frame_asset_id,
                    provider_request_id=err.request_id,
                )
            )
            best = best.model_copy(
                update={"raw_label": what, "observed_attributes": {"details": [search_desc]}}
            )

        return AnalysisResult(
            status="ok" if ok_frames == len(frames) else "partial",
            mode=self.mode,
            observations=[best],
            requests=metas,
            issues=issues,
            dropped_detections=dropped,
        )


# --------------------------------------------------------------- user edits
def manual_observation(
    media: MediaService,
    frame: FrameRef,
    box01: Sequence[float],
    category: Category,
    owner_id: str,
) -> GarmentObservation:
    """Manual crop fallback: a user-drawn box with no provider involvement."""
    crop = media.crop(frame.asset_id, box01, owner_id)
    return GarmentObservation(
        id=_obs_id(frame.asset_id, crop.box01, category, "manual"),
        media_id=frame.media_id,
        frame_asset_id=frame.asset_id,
        timestamp_ms=frame.timestamp_ms,
        box01=crop.box01,
        crop_asset_id=crop.crop_asset_id,
        category=category,
        person_track_id=None,
        observed_attributes={},
        visible_text=[],
        provider_request_id=None,
        model_id="manual",
        edited_by_user=True,
        raw_label=None,
        model_generated_fields=[],
        user_corrected_fields=["box01", "category"],
    )


def correct_observation(
    media: MediaService,
    obs: GarmentObservation,
    owner_id: str,
    *,
    box01: Sequence[float] | None = None,
    category: Category | None = None,
) -> GarmentObservation:
    """Apply a user crop/category correction while keeping provenance (FR05)."""
    update: dict = {"edited_by_user": True}
    corrected = list(obs.user_corrected_fields)
    generated = list(obs.model_generated_fields)
    if box01 is not None:
        crop = media.crop(obs.frame_asset_id, box01, owner_id)
        update["box01"] = crop.box01
        update["crop_asset_id"] = crop.crop_asset_id
        corrected.append("box01")
        generated = [f for f in generated if f != "box01"]
    if category is not None and category != obs.category:
        update["category"] = category
        corrected.append("category")
        generated = [f for f in generated if f != "category"]
    update["user_corrected_fields"] = sorted(set(corrected))
    update["model_generated_fields"] = generated
    return obs.model_copy(update=update)
