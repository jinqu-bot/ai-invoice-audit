"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { InvoiceCard } from "@/components/InvoiceCard";
import { StatCard } from "@/components/Stats";
import { VerdictBadge } from "@/components/VerdictBadge";
import { api, assetUrl } from "@/lib/api";
import { seconds, yuan } from "@/lib/format";
import { subscribeBatch } from "@/lib/sse";
import type { BatchResults, StreamBatchDone } from "@/lib/types";

/** 还没审完的那张：只知道它叫什么、图片在哪、当前走到哪一步 */
interface Pending {
  invoice_id: string;
  image_url?: string;
  step: string;
}

export default function BatchPage() {
  const params = useParams();
  const batchId = String(params.batchId ?? "");

  const [results, setResults] = useState<BatchResults | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<Record<string, Pending>>({});
  const [replay, setReplay] = useState(false);
  const [batchDone, setBatchDone] = useState<StreamBatchDone | null>(null);
  const [runId, setRunId] = useState(0);

  /** 拉一次结果。D6 之后它是"真进度"的唯一数据源：
   *  SSE 只负责告诉你"有变化了"，具体数字还是从接口拿，避免两套状态对不上。 */
  const refresh = useCallback(async () => {
    const next = await api.getResults(batchId);
    setResults(next);
    setPending((prev) => {
      if (!Object.keys(prev).length) return prev;
      const kept = { ...prev };
      next.items.forEach((item) => delete kept[item.invoice_id]);
      return kept;
    });
    return next;
  }, [batchId]);

  // 首屏 + 每次重播：先拿一次数据，再挂流，同时开一个轮询兜底。
  // 现场网络不可靠，SSE 随时可能被代理掐掉——那时页面必须还能自己走完。
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setInterval> | null = null;
    setPending({});
    setReplay(false);
    setBatchDone(null);
    setError(null);

    const tick = async () => {
      try {
        const body = await refresh();
        if (!alive) return;
        if (body.batch.status !== "processing" && timer) {
          clearInterval(timer);
          timer = null;
        }
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : "加载失败");
      }
    };

    void tick();

    const stop = subscribeBatch(batchId, {
      onHello: (h) => alive && setReplay(h.replay),
      onStart: (d) =>
        alive &&
        setPending((m) => ({
          ...m,
          [d.invoice_id]: { invoice_id: d.invoice_id, image_url: d.image_url, step: "开始审核" },
        })),
      onTrace: (d) =>
        alive &&
        setPending((m) =>
          m[d.invoice_id] ? { ...m, [d.invoice_id]: { ...m[d.invoice_id], step: d.title } } : m,
        ),
      onFileFailed: () => {
        void tick();
      },
      onInvoiceDone: () => {
        void tick();
      },
      onBatchDone: (d) => {
        if (!alive) return;
        setBatchDone(d);
        void tick();
      },
      // 流断了不弹错：轮询还在跑，结果照样会出来
      onError: () => undefined,
    });

    timer = setInterval(tick, 1000);

    return () => {
      alive = false;
      stop();
      if (timer) clearInterval(timer);
    };
  }, [batchId, refresh, runId]);

  const batch = results?.batch ?? null;
  const items = results?.items ?? [];
  const failures = results?.failures ?? [];

  // 总数以批次的 invoice_count 为准：processing 期间它等于"待审张数"，
  // 跑完之后等于实际张数。**不要用 items.length**，那会随着进度变化。
  const total = Math.max(batch?.invoice_count ?? 0, items.length);
  const finished = batch !== null && batch.status !== "processing";
  const pendingList = finished
    ? [] // 整批已结束还挂着"审核中"的卡片，只会让人以为卡住了
    : Object.values(pending).filter(
        (p) => !items.some((item) => item.invoice_id === p.invoice_id),
      );
  const queued = Math.max(total - items.length - pendingList.length, 0);

  const elapsed = useMemo(
    () => batchDone?.elapsed_ms ?? batch?.elapsed_ms ?? 0,
    [batchDone, batch],
  );

  if (error && !batch) {
    return (
      <div className="mx-auto max-w-2xl">
        <div className="card p-6">
          <h2 className="text-[15px] font-semibold text-rose-700">打不开这批数据</h2>
          <p className="mt-2 text-[12.5px] text-ink-500">{error}</p>
          <Link
            href="/"
            className="mt-4 inline-block text-[12.5px] text-brand-500 hover:text-brand-700"
          >
            ← 回到上传页
          </Link>
        </div>
      </div>
    );
  }

  if (!batch) {
    return (
      <div className="mx-auto max-w-5xl">
        <div className="mb-6 h-7 w-48 skeleton" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="card h-[190px] p-4">
              <div className="skeleton h-4 w-24" />
              <div className="mt-3 skeleton h-3 w-full" />
              <div className="mt-2 skeleton h-3 w-2/3" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-[20px] font-semibold tracking-tight text-ink-900">
              审核结果
            </h1>
            {finished ? (
              <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-600/20">
                已完成
              </span>
            ) : (
              <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-medium text-brand-700 ring-1 ring-inset ring-brand-500/20">
                审核中 {items.length}/{total}
              </span>
            )}
            {replay && (
              <span
                className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-ink-500"
                title="这批已经审完了，下面播放的是存下来的过程，不是正在发生"
              >
                回放
              </span>
            )}
          </div>
          <p className="num mt-1 text-[11.5px] text-ink-500">
            {batch.batch_id} · {batch.created_at} · 共 {batch.invoice_count} 张 ·{" "}
            {yuan(batch.total_amount)}
          </p>
        </div>

        <button
          type="button"
          onClick={() => setRunId((r) => r + 1)}
          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-[12px] text-ink-700 transition-colors hover:border-brand-500 hover:text-brand-700"
        >
          重新播放审核过程
        </button>
      </header>

      <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label="审核总数" value={String(batch.invoice_count)} hint="张" />
        <StatCard
          label="通过"
          value={String(batch.pass_count)}
          accent="emerald"
          hint="无需处理"
        />
        <StatCard
          label="存疑"
          value={String(batch.suspect_count)}
          accent="amber"
          hint="补充材料"
        />
        <StatCard
          label="驳回"
          value={String(batch.reject_count)}
          accent="rose"
          hint="不可报销"
        />
        <StatCard label="整批耗时" value={seconds(elapsed)} hint="端到端" />
      </div>

      {!finished && (
        <div className="mb-6 h-1 w-full overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-brand-500 transition-all duration-300"
            style={{ width: `${total ? (items.length / total) * 100 : 0}%` }}
          />
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((item) => (
          <InvoiceCard key={item.invoice_id} item={item} />
        ))}

        {pendingList.map((p) => (
          <PendingCard key={p.invoice_id} imageUrl={p.image_url} step={p.step} />
        ))}

        {Array.from({ length: queued }).map((_, i) => (
          <PendingCard key={`queued-${i}`} step="排队中" />
        ))}
      </div>

      {finished && total === 0 && (
        <div className="card mt-4 p-6 text-center text-[13px] text-ink-500">
          这一批没有可审核的发票。
        </div>
      )}

      {failures.length > 0 && (
        <div className="mt-5 rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-3">
          <div className="text-[12.5px] font-medium text-amber-900">
            {failures.length} 个文件没能处理，其余照常审完
          </div>
          <ul className="mt-2 space-y-1">
            {failures.map((f, index) => (
              <li
                key={`${f.filename}-${index}`}
                className="text-[12px] leading-relaxed text-amber-800"
              >
                <span className="num">{f.filename}</span>
                <span className="mx-1.5 text-amber-400">·</span>
                {f.message}
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-[11.5px] text-amber-700">
            一张失败不影响这一批的其它张。
          </p>
        </div>
      )}

      {finished && total > 0 && (
        <p className="mt-6 text-center text-[12px] text-ink-300">
          审核完成。点任意一张查看字段、依据与完整轨迹。
        </p>
      )}
    </div>
  );
}

function PendingCard({ imageUrl, step }: { imageUrl?: string; step?: string }) {
  return (
    <div className="card overflow-hidden opacity-90">
      <div className="flex gap-3 border-b border-slate-100 p-3">
        {imageUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={assetUrl(imageUrl)}
            alt=""
            className="h-[74px] w-[54px] shrink-0 rounded border border-slate-200 bg-slate-50 object-cover"
          />
        ) : (
          <div className="h-[74px] w-[54px] shrink-0 rounded border border-slate-200 bg-slate-50" />
        )}
        <div className="min-w-0 flex-1">
          <VerdictBadge verdict="manual" size="sm" />
          <div className="mt-1.5 skeleton h-3.5 w-3/4" />
          <div className="mt-1.5 skeleton h-2.5 w-1/2" />
        </div>
      </div>
      <div className="p-3">
        <div className="flex items-center gap-2 text-[12px] text-ink-500">
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" />
          {step ?? "排队中"}
          <span className="text-ink-300">…</span>
        </div>
      </div>
    </div>
  );
}