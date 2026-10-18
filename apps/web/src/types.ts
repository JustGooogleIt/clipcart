import type {
  AgentEvent,
  AnalysisJob,
  Evidence,
  FrameRef,
  Garment,
  GarmentObservation,
  Listing,
  MediaAsset,
  Recommendation,
  SearchJob,
  ShoppingSession,
} from "@contracts";

export type { AgentEvent, Evidence, FrameRef, Garment, GarmentObservation, Listing, Recommendation };

export type SessionWire = Omit<ShoppingSession, "ownerId">;
export type GarmentDoc = Garment & { category: string; manual?: boolean; analysisId?: string | null };
export type AnalysisDoc = AnalysisJob & { frames?: FrameRef[]; droppedDetections?: number };
export type SearchJobDoc = Omit<SearchJob, "ownerId"> & {
  workerModes?: Record<string, string>;
  summary?: string | null;
};

export interface SessionView {
  session: SessionWire;
  media: Omit<MediaAsset, "ownerId" | "storageKey"> | null;
  analysis: AnalysisDoc | null;
  garments: GarmentDoc[];
  observations: GarmentObservation[];
  activeSearch?: SearchJobDoc | null;
  searchId?: string;
}

export interface ResultItem {
  recommendation: Recommendation;
  listing: Listing | null;
  evidence: Evidence[];
}

export interface SearchView {
  job: SearchJobDoc;
  events: AgentEvent[];
  results: ResultItem[];
}

export interface ProviderSnapshot {
  mode: string;
  configured: boolean;
  calls: number;
  failures: number;
  lastSuccessAt: string | null;
  lastError: { code?: string; note?: string; traceId?: string } | null;
  recent?: { at: string; ok: boolean; traceId: string | null; code: string | null; note: string }[];
  model?: string;
  provider?: string;
  setting?: string;
  error?: string | null;
}

export interface Health {
  api: string;
  database: { mode: string; ok: boolean; note: string | null };
  providers: { perceptron: ProviderSnapshot; grok: ProviderSnapshot; catalog: ProviderSnapshot };
  features: {
    photon: boolean;
    voice: boolean;
    solana: boolean;
    agentResearch?: boolean;
    youtubeDownload?: boolean;
  };
  youtube?: { enabled: boolean; allowedVideoCount: number; maxDurationS: number };
}
