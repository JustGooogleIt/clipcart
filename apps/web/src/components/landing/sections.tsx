import { useEffect, useRef, useState, type ReactNode } from "react";
import { CHATTER, COPY, GALLERY, GALLERY_COLUMNS, HERO, HERO_SIDE } from "./content";
import { LoopVideo, fmt, useInView, useSize } from "./media";

/** Cycles through words in place; holds still when motion is reduced. */
function Rotator({ words, reduced }: { words: string[]; reduced: boolean }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (reduced) return;
    const t = setInterval(() => setI((n) => (n + 1) % words.length), 2200);
    return () => clearInterval(t);
  }, [words.length, reduced]);
  return (
    <span className="rv-rot">
      <span key={words[i]} className="rv-rot-word">
        {words[i]}
      </span>
    </span>
  );
}

/** fc08 front and center, two supporting clips angled behind it. */
export function Hero({ reduced, ctas, link }: { reduced: boolean; ctas: ReactNode; link: ReactNode }) {
  return (
    <section className="rv-hero">
      <div className="rv-hero-copy">
        <p className="rv-kicker">{COPY.kicker}</p>
        <h1 className="rv-hero-title">
          {COPY.titleA} <Rotator words={COPY.rotate} reduced={reduced} />
          <br />
          {COPY.titleB}
          <br />
          <span className="rv-grad">{COPY.titleGrad}</span>
        </h1>
        <p className="rv-hero-sub">{COPY.sub}</p>
        <div className="rv-ctas">{ctas}</div>
        {link}
      </div>
      <div className="rv-hero-media">
        <div className="rv-chatter" aria-hidden>
          {CHATTER.map((t, i) => (
            <span key={t} className={`rv-bubble rv-bubble-${i}`}>
              {t}
            </span>
          ))}
        </div>
        {HERO_SIDE.map((c, i) => (
          <div key={c.id} className={`rv-hero-card rv-hero-side rv-hero-side-${i}`} aria-hidden>
            <LoopVideo clip={c} reduced={reduced} />
          </div>
        ))}
        <div className="rv-hero-card rv-hero-main">
          <LoopVideo clip={HERO} reduced={reduced} label={`Fit-check clip: ${HERO.caption.toLowerCase()}`} />
        </div>
      </div>
    </section>
  );
}

/** Real fit-check clips on 9:16 cards; alternate columns sit lower. */
export function Gallery({ reduced }: { reduced: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  const { w } = useSize(ref);
  const cols = w && w < 640 ? GALLERY_COLUMNS.narrow : GALLERY_COLUMNS.wide;
  return (
    <section className="rv-gallery" aria-labelledby="rv-gallery-title">
      <header className="rv-sec-head">
        <p className="rv-kicker">{COPY.galleryKicker}</p>
        <h2 id="rv-gallery-title">{COPY.galleryTitle}</h2>
        <p className="rv-sec-sub">{COPY.gallerySub}</p>
      </header>
      <div ref={ref} className="rv-grid" style={{ ["--cols" as string]: cols }}>
        {GALLERY.map((c, i) => (
          <figure key={c.id} className={`rv-card ${(i % cols) % 2 === 1 ? "rv-lift" : ""}`}>
            <LoopVideo clip={c} reduced={reduced} label={c.caption} />
            <figcaption>
              <span>{c.caption}</span>
              <span>{fmt(c.sourceSeconds)}</span>
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}

export function Marquee({ reduced }: { reduced: boolean }) {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref);
  return (
    <section className="rv-marquee" ref={ref} aria-hidden>
      <div className="rv-track" style={{ animationPlayState: inView && !reduced ? "running" : "paused" }}>
        {[0, 1].map((k) => (
          <div key={k} className="rv-run">
            {COPY.marqueeWords.map((w, i) => (
              <span key={w} className="rv-word">
                {w}
                <span className="rv-chip">
                  <LoopVideo clip={GALLERY[(i * 2 + k) % GALLERY.length]} reduced={reduced} />
                </span>
              </span>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

export function Truth() {
  return (
    <section className="rv-truth">
      <h2>{COPY.truthTitle}</h2>
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
  );
}
