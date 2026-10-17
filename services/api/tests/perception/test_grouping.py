from app.media.grouping import GarmentGrouper, merge_user_confirmed
from app.media.types import GarmentObservation


def obs(oid, frame, ts, box, cat="jacket", color=None, media="med_x", person=None):
    return GarmentObservation(
        id=oid,
        media_id=media,
        frame_asset_id=frame,
        timestamp_ms=ts,
        box01=box,
        crop_asset_id=f"crp_{oid}",
        category=cat,
        person_track_id=person,
        observed_attributes={"color": color} if color else {},
        visible_text=[],
        provider_request_id=None,
        model_id="test",
        edited_by_user=False,
    )


G = GarmentGrouper()


def test_same_jacket_across_consecutive_frames_merges():
    o = [obs("a", "f0", 0, (0.1, 0.2, 0.4, 0.8)), obs("b", "f1", 500, (0.12, 0.2, 0.42, 0.8)), obs("c", "f2", 1000, (0.14, 0.21, 0.44, 0.8))]
    [g] = G.group(o, [], session_id="s")
    assert g.observation_ids == ["a", "b", "c"]
    assert g.grouping_basis == "within_shot"


def test_two_similar_jackets_on_two_people_stay_separate():
    """AT04: same colour, same frames, different positions -> two garments."""
    o = [
        obs("l0", "f0", 0, (0.05, 0.2, 0.35, 0.8), color=["gray"]),
        obs("r0", "f0", 0, (0.6, 0.2, 0.9, 0.8), color=["gray"]),
        obs("l1", "f1", 500, (0.06, 0.2, 0.36, 0.8), color=["gray"]),
        obs("r1", "f1", 500, (0.61, 0.2, 0.91, 0.8), color=["gray"]),
    ]
    gs = G.group(o, [], session_id="s")
    assert sorted(sorted(g.observation_ids) for g in gs) == [["l0", "l1"], ["r0", "r1"]]


def test_overlapping_people_are_ambiguous_and_not_merged():
    # Two jackets in frame 1 both overlap the single jacket from frame 0.
    o = [
        obs("a", "f0", 0, (0.3, 0.2, 0.6, 0.8)),
        obs("b", "f1", 500, (0.28, 0.2, 0.55, 0.8)),
        obs("c", "f1", 500, (0.35, 0.2, 0.62, 0.8)),
    ]
    gs = G.group(o, [], session_id="s")
    assert len(gs) == 3 and all(g.grouping_basis == "single" for g in gs)


def test_cut_prevents_merge():
    o = [obs("a", "f0", 0, (0.1, 0.2, 0.4, 0.8)), obs("b", "f1", 1500, (0.1, 0.2, 0.4, 0.8))]
    assert len(G.group(o, [1000], session_id="s")) == 2
    assert len(G.group(o, [], session_id="s")) == 1


def test_large_time_gap_prevents_merge():
    o = [obs("a", "f0", 0, (0.1, 0.2, 0.4, 0.8)), obs("b", "f1", 9000, (0.1, 0.2, 0.4, 0.8))]
    assert len(G.group(o, [], session_id="s")) == 2


def test_colour_conflict_and_category_conflict_prevent_merge():
    a = obs("a", "f0", 0, (0.1, 0.2, 0.4, 0.8), color=["black"])
    assert len(G.group([a, obs("b", "f1", 500, (0.1, 0.2, 0.4, 0.8), color=["tan"])], [], session_id="s")) == 2
    assert len(G.group([a, obs("c", "f1", 500, (0.1, 0.2, 0.4, 0.8), cat="bag")], [], session_id="s")) == 2
    # Missing colour on one side is not a conflict.
    assert len(G.group([a, obs("d", "f1", 500, (0.1, 0.2, 0.4, 0.8))], [], session_id="s")) == 1


def test_person_track_conflict_prevents_merge():
    a = obs("a", "f0", 0, (0.1, 0.2, 0.4, 0.8), person="person_1")
    b = obs("b", "f1", 500, (0.1, 0.2, 0.4, 0.8), person="person_2")
    assert len(G.group([a, b], [], session_id="s")) == 2


def test_still_images_never_merge_and_ids_are_stable():
    o = [obs("a", "f0", None, (0.1, 0.2, 0.4, 0.8)), obs("b", "f9", None, (0.1, 0.2, 0.4, 0.8))]
    gs = G.group(o, [], session_id="s")
    assert len(gs) == 2 and {g.grouping_basis for g in gs} == {"single"}
    assert [g.id for g in G.group(list(reversed(o)), [], session_id="s")] == [g.id for g in gs]


def test_different_media_never_merge():
    o = [obs("a", "f0", 0, (0.1, 0.2, 0.4, 0.8), media="m1"), obs("b", "f1", 500, (0.1, 0.2, 0.4, 0.8), media="m2")]
    assert len(G.group(o, {"m1": [], "m2": []}, session_id="s")) == 2


def test_label_and_representative_crop():
    o = [obs("a", "f0", 0, (0.1, 0.2, 0.4, 0.8), color=["black"]), obs("b", "f1", 500, (0.1, 0.2, 0.4, 0.8), color=["black"])]
    [g] = G.group(o, [], session_id="s", crop_quality=lambda cid: 2.0 if cid == "crp_b" else 1.0)
    assert g.label == "black jacket" and g.representative_crop_id == "crp_b"


def test_user_confirmed_merge():
    o = [obs("a", "f0", 0, (0.1, 0.2, 0.4, 0.8)), obs("b", "f1", 9000, (0.6, 0.2, 0.9, 0.8))]
    gs = G.group(o, [], session_id="s")
    merged = merge_user_confirmed(gs, "s")
    assert merged.grouping_basis == "user_confirmed" and sorted(merged.observation_ids) == ["a", "b"]
