# ClipCart System Requirements

Version 1.2 | October 17, 2026 | Product owner Ashwin Subramanian

Audience: Ashwin, his teammate, and the coding agents implementing the DubHacks prototype.

**Product promise: Send us a look. Your shopping agent finds the original, searches alternatives, and brings back options that fit your budget.**

This is the implementation contract for ClipCart, the fashion-commerce pivot. It replaces the Afterspace VFX plan for this build. It specifies a working core, optional sponsor extensions, two-person execution, coding-agent ownership, runtime contracts, and acceptance gates. Use ClipCart in the app UI, demo, and submission materials.

## 1 Recommended decision

Build ClipCart as a web-first fashion shopping agent for jackets, tops, and bags. A user provides a video or image, selects a garment, and receives real retailer listings. Perceptron identifies the garment. Two bounded Grok-powered search workers look for the original and alternatives. A verification stage evaluates the evidence and constraints. MongoDB Atlas stores the session, garment observations, listing evidence, preferences, and results.

The user can refine results with text first and Grok Voice next. Photon adds an iMessage entry point into the same backend. Shopping has two completion paths: third-party retailer listings route to the retailer, while a small, explicitly participating demo merchant catalog can use in-app Solana devnet checkout and issue a compressed NFT receipt after verified payment. Referral revenue and merchant checkout fees are distinct business hypotheses; neither follows automatically from a click or a test payment.

The main Claude Code session owns the full-stack implementation and all integration decisions. Codex owns a narrow media/perception module and its tests. The teammate owns provider access, real product evidence, demo examples, and the Photon proof of connection. Grok and Cursor assist these owners; they do not become additional independent architects.

The highest-value result is one reliable workflow from a real garment crop to useful product listings and a working retailer link. Voice, iMessage, and receipts must not prevent that workflow from shipping.

## 2 What success looks like

A judge sees a short fashion clip and says, "Find that jacket under $120, in medium, with no leather." The app shows which garment it selected, searches for the original and alternatives, and returns evidence-backed options. The judge can ask for a different color without losing the budget. Clicking a result opens the relevant retailer page.

The demo must show a real tool decision: for example, the original exceeds the budget, so the system retrieves alternatives; or a candidate has conflicting material information, so it is excluded or labeled uncertain. An agent animation without tool execution does not satisfy the agentic requirement.

The two-click promise means selecting a product card and opening its retailer listing. Checkout, shipping, payment, and final stock confirmation happen at the retailer. We do not promise two-click purchase completion.

Prototype limits: one selected garment at a time; one shopping session per browser user; an uploaded clip of at most 90 seconds or a supported link segment; US/USD shopping by default; up to three primary recommendations. These limits are implementation choices, not claims that all videos or retailers are supported.

## 3 Team and coding-tool allocation

### Human ownership

| Owner | Primary job | Must personally verify |
| --- | --- | --- |
| Ashwin | Product decisions, main Claude Code session, merges, final demo | The end-to-end experience, priorities, sponsor story, and submission |
| Teammate | Data/provider access, example clips, product truth set, Photon setup, independent testing | Real listings and API access; messages round-trip; matching quality on unfamiliar examples |

The teammate's coding experience is unknown. Their critical-path assignments must be achievable with their available Grok account and normal developer tools. If they can code, they can own the isolated Photon bridge after its contract is frozen. If they cannot, they own the connection proof and fixtures; Claude implements the bridge later.

### Coding-tool ownership

| Tool or account | Assigned role | Boundary |
| --- | --- | --- |
| Main Claude Max / Claude Code | Lead implementer and sole integration owner; approximately two-thirds of implementation effort | Frontend, API, contracts, database, Grok orchestration, ranking, referral flow, final integration |
| Ashwin's Codex access | Bounded media/perception implementation, then targeted independent review | Frame extraction, crop geometry, Perceptron adapter, deduplication, module tests |
| Ashwin's Cursor Pro | Editor and short local fixes approved by integration owner | No second full-stack rewrite and no simultaneous edits to files Claude owns |
| Ashwin's Grok access | Provider research, agent prompt experiments, documentation checks | Evidence and proposed prompts; runtime access is verified separately |
| Teammate's Grok access | Catalog research, adversarial examples, manual tests, optional Photon bridge assistance | Own account, separate task context, explicit deliverables |

Effort allocation is a planning choice, not a prediction of model throughput. Use the strongest available reasoning mode for contracts and difficult integration bugs; use a normal coding mode for bounded implementation. Do not assume specific model names, unlimited usage, or identical limits across accounts.

Keep one main Claude session rather than many competing full-repository sessions. It may use a bounded reviewer or research subtask when supported, but the review cannot modify owned implementation files concurrently. Check current usage before launching large tasks. Keep a handoff checkpoint after each milestone so Codex or a human can take over if a limit is reached.

### Development access versus runtime access

Subscriptions fund supported developer interactions; application API access and billing require separate verification. Claude's current documentation describes shared Claude/Claude Code limits and possible plan-specific API credits, so do not assume either no credits or unlimited API credit. Codex access also has plan-specific usage limits. Cursor/Grok entitlements vary by actual account configuration. Inspect each dashboard rather than deriving access from the informal plan name. [S1, S2, S3]

Do not share account passwords or route shopper requests through a logged-in consumer chat application. Application runtime uses supported APIs and project credentials. Grok Bot is a separately documented agent product; a website-callable dispatch interface has not been established for this project. Use Grok API workers unless a supported integration is verified. [S4]

No Claude or OpenAI API is required by the proposed production path. Claude and Codex write the code; Perceptron and xAI power the demonstrated AI features. This separation prevents an accidental dependency on coding-plan allowances for shopper requests.

## 4 Before coding and access gates

Use the remaining pre-build time for planning and access checks consistent with event rules. Do not create application code or fixtures early if prohibited by the organizers. The supplied event materials describe a 12:30 PM Saturday build start; verify the final rule at opening. Plan to submit the draft by 10:30 PM Saturday and the final by 10:00 AM Sunday, America/Los_Angeles, unless organizers explicitly revise those deadlines. [S5]

| Dependency | Smallest proof | Owner | Fallback |
| --- | --- | --- | --- |
| Perceptron | One real image request returning an interpretable garment region | Ashwin plus Codex | Typed manual crop keeps the app working but does not satisfy the Perceptron demo gate |
| Product retrieval | One actual query returns listing URLs, images, and sourced prices | Teammate | Bounded sourced catalog, labeled catalog mode |
| Grok runtime | One structured/tool-call request using a valid API key | Ashwin | Deterministic search flow, labeled non-agentic; reduced scope |
| MongoDB Atlas | Authenticated write and read from backend | Claude | Local development store behind adapter, explicitly not Atlas-track completion |
| Video input | Decode a team-owned uploaded clip and extract timed frames | Codex | Still image upload; reduced video scope |
| Photon | Receive a test message and reply through the chosen SDK | Teammate | Web experience remains available; omit Photon claim |
| Grok Voice | Browser microphone to transcript/reply | Claude after core | Text input |
| Solana | Verify one controlled demo-merchant payment on devnet, then mint/retrieve a buyer-wallet compressed NFT | Isolated late task | Keep retailer redirect working; mark checkout unavailable and do not claim payment or receipt |

Verify the actual third-party product-search account first. eBay Browse is one documented candidate for listing retrieval, including image-based search, but its availability and permissions for this account must be tested. Do not spend hours implementing an endpoint that the team cannot call. [S6]

For shopping data, choose one usable provider in the first two build hours. A commercial product-search provider, a merchant feed, or a supported marketplace API is acceptable. Document the selected provider and actual coverage. General web search can discover candidates, but search snippets alone are insufficient evidence of current size or stock.

Use sponsor credits where available. Configure request limits and provider spending controls. No paid plan purchase, automatic top-up, or budget increase is authorized by this document. If paid API capacity is unavailable, expose the reduced mode honestly.

## 5 Priorities and explicit exclusions

