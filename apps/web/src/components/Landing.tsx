import { useEffect, useRef, useState } from "react";
import Upload from "./Upload";
import denim from "../assets/showcase/denim.mp4";
import denimWebm from "../assets/showcase/denim.webm";
import denimPoster from "../assets/showcase/denim.jpg";
import knit from "../assets/showcase/knit.mp4";
import knitWebm from "../assets/showcase/knit.webm";
import knitPoster from "../assets/showcase/knit.jpg";
import leather from "../assets/showcase/leather.mp4";
import leatherWebm from "../assets/showcase/leather.webm";
import leatherPoster from "../assets/showcase/leather.jpg";
import nylon from "../assets/showcase/nylon.mp4";
import nylonWebm from "../assets/showcase/nylon.webm";
import nylonPoster from "../assets/showcase/nylon.jpg";
import satin from "../assets/showcase/satin.mp4";
import satinWebm from "../assets/showcase/satin.webm";
import satinPoster from "../assets/showcase/satin.jpg";
import silk from "../assets/showcase/silk.mp4";
import silkWebm from "../assets/showcase/silk.webm";
import silkPoster from "../assets/showcase/silk.jpg";
import sampleScene from "../assets/showcase/demo-scene.jpg";

// Showcase loops are rendered material close-ups. Swap in creator clips by replacing the files in assets/showcase.
type Clip = { src: string; webm: string; poster: string; label: string; meta: string; tall?: boolean };
const CLIPS: Clip[] = [
  { src: silk, webm: silkWebm, poster: silkPoster, label: "Silk slip", meta: "0:06", tall: true },
  { src: nylon, webm: nylonWebm, poster: nylonPoster, label: "Nylon bomber", meta: "0:06" },
  { src: leather, webm: leatherWebm, poster: leatherPoster, label: "Leather moto", meta: "0:06", tall: true },
  { src: satin, webm: satinWebm, poster: satinPoster, label: "Satin set", meta: "0:06" },
  { src: denim, webm: denimWebm, poster: denimPoster, label: "Raw denim", meta: "0:06", tall: true },
  { src: knit, webm: knitWebm, poster: knitPoster, label: "Chunky knit", meta: "0:06", tall: true },
];
const COLUMNS = [
  { speed: -0.04, clips: [CLIPS[0], CLIPS[3]] },
  { speed: 0.05, clips: [CLIPS[1], CLIPS[2]] },
  { speed: -0.08, clips: [CLIPS[4], CLIPS[5]] },
];

// Bundlers may inline the sample as a data: URL, which some embeds won't fetch; decode those directly.
async function toBlob(url: string) {
  if (!url.startsWith("data:")) return (await fetch(url)).blob();
  const [head, data] = url.split(",");
  const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
  return new Blob([bytes], { type: head.slice(5).split(";")[0] });
}

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Muted looping video that only plays while on screen, and never autoplays for reduced-motion users. */
function Loop({ clip, className }: { clip: Clip; className?: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = ref.current;
    if (!v || reducedMotion()) return;
    const io = new IntersectionObserver(([e]) => (e.isIntersecting ? v.play().catch(() => undefined) : v.pause()), { rootMargin: "120px" });
    io.observe(v);
    return () => io.disconnect();
  }, []);
  return (
    <figure className={`tile ${clip.tall ? "tile-tall" : ""} ${className ?? ""}`}>
      <video ref={ref} poster={clip.poster} muted loop playsInline preload="metadata" aria-hidden>
        <source src={clip.webm} type="video/webm" />
        <source src={clip.src} type="video/mp4" />
      </video>
      <figcaption>
        <span>{clip.label}</span>
        <span>{clip.meta}</span>
      </figcaption>
    </figure>
  );
}

