"""测试辅助：等后台任务跑完。

D6 起上传是两段式的——`POST` 立刻返回 202，真正的审核在后台任务里跑。
所以测试不能假设"POST 返回了就审完了"，必须像前端兜底那样轮询 `/results`，
等 `status` 不再是 `processing`。

这条路径本身就是被测行为：**现场网络断了的时候，前端就是靠这个轮询拿结果的。**
测试天天跑它，等于天天验一次兜底。
"""

from __future__ import annotations

import time


def wait_done(client, batch_id: str, timeout: float = 10.0) -> dict:
    """轮询直到批次跑完，返回最后一版 `/results`。"""
    deadline = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < deadline:
        body = client.get(f"/api/batches/{batch_id}/results").json()
        if body["batch"]["status"] != "processing":
            return body
        time.sleep(0.02)
    raise AssertionError(f"批次 {batch_id} 在 {timeout}s 内没跑完：{body}")


def upload_and_wait(client, files) -> dict:
    """上传并等到跑完，返回"收口后的批次概要 + 失败清单"。

    返回的形状对齐 D5 时代的同步响应（`status` / `invoice_count` / `failed` 都在顶层），
    这样断言写起来还是同一句话，同时又真的走了一遍"202 → 轮询"的新契约。
    """
    resp = client.post("/api/batches", files=files)
    assert resp.status_code == 202, resp.text
    posted = resp.json()
    body = wait_done(client, posted["batch_id"])
    merged = dict(body["batch"])
    merged["failed"] = body["failures"]
    merged["next_action"] = posted["next_action"]
    return merged