| Level | Scope |
| --- | --- |
| P0 required | Uploaded video/image, real Perceptron observations, garment selection, sourced product retrieval, bounded Grok search workers, evidence-based ranking, text refinement, Atlas persistence, retailer redirect tracking |
| P1 desired | Supported YouTube ingestion, Grok Voice, Photon iMessage, polished comparison cards, second-provider price comparison |
| P2 extension | Wallet-connected Solana devnet checkout for one controlled demo product, verified order, compressed NFT receipt, wardrobe-aware follow-up |
| Deferred | Universal checkout, real-money checkout, payment for unaffiliated retailer inventory, autonomous purchasing, production affiliate settlement, arbitrary-video coverage, exhaustive wardrobe extraction, virtual try-on, continuous price monitoring, large product-catalog indexing |

YouTube link entry remains a visible intended workflow. Promote real link ingestion to P0 only after the access gate works. The reliable demonstration path must accept an uploaded video even if link ingestion succeeds. A preset demonstration video must be explicitly labeled; never pretend an arbitrary link was analyzed when the app substituted a fixture.

A full live demonstration requires actual provider calls for perception and product search. Fixtures are appropriate for development and replay; they must be labeled when presented. Partial modes do not qualify as completed sponsor integrations.

## 6 User journeys

### Core web journey

1. Create a shopping session and choose a link, video upload, or image upload.
2. See truthful ingestion and analysis status.
3. Select a garment from a frame or a deduplicated garment tray.
4. Enter optional budget, size with sizing system, color, material exclusions, and shopping region.
5. Start the search. See real progress events and partial results when verified.
6. Review up to three recommended items with original crop, listing image, price, retailer, match label, evidence, and availability status.
7. Refine with text or voice. A new search revision preserves unspecified preferences.
8. Select a result for details. External inventory opens the retailer checkout; an explicitly participating demo merchant item can offer the optional in-app devnet checkout.

### Photon journey

1. A user sends a link or photo and a shopping request to the provisioned bot.
2. The bot resolves or asks for the target garment; it does not guess when several people/items are plausible.
3. The same backend executes the search.
4. The bot returns short recommendations, supported image attachments, and retailer links.
5. "The second one in black" refers to the stable last-presented result list for that conversation.

### Participating merchant checkout and receipt journey

1. The user selects an eligible item from a controlled demo merchant catalog. External retailer items retain the outbound-link path and cannot be paid for in this app.
2. The app shows the merchant, item, fixed devnet price, network, and demo-only fulfillment terms before wallet connection or signing.
3. The user connects a devnet wallet and approves a Solana Pay transfer to the demo merchant's wallet with a unique order reference.
4. The server verifies the confirmed transaction, recipient, amount, asset/mint, network, reference, and successful status before marking the order paid. Wallet UI success alone is insufficient.
5. The server mints one compressed NFT receipt to the buyer wallet, reconciles uncertain mint outcomes, and displays separate payment and receipt states.
6. The wardrobe records a verified devnet test purchase. It never implies that an outside retailer shipped an item.

## 7 Functional requirements

### Media and perception

**FR01 P0** Accept JPEG/PNG and MP4/MOV input through bounded streaming upload. Validate actual media type with decoding/probing; reject excessive duration, dimensions, or size before expensive processing.

**FR02 P1** Accept a canonical YouTube URL and optional selected interval. Embed playback using the supported player. Obtain analysis bytes only through a verified supported ingestion path. The player iframe is not a frame-extraction API. If retrieval fails, request a clip or screenshot. [S7]

**FR03 P0** Extract a bounded frame sample with accurate source timestamps. Preserve orientation and a known mapping between original and resized image coordinates. Store frame/crop provenance.

**FR04 P0** Use Perceptron to identify visible jackets, tops, and bags and provide region observations. Extract category, color, pattern, cut, visible text/logo evidence, and descriptive details. Store uncertainty; never invent brand identity, fabric composition, body measurements, or size from appearance.

**FR05 P0** Show cropped observations alongside their source timestamp. A user can adjust a crop and relabel its category. Preserve which fields are model-generated and which were user-corrected.

**FR06 P0** Group likely repeated observations within a continuous shot. Do not merge similar garments on different people or across cuts without evidence. When uncertain, retain separate candidates or ask the user.

**FR07 P0** Search only the selected garment. Scanning a video must not launch a shopping agent for every visible object automatically.

### Search and refinement

**FR08 P0** Capture explicit constraints: budget and currency, size and sizing system, color, material exclusions, condition preference, and shopping country. Preserve original user wording when normalization is uncertain.

**FR09 P0** Run an exact-match worker and an alternatives worker with bounded tools. Each returns real listing references and evidence, not invented product names or URLs.

**FR10 P0** Verify and deduplicate candidate listings before ranking. Track observed price, variant, condition, availability, evidence source, and observation time.

**FR11 P0** Separate identity certainty from stock certainty. An exact product match can still have unknown size availability. Classify products as verified match, likely match, or similar option according to Section 11.

**FR12 P0** Apply hard constraints deterministically. Do not recommend an over-budget item as within budget, claim unknown material meets an exclusion, or equate different sizing systems without a mapping.

**FR13 P0** Return three or fewer useful primary results. If fewer qualify, return fewer and explain the constraint or missing information. Do not silently relax preferences to fill three cards.

**FR14 P0** Apply text refinements as validated patches to preferences or selection. Preserve all unspecified fields. Reject stale refinements or resolve them against the last committed session revision.

**FR15 P0** Supersede in-flight searches when the user changes the selected garment or preferences. Late results from the old search must not overwrite the current result set.

**FR16 P0** Expose honest progress based on tool/job events: locating garment, searching original, searching alternatives, verifying listings, completed/partial/no match/failed. Do not expose hidden model reasoning or manufacture activity.

### Retailer routing and persistence

**FR17 P0** Show price and currency from a source, a checked-at timestamp, match basis, retailer domain, and size status. Unknown information must be null/unknown, never a guessed default.

**FR18 P0** Route to the selected product and variant URL where available. A redirect endpoint accepts only a stored listing ID, never an arbitrary client-supplied URL.

**FR19 P0** Record outbound referral events idempotently. Distinguish gross clicks, deduplicated click events, and verified conversions. Do not show estimated commissions as earned revenue.

**FR20 P0** Persist sessions, selection, preferences, searches, evidence, and results in Atlas. Reload restores the last committed state, not transient placeholders.

**FR21 P0** Protect sessions with a server-issued opaque identity and ownership checks. One user must not access another user's media, preferences, order, or messages by changing a URL ID.

### Optional interfaces and receipts

**FR22 P1** Add push-to-talk Grok Voice with visible listening state, transcript, and editable interpreted preferences. The voice path calls the same shopping tools as text and speaks only from validated results.

**FR23 P1** Handle corrections and interruption. A spoken "actually, under $80" changes the budget while preserving the garment and other constraints. A failed voice connection leaves text usable.

**FR24 P1** Add Photon with a signed/verified inbound connection, duplicate-message handling, and conversation-scoped state. Reply only to the originating conversation and route.

**FR25 P1** Link a Photon conversation to a web session only via an explicit, short-lived, single-use linking flow. Never infer shared identity from names or a phone number entered in a web form.

**FR26 P1** Compare prices only for the same identifiable product and compatible variant/condition. Similar alternatives belong in a separate list. Shipping/tax exclusions must remain visible.

**FR27 P2** Distinguish external listings from participating demo merchant catalog items at the data and UI layers. Only explicitly eligible catalog items expose in-app checkout. Never collect payment for a third-party listing without merchant participation and a fulfillment agreement.

**FR28 P2** Create an owner-scoped, server-priced, single-use devnet order with a unique payment reference and expiration. Show merchant wallet, network, token, exact amount, product, and demo-only fulfillment terms before the user signs. The client cannot set its own price or recipient.

**FR29 P2** Verify the on-chain transfer server-side against the stored order: network, reference, recipient, exact amount, correct token mint or native SOL, successful status, and sufficient confirmation. Reject reused signatures, wrong amounts, wrong recipients, expired orders, and transactions for another order. The order is paid only after validation.

**FR30 P2** Mint one compressed NFT receipt to the paying wallet only after a verified payment. Recover mint state after interruption and expose payment and receipt pending/confirmed/failed states separately. A click, wallet connection, unverified signature, or simulated event cannot mint a purchase receipt.

