"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { UploadDropzone } from "@/components/UploadDropzone";
import { SourceNotice } from "@/components/SourceNotice";
import { compressInvoice } from "@/lib/compress";
import { API_BASE, api } from "@/lib/api";
import { InvoiceMapHero } from "@/components/InvoiceMapHero";

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

  return (
    <div className="audit-shell">
      <InvoiceMapHero />

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
