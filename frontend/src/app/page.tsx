"use client";

import { useEffect } from "react";
import { TransitionLink, usePageNavigation } from "@/components/PageTransitions";
import { InvoiceMapHero } from "@/components/InvoiceMapHero";
import { DEMO_BATCH_ID } from "@/lib/api";

export default function IntroPage() {
  const navigate = usePageNavigation();

  useEffect(() => {
    if (window.location.hash === "#upload") navigate("/upload");
  }, [navigate]);

  return (
    <div className="audit-shell">
      <InvoiceMapHero />

      <section className="audit-manifest">
        <div className="section-kicker"><span>03</span><i />WHAT GETS CHECKED</div>
        <div className="manifest-grid">
          {[
            { n: "01", t: "字段识别", d: "号码、日期、购销双方、税号与金额三件套" },
            { n: "02", t: "规则追踪", d: "R0—R8 每条结论都能回到制度条款" },
            { n: "03", t: "人工复核", d: "改判有原因、有时间、有操作人" },
          ].map(item => (
            <div className="manifest-card" key={item.n}>
              <span>{item.n}</span><h3>{item.t}</h3><p>{item.d}</p><b>→</b>
            </div>
          ))}
        </div>
      </section>

      <section className="intro-cta" aria-labelledby="intro-cta-title">
        <h2 id="intro-cta-title">让每一张发票，都有据可查。</h2>
        <p>从字段识别到规则依据，再到人工复核。了解了系统能做什么，现在就可以开始。</p>
        <TransitionLink href="/upload" className="hero-primary intro-upload-link">开始上传发票 →</TransitionLink>
        <nav className="intro-cta-links" aria-label="了解更多">
          <TransitionLink href={"/batches/" + DEMO_BATCH_ID}>看演示批次</TransitionLink>
          <TransitionLink href="/ask">制度问答</TransitionLink>
          <TransitionLink href="/dashboard">审核看板</TransitionLink>
        </nav>
      </section>
    </div>
  );
}