**FR31 P2** Keep personal order details private and store minimal public receipt metadata. Refund/cancellation status remains queryable; NFT possession alone is not proof of current entitlement.

**FR32 P2** Maintain distinct referral and in-app checkout economics. Referral commission requires affiliate attribution; participating merchant revenue requires a real fee/margin agreement. Devnet transfers create no realized revenue.

**FR33 P0** Include a diagnostics page with capability flags, provider mode, request counts, usage when available, failures, and non-sensitive trace IDs. It must distinguish live, cached, catalog, and fixture results.

## 8 Architecture and repository

Use React/TypeScript/Vite for the website and Python/FastAPI for the backend. This keeps the official Perceptron Python SDK easy to use and gives one shared Python shopping pipeline for web, voice tools, and Photon. A small Node/TypeScript Photon bridge is optional and must contain transport logic only.

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Web | React, TypeScript, Vite | Video/frame viewer, selection, results, text/voice controls |
| Backend | FastAPI, Pydantic v2 | Validation, sessions, authorization, tools, orchestration |
| Perception | FFmpeg/ffprobe, image processing, Perceptron adapter | Frames, crops, observations |
| Agent runtime | xAI SDK or documented HTTP API | Bounded tool-using searches |
| Product retrieval | One provider adapter, later additional adapters | Real listing discovery and detail lookup |
| Persistence | MongoDB Atlas with supported Python driver | Sessions, evidence, jobs, results, referrals |
| Media | Local files for demo; private object storage if hosted | Bytes referenced by opaque asset IDs |
| Voice | Grok realtime voice adapter | Browser audio and validated shopping-tool calls |
| Messaging | Photon bridge using one verified SDK/version | Normalize inbound messages and send replies |
| Optional checkout and receipts | Solana Pay devnet and Bubblegum adapter | Controlled merchant payment validation and cNFT receipt issuance |

Do not add a general multi-agent framework, Redis, Kafka, or a second database unless a concrete blocking need appears. A small explicit orchestrator and a Mongo-backed job collection are sufficient for this prototype. Deploy one worker process initially with a bounded concurrency semaphore.

Suggested layout:

```text
apps/web/src/
services/api/app/contracts/       # Pydantic source of truth, Claude-owned
services/api/app/routes/
services/api/app/sessions/
services/api/app/shopping/
services/api/app/providers/catalog/
services/api/app/providers/grok/
services/api/app/providers/perceptron/  # Codex-owned
services/api/app/media/                # Codex-owned
services/api/app/jobs/
services/api/app/storage/
services/api/app/receipts/         # optional, assigned later
services/api/tests/media/         # Codex-owned
services/api/tests/perception/    # Codex-owned
services/api/tests/shopping/
services/photon-bridge/           # optional isolated owner
packages/contracts/              # generated JSON Schema and TypeScript
tests/e2e/
fixtures/                        # provenance-tagged, no secrets/private media
docs/status.md
docs/decisions.md
docs/provider-access.md
docs/evaluation.md
```

Claude defines canonical Pydantic models, exports JSON Schema/OpenAPI, and generates or deliberately maintains matching TypeScript types. Contract fixtures must round-trip through both sides. Pin compatible dependency versions after actual smoke tests and commit lockfiles. No autonomous owner may change root dependencies or canonical schemas without integration-owner approval.

## 9 Media and garment extraction

Limits proposed for the demo: uploaded video <=150 MB and <=90 seconds, image <=10 MB, at most 24 sampled frames for initial analysis, and at most 12 additional frames around a chosen target. A long YouTube video requires a selected segment and a supported resolver. Never fetch an entire long video merely to inspect one jacket.

Frame sampling: sample up to 12 evenly spaced frames first; optionally add frames around scene changes or the requested timestamp up to the limit. Use decode timestamps, not assumed constant frame rate. Select clear crops with simple blur/size heuristics. Keep at most three supporting crops per selected garment.

Store image origin at top-left and boxes as normalized [xmin,ymin,xmax,ymax] in [0,1]. Require ordered, nonzero-area boxes. Retain the original coordinate system from the provider in raw diagnostics and convert once in the adapter. Apply rotation/crop/resize transforms consistently. Validate pixel crops against the displayed image before trusting detections.

Use stable IDs for observations and garment groups. The same gray jacket on two different people must not be automatically treated as one item. For P0, group within a continuous shot using spatial continuity and attribute agreement; across cuts prefer conservative duplicates. Full video-wide identity tracking is unnecessary.

Send bounded frames or crops through the documented Perceptron interface. Perceptron documents detection and grounded outputs, but extraction accuracy and deduplication must be evaluated on the team's clips. [S8] Do not assume an arbitrary YouTube page URL is a valid model video input.

Perception output must preserve visible versus inferred attributes. For example, "shiny black jacket" can be observed; "genuine leather" requires product evidence. Avoid face recognition, demographic inference, or inferred clothing size. Person references may be local labels such as person_1 within the clip.

## 10 Runtime agents and tool contracts

### Pipeline

1. Validate the selected garment and constraints.
2. Start exact-match and alternative workers concurrently.
3. Each worker chooses bounded retrieval actions and can adjust its query based on results.
4. Normalize listing records and fetch details for the strongest candidates.
5. Apply deterministic hard filters and evidence rules.
6. Rank eligible results; use the model for concise evidence-grounded explanations if needed.
7. Commit results only if the search revision is still current.

The verifier is a stage, not an unconstrained third browsing swarm. The two workers may use the same model with different instructions and isolated scratch state. They share immutable input and a request-budget ledger, not mutable conversation memory.

### Roles

**Exact-match worker:** Seek evidence for the original product. Use visible branding, distinctive garment details, creator descriptions/links when available, and catalog queries. Return likely candidates when evidence is insufficient; never promote a visual resemblance to verified identity.

**Alternative worker:** Search for the look under the user's constraints. Prefer useful stylistic similarity and clear availability information. It may expand search wording, but it may not change budget, exclusions, condition, or size requirements silently.

**Verifier/ranker:** Merge duplicates, retrieve details, detect contradictions, enforce constraints, and produce at most three primary options. If an original item violates budget, it may appear in a separate "Original found" context area, explicitly over budget, not in the qualifying recommendation set.

### Allowed tools

```text
search_catalog(query, category, country, currency, limit)
search_by_image(crop_asset_id, category, country, limit)
get_listing_details(provider, listing_id)
search_web_evidence(query, allowed_domains, limit)       # optional discovery
read_product_evidence(candidate_id)                    # verified safe fetch adapter
submit_candidates(candidate_ids, evidence_ids)
```

Tools return typed data and opaque IDs. Read-product tools accept validated candidates from retrieval, not arbitrary model-supplied URLs. Models cannot execute shell commands, submit purchases, send messages to arbitrary recipients, or mutate saved preferences directly.

The browser UI and voice tool layer additionally expose validated application actions: select_garment, update_preferences, start_search, get_results, and show_result_details. These actions require the current session revision. Retailer navigation remains an explicit user action.

### Initial budgets

Proposed configuration per selected-garment search: two concurrent workers; at most three reasoning rounds per worker; at most 12 external tool calls total across both workers and verification; at most six distinct listing-detail fetches; 60-second overall deadline. Cache hits do not consume paid-call budget but still count toward a separate execution-loop cap. Provider timeouts must fit inside the remaining overall deadline.

The backend enforces budgets atomically before dispatch. Native provider max_turns controls reasoning turns, not necessarily the total tool-call count, so it is insufficient alone. [S9] Record reasoning-call usage separately from tool-call counts. Provider-specific monetary caps are configured after access checks; cost_unknown must remain unknown.

Retry a transient read failure at most once with jitter within the original budget/deadline. Do not retry authentication failures. A tool timeout can yield partial results if other candidates were actually verified. Each search ends as completed, partial, no_match, failed, cancelled, or superseded.

### Product prompt templates

```text
EXACT MATCH
Find evidence for the original garment in the supplied crops and observations.
Use only the provided retrieval tools. Cite evidence IDs for every identity claim.
Do not infer material, size, price, stock, or exact brand from resemblance alone.
Return candidate IDs and evidence. If you cannot establish identity, say so.
Stop within the supplied remaining tool budget and deadline.
```

