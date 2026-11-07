"""D6：真·异步批次 + 真·进度流。

这一组测试守的是契约里最容易骗人的部分：

- `POST` 必须**立刻**返回（不能偷偷把活干完了再返回 202）；
- `/results` 在 `processing` 期间就能调，数量一张张变多；
- `/stream` 对正在跑的批次走**直播**（第一条事件是 `batch_start`），
  对跑完的批次走**回放**（`hello.replay=true`，没有 batch_start）；
- 后台任务无论怎么炸，批次都不能停在 `processing`；
- 进程重启后卡住的批次必须被标成 `failed`，不能让页面永远转圈。

最后一条尤其重要：一个永远转圈的批次，比一个明确失败的批次糟得多。
"""

from __future__ import annotations

import asyncio
import io
import json
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

import app.services.runner as runner_mod
from app.config import settings
from app.main import app
from app.services import jobs, store
from support import upload_and_wait, wait_done

client = TestClient(app)


def make_png(seed: int = 0, size: tuple[int, int] = (800, 1100)) -> bytes:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    for i in range(0, size[1], 18):
        d.line([(30, i + seed % 7), (size[0] - 30, i + 3)], fill=(215, 219, 225))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def mock_model(monkeypatch):
    monkeypatch.setattr(settings, "vlm_api_key", "")
    monkeypatch.setattr(settings, "mock_variant", "")
    monkeypatch.setattr(settings, "cache_enabled", False)
    return monkeypatch


def parse_sse(text: str) -> list[tuple[str, dict]]:
    """把 SSE 文本拆成 (事件名, 数据) 列表。够用就行，不引第三方解析库。"""
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        name = ""
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: "):].strip()
            elif line.startswith("data: "):
                data = json.loads(line[len("data: "):])
        if name:
            events.append((name, data or {}))
    return events


def upload(*files) -> dict:
    return upload_and_wait(
        client, [("files", (name, raw, mime)) for name, raw, mime in files]
    )


# ------------------------------------------------------------------ 202

