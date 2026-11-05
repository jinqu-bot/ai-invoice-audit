# AI 报销审核台

> 第九届传智杯 AI WEB 网页开发挑战赛 · 省赛
> 一句话定位：**不是帮你识别发票，是帮你决定这张发票该不该报——而且每个驳回都指得出制度第几条。**

---

## 现在到哪一步了

| 阶段 | 状态 | 说明 |
|---|---|---|
| D1 | ✅ 完成 | 后端 11 个接口 + **前端四个页面骨架**，全部返回假数据，跑得通 |
| D2 | ✅ 完成 | **识别链路是真的了**：图片压缩 → 视觉模型 → 四道关校验 → 置信度闸门 |
| D3 | 🟡 进行中 | 样例发票已能自动生成；C 的 40 张数据集（含噪声/旋转/折痕）待做 |
| D4 | ⬜ 待办 | 规则引擎 R1–R8 + 查重 |

> 每次推进都更新这张表。评委也会看 README。

---

## 目录结构

```
.
├── backend/                 后端（Python / FastAPI）
│   ├── app/
│   │   ├── main.py          入口，注册路由与错误处理
│   │   ├── config.py        配置（密钥只从环境变量读）
│   │   ├── schemas.py       ★ 前后端契约，所有返回结构都在这里
│   │   ├── services/        ★ 业务能力层（D2 起是真逻辑）
│   │   │   ├── image.py     图片指纹、压缩、转 base64
│   │   │   ├── llm.py       模型调用（OpenAI 兼容）+ 无密钥时的 mock
│   │   │   ├── validators.py 四道关：格式 / 金额勾稽 / 常识
│   │   │   ├── extract.py   ★ 抽取编排：重试、置信度、缓存
│   │   │   └── store.py     批次与图片的内存存储
│   │   ├── mock/
│   │   │   └── fixtures.py  演示批次假数据（?demo=true 用）
│   │   └── routers/         各接口模块
│   ├── scripts/
│   │   └── make_samples.py  生成样例发票图片（测试用）
│   ├── tests/               单元测试（pytest）
│   ├── data/samples/        样例发票 + ground_truth（脚本生成，不入库）
│   ├── requirements.txt     依赖锁版本
│   └── .env.example         环境变量模板（.env 不进仓库）
├── docs/
│   ├── API设计.md           接口清单，前端按这个开发
│   ├── D1完成报告.md        当日进度与分工
│   └── D2完成报告.md        识别链路做了什么、怎么验收
├── frontend/                前端（Next.js 14 + TypeScript + Tailwind）
│   └── src/
│       ├── app/             页面（App Router）
│       │   ├── page.tsx                 上传页
│       │   ├── batches/[batchId]/       审核结果页（含 SSE 进度）
│       │   ├── invoices/[invoiceId]/    发票详情页
│       │   └── dashboard/               审核看板
│       ├── components/      组件（卡片 / 轨迹 / 下拉上传 / 图表）
│       └── lib/
│           ├── types.ts     ★ 与 schemas.py 一一对应的类型
│           ├── api.ts       所有请求的唯一出口
│           └── sse.ts       审核进度流封装
└── README.md
```

---

## 快速开始（后端）

**1. 建虚拟环境并装依赖**（只需一次）

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r backend/requirements.txt
```

**2. 复制环境变量**

```bash
cp backend/.env.example backend/.env
# 现在不填也能跑：没配 VLM_API_KEY 时自动走 mock，链路照跑但 provider 会写 mock-vlm
```

> **`backend/.env` 会被自动加载**（`app/config.py` 里自带十几行解析，不依赖 python-dotenv），
> 启动命令不需要加 `--env-file`。
> 真实环境变量优先级更高——临时想换个模型，直接在命令行给值就行，不用改文件。

**3. 启动**

```bash
# 方式一：进目录再起（bash / zsh / PowerShell 都行）
cd backend
uvicorn app.main:app --reload --port 8000
```

```powershell
# 方式二：不进目录，一行搞定（Windows PowerShell 推荐这个）
uvicorn app.main:app --reload --port 8000 --app-dir backend
```

> ⚠️ **Windows PowerShell 5.1 不支持 `&&`**：写 `cd backend && uvicorn ...` 会报
> 「标记“&&”不是此版本中的有效语句分隔符」。改成换行、用 `;`，或者直接用方式二。

**4. 打开接口文档**

- Swagger（可以点按钮直接试）：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health

**5. 看演示数据长什么样**

```
http://127.0.0.1:8000/api/batches/B20261104-001/results
http://127.0.0.1:8000/api/invoices/INV-0005
```

---

## 快速开始（前端）

后端要先起来，前端才有数据。

```bash
cd frontend
npm install          # 只需一次
npm run dev          # http://127.0.0.1:3100
```

> **为什么是 3100 不是 3000？** 3000 常被别的程序占（本机就被 Grafana 占了），
> 起在 3000 会直接 `EADDRINUSE`。要改端口就改 `frontend/package.json` 里的 `-p`。

打开 http://127.0.0.1:3100 后，点「用演示数据体验（5 张）」就能看到完整效果。

**前端四个页面**

| 路由 | 页面 | 对应接口 |
|---|---|---|
| `/` | 上传发票 | `POST /api/batches` |
| `/batches/B20261104-001` | 审核结果（逐张点亮 + 轨迹） | `/results`（取数据）+ `/stream`（SSE 动画） |
| `/invoices/INV-0005` | 发票详情（字段/规则/条款/轨迹） | `/api/invoices/{id}` |
| `/dashboard` | 审核看板 | `/api/dashboard` |

**改代码前记住三条**

1. 所有请求都走 `src/lib/api.ts`，页面里不要写裸 `fetch`。
2. 后端字段变了，`src/lib/types.ts` 必须同步改（它和 `schemas.py` 一一对应）。
3. 结论颜色统一用 `VERDICT_META`（在 `src/lib/format.ts`），别在页面里自己挑颜色。

---

## 识别链路是怎么工作的（D2 核心）

一张图进来，走五步，任何一步不过关就转人工：

```
上传 → 压缩 → 模型抽取 → 四道关 → 置信度闸门 → 结论
        ↓         ↓          ↓           ↓
     指纹去重   严格 JSON   错误回灌重试   低于 0.8 转人工
