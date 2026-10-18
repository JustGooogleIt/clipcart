"""Conservative grouping of repeated garment observations (SRS FR06, AT04).

Two observations merge only when every one of these holds:

* same media, same category, both timed (still images never merge);
* same shot (no detected cut between them) and the time gap is at most
  ``max_gap_ms``;
* different sampled frames (two boxes in one frame are two garments);
* no conflicting ``person_track_id``;
* no disjoint colour or pattern attributes when both sides report them;
* spatial continuity: IoU >= ``min_iou``, or a small centre shift with a
  similar box area;
* the match is unambiguous: the observation is compatible with exactly one
  open group and that group with exactly one observation in the frame.

Anything else stays a separate candidate. Similar jackets on two people or
across a cut are therefore never merged automatically.
"""

from __future__ import annotations

import bisect
import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from app.categories import is_accessory

from .geometry import area, center_distance, iou
from .types import Garment, GarmentObservation

_CONFLICT_KEYS = ("color", "pattern")


@dataclass
class _Track:
    obs: list[GarmentObservation] = field(default_factory=list)
    shot: int = 0

    @property
    def last(self) -> GarmentObservation:
        return self.obs[-1]


class GarmentGrouper:
    def __init__(
        self,
        *,
        max_gap_ms: int = 4000,
        min_iou: float = 0.3,
        max_center_shift: float = 0.12,
        max_area_ratio: float = 2.0,
    ):
        self.max_gap_ms = max_gap_ms
        self.min_iou = min_iou
        self.max_center_shift = max_center_shift
        self.max_area_ratio = max_area_ratio

    # ----------------------------------------------------------------- rules
    @staticmethod
    def _attr_conflict(a: GarmentObservation, b: GarmentObservation) -> bool:
        for key in _CONFLICT_KEYS:
            va = {s.strip().lower() for s in a.observed_attributes.get(key, []) if s.strip()}
            vb = {s.strip().lower() for s in b.observed_attributes.get(key, []) if s.strip()}
            if va and vb and va.isdisjoint(vb):
                return True
        return False

    def _spatially_continuous(self, a: GarmentObservation, b: GarmentObservation) -> bool:
        if iou(a.box01, b.box01) >= self.min_iou:
            return True
        aa, ab = area(a.box01), area(b.box01)
        ratio = max(aa, ab) / min(aa, ab)
        shift = self.max_center_shift
        if is_accessory(a.category):
            # Small objects: the allowed shift scales with the object, so two earrings ~10% apart never merge.
            side = max(a.box01[2] - a.box01[0], a.box01[3] - a.box01[1], b.box01[2] - b.box01[0], b.box01[3] - b.box01[1])
            shift = min(self.max_center_shift, max(0.015, side))
        return center_distance(a.box01, b.box01) <= shift and ratio <= self.max_area_ratio

    def compatible(self, track: _Track, ob: GarmentObservation, shot: int) -> bool:
        last = track.last
        if last.media_id != ob.media_id or last.category != ob.category:
            return False
        if last.timestamp_ms is None or ob.timestamp_ms is None:
            return False
        if last.frame_asset_id == ob.frame_asset_id or any(o.frame_asset_id == ob.frame_asset_id for o in track.obs):
            return False
        if track.shot != shot:
            return False
        if not (0 < ob.timestamp_ms - last.timestamp_ms <= self.max_gap_ms):
            return False
        if last.person_track_id and ob.person_track_id and last.person_track_id != ob.person_track_id:
            return False
        if self._attr_conflict(last, ob):
            return False
        return self._spatially_continuous(last, ob)

    # ----------------------------------------------------------------- group
    def group(
        self,
        observations: Sequence[GarmentObservation],
        shot_boundaries_ms: Sequence[int] | Mapping[str, Sequence[int]],
        *,
        session_id: str,
        crop_quality: Callable[[str], float] | None = None,
    ) -> list[Garment]:
        """Return garments in first-seen order.

        ``shot_boundaries_ms`` is a list of cut times for a single media item or
        a mapping ``media_id -> cut times`` when several media are grouped.
        """

        def cuts_for(media_id: str) -> list[int]:
            if isinstance(shot_boundaries_ms, Mapping):
                return sorted(shot_boundaries_ms.get(media_id, []))
            return sorted(shot_boundaries_ms)

        ordered = sorted(
            observations,
            key=lambda o: (o.media_id, o.timestamp_ms if o.timestamp_ms is not None else -1, o.frame_asset_id, o.id),
        )
        tracks: list[_Track] = []
        open_tracks: list[_Track] = []
        i = 0
        while i < len(ordered):
            # One sampled frame at a time.
            frame_id = ordered[i].frame_asset_id
            frame_obs = []
            while i < len(ordered) and ordered[i].frame_asset_id == frame_id:
                frame_obs.append(ordered[i])
                i += 1
            ts = frame_obs[0].timestamp_ms
            shot = bisect.bisect_right(cuts_for(frame_obs[0].media_id), ts) if ts is not None else 0

            compat = {
                id(ob): [t for t in open_tracks if self.compatible(t, ob, shot)] for ob in frame_obs
            }
            per_track: dict[int, list[GarmentObservation]] = {}
            for ob in frame_obs:
                for t in compat[id(ob)]:
                    per_track.setdefault(id(t), []).append(ob)

            for ob in frame_obs:
                cands = compat[id(ob)]
                if len(cands) == 1 and len(per_track[id(cands[0])]) == 1:
                    cands[0].obs.append(ob)
                else:
                    t = _Track(obs=[ob], shot=shot)
                    tracks.append(t)
                    if ob.timestamp_ms is not None:
                        open_tracks.append(t)

        return [self._to_garment(t, session_id, crop_quality) for t in tracks]

    @staticmethod
    def _to_garment(track: _Track, session_id: str, crop_quality: Callable[[str], float] | None) -> Garment:
        obs = track.obs
        ids = [o.id for o in obs]
        gid = "gar_" + hashlib.sha256((session_id + "|" + "|".join(sorted(ids))).encode()).hexdigest()[:24]
        rep = max(obs, key=lambda o: crop_quality(o.crop_asset_id)) if crop_quality else obs[0]
        colors = rep.observed_attributes.get("color") or []
        label = f"{colors[0]} {rep.category}" if colors else rep.category
        return Garment(
            id=gid,
            session_id=session_id,
            observation_ids=ids,
            representative_crop_id=rep.crop_asset_id,
            label=label,
            grouping_basis="single" if len(obs) == 1 else "within_shot",
        )


def merge_user_confirmed(garments: Sequence[Garment], session_id: str) -> Garment:
    """Merge garments the user explicitly confirmed as the same item."""
    if len(garments) < 2:
        raise ValueError("need at least two garments to merge")
    if any(g.session_id != session_id for g in garments):
        raise ValueError("garments belong to different sessions")
    ids = [oid for g in garments for oid in g.observation_ids]
    gid = "gar_" + hashlib.sha256((session_id + "|" + "|".join(sorted(ids))).encode()).hexdigest()[:24]
    return Garment(
        id=gid,
        session_id=session_id,
        observation_ids=ids,
        representative_crop_id=garments[0].representative_crop_id,
        label=garments[0].label,
        grouping_basis="user_confirmed",
    )
