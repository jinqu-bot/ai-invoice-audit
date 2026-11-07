"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { DEMO_BATCH_ID } from "@/lib/api";

const NAV = [
  { href: "/", label: "上传发票", desc: "拖一叠进来" },
  { href: `/batches/${DEMO_BATCH_ID}`, label: "审核结果", desc: "演示批次" },
  { href: "/dashboard", label: "审核看板", desc: "本月概览" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href.split("?")[0]);
}

export function SideNav() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-slate-200 bg-white px-3 py-5 lg:flex">
      <Link href="/" className="mb-7 block px-2">
        <div className="text-[15px] font-semibold tracking-tight text-brand-700">
          AI 报销审核台
        </div>
        <div className="mt-0.5 text-[11px] text-ink-500">
          让每条驳回都有依据
        </div>
      </Link>

      <nav className="flex flex-col gap-1">
        {NAV.map((item) => {
          const active = isActive(pathname, item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={[
                "group rounded-lg px-3 py-2 transition-colors",
                active
                  ? "bg-brand-50 text-brand-700"
                  : "text-ink-700 hover:bg-slate-50",
              ].join(" ")}
            >
              <div className="text-[13.5px] font-medium">{item.label}</div>
              <div
                className={[
                  "text-[11px]",
                  active ? "text-brand-500/80" : "text-ink-500",
                ].join(" ")}
              >
                {item.desc}
              </div>
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto rounded-lg bg-slate-50 px-3 py-3 text-[11px] leading-relaxed text-ink-500">
        <div className="mb-1 font-medium text-ink-700">当前阶段：D6</div>
        规则引擎 R0–R8 · 结果落库 · 进度实时。
        <br />
        识别走 mock（未接真模型 key）。
      </div>
    </aside>
  );
}

export function MobileNav() {
  const pathname = usePathname();

  return (
    <div className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur lg:hidden">
      <div className="flex items-center gap-4 px-4 py-3">
        <span className="text-[13px] font-semibold text-brand-700">AI 报销审核台</span>
        <nav className="flex gap-1 overflow-x-auto">
          {NAV.map((item) => {
            const active = isActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={[
                  "whitespace-nowrap rounded-md px-2.5 py-1 text-[12.5px]",
                  active ? "bg-brand-50 text-brand-700" : "text-ink-700",
                ].join(" ")}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
