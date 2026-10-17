import { useState } from "react";
import { ago, mediaUrl } from "../api";
import type { ResultItem } from "../types";

const TIER: Record<string, string> = { verified: "Verified match", likely: "Likely match", similar: "Similar option" };
const STATE_ICON: Record<string, string> = { satisfied: "✓", violated: "✕", unknown: "?" };
const MODE: Record<string, string> = { live: "Live", cached: "Cached", fixture: "Fixture", catalog: "Catalog" };

export default function ResultCard({ item, cropId }: { item: ResultItem; cropId: string | null }) {
  const [open, setOpen] = useState(false);
  const { recommendation: r, listing: L, evidence } = item;
  if (!L) return null;
  const avail =
    L.availability === "in_stock" ? (L.priceBasis === "aggregate_lowest" ? "Some sizes listed in stock" : "In stock") : L.availability === "out_of_stock" ? "Out of stock" : "Availability unknown";
  const [first, ...rest] = r.links;
  return (
    <article className={`card card-${r.section}`}>
      <div className="card-media">
        {L.imageUrls[0] ? (
          <img src={L.imageUrls[0]} alt={L.title} loading="lazy" referrerPolicy="no-referrer" />
        ) : (
          <div className="card-noimg">No image</div>
        )}
        <span className={`tier tier-${r.identityTier}`}>{TIER[r.identityTier]}</span>
      </div>
      <div className="card-body">
        <p className="card-brand">{L.brand ?? "Brand not listed"}</p>
        <h3 className="card-title">{L.title}</h3>
        {first && <p className="card-price">{first.priceNote}</p>}
        <p className="card-reason">{r.explanation}</p>
        <ul className="checks" aria-label="Constraint checks">
          {r.constraintChecks.map((c) => (
            <li key={c.constraint} className={`check check-${c.state}`} title={c.detail}>
              <span aria-hidden>{STATE_ICON[c.state]}</span> {c.constraint}
              <span className="sr-only">: {c.state}. {c.detail}</span>
            </li>
          ))}
          <li className={`check ${L.availability === "in_stock" ? "check-satisfied" : "check-unknown"}`}>{avail}</li>
        </ul>
        <p className="card-meta">
          <span className={`mode mode-${L.mode}`}>{MODE[L.mode] ?? L.mode}</span> · checked {ago(L.checkedAt)} ·{" "}
          {L.sourceKind === "aggregator" ? "price comparison site" : L.retailer}
        </p>
        <div className="card-actions">
          {first && (
            <a className="btn btn-primary" href={`/go/${first.token}`} target="_blank" rel="noopener noreferrer">
              {first.label} <span aria-hidden>↗</span>
            </a>
          )}
          {rest.map((lk) => (
            <a key={lk.token} className="btn btn-quiet" href={`/go/${lk.token}`} target="_blank" rel="noopener noreferrer" title={lk.priceNote}>
              {lk.label} <span aria-hidden>↗</span>
              <small>{lk.priceNote}</small>
            </a>
          ))}
        </div>
        <button type="button" className="linkish" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "Hide evidence" : "Evidence and details"}
        </button>
        {open && (
          <div className="evidence">
            {cropId && (
              <figure>
                <img src={mediaUrl(cropId)} alt="Your selected garment" />
                <figcaption>Your garment</figcaption>
              </figure>
            )}
            <dl>
              {r.constraintChecks.map((c) => (
                <div key={c.constraint}>
                  <dt>{c.constraint}</dt>
                  <dd>
                    {c.state}: {c.detail}
                  </dd>
                </div>
              ))}
              {L.storeOffers && L.storeOffers.length > 0 && (
                <div>
                  <dt>Named stores</dt>
                  <dd>{L.storeOffers.map((s) => `${s.retailer} (${s.price ? "price listed" : "no price shown"})`).join(", ")}</dd>
                </div>
              )}
              {L.hiddenStoreCount ? (
                <div>
                  <dt>Hidden sellers</dt>
                  <dd>{L.hiddenStoreCount} cheapest seller name(s) withheld by SoleScout</dd>
                </div>
              ) : null}
              {L.sizesInStock && (
                <div>
                  <dt>Sizes listed in stock</dt>
                  <dd>{L.sizesInStock.length ? L.sizesInStock.map((s) => s.raw).join(", ") : "None listed (stock unknown)"}</dd>
                </div>
              )}
            </dl>
            <h4>Sources</h4>
            <ul className="sources">
              {evidence.map((e) => (
                <li key={e.id}>
                  {e.provider} {e.sourceType.replace("_", " ")} · retrieved {new Date(e.retrievedAt).toLocaleString()}
                </li>
              ))}
            </ul>
            {r.warnings.length > 0 && (
              <ul className="warnings">
                {r.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            )}
            <p className="muted small">Checkout, shipping and final stock are confirmed on the destination site, not by ClipCart.</p>
          </div>
        )}
      </div>
    </article>
  );
}
