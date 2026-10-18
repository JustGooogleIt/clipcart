import { useEffect, useId, useRef, useState } from "react";
import type { Health, ProviderSnapshot } from "../types";
import { researchProvider } from "./Research";

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

/**
 * Health wording that matches the server's semantics (services/api/app/providers/status.py):
 * fixture = simulated data; unavailable = not configured; unverified = configured, no successful call since the
 * server started; live = at least one real call succeeded since then (later calls may still fail, so the latest
 * result is shown too).
 */
function health(s: ProviderSnapshot, notYet: string): { mode: string; note: string } {
  if (s.mode === "fixture") return { mode: "fixture", note: "Fixture (simulated data)" };
  if (s.mode === "unavailable") return { mode: "unavailable", note: "Not configured" };
  const latestFailed = s.recent?.[0] ? !s.recent[0].ok : false;
  if (s.mode === "live") return latestFailed ? { mode: "unverified", note: "Worked earlier · latest call failed" } : { mode: "live", note: "Live" };
  return s.failures > 0 ? { mode: "unverified", note: "Configured · calls failing" } : { mode: "unverified", note: notYet };
}

/** True when detection or listings are simulated, so the header can say so without the full list. */
export function usesFixtures(health: Health | null) {
  if (!health) return false;
  return (
    health.providers.perceptron.mode === "fixture" ||
    health.providers.catalog.mode === "fixture" ||
    researchProvider(health)?.mode === "fixture"
  );
}

function ModeList({ health: hp }: { health: Health }) {
  const p = hp.providers;
  const db = hp.database.mode;
  const det = health(p.perceptron, "Key set, no successful call yet");
  const grok = health(p.grok, "Key set, no successful call yet");
  const cat = health(p.catalog, "No successful call yet");
  const catName = p.catalog.provider === "solescout" ? "SoleScout" : p.catalog.provider;
  const store =
    db === "local_memory"
      ? { mode: "rule", note: "Local dev store (not Atlas)" }
      : { mode: hp.database.ok ? "live" : "unavailable", note: `${db === "atlas" ? "MongoDB Atlas" : "MongoDB"} · ${hp.database.ok ? "reachable" : "not reachable"}` };
  return (
    <ul className="chips" aria-label="Service modes">
      <Chip name="Detection · Perceptron" mode={det.mode} note={det.note} />
      {p.grok.mode === "unavailable" ? (
        <Chip name="Search agent" mode="rule" note="Rule-based (Grok not configured)" />
      ) : (
        <Chip name="Search agent" mode={grok.mode} note={`Grok · ${grok.note}`} />
      )}
      {p.catalog.mode === "fixture" ? (
        <Chip name="Listings" mode="fixture" note="Fixture catalog (simulated data)" />
      ) : (
        <Chip name="Listings" mode={cat.mode} note={`${catName} · ${cat.note}`} />
      )}
      <Chip name="Storage" mode={store.mode} note={store.note} />
      <Chip
        name="YouTube URL"
        mode={hp.features.youtubeDownload ? "live" : "unavailable"}
        note={
          hp.features.youtubeDownload
            ? `On · ${hp.youtube?.allowedVideoCount ?? 0} permitted clips`
            : "Off · upload clips instead"
        }
      />
      <Chip
        name="Watches and jewelry"
        mode={hp.features.accessoryDetection ? (det.mode === "fixture" ? "fixture" : "unverified") : "unavailable"}
        note={
          hp.features.accessoryDetection
            ? det.mode === "fixture"
              ? "On · fixture detection"
              : "On · not yet checked live"
            : "Off · box them or use Find"
        }
      />
      <ResearchChip health={hp} catalogMode={p.catalog.mode === "fixture" ? "fixture" : cat.mode} />
      {hp.features.styleMemory && (
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

/** Research jobs: off, or which provider runs them. A bridge provider reads Live only once a job of its completed. */
function ResearchChip({ health: hp, catalogMode }: { health: Health; catalogMode: string }) {
  const r = researchProvider(hp);
  if (!r) return <Chip name="More offers" mode="unavailable" note="Off" />;
  // Health reports the mode jobs get; manual import runs nothing, and null means the provider isn't implemented here.
  // "live" only says jobs aren't fixtures: the SoleScout fallback is as healthy as the catalog it calls, and any other
  // live provider stays unverified until it has returned results.
  const mode =
    r.mode === "manual"
      ? "rule"
      : r.mode === "live"
        ? r.id === "solescout"
          ? catalogMode
          : hp.research?.status === "operational"
            ? "live"
            : "unverified"
        : (r.mode ?? "unavailable");
  return <Chip name="More offers" mode={mode} note={r.name} />;
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
          <p className="diag-pop-note">
            Live: a real call succeeded since this server started (Style notes: its latest call succeeded). Fixture:
            simulated data. These reset when the server restarts.
          </p>
          <ModeList health={health} />
          <a className="diag-pop-link" href="#/diagnostics" onClick={() => setOpen(false)}>
            Open full diagnostics →
          </a>
        </div>
      )}
    </div>
  );
}
