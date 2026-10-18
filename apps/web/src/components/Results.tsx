import { useState } from "react";
import { mediaUrl } from "../api";
import type { SearchView } from "../types";
import ResultCard from "./ResultCard";

const STAGE: Record<string, string> = {
  locating_garment: "Garment",
  searching_original: "Original",
  searching_alternatives: "Alternatives",
  verifying_listings: "Verifying",
  ranking: "Rules",
  completed: "Done",
  partial: "Partial",
  no_match: "No match",
  failed: "Failed",
  superseded: "Replaced",
};
const PIPELINE = ["searching_original", "searching_alternatives", "verifying_listings", "ranking"];

/** Search outcomes where no catalog call happened (backend pipeline): shown as such, never as an empty catalog. */
const NO_RETRIEVAL = new Set(["no_search_query", "deadline_before_search", "budget_before_search"]);

export default function Results({
  view,
  cropId,
  garmentLabel,
  accessory = false,
  onRetry,
  onCancel,
}: {
  view: SearchView | null;
  cropId: string | null;
  garmentLabel: string | null;
  accessory?: boolean;
  onRetry: () => void;
  onCancel: () => void;
}) {
  const [showLog, setShowLog] = useState(false);
  if (!view) return null;
  const { job, events, results } = view;
  const running = job.status === "queued" || job.status === "running";
  const primary = results.filter((r) => r.recommendation.section === "primary");
  const needs = results.filter((r) => r.recommendation.section === "needs_checking");
  const original = results.filter((r) => r.recommendation.section === "original_over_budget");
  const modes = Object.values(job.workerModes ?? {});
  const agent = job.workerMode === "grok" ? (modes.includes("rule_based_fallback") ? "Grok (fell back to rules)" : "Grok workers") : "Rule-based workers";
  const reached = new Set<string>(events.map((e) => e.stage));
  const latest = events[events.length - 1];
  const count = results.filter((r) => r.listing).length;
  const title = running
    ? "Searching…"
    : job.status === "failed"
      ? "Search failed"
      : job.status === "no_match"
        ? "No qualifying results"
        : job.status === "cancelled"
          ? "Search cancelled"
          : `${count} option${count === 1 ? "" : "s"}`;

  return (
    <section className="results" aria-live="polite" aria-busy={running}>
      <header className="bridge">
        {cropId && <img className="bridge-crop" src={mediaUrl(cropId)} alt="" />}
        <span className="bridge-arrow" aria-hidden>
          →
        </span>
        <div className="bridge-text">
          <p className="bridge-kicker">{garmentLabel ? `Shopping results for your ${garmentLabel.toLowerCase()}` : "Shopping results"}</p>
          <h2>{title}</h2>
          <p className="muted small">
            {agent} · {job.budget.usedToolCalls}/{job.budget.maxToolCalls} catalog calls
            {job.summary && !running ? ` · ${job.summary}` : ""}
          </p>
        </div>
        {running && (
          <button type="button" className="btn btn-quiet btn-sm" onClick={onCancel}>
            Cancel
          </button>
        )}
      </header>

      {running && (
        <div className="pipeline" role="status">
          <ol>
            {PIPELINE.map((st) => (
              <li key={st} className={reached.has(st) ? "pl-on" : ""}>
                {STAGE[st]}
              </li>
            ))}
          </ol>
          <p>
            <span className="spinner" aria-hidden /> {latest?.summary ?? "Starting the search…"}
          </p>
        </div>
      )}

      {job.status === "failed" && (
        <div className="banner banner-error" role="alert">
          {job.error?.code === "interrupted"
            ? "The server restarted during this search."
            : NO_RETRIEVAL.has(job.error?.code ?? "")
              ? job.summary // the server says nothing was searched (or time ran out first): never "no listings found"
              : "The listing provider didn't respond."}{" "}
          Your garment and preferences are saved.{" "}
          <button type="button" className="btn btn-sm" onClick={onRetry}>
            Retry
          </button>
        </div>
      )}
      {job.status === "partial" && <div className="banner">Some provider calls failed. These results passed the same checks.</div>}

      {running && (
        <div className="cards" aria-hidden>
          {[0, 1, 2].map((i) => (
            <div key={i} className="card card-skel">
              <div className="card-media" />
              <div className="card-body">
                <span />
                <span />
                <span />
              </div>
            </div>
          ))}
        </div>
      )}

      {!running && primary.length > 0 && (
        <>
          <h3 className="section-title">Recommended</h3>
          <div className="cards">{primary.map((r) => <ResultCard key={r.recommendation.id} item={r} cropId={cropId} accessory={accessory} />)}</div>
        </>
      )}
      {!running && primary.length === 0 && needs.length > 0 && (
        <div className="banner">
          Nothing could be fully confirmed against your constraints. The options below need checking before you buy.
        </div>
      )}
      {!running && needs.length > 0 && (
        <>
          <h3 className="section-title">Needs checking</h3>
          <p className="muted small section-sub">Each one has something to confirm before you buy, listed on the card.</p>
          <div className="cards">{needs.map((r) => <ResultCard key={r.recommendation.id} item={r} cropId={cropId} accessory={accessory} />)}</div>
        </>
      )}
      {!running && original.length > 0 && (
        <>
          <h3 className="section-title">Possible original, above your budget</h3>
          <div className="cards">{original.map((r) => <ResultCard key={r.recommendation.id} item={r} cropId={cropId} accessory={accessory} />)}</div>
        </>
      )}
      {!running && job.status === "no_match" && (
        <div className="banner">
          {job.summary?.toLowerCase().includes("constraint")
            ? "No listings met your constraints. Try raising the budget or removing a size or material rule. We don't relax them for you."
            : job.summary || "No close listings found for this garment. Try another piece from the tray, or add a short description (e.g. denim trucker)."}
        </div>
      )}

      <div className="log">
        <button type="button" className="linkish" aria-expanded={showLog} onClick={() => setShowLog(!showLog)}>
          {showLog ? "Hide" : "Show"} agent activity ({events.length})
        </button>
        {showLog && (
          <ol className="events">
            {events.map((e) => (
              <li key={e.id} className={`ev ev-${e.worker}`}>
                <span className="ev-stage">{STAGE[e.stage] ?? e.stage}</span>
                <span>{e.summary}</span>
              </li>
            ))}
            {running && <li className="ev ev-pending">Working…</li>}
          </ol>
        )}
      </div>
    </section>
  );
}
