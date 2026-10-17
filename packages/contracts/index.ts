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
  category: "jacket" | "top" | "bag" | "other";
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
  sourceType: "upload_image" | "upload_video";
  storageKey: string;
  width: number;
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
  size?: SizePref | null;
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
