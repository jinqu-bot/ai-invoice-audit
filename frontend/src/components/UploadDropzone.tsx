"use client";

import { useEffect, useRef, useState } from "react";

const MAX_FILES = 20;
const MAX_BYTES = 20 * 1024 * 1024;
const TYPES = ["image/jpeg", "image/png", "image/webp"];
const size = (bytes: number) => bytes < 1024 * 1024
  ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(2)} MB`;

export function UploadDropzone({
  files,
  onFiles,
  disabled,
}: {
  files: File[];
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function accept(list: FileList | null) {
    if (disabled || !list?.length) return;
    const incoming = Array.from(list);
    const errors = incoming.flatMap((file) => {
      if (!TYPES.includes(file.type) && (file.type || !/\.(jpe?g|png|webp)$/i.test(file.name))) {
        return [`${file.name}：仅支持 JPG / PNG / WebP`];
      }
      if (!file.size) return [`${file.name}：文件为空`];
      if (file.size > MAX_BYTES) return [`${file.name}：超过单张 20 MB`];
      return [];
    });
    if (files.length + incoming.length > MAX_FILES) errors.push("每批最多 20 张，请减少文件后重选");
    setError(errors.join("；"));
    if (!errors.length) onFiles([...files, ...incoming]);
  }

  return (
    <section aria-label="待上传发票" aria-busy={disabled}>
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-disabled={disabled}
      aria-label="选择或拖入发票"
      onKeyDown={(e) => {
        if (!disabled && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); inputRef.current?.click(); }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        if (disabled) return;
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (disabled) return;
        accept(e.dataTransfer.files);
      }}
      onClick={() => !disabled && inputRef.current?.click()}
      className={[
        "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-14 text-center transition-colors",
        disabled
          ? "cursor-not-allowed border-slate-200 bg-slate-50/60"
          : dragging
            ? "border-brand-500 bg-brand-50/60"
            : "border-slate-300 bg-white hover:border-brand-500 hover:bg-brand-50/40",
      ].join(" ")}
    >
      <input
        ref={inputRef}
        type="file"
        disabled={disabled}
        aria-label="选择发票文件"
        multiple
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => { accept(e.target.files); e.target.value = ""; }}
      />

      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-brand-50 text-brand-700">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M12 16V4m0 0L7 9m5-5 5 5" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" />
        </svg>
      </div>

      <p className="text-[14px] font-medium text-ink-900">
        把发票照片拖进来，或点击选择
      </p>
      <p className="mt-1 text-[12px] text-ink-500">
        JPG / PNG / WebP · 每批最多 20 张 · 单张不超过 20 MB
      </p>
      <p className="mt-1 text-[12px] text-ink-500">选好后可预览、删除，点击“开始审核”才会上传</p>
    </div>
      {error && <p role="alert" className="mt-3 break-words rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{error}。本次选择未加入，已有文件已保留。</p>}
      <p aria-live="polite" className="my-3 text-[12px] text-ink-500">
        已选 {files.length} / {MAX_FILES} 张 · 合计 {size(files.reduce((sum, file) => sum + file.size, 0))}
      </p>
      <ul className="grid gap-3 sm:grid-cols-2">
        {files.map((file, index) => (
          <li key={`${file.name}-${file.lastModified}-${index}`} className="flex min-w-0 items-center gap-3 rounded-lg border border-slate-200 bg-white p-3">
            <Preview file={file} />
            <div className="min-w-0 flex-1">
              <p className="break-all text-[12px] text-ink-900">{file.name}</p>
              <p className="mt-1 text-[11px] text-ink-500">{size(file.size)}</p>
            </div>
            <button type="button" disabled={disabled} aria-label={`删除 ${file.name}`}
              className="shrink-0 rounded px-2 py-1 text-[12px] text-rose-700 hover:bg-rose-50 disabled:opacity-40"
              onClick={() => { setError(""); onFiles(files.filter((_, i) => i !== index)); }}>删除</button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Preview({ file }: { file: File }) {
  const [url, setUrl] = useState("");
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const next = URL.createObjectURL(file);
    setUrl(next);
    setFailed(false);
    return () => URL.revokeObjectURL(next);
  }, [file]);
  if (!url || failed) return <span className="w-14 shrink-0 text-[11px] text-ink-500">无法预览</span>;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={url} alt={`${file.name} 预览`} onError={() => setFailed(true)} className="h-16 w-14 shrink-0 rounded bg-slate-50 object-contain" />;
}
