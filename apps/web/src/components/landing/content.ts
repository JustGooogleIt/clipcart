// Landing copy and media, ported from the approved preview (landing-video artifact, default settings).
// Media is built from downloads/fit-checks/ by apps/web/scripts/landing-media.sh.
import fc01Sample from "../../assets/landing/fc01-sample.mp4";
import fc01Poster from "../../assets/landing/fc01-poster.jpg";
import fc02 from "../../assets/landing/fc02-loop.mp4";
import fc02Poster from "../../assets/landing/fc02-poster.jpg";
import fc03 from "../../assets/landing/fc03-loop.mp4";
import fc03Poster from "../../assets/landing/fc03-poster.jpg";
import fc04 from "../../assets/landing/fc04-loop.mp4";
import fc04Poster from "../../assets/landing/fc04-poster.jpg";
import fc05 from "../../assets/landing/fc05-loop.mp4";
import fc05Poster from "../../assets/landing/fc05-poster.jpg";
import fc06 from "../../assets/landing/fc06-loop.mp4";
import fc06Poster from "../../assets/landing/fc06-poster.jpg";
import fc07 from "../../assets/landing/fc07-loop.mp4";
import fc07Poster from "../../assets/landing/fc07-poster.jpg";
import fc08 from "../../assets/landing/fc08-loop.mp4";
import fc08Poster from "../../assets/landing/fc08-poster.jpg";
import fc09 from "../../assets/landing/fc09-loop.mp4";
import fc09Poster from "../../assets/landing/fc09-poster.jpg";
import fc10 from "../../assets/landing/fc10-loop.mp4";
import fc10Poster from "../../assets/landing/fc10-poster.jpg";

export type Clip = {
  id: string;
  src: string;
  poster: string;
  /** Visible outfit, not a product name. */
  caption: string;
  /** Length of the full source fit-check, in seconds. Loops are short excerpts. */
  sourceSeconds: number;
};

const clip = (id: string, src: string, poster: string, caption: string, sourceSeconds: number): Clip => ({ id, src, poster, caption, sourceSeconds });

export const HERO = clip("fc08", fc08, fc08Poster, "Little black dress", 11.1);
export const HERO_SIDE = [clip("fc05", fc05, fc05Poster, "Safari jacket", 64.6), clip("fc09", fc09, fc09Poster, "Leopard top, wide jeans", 13.1)];

export const GALLERY: Clip[] = [
  HERO_SIDE[0],
  HERO_SIDE[1],
  clip("fc02", fc02, fc02Poster, "Camo jacket, street", 57.0),
  clip("fc07", fc07, fc07Poster, "Graphic pullover", 45.8),
  clip("fc10", fc10, fc10Poster, "White kurta", 23.8),
  clip("fc06", fc06, fc06Poster, "Polo lineup", 65.3),
  clip("fc03", fc03, fc03Poster, "Rate the fit", 11.4),
  clip("fc04", fc04, fc04Poster, "White shirt, street", 5.6),
];
export const GALLERY_COLUMNS = { wide: 4, narrow: 2 };

/**
 * Walkthrough: the original fc01 clip, paused at 22s on the jacket.
 * The box is illustrative (placed by hand, percent of the video frame), not Perceptron output.
 */
export const WALKTHROUGH = {
  id: "fc01",
  src: fc01Sample,
  poster: fc01Poster,
  fileName: "fc01_zf6CmntK3BY.mp4",
  t: 22,
  label: "Jacket",
  box: { x: 6, y: 31, w: 92, h: 66 },
  /** Source frame size, used to map the box onto the cropped video. */
  frame: { w: 720, h: 1280 },
};

export const COPY = {
  kicker: "Shop the fit · from any frame",
  titleA: "Saw that",
  rotate: ["jacket", "dress", "shirt", "jeans", "top"],
  titleB: "in a video?",
  titleGrad: "Tap it. Shop it.",
  sub: "No more “link?” in the comments. Upload a clip, tap the piece, and ClipCart finds where it's actually sold, in your size and under your budget.",
  ctaMain: "Upload a clip",
  ctaAlt: "See how it works",
  galleryKicker: "Real fit checks",
  galleryTitle: "Every fit check is a shop window.",
  gallerySub: "Street interviews, store try-ons and mirror checks. Pause on a piece and shop it.",
  walkKicker: "How it works",
  walkTitle: "Pause. Tap. Shop that piece.",
  tryVideo: "Try this video",
  steps: [
    { short: "Drop in a clip", title: "Any fit check. Any clip.", body: "A creator's fit check, a street interview, a scene you paused on." },
    { short: "Pause on the moment", title: "Stop on the frame that has it.", body: "Scrub to the second the piece is clearly in view." },
    { short: "Tap the piece", title: "Tap the one you want.", body: "Boxes mark what's shoppable. Missed one? Draw your own." },
    { short: "Shop that piece", title: "Only that piece is searched.", body: "Every price links to its source. Matches are labeled honestly: similar option, likely or verified. No checkout." },
  ],
  marqueeWords: ["Jackets", "Dresses", "Denim"],
  truthTitle: "Shopping you can trust.",
  startTitle: "Start with your own clip.",
};

export const CHATTER = ["link??", "where's the jacket from 😭", "need that dress", "drop the link pls"];
