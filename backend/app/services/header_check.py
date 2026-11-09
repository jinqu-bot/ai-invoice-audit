"""抬头二次核验：把关键字段裁出来放大，再逐字读一遍。

## 为什么需要这个

真模型实测（见 docs/识别准确率实测.md）发现一类静默失效：

票面印的是 `杭州云帆科技有限公可`（故意写错一个字，用来触发 R3 抬头校验），
模型读出 `杭州云帆科技有限公司`——**它把「可」认成了「司」**，置信度还给到 0.96。

后果不是"识别错一个字"这么简单：R3 拿到的是一份"看起来完全正确的公司名"，
比对通过、直接放行，**本该驳回的票变成了通过，而且没有任何提示**。

试过但没用：
- 提示词里写"原样抄录，不许纠正错别字" → 仍读成「公司」
- 推理档位调到 high → 仍读成「公司」
- 整图 + "逐字读"提示词 → 仍读成「公司」

有效的是：**把那一行裁出来放大 2.5 倍再问**（实测能正确读出「公可」）。
原因很直观——整图里公司名只有十几像素高，放大后笔画差异才看得见。

## 这里怎么用

跑在第一次识别之后：
1. 裁上半部分（抬头一般在这里）→ 放大 → 问"逐字读购买方名称"
2. 两遍结果不一致 → **采信第二次**（它是逐字看的），并把该项置信度压到 0.5
3. 置信度 0.5 会让 R0 兜住转人工，同时 R3 也能拿正确的名字去比对

代价是每张票多一次模型调用（约 2-4 秒）。用 VLM_VERIFY_HEADER=1 打开。
"""

from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

from PIL import Image

# 注意：抽取链路开着 json_object 模式，所以这里也要求 JSON，
# 否则模型会把整段结构化结果吐回来（踩过）。
_ASK = (
    "逐字读出这张发票上「购买方 名称」一栏的文字，一个字一个字念。\n"
    "不要纠正错别字、不要按常识补全：看到「公可」就输出「公可」，不要自动写成「公司」。\n"
    '只输出一个 JSON：{"buyer_name": "读到的名称"}，不要任何解释。'
)

_PREFIX = re.compile(r"^(购买方)?\s*(名称)?\s*[:：]?\s*")


def crop_header_png(raw: bytes, top_ratio: float = 0.45, zoom: float = 2.5) -> bytes:
    """裁上半部分并放大，返回 PNG 字节。裁歪了也不会崩，最坏结果是读不出来。"""
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    width, height = img.size
    crop = img.crop((0, 0, width, max(1, int(height * top_ratio))))
    zoomed = crop.resize(
        (int(crop.width * zoom), int(crop.height * zoom)), Image.LANCZOS
    )
    buf = io.BytesIO()
    zoomed.save(buf, format="PNG")
    return buf.getvalue()


_JSON_NAME = re.compile(r'"buyer_name"\s*:\s*"([^"]*)"')


def clean_name(text: str) -> str:
    """从模型输出里把名字取出来：优先解析 JSON，失败再退回纯文本处理。"""
    raw = (text or "").strip()
    match = _JSON_NAME.search(raw)
    if match:
        raw = match.group(1)
    else:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("buyer_name"):
                raw = str(parsed["buyer_name"])
        except (ValueError, TypeError):
            pass
    value = raw.strip().strip("「」\"'` ")
    value = value.splitlines()[0] if value else ""
    return _PREFIX.sub("", value).strip()


def data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def reconcile(first: str, second: str) -> tuple[str, bool]:
    """返回 (最终采用的名字, 是否两遍不一致)。

    不一致时采信第二次：它是把字放大后逐字看的，比整图扫一眼可靠。
    """
    a, b = clean_name(first), clean_name(second)
    if not b or a == b:
        return a, False
    return b, True


async def _sample(provider: Any, uri: str) -> str:
    from app.services.llm import build_messages

    try:
        chat = await provider.chat(build_messages(uri, _ASK))
    except Exception:
        return ""
    return clean_name(chat.text)


async def verify(
    provider: Any, raw: bytes, first_name: str, samples: int = 3
) -> dict[str, Any]:
    """同一个字段多读几遍。

    为什么要多读：实测发现这类形近字错误**是随机的**——同一张图、同样的参数，
    有时读对「公可」，有时读成「公司」。单次结果不可信，但**"读不稳定"本身就是信号**：
    如果三次里有分歧，就说明这一格机器没看清，该转人工，而不是挑一个信它。

    返回 {name, conflict, unstable}。任何异常都返回空，绝不影响主流程。
    """
    try:
        uri = data_uri(crop_header_png(raw))
    except Exception:
        return {"name": "", "conflict": False, "unstable": False}

    readings = [await _sample(provider, uri) for _ in range(max(2, samples))]
    readings = [r for r in readings if r]
    if not readings:
        return {"name": "", "conflict": False, "unstable": False}

    stable = len(set(readings)) == 1
    if not stable:
        # 同一张图读几遍自己都对不上 → 这一格机器没看清，采信出现最多的但标记出来
        best = max(set(readings), key=readings.count)
        return {"name": best, "conflict": True, "unstable": True, "readings": readings}

    name, conflict = reconcile(first_name, readings[0])
    return {
        "name": name,
        "conflict": conflict,
        "unstable": False,
        "readings": readings,
    }
