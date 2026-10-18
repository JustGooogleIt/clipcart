import { useState } from "react";
import { ago, mediaUrl, money } from "../api";
import { useMemoryActions } from "../memory";
import type { ResultItem } from "../types";

// Only a verified listing is called a match. Everything else, including the ranker's "likely" tier, is a similar option.
const TIER: Record<string, string> = { verified: "Verified match", likely: "Similar option", similar: "Similar option" };
const RULE: Record<string, string> = { budget: "Budget", size: "Size", color: "Color", colors: "Color", material: "Materials", materials: "Materials", condition: "Condition", fit: "Fit" };
const ruleName = (c: string) => RULE[c] ?? c.charAt(0).toUpperCase() + c.slice(1);
const STATE_ICON: Record<string, string> = { satisfied: "✓", violated: "✕", unknown: "?" };
const MODE: Record<string, string> = { live: "Live price", cached: "Cached price", fixture: "Fixture data", catalog: "Demo catalog" };

// The server's warning when a listing's own text claims metal, stones or authenticity (docs/contracts/accessories.md).
const isSellerClaim = (w: string) => /seller's description/i.test(w);

export default function ResultCard({ item, cropId, accessory = false }: { item: ResultItem; cropId: string | null; accessory?: boolean }) {
  const [showEvidence, setShowEvidence] = useState(false);
  const [imgFailed, setImgFailed] = useState(false);
  const mem = useMemoryActions();
  const { recommendation: r, listing: L, evidence } = item;
  if (!L) return null;
  const stock =
    L.availability === "in_stock"
      ? { cls: "satisfied", text: L.priceBasis === "aggregate_lowest" ? "Some sizes listed in stock" : "In stock" }
      : L.availability === "out_of_stock"
        ? { cls: "violated", text: "Out of stock" }
        : { cls: "unknown", text: "Stock unknown" };
  const [first, ...rest] = r.links;
  const viaComparison = first?.kind === "aggregator_product_page";
  const destination = viaComparison ? `${first?.retailer ?? L.retailer}'s price comparison page` : `${first?.retailer ?? L.retailer}'s product page`;
  const open = r.constraintChecks.filter((c) => c.state !== "satisfied");
  const unmet = open.length;
  // Style memory's reasons when it reordered this result; empty when it had no effect.
  const personalization = r.personalization ?? [];
  const saved = mem.savedEventId(r.id, L.id);
  const hidden = mem.hiddenEventId(r.id, L.id);
  // Watches and jewelry are never matched from appearance: the server caps them at "similar".
  const tier = accessory && r.identityTier !== "verified" ? "Similar look" : (TIER[r.identityTier] ?? r.identityTier);
  const claims = r.warnings.filter(isSellerClaim);
  if (hidden) {
    return (
      <article className={`card card-${r.section} card-hidden`} data-result={r.id}>
        <p>
          <strong>Hidden:</strong> {L.title}. ClipCart won't show this offer in your results again.
        </p>
        <button type="button" className="linkish" onClick={() => mem.toggleHide(r.id, L.id)}>
          Undo
        </button>
      </article>
    );
  }
  return (
    <article className={`card card-${r.section}`} data-result={r.id}>
      <div className="card-media">
        {L.imageUrls[0] && !imgFailed ? (
          <img src={L.imageUrls[0]} alt={L.title} loading="lazy" referrerPolicy="no-referrer" onError={() => setImgFailed(true)} />
        ) : (
          <div className="card-noimg">{L.imageUrls[0] ? "Product image didn't load" : "No product image"}</div>
        )}
        <span className={`tier tier-${r.identityTier}`}>{tier}</span>
        <span className={`mode mode-${L.mode}`}>{MODE[L.mode] ?? L.mode}</span>
      </div>
      <div className="card-body">
        <p className="card-brand">{L.brand ?? "Brand not listed"}</p>
        <h3 className="card-title" title={L.title}>
          {L.title}
        </h3>
        <div className="card-price">
          <strong>
            {L.price ? (
              <>
                {L.priceBasis === "aggregate_lowest" && <small>from </small>}
                {money(L.price.amountMinor, L.price.currency)}
              </>
            ) : (
              "Price not listed"
            )}
          </strong>
          {first && <span>{first.priceNote}</span>}
        </div>
        <ul className="checks" aria-label="Constraint checks">
          {r.constraintChecks.map((c) => (
            <li key={c.constraint} className={`check check-${c.state}`} title={c.detail}>
              <span aria-hidden>{STATE_ICON[c.state]}</span> {ruleName(c.constraint)}
              <span className="sr-only">: {c.state}. {c.detail}</span>
            </li>
          ))}
          <li className={`check check-${stock.cls}`}>{stock.text}</li>
        </ul>
        {r.section === "needs_checking" && open.length > 0 && (
          <ul className="confirm" aria-label="To confirm before buying">
            {open.map((c) => (
              <li key={c.constraint} className={`confirm-${c.state}`}>
                <strong>{ruleName(c.constraint)}:</strong> {c.detail}
                {c.constraint === "fit" ? ". A size like M on its own doesn't tell us the fit." : ""}
              </li>
            ))}
          </ul>
        )}
        {personalization.length > 0 && (
          <p className="card-personal">
            <span className="card-personal-tag">
              <span aria-hidden>✦</span> Your style
            </span>{" "}
            {personalization.join(" · ")}
          </p>
        )}
        {claims.map((w) => (
          <p key={w} className="card-claim">
            {w}
          </p>
        ))}
        <p className="card-reason">{r.explanation}</p>
        <div className="card-actions">
          {first && <span className={`dest dest-${viaComparison ? "compare" : "retailer"}`}>{viaComparison ? "Price comparison page" : "Retailer product page"}</span>}
          {first && (
            <a className="btn btn-go" href={`/go/${first.token}`} target="_blank" rel="noopener noreferrer">
              <span>{first.label}</span>
              <span aria-hidden>↗</span>
            </a>
          )}
          {mem.ready && (
            <div className="card-mem">
              <button type="button" className={`btn btn-sm btn-save ${saved ? "btn-saved" : ""}`} aria-pressed={!!saved} onClick={() => mem.toggleSave(r.id, L.id)}>
                {saved ? "Saved ✓" : "Save"}
              </button>
              {!saved && (
                <button type="button" className="btn btn-sm btn-quiet btn-hide" onClick={() => mem.toggleHide(r.id, L.id)} title="Hide this offer from your results">
                  Not for me
                </button>
              )}
            </div>
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
        <p className="card-meta">
          Opens {destination} · checked {ago(L.checkedAt)}
          {unmet > 0 && r.section !== "original_over_budget" ? ` · ${unmet} rule${unmet > 1 ? "s" : ""} to confirm` : ""}
        </p>
        <button type="button" className="linkish" aria-expanded={showEvidence} onClick={() => setShowEvidence(!showEvidence)}>
          {showEvidence ? "Hide evidence" : "Why this result? Evidence and sources"}
        </button>
        {showEvidence && (
          <div className="evidence">
            {cropId && (
              <figure>
                <img src={mediaUrl(cropId)} alt="Your selected garment" />
                {L.imageUrls[0] && !imgFailed && <img src={L.imageUrls[0]} alt="" referrerPolicy="no-referrer" />}
                <figcaption>Your piece next to this listing. {tier}, not a confirmed identical item unless verified.</figcaption>
              </figure>
            )}
            <dl>
              {r.constraintChecks.map((c) => (
                <div key={c.constraint}>
                  <dt>{ruleName(c.constraint)}</dt>
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
                  <dd>{L.hiddenStoreCount} seller name(s), including the lowest price, aren't shown by SoleScout. The lowest price isn't tied to any named store.</dd>
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
            {r.warnings.filter((w) => !isSellerClaim(w)).length > 0 && (
              <ul className="warnings">
                {r.warnings.filter((w) => !isSellerClaim(w)).map((w) => (
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