/** Scroll position as a 0..1 progress through an element, updated once per frame. */
function useScrollProgress<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [p, setP] = useState(0);
  useEffect(() => {
    let raf = 0;
    const on = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const el = ref.current;
        if (!el) return;
        const r = el.getBoundingClientRect();
        const span = r.height - window.innerHeight;
        setP(span > 0 ? Math.min(1, Math.max(0, -r.top / span)) : 0);
      });
    };
    on();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", on);
      window.removeEventListener("resize", on);
    };
  }, []);
  return [ref, p] as const;
}

function useMedia(query: string) {
  const [on, setOn] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const m = window.matchMedia(query);
    const h = () => setOn(m.matches);
    m.addEventListener("change", h);
    return () => m.removeEventListener("change", h);
  }, [query]);
  return on;
}

const STORY = [
  { short: "Drop in a clip", title: "Any photo. Any clip.", body: "A creator's fit check, a street shot, a scene from last night's episode." },
  { short: "We spot the pieces", title: "Jackets, tops, pants and bags, boxed for you.", body: "Detection finds what's shoppable. Missed one? Draw your own box." },
  { short: "Tap the one you want", title: "Only that piece is searched.", body: "Add a budget, size, colors and materials to avoid. We never quietly relax them." },
  { short: "Open the listing", title: "Every price links to its source.", body: "Matches are labeled honestly: similar style, likely or verified. No checkout, no hidden markup." },
];
const BEAT_VH = 120;

// Comment-section chatter that drifts behind the hero: the question ClipCart answers.
const CHATTER = ["link??", "where's the jacket from 😭", "need that bag", "fit check 🔥", "drop the link pls", "what brand is the tee"];
const PIECES = ["jacket", "tote", "hoodie", "bomber", "tee"];

/** Cycles through words in place; holds still for reduced-motion users. */
function Rotator({ words }: { words: string[] }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (reducedMotion()) return;
    const t = setInterval(() => setI((n) => (n + 1) % words.length), 2200);
    return () => clearInterval(t);
  }, [words.length]);
  return (
    <span className="l-rot">
      <span key={words[i]} className="l-rot-word">
        {words[i]}
      </span>
    </span>
  );
}

/** Plain-language explanation for a refused YouTube link, always with the upload alternative. */
export function linkErrorText(code: string, message: string) {
  switch (code) {
    case "video_not_permitted":
      return "This demo only scans YouTube clips the team has permission to use, and that video isn't one of them. Upload the clip from your device instead.";
    case "invalid_url":
      return "That isn't a YouTube video link. Paste a youtube.com or youtu.be video link, or upload the clip instead.";
    case "feature_disabled":
      return "YouTube scanning is turned off on this server. Upload the clip instead.";
    case "rate_limited":
      return "Too many YouTube scans in a short time. Wait a few minutes, or upload the clip instead.";
    default:
      return /upload/i.test(message) ? message : `${message} You can upload the clip from your device instead.`;
  }
}

/** YouTube link field. Only rendered when the server reports the feature on; it accepts permitted clips only. */
export function LinkInput({
  busy,
  onSubmit,
  error,
  compact,
}: {
  busy: boolean;
  onSubmit: (url: string) => void;
  error?: string | null;
  compact?: boolean;
}) {
  const [url, setUrl] = useState("");
  const id = compact ? "yt-url-2" : "yt-url";
  return (
    <div className={`yt-wrap ${compact ? "yt-compact" : ""}`}>
      <form
        className="yt-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (url.trim() && !busy) onSubmit(url.trim());
        }}
      >
        <span className="yt-glyph" aria-hidden>
          <svg viewBox="0 0 28 20" width="22" height="16"><rect width="28" height="20" rx="6" fill="#ff0033" /><path d="M11 5.5v9l8-4.5z" fill="#fff" /></svg>
        </span>
        <label className="sr-only" htmlFor={id}>
          Permitted YouTube link
        </label>
        <input
          id={id}
          type="url"
          inputMode="url"
          placeholder="Paste a permitted YouTube link"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          autoComplete="off"
          aria-describedby={`${id}-hint`}
        />
        <button type="submit" disabled={!url.trim() || busy}>
          {busy ? "Working…" : "Scan clip"}
        </button>
      </form>
      <p className="yt-hint" id={`${id}-hint`}>
        Works only with YouTube clips the team has permission to use. For anything else, upload the clip.
      </p>
      {error && (
        <p className="yt-error" role="alert">
          {error}{" "}
          <label htmlFor="file" className="yt-error-action">
            Upload a clip
          </label>
        </p>
      )}
    </div>
  );
}

