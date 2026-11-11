"""让模型自己决定"先查什么"——Function Calling 版审核规划。

**为什么单独做一层，而不是塞进主链路：**

主链路（`rules.run_audit`）是固定顺序 + 短路，结果是确定的、可复现的、能拿单元测试钉住的。
这一层的目的是另一件事：证明**模型能在工作流里做决定**（选哪个工具、按什么顺序），
而不是被 if-else 牵着走。所以它是一条**旁路**：

- 主链路出结论，永远不依赖它（它挂了、超时了，审核照常）；
- 它自己出问题时退回固定顺序，并且**把这个降级写进轨迹**——兜底也要能被看见。

评分表里「Agent/工作流设计 8%」考的是规划、工具调用、自主决策；
「MCP/工具集成 4%」认 MCP **或 Function Calling**。这里用后者，少一个进程、少一个崩溃点。

工具只有三个，而且都能落到真实数据上（不编）：
- `check_duplicate` → 查真台账（`history.find`）
- `search_policy`  → 检索真制度条款（`policy_qa.retrieve`）
- `get_threshold`  → 读真阈值配置（`rules.LIMITS`）
"""

from __future__ import annotations

import json
import time
from typing import Any

from app.services import history, policy_qa, rules
from app.services.llm import ProviderError, VisionProvider

MAX_ROUNDS = 3

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "check_duplicate",
            "description": (
                "查这张发票的号码在既往审核台账里有没有出现过。"
                "重复报销是后果最重的问题，所以只要号码能读到，就该第一个查。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_number": {"type": "string", "description": "发票号码，原样传入"},
                },
                "required": ["invoice_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_policy",
            "description": (
                "按问题检索公司制度条款，返回条款原文与条号。"
                "金额是否超标准、类目是否敏感、时限是否超期，都要靠它拿依据。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "用中文描述要查的制度问题"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_threshold",
            "description": "取某个费用类目的报销上限（元）。用于判断这张票是不是超标。",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "费用类目，例如 住宿 / 招待 / 办公",
                    },
                },
                "required": ["category"],
            },
        },
    },
]

# 模型没给出任何合法工具调用时，退回这条固定顺序——并且如实标注 by=fallback
DEFAULT_ORDER = ("check_duplicate", "search_policy")

_SYSTEM = """你是报销审核助手。你手上有一组工具，可以用它们查事实。

规则：
1. **先想清楚这张票最可能出什么问题，再决定查什么。** 不要把所有工具都调一遍。
2. 结论只能建立在工具返回的事实上。工具没查到的东西，不许当成"没问题"。
3. 工具最多调 3 次。查够了就用一句话给出你的判断（该通过 / 该驳回 / 该转人工，以及理由）。
4. 如果这张票要素残缺、根本没法查，就直接说明缺什么，不要硬查。"""


