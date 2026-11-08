"""批次相关接口：上传、列表、结果、审核进度流。

D6 起上传是**两段式**：`POST` 立刻返回 202 + 批次号，后台任务逐张审，
进度通过 `/stream` 实时推。`?demo=true` 仍是一次性返回现成的演示批次（200）。

这样做的直接原因：以前 `POST` 要等全部识别完才返回，`/stream` 只是把
存好的轨迹按节奏播一遍——那是动画。现在是真的边跑边推。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, AsyncIterator

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import StreamingResponse

from app.config import settings
from app.mock import fixtures
from app.schemas import BatchList, BatchResults, BatchSummary, UploadResponse
from app.services import jobs, reviews, runner, store

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

@router.post(
    "",
    response_model=UploadResponse,
    status_code=202,
    responses={200: {"description": "demo=true 时直接返回现成批次，不走后台任务"}},
    summary="上传一批发票（立刻返回 202，后台逐张审核）",
)
async def upload_batch(
    response: Response,
    files: list[UploadFile] | None = File(default=None),
    demo: bool = Query(default=False, description="true 时忽略上传文件，直接返回演示批次"),
) -> UploadResponse:
    """上传并**立刻**返回批次号。

    - 真上传：返回 **202** + `status=processing`，随后订阅 `/stream` 看真进度，
      或轮询 `/results`（`status` 变成 `done/partial/failed` 即结束）
    - `?demo=true`：返回 **200** + `status=done`，固定演示批次 B20261104-001
    - 预检就失败的文件（类型/空/过大）直接进 `failed`，不占后台任务
    """
    uploads = files or []
    if not uploads and not demo:
        raise HTTPException(status_code=400, detail="请至少上传 1 张发票，或使用 ?demo=true")

    if demo:
        batch_id = fixtures.DEMO_BATCH_ID
        response.status_code = 200
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

    # 预检：类型、空文件、大小。这些错不必进后台任务，当场就能说清
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
    # 批次壳必须在返回之前落库。放到后台线程里建会有一个竞态窗口：
    # POST 已经返回 202，但行还没写进去，前端立刻 GET /results 会拿到 404——
    # 表现是"打不开这批数据"，而且只在慢机器上偶发。
    store.create_batch(batch_id, expected=len(payloads), failures=failures)
    job = jobs.create(batch_id)
    task = runner.run_batch(job, batch_id, payloads, failures)
    status = "processing"
    try:
        jobs.start_job(task)
    except Exception:
        # 线程没起来：当场收口成 failed 并把批次号交回去，
        # 前端才能显示"这批失败了，原因是…"，而不是干等或丢掉这次上传。
        task.close()  # 没被 await 的协程要显式关掉，否则会有 never-awaited 警告
        failures.append(
            {"filename": "—", "code": "START_FAILED", "message": "后台审核任务未能启动，请重试"}
        )
        summary = store.finish_batch(batch_id, failures=failures)
        job.emit("batch_done", {"batch_id": batch_id, "elapsed_ms": 0, "summary": summary})
        job.finish()
        status = "failed"
    response.headers["Location"] = f"/api/batches/{batch_id}/stream"

    return UploadResponse(
        batch_id=batch_id,
        invoice_count=len(payloads),
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        status=status,
        failed=failures,
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


@router.get(
    "/{batch_id}/results",
    response_model=BatchResults,
    summary="审核结果（processing 期间也能调）",
)
def get_results(batch_id: str) -> dict:
    """`status=processing` 时返回已审完的那几张，数量会一张张变多。

    前端可以拿它当 SSE 的兜底：现场网络不可靠，流断了就轮询这个接口。
    """
    return {
        "batch": _summary(batch_id),
        # 人工复核过的票，这里要显示改判后的结论，否则列表和详情会互相打脸
        "items": reviews.apply_many(_cards(batch_id)),
        "failures": _failures(batch_id),
    }


# ------------------------------------------------------------------ 进度流

@router.get("/{batch_id}/stream", summary="审核进度流（SSE）")
async def stream_batch(batch_id: str) -> StreamingResponse:
    """逐张推送审核进度与轨迹。

    事件：`batch_start` / `invoice_start` / `trace` / `invoice_done` /
    `file_failed` / `batch_done`。

    - **正在跑的批次**：先补发已经发生的事件（页面刷新不丢进度），再接直播
    - **已经跑完的批次**（演示批次、历史批次）：按存下来的轨迹回放一遍，
      给你一个能播的动画——这一路是回放，别拿它当实时
    """
    job = jobs.get(batch_id)
    if job is not None:
        return _live_stream(job)

    cards = _cards(batch_id)  # 批次不存在会抛 404
    return StreamingResponse(
        _replay(cards),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _live_stream(job: jobs.Job) -> StreamingResponse:
    async def gen() -> AsyncIterator[str]:
        # 已经跑完的任务也留着事件：这里直接把它当"快放"给出去，
        # 但必须如实标成 replay——观众要分得清"正在发生"和"发生过"。
        yield _sse("hello", {"batch_id": job.batch_id, "replay": job.finished})
        async for item in job.stream():
            yield _sse(item["event"], item["data"])
            # 客户端读得慢时让出控制权，避免一次性灌满缓冲区
            await asyncio.sleep(0)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _replay(cards: list[dict]) -> AsyncIterator[str]:
    """历史批次：把存下来的轨迹按节奏播一遍（演示批次靠它）。"""
    batch_id = cards[0]["batch_id"] if cards else ""
    yield _sse("hello", {"batch_id": batch_id, "replay": True})
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

    summary: dict[str, Any] = _summary(batch_id) if batch_id else {}
    yield _sse(
        "batch_done",
        {
            "batch_id": batch_id,
            "elapsed_ms": summary.get("elapsed_ms", 0),
            "summary": summary,
        },
    )