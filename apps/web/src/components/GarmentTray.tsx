import { mediaUrl, timestamp } from "../api";
import type { GarmentDoc, GarmentObservation } from "../types";

export default function GarmentTray({
  garments,
  observations,
  selectedId,
  onSelect,
  onRelabel,
  onRedraw,
  busy,
  detectionMode,
}: {
  garments: GarmentDoc[];
  observations: GarmentObservation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onRelabel: (id: string, category: string) => void;
  onRedraw: (g: GarmentDoc) => void;
  busy: boolean;
  detectionMode: string;
}) {
  if (!garments.length) return null;
  const obsById = Object.fromEntries(observations.map((o) => [o.id, o]));
  return (
    <ul className="tray" aria-label="Garments">
      {garments.map((g) => {
        const obs = g.observationIds.map((id) => obsById[id]).filter(Boolean) as GarmentObservation[];
        const first = obs[0];
        const sel = g.id === selectedId;
        const byUser = obs.some((o) => o.editedByUser);
        const ts = first ? timestamp(first.timestampMs) : null;
        const attrs = first ? Object.values(first.observedAttributes ?? {}).flat().slice(0, 3) : [];
        return (
          <li key={g.id} className={`tray-item ${sel ? "tray-on" : ""}`}>
            <button type="button" className="tray-pick" onClick={() => onSelect(g.id)} disabled={busy} aria-pressed={sel}>
              <img src={mediaUrl(g.representativeCropId)} alt={`Crop of ${g.label}`} />
              <span className="tray-text">
                <strong>{g.label.replace(" (your selection)", "").replace(" (edited)", "")}</strong>
                <small>
                  {byUser ? "Your box" : detectionMode === "fixture" ? "Fixture detection" : "Detected by Perceptron"}
                  {ts ? ` · ${ts}` : ""}
                  {obs.length > 1 ? ` · seen in ${obs.length} frames` : ""}
                </small>
                {attrs.length > 0 && <small className="muted">{attrs.join(", ")}</small>}
                {g.userDescription && <small className="muted">“{g.userDescription}”</small>}
              </span>
              {sel && <span className="tray-badge">Selected</span>}
            </button>
            {sel && (
              <div className="tray-tools">
                <label>
                  <span className="sr-only">Category</span>
                  <select value={g.category} onChange={(e) => onRelabel(g.id, e.target.value)} disabled={busy}>
                    <option value="jacket">Jacket</option>
                    <option value="top">Top</option>
                    <option value="pants">Pants</option>
                    <option value="bag">Bag</option>
                  </select>
                </label>
                <button type="button" className="btn btn-quiet btn-sm" onClick={() => onRedraw(g)} disabled={busy}>
                  Adjust crop
                </button>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
