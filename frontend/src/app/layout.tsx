import type { Metadata } from "next";
import "./globals.css";
import "./page-transitions.css";
import "./invoice-cursor-flock.css";
import { MobileNav, SideNav } from "@/components/Nav";
import { PageTransitions } from "@/components/PageTransitions";

export const metadata: Metadata = {
  title: "AI 报销审核台",
  description: "不是帮你识别发票，是帮你决定这张发票该不该报。",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-slate-50 text-ink-900 antialiased">
        <PageTransitions>
          <div className="mx-auto flex min-h-screen w-full max-w-[1440px]">
            <SideNav />
            <div className="flex min-w-0 flex-1 flex-col">
              <MobileNav />
              <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-10 lg:py-9">
                {children}
              </main>
            </div>
          </div>
        </PageTransitions>
      </body>
    </html>
  );
}
