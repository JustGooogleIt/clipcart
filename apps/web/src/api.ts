import type { ResearchJob, SubmittedProduct } from "@contracts";
import type { CategoryInfo, Health, SearchView, SessionView } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public retryable = false,
    public requestId?: string,
  ) {
    super(message);
  }
}

const MUTATE = { "X-ClipCart-Request": "1" };

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? { ...(method !== "GET" ? MUTATE : {}) } : { "Content-Type": "application/json", ...MUTATE },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "network", "Can't reach the ClipCart server. Check that it's running.", true);
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    throw new ApiError(res.status, data?.code ?? "error", data?.message ?? res.statusText, !!data?.retryable, data?.requestId);
  }
  return data as T;
}

export const key = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);

// One boot request at a time per page. A fresh browser has no owner cookie yet, and every cookie-less resume mints a
// new owner: two in flight (React StrictMode runs the boot effect twice in dev) could leave the page on one owner's
// session while the cookie names the other, and the upload then 404s.
let resuming: Promise<SessionView> | null = null;
const resumeOnce = () =>
  (resuming ??= req<SessionView>("POST", "/api/sessions/resume", {}).finally(() => {
    resuming = null;
  }));

export const api = {
  health: () => req<Health>("GET", "/api/health"),
  diagnostics: () => req<Record<string, unknown>>("GET", "/api/diagnostics"),
  latest: () => req<SessionView>("GET", "/api/sessions/latest"),
  resume: resumeOnce,
  createSession: () => req<SessionView>("POST", "/api/sessions"),
  session: (id: string) => req<SessionView>("GET", `/api/sessions/${id}`),
  patch: (id: string, body: Record<string, unknown>) => req<SessionView>("PATCH", `/api/sessions/${id}`, body),
  addGarment: (id: string, body: Record<string, unknown>) =>
    req<{ garment: SessionView["garments"][number] }>("POST", `/api/sessions/${id}/garments`, body),
  patchGarment: (gid: string, body: Record<string, unknown>) => req<{ garment: unknown }>("PATCH", `/api/garments/${gid}`, body),
  startSearch: (id: string, expectedRevision: number) =>
    req<SessionView & { searchId: string }>("POST", `/api/sessions/${id}/searches`, { expectedRevision, idempotencyKey: key() }),
  search: (sid: string, afterSeq = 0) => req<SearchView>("GET", `/api/searches/${sid}?afterSeq=${afterSeq}`),
  cancel: (sid: string) => req<{ status: string }>("POST", `/api/searches/${sid}/cancel`, {}),
  message: (id: string, text: string, expectedRevision: number) =>
    req<SessionView & { applied: boolean; changes: string[]; reply: string; searchId?: string }>(
      "POST",
      `/api/sessions/${id}/messages`,
      { text, expectedRevision, idempotencyKey: key() },
    ),
  findInMedia: (id: string, text: string, expectedRevision: number) =>
    req<
      SessionView & {
        applied: boolean;
        reply: string;
        searchId?: string;
        find?: { query?: string; searchDescription?: string; garmentId?: string };
      }
    >("POST", `/api/sessions/${id}/find-in-media`, {
      text,
      expectedRevision,
      startSearch: true,
      idempotencyKey: key(),
    }),
  youtubeAnalyze: (id: string, youtubeUrl: string, expectedRevision: number) =>
    req<
      SessionView & {
        youtube?: { videoId: string; title: string | null; cacheHit: boolean; source: string };
        warnings?: string[];
      }
    >("POST", `/api/sessions/${id}/youtube-analyze`, { youtubeUrl, expectedRevision }),
  categories: () => req<{ categories: CategoryInfo[] }>("GET", "/api/categories"),
  // Research jobs (FEATURE_AGENT_RESEARCH). Contract: docs/contracts/agent-research.md, v2.
  startResearch: (id: string) => req<{ job: ResearchJob }>("POST", `/api/sessions/${id}/research-jobs`, { idempotencyKey: key() }),
  research: (jobId: string) => req<{ job: ResearchJob }>("GET", `/api/research-jobs/${jobId}`),
  importResearch: (jobId: string, products: SubmittedProduct[], notes: string | null) =>
    req<{ job: ResearchJob }>("POST", `/api/research-jobs/${jobId}/import`, { products, notes }),
};

export function upload(
  sessionId: string,
  revision: number,
  file: File,
  onProgress: (fraction: number) => void,
): Promise<SessionView> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/media/uploads?sessionId=${encodeURIComponent(sessionId)}&expectedRevision=${revision}`);
    xhr.setRequestHeader("X-ClipCart-Request", "1");
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let data: any = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as SessionView);
      else reject(new ApiError(xhr.status, data?.code ?? "upload_failed", data?.message ?? "Upload failed", !!data?.retryable));
    };
    xhr.onerror = () => reject(new ApiError(0, "network", "Upload interrupted. Check your connection and retry.", true));
    xhr.send(file);
  });
}

export const mediaUrl = (assetId: string) => `/api/media/${assetId}`;

export function money(minor: number | null | undefined, currency = "USD"): string {
  if (minor === null || minor === undefined) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: minor % 100 ? 2 : 0 }).format(
    minor / 100,
  );
}

export function timestamp(ms: number | null | undefined): string | null {
  if (ms === null || ms === undefined) return null;
  const s = ms / 1000;
  const m = Math.floor(s / 60);
  return `${m}:${(s - m * 60).toFixed(1).padStart(4, "0")}`;
}

export function ago(iso: string): string {
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.round(d / 60)}\u00a0min ago`;
  if (d < 86400) return `${Math.round(d / 3600)}\u00a0h ago`;
  return new Date(iso).toLocaleDateString();
}
