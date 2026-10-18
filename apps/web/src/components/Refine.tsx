import { useState } from "react";

export default function Refine({ disabled, onSend, reply }: { disabled: boolean; onSend: (t: string) => void; reply: string | null }) {
  const [text, setText] = useState("");
  return (
    <form
      className="refine"
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) {
          onSend(text.trim());
          setText("");
        }
      }}
    >
      <label htmlFor="refine">Refine</label>
      <div className="refine-row">
        <input id="refine" value={text} maxLength={300} placeholder="e.g. under $80 in black, no leather" onChange={(e) => setText(e.target.value)} disabled={disabled} />
        <button className="btn" type="submit" disabled={disabled || !text.trim()}>
          Update
        </button>
      </div>
      {reply && <p className="refine-reply" role="status">{reply}</p>}
    </form>
  );
}
