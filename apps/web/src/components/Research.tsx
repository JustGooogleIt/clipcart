/**
 * Research jobs: more offers for the selected piece, beside (not instead of) the main search.
 * Contract: docs/contracts/agent-research.md, v1 rendering rules plus the v2 section.
 *
 * Honesty rules this component keeps:
 * - The provider is named from health (provider and the mode jobs get) and the job itself. Nothing here is called
 *   Grok Bot output. Fixture jobs say development data; manual imports say "Imported manually".
 * - Never "verified". A price shows only with priceBasis "agent_observed", with its date and page text.
 * - Offer groups compare only confirmed prices; an offer without one is "Price not confirmed" and never "lowest".
 * - Unavailable variants stay visible, struck through.
 */
import { useEffect, useMemo, useState } from "react";
import type { JobError, OfferGroup, ResearchJob, ResearchProduct } from "@contracts";
import { api, ApiError, money } from "../api";
import type { Health } from "../types";
import { SELLER_CLAIMS_TEXT, takeWarning } from "../warnings";
import ManualImport from "./ManualImport";

const SOURCE: Record<string, string> = {
  catalog: "From SoleScout's store record",
  agent: "Found by research agent",
  manual_import: "Imported manually",
};
const SELLER: Record<string, string> = { retailer: "Retailer", marketplace: "Marketplace seller", resale: "Resale seller" };
const CONDITION: Record<string, string> = { new: "New", used: "Used", unknown: "Condition not stated" };
const STOCK: Record<string, { cls: string; text: string }> = {
  in_stock: { cls: "satisfied", text: "In stock" },
  out_of_stock: { cls: "violated", text: "Out of stock" },
  unknown: { cls: "unknown", text: "Stock unknown" },
};
const STATE_ICON: Record<string, string> = { satisfied: "✓", violated: "✕", unknown: "?" };
const RULE: Record<string, string> = { budget: "Budget", size: "Size", color: "Color", colors: "Color", materials: "Materials", condition: "Condition", ring_size: "Ring size" };
const ruleName = (c: string) => RULE[c] ?? c.charAt(0).toUpperCase() + c.slice(1).replace(/_/g, " ");
const day = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "");

/** What research does on this server, from health. Null when the flag is off. */
export function researchProvider(health: Health | null): { id: string; name: string; about: string; mode: "fixture" | "manual" | "live" | null } | null {
  const r = health?.research;
  if (!health?.features?.agentResearch || !r?.provider) return null;
  // health.research.mode is the mode jobs get; null means this server doesn't implement the provider.
  const mode = r.mode;
  if (mode === null) {
    return {
      id: r.provider,
      name: `${r.provider === "grok_bot" ? "Grok Bot research" : r.provider} (not available)`,
      about: "This server names a research provider it doesn't run, so research can't start here.",
      mode,
    };
  }
  switch (r.provider) {
    case "fixture":
      return {
        id: "fixture",
        name: "Development fixture",
        about: "Returns labelled development data built from captured SoleScout records. It isn't live research.",
        mode,
      };
    case "solescout":
      return {
        id: "solescout",
        name: `SoleScout fallback${mode === "fixture" ? " · fixture catalog" : ""}`,
        about: `Runs up to 2 SoleScout searches and 3 detail checks, then lists each named store record as an offer${
          mode === "fixture" ? ", here from the fixture catalog" : ""
        }. It doesn't cover independent retailers or resale.`,
        mode,
      };
    case "manual":
      return {
        id: "manual",
        name: "Manual import only",
        about: "Nothing is researched automatically. Start a job, then import offers you found yourself. They're labelled Imported manually.",
        mode,
      };
    case "grok_bot":
      // Results arrive as agent submissions and are validated like any agent's claims (docs/grok-bot-bridge.md).
      return {
        id: "grok_bot",
        name: health.research?.status === "operational" ? "Grok Bot research agent" : "Grok Bot research · not yet verified here",
        about:
          "Sends this piece to a Grok Bot routine, which browses stores and posts offers back. ClipCart checks every link and keeps only prices shown with the page's own text; nothing the Bot says is treated as verified. If nothing arrives, you can import offers by hand.",
        mode,
      };
    default:
      return {
        id: r.provider,
        name: `${r.provider} (not available)`,
        about: "This server names a research provider ClipCart doesn't know, so research can't run.",
        mode: null,
      };
  }
}

