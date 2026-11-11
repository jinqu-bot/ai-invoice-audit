export function StatCard({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: "emerald" | "amber" | "rose" | "indigo" | "default";
}) {
  const color =
    accent === "emerald"
      ? "text-emerald-600"
      : accent === "amber"
        ? "text-amber-600"
        : accent === "rose"
          ? "text-rose-600"
          : accent === "indigo"
            ? "text-indigo-600"
            : "text-ink-900";

  return (
    <div className="card px-4 py-3">
      <div className="text-[11.5px] text-ink-500">{label}</div>
      <div className={`num mt-1 text-[20px] font-semibold leading-tight ${color}`}>
        {value}
      </div>
      {hint && <div className="mt-0.5 text-[11px] text-ink-300">{hint}</div>}
    </div>
  );
}

export function BarList({
  items,
  formatValue,
  barClass = "bg-brand-500",
}: {
  items: { label: string; value: number; hint?: string }[];
  formatValue?: (v: number) => string;
  barClass?: string;
}) {
  const max = Math.max(...items.map((i) => i.value), 1);

  if (items.length === 0) {
    return <p className="text-[12px] text-ink-400">暂无数据</p>;
  }

  return (
    <ul className="space-y-2.5">
      {items.map((item) => (
        <li key={item.label}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-[12px]">
            <span className="truncate text-ink-700">{item.label}</span>
            <span className="num shrink-0 text-ink-500">
              {formatValue ? formatValue(item.value) : item.value}
              {item.hint && (
                <span className="ml-1 text-ink-300">· {item.hint}</span>
              )}
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className={`h-full rounded-full ${barClass}`}
              style={{ width: `${Math.max((item.value / max) * 100, 3)}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
