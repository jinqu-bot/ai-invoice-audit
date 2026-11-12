"use client";

import { useRef } from "react";
import { ReactLenis } from "lenis/react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

type InvoiceMarker = {
  id: string;
  label: string;
  position: string;
  tone?: "orange" | "lime";
};

const INVOICE_MARKERS: InvoiceMarker[] = [
  { id: "number", label: "Invoice No. / 发票号码", position: "marker-number" },
  { id: "date", label: "Issue Date / 开票日期", position: "marker-date", tone: "lime" },
  { id: "buyer", label: "Buyer / 购买方", position: "marker-buyer", tone: "lime" },
  { id: "seller", label: "Seller / 销售方", position: "marker-seller" },
  { id: "item", label: "Item / 物件名称", position: "marker-item" },
  { id: "quantity", label: "Quantity / 数量", position: "marker-quantity", tone: "lime" },
  { id: "tax", label: "Tax Rate / 税率", position: "marker-tax", tone: "lime" },
  { id: "total", label: "Total / $", position: "marker-total" },
  { id: "rule", label: "Rule Trace / R3 · R4", position: "marker-rule", tone: "lime" },
];

const ease = (value: number) => value * value * (3 - 2 * value);

export function InvoiceMapHero() {
  const containerRef = useRef<HTMLDivElement>(null);
  const heroRef = useRef<HTMLElement>(null);
  const imageRef = useRef<HTMLDivElement>(null);
  const imageElementRef = useRef<HTMLImageElement>(null);
  const maskRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const markerRefs = useRef<Array<HTMLDivElement | null>>([]);
  const contentRef = useRef<HTMLDivElement>(null);
  const progressBarRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    const hero = heroRef.current;
    const image = imageRef.current;
    const imageElement = imageElementRef.current;
    const mask = maskRef.current;
    const grid = gridRef.current;
    const content = contentRef.current;
    const progressBar = progressBarRef.current;

    if (!hero || !image || !imageElement || !mask || !grid || !content || !progressBar) return;

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

        let maskScale = 1.12;
        let saturation = 1;
        let overlayOpacity = 0.2;
        if (progress <= 0.4) {
          maskScale = 1.12;
        } else if (progress <= 0.5) {
          const phase = ease((progress - 0.4) / 0.1);
          maskScale = 1.12 - phase * 0.12;
          saturation = 1 - phase * 0.55;
          overlayOpacity = 0.2 + phase * 0.32;
        } else if (progress <= 0.75) {
          maskScale = 1;
          saturation = 0.45;
          overlayOpacity = 0.52;
        } else if (progress <= 0.85) {
          const phase = ease((progress - 0.75) / 0.1);
          maskScale = 1 + phase * 0.12;
          saturation = 0.45 + phase * 0.55;
          overlayOpacity = 0.52 - phase * 0.32;
        } else {
          maskScale = 1.12;
          saturation = 1;
          overlayOpacity = 0.2;
        }

        gsap.set(mask, { scale: maskScale });
        gsap.set(imageElement, { filter: `saturate(${saturation})` });
        gsap.set(image, { "--source-overlay-opacity": overlayOpacity });

        const gridOpacity = progress <= 0.42
          ? 0
          : progress <= 0.5
            ? ease((progress - 0.42) / 0.08)
            : progress <= 0.78
              ? 1
              : progress <= 0.86
                ? 1 - ease((progress - 0.78) / 0.08)
                : 0;
        gsap.set(grid, { opacity: gridOpacity });

        const markerOpacity = progress <= 0.42
          ? 0
          : progress <= 0.55
            ? ease((progress - 0.42) / 0.13)
            : progress <= 0.82
              ? 1
              : progress <= 0.9
                ? 1 - ease((progress - 0.82) / 0.08)
                : 0;
        gsap.set(markerRefs.current.filter(Boolean), { opacity: markerOpacity });
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

        <div ref={maskRef} className="source-invoice-mask" aria-hidden="true">
          <span className="source-mask-top" />
          <span className="source-mask-left" />
          <span className="source-mask-right" />
          <span className="source-mask-bottom" />
          <span className="source-mask-frame" />
        </div>

        <div ref={gridRef} className="source-invoice-grid" aria-hidden="true">
          <img src="/invoice-grid-overlay.svg" alt="" />
        </div>

        {INVOICE_MARKERS.map((marker, index) => (
          <div
            key={marker.id}
            ref={(node) => { markerRefs.current[index] = node; }}
            className={`source-invoice-marker ${marker.position} ${marker.tone === "lime" ? "marker-lime" : ""}`}
          >
            <span className="source-marker-icon" />
            <p>{marker.label}</p>
          </div>
        ))}

        <div ref={contentRef} className="source-invoice-content">
          <div className="source-invoice-block">
            <div className="source-invoice-copy"><h1>Invoice Framework</h1></div>
          </div>
          <div className="source-invoice-block">
            <div className="source-invoice-copy">
              <h2>Evidence Mapping</h2>
              <p>发票主体被框定在中心窗口，桌面背景退到黑色边界之外。每个字段都对应一个可追踪坐标。</p>
            </div>
          </div>
          <div className="source-invoice-block">
            <div className="source-invoice-copy">
              <h2>Invoice Coordinates</h2>
              <p>号码、日期、购销双方、物件名称、数量、税率、合计金额与规则命中点逐一标注。</p>
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
        <div className="source-invoice-caption"><span>LIVE EVIDENCE / 03</span><b>9 FIELDS · RULE TRACE</b></div>
      </section>
      <section className="source-invoice-outro"><p>证据地图已定位，继续上传发票。</p></section>
    </div>
  );
}
