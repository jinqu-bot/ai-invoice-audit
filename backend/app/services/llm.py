"""模型调用层。

只依赖「OpenAI 兼容协议」这一个事实标准：Qwen-VL、GPT-4o、豆包、本地 vLLM
都支持，换供应商只改 .env 里的 base_url 和 model，代码一行不动。

没配 key 时自动降级到 MockProvider——保证没有密钥也能把整条链路跑通、
前端也能联调，只是 provider 字段会明说是 mock。
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings


class ProviderError(Exception):
    """模型调用失败（网络、鉴权、限流、返回格式）。"""


@dataclass
class ChatResult:
    text: str
    provider: str
    model: str
    latency_ms: int


class VisionProvider(ABC):
    name: str = "base"
    model: str = ""

    @abstractmethod
    async def chat(self, messages: list[dict[str, Any]]) -> ChatResult: ...


# ------------------------------------------------------------------ 真实模型

class OpenAICompatVision(VisionProvider):
    """任何 OpenAI 兼容的视觉接口都能用。"""

    name = "openai-compat"

    def __init__(self) -> None:
        self.model = settings.vlm_model
        self.base = settings.vlm_base_url.rstrip("/")
        self.key = settings.vlm_api_key
        self.timeout = settings.vlm_timeout_s

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base}/chat/completions", headers=headers, json=payload
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(f"模型调用超时（{self.timeout}s）") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"模型调用网络错误：{exc}") from exc

        if resp.status_code >= 400:
            raise ProviderError(f"模型返回 HTTP {resp.status_code}：{resp.text[:300]}")

        try:
            return resp.json()
        except ValueError as exc:
            raise ProviderError("模型返回的不是合法 JSON") from exc

    async def chat(self, messages: list[dict[str, Any]]) -> ChatResult:
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 1600,
        }
        if settings.vlm_force_json:
            payload["response_format"] = {"type": "json_object"}

        try:
            data = await self._post(payload)
        except ProviderError as exc:
            # 有些供应商不支持 response_format，去掉重试一次
            if "response_format" in str(exc) and "response_format" in payload:
                payload.pop("response_format", None)
                data = await self._post(payload)
            else:
                raise

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"模型返回结构异常：{str(data)[:300]}") from exc

        # 少数供应商会把 content 返回成 [{type:text,text:...}]
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )

        return ChatResult(
            text=str(content),
            provider=self.name,
            model=self.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


# ------------------------------------------------------------------ 没有密钥时的替身

_MOCK_VARIANTS: list[dict[str, Any]] = [
    {
        "is_invoice": True,
        "invoice_code": "033002200111",
        "invoice_number": "24815631",
        "invoice_date": "2026-11-01",
        "seller_name": "杭州西溪宾馆有限公司",
        "seller_tax_id": "91330106MA2K7X1A2B",
        "buyer_name": "杭州云帆科技有限公司",
        "buyer_tax_id": "91330100MA2A1B2C3D",
        "amount_excl_tax": 641.51,
        "tax_amount": 38.49,
        "amount_incl_tax": 680.00,
        "tax_rate": 0.06,
        "category": "住宿",
        "items": [{"name": "住宿费", "amount": 641.51}],
        "confidence": {
            "overall": 0.97,
            "per_field": {
                "invoice_number": 0.99,
                "invoice_date": 0.98,
                "amount_incl_tax": 0.99,
                "seller_name": 0.96,
                "buyer_tax_id": 0.97,
            },
        },
    },
    {
        "is_invoice": True,
        "invoice_code": "033002200112",
        "invoice_number": "31027744",
        "invoice_date": "2026-10-30",
        "seller_name": "杭州鲜味餐饮管理有限公司",
        "seller_tax_id": "91330106MA2K7X2C3D",
        "buyer_name": "杭州云帆科技有限公司",
        "buyer_tax_id": "91330100MA2A1B2C3D",
        "amount_excl_tax": 337.74,
        "tax_amount": 20.26,
        "amount_incl_tax": 358.00,
        "tax_rate": 0.06,
        "category": "招待",
        "items": [{"name": "餐饮服务", "amount": 337.74}],
        "confidence": {
            "overall": 0.95,
            "per_field": {
                "invoice_number": 0.97,
                "invoice_date": 0.96,
                "amount_incl_tax": 0.98,
                "seller_name": 0.94,
                "buyer_tax_id": 0.95,
            },
        },
    },
    {
        "is_invoice": True,
        "invoice_code": "033002200113",
        "invoice_number": "44190582",
        "invoice_date": "2026-11-02",
        "seller_name": "滴滴出行科技有限公司",
        "seller_tax_id": "91110108MA0KX3E4F",
        "buyer_name": "杭州云帆科技有限公司",
        "buyer_tax_id": "91330100MA2A1B2C3D",
        "amount_excl_tax": 72.02,
        "tax_amount": 6.48,
        "amount_incl_tax": 78.50,
        "tax_rate": 0.09,
        "category": "交通",
        "items": [{"name": "客运服务", "amount": 72.02}],
        "confidence": {
            "overall": 0.96,
            "per_field": {
                "invoice_number": 0.98,
                "invoice_date": 0.97,
                "amount_incl_tax": 0.99,
                "seller_name": 0.95,
                "buyer_tax_id": 0.96,
            },
        },
    },
]


class MockVision(VisionProvider):
    """没有密钥时的替身：按图片指纹挑一个固定样例，结果可复现。

    它不是"假装 AI 成功"，而是让链路（压缩 → 调用 → 校验 → 缓存 → 前端）
    在没有任何密钥的情况下也能被完整验证。返回里 provider 会明确写 mock。
    """

    name = "mock-vlm"

    def __init__(self, seed: str = "") -> None:
        self.model = "mock-vlm-1"
        self.seed = seed

    async def chat(self, messages: list[dict[str, Any]]) -> ChatResult:
        started = time.perf_counter()
        index = int(self.seed[:8] or "0", 16) % len(_MOCK_VARIANTS) if self.seed else 0
        # 模拟一点真实延迟，让前端的"思考中"状态有东西可看
        await _sleep(0.35)
        return ChatResult(
            text=json.dumps(_MOCK_VARIANTS[index], ensure_ascii=False),
            provider=self.name,
            model=self.model,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)


# ------------------------------------------------------------------ 工厂

def get_provider(seed: str = "") -> VisionProvider:
    if settings.has_vlm:
        return OpenAICompatVision()
    return MockVision(seed=seed)


# ------------------------------------------------------------------ Prompt

SYSTEM_PROMPT = """你是一名财务票据识别引擎。你的唯一职责是"看图抄写"，把票面上的信息原样抄成结构化数据。

