import { useEffect, useId, useRef, useState } from "react";
import type { Health } from "../types";

const LABEL: Record<string, string> = {
  live: "Live",
  unverified: "Key set, not yet verified",
  unavailable: "Not configured",
  fixture: "Fixture",
};

function Chip({ name, mode, note }: { name: string; mode: string; note?: string }) {
  return (
    <li className={`chip chip-${mode}`} title={note}>
      <span className="chip-dot" aria-hidden />
      <span className="chip-name">{name}</span>
      <span className="chip-mode">{note ?? LABEL[mode] ?? mode}</span>
    </li>
  );
}

/** True when detection or listings are simulated, so the header can say so without the full list. */
export function usesFixtures(health: Health | null) {
  if (!health) return false;
  return health.providers.perceptron.mode === "fixture" || health.providers.catalog.mode === "fixture";
}

function ModeList({ health }: { health: Health }) {
  const p = health.providers;
  const db = health.database.mode;
  return (
    <ul className="chips" aria-label="Service modes">
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
    </ul>
  );
}

/**
 * Header entry for service modes: a small Diagnostics button that opens the mode list.
 * A "Fixture data" tag stays on the button whenever detection or listings are simulated.
 */
export default function ModeChips({ health }: { health: Health | null }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const id = useId();

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      btn.current?.focus();
    };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  if (!health) return null;
  const fixtures = usesFixtures(health);
  return (
    <div className="diag-menu" ref={wrap}>
      <button
        ref={btn}
        type="button"
        className="diag-btn"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((o) => !o)}
      >
        <svg className="diag-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden>
          <path d="M1.5 8h3l2-5 3 10 2-5h3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="diag-word">Diagnostics</span>
        {fixtures && (
          <span className="diag-fixture">
            <span className="chip-dot" aria-hidden />
            <span className="diag-fixture-text">Fixture data</span>
          </span>
        )}
        <span className="diag-caret" aria-hidden>
          ▾
        </span>
      </button>
      {open && (
        <div className="diag-pop" id={id} role="region" aria-label="Service modes">
          <p className="diag-pop-note">“Live” means a real call succeeded since the server started.</p>
          <ModeList health={health} />
          <a className="diag-pop-link" href="#/diagnostics" onClick={() => setOpen(false)}>
            Open full diagnostics →
          </a>
        </div>
      )}
    </div>
  );
}
