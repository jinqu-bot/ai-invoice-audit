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
| 2 | POST | `/api/batches` | 上传一批发票 | B |
| 3 | GET | `/api/batches` | 批次列表 | B |
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
  "next_action": "/api/batches/B20261104-001/results"
}
```

> `next_action` 是给前端省的：拿到就直接打这个路径，不用拼字符串。
> **D2 起**：传了文件就真的逐张识别，返回新批次号（形如 `B20261105-001`）；
> `?demo=true` 仍返回固定演示批次 `B20261104-001`，答辩演示用这个最稳。

> 限制：一次最多 20 张；任何一张识别失败整批返回 502，不会静默丢单。

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
      "latency_ms": 210
    }
  ]
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
| `invoice_start` | 一张开始审 | `invoice_id` `seq` `total` `image_url` |
| `trace` | 一条轨迹 | `invoice_id` `step` `tool` `title` `reason` `status` `latency_ms` |
| `invoice_done` | 一张审完 | `invoice_id` `verdict` `headline` `confidence` `hit_rule_codes` |
| `batch_done` | 整批结束 | `batch_id` `elapsed_ms` `summary` |

**接入示例（伪代码）**

```js
const es = new EventSource(`${baseURL}/api/batches/${batchId}/stream`)
es.addEventListener('trace', (e) => {
  const step = JSON.parse(e.data)
  // 往轨迹面板按 step 顺序插一行；step.reason 这一栏一定要显示
})
es.addEventListener('batch_done', () => es.close())
```

**注意**

- 演示批次的流大约 **8–10 秒**跑完（D1 按真实耗时等比缩放）。
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
| `hit_rules` | 命中规则（编号/名称/等级/说明/证据） | 右侧「为什么」 |
| `citations` | 制度条款引用（文档名/第几条/原文/相关度） | 「依据」卡片，可展开原文 |
| `trace` | 审核轨迹数组 | 底部「它怎么审的」时间线 |
| `suggestions` | 给报销人的修改指引 | 驳回卡片的「怎么办」 |
| `missing_fields` | 没识别出来的关键字段名 | 复核表单据此留空，**不要填 0** |

**`trace` 里最重要的是 `reason` 字段**——它写的是「为什么做这一步」。这一栏是「可解释 Agent」的全部证据，**前端一定要显示出来**，不要只显示工具名。

**`status` 取值**：`ok` 通过 / `hit` 命中问题 / `miss` 未命中 / `skip` 主动跳过 / `warn` 待确认 / `error` 出错。
`skip` 尤其重要：它表示「我判断这里不用查」，是 Agent 会思考的证据。
`warn` 表示「跑完了但拿不准」，典型就是置信度不足转人工——它**不是错误**，别用红色。

> `fields` 里缺失的字段目前填的是 `0` 或空串（不让整页渲染崩），
> 「到底是 0 还是没识别到」看 `missing_fields`。人工复核表单必须用它。

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

---

## 8. 前端联调注意事项

1. **CORS 已全开**（`*`），本地 5173/3000 都能直连。
2. **图片是相对路径**，`image_url` 拼 baseURL；SVG 浏览器原生支持。
3. **不要做分页**，演示批次最多 5 张，一次全渲染。
4. **不要把 `verdict` 当唯一依据**，`manual_review` 为 `true` 时要单独提示。
5. **金额自己格式化**（后端给 `1280.0`，你要显示 `¥1,280.00`）。

---

## 9. 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 11-04 | v1.0 | D1 定稿，全部接口可用（假数据） |
| 11-05 | v1.1 | 新增 `POST /api/extract`、`GET /api/files/{id}.jpg`；错误码扩到 413/502 |
| 11-05 | v1.2 | `BatchSummary` 加 `provider`；`InvoiceDetail` 加 `missing_fields`；`trace.status` 增加 `warn`；422 补 `details`；**PDF 明确不做** |
| 11-05 | v1.3 | **D4：`verdict` 由规则引擎 R0–R8 算出**（不再是识别质量复读），`hit_rules` / `citations` 开始有真实内容；新增 `GET /api/rules` |

### 9.1 `verdict` 到底是谁给的（D4 起）

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

### 9.2 关于 PDF（B 提的第 1 条）

页面和文档以前写了支持 PDF，是错的——`batches.py` 只收 `image/*`。

**决定：第一版统一只收图片**，PDF 从文案和后端声明里都去掉，不许出现"支持 PDF"四个字。
理由：PDF 要引入渲染库（pypdfium2 / PyMuPDF）才能变成图像，多一个依赖、多一处出错，
而比赛演示和数据集都是图片。D11 冻结前如果剩余时间富余，再作为增强项补，届时先改契约再加实现。
