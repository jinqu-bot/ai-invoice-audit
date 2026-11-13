# 数据集说明（DATASET.md）

> 本目录为 AI 报销审核台的正式测试数据集：**60 张、零隐私、可完全复现**。
> 全部发票图像均为合成数据（程序渲染 + 打印拍摄），企业名称、税号、金额均为虚构。

## 构成总览

| 构成 | 张数 | 文件前缀 | 说明 |
|---|---|---|---|
| 合成票 · 干净渲染 | 12 | `ds_001`–`ds_012` | Pillow 按增值税电子发票版式渲染（含 9 张埋雷母票） |
| 合成票 · 增广 | 23 | `ds_013`–`ds_035` | 噪声 10 / 旋转 8 / 折痕 5；子票继承母票字段、发票号码唯一化 |
| 合成票 · 转人工样例 | 3 | `ds_036`–`ds_038` | 见下表 |
| 实拍票 | 12 | `real_01`–`real_12` | 打印合成票 → 折叠 3 / 揉皱 6 / 平拍 3 → 手机拍摄（含闪光与顶灯样本） |
| 非发票 | 10 | `non_invoice_1/2`、`ni_03`–`ni_10` | 聊天截图、手写收据、投影、风景街景（ni_09/10 为程序生成） |

## 埋雷速查表（规则 ↔ 触发票）

| 规则 | 触发票 | 埋雷方式 |
|---|---|---|
| R1 重复报销 | `ds_003.png` | 发票号码 66472890 撞预置台账（BX-1102-007） |
| R2 必填缺失 | `ds_036.png`、`ds_037.png` | 号码区域留白 / 金额三件套缺失（GT 对应字段为 null） |
| R3 抬头不符 | `ds_004.png`（+增广子票） | 购买方故意错字"杭州云帆科技有限公**可**" |
| R4 超期提交 | `ds_006.png`、`ds_007.png`（+子票） | 开票日期早于基准日 30 天以上 |
| R5 超出标准 | `ds_001.png`（住宿 1280）、`real_01.jpg`（住宿 829.47） | 超 800 元/晚住宿标准 |
| R6 明细不符 | `ds_008.png`（+子票） | 明细合计 420 ≠ 不含税 471.70 |
| R7 税率异常 | `ds_002.png` | 住宿类目 13% 税率（法定外） |
| R8 敏感类目 | `ds_010.png`（"烟"）、`ds_011.png`（"酒水"）（+子票） | 项目名命中敏感词表 |
| R0 置信度不足 | `ds_038.png` | 关键字段区域马赛克，识别置信度低转人工 |

**无雷票**（expected_verdict = pass）：其余全部，`ground_truth.json` 逐条可查。

## ground_truth.json 字段约定

- 发票条目：InvoiceFields 全部字段 + `augment`（增广类型）+ `expected_verdict`（pass/suspect/reject/manual）+ `hit_rules`（命中的规则码）+ `eval_date`（评测基准日 **2026-11-06**）
- 非发票条目：`{"file", "is_invoice": false, "hit_rules": ["R0"], "expected_verdict": "manual"}`
- R2 样例的缺失字段为 `null`（不是空字符串）

## 复现三步

```bash
python backend/scripts/make_dataset.py     # 40 张合成批次（固定种子 20261106，逐字节一致）
python backend/scripts/make_to_print.py    # 打印素材 print_01–10 + gt
# 打印 → 折叠/揉皱 → 手机拍摄 → 命名 real_XX.jpg 并入本目录
python -m pytest backend/tests/test_dataset.py -v   # 13 项一致性校验，必须全绿
```

## 引用格式

> "60 张样本（38 合成 + 12 实拍 + 10 非发票，零隐私合成数据），识别字段级 544/550 = 98.9%，模型 deepseek-flash。"

引用规则口径、识别口径、端到端口径时，分别对照 `docs/评测口径总表.md` 的三个冻结数字，不得互推，不得引用已作废的旧数字（40/40、58/58、92.5%、55/60 等）。

## 关联文件

- 对拍工具：`backend/scripts/eval_dataset.py`（规则口径）、`backend/scripts/evaluate_accuracy.py`（识别字段）
- 识别报告：`verification/recognition-11-fields-60.md`、端到端 `verification/end-to-end-60.md`
- 数据层测试：`backend/tests/test_dataset.py`
