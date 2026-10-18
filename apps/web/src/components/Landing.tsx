import { useRef, useState } from "react";
import Upload from "./Upload";
import { COPY, WALKTHROUGH } from "./landing/content";
import { useReducedMotion } from "./landing/media";
import { Gallery, Hero, Marquee, Truth } from "./landing/sections";
import Walkthrough from "./landing/Walkthrough";
import "./landing/landing.css";

// Bundlers may inline small assets as data: URLs, which some embeds won't fetch; decode those directly.
async function toBlob(url: string) {
  if (!url.startsWith("data:")) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`sample ${r.status}`);
    return r.blob();
  }
  const [meta, data] = url.split(",");
  const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
  return new Blob([bytes], { type: meta.slice(5).split(";")[0] });
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
  onFile: (f: File) => void | Promise<void>;
  youtubeEnabled: boolean;
  onYouTube: (url: string) => void;
  linkError: string | null;
}) {
  const reduced = useReducedMotion();
  const demoRef = useRef<() => void>(() => undefined);
  const [sampleError, setSampleError] = useState<string | null>(null);
  // Set synchronously on the first click and held until the upload settles, so repeated clicks
  // while the sample is being fetched (before `busy` flips) can't start a second upload.
  const sampleLock = useRef(false);
  const [sampleBusy, setSampleBusy] = useState(false);

  // "Try this video" sends the real fc01 MP4 through the same upload flow as a picked file.
  const trySample = async () => {
    if (sampleLock.current || busy) return;
    sampleLock.current = true;
    setSampleBusy(true);
    setSampleError(null);
    try {
      let blob: Blob;
      try {
        blob = await toBlob(WALKTHROUGH.src);
      } catch {
        setSampleError("The sample video didn't load. Upload a clip instead.");
        return;
      }
      // The studio replaces the landing in place; start the user at the top of it.
      window.scrollTo({ top: 0, behavior: "auto" });
      await onFile(new File([blob], WALKTHROUGH.fileName, { type: "video/mp4" }));
    } finally {
      sampleLock.current = false;
      setSampleBusy(false);
    }
  };

  const showHow = () => {
    document.getElementById("how")?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "center" });
    demoRef.current();
  };

  return (
    <main className={`rv ${reduced ? "rv-reduced" : ""}`}>
      <Hero
        reduced={reduced}
        ctas={
          <>
            <label htmlFor="file" className="rv-btn rv-btn-main" aria-disabled={busy}>
              {busy ? "Uploading…" : COPY.ctaMain}
            </label>
            <button type="button" className="rv-btn" onClick={showHow}>
              {COPY.ctaAlt}
            </button>
          </>
        }
        link={
          youtubeEnabled && (
            <>
              <p className="rv-or">or</p>
              <LinkInput busy={busy} onSubmit={onYouTube} error={linkError} />
            </>
          )
        }
      />
      <Gallery reduced={reduced} />
      <Walkthrough reduced={reduced} busy={busy || sampleBusy} onTry={trySample} demoRef={demoRef} error={sampleError} />
      <Marquee reduced={reduced} />
      <Truth />
      <section className="rv-start" id="start">
        <h2>{COPY.startTitle}</h2>
        <Upload busy={busy} progress={progress} onFile={onFile} />
        {youtubeEnabled && <LinkInput busy={busy} onSubmit={onYouTube} error={linkError} compact />}
      </section>
    </main>
  );
}
