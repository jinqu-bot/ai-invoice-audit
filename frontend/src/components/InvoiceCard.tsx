import Link from "next/link";
import { assetUrl } from "@/lib/api";
import { pct, yuan } from "@/lib/format";
import type { InvoiceCard as InvoiceCardType } from "@/lib/types";
import { VerdictBadge } from "./VerdictBadge";

export function InvoiceCard({ item }: { item: InvoiceCardType }) {
  return (
    <Link
      href={`/invoices/${item.invoice_id}`}
      className="card card-hover group flex flex-col overflow-hidden"
    >
      <div className="flex gap-3 border-b border-slate-100 p-3">
        {/* 用原生 img：图片来自本地后端，不走 next/image 的远端优化 */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={assetUrl(item.image_url)}
          alt={`发票 ${item.invoice_number}`}
          className="h-[74px] w-[54px] shrink-0 rounded border border-slate-200 bg-slate-50 object-cover"
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <VerdictBadge verdict={item.verdict} size="sm" />
            <span className="num shrink-0 text-[13px] font-semibold text-ink-900">
              {yuan(item.amount_incl_tax)}
            </span>
          </div>
          <div className="mt-1.5 truncate text-[13px] font-medium text-ink-900">
            {item.seller_name}
          </div>
          <div className="num mt-0.5 text-[11px] text-ink-500">
            No. {item.invoice_number} · {item.invoice_date}
          </div>
        </div>
      </div>

      <div className="flex flex-1 flex-col justify-between gap-3 p-3">
        <p className="line-clamp-2 text-[12.5px] leading-relaxed text-ink-700">
          {item.headline}
        </p>

        <div className="flex items-center justify-between text-[11px] text-ink-500">
          <div className="flex items-center gap-1.5">
            {item.hit_rule_codes.length > 0 ? (
              item.hit_rule_codes.map((code) => (
                <span
                  key={code}
                  className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10.5px] text-ink-700"
                >
                  {code}
                </span>
              ))
            ) : (
              <span className="text-ink-300">无规则命中</span>
            )}
          </div>
          <span className="num">
            把握 {pct(item.confidence)} · {(item.latency_ms / 1000).toFixed(1)}s
          </span>
        </div>
      </div>
    </Link>
  );
}
