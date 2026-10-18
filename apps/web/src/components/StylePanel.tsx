import { useEffect, useRef, useState } from "react";
import { ago, money } from "../api";
import {
  MemoryError,
  STYLE_VOCAB,
  memoryApi,
  type Interpretations,
  noteReader,
  noteResultReader,
  type MemoryKind,
  type MemoryState,
  type StyleEvent,
  type StyleMemory,
  type StyleModelInfo,
  type StyleNoteResult,
  type StyleProposal,
} from "../memory";

const KIND: Record<MemoryKind, string> = {
  size: "Size",
  fit: "Fit",
  budget_max: "Budget",
  color_like: "Likes",
  color_avoid: "Avoids",
  material_like: "Likes",
  material_avoid: "Avoids",
  brand_like: "Likes",
  brand_avoid: "Avoids",
  // Accessory kinds (docs/contracts/accessories.md): tone applies to watches and jewelry only.
  tone_like: "Likes",
  tone_avoid: "Avoids",
  ring_size: "Ring size (US)",
  // Style kinds (docs/contracts/style-memory.md, v2), shown as chips.
  style_like: "Likes",
  style_avoid: "Avoids",
};
const OPPOSITE: Partial<Record<MemoryKind, MemoryKind>> = {
  style_like: "style_avoid",
  style_avoid: "style_like",
  tone_like: "tone_avoid",
  tone_avoid: "tone_like",
};
const FIT: Record<string, string> = { womens: "Women's", mens: "Men's", unisex: "Unisex" };

/** Display text for a memory value, from the contract's shapes. */
export function valueText(kind: MemoryKind, v: unknown): string {
  if ((kind === "size" || kind === "ring_size") && v && typeof v === "object") return String((v as { raw?: string }).raw ?? "");
  if (kind === "budget_max" && v && typeof v === "object") {
    const b = v as { amountMinor?: number; currency?: string };
    return `Up to ${money(b.amountMinor, b.currency ?? "USD")} per item`;
  }
  if (kind === "fit") return FIT[String(v)] ?? String(v);
  if (kind === "tone_like" || kind === "tone_avoid") {
    const t = String(v ?? "");
    return `${t.charAt(0).toUpperCase()}${t.slice(1)} (watches and jewelry)`;
  }
  return String(v ?? "");
}

/** What the correction box starts with: the bare value the server accepts back. */
function editText(kind: MemoryKind, v: unknown): string {
  if (kind === "budget_max" && v && typeof v === "object") return String(((v as { amountMinor?: number }).amountMinor ?? 0) / 100);
  return kind === "fit" ? String(v ?? "") : valueText(kind, v);
}

// Every memory says where it came from. Inferred ones say so and how much evidence they rest on.
function sourceText(m: StyleMemory, modelRanks = false): string {
  if (m.origin === "stated") {
    if (m.source === "style_note") return "From your style note";
    if (m.source === "style_panel") return "You corrected this";
    if (m.source === "chat_refinement") return "From what you typed in Refine";
    return "You set this";
  }
  const n = m.evidenceCount;
  if (m.source === "saved_items") return `Inferred from ${n} saved item${n === 1 ? "" : "s"}`;
  if (m.source === "rejected_items") return `Inferred from ${n} item${n === 1 ? "" : "s"} you hid`;
  if (m.source === "purchases") return `Inferred from ${n} item${n === 1 ? "" : "s"} you said you bought`;
  if (m.source === "model_interpretation")
    return `Suggested by the style model from your saves${modelRanks ? "" : " (doesn't affect ranking)"}`;
  return "Inferred";
}

/** Contract bands: High ≥ 0.7, Medium ≥ 0.45, otherwise Low. Stated memories are the shopper's word, not a score. */
export function confidenceLabel(m: Pick<StyleMemory, "origin" | "confidence">): { band: "stated" | "high" | "medium" | "low"; text: string } | null {
  if (m.origin === "stated") return { band: "stated", text: "You said so" };
  if (m.confidence == null) return null;
  const band = m.confidence >= 0.7 ? "high" : m.confidence >= 0.45 ? "medium" : "low";
  return { band, text: `${band.charAt(0).toUpperCase()}${band.slice(1)} confidence` };
}

