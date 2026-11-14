"use client";

import { useEffect, useState } from "react";
import { TransitionLink as Link } from "@/components/PageTransitions";
import { api } from "@/lib/api";
import type { BatchList } from "@/lib/types";
import { sourceLabel } from "@/components/SourceNotice";

export default function HistoryPage() {
  const [data, setData] = useState<BatchList | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setData(null); setError("");
    api.listBatches(20, offset).then(value => { if (active) setData(value); })
      .catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [offset]);
  return <div>
    <h1 className="text-xl font-semibold">审核历史</h1>
    <p className="my-3 text-sm text-ink-500">审核记录不等于真实报销台账。演示数据并非真实报销提交，请先核对来源。</p>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p>正在加载…</p>}
    {data && <>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead><tr>{["批次 / 时间", "数据来源", "状态", "张数", "结果"].map(x => <th key={x} className="p-3">{x}</th>)}</tr></thead>
        <tbody>{data.items.map(item => <tr key={item.batch_id} className="border-t border-slate-200">
          <td className="p-3"><div>{item.batch_id}</div><small>{item.created_at}</small></td>
          <td className="p-3">{sourceLabel(item.provider)}</td>
          <td className="p-3">{{processing:"审核中",done:"已完成",partial:"部分失败",failed:"失败"}[item.status]}</td>
          <td className="p-3">{item.invoice_count}</td>
          <td className="p-3"><Link className="text-brand-700 underline" href={`/batches/${item.batch_id}`}>查看</Link></td>
        </tr>)}</tbody>
      </table></div>
      {data.items.length === 0 && <p>暂无审核记录</p>}
      <div className="mt-4 flex gap-4">
        <button disabled={offset === 0} onClick={() => setOffset(n => Math.max(0,n-20))} className="disabled:opacity-40">上一页</button>
        <span>共 {data.total} 批</span>
        <button disabled={offset+20 >= data.total} onClick={() => setOffset(n => n+20)} className="disabled:opacity-40">下一页</button>
      </div>
    </>}
  </div>;
}
