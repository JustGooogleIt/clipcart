# Contract: accessories (watches and jewelry)

Status: **published for UI review before any frontend work** on `feat/accessories`. Backend owner: Claude. UI owner: Claude app. Every change is **additive**. Existing garment categories, fields and behavior are unchanged.

## Categories

`Category` gains five values. Existing values stay valid.

| `category` | Label | Family | Size rule |
| --- | --- | --- | --- |
| `jacket`, `top`, `pants` | Jacket, Top, Pants | `apparel` | Clothing `preferences.size` |
| `bag` | Bag | `bag` | Clothing `preferences.size`, unchanged from today's behavior |
| `watch` | Watch | `watch` | None. Clothing size never applies. |
| `necklace` | Necklace | `jewelry` | None. Clothing size never applies. |
| `bracelet` | Bracelet | `jewelry` | None. Clothing size never applies. |
| `ring` | Ring | `jewelry` | `preferences.ringSize` only |
| `earrings` | Earrings | `jewelry` | None. Clothing size never applies. |
| `other` | Other | `other` | None |

### New: `GET /api/categories`

Read-only, no flag, no auth. The UI should build category pickers and per-category rule inputs from this response rather than hard-coding them.

```json
{ "categories": [
  { "id": "jacket", "label": "Jacket", "family": "apparel", "sizeRule": "clothing", "attributeKeys": ["color", "pattern", "cut", "details"] },
  { "id": "ring", "label": "Ring", "family": "jewelry", "sizeRule": "ring", "attributeKeys": ["color", "cut", "details"] },
  { "id": "watch", "label": "Watch", "family": "watch", "sizeRule": "none", "attributeKeys": ["color", "cut", "details"] }
] }
```

`sizeRule` is `clothing`, `ring` or `none`.

## Observed attributes (`GarmentObservation.observedAttributes`)

The keys are the same as for garments. Their meaning per family:

| Key | Apparel and bag (unchanged) | Watch and jewelry |
| --- | --- | --- |
| `color` | Hues | Tone and visible colors only: `gold-tone`, `silver-tone`, `rose-gold-tone`, `black`, `two-tone`, plus dial or bead colors |
| `cut` | Silhouette and closures | Form: `hoop`, `stud`, `drop`, `chain`, `pendant`, `choker`, `bangle`, `cuff`, `link`, `beaded`, `band`, `signet`, `round case`, `square case`, `metal bracelet strap`, `leather-look strap` |
| `pattern` | Pattern | Usually empty |
| `details` | Visible cues | Visible cues such as `clear stones`, `textured links`, `numeral dial`, `bezel markings`, `small charm` |
| `visibleText` | Readable lettering | Readable lettering, labelled "text seen on the item". **Never a brand or authenticity claim.** |

### Appearance-only rule (enforced in code)

ClipCart never infers authenticity, a luxury brand, precious metal or gemstone composition from how an item looks. Model output for accessories is normalized before storage:

| Model says | Stored as |
| --- | --- |
| gold, rose gold, silver, platinum, white gold | `gold-tone`, `rose-gold-tone`, `silver-tone`, `silver-tone`, `silver-tone` |
| diamond, crystal, cubic zirconia | `clear stone` |
| emerald, ruby, sapphire | `green stone`, `red stone`, `blue stone` |
| pearl, pearls | `round beads` |
| 14k, 18k, 925, sterling, karat, solid gold, plated, genuine, authentic, real, luxury, designer, replica | removed |
| Luxury brand names in model-written attributes, for example "Rolex-style crown" | removed. Lettering stays only in `visibleText`. |

A garment whose attributes were changed this way gets `"appearanceNormalized": ["true"]` in `observedAttributes`. Values are always string lists.

## Shopper constraints

- **Ring size:** `Preferences.ringSize` is new and optional, shaped `{ "raw": "7", "system": "us" }`. It sits alongside `size` and appears in `PreferencePatch` too. It applies **only** to `ring` searches. Half sizes such as `"6.5"` are allowed.
- **Clothing size:** `preferences.size` is ignored for watch and jewelry searches. **No `size` constraint check is emitted** for them, so it can never exclude a watch or necklace.
- **Unchanged constraints:** budget, colors, excluded materials and condition apply to every category. Colors match tone words, so the shopper's `gold` also matches `gold-tone` listings.

