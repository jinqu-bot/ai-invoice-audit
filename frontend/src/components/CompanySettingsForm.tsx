"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import type { CompanySettings } from "@/lib/types";
import styles from "./CompanySettingsForm.module.css";

const LIMIT_FIELDS = [
  { key: "住宿", label: "住宿标准", unit: "元 / 晚" },
  { key: "招待", label: "招待标准", unit: "元 / 次" },
  { key: "办公", label: "办公标准", unit: "元 / 笔" },
] as const;

type Props = {
  settings: CompanySettings;
  onSaved: (next: CompanySettings) => void;
  onCancel?: () => void;
  submitLabel?: string;
  disabled?: boolean;
};

/** A server-backed editor shared by upload onboarding and the settings page. */
export function CompanySettingsForm({
  settings,
  onSaved,
  onCancel,
  submitLabel = "保存公司配置",
  disabled = false,
}: Props) {
  const id = useId();
  const form = useRef<HTMLFormElement>(null);
  const savingRef = useRef(false);
  const mounted = useRef(true);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState(settings.is_default ? "" : settings.name);
  const [taxId, setTaxId] = useState(settings.is_default ? "" : settings.tax_id);
  // Strings preserve a deliberately cleared field instead of silently changing it to zero.
  const [days, setDays] = useState(String(settings.deadline_days));
  const [limits, setLimits] = useState<Record<string, string>>(() =>
    Object.fromEntries(LIMIT_FIELDS.map(({ key }) => [key, String(settings.limits[key] ?? "")])),
  );
  const [error, setError] = useState<string | null>(null);
  const [invalid, setInvalid] = useState<string | null>(null);
  const locked = disabled || saving;

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  function reject(field: string, message: string) {
    setInvalid(field);
    setError(message);
    const input = form.current?.elements.namedItem(field);
    if (input instanceof HTMLInputElement) input.focus();
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Lock synchronously: a second submit must not slip in before React renders disabled.
    if (savingRef.current || disabled) return;
    setError(null);
    setInvalid(null);
    const companyName = name.trim();
    const companyTaxId = taxId.trim().toUpperCase();
    if (companyName.length < 2 || companyName.length > 60) {
      reject("company_name", "请填写 2–60 个字符的公司全称，与登记信息一致。");
      return;
    }
    if (!/^[0-9A-Z]{15,20}$/.test(companyTaxId)) {
      reject("company_tax_id", "纳税人识别号应为 15–20 位字母或数字。");
      return;
    }
    const deadline = Number(days.trim());
    if (!/^\d+$/.test(days.trim()) || !Number.isInteger(deadline) || deadline < 1 || deadline > 365) {
      reject("deadline_days", "提交期限请填写 1–365 之间的整数，不能留空。");
      return;
    }
    const parsedLimits: Record<string, number> = {};
    for (const field of LIMIT_FIELDS) {
      const raw = (limits[field.key] ?? "").trim();
      const value = Number(raw);
      if (!/^(?:\d+(?:\.\d{0,2})?|\.\d{1,2})$/.test(raw)
          || !Number.isFinite(value) || value < 0 || value > 10_000_000) {
        reject(`limit_${field.key}`, `${field.label}请填写 0–10,000,000 的金额，最多两位小数，不能留空。`);
        return;
      }
      parsedLimits[field.key] = value;
    }
    savingRef.current = true;
    setSaving(true);
    try {
      const next = await api.updateCompanySettings({
        name: companyName,
        tax_id: companyTaxId,
        deadline_days: deadline,
        limits: parsedLimits,
      });
      if (!mounted.current) return;
      setName(next.name);
      setTaxId(next.tax_id);
      setDays(String(next.deadline_days));
      setLimits(Object.fromEntries(LIMIT_FIELDS.map(({ key }) => [key, String(next.limits[key] ?? "")])));
      onSaved(next);
    } catch (cause) {
      if (mounted.current) setError(cause instanceof Error ? cause.message : "保存失败，请重试。已保留填写内容。");
    } finally {
      savingRef.current = false;
      if (mounted.current) setSaving(false);
    }
  }

  function describedBy(field: string, hint?: string) {
    return [hint, invalid === field ? `${id}-error` : undefined].filter(Boolean).join(" ") || undefined;
  }

  return (
    <form ref={form} className={styles.form} onSubmit={save} noValidate aria-busy={saving}>
      <p className={styles.scope}>
        此配置由整个审核台共用，请按公司的登记信息填写。保存后后续处理使用新配置；有批次正在审核时，请先等待处理结束。
      </p>
      <fieldset className={styles.fieldset} disabled={locked}>
        <legend className={styles.legend}>公司主体</legend>
        <p className={styles.sectionHint}>
          填写报销所属公司的全称与税号，作为购买方核对基准。
          {settings.is_default && "当前没有配置，演示公司的名称和税号不会自动代填。"}
        </p>
        <div className={styles.grid}>
          <div className={styles.field}>
            <label htmlFor={`${id}-name`}>公司全称 <span>必填</span></label>
            <input
              id={`${id}-name`} name="company_name" autoComplete="organization" required maxLength={60}
              className={styles.input} value={name} onChange={(event) => setName(event.target.value)}
              placeholder="填写公司登记全称" aria-invalid={invalid === "company_name"}
              aria-describedby={describedBy("company_name")}
            />
          </div>
          <div className={styles.field}>
            <label htmlFor={`${id}-tax`}>纳税人识别号 <span>必填</span></label>
            <input
              id={`${id}-tax`} name="company_tax_id" autoComplete="off" required maxLength={20}
              className={`${styles.input} ${styles.taxId}`} value={taxId}
              onChange={(event) => setTaxId(event.target.value.toUpperCase())}
              placeholder="15–20 位字母或数字" spellCheck={false}
              aria-invalid={invalid === "company_tax_id"} aria-describedby={describedBy("company_tax_id")}
            />
          </div>
        </div>
      </fieldset>

      <fieldset className={styles.fieldset} disabled={locked}>
        <legend className={styles.legend}>报销制度参数</legend>
        <p id={`${id}-policy-hint`} className={styles.sectionHint}>请核对公司的提交期限及费用标准。金额允许为 0，最多保留两位小数。</p>
        <div className={styles.grid}>
          <div className={styles.field}>
            <label htmlFor={`${id}-days`}>提交期限</label>
            <div className={styles.inputWithUnit}>
              <input
                id={`${id}-days`} name="deadline_days" type="text" inputMode="numeric" autoComplete="off" required
                className={styles.input} value={days} onChange={(event) => setDays(event.target.value)}
                aria-invalid={invalid === "deadline_days"}
                aria-describedby={describedBy("deadline_days", `${id}-days-unit`)}
              />
              <span id={`${id}-days-unit`} className={styles.unit}>天内 · 1–365</span>
            </div>
          </div>
          {LIMIT_FIELDS.map((field) => (
            <div className={styles.field} key={field.key}>
              <label htmlFor={`${id}-${field.key}`}>{field.label}</label>
              <div className={styles.inputWithUnit}>
                <input
                  id={`${id}-${field.key}`} name={`limit_${field.key}`} type="text" inputMode="decimal" autoComplete="off" required
                  className={styles.input} value={limits[field.key] ?? ""} placeholder="0.00"
                  onChange={(event) => setLimits((previous) => ({ ...previous, [field.key]: event.target.value }))}
                  aria-invalid={invalid === `limit_${field.key}`}
                  aria-describedby={describedBy(`limit_${field.key}`, `${id}-${field.key}-unit`)}
                />
                <span id={`${id}-${field.key}-unit`} className={styles.unit}>{field.unit}</span>
              </div>
            </div>
          ))}
        </div>
      </fieldset>

      <div className={styles.notes}>
        <p>抬头核对会读取此配置。有明确价税信息时，后端按购买方名称和税号比对；交通票据等缺少相关信息、且购买方不匹配时转人工核对，不能仅凭识别字段确定票种。</p>
        <p>已完成的审核记录不会自动重算，固定演示批次也不会改变。费用标准已可配置，制度条款原文中的数字目前仍需另行同步。</p>
      </div>

      {error && <p id={`${id}-error`} role="alert" className={styles.error}>{error}</p>}
      <div className={styles.actions}>
        <button type="submit" className={styles.primary} disabled={locked}>{saving ? "正在保存…" : submitLabel}</button>
        {onCancel && <button type="button" className={styles.secondary} disabled={locked} onClick={() => {
          if (!savingRef.current && !disabled) onCancel();
        }}>取消编辑</button>}
        {saving && <span role="status" className={styles.saving}>正在将配置保存到审核台，请稍候。</span>}
      </div>
    </form>
  );
}
