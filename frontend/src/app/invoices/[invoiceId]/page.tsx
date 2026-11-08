"use client";

import { SourceNotice } from "@/components/SourceNotice";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { TracePanel } from "@/components/TracePanel";
import { ReviewPanel } from "@/components/ReviewPanel";
import { VerdictBadge } from "@/components/VerdictBadge";
import { api, assetUrl } from "@/lib/api";
import { pct, yuan } from "@/lib/format";
import type { InvoiceDetail } from "@/lib/types";

export default function InvoicePage() {
  const params = useParams();
  const invoiceId = String(params.invoiceId ?? "");

  const [data, setData] = useState<InvoiceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .getInvoice(invoiceId)
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "加载失败"));
    return () => {
      alive = false;
    };
  }, [invoiceId]);

  if (error) {
    return (
      <div className="mx-auto max-w-2xl">
        <div className="card p-6">
          <h2 className="text-[15px] font-semibold text-rose-700">打不开这张发票</h2>
          <p className="mt-2 text-[12.5px] text-ink-500">{error}</p>
          <Link href="/" className="mt-4 inline-block text-[12.5px] text-brand-500">
            ← 回到上传页
          </Link>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="mx-auto max-w-5xl space-y-4">
        <div className="skeleton h-6 w-40" />
        <div className="skeleton h-28 w-full rounded-xl" />
        <div className="skeleton h-64 w-full rounded-xl" />
      </div>
    );
  }

  const isDemo = data.provider === "mock-vlm" || data.provider === "fixture";
  const f = data.fields;
  const amount = (key: "amount_incl_tax" | "amount_excl_tax" | "tax_amount") =>
    data.missing_fields.includes(key) ? "未识别" : yuan(f[key]);

  return (
    <div className="mx-auto max-w-6xl">
      <Link
        href={`/batches/${data.batch_id}`}
        className="mb-4 inline-flex items-center gap-1 text-[12px] text-ink-500 hover:text-brand-700"
      >
        ← 返回审核结果
      </Link>

      <div className="grid gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
        {/* 左栏：原图 + 修改指引 */}
        <aside className="space-y-4 self-start lg:sticky lg:top-6">
          <div className="card overflow-hidden p-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={assetUrl(data.image_url)}
              alt={`发票 ${f.invoice_number}`}
              className="w-full rounded-lg border border-slate-100 bg-white"
            />
            <p className="px-1 pb-1 pt-2 text-center text-[10.5px] text-ink-300">
              {data.provider === "mock-vlm" ? "上传原图 · 右侧模拟字段与本图无关" : "原图 / 演示图，请核对数据来源"}
            </p>
          </div>

          {data.suggestions.length > 0 && (
            <div className="card p-4">
              <h3 className="mb-2 text-[12.5px] font-semibold text-ink-900">
                建议这样处理
              </h3>
              <ol className="space-y-2">
                {data.suggestions.map((s, i) => (
                  <li key={s} className="flex gap-2 text-[12px] leading-relaxed text-ink-700">
                    <span className="num mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-brand-50 text-[10px] font-medium text-brand-700">
                      {i + 1}
                    </span>
                    {s}
                  </li>
                ))}
              </ol>
            </div>
          )}

          <div className="card p-4">
            <h3 className="mb-2 text-[12.5px] font-semibold text-ink-900">
              {isDemo ? "演示置信度（非识别准确率）" : "识别把握"}
            </h3>
            <div className="num flex items-baseline gap-1">
              <span className="text-[20px] font-semibold text-ink-900">
                {pct(data.field_confidence.overall)}
              </span>
              {data.manual_review && (
                <span className="text-[11px] text-indigo-600">低于阈值，已转人工</span>
              )}
            </div>
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className={[
                  "h-full rounded-full",
                  data.field_confidence.overall >= 0.8
                    ? "bg-emerald-500"
                    : "bg-indigo-500",
                ].join(" ")}
                style={{ width: `${data.field_confidence.overall * 100}%` }}
              />
            </div>
          </div>
        </aside>

        {/* 右栏：结论、字段、规则、依据、轨迹 */}
        <div className="min-w-0 space-y-5">
          <SourceNotice provider={data.provider} />
          <header className="card p-5">
            <div className="flex flex-wrap items-center gap-2">
              <VerdictBadge verdict={data.verdict} />
              <span className="num text-[11px] text-ink-300">{data.invoice_id}</span>
            </div>
            <h1 className="mt-2.5 text-[17px] font-semibold leading-snug text-ink-900">
              {data.headline}
            </h1>
            <div className="mt-3 flex flex-wrap items-baseline gap-x-6 gap-y-2">
              <div>
                <div className="text-[10.5px] text-ink-500">价税合计</div>
                <div className="num text-[19px] font-semibold text-ink-900">
                  {amount("amount_incl_tax")}
                </div>
              </div>
              <div>
                <div className="text-[10.5px] text-ink-500">销售方</div>
                <div className="text-[12.5px] text-ink-700">{f.seller_name}</div>
              </div>
              <div>
                <div className="text-[10.5px] text-ink-500">开票日期</div>
                <div className="num text-[12.5px] text-ink-700">{f.invoice_date}</div>
              </div>
            </div>
          </header>

          <Section title={isDemo ? "演示字段（非票面识别）" : "识别字段"} hint={isDemo ? "以下为模拟或固定样例，不代表上传原票" : "括号内是模型对这一项的把握"}>
            <div className="grid gap-x-8 sm:grid-cols-2">
              <Field label="发票代码" value={f.invoice_code} mono />
              <Field label="发票号码" value={f.invoice_number} mono conf={conf(data, "invoice_number")} />
              <Field label="开票日期" value={f.invoice_date} conf={conf(data, "invoice_date")} />
              <Field label="费用类目" value={f.category} />
              <Field label="购买方" value={f.buyer_name} wide conf={conf(data, "buyer_name")} />
              <Field label="购买方税号" value={f.buyer_tax_id} mono conf={conf(data, "buyer_tax_id")} />
              <Field label="销售方" value={f.seller_name} wide conf={conf(data, "seller_name")} />
              <Field label="销售方税号" value={f.seller_tax_id} mono />
              <Field label="不含税金额" value={amount("amount_excl_tax")} />
              <Field label="税额" value={amount("tax_amount")} />
              <Field label="税率" value={data.missing_fields.includes("tax_rate") ? "未识别" : `${(f.tax_rate * 100).toFixed(0)}%`} />
            </div>

            {f.items.length > 0 && (
              <div className="mt-3 border-t border-slate-100 pt-3">
                <div className="mb-1.5 text-[11px] text-ink-500">消费明细</div>
                <ul className="space-y-1">
                  {f.items.map((it) => (
                    <li
                      key={it.name}
                      className="flex items-baseline justify-between text-[12px] text-ink-700"
                    >
                      <span>{it.name}</span>
                      <span className="num">{yuan(it.amount)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </Section>

          <ReviewPanel key={data.invoice_id} detail={data} onUpdated={setData} />

          <Section
            title="命中规则"
            hint={data.hit_rules.length === 0 ? "所有规则均未命中" : `共 ${data.hit_rules.length} 条`}
          >
            {data.hit_rules.length === 0 ? (
              <p className="text-[12.5px] text-ink-500">
                这张发票通过了全部检查，没有命中任何规则。
              </p>
            ) : (
              <ul className="space-y-2.5">
                {data.hit_rules.map((r) => (
                  <li key={r.code} className="rounded-lg bg-slate-50 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <code className="rounded bg-white px-1.5 py-0.5 font-mono text-[10.5px] text-ink-700 ring-1 ring-slate-200">
                        {r.code}
                      </code>
                      <span className="text-[12.5px] font-medium text-ink-900">{r.name}</span>
                      <VerdictBadge
                        verdict={r.level === "info" ? "manual" : r.level}
                        size="sm"
                      />
                    </div>
                    <p className="mt-1.5 text-[12px] leading-relaxed text-ink-700">
                      {r.detail}
                    </p>
                    {r.evidence && Object.keys(r.evidence).length > 0 && (
                      <dl className="mt-2 grid gap-x-4 gap-y-1 sm:grid-cols-2">
                        {Object.entries(r.evidence).map(([k, v]) => (
                          <div key={k} className="flex items-baseline gap-1.5 text-[11px]">
                            <dt className="shrink-0 text-ink-300">{k}</dt>
                            <dd className="num truncate text-ink-700">{String(v)}</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section
            title="依据条款"
            hint={data.citations.length === 0 ? "本条结论无需引用制度" : "可展开原文核对"}
          >
            {data.citations.length === 0 ? (
              <p className="text-[12.5px] text-ink-500">
                {isDemo ? "演示结论仅用于展示审核流程，不代表原票事实。" : "该结论来自字段校验（查重 / 抬头），请结合原图与台账核实。"}
              </p>
            ) : (
              <ul className="space-y-2.5">
                {data.citations.map((c) => (
                  <li key={`${c.doc_id}-${c.article_no}`} className="rounded-lg border border-slate-200 p-3">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                      <span className="text-[12px] font-medium text-brand-700">
                        《{c.doc_title}》{c.article_no}
                      </span>
                      <span className="num text-[10.5px] text-ink-300">
                        相关度 {c.score.toFixed(2)}
                      </span>
                    </div>
                    <p className="mt-1.5 text-[12px] leading-relaxed text-ink-700">
                      {c.text}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="审核轨迹" hint="AI 每一步在做什么，以及为什么这么做">
            <TracePanel steps={data.trace} />
          </Section>
        </div>
      </div>
    </div>
  );
}

function conf(data: InvoiceDetail, key: string): number | undefined {
  return data.field_confidence.per_field?.[key];
}

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="card p-5">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[13.5px] font-semibold text-ink-900">{title}</h2>
        {hint && <span className="text-[11px] text-ink-300">{hint}</span>}
      </div>
      {children}
    </section>
  );
}

function Field({
  label,
  value,
  mono,
  wide,
  conf,
}: {
  label: string;
  value: string;
  mono?: boolean;
  wide?: boolean;
  conf?: number;
}) {
  const low = conf !== undefined && conf < 0.8;
  return (
    <div className={`field-row ${wide ? "sm:col-span-2" : ""}`}>
      <dt className="shrink-0 text-[11.5px] text-ink-500">{label}</dt>
      <dd
        className={[
          "text-right text-[12.5px] text-ink-900",
          mono ? "num font-mono" : "",
        ].join(" ")}
      >
        {value}
        {low && (
          <span className="ml-1.5 rounded bg-amber-50 px-1 py-0.5 text-[10px] text-amber-700">
            低把握
          </span>
        )}
      </dd>
    </div>
  );
}
