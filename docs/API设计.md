# 接口设计（前后端契约）

> 版本 v1.2 · D2 增补（新增 `/api/extract`、`/api/files`、`provider`、`missing_fields`）
> 规则：**这份文档改了要同步改 `backend/app/schemas.py`，并且在群里说一声。**
> 依据：`backend/app/schemas.py` 是唯一事实源，本文件是人话版。

---

## 0. 三条约定

**① 所有接口前缀 `/api`，返回 JSON，UTF-8。**

**② 金额单位是「元」，保留两位小数。** 不是分，不是千分位字符串。前端自己格式化。

**③ 错误统一长这样**，前端不用猜是 `detail` 还是 `message`：

```json
{ "code": "NOT_FOUND", "message": "发票不存在：INV-9999" }
```

| HTTP | code | 场景 |
|---|---|---|
| 400 | `BAD_REQUEST` | 参数不合法、没传文件、不是图片 |
| 404 | `NOT_FOUND` | 批次 / 发票 / 图片不存在 |
| 413 | `FILE_TOO_LARGE` | 单张超过 `UPLOAD_MAX_MB`（默认 20MB） |
| 422 | `VALIDATION_ERROR` | 请求体结构不对（缺必填字段、类型不对） |
| 502 | `UPSTREAM_ERROR` | 模型调用失败、识别结果不可解析 |
| 500 | `ERROR` | 服务端异常 |

422 比别的多一个 `details`，方便前端定位到是哪个格子填错了：

```json
{
  "code": "VALIDATION_ERROR",
  "message": "q：Field required",
  "details": [{ "field": "q", "reason": "Field required" }]
}
```

**④ 四个结论状态**（贯穿全部接口）：

| 值 | 中文 | 前端颜色建议 |
|---|---|---|
| `pass` | 通过 | 绿 |
| `suspect` | 存疑 | 黄 |
| `reject` | 驳回 | 红 |
| `manual` | 转人工 | 蓝 / 紫 |

> `manual` 是「我判断不了，交给人」——它和 `suspect` 的区别是：`suspect` 有明确依据但不合规；`manual` 是机器没把握。演示时这一张特别值钱。

---

## 1. 接口总表

| # | 方法 | 路径 | 用途 | 谁用 |
|---|---|---|---|---|
| 1 | GET | `/api/health` | 健康检查，确认后端通 | B |
| 2 | POST | `/api/batches` | 上传一批发票（D5 支持部分成功） | B |
| 3 | GET | `/api/batches?limit=&offset=` | 批次列表（D5 起分页） | B |
| 4 | GET | `/api/batches/{batch_id}` | 批次概要 | B |
| 5 | GET | `/api/batches/{batch_id}/results` | **审核结果（整页一次给全）** | B |
| 6 | GET | `/api/batches/{batch_id}/stream` | **审核进度流（SSE）** | B |
| 7 | GET | `/api/invoices/{invoice_id}` | 发票详情（字段/规则/引用/轨迹） | B |
| 8 | GET | `/api/policies` | 制度文档列表 | B |
| 9 | GET | `/api/policies/search?q=` | 条款检索 | B |
| 10 | GET | `/api/dashboard?month=` | 看板数据 | B |
| 11 | GET | `/api/mock/invoice-image/{invoice_id}.svg` | 占位发票图 | B |
| 12 | POST | `/api/extract` | **识别单张发票（D2 新增）** | B / 调试 |
| 13 | GET | `/api/files/{image_id}.jpg` | 回显用户上传的原图（D2 新增） | B |
| 14 | GET | `/api/rules` | **规则清单与制度依据（D4 新增）** | B / 评委 |
| 15 | POST | `/api/invoices/{invoice_id}/review` | **人工复核改判（D8）**，理由必填、改判留痕 | B |
| 16 | GET | `/api/policies/ask?q=&top_k=` | **制度问答（D8）**，只依据检索到的条款，答不出就说没有 | B |
| 17 | POST | `/api/invoices/{invoice_id}/agent-plan` | **模型自主决定查什么（11/11 新增）**，Function Calling 旁路 | B / 评委 |

