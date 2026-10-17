import { useRef, useState } from "react";

const ACCEPT = "image/jpeg,image/png,video/mp4,video/quicktime";

export default function Upload({
  busy,
  progress,
  onFile,
  onYoutube,
  compact,
}: {
  busy: boolean;
  progress: number | null;
  onFile: (f: File) => void;
  onYoutube?: (url: string) => void;
  compact?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [url, setUrl] = useState("");
  const pick = (files: FileList | null) => {
    const f = files?.[0];
    if (f) onFile(f);
  };
  const submitYoutube = () => {
    const trimmed = url.trim();
    if (!trimmed || !onYoutube || busy) return;
    onYoutube(trimmed);
  };
  return (
    <div
      className={`drop ${over ? "drop-over" : ""} ${compact ? "drop-compact" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (!busy) pick(e.dataTransfer.files);
      }}
    >
      <input
        ref={input}
        id="file"
        type="file"
        accept={ACCEPT}
        className="sr-only"
        onChange={(e) => {
          pick(e.target.files);
          e.target.value = "";
        }}
        disabled={busy}
      />
      {compact ? (
        <div className="drop-compact-row">
          <label htmlFor="file" className="btn btn-quiet">
            {busy ? "Working…" : "Use a different photo or clip"}
          </label>
          {onYoutube && (
            <form
              className="yt-compact"
              onSubmit={(e) => {
                e.preventDefault();
                submitYoutube();
              }}
            >
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="YouTube URL"
                disabled={busy}
                aria-label="YouTube URL"
              />
              <button type="submit" className="btn btn-quiet" disabled={busy || !url.trim()}>
                Scan
              </button>
            </form>
          )}
        </div>
      ) : (
        <>
          <p className="drop-title">Send us a look</p>
          <p className="drop-sub">A photo, a short clip, or a YouTube URL. We temporarily download YouTube clips to find the clothes.</p>
          <label htmlFor="file" className="btn btn-primary" aria-disabled={busy}>
            {busy ? "Working…" : "Choose photo or clip"}
          </label>
          <p className="drop-hint">or drop a file here</p>
          {onYoutube && (
            <form
              className="yt-form"
              onSubmit={(e) => {
                e.preventDefault();
                submitYoutube();
              }}
            >
              <label className="yt-label">
                <span>YouTube URL</span>
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=…"
                  disabled={busy}
                  autoComplete="off"
                />
              </label>
              <button type="submit" className="btn btn-primary" disabled={busy || !url.trim()}>
                {busy ? "Scanning…" : "Scan video"}
              </button>
              <p className="drop-hint">Temporary download for analysis — not tab share. Whole clip scanned locally; model sees the best stills.</p>
            </form>
          )}
        </>
      )}
      {progress !== null && (
        <div className="progress" role="progressbar" aria-valuenow={Math.round(progress * 100)} aria-valuemin={0} aria-valuemax={100}>
          <span style={{ width: `${Math.round(progress * 100)}%` }} />
        </div>
      )}
    </div>
  );
}
