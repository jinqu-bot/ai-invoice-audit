export function sourceLabel(provider?: string): string {
  return ({ "mock-vlm": "模拟识别 · 与上传票面无关", fixture: "固定演示数据",
    "openai-compat": "模型接口结果 · 请核对票面", mixed: "混合来源 · 请逐张核对" } as Record<string, string>)[provider ?? ""] ?? "来源未核实";
}

export function SourceNotice({ provider, compact = false }: { provider?: string; compact?: boolean }) {
  const demo = provider === "mock-vlm" || provider === "fixture";
  return <div role="note" className="my-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-900">
    <strong>{sourceLabel(provider)}</strong>
    {!compact && <p className="mt-1">{provider === "mock-vlm"
      ? "模拟识别不会读取上传票面。照片仅用于上传流程测试，金额、商家、号码及审核结论来自模拟样例，与上传票面无关。重复提示只针对样例号码，不代表真实报销。"
      : provider === "fixture" ? "该记录来自固定演示数据，并非真实报销提交。人物、金额和重复记录均用于演示。"
      : provider === "openai-compat" ? "字段由配置的模型接口返回，仍须核对原图。命中既往审核记录不代表该票已经实际报销。"
      : "请先核实每张发票的数据来源；这些记录不能直接证明真实报销。"}</p>}
    {compact && demo && <p>演示结论并非真实报销记录</p>}
  </div>;
}