> 17 是**旁路**：它只返回"模型想怎么查"的轨迹，**不改变这张票的结论**。
> 主链路（规则引擎）才是结论的唯一来源，那条路径确定、可复现、可测试。
> 没有配置真实模型时它返回 **503**——模拟模型不会做规划，我们不替它演。

---

## 2. 上传一支发票

```
POST /api/batches
Content-Type: multipart/form-data
```

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `files` | form | 否 | 多张图片，字段名固定为 `files`；**第一版只收图片**（JPG/PNG/WebP），PDF 见下方说明 |
| `demo` | query | 否 | `true` 时不传文件，直接返回演示批次（**联调期用这个**） |

**返回**

```json
{
  "batch_id": "B20261104-001",
  "invoice_count": 5,
  "created_at": "2026-11-04 19:50:12",
  "status": "done",
  "failed": [],
  "next_action": "/api/batches/B20261104-001/results"
}
```

> `next_action` 是给前端省的：拿到就直接打这个路径，不用拼字符串。
> **D2 起**：传了文件就真的逐张识别，返回新批次号（形如 `B20261105-001`）；
> `?demo=true` 仍返回固定演示批次 `B20261104-001`，答辩演示用这个最稳。

> 限制：一次最多 20 张。

**D6 起：上传变成两段式，状态码 202。**

`POST` 不再等审核跑完，而是**立刻**返回批次号，审核在后台逐张进行：

```json
{
  "batch_id": "B20261107-001",
  "invoice_count": 3,
  "created_at": "2026-11-07 16:12:40",
  "status": "processing",
  "failed": [],
  "next_action": "/api/batches/B20261107-001/results"
}
```

| 状态码 | 含义 | 前端该做什么 |
|---|---|---|
| **202** + `processing` | 已接单，正在后台审 | 跳结果页，订阅 `/stream`（或每秒轮询 `/results`） |
| **200** + `done` | `?demo=true`，现成的批次 | 直接展示，不用等 |

实测 POST 耗时 16ms（3 张票），之前要等 1.3 秒。`Location` 头给的是进度流地址。

> `processing` 期间 `invoice_count` 表示**待审张数**，跑完之后表示实际张数。
> 前端摆放骨架屏要用它，不要用 `items.length`（那个数量会一张张变）。
>
> **D5 起：部分成功。** 一张失败不再让整批失败——成功的照常入库，
> 失败的原样放在 `failed` 里：

```json
{
  "batch_id": "B20261106-001",
  "invoice_count": 2,
  "created_at": "2026-11-06 18:41:09",
  "status": "partial",
  "failed": [
    { "filename": "WeChat截图.png", "code": "BAD_IMAGE", "message": "不是图片文件（只收 JPG / PNG / WebP）" }
  ],
  "next_action": "/api/batches/B20261106-001/results"
}
```

`status` 四个值：`processing` 正在审、`done` 全成功、`partial` 部分成功、
`failed` 一张都没成功。
失败原因码见 §9.1。**全失败时也给批次号**，前端仍能打开结果页告诉用户哪张错了，
而不是只弹一个 toast。

---

## 2.1 识别单张发票（D2 新增）

```
POST /api/extract
Content-Type: multipart/form-data
```

| 参数 | 位置 | 必填 | 说明 |
|---|---|---|---|
| `file` | form | 是 | 单张图片，JPG / PNG |

**返回**（省略部分字段）

