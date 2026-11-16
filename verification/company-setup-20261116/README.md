# 公司配置与上传联调验收（2026-11-16）

基于 `main@61ace06`，分支 `feat/company-setup-upload`。接入 A 已提供的 `GET/PUT /api/settings/company`，本次不修改后端、API 类型、依赖或规则。

## 交付行为

- `/upload` 先展示公司确认步骤。默认演示配置不算完成配置，首次公司的名称、税号留空；保存成功后才允许选择和提交文件。
- 共享表单校验公司全称、税号、提交期限和三类费用标准；避免空金额被转换为 0，防止重复保存，失败保留输入。
- 保存后的上传页显示当前审核基准，支持就地修改和前往 `/settings`；设置页保持深色主题并复用表单。
- 压缩完成、上传 POST 前重新 GET 公司配置。读取失败、配置恢复默认或审核基准变更时，本次不上传，保留文件供核对重试。
- 固定的 5 张演示数据仍可直接体验。公司配置不覆盖已经完成的历史结论。

## 实际验证结果

| 检查 | 结果 |
| --- | --- |
| `npx tsc --noEmit` | 退出码 0 |
| `NEXT_PUBLIC_API_BASE= npm run build` | 退出码 0；Next.js 14.2.35，包含 `/upload` 和 `/settings` |
| `python -m pytest backend/tests/test_settings.py backend/tests/test_rules.py -q` | 44 passed；已有 Starlette 弃用提示，无失败 |
| `git diff --check` | 退出码 0 |
| 浏览器流程检查 | 13 个场景全部通过；见 [browser-check.json](browser-check.json) |
| 原有动画回归 | 全部通过；见 [animation-check.json](animation-check.json) |

Windows 上构建通过忽略的 `.env.production.local` 将 `NEXT_PUBLIC_API_BASE` 设为空字符串，使用同源 API 部署配置。验收浏览器为本机 Edge（Playwright 驱动），桌面 1280×720、手机视口 390×844。使用隔离的本地 SQLite、模拟识别服务，没有调用真实模型或修改线上公司信息。上述测试是流程/规则回归，不能作为识别准确率。

13 个流程场景覆盖：默认配置锁定上传；无效字段不发请求；保存失败保留输入；重复提交只保存一次；编辑/取消保留文件和压缩选项；入场重播/跳过保留状态；配置变化阻止 POST；提交前读取失败及重试；实际上传 HTTP 202 并跳转到完成的模拟批次；刷新持久化、页面过渡与浏览器后退；390px 手机表单/选择文件/导航/Esc；设置页首次读取失败仅显示重试；无公司配置时固定演示及减少动态效果模式仍可操作。

动画检查覆盖：地图滚动前标签隐藏、滚动后 12 个标签出现；图群 6 张图片在 12 个槽位加载并随鼠标更新；首页底部 CTA 完整可见并通过过渡进入上传页；旧 `/#upload` 跳转；整页入场只有一个实例、可结束/重播/跳过。

以下原文件相对 `main@61ace06` 无差异：`InvoiceUploadReveal.tsx`、`InvoiceUploadReveal.module.css`、`PageTransitions.tsx`、`InvoiceMapHero.tsx`、`InvoiceCursorFlock.tsx`、`globals.css`、`page-transitions.css`、`invoice-cursor-flock.css`。新增 CSS 使用模块作用域，仅上传布局设为顶部对齐，以便首次配置表单展开时票据装饰仍在首屏。

## 截图

- [首次配置与锁定状态](desktop-first-setup.png)
- [配置后上传页](desktop-configured.png)
- [390px 上传页](mobile-configured.png)
- [390px 公司设置页](mobile-settings.png)
- [入场重播](reveal-replay.png)
- [发票地图滚动](intro-map.png)
- [光标票据图群](intro-flock.png)

## 给 A、C 的接口与评测边界

1. 配置属于当前部署共享的公司档案，不是个人账户隔离。前端流程限制不是后端接口的权限控制；直接调用上传 API 的行为未改变。
2. 上传前 GET 能发现此前的变更，但 GET、POST、后台规则执行之间没有原子锁定。后端按处理时的共享配置读取规则，不存在批次配置快照；有批次处理中时应避免改配置。多人隔离/批次快照需要另行后端设计。
3. R3 继续按 A 的规则执行，不保证任意抬头都通过。设置本单位是为了避免沿用演示公司误判；票种适用性仍使用现有价税信息启发式判断。
4. 可编辑阈值与制度条款原文目前不是同一来源，修改限额后条款原文数字不会自动同步；表单已提示此限制。
5. C 做规则回归需同时固定公司名称/税号、期限/费用标准、评测日期与台账。识别字段准确率继续与规则结论分开统计，固定演示批次仍使用原演示数据。

A 审查合并后统一部署；本次未直接推送 `main` 或更新公网服务。
