"""批次相关接口：上传、列表、结果、审核进度流。

D2 起上传是真解析的；D5 起两件事变了：
- **部分成功**：一张失败不再让整批失败，成功的照常入库，失败的原样返回
- **落库**：批次和发票写进 SQLite，重启之后还能打开
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.config import settings
from app.mock import fixtures
from app.schemas import BatchList, BatchResults, BatchSummary, UploadResponse
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


def _failures(batch_id: str) -> list[dict]:
    stored = _find_batch(batch_id)
    return stored.failures if stored else []


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
    - 有文件处理失败时，批次状态是 `partial`，失败清单在 `failed` 里，**不会整批失败**
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
            status="done",
            failed=[],
            next_action=f"/api/batches/{batch_id}/results",
        )

    if len(uploads) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"一次最多 {MAX_FILES} 张，请分批上传")

    # 预检：类型、空文件、大小。这些错不必先占并发名额，也不必阻塞其它文件
    payloads: list[tuple[str, bytes]] = []
    failures: list[dict] = []
    for upload in uploads:
        name = upload.filename or "未命名"
        if upload.content_type and not upload.content_type.startswith("image/"):
            failures.append(
                {"filename": name, "code": "BAD_IMAGE", "message": "不是图片文件（只收 JPG / PNG / WebP）"}
            )
            continue
        raw = await upload.read()
        if not raw:
            failures.append({"filename": name, "code": "EMPTY_FILE", "message": "空文件"})
            continue
        if len(raw) > MAX_BYTES:
            failures.append(
                {
                    "filename": name,
                    "code": "FILE_TOO_LARGE",
                    "message": f"超过 {settings.upload_max_mb}MB，请压缩后再传",
                }
            )
            continue
        payloads.append((name, raw))

    batch_id = store.next_batch_id()
    started = datetime.now()
    semaphore = asyncio.Semaphore(3)

    async def run(name: str, raw: bytes):
        async with semaphore:
            try:
                return ("ok", name, raw, await extract_one(raw))
            except ImageError as exc:
                return ("fail", name, None, {"code": "BAD_IMAGE", "message": str(exc)})
            except ExtractionError as exc:
                return ("fail", name, None, {"code": "EXTRACT_FAILED", "message": str(exc)})

    results = await asyncio.gather(*(run(name, raw) for name, raw in payloads))

    entries: list[tuple[str, str, object]] = []
    for kind, name, raw, payload in results:
        if kind == "ok":
            mime = store.guess_mime(name)
            entries.append((name, store.save_image(raw, mime, name), payload))
        else:
            failures.append({"filename": name, **payload})

    elapsed_ms = int((datetime.now() - started).total_seconds() * 1000)
    batch = store.build_batch(batch_id, entries, failures=failures, elapsed_ms=elapsed_ms)

    return UploadResponse(
        batch_id=batch_id,
        invoice_count=batch.summary["invoice_count"],
        created_at=batch.summary["created_at"],
        status=batch.summary["status"],
        failed=batch.failures,
        next_action=f"/api/batches/{batch_id}/results",
    )


# ------------------------------------------------------------------ 查询

@router.get("", response_model=BatchList, summary="批次列表（分页）")
def list_batches(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """分页在合并演示数据之后做：演示批次只有两条，数据量小，先保证"一直看得到"。"""
    _, stored = store.list_batches()
    merged = stored + [fixtures.summary_of(bid) for bid in fixtures.BATCHES]
    merged.sort(key=lambda x: (x["created_at"], x["batch_id"]), reverse=True)
    return {
        "total": len(merged),
        "limit": limit,
        "offset": offset,
        "items": merged[offset : offset + limit],
    }


@router.get("/{batch_id}", response_model=BatchSummary, summary="批次概要")
def get_batch(batch_id: str) -> dict:
    return _summary(batch_id)


@router.get("/{batch_id}/results", response_model=BatchResults, summary="审核结果（整页一次给全）")
def get_results(batch_id: str) -> dict:
    return {
        "batch": _summary(batch_id),
        "items": _cards(batch_id),
        "failures": _failures(batch_id),
    }


# ------------------------------------------------------------------ 进度流

@router.get("/{batch_id}/stream", summary="审核进度流（SSE）")
async def stream_batch(batch_id: str) -> StreamingResponse:
    """逐张推送审核进度与轨迹。

    事件类型：
    - invoice_start  一张开始审
    - trace          一条轨迹（前端往面板里插一行）
    - invoice_done   一张审完，带结论
    - batch_done     整批结束

    ⚠️ 这是**结果回放**：批次早就审完了，这里把存下来的轨迹按节奏播一遍。
    真正的实时进度要等 D6 编排器把 POST 改成先返回、后台再跑。
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