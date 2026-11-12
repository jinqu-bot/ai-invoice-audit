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
  { id: "title", label: "Title / 发票", position: "marker-title" },
  { id: "code", label: "Code Area / 密码区", position: "marker-code", tone: "lime" },
  { id: "sales", label: "Sales Volume / 销售量", position: "marker-sales" },
  { id: "item", label: "Item / 项目名称", position: "marker-item", tone: "lime" },
  { id: "spec", label: "Spec / 规格型号", position: "marker-spec" },
  { id: "unit", label: "Unit / 单位", position: "marker-unit", tone: "lime" },
  { id: "quantity", label: "Quantity / 数量", position: "marker-quantity" },
  { id: "unit-price", label: "Unit Price / 单价", position: "marker-unit-price", tone: "lime" },
  { id: "amount", label: "Amount / $", position: "marker-amount" },
  { id: "seller", label: "Seller / 销售方", position: "marker-seller", tone: "lime" },
  { id: "buyer", label: "Buyer / 购买方", position: "marker-buyer" },
  { id: "date", label: "Issue Date / 开票日期", position: "marker-date", tone: "lime" },
];

const ease = (value: number) => value * value * (3 - 2 * value);

export function InvoiceMapHero() {
  const containerRef = useRef<HTMLDivElement>(null);
  const heroRef = useRef<HTMLElement>(null);
  const imageRef = useRef<HTMLDivElement>(null);
  const photoRef = useRef<HTMLDivElement>(null);
  const imageElementRef = useRef<HTMLImageElement>(null);
  const flatImageRef = useRef<HTMLImageElement>(null);
  const maskRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const markerRefs = useRef<Array<HTMLDivElement | null>>([]);
  const contentRef = useRef<HTMLDivElement>(null);
  const progressBarRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    const hero = heroRef.current;
    const image = imageRef.current;
    const photo = photoRef.current;
    const imageElement = imageElementRef.current;
    const flatImage = flatImageRef.current;
    const mask = maskRef.current;
    const grid = gridRef.current;
    const content = contentRef.current;
    const progressBar = progressBarRef.current;

    if (!hero || !image || !photo || !imageElement || !flatImage || !mask || !grid || !content || !progressBar) return;

    const contentMoveDistance = () => Math.max(content.offsetHeight - window.innerHeight, 0);
    const imageMoveDistance = () => Math.max(image.offsetHeight - window.innerHeight, 0);

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

        // The purchased reference starts with a small, tilted map and resolves
        // into a larger, upright field as the scroll reaches the center phase.
        const resolveProgress = progress <= 0.52 ? ease(progress / 0.52) : 1;
        const photoScale = 0.7 + resolveProgress * 0.3;
        const photoRotation = 0;
        gsap.set(photo, { scale: photoScale, rotation: photoRotation });

        const extractionProgress = progress <= 0.34
          ? 0
          : progress <= 0.56
            ? ease((progress - 0.34) / 0.22)
            : 1;
        gsap.set(imageElement, { opacity: 1 - extractionProgress });
        gsap.set(flatImage, { opacity: extractionProgress });

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
        gsap.set(flatImage, { filter: `saturate(${saturation})` });
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

        const markerOpacity = progress <= 0.54
          ? 0
          : progress <= 0.62
            ? ease((progress - 0.54) / 0.08)
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
          <div ref={photoRef} className="source-invoice-photo">
            <img ref={imageElementRef} className="source-invoice-photo-raw" src="/invoice-map-desktop.jpg" alt="桌面上的发票照片" />
            <img ref={flatImageRef} className="source-invoice-photo-flat" src="/invoice-flat.jpg" alt="透视校正后的发票" />
            <div className="source-invoice-field-layer" aria-label="发票字段标注">
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
            </div>
          </div>
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
              <p>标题、密码区、项目名称、规格型号、单位、数量、单价、金额、购销双方与开票日期逐一标注。</p>
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
        <div className="source-invoice-caption"><span>LIVE EVIDENCE / 03</span><b>12 FIELDS · INVOICE MAP</b></div>
      </section>
      <section className="source-invoice-outro"><p>证据地图已定位，继续上传发票。</p></section>
    </div>
  );
}