function startError(e: unknown, provider: string): string {
  const err = e instanceof ApiError ? e : null;
  if (err?.code === "feature_disabled") return "Research is turned off on this server.";
  if (err?.code === "provider_not_available") return `This server's research provider (${provider}) isn't available, so nothing was started.`;
  if (err?.code === "rate_limited") return "Too many research jobs in the last 10 minutes. Try again shortly.";
  if (err?.code === "no_selection") return "Select a piece first.";
  return err?.message ?? "Couldn't start research.";
}

export default function Research({
  sessionId,
  garmentId,
  health,
  accessory,
}: {
  sessionId: string;
  garmentId: string;
  health: Health | null;
  accessory: boolean;
}) {
  const provider = researchProvider(health);
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A job belongs to the piece it was started for.
  useEffect(() => {
    setJob(null);
    setError(null);
  }, [garmentId]);

  const pending = job?.status === "pending";
  useEffect(() => {
    if (!job || !pending) return;
    let stop = false;
    const t = setTimeout(
      async () => {
        try {
          const r = await api.research(job.id);
          if (!stop) setJob(r.job);
        } catch {
          if (!stop) setJob((j) => (j ? { ...j } : j)); // retry on the next tick
        }
      },
      job.provider === "manual" ? 3000 : 900,
    );
    return () => {
      stop = true;
      clearTimeout(t);
    };
  }, [job, pending]);

  if (!provider) return null;

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      setJob((await api.startResearch(sessionId)).job);
    } catch (e) {
      setError(startError(e, provider.id));
    } finally {
      setBusy(false);
    }
  };

  const err = job?.error ?? null;
  const canImport = !!job && (job.status === "failed" || job.status === "expired" || (job.status === "pending" && job.provider === "manual"));
  const manualResults = job?.resultSource === "manual_import";

  return (
    <section className="research" aria-labelledby="research-title" aria-busy={pending && job?.provider !== "manual"}>
      <header className="research-head">
        <div>
          <h3 id="research-title">More offers</h3>
          <p className="muted small">Optional research beside your main results. {provider.about}</p>
        </div>
        <span className={`research-provider rp-${provider.id}`}>{provider.name}</span>
      </header>

      {!job && (
        <div className="research-start">
          <button type="button" className="btn btn-sm" onClick={start} disabled={busy}>
            {busy ? "Starting…" : provider.id === "manual" ? "Start a manual research job" : "Research more offers"}
          </button>
          {error && (
            <p className="research-error" role="alert">
              {error}
            </p>
          )}
        </div>
      )}

      {job && (
        <div className="research-job" role="status">
          <p className="research-status">
            {pending && job.provider !== "manual" && <span className="spinner" aria-hidden />}
            <strong>{statusLine(job, err)}</strong>
            {(job.status === "completed" || job.status === "pending") && <span className={`research-mode rm-${job.mode}`}>{job.mode === "fixture" ? "Development data" : job.mode === "manual" ? (manualResults ? "Imported manually" : "Manual job · nothing runs") : "Live"}</span>}
          </p>
          {manualResults && (
            <p className="research-banner">
              These offers were imported by hand. ClipCart checked each link but didn't run any research or open the pages.
            </p>
          )}
          {job.agentNotes && <p className="muted small">{job.agentNotes}</p>}
          {job.styleHints && <StyleHintsLine hints={job.styleHints} />}
          {job.status === "failed" && err?.retryable && (
            <button type="button" className="btn btn-sm" onClick={start} disabled={busy}>
              Try again
            </button>
          )}
          {!pending && (
            <button type="button" className="linkish" onClick={() => setJob(null)}>
              Start over
            </button>
          )}
        </div>
      )}

      {job && !!job.products?.length && <Offers products={job.products} accessory={accessory} />}
      {job?.status === "completed" && !job.products?.length && (
        <p className="research-empty">No offers passed ClipCart's checks for this piece. Your main results above are unchanged.</p>
      )}
      {job && (job.rejected?.length ?? 0) > 0 && (
        <details className="research-rejected">
          <summary>
            {job.rejected!.length} result{job.rejected!.length === 1 ? "" : "s"} rejected by ClipCart's checks
          </summary>
          <ul>
            {job.rejected!.map((r) => (
              <li key={r.index}>
                {r.domain ? `${r.domain}: ` : ""}
                {r.reason}
              </li>
            ))}
          </ul>
        </details>
      )}

      {job && canImport && <ManualImport jobId={job.id} waiting={job.provider === "manual"} onImported={setJob} />}
    </section>
  );
}