```text
ALTERNATIVES
Find purchasable alternatives to this selected garment under these constraints.
The user's budget, exclusions, condition, and region are hard constraints.
Unknown material or availability is not confirmation. Preserve uncertainty.
Use source-backed listings, return candidate IDs, and do not invent links.
If too few candidates qualify, return fewer rather than silently changing scope.
```

```text
RESULT EXPLANATION
Explain the already-filtered candidate set using only its verified evidence.
Separate exact identity, visual similarity, and availability. Do not add new facts.
Say what is unknown. Give one short reason per recommendation.
```

## 11 Product evidence and ranking policy

### Identity labels

| Label | Minimum basis |
| --- | --- |
| Verified match | Explicit creator product link identifying the selected garment, readable unique SKU/model tied to a listing, or human-confirmed identity with recorded evidence |
| Likely match | Strong visual and attribute agreement but no definitive identity evidence |
| Similar option | Useful resemblance or style fit without a claim of identical product |

The label is an evidence tier, not a calibrated probability. Do not display invented percentages. A creator's description containing several links is not enough unless the relevant link is associated with the selected item.

### Constraint states

For each candidate and constraint, store satisfied, violated, or unknown, plus evidence IDs. A material exclusion such as no leather is satisfied only when trustworthy product information establishes an allowed composition; a picture alone is insufficient. Unknown matches may appear in a separate "Needs checking" section but never as fully compliant recommendations.

Size is variant-specific. Store raw size labels and the sizing system when known. A user's M is not automatically a merchant's size 8. Ask for clarification or mark size unknown instead of silently converting. Stock belongs to the selected variant and region, not merely the parent product page.

Budget compares the displayed item price in the user's currency. Keep shipping and tax separate. If landed total is unavailable, say that the budget filter excludes unknown shipping/tax. Do not silently convert currencies without a sourced conversion or change currency to force a match.

### Ordering

First filter violations. Then rank eligible candidates by: identity tier for exact-search results, visual/attribute relevance for alternatives, confirmed size/availability, and price. Price is a tie-breaker, not a reason to recommend an unrelated item. Keep ranking deterministic with a recorded version. Start with explicit rules; an embedding index is not required.

Deduplicate primarily by provider and listing ID, then canonical product/variant identifiers. Different sizes, conditions, or sellers are separate offers under the same product where appropriate. Never compare used and new prices as equivalent without labeling condition.

Store listing prices/availability with checkedAt. Cache discovery for a short configurable interval, proposed ten minutes. Detail revalidation is required before claiming fresh stock; if the provider fails, retain the prior observation with its timestamp and downgrade freshness. Never invent a fresh timestamp for a cached response.

## 12 Canonical records

Implement Pydantic models with forbidden extra fields, finite-number checks, bounded arrays, and explicit nulls. The definitions below describe the logical schema; full validation lives in the backend and generated contracts.

```typescript
type EvidenceTier = "verified" | "likely" | "similar";
type CheckState = "satisfied" | "violated" | "unknown";
type ResultMode = "live" | "cached" | "catalog" | "fixture";

interface Preferences {
  country: string;                 // default US, user can change
  currency: string;                // default USD
  maxItemPriceMinor: number | null;
  size: { raw: string; system: string | null } | null;
  colors: string[];
  excludedMaterials: string[];
  condition: "new" | "used" | "any";
}

interface ShoppingSession {
  id: string;
  ownerId: string;
  revision: number;
  mediaId: string | null;
  selectedGarmentId: string | null;
  preferences: Preferences;
  activeSearchId: string | null;
  lastPresentedResultIds: string[];
  createdAt: string;
  updatedAt: string;
}

interface GarmentObservation {
  id: string;
  mediaId: string;
  frameAssetId: string;
  timestampMs: number | null;       // null for still images
  box01: [number, number, number, number];
  cropAssetId: string;
  category: "jacket" | "top" | "bag" | "other";
  personTrackId: string | null;
  observedAttributes: Record<string, string[]>;
  visibleText: string[];
  providerRequestId: string | null;
  modelId: string;
  editedByUser: boolean;
}

interface Garment {
  id: string;
  sessionId: string;
  observationIds: string[];
  representativeCropId: string;
  label: string;
  groupingBasis: "single" | "within_shot" | "user_confirmed";
}

interface Evidence {
  id: string;
  sourceType: "merchant_api" | "merchant_page" | "creator_link"
    | "search_result" | "human_verified";
  sourceUrl: string | null;
  provider: string | null;
  retrievedAt: string;
  claims: { field: string; value: unknown; excerpt: string | null }[];
  rawResponseRef: string | null;
}

interface Listing {
  id: string;                      // immutable observation snapshot ID
  offerKey: string;                // stable provider/listing/variant identity
  provider: string;
  providerListingId: string;
  productId: string | null;
  variantId: string | null;
  retailer: string;
  canonicalUrl: string;
  imageUrls: string[];
  title: string;
  brand: string | null;
  price: { amountMinor: number; currency: string } | null;
  shippingMinor: number | null;
  condition: "new" | "used" | "unknown";
  size: { raw: string; system: string | null } | null;
  availability: "in_stock" | "out_of_stock" | "unknown";
  materialText: string | null;
  colorText: string | null;
  checkedAt: string;
  evidenceIds: string[];
  mode: ResultMode;
}

interface Recommendation {
  id: string;
  searchId: string;
  garmentId: string;
  listingId: string;
  identityTier: EvidenceTier;
  identityEvidenceIds: string[];
  constraintChecks: {
    constraint: string; state: CheckState; evidenceIds: string[];
  }[];
  explanation: string;
  warnings: string[];
  rank: number;
  rankingVersion: string;
}

interface SearchJob {
  id: string;
  sessionId: string;
  sessionRevision: number;
  inputHash: string;
  status: "queued" | "running" | "completed" | "partial"
    | "no_match" | "failed" | "cancelled" | "superseded";
  preferenceSnapshot: Preferences;
  garmentId: string;
  budget: { maxToolCalls: number; usedToolCalls: number;
            maxDetailCalls: number; usedDetailCalls: number };
  deadlineAt: string;
  resultIds: string[];
  error: { code: string; message: string; retryable: boolean } | null;
}

interface ReferralEvent {
  id: string;
  sessionId: string;
  recommendationId: string;
  listingId: string;
  outboundUrl: string;
  occurredAt: string;
  affiliateConfigured: boolean;
  conversionStatus: "unknown" | "confirmed" | "reversed";
}

interface DemoMerchantOrder {
  id: string;
  ownerId: string;
  catalogItemId: string;            // controlled participating merchant inventory only
  merchantId: string;
  recipientWallet: string;
  buyerWallet: string | null;
  network: "devnet";
  assetMint: string | null;         // null for native SOL; never infer mint by symbol
  amountAtomic: string;            // integer base units, server priced
  paymentReference: string;
  expiresAt: string;
  status: "created" | "awaiting_payment" | "verifying" | "paid"
    | "expired" | "failed";
  paymentSignature: string | null;
  receiptStatus: "ineligible" | "eligible" | "minting"
    | "confirmed" | "failed" | "needs_reconciliation";
  receiptAssetId: string | null;
}
```

Money uses integer minor units and a currency code. Dates use UTC ISO 8601; display local time where helpful. IDs are server-issued opaque identifiers. Raw model/provider data is diagnostic evidence, not a replacement for validated entities. Never send keys or private provider responses to the browser.

Listing records are immutable observation snapshots. A new price/stock check creates a new snapshot under the same offerKey. Recommendations reference the snapshot they actually evaluated. Maintain a small current-offer pointer for caching, but do not mutate historical evidence or retroactively change an earlier recommendation's price. If revalidation changes compliance, create a new result revision and show the change rather than silently swapping the underlying listing.

### Frozen module interfaces

Claude must define these interfaces before Codex starts implementation. Below are logical contracts, not assumed SDK methods:

