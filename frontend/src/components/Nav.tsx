"use client";

import { TransitionLink as Link } from "@/components/PageTransitions";
import { usePathname } from "next/navigation";
import { DEMO_BATCH_ID } from "@/lib/api";

const NAV = [
  { href: "/upload", label: "上传发票", desc: "拖一叠进来" },
  { href: "/", label: "项目介绍", desc: "这个系统在做什么" },
  { href: `/batches/${DEMO_BATCH_ID}`, label: "审核结果", desc: "演示批次" },
  { href: "/history", label: "审核历史", desc: "按来源核对记录" },
  { href: "/ask", label: "制度问答", desc: "按条款回答，答不出就说没有" },
  { href: "/dashboard", label: "审核看板", desc: "本月概览" },
  { href: "/settings", label: "公司配置", desc: "抬头与费用标准" },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname.startsWith(href.split("?")[0]);
}

export function SideNav() {
  const pathname = usePathname();

  return (
    <aside className="audit-side-nav sticky top-0 hidden h-screen w-60 shrink-0 flex-col overflow-y-auto border-r border-white/10 bg-[#0c0e14] px-3 py-5 lg:flex">
      <Link href="/" className="mb-7 block shrink-0 px-2">
        <div className="text-[15px] font-semibold tracking-tight text-white">
          AI 报销审核台
        </div>
        <div className="mt-0.5 text-[11px] text-white/45">
          让每条驳回都有依据
        </div>
      </Link>

      <nav aria-label="主导航" className="mb-4 flex shrink-0 flex-col gap-1">
        {NAV.map((item) => {
          const active = isActive(pathname, item.href.startsWith("/batches/") ? "/batches/" : item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={[
                "group rounded-lg px-3 py-2 transition-colors",
                active
                  ? "bg-white/10 text-white"
                  : "text-white/60 hover:bg-white/5 hover:text-white",
              ].join(" ")}
            >
              <div className="text-[13.5px] font-medium">{item.label}</div>
              <div
                className={[
                  "text-[11px]",
                  active ? "text-orange-300/80" : "text-white/35",
                ].join(" ")}
              >
                {item.desc}
              </div>
            </Link>
          );
        })}
      </nav>

      <div className="mt-auto shrink-0 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-3 text-[11px] leading-relaxed text-white/45">
        <div className="mb-1 font-medium text-white/80">当前阶段：D8</div>
        规则引擎 R0–R8 · 结果落库 · 进度实时 · <b className="font-medium text-white/80">人工可改判</b>。
        <br />
        识别来源以每张记录的标识为准。
      </div>
    </aside>
  );
}

export function MobileNav() {
  const pathname = usePathname();

  return (
    <div className="audit-mobile-nav sticky top-0 z-20 border-b border-white/10 bg-[#0c0e14]/90 backdrop-blur lg:hidden">
      <div className="flex items-center gap-4 px-4 py-3">
        <span className="shrink-0 text-[13px] font-semibold text-white">AI 报销审核台</span>
        <nav aria-label="主导航" className="flex min-w-0 flex-1 gap-1 overflow-x-auto">
          {NAV.map((item) => {
            const active = isActive(pathname, item.href.startsWith("/batches/") ? "/batches/" : item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={[
                  "flex min-h-11 shrink-0 items-center whitespace-nowrap rounded-md px-2.5 py-1 text-[12.5px]",
                  active ? "bg-white/10 text-white" : "text-white/60",
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
