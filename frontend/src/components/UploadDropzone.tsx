"use client";

import { useCallback, useRef, useState } from "react";

export function UploadDropzone({
  onFiles,
  disabled,
}: {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
}) {
  const [dragging, setDragging] = useState(false);
  const [names, setNames] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const accept = useCallback(
    (list: FileList | null) => {
      if (!list || list.length === 0) return;
      const files = Array.from(list);
      setNames(files.map((f) => f.name));
      onFiles(files);
    },
    [onFiles],
  );

  return (
    <div
      onDragOver={(e) => {
        if (disabled) return;
        e.preventDefault();
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
        multiple
        accept="image/*,application/pdf"
        className="hidden"
        onChange={(e) => accept(e.target.files)}
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
        支持 JPG / PNG / PDF，可一次上传多张
      </p>

      {names.length > 0 && (
        <p className="mt-3 rounded-md bg-slate-100 px-2.5 py-1 text-[11.5px] text-ink-700">
          已选 {names.length} 个文件：{names.slice(0, 3).join("、")}
          {names.length > 3 && " …"}
        </p>
      )}
    </div>
  );
}