```text
MediaService.ingest(upload, owner_id)
    -> MediaAsset
MediaService.extract_frames(media_id, interval_ms, max_frames)
    -> FrameRef[] with source timestamp, image dimensions, asset ID, transform
PerceptionProvider.analyze(frame_refs, categories, request_context)
    -> GarmentObservation[] plus provider request metadata
MediaService.crop(frame_asset_id, box01)
    -> crop_asset_id with coordinate provenance
GarmentGrouper.group(observations, shot_boundaries)
    -> Garment[] with conservative grouping basis
CatalogProvider.search(query, filters, limit)
    -> normalized listing snapshots and evidence
CatalogProvider.search_image(crop_asset_id, filters, limit)
    -> normalized listing snapshots and evidence, or unsupported capability
CatalogProvider.get_details(provider_listing_id, variant_id)
    -> new listing snapshot and evidence
```

Request context includes ownership, request ID, deadline, and cancellation. Media and perception modules return data to the orchestrator and never write shopping preferences or launch retailer searches. Provider adapters normalize errors into auth_error, rate_limited, unavailable, timeout, invalid_response, or unsupported_capability. An empty valid detection/search result is distinct from an adapter failure.

Define additional MediaAsset, AnalysisJob, AgentEvent, ChannelBinding, and Receipt records before their modules begin. MediaAsset includes owner, SHA-256, MIME, dimensions, duration, source type, optional canonical source URL, and storage key. AgentEvent includes job ID, sequence number, stage, safe summary, tool name, timing, and evidence/result IDs. It must not include chain-of-thought.

## 13 State consistency and jobs

Session mutations require expectedRevision and idempotencyKey. Perform an atomic compare-and-update on the session document. Stale revisions return 409. Retrying the same key and identical content returns its existing result; a reused key with different content conflicts. The application must not apply the same voice command twice after a reconnect.

Persist a search job before dispatch. The job stores immutable preferences and selected garment. Workers claim queued jobs atomically with lease owner, lease expiry, and attempt number. Bound attempts to two; renew while working. If a worker dies, another claim can recover it without resetting its call budget. Account for external calls conservatively when their final outcome is unknown.

Use a transaction where supported for session/job activation, or an explicit compare-and-set protocol with recovery if one step fails. Do not launch paid work before the job record and current-session reference are consistent. Commit results only when job ID and session revision still match the current session. Superseded jobs retain diagnostics but cannot publish new recommendations to that session.

Progress uses server events or simple polling. Prefer polling initially; use SSE only after reconnect/replay works. Event sequence numbers make duplicate delivery harmless. The frontend renders a partial result only after it has passed the same evidence and constraint checks as final results.

## 14 UI and product behavior

Build one polished working page with a visible input area, video or frame viewer, garment tray, shopping constraints, and product cards. Use a light editorial fashion aesthetic with strong photography, restrained typography, and generous spacing. Keep the product experience focused on clothing, not infrastructure or an agent dashboard.

Each primary card shows: product image, title, retailer, sourced price/currency, match tier, size/stock status, one reason it fits, and a retailer action. Details reveal the garment crop and supporting evidence. Use "Similar option" rather than a false exact-match badge.

The agent activity area can be a short collapsible list. Show evidence of useful work, such as "Original is above your budget" or "Excluded one result containing leather," only when supported by stored facts. Avoid a swarm visualization that implies agents are working when they are idle.

Required states: empty input, uploading, unsupported link, analyzing, no garments, ambiguous selection, searching, partial results, no qualifying results, provider unavailable, expired/stale listing, and retry. Preserve selection/preferences through recoverable errors.

Show video overlays on extracted frames we control. Keep third-party embedded player controls intact. A timestamp click seeks the supported player; if only an image is supplied, do not show an invented video timestamp.

Provide keyboard navigation, visible focus, labeled inputs, text alternatives for voice, and crop-image alt text. Prevent double submissions. Opening a retailer should work even if analytics storage temporarily fails; log the failure without blocking the user's shopping action.

## 15 API surface

All public app routes use session ownership checks. Provider webhooks use their own verified authentication. A capability endpoint reports configuration without returning secrets.

| Method and route | Contract |
| --- | --- |
| GET /api/health | API, database, worker, and per-provider readiness/mode |
| POST /api/sessions | Create opaque browser session; HttpOnly cookie |
| GET /api/sessions/{id} | Authorized current state and revision |
| PATCH /api/sessions/{id} | Validated preference/selection patch with expected revision |
| POST /api/media/uploads | Stream and validate media; return asset ID |
| POST /api/media/resolve | Supported URL plus optional interval; honest resolver result |
| GET /api/media/{id} | Authorized byte access or short-lived signed URL |
| POST /api/sessions/{id}/analysis | Create media-analysis job |
| GET /api/analysis/{id} | Analysis status and garment IDs |
| PATCH /api/garments/{id} | User-confirmed crop/category correction with ownership |
| POST /api/sessions/{id}/searches | Start search from expected session revision |
| GET /api/searches/{id} | Job status, evidence-backed recommendations |
| POST /api/searches/{id}/cancel | Idempotent cancellation |
| POST /api/sessions/{id}/messages | Text turn; propose/apply validated action |
| POST /api/referrals | Validate recommendation and create tracked outbound record |
| GET /go/{token} | Resolve stored, unexpired referral target and redirect |
| POST /api/demo-orders | P2: create owner-scoped order from an eligible merchant catalog item and server-side price |
| GET /api/demo-orders/{id} | P2: authorized payment and receipt status, exact network/amount, optional explorer references |
| POST /api/demo-orders/{id}/verify | P2: server-side transfer validation; idempotent with stored signature |
| POST /api/voice/sessions | Optional voice connection; short-lived authorization |
| POST /api/channels/photon/webhook | Optional authenticated inbound message |
| POST /api/channels/link | Single-use cross-channel linking exchange |
| GET /api/receipts/{id} | Optional receipt status and devnet references |

Errors have code, message, retryable, and requestId. Use meaningful 400/401/403/404/409/413/422/429/503 responses. No endpoint accepts a client-supplied database query, arbitrary shell string, signing instruction, or unrestricted redirect URL.

## 16 Database design

Use MongoDB Atlas as the sole application database. Collections: sessions, media_assets, garment_observations, garments, offers, listings, evidence, search_jobs, agent_events, recommendations, referrals, channel_bindings, and optional demo_catalog_items/demo_orders/receipts. Offers store identity and the latest snapshot pointer; listings store immutable observations. Demo catalog eligibility is set by the server and never inferred from an external listing URL.

Required indexes: owner/session lookup; unique provider+providerListingId+variant identity on offers with an explicit null strategy; listings(offerKey, checkedAt); search_jobs(status, leaseExpiresAt); agent_events(jobId, sequence); unique idempotency key within operation scope; unique channel provider+conversation identifier; unique payment reference and payment signature; unique order ID on receipt eligibility. Payment signatures are claimed atomically before marking an order paid.

Keep images/video in file/object storage, not large embedded database documents. Keep media permissions tied to owner IDs. Apply a configurable retention policy to raw uploads and provider traces; deletion must remove access to related private assets. Do not rely solely on asynchronous TTL cleanup for authorization.

MongoDB Vector Search is a later enhancement for an indexed catalog. It requires compatible generated embeddings and an index; it is not automatic product recognition or access to a global catalog. [S10] Use ordinary queries and explicit ranking first. Tiger Data is excluded from this implementation to avoid two persistence systems; reconsider it only if price-history monitoring becomes a primary feature.

## 17 Voice and Photon integration

### Voice

Use a documented Grok voice connection after a real smoke test. Keep permanent API keys on the backend; use a supported server relay or short-lived client credentials. Grok documents realtime voice and browser authentication, but the actual integration must be tested on the demo browser. [S11]

Start with push-to-talk rather than always-on listening. Show the transcript and selected garment. "That one" must resolve against the active garment/result context; otherwise ask a short clarification. Read prices and stock only from current validated result records. Never let the voice model invent or navigate to a product URL from memory.

If a voice turn is interrupted, discard unfinished actions and deduplicate any completed tool call by turn ID. For uncertain constraint extraction, show a compact confirmation before starting a paid search. Background audio from the video must not accidentally become a shopper command; pause playback during capture where appropriate.

### Photon

