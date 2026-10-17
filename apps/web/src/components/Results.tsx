import { useState } from "react";
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

export default function Results({
  view,
  cropId,
  onRetry,
  onCancel,
}: {
  view: SearchView | null;
  cropId: string | null;
  onRetry: () => void;
  onCancel: () => void;
}) {
  const [showLog, setShowLog] = useState(true);
  if (!view) return null;
  const { job, events, results } = view;
  const running = job.status === "queued" || job.status === "running";
  const primary = results.filter((r) => r.recommendation.section === "primary");
  const needs = results.filter((r) => r.recommendation.section === "needs_checking");
  const original = results.filter((r) => r.recommendation.section === "original_over_budget");
  const modes = Object.values(job.workerModes ?? {});
  const agent = job.workerMode === "grok" ? (modes.includes("rule_based_fallback") ? "Grok (fell back to rules)" : "Grok workers") : "Rule-based workers";

  return (
    <section className="results" aria-live="polite" aria-busy={running}>
      <header className="results-head">
        <h2>{running ? "Searching…" : job.status === "failed" ? "Search failed" : job.status === "no_match" ? "No qualifying results" : job.status === "cancelled" ? "Search cancelled" : "Results"}</h2>
        <p className="muted">
          {agent} · {job.budget.usedToolCalls}/{job.budget.maxToolCalls} catalog calls
          {job.summary ? ` · ${job.summary}` : ""}
        </p>
        {running && (
          <button type="button" className="btn btn-quiet btn-sm" onClick={onCancel}>
            Cancel
          </button>
        )}
      </header>

      {job.status === "failed" && (
        <div className="banner banner-error" role="alert">
          {job.error?.code === "interrupted" ? "The server restarted during this search." : "The listing provider didn't respond."}{" "}
          Your garment and preferences are saved.{" "}
          <button type="button" className="btn btn-sm" onClick={onRetry}>
            Retry
          </button>
        </div>
      )}
      {job.status === "partial" && <div className="banner">Some provider calls failed. These results passed the same checks.</div>}

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

      {!running && primary.length > 0 && (
        <>
          <h3 className="section-title">Recommended</h3>
          <div className="cards">{primary.map((r) => <ResultCard key={r.recommendation.id} item={r} cropId={cropId} />)}</div>
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
          <p className="muted small">Each one is missing evidence for at least one constraint, shown with “?”.</p>
          <div className="cards">{needs.map((r) => <ResultCard key={r.recommendation.id} item={r} cropId={cropId} />)}</div>
        </>
      )}
      {!running && original.length > 0 && (
        <>
          <h3 className="section-title">Possible original, above your budget</h3>
          <div className="cards">{original.map((r) => <ResultCard key={r.recommendation.id} item={r} cropId={cropId} />)}</div>
        </>
      )}
      {!running && job.status === "no_match" && (
        <div className="banner">
          No listings met your constraints. Try raising the budget or removing a size or material rule. We don't relax them for you.
        </div>
      )}
    </section>
  );
}
