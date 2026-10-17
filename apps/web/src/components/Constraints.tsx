import { useEffect, useState } from "react";
import type { SessionWire } from "../types";

const MATERIALS = ["leather", "suede", "wool", "fur", "polyester"];
const SIZES = ["XS", "S", "M", "L", "XL"];

export interface PrefsDraft {
  budget: string;
  size: string;
  colors: string;
  excluded: string[];
  condition: "any" | "new" | "used";
}

export function draftFrom(s: SessionWire): PrefsDraft {
  const p = s.preferences;
  return {
    budget: p.maxItemPriceMinor == null ? "" : String(p.maxItemPriceMinor / 100),
    size: p.size?.raw ?? "",
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
    colors: d.colors
      .split(/[,/]/)
      .map((c) => c.trim().toLowerCase())
      .filter(Boolean)
      .slice(0, 6),
    excludedMaterials: d.excluded,
    condition: d.condition,
  };
}

export default function Constraints({
  session,
  canSearch,
  busy,
  onSubmit,
}: {
  session: SessionWire;
  canSearch: boolean;
  busy: boolean;
  onSubmit: (d: PrefsDraft) => void;
}) {
  const [d, setD] = useState<PrefsDraft>(() => draftFrom(session));
  const [custom, setCustom] = useState("");
  // Refinements change preferences server-side; reflect them here.
  useEffect(() => setD(draftFrom(session)), [session.revision]); // eslint-disable-line react-hooks/exhaustive-deps
  const budgetBad = d.budget.trim() !== "" && !(parseFloat(d.budget) >= 0);
  const toggle = (m: string) =>
    setD((x) => ({ ...x, excluded: x.excluded.includes(m) ? x.excluded.filter((y) => y !== m) : [...x.excluded, m] }));
  return (
    <form
      className="constraints"
      onSubmit={(e) => {
        e.preventDefault();
        if (!budgetBad) onSubmit(d);
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
      <div className="field">
        <label htmlFor="colors">Colors you want</label>
        <input id="colors" placeholder="Any color" value={d.colors} onChange={(e) => setD({ ...d, colors: e.target.value })} />
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
      <button className="btn btn-primary btn-block" type="submit" disabled={!canSearch || busy || budgetBad}>
        {busy ? "Starting…" : canSearch ? "Find it" : "Select a garment first"}
      </button>
    </form>
  );
}