function statusLine(job: ResearchJob, err: JobError | null): string {
  if (job.status === "pending") return job.provider === "manual" ? "Waiting for your manual import" : "Researching…";
  if (job.status === "expired") return job.summary ?? "No research results arrived before the job expired.";
  if (job.status === "failed") {
    if (err?.code === "catalog_unavailable") return "SoleScout didn't respond, so research stopped. Nothing was guessed.";
    return `Research failed${err?.message ? `: ${err.message}` : ""}.`;
  }
  return job.summary ?? "Research finished.";
}

function StyleHintsLine({ hints }: { hints: NonNullable<ResearchJob["styleHints"]> }) {
  const parts = [
    hints.colorsLike?.length ? `likes ${hints.colorsLike.join(", ")}` : "",
    hints.tonesLike?.length ? `likes ${hints.tonesLike.join(", ")}` : "",
    hints.brandsLike?.length ? `likes ${hints.brandsLike.join(", ")}` : "",
    hints.colorsAvoid?.length ? `avoids ${hints.colorsAvoid.join(", ")}` : "",
    hints.brandsAvoid?.length ? `avoids ${hints.brandsAvoid.join(", ")}` : "",
    hints.materialsAvoid?.length ? `avoids ${hints.materialsAvoid.join(", ")}` : "",
  ].filter(Boolean);
  if (!parts.length) return null;
  return (
    <p className="muted small">
      <span aria-hidden>✦</span> Your style was shared as soft hints ({parts.join("; ")}). Only your rules are hard limits.
    </p>
  );
}

const GROUP_TITLE: Record<OfferGroup["equivalence"], string> = {
  identifier_match: "Same product",
  approximate: "Looks like the same product — not confirmed",
  single: "",
};

/** Offers, with same-product groups shown together as an evidence-backed price comparison. */
function Offers({ products, accessory }: { products: ResearchProduct[]; accessory: boolean }) {
  const { groups, singles } = useMemo(() => {
    const byGroup = new Map<string, ResearchProduct[]>();
    for (const p of products) {
      const g = p.offerGroup;
      if (p.section === "excluded" || !g || g.equivalence === "single" || g.offerCount < 2) continue;
      byGroup.set(g.id, [...(byGroup.get(g.id) ?? []), p]);
    }
    const grouped = new Set([...byGroup.values()].flat().map((p) => p.id));
    return {
      groups: [...byGroup.values()],
      singles: products.filter((p) => !grouped.has(p.id) && p.section !== "excluded"),
    };
  }, [products]);
  const excluded = products.filter((p) => p.section === "excluded").length;
  const primary = singles.filter((p) => p.section === "primary");
  const needs = singles.filter((p) => p.section === "needs_checking");
  return (
    <div className="research-offers">
      {groups.map((g) => (
        <OfferGroupBlock key={g[0].offerGroup!.id} offers={g} accessory={accessory} />
      ))}
      {primary.length > 0 && (
        <>
          <h4 className="section-title">Recommended</h4>
          <div className="offer-list">{primary.map((p) => <Offer key={p.id} p={p} accessory={accessory} />)}</div>
        </>
      )}
      {needs.length > 0 && (
        <>
          <h4 className="section-title">Needs checking</h4>
          <div className="offer-list">{needs.map((p) => <Offer key={p.id} p={p} accessory={accessory} />)}</div>
        </>
      )}
      {excluded > 0 && <p className="muted small">{excluded} more didn't meet your rules and aren't linked.</p>}
    </div>
  );
}