```json
{
  "extraction": {
    "extraction_id": "a1b2c3d4e5f6",
    "is_invoice": true,
    "fields": {
      "invoice_number": "24815631",
      "invoice_date": "2026-11-01",
      "seller_name": "杭州西溪宾馆有限公司",
      "amount_incl_tax": 680.0,
      "category": "住宿",
      "items": [{ "name": "住宿服务", "amount": 641.51 }]
    },
    "field_confidence": {
      "overall": 0.96,
      "per_field": { "invoice_number": 0.99, "amount_incl_tax": 0.99 }
    },
    "overall_confidence": 0.96,
    "verdict_hint": "pass",
    "validation": {
      "schema_ok": true,
      "arithmetic_ok": true,
      "sanity_ok": true,
      "errors": [],
      "warnings": []
    },
    "provider": "openai-compat",
    "model": "qwen-vl-max",
    "cached": false,
    "retry_count": 0,
    "latency_ms": 1420,
    "image": {
      "sha256": "…",
      "original_bytes": 1834210,
      "compressed_bytes": 214882,
      "width": 786,
      "height": 1024,
      "mime": "image/jpeg"
    }
  },
  "image_url": "/api/files/4a53237e6d0b48d8.jpg"
}
```

**几个字段的含义，前端别理解错：**

| 字段 | 含义 |
|---|---|
| `verdict_hint` | **只看识别质量**的初判，还没跑规则引擎。`manual` = 机器没把握 |
| `overall_confidence` | 取**最没把握的关键字段**，不是平均值 |
| `cached` | `true` 表示命中缓存，`latency_ms` 会很小 |
| `retry_count` | 校验不过回灌重试的次数，`1` 表示重试过一次才对 |
| `provider` | 没配密钥时是 `mock-vlm`，页面上可以据此提示"演示模式" |
| `image` | 压缩前后的字节数，可以用来展示"省了多少带宽" |

---

## 3. 审核结果（结果页一次拿全）

```
GET /api/batches/{batch_id}/results
```

**返回**

```json
{
  "batch": {
    "batch_id": "B20261104-001",
    "created_at": "2026-11-04 09:12:38",
    "invoice_count": 5,
    "status": "done",
    "total_amount": 2876.5,
    "pass_count": 3,
    "suspect_count": 1,
    "reject_count": 1,
    "manual_count": 0,
    "elapsed_ms": 5230,
    "provider": "fixture"
  },
  "items": [
    {
      "invoice_id": "INV-0005",
      "batch_id": "B20261104-001",
      "seq": 5,
      "image_url": "/api/mock/invoice-image/INV-0005.svg",
      "verdict": "reject",
      "headline": "该发票已于 11-02 由张伟报销",
      "seller_name": "杭州老码头餐饮管理有限公司",
      "invoice_number": "66472890",
      "invoice_date": "2026-10-28",
      "amount_incl_tax": 486.0,
      "category": "餐饮",
      "confidence": 0.98,
      "manual_review": false,
      "hit_rule_codes": ["R1"],
      "latency_ms": 210,
      "filename": "IMG_2043.png"
    }
  ],
  "failures": []
}
```

**字段说明**

| 字段 | 说明 |
|---|---|
| `headline` | **卡片上那句话**，直接用，别自己拼 |
| `seq` | 批内序号，排序用它，别用时间 |
| `image_url` | 相对路径，拼上 baseURL 即可 |
| `hit_rule_codes` | 命中的规则编号，用于显示红点/标签 |
| `confidence` | 0–1，低于 0.8 时建议在卡片上提示 |
| `manual_review` | `true` 必须人工过一眼，别只靠 `verdict` 判断 |
| `filename` | 用户上传时的原始文件名（D5），"你传的是哪张" |
| `failures` | 这一批没处理成功的文件（D5），逐条显示，别吞掉 |
| `provider` | 这一批实际的识别来源：`mock-vlm`（没配 key，演示模式）/ `openai-compat`（真模型）/ `mixed`（一批里混了）/ `fixture`（固定演示数据） |

> `provider` 放在 `batch` 里，卡片和详情不再需要从 `trace[].args` 里挖。
> **只要不是 `openai-compat`，页面上就该有一行小字说明当前不是真模型**——这不丢人，装成真模型才丢人。

---

