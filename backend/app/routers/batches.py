"""批次相关接口：上传、列表、结果、审核进度流。

D2 起上传是真解析了：
- 传文件 → 逐张跑抽取（图片压缩 → 模型 → 四道关 → 置信度闸门）
- 传 ?demo=true → 还是那 5 张演示数据，答辩演示不会被模型波动影响
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.config import settings
from app.mock import fixtures
from app.schemas import BatchResults, BatchSummary, UploadResponse
from app.services import store
from app.services.extract import ExtractionError, extract_one
from app.services.image import ImageError

router = APIRouter(prefix="/api/batches", tags=["batches"])

MAX_FILES = 20
MAX_BYTES = settings.upload_max_mb * 1024 * 1024


# ------------------------------------------------------------------ 数据源

def _find_batch(batch_id: str) -> store.StoredBatch | None:
    return store.get_batch(batch_id)


def _summary(batch_id: str) -> dict:
    stored = _find_batch(batch_id)
    if stored:
        return stored.summary
    if batch_id in fixtures.BATCHES:
        return fixtures.summary_of(batch_id)
    raise HTTPException(status_code=404, detail=f"批次不存在：{batch_id}")


def _cards(batch_id: str) -> list[dict]:
    stored = _find_batch(batch_id)
    if stored:
        return stored.cards
    if batch_id in fixtures.BATCHES:
        return fixtures.items_of(batch_id)
    raise HTTPException(status_code=404, detail=f"批次不存在：{batch_id}")


def _detail(invoice_id: str) -> dict | None:
    return store.get_detail(invoice_id) or fixtures.get_detail(invoice_id)


# ------------------------------------------------------------------ 上传

@router.post("", response_model=UploadResponse, summary="上传一批发票")
async def upload_batch(
    files: list[UploadFile] | None = File(default=None),
    demo: bool = Query(default=False, description="true 时忽略上传文件，直接返回演示批次"),
) -> UploadResponse:
    """上传并立即识别。

    - `?demo=true`：返回固定演示批次 B20261104-001（3 绿 1 黄 1 红）
    - 真上传：逐张识别，返回新批次号；随后打 /results 取结论、/stream 看过程
    """
    uploads = files or []
    if not uploads and not demo:
        raise HTTPException(status_code=400, detail="请至少上传 1 张发票，或使用 ?demo=true")

    if demo:
        batch_id = fixtures.DEMO_BATCH_ID
        return UploadResponse(
            batch_id=batch_id,
            invoice_count=fixtures.BATCHES[batch_id]["invoice_count"],
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            next_action=f"/api/batches/{batch_id}/results",
        )

    if len(uploads) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"一次最多 {MAX_FILES} 张，请分批上传")

    # 先把字节读出来并做基本检查，避免占着并发名额等 IO
    payloads: list[tuple[str, bytes]] = []
    for upload in uploads:
        name = upload.filename or "未命名"
        if upload.content_type and not upload.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail=f"{name} 不是图片文件")
        raw = await upload.read()
        if not raw:
            raise HTTPException(status_code=400, detail=f"{name} 是空文件")
        if len(raw) > MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"{name} 超过 {settings.upload_max_mb}MB，请压缩后再传",
            )
        payloads.append((name, raw))

    batch_id = store.next_batch_id()
    started = datetime.now()
    semaphore = asyncio.Semaphore(3)

    async def run(name: str, raw: bytes):
        async with semaphore:
            try:
                result = await extract_one(raw)
            except ImageError as exc:
                raise HTTPException(status_code=400, detail=f"{name}：{exc}") from exc
            except ExtractionError as exc:
                raise HTTPException(status_code=502, detail=f"{name} 识别失败：{exc}") from exc
        image_id = store.save_image(raw, store.guess_mime(name))
        return (name, image_id, result)

    entries = await asyncio.gather(*(run(name, raw) for name, raw in payloads))
    batch = store.build_batch(batch_id, entries)

    # 用实测耗时覆盖按张累加，更接近用户真实体感
    batch.summary["elapsed_ms"] = int((datetime.now() - started).total_seconds() * 1000)

    return UploadResponse(
        batch_id=batch_id,
        invoice_count=len(entries),
        created_at=batch.summary["created_at"],
        next_action=f"/api/batches/{batch_id}/results",
    )


# ------------------------------------------------------------------ 查询

@router.get("", response_model=list[BatchSummary], summary="批次列表")
def list_batches() -> list[dict]:
    return store.list_batches() + [fixtures.summary_of(bid) for bid in fixtures.BATCHES]


@router.get("/{batch_id}", response_model=BatchSummary, summary="批次概要")
def get_batch(batch_id: str) -> dict:
    return _summary(batch_id)


@router.get("/{batch_id}/results", response_model=BatchResults, summary="审核结果（整页一次给全）")
def get_results(batch_id: str) -> dict:
    return {"batch": _summary(batch_id), "items": _cards(batch_id)}


# ------------------------------------------------------------------ 进度流

@router.get("/{batch_id}/stream", summary="审核进度流（SSE）")
async def stream_batch(batch_id: str) -> StreamingResponse:
    """逐张推送审核进度与轨迹。

    事件类型：
    - invoice_start  一张开始审
    - trace          一条轨迹（前端往面板里插一行）
    - invoice_done   一张审完，带结论
    - batch_done     整批结束
    """
    cards = _cards(batch_id)

    async def gen():
        started = datetime.now()
        for card in cards:
            detail = _detail(card["invoice_id"]) or {}
            yield _sse(
                "invoice_start",
                {
                    "invoice_id": card["invoice_id"],
                    "seq": card["seq"],
                    "total": len(cards),
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
                # 按真实耗时等比缩放，演示时能看到"正在想"的节奏
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
                "summary": _summary(batch_id),
            },
        )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"