function OfferGroupBlock({ offers, accessory }: { offers: ResearchProduct[]; accessory: boolean }) {
  const g = offers[0].offerGroup!;
  // Confirmed prices first, cheapest first; offers without a confirmed price after, never ranked.
  const sorted = [...offers].sort((a, b) => {
    const pa = confirmedPrice(a)?.amountMinor ?? Infinity;
    const pb = confirmedPrice(b)?.amountMinor ?? Infinity;
    return pa - pb;
  });
  const lowest = offers.find((p) => p.offerGroup?.isLowestConfirmed && p.price);
  return (
    <section className={`offer-group og-${g.equivalence}`} aria-label="Price comparison">
      <header>
        <p className="og-kicker">Price comparison</p>
        <h4>
          {GROUP_TITLE[g.equivalence]}
          {g.equivalence === "identifier_match" && <span className="og-basis"> ({g.basis})</span>}
        </h4>
        {g.equivalence === "approximate" && <p className="muted small">{g.basis}</p>}
        <p className="og-summary">
          {g.lowestConfirmedPrice && lowest ? (
            <>
              Lowest confirmed price <strong>{money(g.lowestConfirmedPrice.amountMinor, g.lowestConfirmedPrice.currency)}</strong> at {lowest.retailer}
            </>
          ) : (
            "No confirmed price to compare yet"
          )}
          {" · "}
          {g.offerCount} offer{g.offerCount === 1 ? "" : "s"} found{g.offerCount > offers.length ? `, ${offers.length} shown` : ""}
          {g.uncertainPriceCount > 0 ? ` · ${g.uncertainPriceCount} without a confirmed price, not compared` : ""}
        </p>
      </header>
      <div className="offer-list">
        {sorted.map((p) => (
          <Offer key={p.id} p={p} accessory={accessory} />
        ))}
      </div>
    </section>
  );
}

const confirmedPrice = (p: ResearchProduct) => (p.priceBasis === "agent_observed" && p.price ? p.price : null);

function priceNote(p: ResearchProduct): string {
  const on = day(p.observedAt);
  if (p.source === "catalog") return `from the store record, seen ${on}`;
  if (p.source === "manual_import") return `seen on the page ${on}, imported by hand`;
  return `seen by the agent on ${on}`;
}

