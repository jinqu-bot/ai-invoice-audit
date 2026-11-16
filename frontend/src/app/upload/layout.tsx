import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "上传发票 · AI 报销审核台",
};

export default function UploadLayout({ children }: { children: ReactNode }) {
  return children;
}
