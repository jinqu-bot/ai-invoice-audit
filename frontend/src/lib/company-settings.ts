import type { CompanySettings } from "./types";

/** Use the server's saved profile, never a browser-local onboarding flag. */
export function isCompanyConfigured(company: CompanySettings | null): company is CompanySettings {
  return company !== null && company.is_default === false
    && company.name.trim().length >= 2
    && /^[0-9A-Z]{15,20}$/.test(company.tax_id.trim())
    && Number.isInteger(company.deadline_days)
    && company.deadline_days >= 1 && company.deadline_days <= 365
    && ["住宿", "招待", "办公"].every(key => Number.isFinite(company.limits[key])
      && company.limits[key] >= 0 && company.limits[key] <= 10_000_000);
}

/** Ignore save timestamps; compare the actual audit criteria shown to the user. */
export function companyCriteriaKey(company: CompanySettings): string {
  return JSON.stringify([
    company.name, company.tax_id, company.deadline_days,
    ...["住宿", "招待", "办公"].map(key => company.limits[key]),
  ]);
}
