import { useEffect, useRef, useState, type RefObject } from "react";
import type { Clip } from "./content";

export const fmt = (s: number) => {
  if (!Number.isFinite(s)) return "–:––";
  const t = Math.max(0, Math.round(s));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};

/** True while the element is on (or near) screen. */
export function useInView(ref: RefObject<Element>, margin = "80px") {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setOn(e.isIntersecting), { rootMargin: margin });
    io.observe(el);
    return () => io.disconnect();
  }, [ref, margin]);
  return on;
}

export function useReducedMotion() {
  const q = "(prefers-reduced-motion: reduce)";
  const [on, setOn] = useState(() => window.matchMedia(q).matches);
  useEffect(() => {
    const m = window.matchMedia(q);
    const h = () => setOn(m.matches);
    m.addEventListener("change", h);
    return () => m.removeEventListener("change", h);
  }, []);
  return on;
}

export function useSize(ref: RefObject<Element>) {
  const [size, setSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);
  return size;
}

/** Where the video's picture sits inside its box under object-fit: cover. */
export function coverRect(cw: number, ch: number, vw: number, vh: number) {
  if (!cw || !ch) return { x: 0, y: 0, w: cw, h: ch };
  const s = Math.max(cw / vw, ch / vh);
  return { x: (cw - vw * s) / 2, y: (ch - vh * s) / 2, w: vw * s, h: vh * s };
}

/**
 * Muted, inline, looping clip that plays only while on screen.
 * With reduced motion it never autoplays and shows its poster frame.
 */
export function LoopVideo({ clip, reduced, label }: { clip: Clip; reduced: boolean; label?: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  const inView = useInView(ref);
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    v.muted = true;
    if (inView && !reduced) v.play().catch(() => undefined);
    else v.pause();
  }, [inView, reduced]);
  return (
    <video
      ref={ref}
      src={clip.src}
      poster={clip.poster}
      muted
      loop
      playsInline
      preload="metadata"
      aria-label={label}
      aria-hidden={label ? undefined : true}
    />
  );
}
