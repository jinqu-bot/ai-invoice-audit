"use client";

import { useEffect, useState } from "react";
import { CompanySettingsForm } from "@/components/CompanySettingsForm";
import { TransitionLink } from "@/components/PageTransitions";
import { api } from "@/lib/api";
import type { CompanySettings } from "@/lib/types";
import styles from "@/components/CompanySettingsForm.module.css";

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [settings, setSettings] = useState<CompanySettings | null>(null);
  const [revision, setRevision] = useState(0);
  const [saved, setSaved] = useState<CompanySettings | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    api.getCompanySettings()
      .then((next) => { if (alive) setSettings(next); })
      .catch((cause) => {
        if (alive) {
          setSettings(null);
          setError(cause instanceof Error ? cause.message : "暂时无法读取公司配置，请重试。");
        }
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [revision]);

  return (
    <div className={`audit-shell ${styles.settingsPage}`}>
      <div className={styles.pageInner}>
        <header className={styles.pageHeader}>
          <div className={styles.eyebrow}>COMPANY PROFILE</div>
          <h1>公司配置</h1>
          <p>先确定审核哪家公司的票，再核对发票。公司全称和税号是购买方比对基准，提交期限与费用标准用于后续规则检查。</p>
          {!loading && settings && <p className={styles.meta}>{settings.is_default
            ? "尚未配置公司，请先填写并保存，再上传发票。"
            : `当前公司：${settings.name} · 上次保存：${settings.updated_at ?? "未记录"}`}</p>}
        </header>

        {loading ? (
          <div className={styles.stateCard} role="status">正在读取审核台的公司配置…</div>
        ) : error || !settings ? (
          <section className={styles.stateCard}>
            <h2>公司配置暂时无法读取</h2>
            <p role="alert">{error ?? "未取得有效配置，请重试。"}</p>
            <button type="button" className={styles.primary} onClick={() => setRevision((value) => value + 1)}>重新读取配置</button>
          </section>
        ) : (
          <>
            <CompanySettingsForm settings={settings} onSaved={(next) => {
              setSettings(next);
              setSaved(next);
            }} />
            {saved && <section className={styles.savedCard}>
              <p role="status">最近一次保存成功：{saved.name}。税号 {saved.tax_id}；保存时间 {saved.updated_at ?? "刚刚"}。</p>
              <TransitionLink href="/upload" className={styles.primary}>前往上传发票 →</TransitionLink>
            </section>}
          </>
        )}
      </div>
    </div>
  );
}
