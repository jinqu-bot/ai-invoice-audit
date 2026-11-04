"""批次相关接口：上传、列表、结果、审核进度流。

D1 说明：
- 上传不做真实解析，直接返回演示批次的 batch_id。
- 进度流是真的 SSE，前端今天就能把“逐张审核 + 轨迹流动”的效果做出来。
"""

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.mock import fixtures
from app.schemas import BatchResults, BatchSummary, UploadResponse

router = APIRouter(prefix="/api/batches", tags=["batches"])


@router.post("", response_model=UploadResponse, summary="上传一批发票")
async def upload_batch(
    files: list[UploadFile] | None = File(default=None),
    demo: bool = Query(default=False, description="true 时忽略上传文件，直接返回演示批次"),
) -> UploadResponse:
    """D1 只做“接住文件”，不解析。

    - 传了文件或 demo=true：返回演示批次 B20261104-001（5 张：3 绿 1 黄 1 红）
    - 前端拿到 batch_id 后，去打 /results 和 /stream
    """
    count = len(files or [])
    if count == 0 and not demo:
        raise HTTPException(status_code=400, detail="请至少上传 1 张发票，或使用 ?demo=true")

    batch_id = fixtures.DEMO_BATCH_ID
    return UploadResponse(
        batch_id=batch_id,
        invoice_count=fixtures.BATCHES[batch_id]["invoice_count"],
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        next_action=f"/api/batches/{batch_id}/results",
    )


@router.get("", response_model=list[BatchSummary], summary="批次列表")
def list_batches() -> list[dict]:
    return [fixtures.summary_of(bid) for bid in fixtures.BATCHES]


@router.get("/{batch_id}", response_model=BatchSummary, summary="批次概要")
def get_batch(batch_id: str) -> dict:
    if batch_id not in fixtures.BATCHES:
        raise HTTPException(status_code=404, detail=f"批次不存在：{batch_id}")
    return fixtures.summary_of(batch_id)


@router.get("/{batch_id}/results", response_model=BatchResults, summary="审核结果（整页一次给全）")
def get_results(batch_id: str) -> dict:
    if batch_id not in fixtures.BATCHES:
        raise HTTPException(status_code=404, detail=f"批次不存在：{batch_id}")
    return {"batch": fixtures.summary_of(batch_id), "items": fixtures.items_of(batch_id)}


@router.get("/{batch_id}/stream", summary="审核进度流（SSE）")
async def stream_batch(batch_id: str) -> StreamingResponse:
    """逐张推送审核进度与轨迹。

    事件类型：
    - invoice_start  一张开始审
    - trace          一条轨迹（前端往面板里插一行）
    - invoice_done   一张审完，带结论
    - batch_done     整批结束

    前端用 EventSource 监听，事件名就是 type 字段。
    """
    if batch_id not in fixtures.BATCHES:
        raise HTTPException(status_code=404, detail=f"批次不存在：{batch_id}")

    items = fixtures.items_of(batch_id)

    async def gen():
        started = datetime.now()
        for card in items:
            detail = fixtures.get_detail(card["invoice_id"]) or {}
            yield _sse(
                "invoice_start",
                {
                    "invoice_id": card["invoice_id"],
                    "seq": card["seq"],
                    "total": len(items),
                    "image_url": card["image_url"],
                },
            )
            await asyncio.sleep(0.15)

            for step in detail.get("trace", []):
                yield _sse(
                    "trace",
                    {
                        "invoice_id": card["invoice_id"],
                        "step": step["step"],
                        "tool": step["tool"],
                        "title": step["title"],
                        "reason": step["reason"],
                        "status": step["status"],
                        "latency_ms": step["latency_ms"],
                    },
                )
                # 按真实耗时等比缩放，演示时能看到“正在想”的节奏
                await asyncio.sleep(min(step["latency_ms"] / 1000.0, 0.5))

            yield _sse(
                "invoice_done",
                {
                    "invoice_id": card["invoice_id"],
                    "verdict": card["verdict"],
                    "headline": card["headline"],
                    "confidence": card["confidence"],
                    "hit_rule_codes": card["hit_rule_codes"],
                },
            )
            await asyncio.sleep(0.1)

        elapsed = int((datetime.now() - started).total_seconds() * 1000)
        yield _sse(
            "batch_done",
            {
                "batch_id": batch_id,
                "elapsed_ms": elapsed,
                "summary": fixtures.summary_of(batch_id),
            },
        )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
