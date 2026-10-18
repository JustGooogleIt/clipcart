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
  const timers = useRef<number[]>([]);
  const ran = useRef(false);
  const t = W.t;

  const clear = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  const later = (ms: number, fn: () => void) => timers.current.push(window.setTimeout(fn, ms));

  const whenReady = (v: HTMLVideoElement) =>
    new Promise<void>((resolve) => {
      if (v.readyState >= 1) return resolve();
      v.addEventListener("loadedmetadata", () => resolve(), { once: true });
      v.load();
    });

  const seekPause = async () => {
    const v = vref.current;
    if (!v) return;
    v.pause();
    await whenReady(v);
    if (Math.abs(v.currentTime - t) < 0.04) return;
    await new Promise<void>((resolve) => {
      v.addEventListener("seeked", () => resolve(), { once: true });
      v.currentTime = t;
    });
  };

  const go = async (n: number, manual = true) => {
    if (manual) clear();
    const v = vref.current;
    if (!v) return;
    if (n === 0) {
      setStep(0);
      await whenReady(v);
      v.currentTime = Math.max(0, t - 3);
      v.play().catch(() => undefined);
      return;
    }
    await seekPause();
    setStep(n);
  };

  const runDemo = () => {
    clear();
    if (reduced) return void go(2, false);
    go(0, false);
    later(2800, () => go(1, false));
    later(3700, () => go(2, false));
    later(5500, () => setStep(3));
  };
  demoRef.current = runDemo;

  // Run the demo once when the section first comes into view; pause it whenever it leaves.
  useEffect(() => {
    if (!inView) {
      clear();
      vref.current?.pause();
      return;
    }
    if (!ran.current) {
      ran.current = true;
      runDemo();
    }
  }, [inView]);

  useEffect(() => clear, []);

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
          <button type="button" className="rv-btn rv-btn-sm" onClick={runDemo}>
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
            />
            {showBox && (
              <>
                <span className="rv-illus">Illustrative box · not detection output</span>
                <button
                  type="button"
                  className={`rv-gbox ${selected ? "rv-gbox-on" : ""}`}
                  style={box}
                  onClick={() => {
                    clear();
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
              onClick={() => {
                if (playing) {
                  clear();
                  vref.current?.pause();
                  setStep(1);
                } else go(0);
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
                onChange={(e) => {
                  clear();
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
            <button type="button" className="rv-jump" onClick={() => go(Math.max(2, step))}>
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
