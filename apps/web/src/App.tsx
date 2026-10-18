import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, upload } from "./api";
import Constraints, { draftFrom, patchFrom, type PrefsDraft } from "./components/Constraints";
import Diagnostics from "./components/Diagnostics";
import GarmentTray from "./components/GarmentTray";
import ModeChips from "./components/ModeChips";
import Refine from "./components/Refine";
import Results from "./components/Results";
import Upload from "./components/Upload";
import Viewer from "./components/Viewer";
import type { GarmentDoc, Health, SearchView, SessionView } from "./types";

type Box = [number, number, number, number];
type Drawing = { mode: "new" } | { mode: "edit"; garmentId: string };

function useHashRoute() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const on = () => setHash(window.location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash;
}

const TERMINAL = new Set(["completed", "partial", "no_match", "failed", "cancelled", "superseded"]);

export default function App() {
  const route = useHashRoute();
  const [health, setHealth] = useState<Health | null>(null);
  const [view, setView] = useState<SessionView | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: "error" | "info"; text: string } | null>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [frameId, setFrameId] = useState<string | null>(null);
  const [drawing, setDrawing] = useState<Drawing | null>(null);
  const [draft, setDraft] = useState<Box | null>(null);
  const [manualCat, setManualCat] = useState("jacket");
  const [manualDesc, setManualDesc] = useState("");
  const [searchId, setSearchId] = useState<string | null>(null);
  const [search, setSearch] = useState<SearchView | null>(null);
  const [reply, setReply] = useState<string | null>(null);
  const seqRef = useRef(0);

  const s = view?.session ?? null;
  const analysis = view?.analysis ?? null;
  const frames = analysis?.frames ?? [];
  const isVideo = view?.media?.kind === "video";

  const refreshHealth = useCallback(() => api.health().then(setHealth).catch(() => undefined), []);

  const fail = useCallback(
    async (e: unknown) => {
      const err = e instanceof ApiError ? e : new ApiError(0, "error", String(e));
      if (err.status === 409 && s) {
        try {
          setView(await api.session(s.id));
        } catch {
          /* keep current */
        }
        setNotice({ kind: "info", text: "Your session changed in another tab or request. We reloaded the latest version; try again." });
      } else {
        setNotice({ kind: "error", text: `${err.message}${err.requestId ? ` (ref ${err.requestId})` : ""}` });
      }
    },
    [s],
  );

  // Boot: restore the last committed session or create one.
  useEffect(() => {
    refreshHealth();
    (async () => {
      try {
        const v = await api.resume();
        setView(v);
        if (v.session.activeSearchId) setSearchId(v.session.activeSearchId);
      } catch (e) {
        setBootError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [refreshHealth]);

  // Poll the session while analysis runs.
  useEffect(() => {
    if (!s || !analysis || !["queued", "running"].includes(analysis.status)) return;
    const t = setInterval(async () => {
      try {
        setView(await api.session(s.id));
      } catch {
        /* transient */
      }
    }, 900);
    return () => clearInterval(t);
  }, [s?.id, analysis?.id, analysis?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  // When analysis finishes with nothing to pick, open manual drawing.
  useEffect(() => {
    if (!analysis || ["queued", "running"].includes(analysis.status)) return;
    if (!frameId && frames.length) setFrameId(frames[Math.floor(frames.length / 2)].assetId);
    if ((view?.garments.length ?? 0) === 0 && !drawing) setDrawing({ mode: "new" });
  }, [analysis?.status, analysis?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll the active search; events are incremental.
  useEffect(() => {
    if (!searchId) return;
    let stop = false;
    seqRef.current = 0;
    setSearch(null);
    const tick = async () => {
      try {
        const r = await api.search(searchId, seqRef.current);
        if (stop) return;
        if (r.events.length) seqRef.current = r.events[r.events.length - 1].sequence;
        setSearch((prev) => ({ ...r, events: [...(prev && prev.job.id === r.job.id ? prev.events : []), ...r.events] }));
        if (TERMINAL.has(r.job.status)) {
          refreshHealth();
          return;
        }
      } catch {
        /* retry next tick */
      }
      if (!stop) setTimeout(tick, 800);
    };
    tick();
    return () => {
      stop = true;
    };
  }, [searchId, refreshHealth]);

  const garmentOf = useMemo(() => {
    const m: Record<string, GarmentDoc> = {};
    for (const g of view?.garments ?? []) for (const o of g.observationIds) m[o] = g;
    return m;
  }, [view?.garments]);
  const selected = view?.garments.find((g) => g.id === s?.selectedGarmentId) ?? null;

  if (route.startsWith("#/diagnostics")) {
    return (
      <div className="shell">
        <Diagnostics />
      </div>
    );
  }

  const onFile = async (f: File) => {
    if (!s) return;
    if (f.size > 150 * 1024 * 1024) return setNotice({ kind: "error", text: "That file is over 150 MB. Trim the clip and try again." });
    setNotice(null);
    setBusy(true);
    setProgress(0);
    setSearch(null);
    setSearchId(null);
    setFrameId(null);
    setDrawing(null);
    setDraft(null);
    try {
      setView(await upload(s.id, s.revision, f, setProgress));
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
      setProgress(null);
    }
  };

  const onYoutube = async (youtubeUrl: string) => {
    if (!s) return;
    setNotice({
      kind: "info",
      text: "Downloading a temporary copy of the YouTube clip, then scanning for clothes…",
    });
    setBusy(true);
    setProgress(null);
    setSearch(null);
    setSearchId(null);
    setFrameId(null);
    setDrawing(null);
    setDraft(null);
    try {
      const v = await api.youtubeAnalyze(s.id, youtubeUrl, s.revision);
      setView(v);
      const title = v.youtube?.title ? `“${v.youtube.title}”` : "YouTube clip";
      setNotice({
        kind: "info",
        text: `${title} ${v.youtube?.cacheHit ? "(cache hit)" : "downloaded"} — analyzing the best frames now.`,
      });
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const selectGarment = async (gid: string) => {
    if (!s || gid === s.selectedGarmentId) return;
    setBusy(true);
    try {
      setView(await api.patch(s.id, { expectedRevision: s.revision, selectedGarmentId: gid, idempotencyKey: crypto.randomUUID() }));
      setSearchId(null);
      setSearch(null);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const saveDraft = async () => {
    if (!s || !draft || !drawing) return;
    setBusy(true);
    try {
      if (drawing.mode === "new") {
        const frame = frameId ?? frames[0]?.assetId;
        const { garment } = await api.addGarment(s.id, { frameAssetId: frame, box01: draft, category: manualCat, description: manualDesc || null });
        const v = await api.session(s.id);
        setView(await api.patch(s.id, { expectedRevision: v.session.revision, selectedGarmentId: garment.id, idempotencyKey: crypto.randomUUID() }));
      } else {
        await api.patchGarment(drawing.garmentId, { box01: draft });
        setView(await api.session(s.id));
      }
      setDraft(null);
      setDrawing(null);
      setManualDesc("");
      setSearchId(null);
      setSearch(null);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const findIt = async (d: PrefsDraft) => {
    if (!s) return;
    setBusy(true);
    setNotice(null);
    setReply(null);
    try {
      const v = await api.patch(s.id, { expectedRevision: s.revision, preferences: patchFrom(d), idempotencyKey: crypto.randomUUID() });
      const r = await api.startSearch(s.id, v.session.revision);
      setView(r);
      setSearchId(r.searchId);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const refine = async (text: string) => {
    if (!s) return;
    setBusy(true);
    try {
      const r = await api.message(s.id, text, s.revision);
      setView(r);
      setReply(r.reply);
      if (r.searchId) setSearchId(r.searchId);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const analyzing = analysis && ["queued", "running"].includes(analysis.status);

  return (
    <div className="shell">
      <header className="top">
        <div>
          <h1 className="wordmark">ClipCart</h1>
          <p className="tagline">
            Drop a fit check, photo, or YouTube Short. We find the clothes, then search real listings that match your budget.
          </p>
        </div>
        <ModeChips health={health} />
      </header>

      {bootError && (
        <div className="banner banner-error" role="alert">
          Couldn't start a shopping session: {bootError}
        </div>
      )}
      {notice && (
        <div className={`banner ${notice.kind === "error" ? "banner-error" : ""}`} role={notice.kind === "error" ? "alert" : "status"}>
          {notice.text}
          <button type="button" className="linkish" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}

      {!view?.media ? (
        <main className="empty">
          <Upload
            busy={busy || !s}
            progress={progress}
            onFile={onFile}
            onYoutube={health?.features?.youtubeDownload ? onYoutube : undefined}
          />
          <ol className="how">
            <li>
              <strong>Send a look.</strong> Photo, short clip, or YouTube URL — we scan for jackets, tops, pants and bags.
            </li>
            <li>
              <strong>Pick the piece</strong> in the tray (or draw a box if we missed it).
            </li>
            <li>
              <strong>Set your rules</strong> — budget, size, materials to avoid — then shop sourced options.
            </li>
          </ol>
        </main>
      ) : (
        <main className="grid">
          <section className="col-look" aria-label="Your look">
            <div className="section-head">
              <h2>1 · Pick the garment</h2>
              <Upload
                busy={busy}
                progress={progress}
                onFile={onFile}
                onYoutube={health?.features?.youtubeDownload ? onYoutube : undefined}
                compact
              />
            </div>
            {analyzing && (
              <div className="banner" role="status">
                <span className="spinner" aria-hidden />{" "}
                {analysis?.frameIds?.length ? "Looking for jackets, tops, pants and bags…" : "Scanning the best frames…"}
              </div>
            )}
            {analysis?.message && !analyzing && (
              <div className={`banner ${analysis.status === "failed" ? "banner-error" : ""}`}>{analysis.message}</div>
            )}
            {frames.length > 0 && (
              <Viewer
                frames={frames}
                frameId={frameId}
                onFrame={(id) => setFrameId(id)}
                observations={view.observations}
                garmentOf={garmentOf}
                selectedGarmentId={s?.selectedGarmentId ?? null}
                onSelectGarment={selectGarment}
                drawing={!!drawing}
                draft={draft}
                onDraft={setDraft}
                isVideo={isVideo}
              />
            )}
            {frames.length > 0 && !analyzing && (
              <div className="draw">
                {!drawing ? (
                  <button type="button" className="btn btn-quiet btn-sm" onClick={() => setDrawing({ mode: "new" })} disabled={busy}>
                    Draw a box around a garment
                  </button>
                ) : (
                  <div className="draw-panel">
                    <p>
                      {drawing.mode === "edit" ? "Drag a new box around the garment." : "Drag a box around the garment you want."}{" "}
                      {!draft && (
                        <button type="button" className="linkish" onClick={() => setDraft([0.02, 0.02, 0.98, 0.98])}>
                          Use the whole frame
                        </button>
                      )}
                    </p>
                    {draft && drawing.mode === "new" && (
                      <div className="draw-fields">
                        <label>
                          Category
                          <select value={manualCat} onChange={(e) => setManualCat(e.target.value)}>
                            <option value="jacket">Jacket</option>
                            <option value="top">Top</option>
                            <option value="pants">Pants</option>
                            <option value="bag">Bag</option>
                          </select>
                        </label>
                        <label>
                          Describe it (optional)
                          <input value={manualDesc} maxLength={120} placeholder="e.g. black nylon bomber" onChange={(e) => setManualDesc(e.target.value)} />
                        </label>
                      </div>
                    )}
                    <div className="draw-actions">
                      <button type="button" className="btn btn-primary btn-sm" disabled={!draft || busy} onClick={saveDraft}>
                        {drawing.mode === "edit" ? "Save crop" : "Use this garment"}
                      </button>
                      <button
                        type="button"
                        className="btn btn-quiet btn-sm"
                        onClick={() => {
                          setDrawing(null);
                          setDraft(null);
                        }}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
            <GarmentTray
              garments={view.garments}
              observations={view.observations}
              selectedId={s?.selectedGarmentId ?? null}
              onSelect={selectGarment}
              onRelabel={async (gid, category) => {
                try {
                  await api.patchGarment(gid, { category });
                  setView(await api.session(s!.id));
                } catch (e) {
                  fail(e);
                }
              }}
              onRedraw={(g) => {
                const o = view.observations.find((x) => x.id === g.observationIds[0]);
                if (o) setFrameId(o.frameAssetId);
                setDraft(null);
                setDrawing({ mode: "edit", garmentId: g.id });
              }}
              busy={busy}
              detectionMode={analysis?.detectionMode ?? "unavailable"}
            />
          </section>

          <section className="col-rules" aria-label="Your constraints">
            <h2>2 · Set your rules</h2>
            {s && <Constraints session={s} canSearch={!!selected} busy={busy} onSubmit={findIt} />}
          </section>

          <section className="col-results" aria-label="Results">
            {search ? (
              <>
                <Results
                  view={search}
                  cropId={selected?.representativeCropId ?? null}
                  onRetry={() => s && findIt(draftFrom(s))}
                  onCancel={async () => {
                    if (searchId) await api.cancel(searchId).catch(fail);
                  }}
                />
                <Refine disabled={busy || !selected} onSend={refine} reply={reply} />
              </>
            ) : (
              <div className="placeholder">
                <h2>3 · Results</h2>
                <p className="muted">
                  {selected ? "Set your rules and press Find it." : "Select or draw the garment you want first. Only that garment is searched."}
                </p>
              </div>
            )}
          </section>
        </main>
      )}
      <footer className="foot">
        <p>
          ClipCart doesn't sell anything. Prices come from the listed sources and change often; confirm on the destination site. Links are not
          affiliate links.
        </p>
      </footer>
    </div>
  );
}

