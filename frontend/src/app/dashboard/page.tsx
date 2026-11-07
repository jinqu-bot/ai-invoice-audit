"use client";

import { SourceNotice } from "@/components/SourceNotice";
import { useEffect, useState } from "react";
import { BarList, StatCard } from "@/components/Stats";
import { api } from "@/lib/api";
import { pct, yuan } from "@/lib/format";
import type { Dashboard } from "@/lib/types";

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .getDashboard()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "加载失败"));
    return () => {
      alive = false;
    };
  }, []);

  if (error) {
    return (
      <div className="mx-auto max-w-2xl">
        <div className="card p-6">
          <h2 className="text-[15px] font-semibold text-rose-700">看板数据加载失败</h2>
          <p className="mt-2 text-[12.5px] text-ink-500">{error}</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="mx-auto max-w-6xl space-y-4">
        <div className="skeleton h-6 w-40" />
        <div className="grid gap-4 sm:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-24 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl">
      <header className="mb-5">
        <h1 className="text-[20px] font-semibold tracking-tight text-ink-900">审核看板</h1>
        <SourceNotice provider="fixture" />
        <p className="mt-1 text-[11.5px] text-ink-500">
          {data.month} · 数据为演示样例
        </p>
      </header>

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="本月审核" value={String(data.total_count)} hint="张发票" />
        <StatCard label="涉及金额" value={yuan(data.total_amount)} hint="价税合计" />
        <StatCard
          label="通过率"
          value={pct(data.pass_rate)}
          accent="emerald"
          hint="一次过审"
        />
        <StatCard
          label="驳回 TOP1"
          value={data.reject_reasons[0]?.name ?? "—"}
          accent="rose"
          hint={`${data.reject_reasons[0]?.count ?? 0} 张`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="驳回原因 TOP5" subtitle="按命中张数排序">
          <BarList
            items={data.reject_reasons.map((r) => ({ label: r.name, value: r.count }))}
            barClass="bg-rose-500"
            formatValue={(v) => `${v} 张`}
          />
        </Panel>

        <Panel title="部门费用分布" subtitle="金额口径">
          <BarList
            items={data.by_department.map((d) => ({
              label: d.dept,
              value: d.amount,
              hint: `${d.count} 张`,
            }))}
            formatValue={(v) => yuan(v)}
          />
        </Panel>

        <Panel title="费用类目" subtitle="按发票张数">
          <BarList
            items={data.by_category.map((c) => ({ label: c.name, value: c.count }))}
            formatValue={(v) => `${v} 张`}
          />
        </Panel>

        <Panel title="供应商 TOP" subtitle="金额口径，异常集中要留意">
          <BarList
            items={data.by_supplier.map((s) => ({
              label: s.dept,
              value: s.amount,
              hint: `${s.count} 张`,
            }))}
            formatValue={(v) => yuan(v)}
            barClass="bg-indigo-400"
          />
        </Panel>

        <Panel title="金额区间分布" subtitle="按发票张数">
          <BarList
            items={data.amount_buckets.map((b) => ({ label: b.name, value: b.count }))}
            formatValue={(v) => `${v} 张`}
            barClass="bg-slate-400"
          />
        </Panel>

        <Panel title="每日审核量" subtitle="近几日">
          <BarList
            items={data.daily_trend.map((t) => ({ label: t.name, value: t.count }))}
            formatValue={(v) => `${v} 张`}
            barClass="bg-emerald-400"
          />
        </Panel>
      </div>
    </div>
  );
}

function Panel({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="card p-5">
      <div className="mb-4">
        <h2 className="text-[13.5px] font-semibold text-ink-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-[11px] text-ink-300">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}
