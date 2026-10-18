/* Generated from packages/contracts/clipcart.schema.json by npm run gen:types. Do not edit. */

export interface ClipCartContracts {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "AgentEvent".
 */
export interface AgentEvent {
  at: string;
  elapsedMs?: number | null;
  evidenceIds?: string[];
  id: string;
  jobId: string;
  resultIds?: string[];
  sequence: number;
  stage:
    | "locating_garment"
    | "searching_original"
    | "searching_alternatives"
    | "verifying_listings"
    | "ranking"
    | "completed"
    | "partial"
    | "no_match"
    | "failed"
    | "superseded";
  summary: string;
  toolName?: string | null;
  worker?: "exact" | "alternatives" | "verifier" | "system";
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "AnalysisJob".
 */
export interface AnalysisJob {
  createdAt: string;
  detectionMode: "live" | "unverified" | "fixture" | "unavailable";
  finishedAt?: string | null;
  frameIds?: string[];
  garmentIds?: string[];
  id: string;
  issues?: {}[];
  mediaId: string;
  message?: string | null;
  ownerId: string;
  sessionId: string;
  shotBoundariesMs?: number[];
  status: "queued" | "running" | "completed" | "partial" | "detection_unavailable" | "failed";
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "ApiError".
 */
export interface ApiError {
  code: string;
  message: string;
  requestId: string;
  retryable: boolean;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "ConstraintCheck".
 */
export interface ConstraintCheck {
  constraint: string;
  detail: string;
  evidenceIds?: string[];
  state: "satisfied" | "violated" | "unknown";
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "Evidence".
 */
export interface Evidence {
  claims: EvidenceClaim[];
  id: string;
  provider: string | null;
  rawResponseRef: string | null;
  retrievedAt: string;
  sourceType: "merchant_api" | "merchant_page" | "creator_link" | "search_result" | "human_verified";
  sourceUrl: string | null;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "EvidenceClaim".
 */
export interface EvidenceClaim {
  excerpt?: string | null;
  field: string;
  value?: {
    [k: string]: unknown;
  };
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "FrameRef".
 */
export interface FrameRef {
  assetId: string;
  height: number;
  index: number;
  mediaId: string;
  ptsSeconds: number | null;
  sharpness: number;
  timestampMs: number | null;
  transform: FrameTransform;
  width: number;
}
/**
 * How a stored frame's pixels relate to the original coded media pixels.
 *
 * Pipeline: coded pixels -> orientation (EXIF orientation 1..8 or video
 * display rotation) -> oriented pixels -> uniform resize -> stored frame.
 * The resize is uniform with no padding or cropping, so a normalized box in
 * the stored frame is the same normalized box in the oriented source.
 *
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "FrameTransform".
 */
export interface FrameTransform {
  exifOrientation: number;
  orientedHeight: number;
  orientedWidth: number;
  outputHeight: number;
  outputWidth: number;
  rotationDegrees: number;
  scale: number;
  sourceHeight: number;
  sourceWidth: number;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "Garment".
 */
export interface Garment {
  groupingBasis: "single" | "within_shot" | "user_confirmed";
  id: string;
  label: string;
  /**
   * @minItems 1
   */
  observationIds: [string, ...string[]];
  representativeCropId: string;
  sessionId: string;
  userDescription?: string | null;
}
/**
 * Mirrors SRS ``GarmentObservation`` plus explicit provenance fields.
 *
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "GarmentObservation".
 */
export interface GarmentObservation {
  /**
   * @minItems 4
   * @maxItems 4
   */
  box01: [unknown, unknown, unknown, unknown];
  category: "jacket" | "top" | "pants" | "bag" | "watch" | "necklace" | "bracelet" | "ring" | "earrings" | "other";
  cropAssetId: string;
  editedByUser: boolean;
  frameAssetId: string;
  id: string;
  mediaId: string;
  modelGeneratedFields?: string[];
  modelId: string;
  observedAttributes: {
    [k: string]: string[];
  };
  personTrackId: string | null;
  providerRequestId: string | null;
  rawLabel?: string | null;
  timestampMs: number | null;
  userCorrectedFields?: string[];
  visibleText: string[];
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "JobError".
 */
export interface JobError {
  code: string;
  message: string;
  retryable: boolean;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "Listing".
 */
export interface Listing {
  availability: "in_stock" | "out_of_stock" | "unknown";
  brand: string | null;
  canonicalUrl: string;
  checkedAt: string;
  colorText: string | null;
  condition: "new" | "used" | "unknown";
  detailChecked: boolean;
  evidenceIds: string[];
  hiddenStoreCount?: number | null;
  id: string;
  imageUrls: string[];
  materialText: string | null;
  mode: "live" | "cached" | "catalog" | "fixture";
  offerKey: string;
  price: Money | null;
  priceBasis: "seller_offer" | "aggregate_lowest" | "unknown";
  productId: string | null;
  provider: string;
  providerListingId: string;
  retailer: string;
  sellerVisibility: "named" | "hidden" | "unknown";
  shippingMinor: number | null;
  size: SizePref | null;
  sizesInStock: SizeStock[] | null;
  sourceKind: "aggregator" | "retailer" | "marketplace" | "demo_catalog";
  storeOffers?: StoreOffer[];
  storesCarrying?: number | null;
  styleCode?: string | null;
  title: string;
  variantId: string | null;
  warnings?: string[];
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "Money".
 */
export interface Money {
  amountMinor: number;
  currency: string;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "SizePref".
 */
export interface SizePref {
  raw: string;
  system?: string | null;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "SizeStock".
 */
export interface SizeStock {
  lowestPrice: Money | null;
  raw: string;
}
/**
 * A retailer the aggregator names. Its price is often not disclosed.
 *
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "StoreOffer".
 */
export interface StoreOffer {
  price: Money | null;
  retailer: string;
  sizesInStock?: string[];
  url: string | null;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "MediaAsset".
 */
export interface MediaAsset {
  byteSize: number;
  canonicalSourceUrl?: string | null;
  createdAt: string;
  durationMs: number | null;
  exifOrientation?: number;
  height: number;
  id: string;
  kind: "image" | "video";
  mime: "image/jpeg" | "image/png" | "video/mp4" | "video/quicktime";
  ownerId: string;
  rotationDegrees?: number;
  sha256: string;
  sourceTitle?: string | null;
  sourceType: "upload_image" | "upload_video" | "youtube_download" | "browser_capture";
  storageKey: string;
  width: number;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "MemoryEvidence".
 */
export interface MemoryEvidence {
  at: string;
  eventId: string;
  excerpt?: string | null;
  type: string;
}
/**
 * Offers ClipCart treats as the same product, for price comparison.
 *
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "OfferGroup".
 */
export interface OfferGroup {
  basis: string;
  equivalence: "identifier_match" | "approximate" | "single";
  id: string;
  isLowestConfirmed: boolean;
  lowestConfirmedPrice: Money | null;
  offerCount: number;
  uncertainPriceCount: number;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "OutboundLink".
 */
export interface OutboundLink {
  kind: "aggregator_product_page" | "retailer_product_page";
  label: string;
  priceNote: string;
  retailer: string;
  token: string;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "OwnedItem".
 */
export interface OwnedItem {
  at: string;
  brand: string | null;
  source: "user_confirmed_purchase" | "verified_order";
  title: string;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "PageEvidence".
 */
export interface PageEvidence {
  excerpt: string;
  field: "title" | "price" | "availability" | "size" | "condition" | "brand" | "identifier" | "image";
}
/**
 * Partial update. Only fields present in the request are applied (FR14).
 *
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "PreferencePatch".
 */
export interface PreferencePatch {
  colors?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | null;
  condition?: ("new" | "used" | "any") | null;
  country?: string | null;
  currency?: string | null;
  excludedMaterials?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string]
    | null;
  maxItemPriceMinor?: number | null;
  ringSize?: SizePref | null;
  size?: SizePref | null;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "Preferences".
 */
export interface Preferences {
  /**
   * @maxItems 6
   */
  colors?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string];
  condition?: "new" | "used" | "any";
  country?: string;
  currency?: string;
  /**
   * @maxItems 8
   */
  excludedMaterials?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string]
    | [string, string, string, string, string, string]
    | [string, string, string, string, string, string, string]
    | [string, string, string, string, string, string, string, string];
  maxItemPriceMinor?: number | null;
  ringSize?: SizePref | null;
  size?: SizePref | null;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "ProductIdentifiers".
 */
export interface ProductIdentifiers {
  catalogRef?: string | null;
  gtin?: string | null;
  mpn?: string | null;
  sku?: string | null;
  styleCode?: string | null;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "ProfileEntry".
 */
export interface ProfileEntry {
  confidence?: number | null;
  evidenceCount?: number | null;
  memoryId: string;
  origin: "stated" | "inferred";
  source?: string | null;
  value: unknown;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "Recommendation".
 */
export interface Recommendation {
  constraintChecks: ConstraintCheck[];
  explanation: string;
  foundBy: ("exact" | "alternatives")[];
  garmentId: string;
  id: string;
  identityEvidenceIds: string[];
  identityTier: "verified" | "likely" | "similar";
  links: OutboundLink[];
  listingId: string;
  personalization?: string[];
  rank: number;
  rankingVersion: string;
  searchId: string;
  section: "primary" | "needs_checking" | "original_over_budget";
  warnings: string[];
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "ReferralEvent".
 */
export interface ReferralEvent {
  affiliateConfigured?: boolean;
  conversionStatus?: "unknown" | "confirmed" | "reversed";
  id: string;
  linkKind: "aggregator_product_page" | "retailer_product_page";
  linkToken: string;
  listingId: string;
  occurredAt: string;
  outboundUrl: string;
  recommendationId: string;
  sessionId: string;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "RejectedItem".
 */
export interface RejectedItem {
  domain?: string | null;
  index: number;
  reason: string;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "ResearchGarmentContext".
 */
export interface ResearchGarmentContext {
  category: string;
  colors?: string[];
  cropAssetId?: string | null;
  cut?: string[];
  description?: string | null;
  details?: string[];
  garmentId: string;
  garmentSource: "media" | "gemini_youtube";
  pattern?: string[];
  timestampMs?: number | null;
  visibleText?: string[];
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "ResearchJob".
 */
export interface ResearchJob {
  agentNotes?: string | null;
  createdAt: string;
  error?: {} | null;
  expiresAt: string;
  finishedAt?: string | null;
  garment: ResearchGarmentContext;
  id: string;
  mode: "live" | "fixture" | "manual";
  preferences: Preferences;
  products?: ResearchProduct[];
  provider: "fixture" | "solescout" | "manual" | "grok_bot";
  rejected?: RejectedItem[];
  resultSource?: "provider" | "manual_import";
  sessionId: string;
  status: "pending" | "completed" | "failed" | "expired";
  styleHints?: StyleHints | null;
  summary?: string | null;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "ResearchProduct".
 */
export interface ResearchProduct {
  availability: "in_stock" | "out_of_stock" | "unknown";
  brand?: string | null;
  brandBasis?: ("page_text" | "catalog_record") | null;
  condition?: "new" | "used" | "unknown";
  constraintChecks: ConstraintCheck[];
  domain: string;
  evidence?: PageEvidence[];
  id: string;
  identityTier: "likely" | "similar";
  imageUrl?: string | null;
  jobId: string;
  links: OutboundLink[];
  matchClaim: "exact" | "similar";
  mode: "live" | "fixture" | "manual";
  observedAt: string;
  offerGroup?: OfferGroup | null;
  price: Money | null;
  priceBasis: "agent_observed" | "unknown";
  priceExcerpt: string | null;
  retailer: string;
  section: "primary" | "needs_checking" | "excluded";
  sellerKind?: "retailer" | "marketplace" | "resale" | "unknown";
  sizesAvailable: string[];
  source?: "agent" | "catalog" | "manual_import";
  title: string;
  uncertainty: string | null;
  validatedAt: string;
  variants?: ResearchVariant[];
  verification: "url_checked_page_not_fetched";
  warnings: string[];
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "ResearchVariant".
 */
export interface ResearchVariant {
  availability: "available" | "unavailable" | "unknown";
  label: string;
  price?: Money | null;
}
/**
 * Compact, soft hints from the shopper's style profile. Never hard constraints.
 *
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "StyleHints".
 */
export interface StyleHints {
  /**
   * @maxItems 5
   */
  brandsAvoid?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string];
  /**
   * @maxItems 5
   */
  brandsLike?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string];
  /**
   * @maxItems 5
   */
  colorsAvoid?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string];
  /**
   * @maxItems 5
   */
  colorsLike?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string];
  /**
   * @maxItems 5
   */
  materialsAvoid?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string];
  /**
   * @maxItems 5
   */
  tonesLike?:
    | []
    | [string]
    | [string, string]
    | [string, string, string]
    | [string, string, string, string]
    | [string, string, string, string, string];
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "ResearchSubmission".
 */
export interface ResearchSubmission {
  jobId: string;
  notes?: string | null;
  /**
   * @maxItems 20
   */
  products:
    | []
    | [SubmittedProduct]
    | [SubmittedProduct, SubmittedProduct]
    | [SubmittedProduct, SubmittedProduct, SubmittedProduct]
    | [SubmittedProduct, SubmittedProduct, SubmittedProduct, SubmittedProduct]
    | [SubmittedProduct, SubmittedProduct, SubmittedProduct, SubmittedProduct, SubmittedProduct]
    | [SubmittedProduct, SubmittedProduct, SubmittedProduct, SubmittedProduct, SubmittedProduct, SubmittedProduct]
    | [
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct
      ]
    | [
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct
      ]
    | [
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct
      ]
    | [
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct
      ]
    | [
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct
      ]
    | [
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct
      ]
    | [
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct
      ]
    | [
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct
      ]
    | [
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct
      ]
    | [
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct
      ]
    | [
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct
      ]
    | [
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct
      ]
    | [
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct
      ]
    | [
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct,
        SubmittedProduct
      ];
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "SubmittedProduct".
 */
export interface SubmittedProduct {
  availability?: "in_stock" | "out_of_stock" | "unknown";
  brand?: string | null;
  condition?: "new" | "used" | "pre_owned" | "unknown";
  /**
   * @maxItems 12
   */
  evidence?:
    | []
    | [PageEvidence]
    | [PageEvidence, PageEvidence]
    | [PageEvidence, PageEvidence, PageEvidence]
    | [PageEvidence, PageEvidence, PageEvidence, PageEvidence]
    | [PageEvidence, PageEvidence, PageEvidence, PageEvidence, PageEvidence]
    | [PageEvidence, PageEvidence, PageEvidence, PageEvidence, PageEvidence, PageEvidence]
    | [PageEvidence, PageEvidence, PageEvidence, PageEvidence, PageEvidence, PageEvidence, PageEvidence]
    | [PageEvidence, PageEvidence, PageEvidence, PageEvidence, PageEvidence, PageEvidence, PageEvidence, PageEvidence]
    | [
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence
      ]
    | [
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence
      ]
    | [
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence
      ]
    | [
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence,
        PageEvidence
      ];
  identifiers?: ProductIdentifiers | null;
  imageUrl?: string | null;
  matchType: "exact" | "similar";
  observedAt: string;
  observedPrice?: SubmittedPrice | null;
  priceExcerpt?: string | null;
  productUrl: string;
  retailer: string;
  sellerKind?: "retailer" | "marketplace" | "resale" | "unknown";
  /**
   * @maxItems 30
   */
  sizesAvailable?: string[];
  sourceUrl?: string | null;
  title: string;
  uncertainty?: string | null;
  /**
   * @maxItems 60
   */
  variants?: SubmittedVariant[];
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "SubmittedPrice".
 */
export interface SubmittedPrice {
  amountMinor: number;
  currency: string;
}
/**
 * A size or variant as the page showed it. ``available`` False is kept, never dropped.
 *
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "SubmittedVariant".
 */
export interface SubmittedVariant {
  available?: boolean | null;
  label: string;
  price?: SubmittedPrice | null;
  priceExcerpt?: string | null;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "SearchBudget".
 */
export interface SearchBudget {
  maxDetailCalls?: number;
  maxRoundsPerWorker?: number;
  maxToolCalls?: number;
  reasoningCalls?: number;
  usedDetailCalls?: number;
  usedToolCalls?: number;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "SearchJob".
 */
export interface SearchJob {
  budget: SearchBudget;
  catalogMode: string;
  createdAt: string;
  deadlineAt: string;
  error?: JobError | null;
  finishedAt?: string | null;
  garmentId: string;
  id: string;
  inputHash: string;
  ownerId: string;
  preferenceSnapshot: Preferences;
  resultIds?: string[];
  sessionId: string;
  sessionRevision: number;
  status: "queued" | "running" | "completed" | "partial" | "no_match" | "failed" | "cancelled" | "superseded";
  summary?: string | null;
  workerMode: "grok" | "rule_based";
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "ShoppingSession".
 */
export interface ShoppingSession {
  activeSearchId: string | null;
  analysisId?: string | null;
  createdAt: string;
  id: string;
  lastPresentedResultIds?: string[];
  mediaId: string | null;
  ownerId: string;
  preferences: Preferences;
  revision: number;
  selectedGarmentId: string | null;
  updatedAt: string;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "StyleEvent".
 */
export interface StyleEvent {
  id: string;
  item?: StyleItem | null;
  linkKind?: string | null;
  memoryId?: string | null;
  occurredAt: string;
  orderId?: string | null;
  origin: "stated" | "inferred";
  source: string;
  type:
    | "explicit_preference"
    | "saved_item"
    | "rejected_item"
    | "retailer_click"
    | "user_confirmed_purchase"
    | "verified_order";
}
/**
 * Listing facts copied server-side from stored records; never client-supplied.
 *
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "StyleItem".
 */
export interface StyleItem {
  brand?: string | null;
  category?: string | null;
  condition?: string | null;
  domain?: string | null;
  listingId?: string | null;
  offerKey?: string | null;
  productKey?: string | null;
  recommendationId?: string | null;
  styleFacts?: StyleTagFact[];
  title: string;
}
/**
 * A style tag the listing's own text states, with the words that state it.
 *
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "StyleTagFact".
 */
export interface StyleTagFact {
  excerpt: string;
  field: "title" | "material";
  tag: string;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "StyleMemory".
 */
export interface StyleMemory {
  confidence?: number | null;
  createdAt: string;
  /**
   * @maxItems 5
   */
  evidence?:
    | []
    | [MemoryEvidence]
    | [MemoryEvidence, MemoryEvidence]
    | [MemoryEvidence, MemoryEvidence, MemoryEvidence]
    | [MemoryEvidence, MemoryEvidence, MemoryEvidence, MemoryEvidence]
    | [MemoryEvidence, MemoryEvidence, MemoryEvidence, MemoryEvidence, MemoryEvidence];
  evidenceCount?: number;
  id: string;
  kind:
    | "size"
    | "fit"
    | "budget_max"
    | "color_like"
    | "color_avoid"
    | "material_like"
    | "material_avoid"
    | "brand_like"
    | "brand_avoid"
    | "tone_like"
    | "tone_avoid"
    | "ring_size"
    | "style_like"
    | "style_avoid";
  lastEvidenceAt?: string | null;
  origin: "stated" | "inferred";
  overriddenBy?: string | null;
  source:
    | "preferences_form"
    | "style_panel"
    | "style_note"
    | "chat_refinement"
    | "saved_items"
    | "rejected_items"
    | "purchases"
    | "model_interpretation";
  sourceEventIds?: string[];
  status: "active" | "overridden" | "removed";
  updatedAt: string;
  value: unknown;
}
/**
 * Which reader handles style notes. Never claims local processing for a hosted model.
 *
 * mode: unavailable (feature or provider off), unverified (configured, no successful call yet),
 * live (a real call succeeded since startup).
 *
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "StyleModelInfo".
 */
export interface StyleModelInfo {
  hosting?: ("local" | "remote") | null;
  label?: string | null;
  mode: "unavailable" | "unverified" | "live";
  model?: string | null;
  provider?: ("none" | "ollama" | "openai_compatible") | null;
}
/**
 * What POST /api/style/notes returns. Proposals only; nothing is saved.
 *
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "StyleNoteResult".
 */
export interface StyleNoteResult {
  hosting?: ("local" | "remote") | null;
  mode: "model" | "rule_based";
  model?: string | null;
  note?: string | null;
  proposals?: StyleProposal[];
  provider: string;
  rejectedProposals?: number;
  usage?: StyleNoteUsage | null;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "StyleProposal".
 */
export interface StyleProposal {
  action: "add" | "set" | "remove";
  kind:
    | "size"
    | "fit"
    | "budget_max"
    | "color_like"
    | "color_avoid"
    | "material_like"
    | "material_avoid"
    | "brand_like"
    | "brand_avoid"
    | "tone_like"
    | "tone_avoid"
    | "ring_size"
    | "style_like"
    | "style_avoid";
  quote: string;
  value: unknown;
}
/**
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "StyleNoteUsage".
 */
export interface StyleNoteUsage {
  completionTokens?: number | null;
  promptTokens?: number | null;
  wallMs?: number | null;
}
/**
 * What GET /api/style/profile returns: the profile without internal product keys.
 *
 * This interface was referenced by `ClipCartContracts`'s JSON-Schema
 * via the `definition` "StyleProfileView".
 */
export interface StyleProfileView {
  /**
   * @maxItems 5
   */
  brandsAvoid?:
    | []
    | [ProfileEntry]
    | [ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry];
  /**
   * @maxItems 5
   */
  brandsLike?:
    | []
    | [ProfileEntry]
    | [ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry];
  budgetMax?: ProfileEntry | null;
  /**
   * @maxItems 5
   */
  colorsAvoid?:
    | []
    | [ProfileEntry]
    | [ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry];
  /**
   * @maxItems 5
   */
  colorsLike?:
    | []
    | [ProfileEntry]
    | [ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry];
  fit?: ProfileEntry | null;
  /**
   * @maxItems 5
   */
  materialsAvoid?:
    | []
    | [ProfileEntry]
    | [ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry];
  /**
   * @maxItems 5
   */
  materialsLike?:
    | []
    | [ProfileEntry]
    | [ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry];
  /**
   * @maxItems 5
   */
  recentlyOwned?:
    | []
    | [OwnedItem]
    | [OwnedItem, OwnedItem]
    | [OwnedItem, OwnedItem, OwnedItem]
    | [OwnedItem, OwnedItem, OwnedItem, OwnedItem]
    | [OwnedItem, OwnedItem, OwnedItem, OwnedItem, OwnedItem];
  rejectedOfferCount?: number;
  ringSize?: ProfileEntry | null;
  size?: ProfileEntry | null;
  /**
   * @maxItems 5
   */
  stylesAvoid?:
    | []
    | [ProfileEntry]
    | [ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry];
  /**
   * @maxItems 5
   */
  stylesLike?:
    | []
    | [ProfileEntry]
    | [ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry];
  /**
   * @maxItems 5
   */
  tonesAvoid?:
    | []
    | [ProfileEntry]
    | [ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry];
  /**
   * @maxItems 5
   */
  tonesLike?:
    | []
    | [ProfileEntry]
    | [ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry]
    | [ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry, ProfileEntry];
  updatedAt?: string | null;
}