```

**1. 压缩（`services/image.py`）**
手机照片动辄 5MB，直接扔给模型又慢又贵。统一缩到长边 1024、转 JPEG，
票面文字照样清楚，体积和延迟一起降下来。

**2. 抽取（`services/llm.py`）**
只认一个标准：**OpenAI 兼容协议**。Qwen-VL、GPT-4o、豆包、本地 vLLM 都能接，
换供应商只改 `.env` 里的 `base_url` 和 `model`，代码一行不动。

Prompt 里最要紧的是这三句：

> 每个字段都必须来自图片像素，看不清就填 null
> 严禁根据常识补全或推算金额
> 每项都要给 confidence，表示你在这项上的把握

**3. 四道关（`services/validators.py`）**

| 关卡 | 拦什么 |
|---|---|
| 格式关 | 必填字段在不在、类型对不对 |
| 算术关 | 不含税 + 税额 ≈ 价税合计（模型最爱在这翻车） |
| 常识关 | 日期不能是明年、税号不能 12 位、税率不能 7% |
| 把握关 | 关键字段置信度太低就转人工 |

前两关的错误会**回灌给模型重试**（`extract.py`），把"哪一处不对"告诉它，
让它只改这几处。这就是"输出稳定可控"的具体做法。

**4. 置信度为什么取最小值（`extract.py`）**
五个关键字段里四个 0.99、一个 0.3，取平均是 0.85 看着挺好，
但这张票实际不该被信任。**取最弱的那一项才诚实**，也是答辩时能讲清楚的取舍。

**5. 缓存（可选，`.env` 里 `EXTRACT_CACHE=true`）**
同一张图第二次进来直接命中，0ms 返回。演示时很重要——网络抖一下也不会翻车。

### 没有 API Key 也能跑

没配 `VLM_API_KEY` 时会自动降级到 **mock 提供者**：链路照跑，但结果里的
`provider` 会明写 `mock-vlm`。这不是"假装 AI 成功"，是让压缩、校验、重试、
缓存、前端联调这些环节在没有密钥时也能被完整验证。

配了真 key 之后：

```bash
# backend/.env
VLM_API_KEY=sk-xxxx
VLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
VLM_MODEL=qwen-vl-max
```

重启后端，`provider` 会变成 `openai-compat`，同一个接口不用改。

### 自己试一下

```bash
# 先生成三张样例发票（图片由脚本画出，不入库）
python backend/scripts/make_samples.py

# 识别单张
curl -X POST -F "file=@backend/data/samples/inv_001.png" http://127.0.0.1:8000/api/extract
```

也可以直接在 Swagger 里点：http://127.0.0.1:8000/docs

跑测试：

```bash
cd backend
python -m pytest          # 14 个用例，1.6 秒
```

---

## 演示批次说明（重要）

固定批次 `B20261104-001` 一共 5 张，对应演示脚本：

| 序号 | 编号 | 结论 | 埋的雷 |
|---|---|---|---|
| 1 | INV-0001 | 通过 | 住宿 680，未超 800 标准 |
| 2 | INV-0002 | 通过 | 招待人均 119.3，卡在 120 以内 |
| 3 | INV-0003 | 通过 | 市内交通，跳过条款检索 |
| 4 | INV-0004 | **存疑** | 住宿 1280，超标准 480 |
| 5 | INV-0005 | **驳回** | 已于 11-02 由张伟报销（BX-1102-007） |

历史批次 `B20261103-002` 另外 3 张，用来覆盖「抬头错 / 敏感类目 / 转人工」三种 UI 状态。

---

## 团队

| 代号 | 角色 | 负责 |
|---|---|---|
| A | 组长 · 后端 / AI | 接口、抽取、规则引擎、编排器、制度检索、技术文档 AI 章节、主讲 |
| B | 前端 | 全部页面、轨迹可视化、流式输出、动效与响应式 |
| C | 数据 / 文档 / 测试 | 发票生成器、数据集、测试用例、README、技术文档、演示视频 |

---

## 铁律

1. **每天提交一次**，commit 要能看出做了什么，不要最后一次性上传。
2. **`.env` 永不进仓库**，只提交 `.env.example`。
3. **D7 闭环、D11 冻结**：D7 后不加功能，D11 后只做材料。
4. 接口一改，先在群里说一声，再改 `schemas.py`。
5. 演示只用**被测过的**样例数据。