Choose one Photon package/transport and pin it. Its official integrations support messaging channels, but mix-and-match snippets from different Photon SDKs can have incompatible contracts. [S12] Verify provisioning, attachment access, webhook authentication, and outbound reply before building the shopping bridge.

Normalize inbound data to channel, providerMessageId, conversationId, senderBinding, text, attachment references, and receivedAt. Authenticate the event before resolving media. Download attachments only through supported authenticated paths with normal media limits. Deduplicate events before creating jobs or sending replies.

Keep a channel-scoped lastPresentedResultIds list. An ordinal such as "second one" refers to that list, not to a freshly reordered search. Group-chat support is deferred; use a direct conversation for the demo. Only explicitly linked identities share state between web and iMessage. Send one concise result message rather than a stream of every internal agent event.

## 18 Optional Solana checkout and receipt

This extension starts only after the complete shopping flow works. It is a second completion path for one controlled participating demo merchant product, not a way to charge for unrelated retailers' inventory. Use Solana **devnet** and clearly label the test funds, demo merchant, lack of real fulfillment, and receipt. External retailer navigation never requires a wallet. Do not deploy a real-money payment path without merchant, fulfillment, support, and legal arrangements.

The backend creates a fixed-price order and unique reference. The wallet approves a transfer to the configured merchant wallet. Validate the confirmed on-chain payment server-side against order reference, recipient, amount, network, asset/mint, success status, and expiration. Use an idempotent transition from awaiting payment to paid; never trust the client callback as proof. Solana Pay documents transfer requests and reference validation. [S15]

Once payment is verified, a server-paid mint issues a compressed NFT to the payer wallet. Use an official Bubblegum V2 path with a configured tree and required RPC/indexing support. Tree setup, funding, retrieval, and wallet handling are separate integration tasks. [S13] A custom on-chain program is unnecessary for the demo. The receipt establishes that our system issued an asset for a verified **devnet demo order**. It does not establish shipment, a purchase at an outside retailer, or an earned affiliate commission.

Payment states: created, awaiting_payment, verifying, paid, expired, failed. Receipt states: ineligible, eligible, minting, confirmed, failed, needs_reconciliation. Persist the order ID, payment signature, receipt asset intent, mint signature when available, and attempt state before submission. On an uncertain network outcome, reconcile the original transaction/asset before preparing a new mint. Never blindly remint after a timeout. A unique order database key alone does not guarantee exactly-once on-chain issuance.

Store only an opaque receipt ID and minimal issuer/network metadata publicly. Private order data stays off-chain. If committing to private data, use a randomized commitment rather than an unsalted hash of a guessable order number. Public metadata URLs must not expose names, addresses, emails, or order details. Refunded/cancelled orders update a queryable off-chain status; do not imply immutable metadata automatically reverses a purchase.

The wardrobe references the demo catalog item and verified devnet order. It can help a later search, but it must distinguish a saved wish-list item from a verified devnet test purchase and from a future real-world purchase.

## 19 Referral economics and measurement

Track both funnels separately: media analyzed, garment selected, search completed, product detail opened, outbound referral, affiliate conversion, commission confirmed; and eligible catalog item selected, demo order created, devnet payment verified, receipt minted. Do not infer later events from earlier ones.

Affiliate revenue requires an approved merchant/network relationship and successful attribution under that relationship. A provider returning product URLs does not itself authorize affiliate tracking or establish a payout. Store affiliateConfigured and attribution provider explicitly. Normal non-affiliate links remain useful for the demo. In-app merchant checkout is a separate potential revenue model based on a negotiated transaction fee or merchandise margin. A devnet transfer is demonstration activity, not sales or revenue.

Measure first-result latency, full-search latency, external calls per request, source coverage, fraction of requests with compliant recommendations, click-through events, and exact-match false positives. Revenue is unknown until actual conversion/commission reporting exists. Avoid fabricated dashboards and extrapolated sales metrics in the pitch.

## 20 Security and operational requirements

These requirements address concrete inputs and integrations in this build; implement them as part of those features.

- Validate uploads and sandbox/bound media decoding. Enforce timeouts and resource limits.
- URL resolution and evidence fetching must prevent requests to loopback, private/internal networks, metadata services, and unsupported schemes, including after redirects and DNS resolution. Prefer allowlisted provider APIs over arbitrary fetching.
- Treat product pages, transcripts, captions, and model output as data. Embedded instructions cannot alter tool permissions, ranking policy, credentials, or session ownership.
- Keep provider keys server-side; keep browser cookies HttpOnly, Secure when served over HTTPS, and protected against cross-site mutation. Restrict CORS to the intended origin.
- Protect exposed demos with basic access/session controls and rate limits. Do not publish a shared-key unlimited-cost endpoint.
- Preserve distinct user/channel ownership. A received message cannot select another person's session or receipt by supplying an ID.
- Store logs with trace IDs and short safe summaries; redact credentials and personal order information.
- Server-side redirects use stored validated targets. Affiliate redirect chains must have an approved provider path; never turn /go into an open redirect.
- Use devnet for the receipt demo. Keep signing keys isolated from models and never expose seed phrases in prompts or logs.

## 21 Performance and reliability targets

These are proposed engineering targets to measure, not claims of achieved performance.

| Metric | Target on declared demo environment |
| --- | --- |
| Image selection UI | Immediate local preview after upload acceptance |
| Garment analysis | First usable observations within 20 seconds for a small input |
| Shopping search | Useful verified results within 30 seconds when providers cooperate; hard deadline 60 seconds |
| Refinement | Reuse valid cached evidence where possible; never present stale data as freshly checked |
| Web interaction | No blocking UI while analysis/search runs; cancel/retry available |
| External usage | Enforced tool budget and bounded reasoning rounds per job |
| Restart recovery | Queued work resumes or interrupted work is explicitly failed/reconciled |
| Duplicate inbound event | At most one logical search and one final reply for the event |

Record provider/model versions, input size, cache mode, elapsed times, and failures. A provider outage should produce an honest partial/failed state and leave the rest of the interface usable. Cached demo mode must be visibly labeled.

## 22 Acceptance and evaluation

Build a small truth set of at least eight examples: a creator-linked exact item, an unbranded garment, similar-looking different brands, multiple people wearing similar colors, an out-of-stock item, a material-exclusion case, a missing size case, and a failed/unsupported video URL. Record source permissions and how identity/attributes were checked. Use licensed or team-provided media and real listing evidence.

Do not require every example to return a match. A correct no-match or uncertain result is preferable to a false verified match. Evaluate on at least two clips/images not used while tuning prompts.

| ID | Pass condition |
| --- | --- |
| AT01 | Uploaded real video decodes into correctly timed frames and displays garment observations |
| AT02 | Rotated/resized image boxes crop the intended garment; invalid coordinates are rejected |
| AT03 | Real Perceptron call produces displayed evidence tied to its actual frame and request ID |
| AT04 | Similar garments on separate people are not silently merged into one exact identity |
| AT05 | Selected garment alone triggers shopping; changing selection supersedes the old job |
| AT06 | Both Grok search workers perform actual bounded tool calls and retain source evidence |
| AT07 | A failed exact search causes a useful alternatives attempt without changing hard constraints |
| AT08 | Verified-match labels require the specified evidence; visual resemblance alone never qualifies |
| AT09 | Over-budget, wrong-condition, and explicit excluded-material candidates are filtered correctly |
| AT10 | Missing size/material/stock data is shown as unknown, not silently treated as compliant |
| AT11 | A text revision preserves unspecified preferences and does not duplicate work on retry |
| AT12 | Late results from a superseded job cannot replace current results |
| AT13 | Duplicate candidate listings merge without losing variant/condition distinctions |
| AT14 | Each displayed price and retailer URL resolves to recorded source evidence and timestamp |
| AT15 | Retailer click opens the intended stored target; an arbitrary redirect URL is rejected |
| AT16 | Page reload restores the committed session from Atlas; another session cannot read it |
| AT17 | Tool/time budgets terminate excessive loops, including parallel workers and retries |
| AT18 | Invalid keys, rate limits, provider timeout, and no-result cases produce truthful UI states |
| AT19 | At least eight truth-set examples and two held-out examples have recorded outcomes |
| AT20 | Voice correction changes the right constraint and text remains usable after voice failure |
| AT21 | Photon receives a real message and replies with real shopping results in the same conversation |
| AT22 | Replayed Photon event does not create a second search/reply; cross-user linking is blocked |
| AT23 | Controlled demo item creates a fixed-price devnet order; wallet payment is verified on the server against reference, recipient, exact amount, asset/mint, success, and confirmation before order becomes paid |
| AT24 | External retailer listing cannot enter in-app checkout; a click, wallet connection, client callback, wrong payment, or reused signature cannot mint a receipt |
| AT25 | Every claimed live feature can be demonstrated without silently substituting a fixture |
| AT26 | Verified devnet payment yields one buyer-wallet compressed NFT receipt; uncertain mint result is reconciled without blindly reminting |
| AT27 | Demo order and receipt show devnet/test status; a payment never claims shipment or an earned affiliate commission |

