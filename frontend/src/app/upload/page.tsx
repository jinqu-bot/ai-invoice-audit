"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { TransitionLink, usePageNavigation } from "@/components/PageTransitions";
import { UploadDropzone } from "@/components/UploadDropzone";
import { InvoiceRevealArtwork, InvoiceRevealTitle, InvoiceUploadReveal } from "@/components/InvoiceUploadReveal";
import { CompanySettingsForm } from "@/components/CompanySettingsForm";
import { SourceNotice } from "@/components/SourceNotice";
import { compressInvoice } from "@/lib/compress";
import { companyCriteriaKey, isCompanyConfigured } from "@/lib/company-settings";
import { API_BASE, api } from "@/lib/api";
import type { CompanySettings } from "@/lib/types";
import styles from "./CompanyGate.module.css";

export default function UploadPage() {
  const navigate = usePageNavigation();
  const [provider, setProvider] = useState<string>("unknown");
  const [compress, setCompress] = useState(false);
  const [progress, setProgress] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<"checking" | "ok" | "down">("checking");
  const [revealVersion, setRevealVersion] = useState(0);
  const [company, setCompany] = useState<CompanySettings | null>(null);
  const [companyState, setCompanyState] = useState<"loading" | "ready" | "error">("loading");
  const [companyError, setCompanyError] = useState("");
  const [companyNotice, setCompanyNotice] = useState("");
  const [editingCompany, setEditingCompany] = useState(false);
  const companyRequest = useRef(0);
  const configured = companyState === "ready" && isCompanyConfigured(company);
  const uploadEnabled = configured && !editingCompany;

  const loadCompany = useCallback(async () => {
    const request = ++companyRequest.current;
    setCompanyState("loading");
    setCompanyError("");
    setCompanyNotice("");
    try {
      const next = await api.getCompanySettings();
      if (request !== companyRequest.current) return;
      setCompany(next);
      setCompanyState("ready");
      setEditingCompany(false);
      setError(null);
    } catch (e) {
      if (request !== companyRequest.current) return;
      setCompanyState("error");
      setCompanyError(e instanceof Error ? e.message : "暂时无法读取公司配置");
    }
  }, []);

  useEffect(() => {
    let alive = true;
    api.health()
      .then(data => { if (alive) { setHealth("ok"); setProvider(data.recognition_provider ?? "unknown"); } })
      .catch(() => { if (alive) setHealth("down"); });
    void loadCompany();
    return () => { alive = false; ++companyRequest.current; };
  }, [loadCompany]);

  function companySaved(next: CompanySettings) {
    ++companyRequest.current;
    setCompany(next);
    setCompanyState("ready");
    setCompanyError("");
    setEditingCompany(false);
    setError(null);
    setCompanyNotice("公司配置已保存，请核对下方审核基准后选择发票。");
  }

  async function go(action: () => Promise<{ batch_id: string }>) {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError(null);
    try {
      const res = await action();
      navigate(`/batches/${res.batch_id}`);
    } catch (e) {
      setProgress("");
      setError(e instanceof Error ? e.message : "上传失败，请检查后端是否启动");
      submitting.current = false;
      setBusy(false);
    }
  }

  async function upload() {
    if (!uploadEnabled || !company || files.length === 0) return;
    const expectedCriteria = companyCriteriaKey(company);
    await go(async () => {
      const prepared: File[] = [];
      for (const [index, file] of files.entries()) {
        setProgress(`准备文件 ${index + 1}/${files.length}`);
        prepared.push(compress ? await compressInvoice(file) : file);
      }
      // Recheck immediately before POST: another tab may have changed this shared profile.
      setProgress("正在核对最新公司配置…");
      let latest: CompanySettings;
      try {
        latest = await api.getCompanySettings();
      } catch (e) {
        setCompanyState("error");
        setCompanyError(e instanceof Error ? e.message : "无法核对公司配置");
        throw new Error("暂时无法核对审核公司，本次尚未上传。请重试读取配置后再提交。");
      }
      setCompany(latest);
      setCompanyState("ready");
      if (!isCompanyConfigured(latest)) {
        setCompanyNotice("");
        throw new Error("当前公司尚未完成配置，本次尚未上传。请先填写并保存公司信息。");
      }
      if (companyCriteriaKey(latest) !== expectedCriteria) {
        setCompanyNotice("审核基准已更新，请核对公司、税号与标准，再点击开始审核。");
        throw new Error("公司配置已在其他页面变更，本次尚未上传，请核对最新配置后重试。");
      }
      const bytes = prepared.reduce((sum, file) => sum + file.size, 0);
      setProgress(`正在上传 ${prepared.length} 张，合计 ${(bytes / 1024 / 1024).toFixed(2)} MB`);
      return api.uploadFiles(prepared);
    });
  }

  return (
    <InvoiceUploadReveal replayVersion={revealVersion}>
      <section id="upload" className="upload-zone">
        <div className="upload-heading">
          <div><InvoiceRevealTitle /><p data-page-enter>先确认审核公司，再选文件开始审核。每一步都留下轨迹。</p></div>
          <div className="connection-chip" data-page-enter><span className={health === "ok" ? "live-dot" : "live-dot muted"} />{health === "ok" ? "API CONNECTED" : health === "checking" ? "CHECKING API" : "API OFFLINE"}</div>
        </div>
        <div className={`upload-stage ${styles.layout}`}>
          <InvoiceRevealArtwork />
          <div className="upload-workspace">
            <section className={styles.card} aria-labelledby="company-step-heading" data-page-enter>
              <div className={styles.header}>
                <h2 id="company-step-heading" className={styles.heading}>1 · 确认审核公司</h2>
                <span className={`${styles.badge} ${configured ? styles.ready : ""}`}>
                  {companyState === "loading" ? "读取中" : companyState === "error" ? "待重新核对" : configured ? "已配置" : "尚未配置"}
                </span>
              </div>
              {companyState === "loading" && <p className={styles.description} role="status">正在读取公司配置，核对完成后即可继续。</p>}
              {companyState === "error" && <>
                <p className={styles.error} role="alert">{companyError}。无法确认审核基准，暂不上传文件。</p>
                <button type="button" className={styles.button} disabled={busy} onClick={() => void loadCompany()}>重试读取配置</button>
              </>}
              {companyState === "ready" && company && <>
                {(!configured || editingCompany) ? <>
                  <p className={styles.description}>{company.is_default
                    ? "先填写本单位的名称与税号，并核对报销期限和费用标准。保存后才能上传，避免沿用演示公司的抬头判断。"
                    : "修改本审核台的公司信息。保存或取消后可继续上传，已选文件会保留。"}</p>
                  <CompanySettingsForm
                    settings={company}
                    onSaved={companySaved}
                    onCancel={configured ? () => setEditingCompany(false) : undefined}
                    submitLabel="保存公司配置，继续上传"
                    disabled={busy}
                  />
                </> : <>
                  <dl className={styles.summary}>
                    <div><dt>公司名称</dt><dd>{company.name}</dd></div>
                    <div><dt>纳税人识别号</dt><dd>{company.tax_id}</dd></div>
                  </dl>
                  <p className={styles.criteria}>提交期限 {company.deadline_days} 天 · 住宿 ¥{company.limits["住宿"].toLocaleString("zh-CN")} / 晚 · 招待 ¥{company.limits["招待"].toLocaleString("zh-CN")} / 次 · 办公 ¥{company.limits["办公"].toLocaleString("zh-CN")} / 笔</p>
                  <div className={styles.actions}>
                    <button type="button" className={styles.button} disabled={busy} onClick={() => { setEditingCompany(true); setCompanyNotice(""); }}>修改公司配置</button>
                    {!busy && <TransitionLink href="/settings" className={styles.link}>打开公司设置页 →</TransitionLink>}
                  </div>
                  <p className={styles.scope}>本审核台共用此配置，上传前请确认属于你的单位。保存会影响后续审核，处理中请勿修改；已完成记录不会自动重算。</p>
                </>}
              </>}
              {companyNotice && <p role="status" className={styles.notice}>{companyNotice}</p>}
            </section>
            <div data-page-enter><SourceNotice provider={provider} /></div>
            <div className="upload-panel" data-page-enter>
              <h2 className={styles.step}>2 · 选择并审核发票</h2>
              {!uploadEnabled && <p className={styles.locked}>请先完成上方公司配置并保存，再选择或提交发票。固定演示仍可直接体验。</p>}
              <UploadDropzone disabled={busy || !uploadEnabled} files={files} onFiles={next => { setFiles(next); setError(null); }} />
              <div className="upload-controls">
                <label><input type="checkbox" disabled={busy || !uploadEnabled} checked={compress} onChange={e => setCompress(e.target.checked)} />上传前压缩大图 <span>最长边 2560px，原文件不改</span></label>
                <button type="button" disabled={busy || !uploadEnabled || files.length === 0} onClick={() => void upload()} className="audit-submit">
                  {busy ? "正在处理…" : !uploadEnabled ? "先完成公司配置" : error ? "重试审核" : provider === "mock-vlm" ? "开始模拟审核" : "开始审核"}<span>↗</span>
                </button>
              </div>
              {progress && <p role="status" className="upload-progress">{progress}</p>}
              {error && <div role="alert" className="upload-error">{error}<p>已保留所选文件，可修改后重试。</p></div>}
              <div className="upload-footer">
                <div className="upload-footer-actions">
                  <button type="button" disabled={busy} onClick={() => go(() => api.uploadDemo())} className="demo-link">加载演示数据（5 张） →</button>
                  <button type="button" disabled={busy} onClick={() => setRevealVersion(version => version + 1)} className="replay-reveal">重播入场</button>
                </div>
                <span>后端 {API_BASE} · {health === "ok" ? "已连接" : health === "checking" ? "检测中…" : "未连接"}</span>
              </div>
            </div>
            {health === "down" && <div className="offline-note">连不上后端：请在项目根目录启动 <code>uvicorn app.main:app --reload --port 8000 --app-dir backend</code></div>}
          </div>
        </div>
      </section>
    </InvoiceUploadReveal>
  );
}
