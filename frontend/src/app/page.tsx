"use client";

import { CSSProperties, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { UploadDropzone } from "@/components/UploadDropzone";
import { SourceNotice } from "@/components/SourceNotice";
import { compressInvoice } from "@/lib/compress";
import { API_BASE, api } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const [provider, setProvider] = useState<string>("unknown");
  const [compress, setCompress] = useState(false);
  const [progress, setProgress] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking");
  const [pointer, setPointer] = useState({ x: 0, y: 0 });
  const [mode, setMode] = useState<"free" | "grid">("free");

  useEffect(() => {
    api
      .health()
      .then((data) => { setHealth("ok"); setProvider(data.recognition_provider ?? "unknown"); })
      .catch(() => setHealth("down"));
  }, []);

  async function go(action: () => Promise<{ batch_id: string }>) {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError(null);
    try {
      const res = await action();
      router.push(`/batches/${res.batch_id}`);
    } catch (e) {
      setProgress("");
      setError(e instanceof Error ? e.message : "上传失败，请检查后端是否启动");
      submitting.current = false;
      setBusy(false);
    }
  }

  const invoiceStyle = { "--invoice-x": `${pointer.x}deg`, "--invoice-y": `${pointer.y}deg` } as CSSProperties;
  return (
    <div className="audit-shell">
      <section className="audit-hero" onPointerMove={(event) => {
        const rect = event.currentTarget.getBoundingClientRect();
        setPointer({ x: ((event.clientY - rect.top) / rect.height - 0.5) * -10, y: ((event.clientX - rect.left) / rect.width - 0.5) * 14 });
      }} onPointerLeave={() => setPointer({ x: 0, y: 0 })}>
        <div className="hero-grid-lines" aria-hidden="true" />
        <div className="hero-copy">
          <div className="eyebrow"><span className="live-dot" /> AI INVOICE AUDIT / 08</div>
          <h1>让每一张发票，<em>自己说明问题。</em></h1>
          <p className="hero-lede">视觉模型读图，规则引擎做决定。把报销审核从一张平面表格，变成可追溯的证据空间。</p>
          <div className="hero-actions">
            <a href="#upload" className="hero-primary">开始审核 <span>↗</span></a>
            <button type="button" className="mode-toggle" onClick={() => setMode(mode === "free" ? "grid" : "free")}><span className={mode === "grid" ? "toggle-pill on" : "toggle-pill"} />{mode === "grid" ? "网格吸附" : "自由视差"}</button>
          </div>
          <div className="hero-meta"><span>01 / 03</span><i /><span>REAL-TIME TRACE</span><i /><span>R0—R8</span></div>
        </div>
        <div className={`invoice-stage ${mode === "grid" ? "grid-mode" : ""}`}>
          <div className="stage-orbit orbit-one" /><div className="stage-orbit orbit-two" />
          <div className="invoice-shadow" />
          <div className="invoice-3d" style={invoiceStyle}>
            <div className="invoice-topline"><span>电子发票（普通发票）</span><span>NO. 26232000000859984741</span></div>
            <div className="invoice-heading"><div className="invoice-qr"><span /><span /><span /><span /></div><div><small>AI INVOICE / AUDIT COPY</small><strong>发票审核凭证</strong></div><div className="invoice-date">开票日期<br /><b>2026-08-15</b></div></div>
            <div className="invoice-parties"><div><small>购买方信息</small><b>戴海青</b><span>个人 · 统一社会信用代码 / 纳税人识别号：—</span></div><div><small>销售方信息</small><b>哈尔滨鸿源科技有限公司</b><span>91230103MA191WQU0L</span></div></div>
            <div className="invoice-table"><span>项目名称</span><span>数量</span><span>金额</span><span>税率</span><b>电子计算机*笔记本电脑</b><b>1</b><b>¥4,201.77</b><b>13%</b></div>
            <div className="invoice-total"><span>价税合计（小写）</span><strong>¥4,748.00</strong></div>
            <div className="invoice-footer"><span>识别来源 · openai-compat</span><span>规则命中 · R3 / R4</span></div>
            <div className="audit-stamp">REVIEW</div>
          </div>
          <div className="stage-label label-top">MODEL / DEEPSEEK VISION <span>●</span></div>
          <div className="stage-label label-bottom">FIELD ACCURACY <b>98.5%</b></div>
        </div>
        <div className="scroll-cue"><span>SCROLL TO UPLOAD</span><b>↓</b></div>
      </section>

      <section id="upload" className="upload-zone">
        <div className="section-kicker"><span>02</span><i />UPLOAD EVIDENCE</div>
        <div className="upload-heading"><div><h2>把证据放进来</h2><p>先选文件，确认缩略图与数量，再开始审核。每一步都留下轨迹。</p></div><div className="connection-chip"><span className={health === "ok" ? "live-dot" : "live-dot muted"} />{health === "ok" ? "API CONNECTED" : health === "checking" ? "CHECKING API" : "API OFFLINE"}</div></div>
        <SourceNotice provider={provider} />
        <div className="upload-panel">
          <UploadDropzone disabled={busy} files={files} onFiles={(next) => { setFiles(next); setError(null); }} />
          <div className="upload-controls"><label><input type="checkbox" disabled={busy} checked={compress} onChange={e => setCompress(e.target.checked)} />上传前压缩大图 <span>最长边 2560px，原文件不改</span></label><button type="button" disabled={busy || files.length === 0} onClick={() => go(async () => { const prepared: File[] = []; for (const [index, file] of files.entries()) { setProgress(`准备文件 ${index + 1}/${files.length}`); prepared.push(compress ? await compressInvoice(file) : file); } const bytes = prepared.reduce((sum, f) => sum + f.size, 0); setProgress(`正在上传 ${prepared.length} 张，合计 ${(bytes / 1024 / 1024).toFixed(2)} MB`); return api.uploadFiles(prepared); })} className="audit-submit">{busy ? "正在处理…" : error ? "重试审核" : provider === "mock-vlm" ? "开始模拟审核" : "开始审核"}<span>↗</span></button></div>
          {progress && <p role="status" className="upload-progress">{progress}</p>}
          {error && <div role="alert" className="upload-error">{error}<p>已保留所选文件，可修改后重试。</p></div>}
          <div className="upload-footer"><button type="button" disabled={busy} onClick={() => go(() => api.uploadDemo())} className="demo-link">加载演示数据（5 张） →</button><span>后端 {API_BASE} · {health === "ok" ? "已连接" : health === "checking" ? "检测中…" : "未连接"}</span></div>
        </div>
        {health === "down" && <div className="offline-note">连不上后端：请在项目根目录启动 <code>uvicorn app.main:app --reload --port 8000 --app-dir backend</code></div>}
      </section>

      <section className="audit-manifest"><div className="section-kicker"><span>03</span><i />WHAT GETS CHECKED</div><div className="manifest-grid">{[{ n: "01", t: "字段识别", d: "号码、日期、购销双方、税号与金额三件套" }, { n: "02", t: "规则追踪", d: "R0—R8 每条结论都能回到制度条款" }, { n: "03", t: "人工复核", d: "改判有原因、有时间、有操作人" }].map(x => <div className="manifest-card" key={x.n}><span>{x.n}</span><h3>{x.t}</h3><p>{x.d}</p><b>→</b></div>)}</div></section>
    </div>
  );
}
