"""批次后台任务（D6）。

`POST /api/batches` 把活交给这里就返回 202，认领的任务按顺序逐张审：
审一张 → 存一张 → 推一张事件。事件推到 `jobs` 的事件总线，SSE 客户端消费。

**为什么是逐张而不是并发**：并发能让整批快一点，但事件乱序、进度百分比乱跳，
演示时"一张一张出结论"反而更像审核台在做事情。真实场景要提速，把这里的
串行改成 `asyncio.gather` + 信号量即可，事件契约不用动。

**为什么单张内部的轨迹是一次性推完**：除模型调用外，单张的每一步都是毫秒级，
真按耗时推会变成"刷"一下全出来。整批层面的进度是真的，单张层面是审完即发。
这一点在文档里写明，不装成"连思考过程都是实时的"。
"""

from __future__ import annotations

import time
from typing import Any

from app.services import jobs, store
from app.services.extract import ExtractionError, extract_one
from app.services.image import ImageError


async def run_batch(
    job: jobs.Job,
    batch_id: str,
    payloads: list[tuple[str, bytes]],
    failures: list[dict[str, Any]],
) -> None:
    """payloads: [(文件名, 原始字节)]，按上传顺序。failures: 预检就失败的。"""
    started = time.monotonic()
    providers: set[str] = set()
    total = len(payloads)

    try:
        store.create_batch(batch_id, expected=total, failures=failures)
        job.emit(
            "batch_start",
            {"batch_id": batch_id, "total": total, "failed": len(failures)},
        )
        for failure in failures:
            job.emit("file_failed", failure)

        for index, (filename, raw) in enumerate(payloads, start=1):
            seq = index
            invoice_id = f"INV-{batch_id}-{seq:02d}"
            image_id = store.save_image(raw, store.guess_mime(filename), filename)
            job.emit(
                "invoice_start",
                {
                    "invoice_id": invoice_id,
                    "seq": seq,
                    "total": total,
                    "image_url": f"/api/files/{image_id}.jpg",
                    "filename": filename,
                },
            )

            try:
                ext = await extract_one(raw)
            except ImageError as exc:
                failure = {"filename": filename, "code": "BAD_IMAGE", "message": str(exc)}
                failures.append(failure)
                job.emit("file_failed", failure)
                continue
            except ExtractionError as exc:
                failure = {"filename": filename, "code": "EXTRACT_FAILED", "message": str(exc)}
                failures.append(failure)
                job.emit("file_failed", failure)
                continue

            providers.add(ext.provider)
            stored = store.add_invoice(
                batch_id, seq=seq, filename=filename, image_id=image_id, ext=ext
            )
            card, detail = stored["card"], stored["detail"]

            for step in detail["trace"]:
                job.emit(
                    "trace",
                    {
                        "invoice_id": invoice_id,
                        "step": step["step"],
                        "tool": step["tool"],
                        "title": step["title"],
                        "reason": step["reason"],
                        "status": step["status"],
                        "latency_ms": step["latency_ms"],
                    },
                )

            job.emit(
                "invoice_done",
                {
                    "invoice_id": invoice_id,
                    "verdict": card["verdict"],
                    "headline": card["headline"],
                    "confidence": card["confidence"],
                    "hit_rule_codes": card["hit_rule_codes"],
                },
            )
    except Exception as exc:  # 兜底：绝不能让批次停在 processing
        failures.append({"filename": "—", "code": "INTERNAL", "message": f"审核中断：{exc}"})
        job.emit("file_failed", failures[-1])
    finally:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        summary = store.finish_batch(
            batch_id, elapsed_ms=elapsed_ms, failures=failures, providers=providers
        )
        job.emit(
            "batch_done",
            {"batch_id": batch_id, "elapsed_ms": summary["elapsed_ms"], "summary": summary},
        )
        job.finish()