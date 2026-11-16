"use client";

/**
 * 公司配置。
 *
 * 这个系统是"给一家公司用的审核台"：抬头和税号就是 R3 的比对基准，
 * 期限和费用标准是 R4/R5 的参数。换一家公司不用改代码、不用重新部署，
 * 在这里填完保存就生效——这也是最容易被问的那件事的答案。
 */

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { CompanySettings } from "@/lib/types";

const LIMIT_FIELDS: { key: string; label: string; unit: string }[] = [
  { key: "住宿", label: "住宿标准", unit: "元 / 晚" },
  { key: "招待", label: "招待标准", unit: "元 / 次" },
  { key: "办公", label: "办公标准", unit: "元 / 笔" },
];

const INPUT =
  "w-full rounded-md border border-slate-200 px-3 py-1.5 text-[13px] outline-none focus:border-brand-500";

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState("");
  const [meta, setMeta] = useState<CompanySettings | null>(null);

  const [name, setName] = useState("");
  const [taxId, setTaxId] = useState("");
  const [deadlineDays, setDeadlineDays] = useState(30);
  const [limits, setLimits] = useState<Record<string, number>>({});

  useEffect(() => {
    let alive = true;
    api
      .getCompanySettings()
      .then((s) => {
        if (!alive) return;
        setMeta(s);
        setName(s.name);
        setTaxId(s.tax_id);
        setDeadlineDays(s.deadline_days);
        setLimits({ ...s.limits });
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : "加载失败"))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  async function save() {
    setError(null);
    setSaved("");
    if (name.trim().length < 2) {
      setError("公司名称至少 2 个字");
      return;
    }
    if (!/^[0-9A-Za-z]{15,20}$/.test(taxId.trim())) {
      setError("纳税人识别号应为 15–20 位字母或数字");
      return;
    }
    setSaving(true);
    try {
      const next = await api.updateCompanySettings({
        name: name.trim(),
        tax_id: taxId.trim().toUpperCase(),
        deadline_days: Number(deadlineDays),
        limits,
      });
      setMeta(next);
      setName(next.name);
      setTaxId(next.tax_id);
      setDeadlineDays(next.deadline_days);
      setLimits({ ...next.limits });
      setSaved("已保存，从下一张发票开始按新配置判定");
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <div className="skeleton h-6 w-40" />
        <div className="skeleton h-64 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <header className="mb-5">
        <h1 className="text-[20px] font-semibold tracking-tight text-ink-900">公司配置</h1>
        <p className="mt-1 text-[11.5px] text-ink-500">
          这个系统服务一家公司。下面填的是<b className="font-medium text-ink-700">审核基准</b>：
          抬头和税号用于判断"这张票能不能入账"，期限和标准用于判断"该不该报"。
        </p>
        <p className="mt-1 text-[11.5px] text-ink-500">
          {meta?.is_default
            ? "当前仍为内置默认公司（演示用），还没配置过。"
            : `上次保存：${meta?.updated_at ?? "—"}`}
        </p>
      </header>

      <section className="card p-5">
        <h2 className="text-[13.5px] font-semibold text-ink-900">主体信息</h2>
        <p className="mt-1 text-[11px] text-ink-400">
          发票购买方必须与这里<b className="font-medium text-ink-700">完全一致</b>，差一个字都算抬头不符（R3）。
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-[12px] text-ink-700">公司名称</span>
            <input
              className={INPUT}
              maxLength={60}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例：杭州云帆科技有限公司"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[12px] text-ink-700">纳税人识别号</span>
            <input
              className={INPUT}
              maxLength={20}
              value={taxId}
              onChange={(e) => setTaxId(e.target.value.toUpperCase())}
              placeholder="例：91330100MA2A1B2C3D"
            />
          </label>
        </div>
      </section>

      <section className="card mt-4 p-5">
        <h2 className="text-[13.5px] font-semibold text-ink-900">制度参数</h2>
        <p className="mt-1 text-[11px] text-ink-400">
          提交期限对应 R4，三个标准对应 R5。改了立刻生效，不用重启。
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-[12px] text-ink-700">提交期限</span>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min={1}
                max={365}
                className={INPUT}
                value={deadlineDays}
                onChange={(e) => setDeadlineDays(Number(e.target.value))}
              />
              <span className="shrink-0 text-[12px] text-ink-400">天内</span>
            </div>
          </label>
          {LIMIT_FIELDS.map((f) => (
            <label key={f.key} className="block">
              <span className="mb-1 block text-[12px] text-ink-700">{f.label}</span>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={0}
                  step={10}
                  className={INPUT}
                  value={limits[f.key] ?? 0}
                  onChange={(e) =>
                    setLimits((prev) => ({ ...prev, [f.key]: Number(e.target.value) }))
                  }
                />
                <span className="shrink-0 text-[12px] text-ink-400">{f.unit}</span>
              </div>
            </label>
          ))}
        </div>
      </section>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="min-h-11 rounded-md bg-brand-600 px-4 py-2 text-[13px] font-medium text-white transition hover:bg-brand-700 disabled:opacity-60"
        >
          {saving ? "保存中…" : "保存配置"}
        </button>
        {saved && <span className="text-[12px] text-emerald-700">{saved}</span>}
        {error && <span className="text-[12px] text-rose-700">{error}</span>}
      </div>

      <section className="mt-5 rounded-lg border border-slate-200 bg-slate-50 p-4 text-[11.5px] leading-relaxed text-ink-500">
        <div className="mb-1 font-medium text-ink-700">改配置会发生什么</div>
        <ul className="list-disc space-y-1 pl-4">
          <li>只影响<b className="font-medium text-ink-700">之后上传</b>的发票；库里已有的审核记录不会被改写。</li>
          <li>演示批次 <code>B20261104-001</code> 是内置固定样例（抬头为杭州云帆），不随配置变化。</li>
          <li>费用标准与制度条款原文目前是两份数据：改了标准，条款里印的还是原数字，制度同源是下一步。</li>
        </ul>
      </section>
    </div>
  );
}