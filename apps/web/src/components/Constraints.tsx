import { useEffect, useState } from "react";
import { isAccessory, ringSize } from "../categories";
import type { CategoryInfo, SessionWire } from "../types";

const MATERIALS = ["leather", "suede", "wool", "fur", "polyester"];
const SIZES = ["XS", "S", "M", "L", "XL"];
// Suggestions for watches and jewelry: appearance words the server matches, never metal claims.
const TONES = ["gold-tone", "silver-tone", "rose-gold-tone"];
const PLURAL: Record<string, string> = { watch: "watches", necklace: "necklaces", bracelet: "bracelets", earrings: "earrings", other: "this piece" };

export interface PrefsDraft {
  budget: string;
  size: string;
  ringSize: string;
  colors: string;
  excluded: string[];
  condition: "any" | "new" | "used";
}

export function draftFrom(s: SessionWire): PrefsDraft {
  const p = s.preferences;
  return {
    budget: p.maxItemPriceMinor == null ? "" : String(p.maxItemPriceMinor / 100),
    size: p.size?.raw ?? "",
    ringSize: p.ringSize?.raw ?? "",
    colors: (p.colors ?? []).join(", "),
    excluded: p.excludedMaterials ?? [],
    condition: (p.condition ?? "any") as PrefsDraft["condition"],
  };
}

export function patchFrom(d: PrefsDraft) {
  const budget = d.budget.trim() === "" ? null : Math.round(parseFloat(d.budget) * 100);
  const size = d.size.trim();
  const upper = size.toUpperCase();
  return {
    maxItemPriceMinor: budget !== null && Number.isFinite(budget) && budget >= 0 ? budget : null,
    size: size ? { raw: SIZES.includes(upper) || ["XXS", "XXL"].includes(upper) ? upper : size, system: SIZES.includes(upper) ? "alpha" : /^\d/.test(size) ? "numeric" : null } : null,
    ringSize: d.ringSize.trim() && ringSize(d.ringSize) ? { raw: ringSize(d.ringSize)!, system: "us" } : null,
    colors: d.colors
      .split(/[,/]/)
      .map((c) => c.trim().toLowerCase())
      .filter(Boolean)
      .slice(0, 6),
    excludedMaterials: d.excluded,
    condition: d.condition,
  };
}

export function findLabel(busy: boolean, canSearch: boolean, pieceLabel: string | null) {
  if (busy) return "Working…";
  if (!canSearch) return "Select a garment first";
  return pieceLabel ? `Find this ${pieceLabel.toLowerCase()}` : "Find it";
}

const colorList = (colors: string) =>
  colors
    .split(/[,/]/)
    .map((c) => c.trim().toLowerCase())
    .filter(Boolean);

