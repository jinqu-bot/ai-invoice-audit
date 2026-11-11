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
from app.services import model_health


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

    async def chat_tools(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], int]:
        """带工具的一次对话，返回模型原始 message（可能含 tool_calls）和耗时。

        只有真模型能调工具：Mock 是"钉住输出"的替身，让它假装规划等于演。
        子类不实现就抛 ProviderError，调用方据此降级。
        """
        raise ProviderError("当前模型不支持函数调用（需要配置真实的视觉模型）")


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
            model_health.record_failure(f"模型调用超时（{self.timeout}s）")
            raise ProviderError(f"模型调用超时（{self.timeout}s）") from exc
        except httpx.HTTPError as exc:
            model_health.record_failure(f"模型调用网络错误：{exc}")
            raise ProviderError(f"模型调用网络错误：{exc}") from exc

        if resp.status_code >= 400:
            # 402 = 欠费、401 = key 失效、429 = 限流。这三种都要让 /api/health 看得见，
            # 不然健康检查会一直绿到用户上传为止（11/11 就是这么翻车的）。
            model_health.record_failure(f"模型返回 HTTP {resp.status_code}：{resp.text[:200]}")
            raise ProviderError(f"模型返回 HTTP {resp.status_code}：{resp.text[:300]}")

        model_health.record_ok()
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
            "max_tokens": settings.vlm_max_tokens,
        }
        if settings.vlm_effort:
            # 部分 OpenAI 兼容供应商支持推理档位（DeepSeek: low/high/max）
            payload["effort"] = settings.vlm_effort
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

    async def chat_tools(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], int]:
        """Function Calling：把工具清单交给模型，让它自己决定调哪个、按什么顺序。

        这一步是"AI 在工作流里做决定"和"代码写死 if-else"的分界线。
        模型返回的 tool_calls 由调用方执行并把结果回灌，直到它不再要工具为止。
        """
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": settings.vlm_max_tokens,
            "tools": tools,
            "tool_choice": "auto",
        }
        data = await self._post(payload)
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"模型返回结构异常：{str(data)[:300]}") from exc
        if not isinstance(message, dict):
            raise ProviderError(f"模型返回的 message 不是对象：{message!r}"[:300])
        return message, int((time.perf_counter() - started) * 1000)


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


# 单独放，不混进 _MOCK_VARIANTS：混进去会改变按指纹取样的映射，
# 让之前跑通的结果对不上。它只在显式指定时才用。
_NON_INVOICE_VARIANT: dict[str, Any] = {
    "is_invoice": False,
    "invoice_code": None,
    "invoice_number": None,
    "invoice_date": None,
    "seller_name": None,
    "seller_tax_id": None,
    "buyer_name": None,
    "buyer_tax_id": None,
    "amount_excl_tax": None,
    "tax_amount": None,
    "amount_incl_tax": None,
    "tax_rate": None,
    "category": None,
    "items": [],
    "confidence": {"overall": 0.20, "per_field": {}},
    "note": "画面里没有发票，只有聊天记录截图",
}