【硬性规则】
1. 只输出一个 JSON 对象。不要 markdown 代码块、不要解释、不要任何前后缀文字。
2. 每个字段都必须来自图片像素。看不清、被遮挡、图上没有 → 值填 null，并把该字段 confidence 设为 0.3 以下。
3. 严禁根据常识补全或推算金额。金额只从图上读，不要做加减乘除。
4. 日期统一 YYYY-MM-DD；金额为纯数字、两位小数，不带 ¥ 符号和千分位。
5. category 只能取下列之一：住宿 / 餐饮 / 交通 / 办公 / 招待 / 其他。
6. 如果图片根本不是发票（风景照、聊天截图、空白页），把 is_invoice 设为 false，其余字段全部 null。
7. 每个字段都要给 confidence（0~1），表示你在这一项上的把握；overall 取你最没把握的那一项的思路给。

【输出结构】
{
  "is_invoice": true,
  "invoice_code": "发票代码，字符串",
  "invoice_number": "发票号码，字符串",
  "invoice_date": "YYYY-MM-DD",
  "seller_name": "销售方名称",
  "seller_tax_id": "销售方纳税人识别号",
  "buyer_name": "购买方名称",
  "buyer_tax_id": "购买方纳税人识别号",
  "amount_excl_tax": 0.00,
  "tax_amount": 0.00,
  "amount_incl_tax": 0.00,
  "tax_rate": 0.06,
  "category": "住宿",
  "items": [{"name": "项目名称", "amount": 0.00}],
  "confidence": {
    "overall": 0.0,
    "per_field": {
      "invoice_number": 0.0,
      "invoice_date": 0.0,
      "amount_incl_tax": 0.0,
      "seller_name": 0.0,
      "buyer_tax_id": 0.0
    }
  }
}"""

USER_PROMPT = "请提取这张发票的全部要素，严格按约定结构输出 JSON。"


def build_messages(image_data_uri: str, user_text: str = USER_PROMPT) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": image_data_uri}},
            ],
        },
    ]


def retry_messages(
    base: list[dict[str, Any]], previous: str, errors: list[str]
) -> list[dict[str, Any]]:
    """把校验错误回灌给模型，让它只改这几处。"""
    issue = "\n".join(f"- {e}" for e in errors)
    return [
        *base,
        {"role": "assistant", "content": previous},
        {
            "role": "user",
            "content": (
                "你上一次的输出存在以下问题：\n"
                f"{issue}\n\n"
                "请回到图片上重新核对这几处，只修正上述问题，"
                "重新输出完整的 JSON 对象。不要解释，不要输出其它内容。"
            ),
        },
    ]
