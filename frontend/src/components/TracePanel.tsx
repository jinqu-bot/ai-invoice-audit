import { TRACE_STATUS_META } from "@/lib/format";
import type { TraceStep } from "@/lib/types";

/**
 * 审核轨迹。
 * reason 这一栏是整个"可解释 Agent"的证据，一定不能省——评委看的就是它。
 */
export function TracePanel({ steps }: { steps: TraceStep[] }) {
  if (steps.length === 0) {
    return <p className="text-[12.5px] text-ink-500">没有轨迹记录。</p>;
  }

  return (
    <ol className="relative ml-2 space-y-4 border-l border-slate-200 pl-5">
      {steps.map((step) => {
        const meta = TRACE_STATUS_META[step.status];
        const hasPayload = Boolean(step.args || step.result);

        return (
          <li key={`${step.step}-${step.tool}`} className="relative">
            <span
              className={`absolute -left-[27px] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-white ${meta.dot}`}
            />

            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
              <div className="flex items-baseline gap-2">
                <span className="num text-[11px] text-ink-300">
                  {String(step.step).padStart(2, "0")}
                </span>
                <span className="text-[13px] font-medium text-ink-900">
                  {step.title}
                </span>
                <code className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[10.5px] text-ink-500">
                  {step.tool}
                </code>
              </div>
              <div className="num flex items-center gap-2 text-[11px] text-ink-500">
                <span>{meta.label}</span>
                <span className="text-ink-300">·</span>
                <span>{step.latency_ms}ms</span>
              </div>
            </div>

            <p className="mt-1 text-[12px] leading-relaxed text-ink-500">
              {step.reason}
            </p>

            {hasPayload && (
              <details className="mt-1.5">
                <summary className="cursor-pointer text-[11px] text-brand-500 hover:text-brand-700">
                  看参数与返回
                </summary>
                <pre className="mt-1.5 overflow-x-auto rounded-md bg-slate-50 p-2.5 font-mono text-[10.5px] leading-relaxed text-ink-700">
{JSON.stringify({ args: step.args, result: step.result }, null, 2)}
                </pre>
              </details>
            )}
          </li>
        );
      })}
    </ol>
  );
}
