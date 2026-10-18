import { useState } from "react";

/** What Find reports back: what it found, where, and the full description it searches with. */
export interface FindReply {
  tone: "found" | "error";
  headline: string;
  where?: string | null;
  description?: string | null;
}

export default function FindInVideo({
  disabled,
  busy,
  onFind,
  reply,
}: {
  disabled?: boolean;
  busy?: boolean;
  onFind: (text: string) => Promise<void>;
  reply?: FindReply | null;
}) {
  const [text, setText] = useState("");
  return (
    <form
      className="find-in-video"
      onSubmit={(e) => {
        e.preventDefault();
        const t = text.trim();
        if (t && !disabled && !busy) void onFind(t).then(() => setText(""));
      }}
    >
      <label htmlFor="find-in-video">Find in video</label>
      <p className="muted small">
        Anything visible — clothes, a plant, a painting. Name color, material, shape, and distinctive details; we keep that full description for search.
      </p>
      <div className="find-row">
        <input
          id="find-in-video"
          value={text}
          maxLength={400}
          placeholder='e.g. find me the light-wash denim trucker with copper rivets'
          onChange={(e) => setText(e.target.value)}
          disabled={disabled || busy}
        />
        <button className="btn btn-primary" type="submit" disabled={disabled || busy || text.trim().length < 2}>
          {busy ? "Finding…" : "Find"}
        </button>
      </div>
      {reply && (
        <div className={`find-reply find-reply-${reply.tone}`} role={reply.tone === "error" ? "alert" : "status"}>
          <p className="find-reply-head">
            {reply.headline}
            {reply.where && <span className="find-reply-where"> · {reply.where}</span>}
          </p>
          {reply.description && (
            <p className="find-reply-desc">
              <span>Searching with</span> {reply.description}
            </p>
          )}
        </div>
      )}
    </form>
  );
}