const EVIDENCE_TYPE: Record<string, string> = {
  saved_item: "You saved",
  rejected_item: "You hid",
  user_confirmed_purchase: "You said you bought",
  verified_order: "Verified order",
  explicit_preference: "You said",
};
const shortDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });

/** Why ClipCart believes a memory: confidence, the latest evidence date and each excerpt with its date. */
function Evidence({ m }: { m: StyleMemory }) {
  const conf = confidenceLabel(m);
  const ev = m.evidence ?? [];
  return (
    <div className="mem-evidence">
      <p>
        {conf && <span className={`conf conf-${conf.band}`}>{conf.text}</span>}
        {m.lastEvidenceAt && <span className="mem-when"> · latest evidence {shortDate(m.lastEvidenceAt)}</span>}
      </p>
      {ev.length > 0 ? (
        <ul>
          {ev.map((e) => (
            <li key={e.eventId}>
              <span className="ev-type">{EVIDENCE_TYPE[e.type] ?? e.type}</span> {shortDate(e.at)}
              {e.excerpt && (
                <>
                  {": "}
                  <q>{e.excerpt}</q>
                </>
              )}
            </li>
          ))}
        </ul>
      ) : (
        m.origin === "inferred" && <p className="mem-note">No evidence excerpts kept for this one.</p>
      )}
    </div>
  );
}

const EVENT_SOURCE: Partial<Record<StyleEvent["type"], string>> = {
  saved_item: "You saved this · interest, not ownership",
  rejected_item: "You marked this Not for me",
  retailer_click: "Opened retailer link · not a purchase",
  user_confirmed_purchase: "You said you bought this · not verified by ClipCart",
  verified_order: "Verified ClipCart demo order",
};

const failText = (e: unknown, fallback: string) =>
  e instanceof MemoryError && e.code === "invalid_memory"
    ? "ClipCart doesn't recognize that value. Use a plain color, material, brand, size or amount."
    : fallback;

