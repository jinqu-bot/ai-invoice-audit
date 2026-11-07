"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { UploadDropzone } from "@/components/UploadDropzone";
import { API_BASE, api } from "@/lib/api";

export default function UploadPage() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking");

  useEffect(() => {
    api
      .health()
      .then(() => setHealth("ok"))
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
      setError(e instanceof Error ? e.message : "上传失败，请检查后端是否启动");
      submitting.current = false;
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-7">
        <h1 className="text-[22px] font-semibold tracking-tight text-ink-900">
          上传发票，查看审核结果
        </h1>
        <p className="mt-1.5 text-[13px] leading-relaxed text-ink-500">
          系统会自动识别要素、查重、核对制度标准，并给出结论与依据。
          <br className="hidden sm:block" />
          每一张被驳回的发票，都能指到具体是哪个制度第几条。
        </p>
      </header>

      <UploadDropzone
        disabled={busy}
        files={files}
        onFiles={(next) => { setFiles(next); setError(null); }}
      />

      <button type="button" disabled={busy || files.length === 0}
        onClick={() => go(() => api.uploadFiles(files))}
        className="mt-4 rounded-lg bg-brand-700 px-5 py-2.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50">
        {busy ? "正在处理，请稍候…" : error ? "重试审核" : "开始审核"}
      </button>

      {error && (
        <div role="alert" className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3.5 py-2.5 text-[12.5px] text-rose-700">
          {error}
          {files.length > 0 && <p className="mt-1">已保留所选文件，可修改后重试。连接中断时请先确认批次是否已创建，避免重复提交。</p>}
        </div>
      )}

      <div className="mt-5 flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
        <button
          type="button"
          disabled={busy}
          onClick={() => go(() => api.uploadDemo())}
          className="inline-flex items-center gap-2 rounded-lg bg-brand-700 px-4 py-2.5 text-[13px] font-medium text-white shadow-sm transition-colors hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          用演示数据体验（5 张）
        </button>

        <p className="num text-[11.5px] text-ink-300">
          后端 {API_BASE} ·{" "}
          {health === "checking"
            ? "检测中…"
            : health === "ok"
              ? "已连接"
              : "未连接"}
        </p>
      </div>

      {health === "down" && (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3 text-[12.5px] leading-relaxed text-amber-800">
          <div className="font-medium">连不上后端</div>
          <div className="mt-1 text-amber-700">
            在项目根目录执行：
            <code className="mx-1 rounded bg-amber-100 px-1.5 py-0.5 font-mono text-[11px]">
              uvicorn app.main:app --reload --port 8000 --app-dir backend
            </code>
          </div>
        </div>
      )}

      <section className="mt-9 grid gap-4 sm:grid-cols-3">
        {[
          { t: "演示批次共 5 张", d: "固定样例用于体验界面，不代表照片识别效果" },
          { t: "埋了两颗雷", d: "一张重复报销、一张超出住宿标准 480 元" },
          { t: "每张都留痕", d: "审核轨迹记录每一步查了什么、为什么查" },
        ].map((x) => (
          <div key={x.t} className="card p-4">
            <div className="text-[12.5px] font-medium text-ink-900">{x.t}</div>
            <div className="mt-1 text-[11.5px] leading-relaxed text-ink-500">
              {x.d}
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
