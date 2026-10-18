/**
 * Style memory client. Contract: docs/contracts/style-memory.md (PR #15); types come from @contracts.
 *
 * Every call fails soft: the feature flag being off, an offline memory service or an unreachable style model must
 * never block the shopping flow. Nothing in the upload → pick → rules → search path waits on this module.
 */
import { createContext, useContext } from "react";
import type { StyleEvent, StyleMemory, StyleModelInfo, StyleNoteResult } from "@contracts";
import { key } from "./api";

export type { StyleEvent, StyleItem, StyleMemory, StyleModelInfo, StyleNoteResult, StyleProposal } from "@contracts";
export type MemoryKind = StyleMemory["kind"];

export type MemoryState =
  | { state: "loading" }
  | { state: "ready"; memories: StyleMemory[]; events: StyleEvent[]; styleModel: StyleModelInfo }
  | { state: "unavailable"; reason: "disabled" | "offline"; message: string };

const MUTATE = { "X-ClipCart-Request": "1" };
const TIMEOUT_MS = 5000;

export class MemoryError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      credentials: "same-origin",
      signal: ctl.signal,
      headers: body === undefined ? (method === "GET" ? {} : MUTATE) : { "Content-Type": "application/json", ...MUTATE },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new MemoryError(0, "network", "Can't reach the memory service.");
  } finally {
    clearTimeout(t);
  }
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    /* non-JSON, e.g. a proxy error page */
  }
  if (!res.ok) throw new MemoryError(res.status, data?.code ?? "error", data?.message ?? res.statusText);
  return data as T;
}

export async function loadMemory(): Promise<MemoryState> {
  try {
    const [p, m, e] = await Promise.all([
      call<{ styleModel: StyleModelInfo }>("GET", "/api/style/profile"),
      call<{ memories: StyleMemory[] }>("GET", "/api/style/memories"),
      call<{ events: StyleEvent[] }>("GET", "/api/style/events?limit=50"),
    ]);
    return { state: "ready", memories: m.memories ?? [], events: e.events ?? [], styleModel: p.styleModel };
  } catch (err) {
    const status = err instanceof MemoryError ? err.status : 0;
    // 404 feature_disabled when FEATURE_STYLE_MEMORY is off; a plain 404 on a server without the routes.
    if (status === 404 || status === 405)
      return { state: "unavailable", reason: "disabled", message: "Your style is turned off on this server." };
    return { state: "unavailable", reason: "offline", message: "The memory service is offline right now." };
  }
}

export const memoryApi = {
  /** A stated preference. For one-active kinds (size, fit, budget_max) the server overrides the older one. */
  state: (kind: MemoryKind, value: unknown, source: "style_panel" | "style_note" = "style_panel") =>
    call<{ memory: StyleMemory; overridden: string[] }>("POST", "/api/style/memories", { kind, value, source, idempotencyKey: key() }),
  remove: (id: string) => call<{ memory: StyleMemory }>("DELETE", `/api/style/memories/${id}`),
  /** saved_item, rejected_item or user_confirmed_purchase. Clicks and verified orders are server-only. */
  event: (type: "saved_item" | "rejected_item" | "user_confirmed_purchase", recommendationId: string) =>
    call<{ event: StyleEvent }>("POST", "/api/style/events", { type, recommendationId, idempotencyKey: key() }),
  removeEvent: (id: string) => call<{ deleted: string }>("DELETE", `/api/style/events/${id}`),
  /** Proposes updates from text and saves nothing. */
  note: (text: string) => call<StyleNoteResult>("POST", "/api/style/notes", { text }),
};

/**
 * One-line description of what reads style notes right now, from the server's own label and hosting.
 * Never calls a reader local unless the server says so, and never names a model before a real call succeeded.
 */
export function noteReader(m: StyleModelInfo): string {
  const name = m.label ?? m.model ?? "style model";
  if (m.mode === "live") return name;
  if (m.mode === "unverified") return `Rule-based parser · ${name} set up, no successful call yet`;
  return m.label ?? "Rule-based parser only";
}

/** Who read one note: the rule-based parser, or the model the response names, with where it runs. */
export function noteResultReader(r: StyleNoteResult, m: StyleModelInfo | null): string {
  if (r.mode !== "model") return "the rule-based parser";
  if (m?.mode === "live" && m.label) return m.label;
  const name = r.model ?? r.provider;
  return r.hosting === "remote" ? `${name}, hosted (not local)` : r.hosting === "local" ? `${name}, local` : name;
}

/** What result cards need from the panel: whether saving works, which results are saved, and the toggle. */
export interface MemoryActions {
  ready: boolean;
  savedEventId: (recommendationId: string, listingId: string) => string | null;
  toggleSave: (recommendationId: string, listingId: string) => void;
}

export const MemoryContext = createContext<MemoryActions>({
  ready: false,
  savedEventId: () => null,
  toggleSave: () => undefined,
});
export const useMemoryActions = () => useContext(MemoryContext);
