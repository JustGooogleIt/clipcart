import { useRef, useState } from "react";

const ACCEPT = "image/jpeg,image/png,video/mp4,video/quicktime";

export default function Upload({
  busy,
  progress,
  onFile,
  compact,
}: {
  busy: boolean;
  progress: number | null;
  onFile: (f: File) => void;
  compact?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const pick = (files: FileList | null) => {
    const f = files?.[0];
    if (f) onFile(f);
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
        <label htmlFor="file" className="btn btn-quiet">
          {busy ? "Uploading…" : "Use a different photo or clip"}
        </label>
      ) : (
        <>
          <p className="drop-title">Send us a look</p>
          <p className="drop-sub">A photo or a short clip of an outfit. JPEG, PNG, MP4 or MOV, up to 90 seconds.</p>
          <label htmlFor="file" className="btn btn-primary" aria-disabled={busy}>
            {busy ? "Uploading…" : "Choose photo or clip"}
          </label>
          <p className="drop-hint">or drop a file here</p>
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