## Results for accessories

- **Identity tier:** a watch or jewelry result is never `verified` or `likely` from appearance. The tier is capped at `similar`, and the card says "Similar look".
- **Seller claims:** when a listing's title or material text claims precious metal, gemstones or authenticity (for example "14k gold", "diamond", "authentic"), the result gets this warning: *"Metal, stones and authenticity are the seller's description; ClipCart doesn't verify them."* The claim is never repeated as a ClipCart fact.
- **Category matching:**
  - Watch straps and bands are not watches.
  - "Key ring", "ring light" and "O-ring" are not rings.
  - Earrings are never matched as rings.

## Grouping and small objects

- **Grouping:** accessories group only within their own category, and the center-shift allowance is relative to the box size. Two earrings in one frame stay two items, because the existing rule says two boxes in a frame are two items.
- **Find in video:** it accepts smaller boxes for accessory queries, down to about 0.04% of the frame, and stops preferring large boxes for them.
- **Manual crop:** `POST /api/sessions/{id}/garments` accepts the new categories in `category`. The minimum crop is still 16 px a side.
- **Automatic detection:** this is behind the new flag `FEATURE_ACCESSORY_DETECTION`, **off by default**. It changes the live Perceptron request, so turning it on is a proposed change for the owner. While it's off, accessories come only from manual crop and Find in video.

## Style memory

There are new memory kinds:

- **Tone:** `tone_like` and `tone_avoid`, with values `gold-tone`, `silver-tone`, `rose-gold-tone`, `black` and `two-tone`.
- **Ring size:** `ring_size`, shaped `{raw, system: "us"}`, which is one active value, like `size`.

`StyleProfileView` gains `tonesLike`, `tonesAvoid` and `ringSize`. Tone preferences nudge ranking **only for watch and jewelry searches**. A jacket with gold buttons is never boosted by a gold-tone jewelry preference.

The clothing `size` memory never applies to accessories.

## Health

`features.accessoryDetection` reports the flag. `GET /api/categories` is always available.

## Live Perceptron checks still needed

These are separate from the offline tests, and none has been run. Each one is a single bounded call with `PERCEPTRON_MAX_TOKENS` 1200, run only with the owner's approval:

1. **Wrist (1 detect):** a photo of a wrist with a watch and a bracelet, with the accessory classes requested. Confirm the labels map to `watch` and `bracelet` and the boxes fit the objects.
2. **Portrait (1 detect):** a close-up showing earrings and a necklace. Confirm small earring boxes are returned and kept.
3. **Hand (1 detect):** a ring on a hand, a small object possibly cut off at the frame edge.
4. **Find (1 detect + 1 describe):** Find in video with "gold hoop earring" on a portrait frame where the earring is under 0.4% of the frame.
5. **Describe (1 call):** one accessory crop. Confirm the JSON follows the schema and the tone wording, and count how often the normalizer has to rewrite the output.

That's at most 7 paid calls in total. Turning on `FEATURE_ACCESSORY_DETECTION` for everyday use should wait until checks 1–3 look right.

## UI follow-up (Claude app)

1. **Pickers:** category pickers (manual crop, garment edit) get their options from `GET /api/categories`.
2. **Size inputs:** when the selected item's `sizeRule` is `none`, hide clothing size inputs and chips. When it's `ring`, show a **Ring size (US)** input bound to `preferences.ringSize`.
3. **Tone chips:** offer Gold-tone, Silver-tone and Rose-gold-tone suggestions for color when the selection is watch or jewelry.
4. **Labels:** show `visibleText` for accessories as "Text seen on the item", never as a brand. Show the seller-claims warning and the "Similar look" tier as returned.
5. **Memory panel:** show `tone_like`, `tone_avoid` and `ring_size` with the existing like/avoid and size patterns. The backend PR adds only type-compatible labels to `StylePanel.tsx`'s exhaustive `KIND` map ("Likes", "Avoids" and "Ring size") so the build stays green. Their presentation is the UI lane's.
