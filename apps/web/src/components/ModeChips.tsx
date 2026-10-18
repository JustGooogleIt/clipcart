import type { Health } from "../types";

const LABEL: Record<string, string> = {
  live: "Live",
  unverified: "Key set, not yet verified",
  unavailable: "Not configured",
  fixture: "Fixture",
};

function Chip({ name, mode, note }: { name: string; mode: string; note?: string }) {
  return (
    <span className={`chip chip-${mode}`} title={note}>
      <span className="chip-dot" aria-hidden />
      <span className="chip-name">{name}</span>
      <span className="chip-mode">{note ?? LABEL[mode] ?? mode}</span>
    </span>
  );
}

export default function ModeChips({ health }: { health: Health | null }) {
  if (!health) return null;
  const p = health.providers;
  const db = health.database.mode;
  return (
    <div className="chips" aria-label="Service modes">
      <Chip name="Detection · Perceptron" mode={p.perceptron.mode} />
      <Chip
        name="Search agent"
        mode={p.grok.mode === "unavailable" ? "rule" : p.grok.mode}
        note={p.grok.mode === "unavailable" ? "Rule-based (Grok not configured)" : `Grok · ${LABEL[p.grok.mode] ?? p.grok.mode}`}
      />
      <Chip
        name="Listings"
        mode={p.catalog.mode === "unverified" ? "ready" : p.catalog.mode}
        note={
          p.catalog.mode === "fixture"
            ? "Fixture catalog"
            : `${p.catalog.provider === "solescout" ? "SoleScout" : p.catalog.provider} · ${p.catalog.mode === "live" ? "Live" : "Live API, no call yet"}`
        }
      />
      <Chip name="Storage" mode={db === "local_memory" ? "rule" : "live"} note={db === "local_memory" ? "Local dev store (not Atlas)" : db === "atlas" ? "MongoDB Atlas" : "MongoDB"} />
      <Chip
        name="YouTube URL"
        mode={health.features.youtubeDownload ? "live" : "unavailable"}
        note={
          health.features.youtubeDownload
            ? `On · ${health.youtube?.allowedVideoCount ?? 0} permitted clips`
            : "Off · upload clips instead"
        }
      />
      {health.features.styleMemory && (
        <Chip
          name="Style notes"
          mode={p.styleModel?.mode === "live" ? "live" : "rule"}
          // The model is only named as in use once a real call has succeeded, using the server's own label.
          note={p.styleModel?.mode === "live" ? `${p.styleModel.label ?? p.styleModel.model ?? "Style model"} · Live` : "Rule-based parser"}
        />
      )}
      <a className="chip chip-link" href="#/diagnostics">
        Diagnostics
      </a>
    </div>
  );
}