AT01-AT19 and AT25 cover the core. AT20-AT24 and AT26-AT27 apply only to claimed extensions and must be marked deferred rather than passed when absent. Automate geometry conversion, constraint filtering, schema validation, concurrency/idempotency, ownership, redirect and payment-validation boundary tests. Use a small number of real integration checks for providers and human visual review for match quality. Do not run costly live APIs for every unit test.

## 23 Build schedule and stop rules

All times are local Pacific time on October 17-18, 2026, subject to confirmed event rules. Assume coding starts at 12:30 PM Saturday. Do not consume the full night adding integrations; reserve final hours for evidence and a reliable demo.

| Time | Claude and Ashwin | Codex | Teammate and Grok |
| --- | --- | --- | --- |
| Before allowed start | Read spec; confirm rules, access, and ownership | Read assigned module contract | Confirm provider access and prepare a source list |
| 12:30-1:15 PM | Bootstrap repo, contracts, Atlas, basic UI | Wait for contract freeze; inspect frame/perception interfaces | Prove one real product-search call and Photon connection availability |
| 1:15-3:00 PM | End-to-end session -> listing -> retailer skeleton using labeled fixtures | Real upload/frame/crop/Perceptron module | Build truth set and document real listing evidence |
| 3:00-5:30 PM | Integrate actual detection and one real catalog; Grok tools | Fix perception integration defects and geometry tests | Test unfamiliar examples and verify match labels |
| 5:30-7:30 PM | Two search workers, filtering, revisions, persistence | Independent core review after module merge | Validate product/provider coverage; isolated Photon bridge if ready |
| 7:30 PM gate | Core must work with real data | Fix bounded defects | Run end-to-end acceptance cases |
| 7:30-9:30 PM | Voice or Photon integration, whichever is ready | Assigned narrow reliability fix | Complete message round-trip and help test voice |
| 9:30-10:15 PM | Draft submission and core demo recording | Verify clean-start instructions | Track declarations, screenshots, evidence |
| By 10:30 PM | Submit required draft | No dependency on late feature completion | Confirm both teammates and tracks are included |
| 10:30 PM-1:00 AM | One optional extension only if core is stable | Receipt/reliability task only if explicitly assigned | Solana test flow or focused user testing |
| Overnight | Freeze architecture; bounded bug fixes and human rest shifts | No unsolicited refactor | Rehearse and preserve working version |
| Sunday 7:00-8:30 AM | Full regression and fresh live run | Review concrete failures | Verify product links and record backup demo |
| 8:30-9:30 AM | Final presentation and submission content | Stop feature work | Final evidence and upload checks |
| Before 10:00 AM | Submit final | Preserve release commit | Confirm submission receipt |

If the team starts late, compress scope rather than remove the final verification window. If the catalog API is blocked after a 45-minute targeted attempt, switch to a sourced limited catalog and label it. If YouTube ingestion is blocked, use uploads immediately. If core shopping is not working by 7:30 PM, defer voice/Photon/receipts until it is.

At most two repository-writing agents run concurrently. Do not use all available subscriptions simply to maximize activity. Additional sessions should have read-only research/review assignments unless they own an isolated module and a frozen contract.

## 24 Work tickets and ownership

| Ticket | Owner | Deliverable | Dependency |
| --- | --- | --- | --- |
| T01 Contracts and bootstrap | Claude | Models, generated client types, repo setup, config, health | None |
| T02 Media and perception | Codex | Frames, crops, observations, adapter, tests | T01 |
| T03 Catalog access and examples | Teammate | Working provider proof, evidence fixtures, access notes | Credentials |
| T04 Session and UI skeleton | Claude | Upload/selection/results flow and Atlas persistence | T01 |
| T05 Retrieval and verification | Claude | Catalog adapter, candidate normalization, deterministic rules | T03 |
| T06 Grok worker orchestration | Claude | Two bounded workers, shared budget, events, cancellation | T05 |
| T07 Retailer routing | Claude | Stored-target redirects and referral events | T04, T05 |
| T08 Core acceptance review | Codex and teammate | Specific defects with reproduction and evidence | T02-T07 |
| T09 Voice | Claude | One real voice refinement through shared pipeline | Core gate |
| T10 Photon bridge | Teammate with available tools, or Claude | Verified message -> backend -> same-conversation reply | Core gate, access proof |
| T11 Demo checkout and receipt | Explicitly assigned later | Controlled catalog item -> devnet payment -> server verification -> buyer-wallet cNFT -> reconciliation proof | Core gate, time remaining |
| T12 Release and submission | Ashwin | Working commit, video, evidence, track declarations | Core acceptance |

Each ticket ends with changed paths, exact commit, test commands/results, known limitations, required environment variables, and one integration example. A successful compile is not sufficient evidence for a provider integration.

## 25 Repository coordination and subscription usage

Claude owns main integration. Codex works on feat/perception in a separate worktree or checkout from the agreed base commit. The teammate's optional code lives on feat/photon. Use the same remote repository and exchange commits/PRs, not pasted copies of large files.

Claude alone modifies app/contracts, generated contracts, root dependency files, environment templates, and shared routes unless ownership is explicitly transferred. Codex may request an interface change in docs/status.md; it must not silently fork the schema. Merge the perception module early, before building more features around a temporary mock.

Each task handoff records:

```text
Task and owner:
Base commit and branch:
Allowed paths:
Forbidden/shared paths:
Input/output contract:
Acceptance checks:
Known dependency or credential blocker:
Latest tested commit:
Next integration step:
```

Keep docs/status.md short: current working flow, active owners, latest good commit, failing tests, known blockers, and next task. Keep docs/decisions.md for provider/version/schema decisions. Before a context reset, require a checkpoint with these facts. Do not ask a fresh model to rediscover the whole project.

Use Grok sessions for bounded questions with verifiable outputs: provider setup details, current listing evidence, adversarial test cases, and prompt improvements. Their output must cite the relevant source and acknowledge failed access. Do not ask multiple models to independently build the whole application and then attempt a last-minute merge.

If Claude reaches a usage limit, preserve its branch and stop other writers before transferring integration ownership to Codex. Give Codex the status file, decision log, base commit, and failing gate. Resume Claude later only after assigning a new bounded role. Check whether authentication uses the intended subscription or an API key; do not accidentally switch billing modes. [S1]

## 26 Prompts to start the work

### Main Claude Code session

```text
You are the lead implementer and sole integration owner for this project.
Read Video_Shopping_Agent_System_Requirements.md and all applicable repository
instructions. This is the fashion-shopping pivot; do not build the old Afterspace
VFX product. Inspect the existing repository before creating or replacing files.

Own the frontend, backend, canonical contracts, Atlas persistence, shopping
orchestration, ranking, and retailer routing. Codex owns media/frame extraction
and the Perceptron adapter in the explicitly assigned directories. A teammate
owns provider evidence and may own an isolated Photon bridge. Do not edit their
active work without a documented ownership transfer.

First establish canonical Pydantic contracts and fixtures, then give Codex a
small frozen adapter contract. Build a thin vertical path from one real garment
to a real listing and retailer link. Fixtures may support development but must
remain labeled and must not masquerade as live integrations.

Implement P0 before optional channels. Use MongoDB Atlas as the only database.
Use supported runtime APIs; do not assume consumer subscriptions pay for API
calls. Verify actual credentials, models, tool interfaces, and provider access.
No autonomous purchasing, public unlimited-cost endpoints, or new paid services.

Every recommendation must preserve evidence, uncertainty, source URL, timestamp,
variant/size status, and constraints. Enforce budgets and session revisions in
code. Do not rely on model instructions alone for correctness.

Work in small tested commits and keep docs/status.md current. At each gate,
report what works with live data, what is blocked, and the next dependency.
Deliver a reproducible local run guide, .env.example, measured acceptance matrix,
and a real demonstration flow. Use the schedule and cut rules in the spec.
```

