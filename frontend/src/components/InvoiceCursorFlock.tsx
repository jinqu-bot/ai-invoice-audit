"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";

// Adapted from the user's purchased ti-telescope-cursor-driven-image-flock.
// The source has 12 image slots; these six original invoice artworks repeat twice.
const ARTWORK = [
  "/invoice-flock/invoice-paper.webp",
  "/invoice-flock/audit-stamp.webp",
  "/invoice-flock/receipt-roll.webp",
  "/invoice-flock/ledger-detail.webp",
  "/invoice-flock/calculator.webp",
  "/invoice-flock/envelope.webp",
] as const;

const CONFIG = {
  slots: 12,
  desktopSize: 0.075,
  mobileSize: 0.05,
  spacing: 0.05,
  breakpoint: 1000,
  reach: 0.35,
  maxScale: 3.5,
  driftSpeed: 75,
  followSpeed: 5,
  imageAspect: 9 / 11,
};

function wrap(value: number, min: number, max: number) {
  const range = max - min;
  return (((value - min) % range) + range) % range + min;
}

export function InvoiceCursorFlock() {
  const sectionRef = useRef<HTMLElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const section = sectionRef.current;
    const canvas = canvasRef.current;
    if (!section || !canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const coarsePointer = window.matchMedia("(hover: none), (pointer: coarse)");
    const images: Array<HTMLImageElement | null> = ARTWORK.map(() => null);
    const requests: HTMLImageElement[] = [];
    const pointer = { x: 0, y: 0 };
    const focal = { x: 0, y: 0 };
    const reveal = { intensity: 0 };
    let disposed = false;
    let width = 0;
    let height = 0;
    let baseSize = 0;
    let step = 0;
    let columns = 0;
    let rows = 0;
    let reach = 0;
    let driftElapsed = 0;
    let hasPointer = false;
    let inside = false;
    let inView = false;
    let ticking = false;
    let staticMode = reducedMotion.matches || coarsePointer.matches;
    let resizeFrame = 0;
    let revealTween: gsap.core.Tween | null = null;

    function paint(deltaSeconds = 0) {
      if (disposed || !width || !height || !step || !reach) return;
      const ctx = context!;
      ctx.clearRect(0, 0, width, height);
      if (staticMode) {
        focal.x = width / 2;
        focal.y = height / 2;
      } else {
        // Clamp long background-frame gaps without changing normal source inertia.
        const dt = Math.min(deltaSeconds, 0.05);
        focal.x += (pointer.x - focal.x) * dt * CONFIG.followSpeed;
        focal.y += (pointer.y - focal.y) * dt * CONFIG.followSpeed;
        driftElapsed += dt;
      }

      const intensity = staticMode ? 1 : reveal.intensity;
      if (intensity < 0.001) return;
      const drift = staticMode ? 0 : driftElapsed * CONFIG.driftSpeed;

      for (let row = -1; row < rows; row += 1) {
        for (let col = -1; col < columns; col += 1) {
          const slot = Math.abs((col * 11 + row * 7) % CONFIG.slots);
          const image = images[slot % ARTWORK.length];
          if (!image) continue;
          const cellX = wrap(col * step + drift, -step, width + step);
          const cellY = wrap(row * step - drift, -step, height + step);
          const distance = Math.hypot(
            cellX + baseSize / 2 - focal.x,
            cellY + baseSize / 2 - focal.y,
          );
          if (distance >= reach) continue;

          const falloff = 1 - (distance / reach) ** 2;
          const scale = falloff * falloff * CONFIG.maxScale * intensity;
          if (scale < 0.02) continue;
          const drawWidth = baseSize * CONFIG.imageAspect * scale;
          const drawHeight = baseSize * scale;

          // Center-crop at render time, preserving the original generated asset.
          let cropWidth = image.naturalWidth;
          let cropHeight = image.naturalHeight;
          if (cropWidth / cropHeight > CONFIG.imageAspect) {
            cropWidth = cropHeight * CONFIG.imageAspect;
          } else {
            cropHeight = cropWidth / CONFIG.imageAspect;
          }
          ctx.drawImage(
            image,
            (image.naturalWidth - cropWidth) / 2,
            (image.naturalHeight - cropHeight) / 2,
            cropWidth,
            cropHeight,
            cellX + (baseSize - drawWidth) / 2,
            cellY + (baseSize - drawHeight) / 2,
            drawWidth,
            drawHeight,
          );
        }
      }
    }

    function tick(_elapsed: number, deltaMs: number) {
      paint(deltaMs / 1000);
    }

    function syncPlayback() {
      if (disposed) return;
      const visible = inView && !document.hidden && width > 0 && height > 0;
      revealTween?.paused(!visible);
      const shouldTick = visible && !staticMode &&
        (inside || reveal.intensity > 0.001 || revealTween !== null);
      if (shouldTick && !ticking) {
        gsap.ticker.add(tick);
        ticking = true;
      } else if (!shouldTick && ticking) {
        gsap.ticker.remove(tick);
        ticking = false;
      }
      section!.dataset.flockState = !visible ? "paused" : staticMode ? "static" : shouldTick ? "following" : "idle";
      if (visible && !ticking) paint();
    }

    function fadeTo(intensity: number, duration: number) {
      revealTween?.kill();
      revealTween = gsap.to(reveal, {
        intensity,
        duration,
        ease: "power2.inOut",
        onComplete: () => {
          revealTween = null;
          syncPlayback();
        },
      });
      syncPlayback();
    }

    function resize() {
      if (disposed) return;
      const bounds = section!.getBoundingClientRect();
      width = Math.max(0, bounds.width);
      height = Math.max(0, bounds.height);
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas!.width = Math.max(1, Math.round(width * dpr));
      canvas!.height = Math.max(1, Math.round(height * dpr));
      context!.setTransform(dpr, 0, 0, dpr, 0, 0);
      baseSize = height * (width >= CONFIG.breakpoint ? CONFIG.desktopSize : CONFIG.mobileSize);
      step = baseSize + height * CONFIG.spacing;
      columns = step ? Math.ceil(width / step) + 2 : 0;
      rows = step ? Math.ceil(height / step) + 2 : 0;
      reach = Math.min(width, height) * CONFIG.reach;
      if (!hasPointer || staticMode) {
        pointer.x = focal.x = width / 2;
        pointer.y = focal.y = height / 2;
      } else {
        pointer.x = Math.min(width, Math.max(0, pointer.x));
        pointer.y = Math.min(height, Math.max(0, pointer.y));
        focal.x = Math.min(width, Math.max(0, focal.x));
        focal.y = Math.min(height, Math.max(0, focal.y));
      }
      if (inView && !document.hidden) paint();
      syncPlayback();
    }

    function queueResize() {
      window.cancelAnimationFrame(resizeFrame);
      resizeFrame = window.requestAnimationFrame(resize);
    }

    function position(event: PointerEvent) {
      const bounds = section!.getBoundingClientRect();
      pointer.x = Math.min(width, Math.max(0, event.clientX - bounds.left));
      pointer.y = Math.min(height, Math.max(0, event.clientY - bounds.top));
      hasPointer = true;
    }

    function enter(event: PointerEvent) {
      if (staticMode || event.pointerType === "touch") return;
      position(event);
      inside = true;
      fadeTo(1, 0.5);
    }

    function move(event: PointerEvent) {
      if (staticMode || event.pointerType === "touch") return;
      position(event);
      // Also recover when layout scrolling brings this region under the cursor.
      if (!inside) {
        inside = true;
        fadeTo(1, 0.5);
      }
    }

    function leave() {
      if (staticMode) return;
      inside = false;
      fadeTo(0, 0.35);
    }

    function updateMode() {
      staticMode = reducedMotion.matches || coarsePointer.matches;
      section!.dataset.flockMode = staticMode ? "static" : "pointer";
      revealTween?.kill();
      revealTween = null;
      inside = false;
      reveal.intensity = staticMode ? 1 : 0;
      resize();
    }

    const resizeObserver = new ResizeObserver(queueResize);
    resizeObserver.observe(section);
    const intersectionObserver = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      syncPlayback();
    });
    intersectionObserver.observe(section);
    section.addEventListener("pointerenter", enter, { passive: true });
    section.addEventListener("pointermove", move, { passive: true });
    section.addEventListener("pointerleave", leave, { passive: true });
    window.addEventListener("resize", queueResize, { passive: true });
    document.addEventListener("visibilitychange", syncPlayback);
    reducedMotion.addEventListener("change", updateMode);
    coarsePointer.addEventListener("change", updateMode);
    updateMode();

    ARTWORK.forEach((src, index) => {
      const image = new Image();
      requests.push(image);
      image.decoding = "async";
      image.onload = () => {
        if (disposed) return;
        images[index] = image;
        section.dataset.loadedCount = String(images.filter(Boolean).length);
        if (inView && !document.hidden) paint();
      };
      image.onerror = () => {
        if (!disposed) section.dataset.failedCount = String(Number(section.dataset.failedCount || 0) + 1);
      };
      image.src = src;
    });

    return () => {
      disposed = true;
      window.cancelAnimationFrame(resizeFrame);
      gsap.ticker.remove(tick);
      revealTween?.kill();
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      section.removeEventListener("pointerenter", enter);
      section.removeEventListener("pointermove", move);
      section.removeEventListener("pointerleave", leave);
      window.removeEventListener("resize", queueResize);
      document.removeEventListener("visibilitychange", syncPlayback);
      reducedMotion.removeEventListener("change", updateMode);
      coarsePointer.removeEventListener("change", updateMode);
      requests.forEach((image) => {
        image.onload = null;
        image.onerror = null;
      });
      context.clearRect(0, 0, width, height);
    };
  }, []);

  return (
    <section
      ref={sectionRef}
      className="source-invoice-outro invoice-flock-region"
      aria-label="票据图群"
      data-loaded-count="0"
      data-failed-count="0"
      data-image-slots="12"
    >
      <canvas ref={canvasRef} className="invoice-flock-canvas" aria-hidden="true" />
      <div className="invoice-flock-copy">
        <p>证据地图已定位，继续上传发票。</p>
        <span className="invoice-flock-hint">移动光标，唤起票据</span>
      </div>
    </section>
  );
}