function MemoryRow({ m, modelRanks, onChanged }: { m: StyleMemory; modelRanks: boolean; onChanged: () => void }) {
  const [editing, setEditing] = useState(false);
  const [why, setWhy] = useState(false);
  const conf = confidenceLabel(m);
  const [confirming, setConfirming] = useState(false);
  const [value, setValue] = useState(editText(m.kind, m.value));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    const v = value.trim();
    if (!v || v === editText(m.kind, m.value)) return setEditing(false);
    setBusy(true);
    setError(null);
    try {
      // A correction is a new stated memory. One-active kinds replace the old one on the server; for
      // like/avoid lists, the old value is removed so it isn't kept alongside the correction.
      await memoryApi.state(m.kind, m.kind === "budget_max" ? v.replace(/^\$\s*/, "") : v);
      if (!["size", "fit", "budget_max"].includes(m.kind)) await memoryApi.remove(m.id);
      setEditing(false);
      onChanged();
    } catch (e) {
      setError(failText(e, "Couldn't save. The memory service may be offline."));
      setBusy(false);
    }
  };
  const remove = async () => {
    setBusy(true);
    setError(null);
    try {
      await memoryApi.remove(m.id);
      onChanged();
    } catch {
      setError("Couldn't remove. The memory service may be offline.");
      setBusy(false);
    }
  };

  return (
    <li className={`mem mem-${m.kind} mem-${m.origin}`}>
      <div className="mem-text">
        {editing ? (
          <form
            className="mem-edit"
            onSubmit={(e) => {
              e.preventDefault();
              void save();
            }}
          >
            <label className="sr-only" htmlFor={`mem-${m.id}`}>
              Correct {KIND[m.kind].toLowerCase()}
            </label>
            {m.kind === "fit" ? (
              <select id={`mem-${m.id}`} value={value} onChange={(e) => setValue(e.target.value)} disabled={busy}>
                {Object.entries(FIT).map(([k, label]) => (
                  <option key={k} value={k}>
                    {label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id={`mem-${m.id}`}
                value={value}
                maxLength={40}
                inputMode={m.kind === "budget_max" ? "decimal" : undefined}
                autoFocus
                onChange={(e) => setValue(e.target.value)}
                disabled={busy}
              />
            )}
            <button className="btn btn-primary btn-sm" type="submit" disabled={busy || !value.trim()}>
              Save
            </button>
            <button
              className="btn btn-quiet btn-sm"
              type="button"
              onClick={() => {
                setValue(editText(m.kind, m.value));
                setEditing(false);
                setError(null);
              }}
            >
              Cancel
            </button>
          </form>
        ) : (
          <strong className="mem-value">
            {m.kind !== "budget_max" && <span className="mem-key">{KIND[m.kind]}</span>}
            {valueText(m.kind, m.value)}
          </strong>
        )}
        <span className="mem-source">
          <span className={`src src-${m.origin}`}>{sourceText(m, modelRanks)}</span>
          {conf && m.origin === "inferred" && <span className={`conf conf-${conf.band}`}>{conf.text}</span>}
          <span className="mem-when"> · {ago(m.updatedAt)}</span>
          {m.origin === "inferred" && (
            <>
              {" · "}
              <button type="button" className="linkish" aria-expanded={why} onClick={() => setWhy(!why)}>
                {why ? "Hide why" : "Why?"}
              </button>
            </>
          )}
        </span>
        {why && <Evidence m={m} />}
      </div>
      {!editing && (
        <div className="mem-actions">
          {!confirming && (
            <button type="button" className="linkish" onClick={() => setEditing(true)} disabled={busy}>
              Correct
            </button>
          )}
          {confirming ? (
            <>
              <button type="button" className="btn btn-sm mem-danger" onClick={remove} disabled={busy}>
                Forget it
              </button>
              <button type="button" className="linkish" onClick={() => setConfirming(false)} disabled={busy}>
                Keep
              </button>
            </>
          ) : (
            <button type="button" className="linkish" onClick={() => setConfirming(true)} disabled={busy}>
              Remove
            </button>
          )}
        </div>
      )}
      {error && (
        <p className="mem-error" role="alert">
          {error}
        </p>
      )}
    </li>
  );
}

function EventRow({ ev, bought, onChanged }: { ev: StyleEvent; bought: boolean; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const it = ev.item;
  const run = async (f: () => Promise<unknown>, msg: string) => {
    setBusy(true);
    setError(null);
    try {
      await f();
      onChanged();
    } catch {
      setError(msg);
      setBusy(false);
    }
  };
  const recId = it?.recommendationId;
  return (
    <li className={`mem mem-ev-${ev.type}`}>
      <div className="mem-text">
        <strong className="mem-title">{it?.title ?? "Item"}</strong>
        <span className="mem-sub">{[it?.brand, it?.domain, it?.condition && it.condition !== "unknown" ? it.condition : null].filter(Boolean).join(" · ")}</span>
        {!!it?.styleFacts?.length && (
          <ul className="style-facts" aria-label="Style words in the listing">
            {it.styleFacts.map((f) => (
              <li key={`${f.tag}-${f.excerpt}`} title={`From the listing ${f.field}: “${f.excerpt}”`}>
                {f.tag}
                <small>
                  {" "}
                  “{f.excerpt}”
                </small>
              </li>
            ))}
          </ul>
        )}
        <span className="mem-source">
          <span className={`src src-ev-${ev.type}`}>{EVENT_SOURCE[ev.type] ?? ev.type}</span>
          <span className="mem-when"> · {ago(ev.occurredAt)}</span>
        </span>
      </div>
      <div className="mem-actions">
        {ev.type === "retailer_click" &&
          (bought ? (
            <span className="mem-tag">In Purchases</span>
          ) : recId ? (
            <button
              type="button"
              className="btn btn-sm mem-buy"
              disabled={busy}
              onClick={() => run(() => memoryApi.event("user_confirmed_purchase", recId), "Couldn't record that. The memory service may be offline.")}
            >
              I bought this
            </button>
          ) : null)}
        {ev.type !== "verified_order" && (
          <button
            type="button"
            className="linkish"
            disabled={busy}
            onClick={() => run(() => memoryApi.removeEvent(ev.id), "Couldn't remove. The memory service may be offline.")}
          >
            {ev.type === "rejected_item" ? "Unhide" : "Remove"}
          </button>
        )}
      </div>
      {error && (
        <p className="mem-error" role="alert">
          {error}
        </p>
      )}
    </li>
  );
}

function StyleNote({ model, memories, onSaved }: { model: StyleModelInfo; memories: StyleMemory[]; onSaved: () => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<StyleNoteResult | null>(null);
  const [keep, setKeep] = useState<boolean[]>([]);
  const [error, setError] = useState<string | null>(null);

  const read = async () => {
    setBusy(true);
    setError(null);
    try {
      const r = await memoryApi.note(text.trim());
      setResult(r);
      setKeep((r.proposals ?? []).map(() => true));
    } catch {
      setError("Couldn't read that note. The memory service may be offline.");
    } finally {
      setBusy(false);
    }
  };
  const save = async () => {
    if (!result) return;
    setBusy(true);
    setError(null);
    try {
      for (const [i, p] of (result.proposals ?? []).entries()) {
        if (!keep[i]) continue;
        if (p.action !== "remove") await memoryApi.state(p.kind, p.value, "style_note");
        else {
          const same = memories.find((m) => m.kind === p.kind && JSON.stringify(m.value).toLowerCase() === JSON.stringify(p.value).toLowerCase());
          if (same) await memoryApi.remove(same.id);
        }
      }
      setResult(null);
      setText("");
      onSaved();
    } catch (e) {
      setError(failText(e, "Couldn't save. The memory service may be offline."));
    } finally {
      setBusy(false);
    }
  };
  const describe = (p: StyleProposal) => `${p.action === "remove" ? "Forget: " : ""}${KIND[p.kind]} ${valueText(p.kind, p.value)}`;

  return (
    <section className="mem-section mem-note-box">
      <h3>Tell ClipCart your style</h3>
      <p className="mem-note">Nothing is saved until you confirm it. Read by: {noteReader(model)}.</p>
      <form
        className="mem-edit"
        onSubmit={(e) => {
          e.preventDefault();
          if (text.trim().length >= 2) void read();
        }}
      >
        <label className="sr-only" htmlFor="style-note">
          Style note
        </label>
        <input
          id="style-note"
          value={text}
          maxLength={500}
          placeholder="e.g. I'm a medium, I hate orange, no leather"
          onChange={(e) => setText(e.target.value)}
          disabled={busy}
        />
        <button className="btn btn-sm" type="submit" disabled={busy || text.trim().length < 2}>
          {busy && !result ? "Reading…" : "Read it"}
        </button>
      </form>
      {result && (
        <div className="mem-proposals" role="status">
          <p className="mem-note">
            Read by {noteResultReader(result, model)}.{" "}
            {result.proposals?.length ? "Untick anything that's wrong, then save." : "Nothing ClipCart can remember was found in that note."}
          </p>
          {!!result.proposals?.length && (
            <>
              <ul className="mem-list">
                {result.proposals.map((p, i) => (
                  <li key={i} className="mem mem-proposal">
                    <label>
                      <input
                        type="checkbox"
                        checked={keep[i] ?? false}
                        onChange={(e) => setKeep((k) => k.map((x, j) => (j === i ? e.target.checked : x)))}
                      />
                      <span>
                        <strong>{describe(p)}</strong>
                        <span className="mem-source"> · from “{p.quote}”</span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
              <div className="mem-actions">
                <button type="button" className="linkish" onClick={() => setResult(null)} disabled={busy}>
                  Discard
                </button>
                <button type="button" className="btn btn-primary btn-sm" onClick={save} disabled={busy || !keep.some(Boolean)}>
                  Save selected
                </button>
              </div>
            </>
          )}
        </div>
      )}
      {error && (
        <p className="mem-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

const TONE_VOCAB = ["gold-tone", "silver-tone", "rose-gold-tone", "black", "two-tone"] as const;

interface ChipGroup {
  like: "style_like" | "tone_like";
  avoid: "style_avoid" | "tone_avoid";
  vocab: readonly string[];
  title: string;
  note: string;
  noun: string;
  empty: string;
}
const STYLE_GROUP: ChipGroup = {
  like: "style_like",
  avoid: "style_avoid",
  vocab: STYLE_VOCAB,
  title: "Style",
  note: "Styles you like or avoid. They reorder results and never change your rules. Tap one to see why.",
  noun: "style",
  empty: "No styles yet. Add one below, or save a few results you like.",
};
const TONE_GROUP: ChipGroup = {
  like: "tone_like",
  avoid: "tone_avoid",
  vocab: TONE_VOCAB,
  title: "Tone for watches and jewelry",
  note: "How metal-look pieces should look. Used only for watch and jewelry searches; it never says what a piece is made of.",
  noun: "tone",
  empty: "No tone preferences.",
};

/** Likes and avoids as chips; each opens to its evidence, confidence and date, with switch and remove. */
function PrefChips({
  group,
  memories,
  interpretations,
  onChanged,
}: {
  group: ChipGroup;
  memories: StyleMemory[];
  interpretations: Interpretations | null;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [add, setAdd] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const styles = memories.filter((m) => m.kind === group.like || m.kind === group.avoid);
  const taken = new Set(styles.map((m) => String(m.value)));
  const fromModel = styles.some((m) => m.source === "model_interpretation");
  const active = styles.find((m) => m.id === open) ?? null;

  const run = async (f: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await f();
      setOpen(null);
      onChanged();
    } catch (e) {
      setError(failText(e, "Couldn't save. The memory service may be offline."));
    } finally {
      setBusy(false);
    }
  };
  // Correction is post-then-delete, so a failed delete leaves both visible rather than neither.
  const flip = (m: StyleMemory) =>
    run(async () => {
      await memoryApi.state(OPPOSITE[m.kind]!, m.value);
      await memoryApi.remove(m.id);
    });

  return (
    <section className="mem-section">
      <h3>{group.title}</h3>
      <p className="mem-note">{group.note}</p>
      {styles.length ? (
        <ul className="style-chips">
          {styles.map((m) => {
            const conf = confidenceLabel(m);
            const like = m.kind === group.like;
            return (
              <li key={m.id}>
                <button
                  type="button"
                  className={`style-chip ${like ? "sc-like" : "sc-avoid"} sc-${m.origin} ${open === m.id ? "sc-open" : ""}`}
                  aria-expanded={open === m.id}
                  onClick={() => setOpen(open === m.id ? null : m.id)}
                >
                  <span aria-hidden>{like ? "♥" : "✕"}</span>
                  <span className="sr-only">{like ? "Likes" : "Avoids"}</span> {String(m.value)}
                  {conf && m.origin === "inferred" && <span className={`conf-dot conf-${conf.band}`} title={conf.text} aria-label={conf.text} />}
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="mem-empty">{group.empty}</p>
      )}
      {active && (
        <div className="style-chip-detail" role="region" aria-label={`About ${String(active.value)}`}>
          <p>
            <strong>
              {active.kind === group.like ? "Likes" : "Avoids"} {String(active.value)}
            </strong>{" "}
            <span className={`src src-${active.origin}`}>{active.source === "style_panel" ? "You set this" : sourceText(active, !!interpretations?.rankingInfluence)}</span>
            <span className="mem-when"> · {ago(active.updatedAt)}</span>
          </p>
          {active.source === "model_interpretation" && (
            <p className="mem-note">
              {interpretations?.rankingInfluence
                ? "The style model's suggestions are allowed to reorder results on this server."
                : "The style model's suggestions don't change your results' order while ranking from them is off."}
            </p>
          )}
          <Evidence m={active} />
          <div className="mem-actions">
            <button type="button" className="btn btn-sm" disabled={busy} onClick={() => flip(active)}>
              {active.kind === group.like ? "Switch to avoid" : "Switch to like"}
            </button>
            <button type="button" className="linkish" disabled={busy} onClick={() => run(() => memoryApi.remove(active.id))}>
              Remove
            </button>
          </div>
        </div>
      )}
      <form
        className="mem-edit style-add"
        onSubmit={(e) => {
          e.preventDefault();
        }}
      >
        <label className="sr-only" htmlFor={`${group.noun}-add`}>
          Add a {group.noun}
        </label>
        <select id={`${group.noun}-add`} value={add} onChange={(e) => setAdd(e.target.value)} disabled={busy}>
          <option value="">Add a {group.noun}…</option>
          {group.vocab.filter((v) => !taken.has(v)).map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
        <button type="button" className="btn btn-sm" disabled={!add || busy} onClick={() => run(async () => (await memoryApi.state(group.like, add), setAdd("")))}>
          I like it
        </button>
        <button type="button" className="btn btn-quiet btn-sm" disabled={!add || busy} onClick={() => run(async () => (await memoryApi.state(group.avoid, add), setAdd("")))}>
          Not for me
        </button>
      </form>
      {group.like === "style_like" && (fromModel || interpretations) && <ModelLine interpretations={interpretations} />}
      {error && (
        <p className="mem-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

/** What reads saves for style suggestions. Names a model only once a real call succeeded. */
function ModelLine({ interpretations: it }: { interpretations: Interpretations | null }) {
  if (!it) return null;
  const m = it.styleModel;
  const live = m?.mode === "live";
  const who = live ? (m?.label ?? m?.model ?? "The style model") : null;
  let text: string;
  if (it.status === "waiting_for_model" || (!live && m?.mode === "unavailable"))
    text = "No style model is running, so only ClipCart's fixed rules suggest styles: two saves, or one purchase, with the style word in the listing.";
  else if (!live) text = "A style model is set up but hasn't answered yet. Until it does, only ClipCart's fixed rules suggest styles.";
  else text = `${who} reads new saves and suggests styles, checked against each listing's own words.`;
  return (
    <p className="mem-note mem-model">
      {text}
      {it.pendingEvents > 0 && live ? ` ${it.pendingEvents} new item${it.pendingEvents === 1 ? "" : "s"} waiting to be read.` : ""}
    </p>
  );
}

function Section({ title, note, empty, children }: { title: string; note?: string; empty: string; children: React.ReactNode[] }) {
  return (
    <section className="mem-section">
      <h3>{title}</h3>
      {note && <p className="mem-note">{note}</p>}
      {children.length ? <ul className="mem-list">{children}</ul> : <p className="mem-empty">{empty}</p>}
    </section>
  );
}

export default function StylePanel({
  open,
  onClose,
  memory,
  onReload,
}: {
  open: boolean;
  onClose: () => void;
  memory: MemoryState;
  onReload: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  let body: React.ReactNode;
  if (memory.state === "loading") {
    body = (
      <p className="mem-status" role="status">
        <span className="spinner" aria-hidden /> Loading what ClipCart remembers…
      </p>
    );
  } else if (memory.state === "unavailable") {
    body = (
      <div className="mem-offline" role="status">
        <p>
          <strong>{memory.message}</strong> Shopping works as usual: searches use only the rules you set, and nothing new is remembered.
        </p>
        {memory.reason === "offline" && (
          <button type="button" className="btn btn-sm" onClick={onReload}>
            Try again
          </button>
        )}
      </div>
    );
  } else {
    const ms = memory.memories;
    const of = (...k: MemoryKind[]) => ms.filter((m) => k.includes(m.kind));
    const evs = (t: StyleEvent["type"]) => memory.events.filter((e) => e.type === t);
    const purchases = [...evs("user_confirmed_purchase"), ...evs("verified_order")];
    const bought = new Set(purchases.map((e) => e.item?.listingId).filter(Boolean));
    const row = (m: StyleMemory) => <MemoryRow key={`${m.id}:${m.updatedAt}`} m={m} modelRanks={!!memory.interpretations?.rankingInfluence} onChanged={onReload} />;
    const evRow = (e: StyleEvent) => <EventRow key={e.id} ev={e} bought={!!e.item?.listingId && bought.has(e.item.listingId)} onChanged={onReload} />;
    body = (
      <>
        <StyleNote model={memory.styleModel} memories={ms} onSaved={onReload} />
        <Section title="Sizes and fit" note="Clothing size is never used for watches or jewelry; ring size is used for rings only." empty="No size remembered. Say it in a style note above.">
          {of("size", "fit", "ring_size").map(row)}
        </Section>
        <Section title="Budget" empty="No budget remembered.">
          {of("budget_max").map(row)}
        </Section>
        <Section
          title="Preferences"
          note="These reorder results. They never add or loosen the rules you set for a search."
          empty="No preferences remembered."
        >
          {of("color_like", "color_avoid", "material_like", "material_avoid", "brand_like", "brand_avoid").map(row)}
        </Section>
        <PrefChips group={STYLE_GROUP} memories={ms} interpretations={memory.interpretations} onChanged={onReload} />
        <PrefChips group={TONE_GROUP} memories={ms} interpretations={memory.interpretations} onChanged={onReload} />
        <div className="wardrobe">
          <h3 className="wardrobe-title">Wardrobe</h3>
          <Section title="Owned (you said)" note="Items you told ClipCart you own or bought. ClipCart doesn't verify them." empty="Nothing yet. Opening a retailer link doesn't count.">
            {evs("user_confirmed_purchase").map(evRow)}
          </Section>
          <Section title="Owned (verified)" note="Paid ClipCart demo orders only. ClipCart can't see retailer orders." empty="No verified orders.">
            {evs("verified_order").map(evRow)}
          </Section>
          <Section title="Saved (interest)" note="Saving shows interest. It never counts as owning something." empty="Nothing saved. Press Save on a result to keep it here.">
            {evs("saved_item").map(evRow)}
          </Section>
          <Section title="Hidden" note="Offers you marked Not for me. They stay out of your results until you unhide them." empty="Nothing hidden.">
            {evs("rejected_item").map(evRow)}
          </Section>
          <Section title="Opened links (not purchases)" note="Opening a link is not a purchase. If you bought it, say so and it moves to Owned (you said)." empty="No links opened yet.">
            {evs("retailer_click").map(evRow)}
          </Section>
        </div>
      </>
    );
  }

  return (
    <div className="style-layer" onClick={onClose}>
      <aside className="style-panel" role="dialog" aria-modal="true" aria-labelledby="style-title" onClick={(e) => e.stopPropagation()}>
        <header className="style-head">
          <div>
            <h2 id="style-title">Your style</h2>
            <p>What ClipCart remembers to personalize results, and where each one came from.</p>
          </div>
          <button ref={closeRef} type="button" className="btn btn-quiet btn-sm" onClick={onClose} aria-label="Close Your style">
            Close
          </button>
        </header>
        <div className="style-body">{body}</div>
      </aside>
    </div>
  );
}