export default function Landing({
  busy,
  progress,
  onFile,
  youtubeEnabled,
  onYouTube,
  linkError,
}: {
  busy: boolean;
  progress: number | null;
  onFile: (f: File) => void;
  youtubeEnabled: boolean;
  onYouTube: (url: string) => void;
  linkError: string | null;
}) {
  const galleryRef = useRef<HTMLDivElement>(null);
  const [storyRef, story] = useScrollProgress<HTMLElement>();
  const stacked = useMedia("(max-width: 900px)");
  // On narrow screens the beats stack as text and the device shows the finished flow.
  const step = stacked ? STORY.length - 1 : Math.min(STORY.length - 1, Math.floor(story * STORY.length * 0.999));
  const jump = (i: number) => {
    const el = storyRef.current;
    if (!el) return;
    const span = el.offsetHeight - window.innerHeight;
    const top = el.getBoundingClientRect().top + window.scrollY;
    window.scrollTo({ top: top + span * ((i + 0.35) / STORY.length), behavior: reducedMotion() ? "auto" : "smooth" });
  };

  // Columns drift at different speeds as the page scrolls.
  useEffect(() => {
    if (reducedMotion()) return;
    let raf = 0;
    const on = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const g = galleryRef.current;
        if (!g) return;
        const y = -g.getBoundingClientRect().top;
        g.querySelectorAll<HTMLElement>("[data-speed]").forEach((c) => {
          c.style.transform = `translate3d(0, ${(y * Number(c.dataset.speed)).toFixed(1)}px, 0)`;
        });
      });
    };
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", on);
    };
  }, []);

  const trySample = async () => {
    const blob = await toBlob(sampleScene);
    onFile(new File([blob], "demo-scene.jpg", { type: "image/jpeg" }));
  };

  return (
    <main className="landing">
      <section className="l-hero">
        <div className="l-chatter" aria-hidden>
          {CHATTER.map((c, i) => (
            <span key={c} className={`l-bubble l-bubble-${i}`}>
              {c}
            </span>
          ))}
        </div>
        <p className="l-kicker">Shop the fit · from any frame</p>
        <h1 className="l-title">
          Saw that <Rotator words={PIECES} />
          <br />
          in a video?
          <br />
          <span className="l-grad">Tap it. Shop it.</span>
        </h1>
        <p className="l-sub">
          No more “link?” in the comments. Upload a photo or clip, tap the piece, and ClipCart finds where it's actually sold, in your size and under your budget.
        </p>
        <div className="l-ctas">
          <label htmlFor="file" className="l-btn l-btn-main" aria-disabled={busy}>
            {busy ? "Uploading…" : "Upload a clip"}
          </label>
          <button type="button" className="l-btn" onClick={trySample} disabled={busy}>
            Try the sample scene
          </button>
        </div>
        {youtubeEnabled && (
          <>
            <p className="l-or">or</p>
            <LinkInput busy={busy} onSubmit={onYouTube} error={linkError} />
          </>
        )}
      </section>

      <div className="l-gallery" ref={galleryRef} aria-label="Showcase">
        {COLUMNS.map((col, i) => (
          <div key={i} className="l-col" data-speed={col.speed}>
            {col.clips.map((c) => (
              <Loop key={c.label} clip={c} />
            ))}
          </div>
        ))}
      </div>

      <section
        className="l-story"
        ref={storyRef}
        style={{ ["--p" as string]: story, height: stacked ? undefined : `calc(${STORY.length * BEAT_VH}vh + 100vh)` }}
      >
        <div className="l-story-pin">
          <div className="l-aura" aria-hidden />
          <div className="l-story-copy">
            <span className="l-num" aria-hidden key={step}>
              {String(step + 1).padStart(2, "0")}
            </span>
            <ol className="l-rail">
              {STORY.map((s, i) => (
                <li key={s.short} className={i === step ? "on" : i < step ? "done" : ""}>
                  <button type="button" onClick={() => jump(i)} aria-current={i === step ? "step" : undefined}>
                    <span className="l-rail-n">{String(i + 1).padStart(2, "0")}</span>
                    <span className="l-rail-t">{s.short}</span>
                  </button>
                </li>
              ))}
            </ol>
            <div className="l-beats">
              {STORY.map((s, i) => (
                <div key={s.short} className={`l-beat ${i === step ? "l-beat-on" : ""}`} aria-hidden={!stacked && i !== step}>
                  <p className="l-kicker">
                    {String(i + 1).padStart(2, "0")} · {s.short}
                  </p>
                  <h2>{s.title}</h2>
                  <p>{s.body}</p>
                </div>
              ))}
            </div>
            <div className="l-progress" aria-hidden>
              <span style={{ transform: `scaleX(${story})` }} />
            </div>
          </div>
          <div className="l-stage">
            <div className={`l-device l-step-${step}`}>
              <div className="l-frame">
                <img src={sampleScene} alt="Sample outfit scene" />
                <div className="l-reel" aria-hidden>
                  <span className="l-avatar" />
                  <b>@studio.fits</b>
                  <span className="l-follow">Follow</span>
                </div>
                <div className="l-scrub" aria-hidden>
                  <span />
                </div>
                <span className="l-box l-box-a">
                  <i>Jacket</i>
                </span>
                <span className="l-box l-box-b">
                  <i>Bag</i>
                </span>
                <div className="l-rules" aria-hidden>
                  <span className="l-rule l-rule-main">Shopping for · Bag</span>
                  <span className="l-rule">Under $100</span>
                  <span className="l-rule">Black</span>
                </div>
              </div>
              <div className="l-results">
                <div className="l-result">
                  <b>adidas Y-3 Canvas Tote Bag</b>
                  <span>from $93 · Similar option</span>
                  <em>Compare prices on SoleScout ↗</em>
                </div>
                <div className="l-result">
                  <b>AMIRI Canvas Tote Bag</b>
                  <span>from $90 · Similar option</span>
                  <em>Compare prices on SoleScout ↗</em>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="l-marquee" aria-hidden>
        <div className="l-track">
          {[0, 1].map((k) => (
            <div key={k} className="l-run">
              {["Jackets", "Tops", "Bags"].map((w, i) => (
                <span key={w} className="l-word">
                  {w}
                  <Loop clip={CLIPS[(i * 2 + k) % CLIPS.length]} className="tile-chip" />
                </span>
              ))}
            </div>
          ))}
        </div>
      </section>

      <section className="l-truth">
        <h2>Shopping you can trust.</h2>
        <ul>
          <li>
            <strong>Sourced prices</strong> Every price links to the page it came from, with when it was checked.
          </li>
          <li>
            <strong>Honest matches</strong> “Similar option” means similar. Only a verified listing is called a match.
          </li>
          <li>
            <strong>No checkout</strong> ClipCart sells nothing. You buy on the retailer's site.
          </li>
        </ul>
      </section>

      <section className="l-start" id="start">
        <h2>Start with your own clip.</h2>
        <Upload busy={busy} progress={progress} onFile={onFile} />
        {youtubeEnabled && <LinkInput busy={busy} onSubmit={onYouTube} error={linkError} compact />}
      </section>
    </main>
  );
}
