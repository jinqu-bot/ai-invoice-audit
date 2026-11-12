"use client";

import { useEffect, useRef, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

type NodeSpec = {
  id: string;
  label: string;
  freeX: number;
  freeY: number;
  freeRotate: number;
  gridX: number;
  gridY: number;
  tone: "orange" | "blue" | "paper";
};

const NODES: NodeSpec[] = [
  { id: "number", label: "NO. 26232000000859984741", freeX: -40, freeY: -31, freeRotate: -14, gridX: -25, gridY: -27, tone: "paper" },
  { id: "date", label: "DATE / 2026-08-15", freeX: 35, freeY: -35, freeRotate: 11, gridX: 24, gridY: -27, tone: "orange" },
  { id: "buyer", label: "BUYER / __________", freeX: -46, freeY: -4, freeRotate: 8, gridX: -27, gridY: -7, tone: "blue" },
  { id: "seller", label: "SELLER / __________", freeX: 47, freeY: -4, freeRotate: -9, gridX: 27, gridY: -7, tone: "paper" },
  { id: "item", label: "ITEM / 物件名称", freeX: -48, freeY: 23, freeRotate: -16, gridX: -27, gridY: 14, tone: "paper" },
  { id: "amount", label: "AMOUNT / $", freeX: 46, freeY: 22, freeRotate: 15, gridX: 27, gridY: 14, tone: "orange" },
  { id: "rule", label: "R3 / R4", freeX: -26, freeY: 40, freeRotate: -7, gridX: -13, gridY: 31, tone: "orange" },
  { id: "source", label: "OPENAI-COMPAT", freeX: 26, freeY: 40, freeRotate: 7, gridX: 13, gridY: 31, tone: "blue" },
];

const clamp = (value: number, min = 0, max = 1) => Math.min(max, Math.max(min, value));
const smooth = (value: number) => value * value * (3 - 2 * value);

function InvoicePaper() {
  return (
    <div className="map-invoice-paper">
      <div className="map-invoice-topline"><span>电子发票（普通发票）</span><span>AI / AUDIT COPY</span></div>
      <div className="map-invoice-title"><div className="map-qr"><i /><i /><i /><i /></div><div><small>INVOICE MAP / 08</small><strong>发票审核凭证</strong></div><span>2026<br /><b>08.15</b></span></div>
      <div className="map-invoice-rule" />
      <div className="map-invoice-columns"><div><small>购买方</small><b>________________</b><span>个人信息留白</span></div><div><small>销售方</small><b>________________</b><span>公司信息留白</span></div></div>
      <div className="map-invoice-line"><span>物件名称</span><b>1</b><b>$</b><b>13%</b></div>
      <div className="map-invoice-total"><small>价税合计（小写）</small><strong>$</strong></div>
      <div className="map-invoice-bottom"><span>识别来源 · openai-compat</span><span>命中 · R3 / R4</span></div>
      <div className="map-review-stamp">REVIEW</div>
    </div>
  );
}

export function InvoiceMapHero() {
  const scrollRef = useRef<HTMLElement>(null);
  const [progress, setProgress] = useState(0);
  const [pointer, setPointer] = useState({ x: 0, y: 0 });
  const [manualGrid, setManualGrid] = useState(false);
  const [selected, setSelected] = useState("amount");

  useEffect(() => {
    const update = () => {
      const element = scrollRef.current;
      if (!element) return;
      const distance = Math.max(element.offsetHeight - window.innerHeight, 1);
      setProgress(clamp(-element.getBoundingClientRect().top / distance));
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => { window.removeEventListener("scroll", update); window.removeEventListener("resize", update); };
  }, []);

  useEffect(() => {
    if (!scrollRef.current) return;
    gsap.registerPlugin(ScrollTrigger);
    const context = gsap.context(() => {
      const timeline = gsap.timeline({
        scrollTrigger: {
          trigger: scrollRef.current,
          start: "top top",
          end: "bottom bottom",
          scrub: 1,
        },
      });
      timeline
        .fromTo(".map-invoice-core", { xPercent: -50, yPercent: -50, scale: 0.72, rotation: -9, opacity: 0.45 }, { xPercent: -50, yPercent: -50, scale: 1, rotation: 0, opacity: 1, ease: "none" }, 0.12)
        .to(".map-invoice-core", { xPercent: -50, yPercent: -50, scale: 0.9, rotation: 5, opacity: 0.78, ease: "none" }, 0.74)
        .fromTo(".map-connection-dash", { strokeDashoffset: 120 }, { strokeDashoffset: 0, ease: "none" }, 0.16);
      gsap.fromTo(".map-copy", { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: 1.1, ease: "power3.out" });
    }, scrollRef);
    return () => context.revert();
  }, []);

  const snap = manualGrid ? 1 : smooth(clamp((progress - 0.1) / 0.55));
  const release = manualGrid ? 0 : smooth(clamp((progress - 0.72) / 0.28));
  const phase = manualGrid ? "grid" : progress < 0.25 ? "free" : progress < 0.72 ? "snap" : "release";
  const mapStyle = { "--map-progress": progress, "--map-snap": snap, "--map-release": release, "--map-pointer-x": `${pointer.x}deg`, "--map-pointer-y": `${pointer.y}deg` } as React.CSSProperties;

  return (
    <section ref={scrollRef} className="invoice-map-scroll" style={mapStyle} aria-label="发票地图交互展示">
      <div className="invoice-map-stage" onPointerMove={(event) => {
        const rect = event.currentTarget.getBoundingClientRect();
        setPointer({ x: ((event.clientY - rect.top) / rect.height - 0.5) * -5, y: ((event.clientX - rect.left) / rect.width - 0.5) * 8 });
      }} onPointerLeave={() => setPointer({ x: 0, y: 0 })}>
        <div className="hero-grid-lines" aria-hidden="true" />
        <div className="map-copy">
          <div className="eyebrow"><span className="live-dot" /> AI INVOICE AUDIT / 08</div>
          <h1>让每一张发票，<em>自己说明问题。</em></h1>
          <span className="map-caption-tag">LIVE EVIDENCE / 03</span>
          <p className="hero-lede">滚动穿过一张发票的证据地图。字段从自由漂移吸附到规则网格，再释放成可追溯的审核结论。</p>
          <div className="map-actions"><a href="#upload" className="hero-primary">开始审核 <span>↗</span></a><button type="button" className="mode-toggle" onClick={() => setManualGrid((value) => !value)}><span className={manualGrid || phase === "grid" ? "toggle-pill on" : "toggle-pill"} />{manualGrid ? "释放网格" : phase === "free" ? "自由视差" : "网格吸附"}</button></div>
          <div className="map-progress"><span>SCROLL / MAP</span><i><b /></i><span>{Math.round(progress * 100).toString().padStart(2, "0")}%</span></div>
        </div>

        <div className={`invoice-map-canvas phase-${phase}`}>
          <svg className="map-connections" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path d="M14 27 L36 43 L64 43 L86 27 M12 51 L37 50 L63 50 L88 52 M22 77 L39 63 L61 63 L78 77" /><path className="map-connection-dash" d="M50 8 L50 92 M8 50 L92 50" /></svg>
          <div className="map-core-glow" />
          <div className="map-invoice-core"><InvoicePaper /></div>
          {NODES.map((node) => {
            const x = node.freeX + (node.gridX - node.freeX) * snap;
            const y = node.freeY + (node.gridY - node.freeY) * snap;
            const rotate = node.freeRotate * (1 - snap);
            const scale = 0.86 + snap * 0.14 - release * 0.1;
            return <button key={node.id} type="button" className={`map-node node-${node.tone} ${selected === node.id ? "selected" : ""}`} style={{ left: `${50 + x}%`, top: `${50 + y}%`, transform: `translate(-50%, -50%) rotate(${rotate}deg) scale(${scale})` }} onClick={() => setSelected(node.id)}><span className="node-pip" /><span>{node.label}</span></button>;
          })}
          <div className="map-crosshair" aria-hidden="true"><span /><span /></div>
          <div className="map-stage-label map-label-top">{phase === "free" ? "FREE PARALLAX" : phase === "grid" ? "GRID LOCKED" : phase === "release" ? "EVIDENCE RELEASE" : "SNAPPING FIELDS"}<b>●</b></div>
          <div className="map-stage-label map-label-bottom">SELECTED FIELD <b>{selected.toUpperCase()}</b></div>
        </div>
        <div className="map-scroll-cue"><span>SCROLL TO EXPLORE</span><b>↓</b></div>
      </div>
    </section>
  );
}
