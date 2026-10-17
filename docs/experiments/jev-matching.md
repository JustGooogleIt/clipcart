# Jev for product matching: findings (bounded experiment)

Date: 2026-10-17. Branch: `exp/jev-match-eval`, from `integration` 77d53ef. No app code changed.

## Result

**Jev was not run.** No `JEV_API_KEY` or `TYPESAFE_API_KEY` exists in the environment or the root `.env`, so `GET /v1/models` and any decision call were impossible. Per the brief, there is no adapter and no PR. This document records the offline baseline and the expected decisions, written before any Jev output existed.

## Setup

- **Observed garment:** the live Perceptron mk1.5 observation (request `be94e617…`). It's a black bomber with gold side zip pockets, a gold centre zip, a ribbed collar, cuffs and hem, and a small embroidered chest logo shaped like a three-leaf clover. **No readable text.**
- **Shopper:** size M, fit category (men's or women's) not stated, no budget.
- **Candidates:** the four manual Grok Bot results, using **only the facts the shopper reported**. They aren't stored in the repo. Prices, colors and details not reported are null.
- **Baseline:** `scripts/experiments/jev_match_baseline.py` runs ClipCart's unchanged `rules.py`.

## Example-by-example

| Candidate (reported facts) | Expected decision | Deterministic pipeline | Gap |
| --- | --- | --- | --- |
| Albion Fit black bomber, **women's item** | Similar. Needs checking. Flag women's item with fit unknown, and side zips not evidenced. | Similar, needs checking (size unknown). **Ranked 1st** (relevance 0.24 from "black" + "bomber"). | **Missed:** no fit or gender rule. A women's item ranks first for a shopper whose fit is unknown. |
| Sacred Bones gold-logo bomber | Similar. Needs checking. No exact-match evidence: the logo and brand differ from the observed clover-shaped logo. Side zips and color not evidenced. | Similar, needs checking (size unknown), relevance 0.02. | **Partly missed:** the gold-logo versus clover-logo difference and missing side-zip evidence aren't surfaced. Ranking is low, which is right. |
| Alpha Industries MA-1 | Similar. Needs checking. No exact-match evidence. Side zips and color not evidenced. | **Set aside as "not a jacket"**, because the category gate has no "MA-1" or "flight" word. | **False negative** in the category vocabulary. |
| Karl Lagerfeld, Farfetch, size unverified | Similar. Needs checking. Size M not verified. No exact-match evidence. | Similar, needs checking (size unknown). | None. |

Correct everywhere: none of the four could be called an exact match. That needs readable text or a style code, and there is none.

## Could Jev close these gaps?

| Gap | Jev's likely contribution | Cheaper fix |
| --- | --- | --- |
| Women's item with fit unknown | A Choice question could classify fit from the title. | A deterministic gendered-title rule (`women's`, `womens`, `wmns`, `ladies`, `men's`) that leaves fit `unknown` and sends the item to Needs checking when the shopper's fit isn't stated. It's explainable and free. |
| "MA-1" fails the category gate | A model would recognise MA-1 as a bomber. | Add `ma-1`, `flight jacket` and similar terms to the category vocabulary. |
| Side zips and logo not evidenced | **Limited.** The evidence is title-only. No model can confirm side zips that the listing text doesn't mention. Jev could only say "insufficient evidence", which the rules can already state as `unknown`. | Surface key observed details (side zip pockets, logo) as `unknown` checks when listing text doesn't mention them. |

**Recommendation:** don't add Jev now. Two of the three gaps have small deterministic fixes. The third is an evidence problem, not a judgement problem. Those fixes change the verifier, which this brief said not to disrupt, so they belong in a separate approved PR.

Revisit Jev only when candidates carry richer listing text, such as product descriptions from detail pages or a research agent. Then a Score of "attribute agreement" across many described details could beat keyword overlap.

## Ready-to-run Jev check (when a key exists)

1. `GET https://api.typesafe.ai/v1/models` with `Authorization: Bearer $JEV_API_KEY`. Pick the returned model id rather than assuming `jev-latest`. This endpoint isn't on the quickstart or API-reference pages and must be confirmed.
2. One `POST /v1/systemone` per candidate. Send only observed attributes plus listing facts: no URLs, prices or retailer claims.

```json
{
  "model": "<id from /v1/models>",
  "state": {
    "observed_garment": {"category": "jacket", "colors": ["black", "gold"], "cut": ["bomber", "ribbed collar", "full front zip"],
                         "details": ["two side zip pockets with gold zippers", "small chest logo, three-leaf clover shape"],
                         "visible_text": []},
    "shopper": {"fit_category": "unknown"},
    "listing_evidence": {"title": "Albion Fit black bomber (women's)", "brand": "Albion Fit", "stated_facts": ["black", "bomber", "women's item"]}
  },
  "questions": {
    "agreement": {"type": "score", "instructions": "How closely does the listing evidence match the observed garment's visible attributes? Use only the evidence given.",
                  "criteria": ["Contradicts a visible attribute", "Same category only", "Category and color agree; key details unknown",
                               "Category, color and key details agree"]},
    "evidence": {"type": "choice", "instructions": "Is the listing evidence enough to call this the same product?",
                 "criteria": {"exact_supported": "Text or code ties the listing to this exact garment",
                              "similar_only": "Resemblance only; no identifying evidence",
                              "insufficient": "Too little evidence to judge similarity"}},
    "fit_conflict": {"type": "noul", "instructions": "Is the listing for a specific fit category (men's or women's) that the shopper has not chosen?"}
  }
}
```

**Pass bar, set in advance.** Jev adds value only if all of these hold:
1. It flags Albion Fit's fit conflict.
2. It never returns `exact_supported` for any of the four.
3. It ranks Albion Fit or Alpha MA-1 above Sacred Bones and Karl Lagerfeld on agreement.
4. It does all of this with confidence high enough to act on, at under about 1 s per candidate.

Even then, it could only reorder or demote candidates. Hard rules, URL checks, price evidence and eligibility stay deterministic.

## Note from the YouTube integration check

The latest `integration` code (77d53ef, PRs #5 and #7) passes `pytest services/api/tests`: 148 passed, 1 skipped. It now downloads YouTube clips server-side with yt-dlp (`app/media/youtube_cache.py`, capped at 90 s, 720p and a 1 h TTL). Earlier guidance ruled out a downloader for the Gemini path, so the product owner should confirm this is intended and acceptable under YouTube's terms.