def test_upload_returns_202_and_processing(mock_model):
    """POST 只负责"接单"，不负责"干完"。"""
    resp = client.post(
        "/api/batches", files={"files": ("a.png", make_png(1), "image/png")}
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "processing"
    assert body["next_action"].endswith("/results")
    assert resp.headers["Location"].endswith("/stream")

    # 批次立刻可见，不必等它跑完
    summary = client.get(f"/api/batches/{body['batch_id']}").json()
    assert summary["batch_id"] == body["batch_id"]

    wait_done(client, body["batch_id"])


def test_demo_upload_still_returns_200_done():
    """演示批次不装样子：它本来就是现成的，直接 200 + done，不排队。"""
    resp = client.post("/api/batches?demo=true")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "done"
    assert body["invoice_count"] == 5


# ------------------------------------------------------------------ 边跑边查

def test_results_grow_while_processing(mock_model, monkeypatch):
    """`processing` 期间 /results 就能用，数量一张张变多——这是前端兜底的路。"""
    real_extract = runner_mod.extract_one

    async def slow_extract(raw: bytes):
        await asyncio.sleep(0.25)
        return await real_extract(raw)

    monkeypatch.setattr(runner_mod, "extract_one", slow_extract)

    resp = client.post(
        "/api/batches",
        files=[
            ("files", ("a.png", make_png(1), "image/png")),
            ("files", ("b.png", make_png(2), "image/png")),
        ],
    )
    assert resp.status_code == 202
    batch_id = resp.json()["batch_id"]

    seen_partial = False
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        body = client.get(f"/api/batches/{batch_id}/results").json()
        if body["batch"]["status"] == "processing" and body["items"]:
            # 关键点：状态还是 processing，但已经有票审完了
            assert len(body["items"]) < 2
            # 待审张数一开始就是 2，页面靠它摆骨架屏；已审张数会一张张追上来
            assert body["batch"]["invoice_count"] == 2
            seen_partial = True
            break
        if body["batch"]["status"] != "processing":
            break
        time.sleep(0.02)

    final = wait_done(client, batch_id)
    assert final["batch"]["status"] == "done"
    assert len(final["items"]) == 2
    assert seen_partial, "没观察到「边跑边有结果」的中间态，可能又变回同步了"


# ------------------------------------------------------------------ 直播 vs 回放

def test_live_stream_starts_with_batch_start(mock_model):
    """正在跑的批次走直播：第一条业务事件是 batch_start。

    回放路径永远不会发 batch_start——它是专门给"真进度"的。
    """
    resp = client.post(
        "/api/batches",
        files=[
            ("files", ("a.png", make_png(1), "image/png")),
            ("files", ("b.png", make_png(2), "image/png")),
        ],
    )
    batch_id = resp.json()["batch_id"]

    stream = client.get(f"/api/batches/{batch_id}/stream")
    assert stream.status_code == 200
    events = parse_sse(stream.text)

    names = [name for name, _ in events]
    assert events[0][0] == "hello" and events[0][1]["replay"] is False
    assert names[1] == "batch_start"
    assert events[1][1]["total"] == 2

    # 每张票都走完 start → trace* → done，最后整批 batch_done
    assert names.count("invoice_start") == 2
    assert names.count("invoice_done") == 2
    assert names[-1] == "batch_done"
    assert names.index("batch_start") < names.index("invoice_start")
    assert names.index("invoice_done") < names.index("batch_done")

    # 轨迹在 done 之前到——前端是拿它来"边看边播"的
    first_done = names.index("invoice_done")
    assert "trace" in names[:first_done]


def test_finished_batch_streams_as_replay(mock_model):
    """跑完的批次再订阅：标成回放（`replay=true`），别让观众以为是实时的。"""
    body = upload(("a.png", make_png(1), "image/png"))
    events = parse_sse(client.get(f"/api/batches/{body['batch_id']}/stream").text)

    assert events[0][0] == "hello"
    assert events[0][1]["replay"] is True
    names = [name for name, _ in events]
    assert names[-1] == "batch_done"


def test_restart_falls_back_to_db_replay(mock_model):
    """后端重启后内存里的事件没了，但库里有批次——照样能播，只是没有 batch_start。"""
    body = upload(("a.png", make_png(1), "image/png"))
    jobs.forget(body["batch_id"])  # 等价于进程重启：内存里的任务没了

    events = parse_sse(client.get(f"/api/batches/{body['batch_id']}/stream").text)
    assert events[0][1]["replay"] is True
    names = [name for name, _ in events]
    assert "batch_start" not in names, "回放路径不该伪造实时事件"
    assert names.count("invoice_done") == 1
    assert names[-1] == "batch_done"


def test_stream_can_be_subscribed_twice(mock_model):
    """页面刷新、开第二个标签页都会重新订阅，两路都得拿到完整过程。"""
    body = upload(("a.png", make_png(1), "image/png"))
    first = parse_sse(client.get(f"/api/batches/{body['batch_id']}/stream").text)
    second = parse_sse(client.get(f"/api/batches/{body['batch_id']}/stream").text)

    names = [name for name, _ in first]
    assert [name for name, _ in second] == names, "第二次订阅少事件了"
    assert names.count("invoice_done") == 1


def test_file_failed_event_carries_reason(mock_model):
    """坏文件当场推 file_failed，并带上原因——不能只在最终结果里躺着。"""
    resp = client.post(
        "/api/batches",
        files=[
            ("files", ("good.png", make_png(1), "image/png")),
            ("files", ("note.txt", b"hello", "text/plain")),
        ],
    )
    batch_id = resp.json()["batch_id"]
    events = parse_sse(client.get(f"/api/batches/{batch_id}/stream").text)

    failed = [data for name, data in events if name == "file_failed"]
    assert len(failed) == 1
    assert failed[0]["filename"] == "note.txt"
    assert failed[0]["code"] == "BAD_IMAGE"
    assert failed[0]["message"]


# ------------------------------------------------------------------ 兜底

def test_internal_error_still_finishes_batch(mock_model, monkeypatch):
    """后台任务炸了也不能停在 processing：标 failed，写清原因。"""

    async def boom(raw: bytes):
        raise RuntimeError("模型服务挂了")

    monkeypatch.setattr(runner_mod, "extract_one", boom)

    resp = client.post(
        "/api/batches", files={"files": ("a.png", make_png(1), "image/png")}
    )
    batch_id = resp.json()["batch_id"]
    final = wait_done(client, batch_id)

    assert final["batch"]["status"] == "failed"
    assert final["items"] == []
    assert final["failures"][0]["code"] == "INTERNAL"
    assert "模型服务挂了" in final["failures"][0]["message"]


def test_restart_marks_stuck_batch_failed(mock_model):
    """重启之后卡在 processing 的批次要被打断，而不是永远转圈。"""
    store.create_batch("B-STUCK-001")
    assert store.get_batch("B-STUCK-001").summary["status"] == "processing"

    interrupted = store.recover_interrupted()
    assert interrupted == 1

    after = store.get_batch("B-STUCK-001")
    assert after.summary["status"] == "failed"
    assert after.failures[0]["code"] == "INTERRUPTED"
    assert "重启" in after.failures[0]["message"]


def test_recover_leaves_finished_batches_alone(mock_model):
    body = upload(("a.png", make_png(1), "image/png"))
    assert store.recover_interrupted() == 0
    assert store.get_batch(body["batch_id"]).summary["status"] == body["status"]