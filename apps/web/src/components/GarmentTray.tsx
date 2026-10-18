import { mediaUrl, timestamp } from "../api";
import type { GarmentDoc, GarmentObservation } from "../types";

// The API caps stored labels at 80 characters, which can end mid-word.
const LABEL_CAP = 80;

/** Shorten at a word boundary with an ellipsis instead of cutting a word in half. */
export function wordSafe(text: string, max: number) {
  const t = text.trim();
  if (t.length <= max) return t;
  const cut = t.slice(0, max + 1);
  const at = cut.search(/\s\S*$/);
  return `${(at > max * 0.5 ? cut.slice(0, at) : t.slice(0, max)).replace(/[\s,;:.\-–—]+$/, "")}…`;
}

export function cleanLabel(label: string) {
  const raw = label.replace(" (your selection)", "").replace(" (edited)", "");
  // A label at the cap was probably cut by the API; drop the partial last word.
  const t = raw.length >= LABEL_CAP ? wordSafe(raw, LABEL_CAP - 2) : raw.trim();
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Honest label for where a garment's box came from. */
export function sourceLabel(byUser: boolean, detectionMode: string) {
  if (byUser) return "Your box";
  if (detectionMode === "fixture") return "Fixture detection";
  if (detectionMode === "live") return "Perceptron detection";
  return "Perceptron (not yet verified live)";
}

export default function GarmentTray({
  garments,
  observations,
  selectedId,
  onSelect,
  busy,
  detectionMode,
}: {
  garments: GarmentDoc[];
  observations: GarmentObservation[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  busy: boolean;
  detectionMode: string;
}) {
  if (!garments.length) return null;
  const obsById = Object.fromEntries(observations.map((o) => [o.id, o]));
  return (
    <div className="tray-wrap">
      <p className="tray-head">
        <span>Pieces in this scene</span>
        <small>{garments.length} found · tap one to shop it</small>
      </p>
      <ul className="tray" aria-label="Garments">
        {garments.map((g) => {
          const obs = g.observationIds.map((id) => obsById[id]).filter(Boolean) as GarmentObservation[];
          const first = obs[0];
          const sel = g.id === selectedId;
          const byUser = obs.some((o) => o.editedByUser);
          const ts = first ? timestamp(first.timestampMs) : null;
          return (
            <li key={g.id} className={`tray-item ${sel ? "tray-on" : ""}`}>
              <button
                type="button"
                className="tray-pick"
                data-garment={g.id}
                onClick={() => onSelect(g.id)}
                disabled={busy && !sel}
                aria-pressed={sel}
              >
                <span className="tray-img">
                  <img src={mediaUrl(g.representativeCropId)} alt="" />
                  {sel && <span className="tray-badge">Shopping</span>}
                </span>
                <span className="tray-text">
                  <strong>{cleanLabel(g.label)}</strong>
                  <small>
                    {sourceLabel(byUser, detectionMode)}
                    {ts ? ` · ${ts}` : ""}
                    {obs.length > 1 ? ` · ${obs.length} frames` : ""}
                  </small>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
