import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, timestamp, upload } from "./api";
import { loadMemory, memoryApi, MemoryContext, type MemoryActions, type MemoryState } from "./memory";
import Constraints, { draftFrom, findLabel, patchFrom, type PrefsDraft } from "./components/Constraints";
import Diagnostics from "./components/Diagnostics";
import FindInVideo, { type FindReply } from "./components/FindInVideo";
import GarmentTray, { cleanLabel, wordSafe } from "./components/GarmentTray";
import Landing, { LinkInput, linkErrorText } from "./components/Landing";
import ModeChips from "./components/ModeChips";
import Refine from "./components/Refine";
import Results from "./components/Results";
import SelectedPiece from "./components/SelectedPiece";
import StylePanel from "./components/StylePanel";
import Upload from "./components/Upload";
import Viewer from "./components/Viewer";
import type { GarmentDoc, GarmentObservation, Health, SearchView, SessionView } from "./types";

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
  const [findReply, setFindReply] = useState<FindReply | null>(null);
  const [linkError, setLinkError] = useState<string | null>(null);
  const [memory, setMemory] = useState<MemoryState>({ state: "loading" });
  const [styleOpen, setStyleOpen] = useState(false);
  const seqRef = useRef(0);
  const resultsRef = useRef<HTMLElement>(null);

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

  // Memory is optional: load it after the session, never in front of it. Offline just means no personalization.
  const reloadMemory = useCallback((quiet = false) => {
    if (!quiet) setMemory({ state: "loading" });
    loadMemory().then((m) => (!quiet || m.state === "ready" ? setMemory(m) : undefined));
  }, []);
  // Wait for the session boot, which sets the owner cookie memory is scoped to.
  const booted = !!s;
  useEffect(() => {
    if (booted) reloadMemory();
  }, [booted, reloadMemory]);
  // Opening the panel refreshes quietly, so links opened since the last load show up.
  const openStyle = () => {
    setStyleOpen(true);
    if (memory.state === "ready") reloadMemory(true);
  };
  const closeStyle = useCallback(() => setStyleOpen(false), []);
  const memoryActions = useMemo<MemoryActions>(() => {
    const evs = memory.state === "ready" ? memory.events : [];
    const savedEventId = (rid: string, lid: string) =>
      evs.find((e) => e.type === "saved_item" && (e.item?.recommendationId === rid || e.item?.listingId === lid))?.id ?? null;
    return {
      ready: memory.state === "ready",
      savedEventId,
      toggleSave: (rid, lid) => {
        const id = savedEventId(rid, lid);
        (id ? memoryApi.removeEvent(id) : memoryApi.event("saved_item", rid))
          .then(() => reloadMemory(true))
          .catch(() => setNotice({ kind: "error", text: "Couldn't update Your style. The memory service may be offline; shopping still works." }));
      },
    };
  }, [memory, reloadMemory]);

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

  // When analysis finishes: refresh provider modes (the detection chip flips to Live here, not after a search)
  // and, with nothing to pick, open manual drawing.
  useEffect(() => {
    if (!analysis || ["queued", "running"].includes(analysis.status)) return;
    refreshHealth();
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

  // Bring the results area into view once a search starts so the hand-off from piece to results is visible.
  const showResults = () =>
    requestAnimationFrame(() =>
      resultsRef.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }),
    );

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

  // YouTube clips are downloaded server-side and analyzed like an upload, but only for permitted video IDs.
  const analyzeLink = async (url: string) => {
    if (!s) return;
    setNotice(null);
    setLinkError(null);
    setBusy(true);
    setSearch(null);
    setSearchId(null);
    setFrameId(null);
    setDrawing(null);
    setDraft(null);
    try {
      setView(await api.youtubeAnalyze(s.id, url, s.revision));
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, "error", String(e));
      if (err.status === 409) fail(err);
      else setLinkError(linkErrorText(err.code, err.message));
    } finally {
      setBusy(false);
    }
  };

  // Show a frame where the garment is visible: keep the current frame if it already is, else jump to its first sighting.
  const frameFor = (v: SessionView, gid: string | null | undefined, current: string | null): GarmentObservation | null => {
    const g = v.garments.find((x) => x.id === gid);
    if (!g) return null;
    const seen = v.observations.filter((o) => g.observationIds.includes(o.id));
    return seen.find((o) => o.frameAssetId === current) ?? seen[0] ?? null;
  };

  const showStage = () =>
    requestAnimationFrame(() =>
      document.querySelector(".scene .stage")?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "nearest",
      }),
    );

  const selectGarment = async (gid: string) => {
    if (!s || gid === s.selectedGarmentId) return;
    setBusy(true);
    try {
      const v = await api.patch(s.id, { expectedRevision: s.revision, selectedGarmentId: gid, idempotencyKey: crypto.randomUUID() });
      setView(v);
      const seen = frameFor(v, gid, frameId);
      if (seen) setFrameId(seen.frameAssetId);
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
      showResults();
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
      if (r.searchId) {
        setSearchId(r.searchId);
        showResults();
      }
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const findInVideo = async (text: string) => {
    if (!s) return;
    setBusy(true);
    setFindReply(null);
    setNotice(null);
    try {
      const r = await api.findInMedia(s.id, text, s.revision);
      setView(r);
      const gid = r.find?.garmentId ?? r.session.selectedGarmentId;
      const g = r.garments.find((x) => x.id === gid);
      // Jump to the frame the found garment was located on, where its box is drawn.
      const seen = frameFor(r, gid, null);
      if (seen) {
        setDrawing(null);
        setDraft(null);
        setFrameId(seen.frameAssetId);
        showStage();
      }
      const at = isVideo ? timestamp(r.analysis?.frames?.find((f) => f.assetId === seen?.frameAssetId)?.timestampMs) : null;
      // Built from the structured response: the server's reply text quotes a label it caps at 80 characters.
      setFindReply(
        g
          ? {
              tone: "found",
              headline: `Found: ${cleanLabel(g.label)}`,
              where: seen ? (at ? `shown at ${at}` : "boxed on the frame") : null,
              description: r.find?.searchDescription ?? g.userDescription ?? null,
            }
          : { tone: "found", headline: wordSafe(r.reply, 160) },
      );
      if (r.searchId) setSearchId(r.searchId);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, "error", String(e));
      // Not found, too vague, or no detector: answer next to the Find box, where the person is looking.
      if (err.status === 409) fail(err);
      else setFindReply({ tone: "error", headline: err.message });
    } finally {
      setBusy(false);
    }
  };

  const analyzing = analysis && ["queued", "running"].includes(analysis.status);
  const detectionMode = analysis?.detectionMode ?? "unavailable";
  // Find-made labels can be a whole sentence; buttons and headings get a word-safe short form.
  const pieceLabel = selected ? wordSafe(cleanLabel(selected.label), 40) : null;
  const searching = !!search && ["queued", "running"].includes(search.job.status);
  const step = !view?.media ? 0 : !selected ? 1 : !searchId ? 2 : 3;
  const youtubeEnabled = !!health?.features?.youtubeDownload;
  const fromYouTube = view?.media?.sourceType === "youtube_download";
  const mediaMeta = view?.media
    ? fromYouTube
      ? `YouTube clip${view.media.durationMs ? ` · ${timestamp(view.media.durationMs)}` : ""} · ${frames.length} frame${frames.length === 1 ? "" : "s"} sampled`
      : isVideo
      ? `Video${view.media.durationMs ? ` · ${timestamp(view.media.durationMs)}` : ""} · ${frames.length} frame${frames.length === 1 ? "" : "s"} sampled`
      : "Photo"
    : null;

  return (
    <MemoryContext.Provider value={memoryActions}>
      <div className={`shell ${view?.media ? "" : "shell-landing"}`}>
        <header className="top">
          <a className="brand" href="#/" aria-label="ClipCart home">
            <span className="brand-mark" aria-hidden>
              ▶
            </span>
            <span className="wordmark">ClipCart</span>
          </a>
          <p className="tagline">Shop the look from any photo or clip.</p>
          <button type="button" className="style-btn" onClick={openStyle} aria-haspopup="dialog">
            <span aria-hidden>✦</span> Your style
            {memory.state === "ready" && memory.memories.length > 0 && <span className="style-count">{memory.memories.length}</span>}
            {memory.state === "unavailable" && <span className="style-off">off</span>}
          </button>
          <ModeChips health={health} />
        </header>
        <StylePanel open={styleOpen} onClose={closeStyle} memory={memory} onReload={() => reloadMemory(true)} />

        {view?.media && (
          <ol className="steps" aria-label="Progress">
            {["Upload", "Pick a piece", "Set rules", "Shop results"].map((label, i) => (
              <li key={label} className={i < step ? "step-done" : i === step ? "step-now" : ""} aria-current={i === step ? "step" : undefined}>
                <span className="step-n">{i < step ? "✓" : i + 1}</span>
                {label}
              </li>
            ))}
          </ol>
        )}

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
          <Landing
            busy={busy || !s}
            progress={progress}
            onFile={onFile}
            youtubeEnabled={youtubeEnabled}
            onYouTube={analyzeLink}
            linkError={linkError}
          />
        ) : (
          <main className="studio">
            <section className="scene" aria-label="Your scene">
              <div className="scene-head">
                <div>
                  <h2>Your scene</h2>
                  {mediaMeta && <p>{mediaMeta}</p>}
                </div>
                <Upload busy={busy} progress={progress} onFile={onFile} compact />
              </div>
              {youtubeEnabled && (
                <div className="yt-again">
                  <LinkInput busy={busy} onSubmit={analyzeLink} error={linkError} compact />
                </div>
              )}
              {analyzing && (
                <div className="scene-status" role="status">
                  <span className="spinner" aria-hidden /> {analysis?.frameIds?.length ? "Looking for jackets, tops, pants and bags…" : "Reading frames…"}
                </div>
              )}
              {analysis?.message && !analyzing && (
                <div className={`scene-status ${analysis.status === "failed" ? "scene-status-error" : ""}`}>{analysis.message}</div>
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
                    <button type="button" className="btn btn-ghost btn-sm" onClick={() => setDrawing({ mode: "new" })} disabled={busy}>
                      <span aria-hidden>⬚</span> Draw a box around a garment
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
                            <input
                              id="manual-desc"
                              value={manualDesc}
                              maxLength={120}
                              placeholder="e.g. black nylon bomber"
                              onChange={(e) => setManualDesc(e.target.value)}
                            />
                          </label>
                        </div>
                      )}
                      <div className="draw-actions">
                        <button type="button" className="btn btn-primary btn-sm" disabled={!draft || busy} onClick={saveDraft}>
                          {drawing.mode === "edit" ? "Save crop" : "Use this garment"}
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
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
                busy={busy}
                detectionMode={detectionMode}
              />
              {/* PR #11: natural-language find in the analyzed frames; adds and selects a garment. */}
              {frames.length > 0 && !analyzing && (
                <FindInVideo disabled={busy} busy={busy} onFind={findInVideo} reply={findReply} />
              )}
            </section>

            <aside className="panel" aria-label="Selected piece and your rules">
              <SelectedPiece
                garment={selected}
                observations={view.observations}
                detectionMode={detectionMode}
                busy={busy}
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
              />
              <h2 className="panel-title">Your rules</h2>
              {s && <Constraints session={s} canSearch={!!selected} pieceLabel={pieceLabel} busy={busy} onSubmit={findIt} />}
            </aside>

            <section className="col-results" aria-label="Results" ref={resultsRef}>
              {search ? (
                <>
                  <Results
                    view={search}
                    cropId={selected?.representativeCropId ?? null}
                    garmentLabel={pieceLabel}
                    onRetry={() => s && findIt(draftFrom(s))}
                    onCancel={async () => {
                      if (searchId) await api.cancel(searchId).catch(fail);
                    }}
                  />
                  <Refine disabled={busy || !selected} onSend={refine} reply={reply} />
                </>
              ) : (
                <div className="placeholder">
                  <span className="placeholder-icon" aria-hidden>
                    ◎
                  </span>
                  <div>
                    <h2>Shopping results land here</h2>
                    <p className="muted">
                      {selected
                        ? `Set your rules, then press “${findLabel(false, true, pieceLabel)}”.`
                        : "Select or draw the garment you want first. Only that garment is searched."}
                    </p>
                  </div>
                </div>
              )}
            </section>

            {selected && !drawing && (
              <div className="dock" aria-label="Quick actions">
                {search && !searching ? (
                  <button type="button" className="btn btn-quiet" onClick={() => resultsRef.current?.scrollIntoView({ behavior: "smooth" })}>
                    See results
                  </button>
                ) : null}
                <button className="btn btn-primary" type="submit" form="rules-form" disabled={busy || searching}>
                  {searching ? "Searching…" : findLabel(busy, true, pieceLabel)}
                </button>
              </div>
            )}
          </main>
        )}
        <footer className="foot">
          <p>
            ClipCart doesn't sell anything and has no checkout. Prices come from the listed sources and change often; confirm on the destination site.
            Links are not affiliate links.
          </p>
        </footer>
      </div>
    </MemoryContext.Provider>
  );
}