## 4. 审核进度流（SSE）

```
GET /api/batches/{batch_id}/stream
```

`Content-Type: text/event-stream`。前端用 `EventSource` 监听，**事件名就是 `type`**。

| 事件 | 时机 | data 关键字段 |
|---|---|---|
| `hello` | 订阅成功 | `batch_id` `replay`（`true` = 回放，`false` = 正在发生） |
| `batch_start` | 整批开始 | `batch_id` `total` `failed` |
| `invoice_start` | 一张开始审 | `invoice_id` `seq` `total` `image_url` `filename` |
| `trace` | 一条轨迹 | `invoice_id` `step` `tool` `title` `reason` `status` `latency_ms` |
| `file_failed` | 某个文件当场失败 | `filename` `code` `message` |
| `invoice_done` | 一张审完 | `invoice_id` `verdict` `headline` `confidence` `hit_rule_codes` |
| `batch_done` | 整批结束 | `batch_id` `elapsed_ms` `summary` |

**D6 起这条路是真进度**：每审完一张就推一张，`invoice_done` 之间隔着真实的识别耗时
（实测 mock 下约 400ms/张）。

**`replay` 这个字段要当真**：

- 正在跑的批次 → `replay: false`，事件随时到；
- 已经跑完的批次（演示批次、历史批次、页面刷新后重播）→ `replay: true`，
  服务端按存下来的轨迹回放。**这一路是放映，不是直播**，页面上要标出来。

**接入示例（伪代码）**

```js
const es = new EventSource(`${baseURL}/api/batches/${batchId}/stream`)
es.addEventListener('hello', (e) => setReplay(JSON.parse(e.data).replay))  // 别把回放当实时
es.addEventListener('trace', (e) => {
  const step = JSON.parse(e.data)
  // 往轨迹面板按 step 顺序插一行；step.reason 这一栏一定要显示
})
es.addEventListener('invoice_done', () => refreshResults())  // 数据仍以 /results 为准
es.addEventListener('batch_done', () => es.close())
```

**注意**

- **SSE 只负责"有变化了"，具体数字去 `/results` 拿**。两套状态各算一遍必然对不上，
  前端只要收到 `invoice_done` 就刷一次接口，简单且不会错。
- `processing` 期间 `/results` 可以正常调用，`items` 会一张张变多——
  **这就是 SSE 断掉时的兜底**（现场网络、企业代理都可能掐流）。
- 演示批次的流大约 **8–10 秒**跑完（按真实耗时等比缩放，这一路是设计好的回放）。
- 如果前端用了 Vite 代理，注意关掉响应缓冲，否则 SSE 会被攒成一坨。

---

## 5. 发票详情

```
GET /api/invoices/{invoice_id}
```

在卡片字段基础上，多返回 4 块：

