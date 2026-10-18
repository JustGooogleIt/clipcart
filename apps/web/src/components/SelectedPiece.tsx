import { mediaUrl, timestamp } from "../api";
import type { GarmentDoc, GarmentObservation } from "../types";
import { cleanLabel, sourceLabel } from "./GarmentTray";

export default function SelectedPiece({
  garment,
  observations,
  detectionMode,
  busy,
  onRelabel,
  onRedraw,
}: {
  garment: GarmentDoc | null;
  observations: GarmentObservation[];
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
          <p className="piece-hint">Tap a box on the scene, or draw one around the piece you want. Only that piece is searched.</p>
        </div>
      </div>
    );
  }
  const obs = observations.filter((o) => garment.observationIds.includes(o.id));
  const byUser = obs.some((o) => o.editedByUser);
  const first = obs[0];
  const attrs = first ? Object.values(first.observedAttributes ?? {}).flat().slice(0, 5) : [];
  const ts = first ? timestamp(first.timestampMs) : null;
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
          <ul className="attrs" aria-label="Observed attributes">
            {attrs.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        )}
        {garment.userDescription && <p className="piece-desc">“{garment.userDescription}”</p>}
        <div className="piece-tools">
          <label>
            <span className="sr-only">Category</span>
            <select value={garment.category} onChange={(e) => onRelabel(garment.id, e.target.value)} disabled={busy}>
              <option value="jacket">Jacket</option>
              <option value="top">Top</option>
              <option value="pants">Pants</option>
              <option value="bag">Bag</option>
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
