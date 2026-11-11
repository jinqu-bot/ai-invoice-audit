"""模型可用性的"体温计"：只记最近一次成功/失败，不花钱。

为什么要有它：
`/api/health` 只看"有没有配 key"，配了就报 `openai-compat`。
但 key 配着、账户欠费、模型 402，健康检查照样说一切正常——**这就是在演**。
11/11 就真的踩到了：余额 -0.01，健康检查还是绿的，直到用户上传才炸。

这里不加探活请求（每次探活都要花钱），只在真实调用失败时记一笔，
健康检查把"最近一次模型错误"如实带出去。演示前看一眼 `/api/health` 就知道模型行不行。
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

_lock = threading.Lock()
_state: dict[str, Any] = {
    "last_ok_at": None,
    "last_error_at": None,
    "last_error": None,
    "consecutive_failures": 0,
}


def record_ok() -> None:
    with _lock:
        _state["last_ok_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _state["consecutive_failures"] = 0
        _state["last_error"] = None


def record_failure(message: str) -> None:
    with _lock:
        _state["last_error_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _state["last_error"] = str(message)[:300]
        _state["consecutive_failures"] = int(_state["consecutive_failures"] or 0) + 1


def snapshot() -> dict[str, Any]:
    """给 /api/health 用。只读，不改状态。"""
    with _lock:
        data = dict(_state)
    data["model_ok"] = bool(
        data["last_ok_at"] and not data["last_error"]
    )
    return data


def reset() -> None:
    with _lock:
        _state.update(last_ok_at=None, last_error_at=None, last_error=None,
                      consecutive_failures=0)