| 字段 | 内容 | 用在哪 |
|---|---|---|
| `fields` | 12 个识别字段 + 明细行 | 详情页左侧「结构化结果」 |
| `field_confidence` | 整体 + 逐字段置信度 | 低置信度字段标黄 |
| `hit_rules` | 命中规则（编号/名称/等级/说明/证据/**依据条款**） | 右侧「为什么」 |
| `citations` | 制度条款引用（文档名/第几条/原文/相关度） | 「依据」卡片，可展开原文 |
| `trace` | 审核轨迹数组 | 底部「它怎么审的」时间线 |
| `suggestions` | 给报销人的修改指引 | 驳回卡片的「怎么办」 |
| `missing_fields` | 没识别出来的关键字段名 | 复核表单据此留空，**不要填 0** |
| `cached` | 这次结论是否**直接取自识别缓存** | 详情页顶部标记，别把缓存说成"模型很快" |
| `reviews` | 人工复核轨迹（按时间正序） | 复核面板 |
| `reviewed` | 是否被改判过 | 列表页「已复核」角标 |

### 5.1 `hit_rules` 里的依据条款（11/11 补）

以前条款只挂在页面底部的 `citations` 列表里，**一条票同时命中 R3+R4 时看不出哪条对应哪一款**。
现在每条命中自带自己的依据：

```json
{
  "code": "R3",
  "name": "抬头或税号不符",
  "level": "reject",
  "detail": "购买方名称为「臧海涛」，应为「杭州云帆科技有限公司」",
  "evidence": { "actual_name": "臧海涛" },
  "basis_doc": "差旅费管理办法",
  "basis_article": "第 8 条",
  "basis_text": "报销发票的购买方名称及纳税人识别号必须与公司登记信息完全一致……"
}
```

**`basis_article` 为 `null` 是有意义的，不是漏了**：R0/R1/R2/R6/R7 这些规则制度里本来就没写条款
（比如查重，依据是台账事实）。**我们不为了界面好看给它编一个条号。**
前端遇到 `null` 不要显示空白，要显示"制度未规定，依据票面/台账事实"。

### 5.2 `cached` 这个字段要当真

同一张图传第二次会命中识别缓存（省钱），几百毫秒甚至几毫秒就出结果。
**几毫秒出结果不等于模型变快了**。所以详情页必须把两种状态分开说：

- `cached: false` → 「本次真实调用模型 · deepseek-flash · 用时 5.3 秒」
- `cached: true` → 「识别缓存命中 · 这次没有调用模型」

要演真读图，先跑 `reset_demo.py --flush-cache` 清缓存。

**`trace` 里最重要的是 `reason` 字段**——它写的是「为什么做这一步」。这一栏是「可解释 Agent」的全部证据，**前端一定要显示出来**，不要只显示工具名。

**`status` 取值**：`ok` 通过 / `hit` 命中问题 / `miss` 未命中 / `skip` 主动跳过 / `warn` 待确认 / `error` 出错。
`skip` 尤其重要：它表示「我判断这里不用查」，是 Agent 会思考的证据。
`warn` 表示「跑完了但拿不准」，典型就是置信度不足转人工——它**不是错误**，别用红色。

> `fields` 里缺失的字段目前填的是 `0` 或空串（不让整页渲染崩），
> 「到底是 0 还是没识别到」看 `missing_fields`。人工复核表单必须用它。

---

## 5.3 让模型自己决定查什么（11/11 新增）

```
POST /api/invoices/{invoice_id}/agent-plan
```

把三个工具交给模型，由它决定**调哪个、按什么顺序**，每次调用的参数和返回都记下来。

**三个工具都是真数据，没有一个是编的：**

| 工具 | 干什么 | 落到哪 |
|---|---|---|
| `check_duplicate` | 查这张票的号码在台账里出现过没有 | `history.find`（真 SQLite） |
| `search_policy` | 按问题检索制度条款 | `policy_qa.retrieve`（真制度库） |
| `get_threshold` | 取某个费用类目的报销上限 | `rules.LIMITS`（真配置） |

**返回：**

```json
{
  "provider": "openai-compat",
  "model": "deepseek-flash",
  "steps": [
    {
      "index": 1,
      "tool": "check_duplicate",
      "label": "查重",
      "args": { "invoice_number": "66472890" },
      "result": { "ok": true, "hit": true, "reimbursement_no": "BX-1102-007" },
      "latency_ms": 2,
      "by": "model"
    }
  ],
  "summary": "这张票的号码在台账里出现过，建议驳回并核对原票。",
  "fallback": false,
  "rounds": 2,
  "latency_ms": 4210
}
```

**`by` 这个字段是这一层的良心：**

- `model` = 这一步是模型自己选的（顺序、参数都照它给的来）
- `fallback` = **模型一次工具都没调**（或者压根不会用工具），已退回固定顺序「查重 → 检索制度」

前端必须把 `fallback` 显式标出来（黄色徽标「模型未给出工具调用 · 已退回固定顺序」）。
**否则就是把兜底顺序包装成"AI 在规划"，那是唬评委。**

**三条硬约束：**

1. **不改结论**。这一层只出轨迹；这张票是 pass 还是 reject，仍然由规则引擎算。
2. **没有真模型就 503**。模拟模型是"钉住输出"的替身，让它假装规划等于演。
3. **叫不出名字的工具如实报错**（`{"ok": false, "reason": "没有这个工具：xxx"}`），不假装调过。

**错误：**

| 码 | 含义 |
|---|---|
| 404 | 发票不存在 |
| 502 | 模型调用失败（超时/HTTP 错误），**主链路不受影响** |
| 503 | 没有配置真实模型 key |

---

## 6. 制度库

```
GET /api/policies
GET /api/policies/search?q=住宿超标了怎么办&top_k=3
```

检索返回：

```json
{
  "query": "住宿超标",
  "clauses": [
    {
      "doc_id": "P-TRAVEL",
      "doc_title": "差旅费管理办法",
      "article_no": "第 12 条",
      "text": "一线城市住宿费标准为每人每晚 800 元，超出部分需经部门总监审批后方可报销。",
      "score": 0.93
    }
  ]
}
```

> D1 是关键词粗筛，只为让前端先把「出处卡片」画出来。D8 换成向量检索后，**接口和字段完全不变**。

---

## 7. 看板

```
GET /api/dashboard?month=2026-11
```

返回：本月总量/总额/通过率、驳回原因 TOP5、部门分布、类目分布、供应商 TOP、金额区间、每日趋势。

字段名注意：`by_supplier` 里也用的是 `dept` 键（历史原因，D2 会改成 `name`，**现在先按 `dept` 取**）。

### 7.1 `source` 必须看（11/11 改）

以前这个接口**永远**返回 fixtures 的 128 张 / 18.6 万，而库里其实是 0 张——
结果页说 5 张、看板说 128 张，评委点一下就看穿。

现在：

| `source` | 含义 | 前端怎么做 |
|---|---|---|
| `db` | 库里**真实审核过**的票聚合出来的 | 显示「真实聚合」，和结果页、详情页是同一份数据 |
| `fixture` | 库里没有这个月的票，退回演示样例 | **必须标注「数据为演示样例」**，不能让假数据冒充真数据 |

另外：库里没有部门字段，`source=db` 时 `by_department` **返回空数组**，界面显示「暂无数据」。
**不编一个部门分布出来**——这是原则问题，不是能力问题。

---

## 8. 前端联调注意事项

1. **CORS 已全开**（`*`），本地 5173/3000 都能直连。
2. **图片是相对路径**，`image_url` 拼 baseURL；SVG 浏览器原生支持。
3. **批次列表要分页**（D5 改了形状：`{total, limit, offset, items}`）。结果页仍是"一次全渲染"，不用分页。
4. **不要把 `verdict` 当唯一依据**，`manual_review` 为 `true` 时要单独提示。
5. **金额自己格式化**（后端给 `1280.0`，你要显示 `¥1,280.00`）。
6. **`failed` / `failures` 不能吞**：那是用户传了但没处理成功的文件，静默丢掉等于骗人。

---

## 9. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 11-04 | v1.0 | D1 定稿，全部接口可用（假数据） |
| 11-05 | v1.1 | 新增 `POST /api/extract`、`GET /api/files/{id}.jpg`；错误码扩到 413/502 |
| 11-05 | v1.2 | `BatchSummary` 加 `provider`；`InvoiceDetail` 加 `missing_fields`；`trace.status` 增加 `warn`；422 补 `details`；**PDF 明确不做** |
| 11-05 | v1.3 | **D4：`verdict` 由规则引擎 R0–R8 算出**（不再是识别质量复读），`hit_rules` / `citations` 开始有真实内容；新增 `GET /api/rules` |
| 11-06 | v1.4 | **D5：部分成功 + 落库 + 分页**。上传返回 `status` / `failed`；结果多 `failures`；卡片多 `filename`；`GET /api/batches` 改为 `{total,limit,offset,items}`；`status` 增加 `partial` |
| 11-11 | v1.5 | **`hit_rules` 每条自带 `basis_doc` / `basis_article` / `basis_text`**（null 表示制度未规定，别显示空白）；卡片与详情新增 `cached`（缓存命中 ≠ 模型变快）；看板新增 `source`（db/fixture）；新增 `POST /api/invoices/{id}/agent-plan`（Function Calling，旁路不改结论，无真模型时 503） |

### 9.1 部分成功、落库与分页（D5）

**① 一张失败不再让整批失败。** 以前第 3 张是微信截图，前两张的成功结果一起丢；
现在逐张处理，失败的进 `failed`，成功的照常入库，批次状态 `partial`。
全失败也给批次号（`failed`），这样才能打开结果页说清"哪张错了、为什么"。

| 失败码 | 含义 |
|---|---|
| `BAD_IMAGE` | 不是图片，或图片打不开 |
| `EMPTY_FILE` | 空文件 |
| `FILE_TOO_LARGE` | 超过 10MB |
| `EXTRACT_FAILED` | 识别这一步失败（模型报错/重试后仍不合法） |

**② 数据落进 SQLite**（`backend/data/app.db`）。批次、发票、台账、批次号序号都在库里，
重启后端还能打开历史批次。**台账落库尤其重要**：以前重启就等于把"已报销过"的记录洗白，
R1 重复报销形同虚设。

**③ 批次列表分页**：

```
GET /api/batches?limit=20&offset=0
→ { "total": 37, "limit": 20, "offset": 0, "items": [...] }
```

排序：`created_at` 倒序，同一时间按 `batch_id` 倒序（保证翻页不重不漏）。
`limit` 上限 100，`limit=0` 或 `offset<0` 返回 422。演示批次始终在列表里。

### 9.2 `verdict` 到底是谁给的（D4 起）

以前 `verdict` 是抽取阶段的"识别质量初判"，只有 `pass` 和 `manual` 两种，
**那是错的说法**：识别得清楚不等于这张票能报。

现在 `verdict` 由规则引擎给，四种结论各有明确来源：

| verdict | 什么时候出现 | 依据 |
|---|---|---|
| `reject` | 重复报销（R1）、抬头或税号不符（R3） | 台账事实 / 差旅费办法第 8 条 |
| `manual` | 置信度不足（R0）、要素缺失（R2）、不是发票 | 机器没把握 |
| `suspect` | 超标准（R5）、超期（R4）、明细不符（R6）、税率异常（R7）、敏感类目（R8） | 对应条款 |
| `pass` | 以上都没命中 | — |

结论优先级：`reject` > `manual` > `suspect` > `pass`。事实压过不确定，不确定压过可补救。

### 9.3 上传改成两段式（D6）

`POST /api/batches` 从 `200 + done` 改成 **`202 + processing`**，审核挪到后台任务。
`?demo=true` 仍是 `200 + done`。

新增三种 SSE 事件：`hello`（带 `replay` 标志）、`batch_start`、`file_failed`。
另外 `processing` 期间 `/results` 可用，作为 SSE 断掉时的兜底。

为什么不直接在原来的同步接口里"边跑边推"：那需要把响应头先发出去再持续写，
等价于自己实现一遍流式响应，比拆成 202 + SSE 更容易出幺蛾子。见 `D6完成报告.md`。

### 9.4 关于 PDF（B 提的第 1 条）

页面和文档以前写了支持 PDF，是错的——`batches.py` 只收 `image/*`。

**决定：第一版统一只收图片**，PDF 从文案和后端声明里都去掉，不许出现"支持 PDF"四个字。
理由：PDF 要引入渲染库（pypdfium2 / PyMuPDF）才能变成图像，多一个依赖、多一处出错，
而比赛演示和数据集都是图片。D11 冻结前如果剩余时间富余，再作为增强项补，届时先改契约再加实现。