# 演示/联调用的整场景样本：让前端在没有真模型、没有数据集的时候
# 也能看到黄灯和红灯长什么样。它们同样是"钉住输出"，不是识别能力。
_SCENARIOS: dict[str, dict[str, Any]] = {
    "over_std": {
        "is_invoice": True,
        "invoice_code": "033002200114",
        "invoice_number": "58231067",
        "invoice_date": "2026-10-31",
        "seller_name": "杭州西溪宾馆有限公司",
        "seller_tax_id": "91330106MA2K7X1A2B",
        "buyer_name": "杭州云帆科技有限公司",
        "buyer_tax_id": "91330100MA2A1B2C3D",
        "amount_excl_tax": 1207.55,
        "tax_amount": 72.45,
        "amount_incl_tax": 1280.00,
        "tax_rate": 0.06,
        "category": "住宿",
        "items": [{"name": "住宿费", "amount": 1207.55}],
        "confidence": {
            "overall": 0.94,
            "per_field": {
                "invoice_number": 0.97,
                "invoice_date": 0.96,
                "amount_incl_tax": 0.93,
                "seller_name": 0.94,
                "buyer_tax_id": 0.95,
            },
        },
    },
    "dup": {
        "is_invoice": True,
        "invoice_code": "033002200115",
        "invoice_number": "66472890",
        "invoice_date": "2026-10-28",
        "seller_name": "杭州老码头餐饮管理有限公司",
        "seller_tax_id": "91330102MA2K7X5G6H",
        "buyer_name": "杭州云帆科技有限公司",
        "buyer_tax_id": "91330100MA2A1B2C3D",
        "amount_excl_tax": 458.49,
        "tax_amount": 27.51,
        "amount_incl_tax": 486.00,
        "tax_rate": 0.06,
        "category": "餐饮",
        "items": [{"name": "餐饮服务", "amount": 458.49}],
        "confidence": {
            "overall": 0.98,
            "per_field": {
                "invoice_number": 0.99,
                "invoice_date": 0.98,
                "amount_incl_tax": 0.99,
                "seller_name": 0.98,
                "buyer_tax_id": 0.99,
            },
        },
    },
    "header_err": {
        "is_invoice": True,
        "invoice_code": "033002200116",
        "invoice_number": "77015543",
        "invoice_date": "2026-10-26",
        "seller_name": "浙江大华办公用品有限公司",
        "seller_tax_id": "91330100MA2K7X6H7J",
        "buyer_name": "杭州云帆网络科技有限公司",
        "buyer_tax_id": "91330100MA2A1B2C3D",
        "amount_excl_tax": 2831.86,
        "tax_amount": 368.14,
        "amount_incl_tax": 3200.00,
        "tax_rate": 0.13,
        "category": "办公",
        "items": [{"name": "办公耗材", "amount": 2831.86}],
        "confidence": {
            "overall": 0.93,
            "per_field": {
                "invoice_number": 0.98,
                "invoice_date": 0.97,
                "amount_incl_tax": 0.96,
                "seller_name": 0.95,
                "buyer_name": 0.88,
                "buyer_tax_id": 0.86,
            },
        },
    },
}


class MockVision(VisionProvider):
    """没有密钥时的替身：按图片指纹挑一个固定样例，结果可复现。

    它不是"假装 AI 成功"，而是让链路（压缩 → 调用 → 校验 → 缓存 → 前端）
    在没有任何密钥的情况下也能被完整验证。返回里 provider 会明确写 mock。

    它**不看图片内容**——输出只跟图片指纹有关。所以它证明不了"识别准不准"，
    只能证明"链路通不通"。想验证"不是发票"这条分支，用 MOCK_VARIANT=non_invoice
    把输出钉住，那是分支验证工具，不是识别能力。
    """

    name = "mock-vlm"

    def __init__(self, seed: str = "") -> None:
        self.seed = seed
        self.variant = (settings.mock_variant or "").strip().lower()
        # 把钉住的变体写进 model 名，缓存的身份校验就会跟着失效——
        # 否则换了 MOCK_VARIANT 还吃旧缓存，看着像开关没生效。
        self.model = f"mock-vlm-1@{self.variant}" if self.variant else "mock-vlm-1"

    def _pick(self) -> dict[str, Any]:
        if self.variant in _SCENARIOS:
            return _SCENARIOS[self.variant]
        if self.variant in ("non_invoice", "non-invoice", "none", "not_invoice"):
            return _NON_INVOICE_VARIANT
        if self.variant.isdigit() and int(self.variant) < len(_MOCK_VARIANTS):
            return _MOCK_VARIANTS[int(self.variant)]
        index = int(self.seed[:8] or "0", 16) % len(_MOCK_VARIANTS) if self.seed else 0
        return _MOCK_VARIANTS[index]

    async def chat(self, messages: list[dict[str, Any]]) -> ChatResult:
        started = time.perf_counter()
        payload = self._pick()
        # 模拟一点真实延迟，让前端的"思考中"状态有东西可看
        await _sleep(0.35)
        return ChatResult(
            text=json.dumps(payload, ensure_ascii=False),
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
3. **原样抄录，不许"帮忙改正"。** 票面上有错别字、少一个字、多了空格、号码位数不对，
   都照原样输出，不要纠正、不要补全、不要规范化。理由：审核要比对"票面写的"和"制度要求的"，
   你替它改对了，这一处违规就永远查不出来。
4. 严禁根据常识补全或推算金额。金额只从图上读，不要做加减乘除。
5. 日期统一 YYYY-MM-DD；金额为纯数字、两位小数，不带 ¥ 符号和千分位。
6. category 只能取下列之一：住宿 / 餐饮 / 交通 / 办公 / 招待 / 其他。
7. 如果图片根本不是发票（风景照、聊天截图、空白页），把 is_invoice 设为 false，其余字段全部 null。
8. 每个字段都要给 confidence（0~1），表示你在这一项上的把握；overall 取你最没把握的那一项的思路给。

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
