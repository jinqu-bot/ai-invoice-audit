"use client";

import { useRef } from "react";
import { ReactLenis } from "lenis/react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const ease = (value: number) => value * value * (3 - 2 * value);

export function InvoiceMapHero() {
  const containerRef = useRef<HTMLDivElement>(null);
  const heroRef = useRef<HTMLElement>(null);
  const imageRef = useRef<HTMLDivElement>(null);
  const imageElementRef = useRef<HTMLImageElement>(null);
  const maskRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const markerOneRef = useRef<HTMLDivElement>(null);
  const markerTwoRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const progressBarRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    const hero = heroRef.current;
    const image = imageRef.current;
    const imageElement = imageElementRef.current;
    const mask = maskRef.current;
    const grid = gridRef.current;
    const markerOne = markerOneRef.current;
    const markerTwo = markerTwoRef.current;
    const content = contentRef.current;
    const progressBar = progressBarRef.current;

    if (!hero || !image || !imageElement || !mask || !grid || !markerOne || !markerTwo || !content || !progressBar) {
      return;
    }

    const contentMoveDistance = () => Math.max(content.offsetHeight - window.innerHeight, 0);
    const imageMoveDistance = () => Math.max(imageElement.offsetHeight - window.innerHeight, 0);

    const trigger = ScrollTrigger.create({
      trigger: hero,
      start: "top top",
      end: () => `+=${window.innerHeight * 4}px`,
      pin: true,
      pinSpacing: true,
      scrub: 1,
      onUpdate: (self) => {
        const progress = self.progress;

        gsap.set(progressBar, { "--source-progress": progress });
        gsap.set(content, { y: -ease(progress) * contentMoveDistance() });

        const imageProgress = progress < 0.45
          ? ease(progress / 0.45) * 0.65
          : progress < 0.75
            ? 0.65
            : 0.65 + ease((progress - 0.75) / 0.25) * 0.35;
        gsap.set(image, { y: imageProgress * imageMoveDistance() });

        let maskScale = 2.5;
        let saturation = 1;
        let overlayOpacity = 0.35;
        if (progress > 0.4 && progress <= 0.5) {
          const phase = ease((progress - 0.4) / 0.1);
          maskScale = 2.5 - phase * 1.5;
          saturation = 1 - phase;
          overlayOpacity = 0.35 + phase * 0.35;
        } else if (progress > 0.5 && progress <= 0.75) {
          maskScale = 1;
          saturation = 0;
          overlayOpacity = 0.7;
        } else if (progress > 0.75 && progress <= 0.85) {
          const phase = ease((progress - 0.75) / 0.1);
          maskScale = 1 + phase * 1.5;
          saturation = phase;
          overlayOpacity = 0.7 - phase * 0.35;
        }

        gsap.set(mask, { scale: maskScale });
        gsap.set(imageElement, { filter: `saturate(${saturation})` });
        gsap.set(image, { "--source-overlay-opacity": overlayOpacity });

        const gridOpacity = progress <= 0.475
          ? 0
          : progress <= 0.5
            ? ease((progress - 0.475) / 0.025)
            : progress <= 0.75
              ? 1
              : progress <= 0.775
                ? 1 - ease((progress - 0.75) / 0.025)
                : 0;
        gsap.set(grid, { opacity: gridOpacity });

        const markerOneOpacity = progress <= 0.5
          ? 0
          : progress <= 0.525
            ? ease((progress - 0.5) / 0.025)
            : progress <= 0.7
              ? 1
              : progress <= 0.75
                ? 1 - ease((progress - 0.7) / 0.05)
                : 0;
        const markerTwoOpacity = progress <= 0.55
          ? 0
          : progress <= 0.575
            ? ease((progress - 0.55) / 0.025)
            : progress <= 0.7
              ? 1
              : progress <= 0.75
                ? 1 - ease((progress - 0.7) / 0.05)
                : 0;
        gsap.set(markerOne, { opacity: markerOneOpacity });
        gsap.set(markerTwo, { opacity: markerTwoOpacity });
      },
    });

    return () => trigger.kill();
  }, { scope: containerRef });

  return (
    <div ref={containerRef} className="source-invoice-framework">
      <ReactLenis root />
      <section ref={heroRef} className="source-invoice-hero" aria-label="发票地图滚动展示">
        <div ref={imageRef} className="source-invoice-image">
          <img ref={imageElementRef} src="/invoice-map.jpg" alt="留白发票地图" />
        </div>
        <div ref={maskRef} className="source-invoice-mask" aria-hidden="true" />
        <div ref={gridRef} className="source-invoice-grid" aria-hidden="true">
          <img src="/invoice-grid-overlay.svg" alt="" />
        </div>
        <div ref={markerOneRef} className="source-invoice-marker source-marker-one">
          <span className="source-marker-icon" />
          <p>Anchor Field / 物件名称</p>
        </div>
        <div ref={markerTwoRef} className="source-invoice-marker source-marker-two">
          <span className="source-marker-icon" />
          <p>Drift Field / $</p>
        </div>
        <div ref={contentRef} className="source-invoice-content">
          <div className="source-invoice-block">
            <div className="source-invoice-copy"><h1>Invoice Framework</h1></div>
          </div>
          <div className="source-invoice-block">
            <div className="source-invoice-copy">
              <h2>Evidence Mapping</h2>
              <p>发票被拆成可追踪的证据坐标。买方与卖方信息保持留白，审核只读取必要字段。</p>
            </div>
          </div>
          <div className="source-invoice-block">
            <div className="source-invoice-copy">
              <h2>Active Fields</h2>
              <p>物件名称、日期、税率与规则命中点在地图中逐一定位；具体金额统一用 $ 表示。</p>
            </div>
          </div>
          <div className="source-invoice-block">
            <div className="source-invoice-copy">
              <h2>Audit Center</h2>
              <p>滚动完成后，字段回到审核中心，继续上传发票并查看可解释的结论。</p>
            </div>
          </div>
        </div>
        <div ref={progressBarRef} className="source-invoice-progress" aria-hidden="true" />
        <div className="source-invoice-caption"><span>LIVE EVIDENCE / 03</span><b>物件名称 · $</b></div>
      </section>
      <section className="source-invoice-outro"><p>证据地图已定位，继续上传发票。</p></section>
    </div>
  );
}
