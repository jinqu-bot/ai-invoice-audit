"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import gsap from "gsap";
import styles from "./InvoiceUploadReveal.module.css";

const CHARACTERS = " .:-=+*xX#%@0369B&";
const MAX_CELLS = 1000;
const INK = "#ff591f";

/** Full-page adaptation of the purchased GoodFella choreography. */
export function InvoiceUploadReveal({ children, replayVersion }: { children: ReactNode; replayVersion: number }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const curtainRef = useRef<HTMLDivElement>(null);
  const finishRef = useRef<() => void>(() => {});
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    const root = rootRef.current;
    const curtain = curtainRef.current;
    if (!mounted || !root || !curtain) return;
    const image = root.querySelector<HTMLImageElement>("[data-reveal-image]")!;
    const grid = root.querySelector<HTMLDivElement>("[data-ascii]")!;
    const title = root.querySelector<HTMLElement>("[data-page-title]")!;
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let context: gsap.Context | undefined;
    let disposed = false;
    let skipped = false;
    let version = 0;
    let firstFrame = 0;
    let secondFrame = 0;

    function reset() {
      context?.revert();
      context = undefined;
      grid.replaceChildren();
    }

    function showImage(phase: string) {
      reset();
      root!.dataset.phase = phase;
      image.style.opacity = "1";
      grid.style.opacity = "0";
      curtain!.style.display = "none";
    }
    function finish() { skipped = true; ++version; window.clearTimeout(loadTimeout); showImage("complete"); }
    finishRef.current = finish;

    function animate() {
      if (disposed || skipped) return;
      if (motion.matches) { showImage("reduced-motion"); return; }
      reset();
      try {
        const aspect = image.naturalWidth / Math.max(1, image.naturalHeight);
        let columns = Math.max(1, Math.floor(Math.sqrt(MAX_CELLS * aspect)));
        let rows = Math.max(1, Math.floor(columns / aspect));
        while (columns * rows > MAX_CELLS) {
          if (columns >= rows) columns -= 1;
          else rows -= 1;
        }
        const sampler = document.createElement("canvas");
        sampler.width = columns;
        sampler.height = rows;
        const canvas = sampler.getContext("2d", { willReadFrequently: true });
        if (!canvas) { showImage("image-fallback"); return; }
        canvas.drawImage(image, 0, 0, columns, rows);
        const pixels = canvas.getImageData(0, 0, columns, rows).data;
        const cells: { element: HTMLSpanElement; distance: number; opacity: number }[] = [];
        const fragment = document.createDocumentFragment();
        for (let row = 0; row < rows; row++) {
          for (let col = 0; col < columns; col++) {
            const offset = (row * columns + col) * 4;
            // Transparent pixels must stay blank instead of becoming a rectangle.
            const brightness = (pixels[offset] * .299 + pixels[offset + 1] * .587 + pixels[offset + 2] * .114) / 255;
            const alpha = pixels[offset + 3] / 255;
            const visible = alpha > .1 && brightness >= .1;
            const element = document.createElement("span");
            element.textContent = visible ? CHARACTERS[Math.floor(brightness * (CHARACTERS.length - 1))] : " ";
            element.style.opacity = "0";
            fragment.appendChild(element);
            cells.push({ element, distance: Math.hypot(col - (columns - 1) / 2, row - (rows - 1) / 2), opacity: visible ? (.1 + brightness * .9) * alpha : 0 });
          }
        }
        grid.style.gridTemplateColumns = `repeat(${columns}, 1fr)`;
        grid.style.gridTemplateRows = `repeat(${rows}, 1fr)`;
        grid.style.fontSize = `${88 / rows}cqh`;
        grid.appendChild(fragment);
        cells.sort((a, b) => a.distance - b.distance);
        const waveDelay = 1.05 / (cells[cells.length - 1]?.distance || 1);
        let opacityHead = 0;
        let colorHead = 0;
        const wave = { time: 0 };
        root!.dataset.phase = "folding";
        context = gsap.context(() => {
          const blocks = curtain!.querySelectorAll<HTMLElement>("[data-fold]");
          const nested = Array.from(blocks).slice(1);
          const loader = curtain!.querySelector<HTMLElement>("[data-loader]")!;
          const loadingCopy = curtain!.querySelectorAll<HTMLElement>("[data-loading-char]");
          const covers = root!.querySelectorAll<HTMLElement>("[data-cover]");
          const pageParts = root!.querySelectorAll<HTMLElement>("[data-page-enter]");
          const navigation = document.querySelectorAll<HTMLElement>(".audit-side-nav, .audit-mobile-nav");
          gsap.set(image, { opacity: 0 });
          gsap.set(grid, { opacity: 1 });
          gsap.set(curtain, { display: "flex", opacity: 1, "--wipe": "0deg" });
          gsap.set(nested, { rotation: -180, transformOrigin: "left center" });
          gsap.set(title, { opacity: 0 });
          gsap.set(pageParts, { autoAlpha: 0, y: 30 });
          gsap.set(navigation, { autoAlpha: 0, y: -60 });
          gsap.set(covers, { scaleX: 0, xPercent: 0, transformOrigin: "left center" });
          // The body portal includes the persistent navigation in the wipe.
          const timeline = gsap.timeline({ onComplete: () => { root!.dataset.phase = "complete"; } });
          timeline.fromTo(loadingCopy, { opacity: 0 }, { opacity: 1, duration: .15, stagger: .07 }, .15);
          timeline.fromTo(loader, { scale: 0 }, { scale: 1, duration: .35, ease: "back.out(1.8)", transformOrigin: "25% center" }, .15);
          timeline.to(nested, { rotation: 0, duration: .55, stagger: .4, ease: "power3.inOut" }, .4);
          timeline.to([loader, ...loadingCopy], { opacity: 0, duration: .25 }, 1.75);
          timeline.to(curtain, { "--wipe": "90deg", duration: 1, ease: "power3.inOut", onStart: () => { root!.dataset.phase = "wipe"; } }, 2);
          timeline.set(curtain, { display: "none" }, 3);
          timeline.to(navigation, { autoAlpha: 1, y: 0, duration: .85, ease: "power3.out" }, 2.35);
          covers.forEach((cover, index) => {
            const start = 2.7 + index * .12;
            timeline.to(cover, { scaleX: 1, duration: .7, ease: "power3.inOut" }, start);
            timeline.to(cover, { scaleX: 0, xPercent: 100, duration: .7, ease: "power3.inOut" }, start + .7);
          });
          timeline.set(title, { opacity: 1 }, 3.4);
          timeline.to(pageParts, { autoAlpha: 1, y: 0, duration: .8, stagger: .08, ease: "power3.out" }, 3.05);
          timeline.to(wave, {
            time: 1.55, duration: 1.55, ease: "none",
            onStart: () => { root!.dataset.phase = "ascii"; },
            onUpdate: () => {
              while (opacityHead < cells.length && cells[opacityHead].distance * waveDelay <= wave.time) {
                const cell = cells[opacityHead++];
                cell.element.style.opacity = String(cell.opacity);
              }
              while (colorHead < cells.length && cells[colorHead].distance * waveDelay <= wave.time - .5) {
                cells[colorHead++].element.style.color = INK;
              }
            },
          }, 3.05);
          timeline.to(image, { opacity: 1, duration: .65, ease: "power2.out", onStart: () => { root!.dataset.phase = "settling"; } }, 4.85);
          timeline.to(grid, { opacity: 0, duration: .6, ease: "power2.out" }, 4.85);
        }, root!);
      } catch {
        showImage("image-fallback");
      }
    }

    function ready() {
      if (skipped || disposed) return;
      const current = ++version;
      if (!image.naturalWidth) return;
      window.clearTimeout(loadTimeout);
      // Let the existing route snapshot animation finish before revealing.
      firstFrame = requestAnimationFrame(() => {
        secondFrame = requestAnimationFrame(() => {
          const transitions = document.getAnimations().filter(animation =>
            typeof CSSAnimation !== "undefined" && animation instanceof CSSAnimation && animation.animationName.startsWith("audit-page-"));
          void Promise.allSettled(transitions.map(animation => animation.finished)).then(() => {
            if (!disposed && version === current) animate();
          });
        });
      });
    }

    function failed() {
      if (skipped || disposed) return;
      skipped = true;
      ++version;
      window.clearTimeout(loadTimeout);
      showImage("unavailable");
    }
    function preferenceChanged() {
      ++version;
      if (motion.matches) showImage("reduced-motion");
      else if (image.naturalWidth) ready();
    }

    const loadTimeout = window.setTimeout(failed, 8000);
    function keydown(event: KeyboardEvent) { if (event.key === "Escape") finish(); }
    window.addEventListener("keydown", keydown);
    image.addEventListener("load", ready);
    image.addEventListener("error", failed);
    motion.addEventListener("change", preferenceChanged);
    if (image.complete) {
      if (image.naturalWidth) ready();
      else failed();
    }
    return () => {
      disposed = true;
      ++version;
      window.clearTimeout(loadTimeout);
      cancelAnimationFrame(firstFrame);
      cancelAnimationFrame(secondFrame);
      image.removeEventListener("load", ready);
      image.removeEventListener("error", failed);
      motion.removeEventListener("change", preferenceChanged);
      window.removeEventListener("keydown", keydown);
      finishRef.current = () => {};
      reset();
      curtain.style.display = "none";
    };
  }, [mounted, replayVersion]);

  return (
    <div ref={rootRef} className={`audit-shell upload-page ${styles.page}`} data-invoice-page-reveal data-phase="loading">
      {children}
      {mounted && createPortal(
        <div ref={curtainRef} className={styles.curtain} data-page-curtain>
          <button type="button" className={styles.skip} onClick={() => finishRef.current()}>跳过动画 ↗</button>
          <div className={styles.loader} data-loader aria-hidden="true">
            <div className={styles.fold} data-fold><div className={styles.fold} data-fold><div className={styles.fold} data-fold><div className={styles.fold} data-fold /></div></div></div>
          </div>
          <div className={styles.loadingCopy} aria-hidden="true">{Array.from("EVIDENCE").map((char, index) => <span key={index} data-loading-char>{char}</span>)}</div>
        </div>, document.body
      )}
    </div>
  );
}

export function InvoiceRevealTitle() {
  return <h1 className={styles.title}><span data-page-title>上传发票</span><span className={styles.orangeCover} data-cover aria-hidden="true" /><span className={styles.whiteCover} data-cover aria-hidden="true" /></h1>;
}

export function InvoiceRevealArtwork() {
  return (
    <figure className={styles.artwork} aria-hidden="true">
      <div className={styles.frame}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img data-reveal-image src="/upload-reveal/invoice-desk.png" width="1024" height="1024" alt="" draggable={false} />
        <div className={styles.ascii} data-ascii />
      </div>
      <figcaption className={styles.caption} data-page-enter>从票面，到依据</figcaption>
    </figure>
  );
}
