# AI 报销审核台

第九届传智杯 AI WEB 网页开发挑战赛参赛项目。上传票据后提取字段，按内置报销制度检查，展示命中规则、条款和处理轨迹；机器判断有误时可人工复核并保留变更记录。

本文件于 2026-11-16 整合，应用代码基线为 `afc9e2a`，已包含公司配置、独立上传页、整页入场动画及浅色公司设置页。本次材料更新只修改说明与环境模板，不改变业务代码；线上部署版本以部署负责人的记录为准。

提交材料：[技术文档 PDF](docs/技术文档.pdf) · [技术文档源稿](docs/技术文档.md) · [环境配置与安装运行](docs/环境配置与安装运行.md)。PDF 与本次整合的源稿同步导出，覆盖八章技术说明。

## 入口

- 正式在线演示：[项目介绍](https://shenpiaobao.xyz/) · [直接上传](https://shenpiaobao.xyz/upload)。域名 HTTP 会跳转至 HTTPS；旧 IP `http://8.217.202.172` 仅作兜底，不作为默认分享入口。
- 代码仓库：https://github.com/jinqu-bot/ai-invoice-audit
- 本地前端：http://127.0.0.1:3100；接口文档：http://127.0.0.1:8000/docs
- 当前应用无登录流程，不需要体验账号。仓库整理时为 Private，提交前须由管理员为评审提供访问权限或按授权调整可见性。
- 无密钥可体验流程，但 `mock-vlm` 不读取票面，不能证明识别准确率；固定演示批次使用 `fixture`。

## 核心能力

1. 先配置审核公司：在上传页填写公司全称、税号，确认提交期限及住宿/招待/办公标准，保存成功后再选票；提交前重新核对服务端配置，变更或读取失败时保留文件并暂停提交。
2. 上传预检：支持 JPG、PNG、WebP，每批最多 20 张、单张最多 20 MB。选择与拖拽共用校验，先预览、删除，再提交；可选压缩，失败保留选择。
3. 异步审核：上传返回 HTTP 202 和批次号；SSE 逐张推送，批次区分 done、partial、failed，逐文件展示失败原因。
4. 证据展示：R0-R8 规则产生通过、存疑、驳回、转人工四类结论。有制度依据的规则关联条款，其余如实标注为技术检查。
5. 人工复核：保留原结论、目标结论、操作者、时间和理由，并同步列表与看板；不抹去原机器结论。
6. 制度问答：检索内置条款后回答并校验引用条号，无依据时说明制度未作规定；无文本模型时回退条款摘录。
7. 介绍与操作分离：`/` 展示发票地图、图群和 CTA；`/upload` 是操作入口，整页动画支持跳过、Esc 和重播。页面间保留过渡效果。

## 技术架构

| 层 | 实现 | 职责 |
| --- | --- | --- |
| 前端 | Next.js 14、React 18、TypeScript、Tailwind CSS、GSAP、Lenis | 上传、实时结果、轨迹、复核与交互动画 |
| API 与任务 | Python、FastAPI、Pydantic、SSE | 接口契约、异步批处理、异常隔离与进度 |
| AI 与规则 | OpenAI 兼容 HTTP 接口、结构化校验、规则引擎、条款检索 | 字段抽取、反馈重试、规则判断与问答 |
| 存储与部署 | SQLite、本地文件、nginx、systemd | 批次/发票/复核落库、反向代理与进程管理 |

前端请求集中于 `frontend/src/lib/api.ts`，类型与 `backend/app/schemas.py` 对齐。规则是业务结论的权威来源；可选 Function Calling 编排不覆盖规则结论。

## 目录

```text
backend/app/main.py           FastAPI 入口
backend/app/config.py         配置及 backend/.env 加载
backend/app/schemas.py        数据契约
backend/app/routers/          上传、结果、详情、历史、问答等 API
backend/app/services/         抽取、校验、规则、存储、复核与任务
backend/app/services/profile.py 公司档案；R3/R4/R5 的审核基准
backend/scripts/              数据生成、规则评测、识别对拍
backend/tests/                pytest 测试
backend/data/dataset/         60 张数据集与 ground_truth.json
frontend/src/app/             页面路由
frontend/src/components/      上传、导航、动画等组件
frontend/src/lib/             API、类型、压缩及展示工具
exports/                     历史识别导出证据
verification/                评测及前端验收记录
docs/                        技术文档、配置、接口与历史记录
deploy/                      nginx 与 systemd 配置
```

## 安装运行

本轮 Windows 后端复核使用 Python 3.14.3；现有前端验收环境为 Node.js 24.21.0 / npm 11.19.0。前端版本由 `package-lock.json` 锁定，后端直接依赖由 `requirements.txt` 固定。不要复用旧 ZIP 的虚拟环境或 node_modules。

### Windows PowerShell

在仓库根目录启动后端：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

保留后端，再开一个终端：

```powershell
cd frontend
Copy-Item .env.local.example .env.local
npm ci
npm run dev
```

打开 http://127.0.0.1:3100/upload 。先填写并保存审核公司的全称、税号及制度参数，再选择样例上传；未配置真实模型时结果标为 mock-vlm。固定“加载演示数据（5 张）”不要求公司配置，可直接体验。已有 `.env` 时核对配置，不要覆盖自己的密钥。

### macOS / Linux

将上述创建命令换为 `python3 -m venv .venv`，Python 路径换为 `.venv/bin/python`，复制命令换为 `cp`，前端命令相同。这些平台命令供复现参考，本轮重新执行的是 Windows 后端安装与测试。

### 模型和生产配置

仅在本机 `backend/.env` 填写 `VLM_API_KEY`、`VLM_BASE_URL`、`VLM_MODEL`，重启后端。服务须支持带图片输入的 OpenAI 兼容协议；文本问答与编排使用 `LLM_*`。示例模型名不是冻结评测的在线账户配置。

生产同源反代时，构建前设置 `NEXT_PUBLIC_API_BASE=` 空值；本地分端口用 `http://127.0.0.1:8000`。前端变量在构建时固化，禁止把密钥放入 `NEXT_PUBLIC_*`。完整配置见 `docs/环境配置与安装运行.md`。

## 页面

| 路由 | 用途 |
| --- | --- |
| `/` | 项目介绍；旧 `/#upload` 自动转向 `/upload` |
| `/upload` | 公司确认、上传、压缩选择与演示入口 |
| `/batches/{batchId}` | 审核结果及失败文件清单 |
| `/history` | 审核历史与来源核对 |
| `/invoices/{id}` | 字段、条款、轨迹和人工复核 |
| `/ask` | 制度问答 |
| `/dashboard` | 审核看板 |
| `/settings` | 独立的浅色公司设置页；从上传页进入，不另占主导航项 |

## 公司配置与适用范围

当前审核台共用一份公司档案，配置保存到 SQLite `app_settings`，不是浏览器本地标记或环境变量。已完成的记录不会自动重算，固定演示批次也不会改变；后续处理按当前档案执行，批次处理中应避免修改。前端上传前复查能够发现此前的配置变化，但不提供后端权限控制或批次配置快照。

R3 使用税额或税率为正值作为价税分离的启发式线索；购买方不匹配且缺少该线索时转人工，避免直接把没有抬头栏的票据判为抬头不符。这不是可靠的票种识别器，仍需人工核对原图。改写费用标准不会同步改写制度条款原文，页面会提示这一限制。

## 数据与评测

60 张数据集为 38 张合成票、12 张打印合成票后的实拍照片、10 张非发票。票据字段为虚构；合成图生成使用固定种子 20261106，实拍复现须使用已交付图片，不能声称重新拍摄会逐像素一致。规则评测固定 `2026-11-06`，按脚本规定初始化台账，并使用与 GT 一致的公司信息、提交期限和费用标准。

| 指标 | 结果 | 证据 |
| --- | --- | --- |
| 规则与 GT 一致性 | 独立/整批均结论 60/60、命中集合 60/60 | `docs/对拍结果.md`；冻结规则口径 |
| 11 字段识别 | 50 张发票全字段正确 44/50；单字段 544/550（98.9%） | `verification/recognition-11-fields-60.md/json` |
| 端到端结论 | 56/60（93.3%）；规则集合完全一致 54/60 | `verification/end-to-end-60.md/json` |

识别成绩来自已存档的 `deepseek-flash` / `openai-compat` 记录，本轮未重新调用模型。11 字段指标不包含 10 张非发票，缺失和失败保留在分母。历史端到端耗时 837 ms 包含 50 次缓存命中，不是实时模型平均延迟。

已知错例：ds_004、ds_005 的“公可”被模型纠正为“公司”，导致 reject→pass；real_06 年份误读导致 pass→suspect；ni_10 为 manual→reject。高置信度不等于正确，系统不能代替人工审批。详见 `docs/技术文档.md`、`docs/评测口径总表.md`。

## 验证

在仓库根目录执行：

```powershell
$env:PYTHONPATH='backend'
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe backend/scripts/eval_dataset.py --as-of 2026-11-06 --mode both
cd frontend
npx tsc --noEmit
npm run build
```

2026-11-16 对应用基线 `afc9e2a` 在独立 Python 3.14.3 / pytest 9.2.0 环境执行上述后端全量命令，结果为 **180 passed**；测试使用隔离存储、空模型密钥，不调用真实模型。测试数量须与代码基线、收集范围及执行环境一起引用，不沿用旧版本总数。前端整页入场证据见 `verification/upload-reveal-20261115/fullpage-check.json`；公司配置、上传前核对和动画回归见 `verification/company-setup-20261116/README.md`，浅色设置页及六项导航验收见该目录的 `light-settings.md`。这些流程检查使用隔离本地 mock，不代表真实识别准确率。本轮材料更新不改变应用代码。

## 团队

| 成员 | 分工 |
| --- | --- |
| A · 戴海青 | 后端接口、模型集成、规则引擎、制度问答、复核接口、部署与技术主讲 |
| B · 易子程 | 前端页面、上传与压缩、实时进度和轨迹、动画、移动端与联调 |
| C · 卢豪 | 数据集及 GT、打印实拍、识别对拍、评测报告和文档素材 |

团队名称：**序峰**；学校：**云南大学**。以上展示信息由团队成员于 2026-11-16 确认。

## 配置与素材边界

- 密钥只放私有环境；不提交 `.env`、数据库、上传原图、缓存、虚拟环境或 node_modules。
- 动画参考团队购买源码并适配。购买不等于任意公开再分发授权；开放仓库前核对授权范围，不将第三方动画宣称为团队原创。仓库未新增统一开源许可。
- 这是基于样例制度的比赛原型，不是对任意单位和票据的合规承诺。真实调用、缓存、模拟识别和固定演示须明确区分。
- 在线状态只代表检查时刻；评审仓库权限、服务和额度持续可用须由团队在提交前确认。
