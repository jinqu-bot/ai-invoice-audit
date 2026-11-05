import { VERDICT_META } from "@/lib/format";
import type { Verdict } from "@/lib/types";

export function VerdictBadge({
  verdict,
  size = "md",
}: {
  verdict: Verdict;
  size?: "sm" | "md";
}) {
  const meta = VERDICT_META[verdict];
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 rounded-full font-medium ring-1 ring-inset",
        meta.badge,
        size === "sm" ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
      ].join(" ")}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${meta.dot}`} />
      {meta.label}
    </span>
  );
}