export default function Constraints({
  session,
  category,
  canSearch,
  pieceLabel,
  busy,
  onSubmit,
}: {
  session: SessionWire;
  /** The selected piece's category; decides which size input applies. Null before anything is selected. */
  category: CategoryInfo | null;
  canSearch: boolean;
  pieceLabel: string | null;
  busy: boolean;
  onSubmit: (d: PrefsDraft) => void;
}) {
  const [d, setD] = useState<PrefsDraft>(() => draftFrom(session));
  const [custom, setCustom] = useState("");
  // Refinements change preferences server-side; reflect them here.
  useEffect(() => setD(draftFrom(session)), [session.revision]); // eslint-disable-line react-hooks/exhaustive-deps
  const budgetBad = d.budget.trim() !== "" && !(parseFloat(d.budget) >= 0);
  const rule = category?.sizeRule ?? "clothing";
  const ringBad = rule === "ring" && d.ringSize.trim() !== "" && !ringSize(d.ringSize);
  const accessory = isAccessory(category);
  const picked = colorList(d.colors);
  const toggleTone = (t: string) =>
    setD((x) => {
      const cs = colorList(x.colors);
      return { ...x, colors: (cs.includes(t) ? cs.filter((c) => c !== t) : [...cs, t]).join(", ") };
    });
  const toggle = (m: string) =>
    setD((x) => ({ ...x, excluded: x.excluded.includes(m) ? x.excluded.filter((y) => y !== m) : [...x.excluded, m] }));
  return (
    <form
      id="rules-form"
      className="constraints"
      onSubmit={(e) => {
        e.preventDefault();
        if (!budgetBad && !ringBad) onSubmit(d);
      }}
    >
      <div className="field">
        <label htmlFor="budget">Budget per item</label>
        <div className="input-prefix">
          <span>$</span>
          <input id="budget" inputMode="decimal" placeholder="No limit" value={d.budget} aria-invalid={budgetBad}
            onChange={(e) => setD({ ...d, budget: e.target.value.replace(/[^\d.]/g, "") })} />
        </div>
        <small className="muted">USD, item price only. Shipping and tax are not included.</small>
      </div>
      {rule === "clothing" && (
        <div className="field">
          <label htmlFor="size">Size</label>
          <input id="size" placeholder="e.g. M or 32" value={d.size} maxLength={12} onChange={(e) => setD({ ...d, size: e.target.value })} />
          <div className="pills" role="group" aria-label="Quick sizes">
            {SIZES.map((s) => (
              <button key={s} type="button" className={`pill ${d.size.toUpperCase() === s ? "pill-on" : ""}`} aria-pressed={d.size.toUpperCase() === s}
                onClick={() => setD({ ...d, size: d.size.toUpperCase() === s ? "" : s })}>
                {s}
              </button>
            ))}
          </div>
          <small className="muted">We never convert between size systems; other systems show as unknown.</small>
        </div>
      )}
      {rule === "ring" && (
        <div className="field">
          <label htmlFor="ring-size">Ring size (US)</label>
          <input id="ring-size" inputMode="decimal" placeholder="e.g. 7 or 6.5" value={d.ringSize} maxLength={6} aria-invalid={ringBad}
            aria-describedby="ring-size-help" onChange={(e) => setD({ ...d, ringSize: e.target.value })} />
          <small id="ring-size-help" className={ringBad ? "field-error" : "muted"}>
            {ringBad ? "Use a US ring size from 3 to 15, like 7 or 6.5." : "Used for rings only. Your clothing size isn't applied to rings."}
          </small>
        </div>
      )}
      {rule === "none" && category && (
        <p className="field field-note muted small">
          Sizes don't apply to {PLURAL[category.id] ?? category.label.toLowerCase()}, so your clothing size isn't used for this search.
        </p>
      )}
      <div className="field">
        <label htmlFor="colors">{accessory ? "Tone or colors you want" : "Colors you want"}</label>
        <input id="colors" placeholder={accessory ? "Any tone or color" : "Any color"} value={d.colors} onChange={(e) => setD({ ...d, colors: e.target.value })} />
        {accessory && (
          <>
            <div className="pills" role="group" aria-label="Tone suggestions">
              {TONES.map((t) => (
                <button key={t} type="button" className={`pill ${picked.includes(t) ? "pill-on" : ""}`} aria-pressed={picked.includes(t)} onClick={() => toggleTone(t)}>
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
            <small className="muted">Tone describes how it looks. ClipCart never judges metal, stones or authenticity.</small>
          </>
        )}
      </div>
      <fieldset className="field">
        <legend>Exclude materials</legend>
        <div className="pills">
          {[...new Set([...MATERIALS, ...d.excluded])].map((m) => (
            <button key={m} type="button" className={`pill ${d.excluded.includes(m) ? "pill-on pill-no" : ""}`} aria-pressed={d.excluded.includes(m)}
              onClick={() => toggle(m)}>
              {d.excluded.includes(m) ? `No ${m}` : m}
            </button>
          ))}
          <input className="pill-input" aria-label="Add a material to exclude" placeholder="+ other" value={custom}
            onChange={(e) => setCustom(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && custom.trim()) {
                e.preventDefault();
                const m = custom.trim().toLowerCase();
                if (!d.excluded.includes(m)) toggle(m);
                setCustom("");
              }
            }} />
        </div>
        {d.excluded.length > 0 && (
          <small className="muted">Listings rarely state composition, so most results will need checking.</small>
        )}
      </fieldset>
      <div className="field">
        <label htmlFor="condition">Condition</label>
        <select id="condition" value={d.condition} onChange={(e) => setD({ ...d, condition: e.target.value as PrefsDraft["condition"] })}>
          <option value="any">New or used</option>
          <option value="new">New only</option>
          <option value="used">Used only</option>
        </select>
      </div>
      <button className="btn btn-primary btn-block btn-find" type="submit" disabled={!canSearch || busy || budgetBad || ringBad}>
        {findLabel(busy, canSearch, pieceLabel)}
      </button>
    </form>
  );
}