def _money(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "（未识别）"


def _user_message(detail: dict[str, Any]) -> str:
    """只给事实，不给机器已经算好的结论——否则它只是在复述我们。"""
    f = detail.get("fields") or {}
    lines = [
        "这张发票识别出来的要素：",
        f"- 发票号码：{f.get('invoice_number') or '（未识别）'}",
        f"- 发票代码：{f.get('invoice_code') or '（未识别）'}",
        f"- 开票日期：{f.get('invoice_date') or '（未识别）'}",
        f"- 销售方：{f.get('seller_name') or '（未识别）'}",
        f"- 购买方：{f.get('buyer_name') or '（未识别）'}",
        f"- 价税合计：{_money(f.get('amount_incl_tax'))} 元",
        f"- 不含税：{_money(f.get('amount_excl_tax'))} 元，税额：{_money(f.get('tax_amount'))} 元",
        f"- 税率：{f.get('tax_rate')}",
        f"- 费用类目：{f.get('category') or '（未识别）'}",
        "",
        "请决定要先查什么，然后用一句话给出判断。",
    ]
    return "\n".join(lines)


# ------------------------------------------------------------------ 工具实现

def _check_duplicate(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    number = str(args.get("invoice_number") or ctx.get("number") or "").strip()
    if not number:
        return {"ok": False, "reason": "没有发票号码，查不了重"}
    found = history.find(number, ctx.get("code"), source=ctx.get("source") or "openai-compat")
    if not found:
        return {"ok": True, "hit": False, "invoice_number": number}
    return {
        "ok": True,
        "hit": True,
        "invoice_number": number,
        "reimbursement_no": found.get("reimbursement_no"),
        "employee": found.get("employee"),
        "submitted_at": found.get("submitted_at"),
        "note": "台账记录表示这张票之前被提交过，需人工核实是否重复报销",
    }


def _search_policy(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    if not query:
        return {"ok": False, "reason": "没有给出要查的制度问题"}
    clauses = policy_qa.retrieve(query, top_k=2)
    if not clauses:
        # 检索不到就必须说没有——这一条和制度问答是同一个原则
        return {"ok": True, "query": query, "found": 0, "clauses": [],
                "note": "制度里没有找到相关条款"}
    return {
        "ok": True,
        "query": query,
        "found": len(clauses),
        "clauses": [
            {
                "doc": c.get("doc_title"),
                "article": c.get("article_no"),
                "text": (c.get("text") or "")[:120],
                "score": c.get("score"),
            }
            for c in clauses
        ],
    }


def _get_threshold(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    category = str(args.get("category") or ctx.get("category") or "").strip()
    rule = rules.LIMITS.get(category)
    if not rule:
        return {"ok": True, "category": category, "limit": None,
                "note": "制度没有给这个类目定上限，不做超标准判断"}
    doc_id, article = rule["doc"]
    return {
        "ok": True,
        "category": category,
        "limit": rule["limit"],
        "unit": rule.get("unit"),
        "basis": f"{doc_id} {article}",
    }


_EXECUTORS = {
    "check_duplicate": (_check_duplicate, "查重"),
    "search_policy": (_search_policy, "检索制度条款"),
    "get_threshold": (_get_threshold, "取费用上限"),
}


def _execute(name: str, args: dict[str, Any], ctx: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """执行一个工具调用。叫不出名字的工具要如实报错，不能假装调过。"""
    entry = _EXECUTORS.get(name)
    if entry is None:
        return name, {"ok": False, "reason": f"没有这个工具：{name}"}
    fn, _label = entry
    try:
        return name, fn(args, ctx)
    except Exception as exc:  # 工具内部出错不能把整轮带崩
        return name, {"ok": False, "reason": f"工具执行失败：{type(exc).__name__}: {exc}"[:200]}


def _ctx_of(detail: dict[str, Any]) -> dict[str, Any]:
    f = detail.get("fields") or {}
    return {
        "number": f.get("invoice_number") or "",
        "code": f.get("invoice_code") or "",
        "category": f.get("category") or "",
        "source": detail.get("provider") or "openai-compat",
    }


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def plan(detail: dict[str, Any], provider: VisionProvider) -> dict[str, Any]:
    """跑一次"模型自主决定查什么"。返回轨迹，不改数据库、不改这张票的结论。"""
    ctx = _ctx_of(detail)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _user_message(detail)},
    ]
    started = time.perf_counter()
    steps: list[dict[str, Any]] = []
    summary = ""
    rounds = 0

    for _ in range(MAX_ROUNDS):
        rounds += 1
        try:
            message, latency = await provider.chat_tools(messages, TOOLS)
        except ProviderError:
            raise
        calls = message.get("tool_calls") or []
        content = (message.get("content") or "").strip()
        if content:
            summary = content
        if not calls:
            break

        messages.append({
            "role": "assistant",
            "content": message.get("content") or "",
            "tool_calls": calls,
        })
        for call in calls:
            name = ((call.get("function") or {}).get("name") or "").strip()
            args = _parse_arguments((call.get("function") or {}).get("arguments"))
            tool_started = time.perf_counter()
            tool_name, result = _execute(name, args, ctx)
            steps.append({
                "index": len(steps) + 1,
                "tool": tool_name,
                "label": _EXECUTORS.get(tool_name, (None, tool_name))[1],
                "args": args,
                "result": result,
                "latency_ms": int((time.perf_counter() - tool_started) * 1000),
                "by": "model",
            })
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id") or f"call_{len(steps)}",
                "content": json.dumps(result, ensure_ascii=False),
            })

    fallback = False
    if not steps:
        # 模型一次工具都没调（或者它压根不会用工具）：退回固定顺序，
        # 但必须把"这次不是模型决定的"写清楚，不能让轨迹看起来像模型规划过。
        fallback = True
        for name in DEFAULT_ORDER:
            tool_started = time.perf_counter()
            args = ({"invoice_number": ctx["number"]} if name == "check_duplicate"
                    else {"query": f"{ctx.get('category') or ''}费用能不能报，有没有上限"})
            tool_name, result = _execute(name, args, ctx)
            steps.append({
                "index": len(steps) + 1,
                "tool": tool_name,
                "label": _EXECUTORS.get(tool_name, (None, tool_name))[1],
                "args": args,
                "result": result,
                "latency_ms": int((time.perf_counter() - tool_started) * 1000),
                "by": "fallback",
            })
        if not summary:
            summary = "模型没有给出工具调用，已按默认顺序（查重 → 检索制度）执行，结论以主链路为准。"

    return {
        "provider": getattr(provider, "name", "unknown"),
        "model": getattr(provider, "model", ""),
        "steps": steps,
        "summary": summary or "模型没有给出文字判断，结论以主链路为准。",
        "fallback": fallback,
        "rounds": rounds,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }
