/**
 * Manual import for a research job (POST /api/research-jobs/{id}/import, docs/contracts/agent-research.md v2).
 * Offered only for failed or expired jobs and for manual-provider jobs, behind its own disclosure, so it never sits in
 * the main shopping path. Everything it sends is labelled "Imported manually" by the server; nothing here is
 * presented as automated research.
 */
import { useState } from "react";
import type { PageEvidence, ResearchJob, SubmittedProduct } from "@contracts";
import { api, ApiError } from "../api";

interface Draft {
  retailer: string;
  productUrl: string;
  title: string;
  price: string;
  priceExcerpt: string;
  brand: string;
  brandExcerpt: string;
  condition: "unknown" | "new" | "used";
  sellerKind: "unknown" | "retailer" | "marketplace" | "resale";
  sizesAvailable: string;
  sizesUnavailable: string;
  matchType: "similar" | "exact";
}

const EMPTY: Draft = {
  retailer: "",
  productUrl: "",
  title: "",
  price: "",
  priceExcerpt: "",
  brand: "",
  brandExcerpt: "",
  condition: "unknown",
  sellerKind: "unknown",
  sizesAvailable: "",
  sizesUnavailable: "",
  matchType: "similar",
};

const words = (t: string) =>
  t
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

function toProduct(d: Draft, observedAt: string): SubmittedProduct {
  const minor = d.price.trim() ? Math.round(parseFloat(d.price.replace(/[^\d.]/g, "")) * 100) : NaN;
  // The page's own words back each field; the server keeps a brand only with its excerpt.
  const ev: PageEvidence[] = [];
  ev.push({ field: "title", excerpt: d.title.trim() });
  if (d.priceExcerpt.trim()) ev.push({ field: "price", excerpt: d.priceExcerpt.trim() });
  if (d.brand.trim() && d.brandExcerpt.trim()) ev.push({ field: "brand", excerpt: d.brandExcerpt.trim() });
  const variants = [
    ...words(d.sizesAvailable).map((label) => ({ label, available: true })),
    ...words(d.sizesUnavailable).map((label) => ({ label, available: false })),
  ];
  return {
    retailer: d.retailer.trim(),
    productUrl: d.productUrl.trim(),
    title: d.title.trim(),
    matchType: d.matchType,
    observedAt,
    ...(Number.isFinite(minor) && minor >= 0 ? { observedPrice: { amountMinor: minor, currency: "USD" } } : {}),
    ...(d.priceExcerpt.trim() ? { priceExcerpt: d.priceExcerpt.trim() } : {}),
    ...(d.brand.trim() ? { brand: d.brand.trim() } : {}),
    condition: d.condition,
    sellerKind: d.sellerKind,
    ...(variants.length ? { variants } : {}),
    evidence: ev as SubmittedProduct["evidence"],
  };
}

function importError(e: unknown): string {
  const err = e instanceof ApiError ? e : null;
  if (err?.code === "already_completed") return "This job already has results, so the import wasn't added.";
  if (err?.code === "rate_limited") return "Too many imports in the last 10 minutes. Try again shortly.";
  if (err?.code === "invalid_import" || err?.status === 422) return `${err?.message ?? "Import not accepted"}. Nothing was changed.`;
  return err?.message ?? "Couldn't import. Nothing was changed.";
}

