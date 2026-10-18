import { mediaUrl, timestamp } from "../api";
import { attrLabel, categoryOf, grouped, isAccessory } from "../categories";
import type { CategoryInfo, GarmentDoc, GarmentObservation } from "../types";
import { cleanLabel, sourceLabel } from "./GarmentTray";

/** Observed attributes for display, keyed by the category's attribute keys, merged across sightings. */
function attributes(obs: GarmentObservation[], cat: CategoryInfo | null) {
  const keys = cat?.attributeKeys ?? ["color", "pattern", "cut", "details"];
  return keys
    .map((k) => ({ key: k, values: [...new Set(obs.flatMap((o) => o.observedAttributes?.[k] ?? []))].slice(0, 4) }))
    .filter((a) => a.values.length);
}

export default function SelectedPiece({
  garment,
  observations,
  categories,
  detectionMode,
  busy,
  onRelabel,
  onRedraw,
}: {
  garment: GarmentDoc | null;
  observations: GarmentObservation[];
  categories: CategoryInfo[];
  detectionMode: string;
  busy: boolean;
  onRelabel: (id: string, category: string) => void;
  onRedraw: (g: GarmentDoc) => void;
}) {
  if (!garment) {
    return (
      <div className="piece piece-empty">
        <span className="piece-ghost" aria-hidden>
          ⬚
        </span>
        <div>
          <p className="piece-kicker">Nothing selected yet</p>
          <p className="piece-hint">Tap a box on the scene, or draw one around the piece you want, including a watch or jewelry. Only that piece is searched.</p>
        </div>
      </div>
    );
  }
  const obs = observations.filter((o) => garment.observationIds.includes(o.id));
  const byUser = obs.some((o) => o.editedByUser);
  const first = obs[0];
  const ts = first ? timestamp(first.timestampMs) : null;
  const cat = categoryOf(categories, garment.category);
  const attrs = attributes(obs, cat);
  const seenText = [...new Set(obs.flatMap((o) => o.visibleText ?? []))].slice(0, 4);
  const normalized = obs.some((o) => o.observedAttributes?.appearanceNormalized?.includes("true"));
  const accessory = isAccessory(cat);
  // A category the list doesn't know (e.g. an older server's list) still shows as the current value.
  const options = grouped(categories);
  const known = categories.some((c) => c.id === garment.category);
  return (
    <div className="piece">
      <img className="piece-img" src={mediaUrl(garment.representativeCropId)} alt={`Crop of ${cleanLabel(garment.label)}`} />
      <div className="piece-body">
        <p className="piece-kicker">Shopping for</p>
        <h2 className="piece-title">{cleanLabel(garment.label)}</h2>
        <p className="piece-meta">
          <span className={`src src-${byUser ? "user" : detectionMode}`}>{sourceLabel(byUser, detectionMode)}</span>
          {ts && <span>at {ts}</span>}
        </p>
        {attrs.length > 0 && (
          <dl className="attr-list" aria-label="Observed attributes">
            {attrs.map((a) => (
              <div key={a.key}>
                <dt>{attrLabel(cat, a.key)}</dt>
                <dd>
                  <ul className="attrs">
                    {a.values.map((v) => (
                      <li key={v}>{v}</li>
                    ))}
                  </ul>
                </dd>
              </div>
            ))}
          </dl>
        )}
        {seenText.length > 0 && (
          <p className="seen-text">
            <span className="seen-text-label">Text seen on the item</span>
            {seenText.map((t) => (
              <q key={t}>{t}</q>
            ))}
            <small>Lettering as it appears. Not a brand or authenticity claim.</small>
          </p>
        )}
        {accessory && (
          <p className="piece-note">
            Described by appearance only{normalized ? "; metal and stone words were reworded to tone and look" : ""}. ClipCart never judges
            metal, stones, brand or authenticity from a picture.
          </p>
        )}
        {garment.userDescription && <p className="piece-desc">“{garment.userDescription}”</p>}
        <div className="piece-tools">
          <label>
            <span className="sr-only">Category</span>
            <select value={garment.category} onChange={(e) => onRelabel(garment.id, e.target.value)} disabled={busy}>
              {!known && <option value={garment.category}>{garment.category}</option>}
              {options.map((g) => (
                <optgroup key={g.label} label={g.label}>
                  {g.items.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.id === "other" ? "Other / object" : c.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <button type="button" className="btn btn-quiet btn-sm" onClick={() => onRedraw(garment)} disabled={busy}>
            Adjust crop
          </button>
        </div>
      </div>
    </div>
  );
}
