"""Accessories in perception: label mapping, small objects, attribute budget, appearance-only output, grouping."""

import io

from app.media.grouping import GarmentGrouper
from app.providers.perceptron.adapter import category_from_label
from app.providers.perceptron.sdk import AttributeResponse, DetectResponse, RawDetection
from media_factory import encode_with_orientation, marker_image
from test_grouping import obs
from test_perceptron_adapter import OWNER, FakeBackend, ctx, provider


def _frame(media, box=(40, 200, 140, 280)):
    asset = media.ingest(io.BytesIO(encode_with_orientation(marker_image((400, 300), box), 1)), OWNER)
    return media.extract_frames(asset.id, OWNER)[0]


JACKET = RawDetection("jacket or coat", 100, 667, 350, 933)  # 100x80 px
EARRING = RawDetection("earring", 600, 100, 650, 167)  # 20x20 px on 400x300: a small object


def test_earring_and_watch_labels_win_over_garment_words():
    assert category_from_label("earring") == "earrings"
    assert category_from_label("gold watch on a leather strap") == "watch"
    assert category_from_label("jacket or coat") == "jacket"


def test_accessories_are_detected_only_when_requested(media):
    f = _frame(media)
    be = FakeBackend(detect=lambda n: DetectResponse([JACKET, EARRING], f"d{n}", "m", None, True))
    garments_only = provider(media, be, max_attribute_calls=0).analyze([f], ["jacket", "top", "pants", "bag"], ctx())
    assert [o.category for o in garments_only.observations] == ["jacket"]
    both = provider(media, be, max_attribute_calls=0).analyze(
        [f], ["jacket", "top", "pants", "bag", "watch", "necklace", "bracelet", "ring", "earrings"], ctx())
    assert sorted(o.category for o in both.observations) == ["earrings", "jacket"]


def test_small_accessory_gets_an_attribute_call_and_appearance_only_attributes(media):
    f = _frame(media)
    seen = []

    def describe(n, cat):
        seen.append(cat)
        if cat == "earrings":
            return AttributeResponse({"color": ["14k yellow gold"], "cut": ["hoop"], "pattern": [],
                                      "details": ["diamond accents", "Tiffany-style clasp"], "visible_text": ["T&CO"]},
                                     f"a{n}", "m", None)
        return AttributeResponse({"color": ["black"], "cut": ["bomber"], "pattern": [], "details": [], "visible_text": []},
                                 f"a{n}", "m", None)

    be = FakeBackend(detect=lambda n: DetectResponse([JACKET, EARRING], f"d{n}", "m", None, True), describe=describe)
    res = provider(media, be, max_attribute_calls=1).analyze([f], ["jacket", "earrings"], ctx())
    ear = next(o for o in res.observations if o.category == "earrings")
    assert seen == ["earrings"]  # the one call went to the small accessory, not the bigger jacket
    a = ear.observed_attributes
    assert a["color"] == ["gold-tone"] and a["cut"] == ["hoop"]
    assert a["details"] == ["clear stone accents", "clasp"]
    assert a["appearanceNormalized"] == ["true"]
    assert ear.visible_text == ["T&CO"]  # lettering kept verbatim as text seen, never as a brand


def test_garment_attributes_are_not_rewritten(media):
    f = _frame(media)
    be = FakeBackend(detect=lambda n: DetectResponse([JACKET], f"d{n}", "m", None, True),
                     describe=lambda n, c: AttributeResponse({"color": ["gold"], "details": ["gold zipper"]}, "a", "m", None))
    o = provider(media, be, max_attribute_calls=1).analyze([f], ["jacket"], ctx()).observations[0]
    assert o.observed_attributes == {"color": ["gold"], "details": ["gold zipper"]}


def test_find_keeps_small_boxes_for_accessory_queries_only(media):
    f = _frame(media, box=(240, 30, 260, 50))
    small = RawDetection("x", 600, 100, 650, 167)  # 0.05 x 0.067 = 0.0033 of the frame
    be = FakeBackend(detect=lambda n: DetectResponse([small], f"d{n}", "m", None, True))
    acc = provider(media, be, max_attribute_calls=1).find_open_vocab([f], "gold hoop earring", ctx())
    assert len(acc.observations) == 1
    be2 = FakeBackend(detect=lambda n: DetectResponse([small], f"d{n}", "m", None, True))
    garment = provider(media, be2, max_attribute_calls=1).find_open_vocab([f], "black bomber jacket", ctx())
    assert garment.observations == []


def test_find_normalizes_accessory_descriptions(media):
    f = _frame(media, box=(240, 30, 260, 50))
    small = RawDetection("x", 600, 100, 650, 167)
    be = FakeBackend(detect=lambda n: DetectResponse([small], f"d{n}", "m", None, True))
    be.describe_object = lambda crop, q: AttributeResponse(
        {"what": "18k gold diamond stud earring", "color": ["gold"], "pattern": [], "form": ["stud"],
         "details": ["genuine diamond"], "search_description": "18k gold diamond stud earrings authentic Cartier",
         "visible_text": []}, "o", "m", None)
    o = provider(media, be, max_attribute_calls=1).find_open_vocab([f], "gold stud earring", ctx()).observations[0]
    blob = " ".join([o.raw_label, *o.observed_attributes["details"], *o.observed_attributes["color"]]).lower()
    assert "diamond" not in blob and "18k" not in blob and "cartier" not in blob and "authentic" not in blob
    assert "gold-tone" in blob and "clear stone" in blob


G = GarmentGrouper()


def test_two_earrings_in_one_frame_stay_two_items():
    o = [obs("l0", "f0", 0, (0.30, 0.40, 0.33, 0.44), cat="earrings"), obs("r0", "f0", 0, (0.42, 0.40, 0.45, 0.44), cat="earrings")]
    assert len(G.group(o, [], session_id="s")) == 2


def test_small_accessory_moving_slightly_merges_but_a_far_one_does_not():
    near = [obs("a", "f0", 0, (0.30, 0.40, 0.33, 0.44), cat="ring"), obs("b", "f1", 500, (0.31, 0.405, 0.34, 0.445), cat="ring")]
    assert len(G.group(near, [], session_id="s")) == 1
    far = [obs("a", "f0", 0, (0.30, 0.40, 0.33, 0.44), cat="earrings"), obs("b", "f1", 500, (0.40, 0.40, 0.43, 0.44), cat="earrings")]
    assert len(G.group(far, [], session_id="s")) == 2  # 0.10 apart: a garment rule would have merged these


def test_partially_visible_accessory_at_frame_edge_is_kept(media):
    f = _frame(media, box=(0, 0, 20, 20))
    edge = RawDetection("wristwatch", 0, 0, 40, 60)  # touches the frame edge, 16x18 px
    be = FakeBackend(detect=lambda n: DetectResponse([edge], f"d{n}", "m", None, True))
    res = provider(media, be, max_attribute_calls=0).analyze([f], ["watch"], ctx())
    assert [o.category for o in res.observations] == ["watch"]
