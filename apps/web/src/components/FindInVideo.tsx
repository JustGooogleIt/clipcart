import { useState } from "react";

export default function FindInVideo({
  disabled,
  busy,
  onFind,
  reply,
}: {
  disabled?: boolean;
  busy?: boolean;
  onFind: (text: string) => Promise<void>;
  reply?: string | null;
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
        Anything visible — clothes, a plant, a painting. Be specific; short labels make weak searches.
      </p>
      <div className="find-row">
        <input
          id="find-in-video"
          value={text}
          maxLength={400}
          placeholder='e.g. find me the tall monstera in the speckled pot'
          onChange={(e) => setText(e.target.value)}
          disabled={disabled || busy}
        />
        <button className="btn btn-primary" type="submit" disabled={disabled || busy || text.trim().length < 2}>
          {busy ? "Finding…" : "Find"}
        </button>
      </div>
      {reply && (
        <p className="find-reply" role="status">
          {reply}
        </p>
      )}
    </form>
  );
}
