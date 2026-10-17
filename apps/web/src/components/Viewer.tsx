import { useRef, useState } from "react";
import { mediaUrl, timestamp } from "../api";
import type { FrameRef, GarmentDoc, GarmentObservation } from "../types";

type Box = [number, number, number, number];

export default function Viewer({
  frames,
  frameId,
  onFrame,
  observations,
  garmentOf,
  selectedGarmentId,
  onSelectGarment,
  drawing,
  draft,
  onDraft,
  isVideo,
}: {
  frames: FrameRef[];
  frameId: string | null;
  onFrame: (id: string) => void;
  observations: GarmentObservation[];
  garmentOf: Record<string, GarmentDoc>;
  selectedGarmentId: string | null;
  onSelectGarment: (gid: string) => void;
  drawing: boolean;
  draft: Box | null;
  onDraft: (b: Box | null) => void;
  isVideo: boolean;
}) {
  const frame = frames.find((f) => f.assetId === frameId) ?? frames[0];
  const area = useRef<HTMLDivElement>(null);
  const [start, setStart] = useState<[number, number] | null>(null);
  if (!frame) return null;
  const onThis = observations.filter((o) => o.frameAssetId === frame.assetId);

  const pos = (e: React.PointerEvent): [number, number] => {
    const r = area.current!.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
  };
  const toBox = (a: [number, number], b: [number, number]): Box => [
    Math.min(a[0], b[0]),
    Math.min(a[1], b[1]),
    Math.max(a[0], b[0]),
    Math.max(a[1], b[1]),
  ];

  return (
    <div className="viewer">
      <div
        ref={area}
        className={`stage ${drawing ? "stage-drawing" : ""}`}
        // Width follows the frame's aspect so percentage boxes stay aligned even when height is capped.
        style={{ aspectRatio: `${frame.width} / ${frame.height}`, width: `min(100%, calc(70vh * ${frame.width / frame.height}))` }}
        onPointerDown={(e) => {
          if (!drawing) return;
          (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
          const p = pos(e);
          setStart(p);
          onDraft([p[0], p[1], p[0], p[1]]);
        }}
        onPointerMove={(e) => drawing && start && onDraft(toBox(start, pos(e)))}
        onPointerUp={(e) => {
          if (!drawing || !start) return;
          const b = toBox(start, pos(e));
          setStart(null);
          onDraft(b[2] - b[0] > 0.03 && b[3] - b[1] > 0.03 ? b : null);
        }}
      >
        <img src={mediaUrl(frame.assetId)} alt={isVideo ? `Frame at ${timestamp(frame.timestampMs)}` : "Uploaded photo"} draggable={false} />
        {!drawing &&
          onThis.map((o) => {
            const g = garmentOf[o.id];
            const sel = g && g.id === selectedGarmentId;
            const [x0, y0, x1, y1] = o.box01 as unknown as [number, number, number, number];
            return (
              <button
                key={o.id}
                type="button"
                className={`box ${sel ? "box-selected" : ""} ${o.editedByUser ? "box-user" : ""}`}
                style={{ left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%` }}
                onClick={() => g && onSelectGarment(g.id)}
                aria-label={`Select ${g?.label ?? o.category}`}
                aria-pressed={!!sel}
              >
                <span className="box-label">{g?.label ?? o.category}</span>
              </button>
            );
          })}
        {draft && (
          <div
            className="box box-draft"
            style={{
              left: `${draft[0] * 100}%`,
              top: `${draft[1] * 100}%`,
              width: `${(draft[2] - draft[0]) * 100}%`,
              height: `${(draft[3] - draft[1]) * 100}%`,
            }}
            aria-hidden
          />
        )}
      </div>
      {frames.length > 1 && (
        <ol className="strip" aria-label="Sampled frames">
          {frames.map((f) => (
            <li key={f.assetId}>
              <button
                type="button"
                className={`thumb ${f.assetId === frame.assetId ? "thumb-on" : ""}`}
                onClick={() => onFrame(f.assetId)}
                aria-label={`Frame at ${timestamp(f.timestampMs)}`}
              >
                <img src={mediaUrl(f.assetId)} alt="" loading="lazy" />
                <span>{timestamp(f.timestampMs)}</span>
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