function Offer({ p, accessory }: { p: ResearchProduct; accessory: boolean }) {
  const [imgFailed, setImgFailed] = useState(false);
  const price = confirmedPrice(p);
  const stock = STOCK[p.availability] ?? STOCK.unknown;
  const [first, ...rest] = p.links;
  const viaComparison = first?.kind === "aggregator_product_page";
  const exactClaim =
    p.matchClaim === "exact" ? (p.source === "manual_import" ? "Marked exact match on import (not confirmed)" : "Agent says exact match (not confirmed)") : null;
  const tier = accessory ? "Similar look" : "Similar option";
  const evidence = p.evidence ?? [];
  const variants = p.variants ?? [];
  const isLowest = !!p.offerGroup?.isLowestConfirmed && !!price;
  const claim = takeWarning(p.warnings, p.warningCodes, "seller_claims_unverified");
  return (
    <article className={`offer ${isLowest ? "offer-lowest" : ""}`} data-offer={p.id}>
      <div className="offer-media">
        {p.imageUrl && !imgFailed ? (
          <img src={p.imageUrl} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setImgFailed(true)} />
        ) : (
          <span className="offer-noimg">{p.imageUrl ? "Image didn't load" : "No image"}</span>
        )}
      </div>
      <div className="offer-body">
        <p className="offer-tags">
          <span className={`offer-source os-${p.source ?? "agent"}`}>{SOURCE[p.source ?? "agent"] ?? p.source}</span>
          {p.mode === "fixture" ? (
            <span className="offer-fixture">Development fixture</span>
          ) : p.mode === "live" ? (
            <span className="offer-live">Live result</span>
          ) : null}
          <span className="tier tier-similar">{tier}</span>
          {isLowest && <span className="offer-lowest-tag">Lowest confirmed price</span>}
        </p>
        {p.brand && (
          <p className="card-brand">
            {p.brand} <small>{p.brandBasis === "catalog_record" ? "(from SoleScout)" : "(from the page)"}</small>
          </p>
        )}
        <h5 className="offer-title">{p.title}</h5>
        <p className="offer-seller">
          {p.retailer}
          {p.domain && !p.retailer.toLowerCase().includes(p.domain.split(".")[0]) ? ` · ${p.domain}` : ""}
          {p.sellerKind && p.sellerKind !== "unknown" ? ` · ${SELLER[p.sellerKind]}` : ""}
        </p>
        {exactClaim && <p className="offer-claim">{exactClaim}</p>}
        {claim.present && <p className="card-claim">{claim.text ?? SELLER_CLAIMS_TEXT}</p>}
        <div className="offer-price">
          {price ? (
            <>
              <strong>{money(price.amountMinor, price.currency)}</strong>
              <span>{priceNote(p)}</span>
              {p.priceExcerpt && <q className="offer-excerpt">{p.priceExcerpt}</q>}
            </>
          ) : (
            <strong className="offer-noprice">Price not confirmed</strong>
          )}
        </div>
        <ul className="checks" aria-label="Checks">
          {p.constraintChecks.map((c) => (
            <li key={c.constraint} className={`check check-${c.state}`} title={c.detail}>
              <span aria-hidden>{STATE_ICON[c.state]}</span> {ruleName(c.constraint)}
              <span className="sr-only">: {c.state}. {c.detail}</span>
            </li>
          ))}
          <li className={`check check-${stock.cls}`}>{stock.text}</li>
          <li className={`check check-${p.condition && p.condition !== "unknown" ? "satisfied" : "unknown"} check-plain`}>
            {CONDITION[p.condition ?? "unknown"]}
          </li>
        </ul>
        {variants.length > 0 && (
          <ul className="variants" aria-label="Sizes and variants on the page">
            {variants.map((v, i) => (
              <li key={`${v.label}-${i}`} className={`variant var-${v.availability}`}>
                {v.availability === "unavailable" ? <s>{v.label}</s> : v.label}
                {v.availability === "unavailable" && <small> Unavailable</small>}
                {v.availability === "unknown" && <small> ?</small>}
                {v.price && <small> {money(v.price.amountMinor, v.price.currency)}</small>}
              </li>
            ))}
          </ul>
        )}
        {p.uncertainty && <p className="offer-uncertain">{p.uncertainty}</p>}
        <div className="card-actions">
          {first && (
            <>
              <span className={`dest dest-${viaComparison ? "compare" : "retailer"}`}>{viaComparison ? "Price comparison page" : "Retailer product page"}</span>
              <a className="btn btn-go btn-sm" href={`/go/${first.token}`} target="_blank" rel="noopener noreferrer">
                <span>{first.label}</span>
                <span aria-hidden>↗</span>
              </a>
            </>
          )}
          {rest.map((lk) => (
            <a key={lk.token} className="alt-link" href={`/go/${lk.token}`} target="_blank" rel="noopener noreferrer">
              <span>
                {lk.label} <span aria-hidden>↗</span>
              </span>
              <small>{lk.priceNote}</small>
            </a>
          ))}
        </div>
        <details className="offer-more">
          <summary>
            Evidence{evidence.length ? ` (${evidence.length})` : ""} and warnings
          </summary>
          {evidence.length > 0 && (
            <dl className="offer-evidence">
              {evidence.map((e, i) => (
                <div key={i}>
                  <dt>{e.field}</dt>
                  <dd>
                    <q>{e.excerpt}</q>
                  </dd>
                </div>
              ))}
            </dl>
          )}
          <ul className="warnings">
            {claim.rest.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
          <p className="muted small">
            ClipCart checked the link but didn't open the page. Checked {day(p.validatedAt)}.
          </p>
        </details>
      </div>
    </article>
  );
}
