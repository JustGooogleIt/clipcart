import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { COPY, WALKTHROUGH as W } from "./content";
import { coverRect, fmt, useInView, useSize } from "./media";

/**
 * How-it-works on the real fc01 clip: it plays, pauses on the chosen frame, shows an illustrative
 * box on the jacket, and demonstrates tapping it. The box only shows while the clip is paused on
 * that frame, so it never drifts over moving footage.
 */
export default function Walkthrough({
  reduced,
  busy,
  onTry,
  demoRef,
  error,
}: {
  reduced: boolean;
  busy: boolean;
  onTry: () => void;
  error: string | null;
  demoRef: MutableRefObject<() => void>;
}) {
  const vref = useRef<HTMLVideoElement>(null);
  const sectionRef = useRef<HTMLElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const size = useSize(frameRef);
  const inView = useInView(sectionRef, "0px");
  const [step, setStep] = useState(0);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [failed, setFailed] = useState(false);
  const timers = useRef<number[]>([]);
  const ran = useRef(false);
  // Every playback action takes a token; leaving the viewport, unmounting or a newer action
  // invalidates older tokens, so a step still waiting on metadata or a seek can never resume playback.
  const epoch = useRef(0);
  const alive = useRef(true);
  const inViewRef = useRef(inView);
  inViewRef.current = inView;
  const t = W.t;

  const clear = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  const later = (ms: number, fn: () => void) => timers.current.push(window.setTimeout(fn, ms));
  const begin = () => ++epoch.current;
  const cancel = () => {
    begin();
    clear();
  };
  const current = (token: number) => alive.current && inViewRef.current && token === epoch.current;

  /** Resolves true once metadata is available, false if the media fails to load. */
  const once = (v: HTMLVideoElement, ok: string, start?: () => void) =>
    new Promise<boolean>((resolve) => {
      const ac = new AbortController();
      const done = (r: boolean) => {
        ac.abort();
        resolve(r);
      };
      v.addEventListener(ok, () => done(true), { signal: ac.signal });
      v.addEventListener("error", () => done(false), { signal: ac.signal });
      start?.();
    });
  const whenReady = (v: HTMLVideoElement) => {
    if (v.error) return Promise.resolve(false);
    if (v.readyState >= 1) return Promise.resolve(true);
    return once(v, "loadedmetadata", () => {
      if (v.networkState !== HTMLMediaElement.NETWORK_LOADING) v.load();
    });
  };

  /** Pause on the walkthrough frame. Returns false if superseded or the media failed. */
  const seekPause = async (token: number) => {
    const v = vref.current;
    if (!v) return false;
    v.pause();
    if (!(await whenReady(v)) || !current(token)) return false;
    if (Math.abs(v.currentTime - t) < 0.04) return true;
    const ok = await once(v, "seeked", () => {
      v.currentTime = t;
    });
    return ok && current(token);
  };

  /** Play from where the clip is. Only Replay (restart = true) jumps back to the lead-in. */
  const play = async (restart: boolean) => {
    const token = begin();
    const v = vref.current;
    if (!v) return;
    setStep(0);
    if (!(await whenReady(v)) || !current(token)) return;
    if (restart) v.currentTime = Math.max(0, t - 3);
    try {
      await v.play();
    } catch {
      /* autoplay refused, or a newer pause interrupted it */
    }
    // Left the viewport or unmounted while play() was pending: stop. A newer action owns the clip otherwise.
    if (!alive.current || !inViewRef.current) v.pause();
  };

  const go = async (n: number, manual = true) => {
    if (manual) clear();
    if (n === 0) return play(false);
    const token = begin();
    if (await seekPause(token)) setStep(n);
  };

  const runDemo = () => {
    clear();
    if (failed) return;
    if (reduced) return void go(2, false);
    void play(true);
    later(2800, () => go(1, false));
    later(3700, () => go(2, false));
    later(5500, () => setStep(3));
  };
  demoRef.current = runDemo;

  // Run the demo once when the section first comes into view; pause it whenever it leaves.
  useEffect(() => {
    if (!inView) {
      cancel();
      vref.current?.pause();
      return;
    }
    if (!ran.current) {
      ran.current = true;
      runDemo();
    }
  }, [inView]);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      cancel();
      vref.current?.pause();
    };
  }, []);

  const rect = coverRect(size.w, size.h, W.frame.w, W.frame.h);
  const showBox = step >= 2 && !playing && Math.abs(time - t) < 0.3;
  const b = W.box;
  const box = {
    left: rect.x + (b.x / 100) * rect.w,
    top: rect.y + (b.y / 100) * rect.h,
    width: (b.w / 100) * rect.w,
    height: (b.h / 100) * rect.h,
  };
  const selected = step === 3 && showBox;

  return (
    <section className="rv-walk" id="how" ref={sectionRef} aria-labelledby="rv-walk-title">
      <div className="rv-aura" aria-hidden />
      <div className="rv-walk-copy">
        <p className="rv-kicker">{COPY.walkKicker}</p>
        <h2 id="rv-walk-title" className="rv-walk-title">
          {COPY.walkTitle}
        </h2>
        <ol className="rv-rail">
          {COPY.steps.map((st, i) => (
            <li key={st.short} className={i === step ? "rv-on" : i < step ? "rv-done" : ""}>
              <button type="button" onClick={() => go(i)} aria-current={i === step ? "step" : undefined}>
                <span className="rv-rail-n">{String(i + 1).padStart(2, "0")}</span>
                <span>{st.short}</span>
              </button>
            </li>
          ))}
        </ol>
        <div className="rv-beats">
          {COPY.steps.map((st, i) => (
            <div key={st.short} className={`rv-beat ${i === step ? "rv-beat-on" : ""}`} aria-hidden={i !== step}>
              <h3>{st.title}</h3>
              <p>{st.body}</p>
            </div>
          ))}
        </div>
        <div className="rv-walk-actions">
          <button type="button" className="rv-btn rv-btn-main rv-btn-sm" onClick={onTry} disabled={busy}>
            {busy ? "Uploading…" : COPY.tryVideo}
          </button>
          <button type="button" className="rv-btn rv-btn-sm" onClick={runDemo} disabled={failed}>
            {reduced ? "Show the frame" : "Replay the demo"}
          </button>
        </div>
        {error && (
          <p className="rv-sample-error" role="alert">
            {error}
          </p>
        )}
      </div>

      <div className="rv-walk-stage">
        <div className={`rv-device ${step >= 2 ? "rv-device-dim" : ""}`}>
          <div className="rv-frame" ref={frameRef}>
            <video
              ref={vref}
              src={W.src}
              poster={W.poster}
              muted
              loop
              playsInline
              preload="metadata"
              aria-label="Fit-check clip used in the walkthrough"
              onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
              onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)}
              onSeeked={(e) => setTime(e.currentTarget.currentTime)}
              onPlay={() => {
                setPlaying(true);
                setStep(0);
              }}
              onPause={() => setPlaying(false)}
              onError={() => {
                cancel();
                setPlaying(false);
                setFailed(true);
              }}
            />
            {failed && (
              <p className="rv-media-error" role="status">
                This clip didn't load. Use “{COPY.tryVideo}” to run it through ClipCart instead.
              </p>
            )}
            {showBox && (
              <>
                <span className="rv-illus">Illustrative box · not detection output</span>
                <button
                  type="button"
                  className={`rv-gbox ${selected ? "rv-gbox-on" : ""}`}
                  style={box}
                  onClick={() => {
                    cancel();
                    setStep(3);
                  }}
                  aria-label={`Select the ${W.label.toLowerCase()}`}
                  aria-pressed={selected}
                >
                  <i>{W.label}</i>
                </button>
                {step === 2 && !reduced && <span className="rv-finger" style={{ left: box.left + box.width / 2, top: box.top + box.height / 2 }} aria-hidden />}
                {step === 2 && reduced && <span className="rv-tap-hint">Tap the {W.label.toLowerCase()}</span>}
              </>
            )}
            {selected && (
              <div className="rv-rules" aria-hidden>
                <span className="rv-rule rv-rule-main">Shopping for · {W.label}</span>
                <span className="rv-rule">Your size</span>
                <span className="rv-rule">Your budget</span>
              </div>
            )}
          </div>
          <div className="rv-controls">
            <button
              type="button"
              className="rv-play"
              disabled={failed}
              onClick={() => {
                if (playing) {
                  cancel();
                  vref.current?.pause();
                  setStep(1);
                } else {
                  clear();
                  void play(false);
                }
              }}
              aria-label={playing ? "Pause" : "Play"}
            >
              {playing ? (
                <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
                  <rect x="3" y="2" width="3.5" height="12" rx="1" fill="currentColor" />
                  <rect x="9.5" y="2" width="3.5" height="12" rx="1" fill="currentColor" />
                </svg>
              ) : (
                <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
                  <path d="M4 2.5v11l9.5-5.5z" fill="currentColor" />
                </svg>
              )}
            </button>
            <div className="rv-scrub">
              <label className="sr-only" htmlFor="rv-scrub">
                Scrub the clip
              </label>
              <input
                id="rv-scrub"
                type="range"
                min="0"
                max={duration || 1}
                step="0.01"
                value={Math.min(time, duration || 1)}
                disabled={failed}
                onChange={(e) => {
                  cancel();
                  const v = vref.current;
                  if (!v) return;
                  v.pause();
                  v.currentTime = Number(e.target.value);
                  setStep((n) => (n >= 2 ? n : 1));
                }}
              />
              {duration > 0 && <span className="rv-mark" style={{ left: `${(t / duration) * 100}%` }} title="Walkthrough frame" />}
            </div>
            <span className="rv-time">
              {fmt(time)} / {fmt(duration)}
            </span>
            <button type="button" className="rv-jump" onClick={() => go(Math.max(2, step))} disabled={failed}>
              Frame {fmt(t)}
            </button>
          </div>
        </div>
        <div className={`rv-results ${selected ? "rv-results-on" : ""}`} aria-live="polite">
          <div className="rv-res-head">
            <b>Shopping for · {W.label}</b>
            <span className="rv-illus rv-illus-static">Illustrative</span>
          </div>
          <p>Only this piece is searched. Similar options appear with the store and price from their source page.</p>
          <div className="rv-skel" aria-hidden>
            <span />
            <span />
          </div>
          <div className="rv-skel" aria-hidden>
            <span />
            <span />
          </div>
          <p className="rv-res-note">Use “Try this video” to run it through ClipCart yourself.</p>
        </div>
      </div>
    </section>
  );
}