export default function ManualImport({
  jobId,
  waiting,
  onImported,
}: {
  jobId: string;
  /** A manual-provider job waiting for this import (open by default), rather than a failed or expired one. */
  waiting: boolean;
  onImported: (job: ResearchJob) => void;
}) {
  const [drafts, setDrafts] = useState<Draft[]>([{ ...EMPTY }]);
  const [json, setJson] = useState<string | null>(null);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (i: number, patch: Partial<Draft>) => setDrafts((ds) => ds.map((d, j) => (j === i ? { ...d, ...patch } : d)));
  const complete = drafts.every((d) => d.retailer.trim() && d.productUrl.trim() && d.title.trim());

  const submit = async () => {
    setError(null);
    let products: SubmittedProduct[];
    if (json !== null) {
      try {
        const parsed = JSON.parse(json);
        products = Array.isArray(parsed) ? parsed : parsed?.products;
        if (!Array.isArray(products) || !products.length) throw new Error();
      } catch {
        return setError("Paste a JSON list of products, or an object with a products list.");
      }
    } else {
      const now = new Date().toISOString();
      products = drafts.map((d) => toProduct(d, now));
    }
    setBusy(true);
    try {
      onImported((await api.importResearch(jobId, products.slice(0, 20), notes.trim() || null)).job);
    } catch (e) {
      setError(importError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="manual-import" open={waiting}>
      <summary>
        <span className="mi-tag">Manual import</span> Add offers you found yourself
      </summary>
      <p className="muted small">
        {waiting
          ? "This server runs no automated research. "
          : "Research didn't return results. "}
        Offers you add here are labelled “Imported manually”, checked like any other result, and never shown as research agent output. ClipCart
        checks each link but doesn't open the page, so paste the page's own price text if you want the price counted as confirmed.
      </p>
      {json === null ? (
        <>
          {drafts.map((d, i) => (
            <fieldset key={i} className="mi-product">
              <legend>
                Offer {i + 1}
                {drafts.length > 1 && (
                  <button type="button" className="linkish" onClick={() => setDrafts((ds) => ds.filter((_, j) => j !== i))}>
                    Remove
                  </button>
                )}
              </legend>
              <div className="mi-grid">
                <label>
                  Store or seller*
                  <input value={d.retailer} maxLength={80} onChange={(e) => set(i, { retailer: e.target.value })} placeholder="e.g. Nordstrom" />
                </label>
                <label className="mi-wide">
                  Product page link (https)*
                  <input value={d.productUrl} inputMode="url" maxLength={500} onChange={(e) => set(i, { productUrl: e.target.value })} placeholder="https://…" />
                </label>
                <label className="mi-wide">
                  Title as the page shows it*
                  <input value={d.title} maxLength={200} onChange={(e) => set(i, { title: e.target.value })} />
                </label>
                <label>
                  Price (USD)
                  <input value={d.price} inputMode="decimal" maxLength={10} onChange={(e) => set(i, { price: e.target.value })} placeholder="e.g. 89.00" />
                </label>
                <label>
                  Price text from the page
                  <input value={d.priceExcerpt} maxLength={120} onChange={(e) => set(i, { priceExcerpt: e.target.value })} placeholder="e.g. Now $89.00" />
                </label>
                <label>
                  Brand
                  <input value={d.brand} maxLength={80} onChange={(e) => set(i, { brand: e.target.value })} />
                </label>
                <label>
                  Brand text from the page
                  <input value={d.brandExcerpt} maxLength={120} onChange={(e) => set(i, { brandExcerpt: e.target.value })} placeholder="kept only with this" />
                </label>
                <label>
                  Condition
                  <select value={d.condition} onChange={(e) => set(i, { condition: e.target.value as Draft["condition"] })}>
                    <option value="unknown">Not stated</option>
                    <option value="new">New</option>
                    <option value="used">Used or pre-owned</option>
                  </select>
                </label>
                <label>
                  Seller type
                  <select value={d.sellerKind} onChange={(e) => set(i, { sellerKind: e.target.value as Draft["sellerKind"] })}>
                    <option value="unknown">Not sure</option>
                    <option value="retailer">Retailer</option>
                    <option value="marketplace">Marketplace seller</option>
                    <option value="resale">Resale</option>
                  </select>
                </label>
                <label>
                  Sizes shown available
                  <input value={d.sizesAvailable} maxLength={120} onChange={(e) => set(i, { sizesAvailable: e.target.value })} placeholder="S, M" />
                </label>
                <label>
                  Sizes shown unavailable
                  <input value={d.sizesUnavailable} maxLength={120} onChange={(e) => set(i, { sizesUnavailable: e.target.value })} placeholder="L" />
                </label>
                <label>
                  Match
                  <select value={d.matchType} onChange={(e) => set(i, { matchType: e.target.value as Draft["matchType"] })}>
                    <option value="similar">Similar</option>
                    <option value="exact">I think it's the exact item</option>
                  </select>
                </label>
              </div>
            </fieldset>
          ))}
          <div className="mi-row">
            {drafts.length < 20 && (
              <button type="button" className="linkish" onClick={() => setDrafts((ds) => [...ds, { ...EMPTY }])}>
                + Add another offer
              </button>
            )}
            <button type="button" className="linkish" onClick={() => setJson("")}>
              Paste JSON instead
            </button>
          </div>
        </>
      ) : (
        <>
          <label className="mi-json">
            Products as JSON (the SubmittedProduct shape, up to 20)
            <textarea rows={6} value={json} onChange={(e) => setJson(e.target.value)} spellCheck={false} />
          </label>
          <button type="button" className="linkish" onClick={() => setJson(null)}>
            Use the form instead
          </button>
        </>
      )}
      <label className="mi-notes">
        Notes (optional)
        <input value={notes} maxLength={500} onChange={(e) => setNotes(e.target.value)} placeholder="Where you looked" />
      </label>
      <div className="mi-row">
        <button type="button" className="btn btn-sm" onClick={submit} disabled={busy || (json === null ? !complete : !json.trim())}>
          {busy ? "Importing…" : "Import offers"}
        </button>
      </div>
      {error && (
        <p className="research-error" role="alert">
          {error}
        </p>
      )}
    </details>
  );
}