### Codex implementation session

```text
Read Video_Shopping_Agent_System_Requirements.md and applicable repo instructions.
Your ticket is T02: media/frame extraction, crop geometry, conservative garment
grouping, and the Perceptron provider adapter. Claude is integration owner.

Work from the agreed base commit in an isolated branch/worktree. Own only
services/api/app/media, services/api/app/providers/perceptron, and their assigned
tests. Use the canonical contracts supplied by Claude; request changes rather
than editing shared schemas, app routes, frontend, or root dependencies silently.

Prove one real uploaded clip can become correctly timed frames and useful garment
observations through the actual Perceptron API. Handle image orientation and
coordinate normalization explicitly. Provide a manual crop fallback and honest
unavailable states. Do not invent brands, material composition, sizes, depth,
model confidence, or successful provider responses.

Test rotated/resized images, invalid boxes, repeated garments, multiple people,
provider failure, and media limits. Return your commit, changed paths, dependency
requests, example inputs/outputs, test evidence, and known limitations. After
merge, wait for a new bounded review/fix assignment rather than expanding scope.
```

### Teammate and Grok research session

```text
Read the product scope and your ownership in the requirements document. Your
first priority is proving product-data access and preparing credible test cases.
Find one provider we can actually call today that returns product listings,
images, sourced prices, and retailer URLs. Verify access before recommending an
implementation. Record limitations, credentials needed, and one real example.

Prepare eight fashion examples covering exact, ambiguous, missing-size,
out-of-stock, excluded-material, and no-match cases. Record source evidence and
whether an exact identity is genuinely known. Do not invent product URLs or
availability. Use team-owned or appropriately licensed media.

Separately verify Photon provisioning and one inbound/outbound test message.
If access works, document the exact SDK/version/transport and ask the integration
owner for the channel contract before writing the optional bridge. Do not modify
shared backend contracts or create a second shopping engine.

Deliver docs/provider-access.md and docs/evaluation.md with concise evidence,
working examples, failed attempts, and recommendations. During integration,
test the real product on unfamiliar examples and report reproducible defects.
```

### Cursor repair session

```text
You are fixing one assigned defect in an existing implementation. Read the
current status, ownership map, and relevant requirement. Reproduce the defect,
make the smallest correct change inside the permitted paths, and verify the
affected behavior. Do not refactor the architecture, change shared contracts,
replace the database, or add features. Report the diff and evidence to the
integration owner before another agent resumes writing those files.
```

### Final independent review

```text
Review the release commit against the P0 requirements and acceptance matrix.
Do not implement features during the review. Focus on false exact matches,
fabricated prices/availability, constraint loss, stale job results, cross-session
access, duplicate requests, unsafe redirects, and undisclosed fixtures. Check
that one real media input reaches a real retailer listing from a clean start.
For each issue, provide severity, reproduction, relevant file, and the smallest
suggested fix. Distinguish failed, untested, and deferred requirements.
```

## 27 Sponsor strategy and demo narrative

Target Visa as the main track, Perceptron and SideShift as clear sponsored side tracks, and Photon as the third only after verifying its exact event brief and completing a real messaging integration. MongoDB Atlas and Solana are listed MLH prize categories. Confirm whether those entries count toward the event's sponsored-side-track limit before submitting. [S5, S14]

Do not claim SpaceXAI eligibility merely for using Cursor/Grok. The supplied prompt includes a real-space-data requirement. Do not add an unrelated space feature to this product to force a fit. Tiger Data is a valid listed category but is not used in this architecture. Avoid claiming a prize integration for a database or model that only appears in a diagram.

Suggested three-minute story:

1. A shopper sees a jacket in a video and wants it under a budget.
2. Perceptron extracts the garment; the app visibly selects the right item.
3. Grok workers find the original and alternatives; the original is over budget or unavailable.
4. Evidence-backed alternatives appear, with uncertain details labeled.
5. The shopper changes a preference by text or voice and results update without losing context.
6. A real retailer link opens. If implemented, show the same request in iMessage.
7. If implemented, select a clearly labeled participating demo item, pay on devnet with a wallet, verify the order, and show the compressed NFT receipt in the wardrobe. Explain that retailer inventory still uses the retailer's checkout.

Demonstrate one fresh live input in addition to a prepared example if stable. Have a recorded backup labeled recorded. Do not fabricate latency, revenue, user counts, or model superiority. The product's differentiation is persistent shopping context, grounded retrieval, and useful follow-up actions.

## 28 Release deliverables and completion standard

Required: repository with lockfiles; environment template; setup/run guide; actual provider access notes; canonical contracts; source-tagged fixtures; eight-case evaluation; acceptance matrix with pass/fail/deferred/untested; a working release commit; and a demo recording with truthful live/cached/test labels.

The core is complete only when a new real uploaded image/video can produce genuine Perceptron observations, bounded Grok-backed retrieval, evidence-based filtered recommendations, and a working retailer redirect, with Atlas persistence and ownership checks. If a dependency is unavailable, report the reduced scope rather than marking it complete.

Voice, Photon, and Solana have separate completion gates. No incomplete extension should break the core. Leave feature flags off until each gate passes. Final submission includes only integrations that were actually demonstrated, plus explicitly labeled future plans.

## 29 Sources and interpretation

Checked October 17, 2026. The architecture, limits, staffing split, and timeboxes are engineering recommendations to validate. These sources establish documented capabilities and event information, not account-specific access, achieved quality, or guaranteed commercial results.

- **S1** Claude Help Center, Use Claude Code with your Pro or Max plan. https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan
- **S2** OpenAI official Codex pricing documentation, redirected to ChatGPT Learn. https://developers.openai.com/codex/pricing/ and https://learn.chatgpt.com/docs/pricing
- **S3** Cursor documentation, Legacy Cursor plans and account-plan differences. https://cursor.com/docs/account/pricing/legacy-cursor-plans
- **S4** xAI, Grok Bot overview. https://docs.x.ai/grok-bot/overview
- **S5** DubHacks 2026 Devpost, requirements and track list; Dubhacks (1).pdf supplied by Ashwin, pages 1-4. https://dubhacks-2026.devpost.com/ and https://dubhacks-2026.devpost.com/project-gallery
- **S6** eBay, Get Started on a Buying Application and Browse API. https://developer.ebay.com/develop/get-started/get-started-on-a-buying-application and https://www.developer.ebay.com/develop/api/buy
- **S7** YouTube IFrame Player API Reference. https://developers.google.com/youtube/iframe_api_reference
- **S8** Perceptron official Python SDK. https://github.com/perceptron-ai-inc/perceptron
- **S9** xAI, Advanced Usage and Tool Usage Details. https://docs.x.ai/developers/tools/advanced-usage and https://docs.x.ai/developers/tools/tool-usage-details
- **S10** MongoDB Vector Search documentation. https://www.mongodb.com/docs/vector-search/
- **S11** xAI, Speech to Speech. https://docs.x.ai/developers/model-capabilities/audio/speech-to-speech
- **S12** Photon official iMessage adapter and package guidance. https://github.com/photon-hq/vercel-chat-adapter-imessage and https://github.com/photon-hq/skills/blob/main/skills/imessage/SKILL.md
- **S13** Metaplex, Minting Compressed NFTs with Bubblegum V2. https://www.metaplex.com/docs/smart-contracts/bubblegum-v2/mint-cnfts
- **S14** Major League Hacking, DubHacks prize categories. https://www.mlh.com/events/dubhacks-97
- **S15** Solana, Solana Pay Transfer Requests and payment validation. https://solana.com/docs/tools/solana-pay/quickstart/transfer-requests
