"""本地假视觉模型（只用来验证"真模型那条路"是通的）。

为什么需要它：项目里从来没跑过 `provider=openai-compat` 这条路径——没有 key，
所有测试走的都是 mock。可 mock 根本不吃图片，等于**这段代码一行都没被真跑过**。
一旦比赛前拿到 key，第一次运行才发现请求格式不对，那就来不及了。

这个桩做两件事：
1. 按 OpenAI 兼容格式回一个 `chat/completions`；
2. 把收到的请求原样写进 _local/fake_vlm_last_request.json，
   用来证明"图片真的以 base64 发出去了、模型名、prompt 都对"。

它回的字段是**用户那张真发票**（笔记本 4748 / 抬头戴海青 / 8 月 15 日），
所以下游 R3、R4 的结论可以顺手验一遍。

跑法：
    .venv\\Scripts\\python.exe _local\\fake_vlm.py
"""

from __future__ import annotations

import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request

LOG = Path(__file__).with_name("fake_vlm_last_request.json")

INVOICE = {
    "is_invoice": True,
    "invoice_code": "",
    "invoice_number": "2623200000859984741",
    "invoice_date": "2026-08-15",
    "seller_name": "哈尔滨鸿淼森科技有限公司",
    "seller_tax_id": "91230103MA1WQU9L",
    "buyer_name": "戴海青",
    "buyer_tax_id": "",
    "amount_excl_tax": 4201.77,
    "tax_amount": 546.23,
    "amount_incl_tax": 4748.00,
    "tax_rate": 0.13,
    "category": "办公",
    "items": [{"name": "电子计算机*笔记本电脑 X1502VA13500", "amount": 4201.77}],
    "confidence": {
        "overall": 0.93,
        "per_field": {
            "invoice_number": 0.97,
            "invoice_date": 0.95,
            "amount_incl_tax": 0.98,
            "seller_name": 0.94,
            "buyer_name": 0.96,
        },
    },
}

app = FastAPI()


@app.post("/v1/chat/completions")
async def chat(request: Request) -> dict:
    payload = await request.json()
    LOG.write_text(json.dumps(payload, ensure_ascii=False)[:200000], encoding="utf-8")

    images = [
        part
        for message in payload.get("messages", [])
        if isinstance(message.get("content"), list)
        for part in message["content"]
        if part.get("type") == "image_url"
    ]
    print(f"[fake-vlm] model={payload.get('model')} images={len(images)}", flush=True)
    for part in images[:1]:
        url = part["image_url"]["url"]
        print(f"[fake-vlm] image url prefix: {url[:40]}… len={len(url)}", flush=True)

    return {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "model": payload.get("model", "fake"),
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": json.dumps(INVOICE, ensure_ascii=False)},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200},
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="warning")