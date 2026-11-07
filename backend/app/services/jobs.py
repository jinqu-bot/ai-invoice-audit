"""批次任务与事件总线（D6）。

以前 `POST /api/batches` 要等全部识别完才返回，`/stream` 再把存好的轨迹
按节奏播一遍——那是**动画**，不是进度。D6 把它拆成两半：

1. `POST` 立刻建批次、存图、起一个后台任务，返回 202；
2. 后台任务每审完一张就往事件总线推事件，SSE 客户端按顺序收。

**为什么用线程而不是 asyncio.create_task**：任务挂在请求的事件循环上时，
任何"请求结束就回收循环"的部署方式（测试客户端就是这样）都会把批次悄悄掐死，
表现是永远转圈。线程 + 自己的事件循环，批次的寿命和请求彻底解耦，
换个 ASGI 服务器也不用重新想这件事。

**为什么 SSE 用轮询而不是阻塞队列**：事件频率是"每张票几条"，几十毫秒的
轮询延迟看不出来；而要把阻塞队列塞进 async 生成器，还得绕一层线程池，
代码复杂度换不来任何体验提升。

**为什么事件要留在内存里回放**：页面刷新、开第二个标签页都会重新订阅，
不留一份就得让前端处理"我连晚了"。留着的代价是每批几十 KB。

进程重启后任务和事件都会丢：`store.recover_interrupted()` 会把还停在
`processing` 的批次标成 `failed` 并写明原因，不让页面无限转圈。
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

# SSE 取事件的最小间隔。事件频率低，30ms 足够"跟手"。
_POLL_SECONDS = 0.03


@dataclass
class Job:
    batch_id: str
    _events: list[dict[str, Any]] = field(default_factory=list)
    _finished: bool = False
    _cv: threading.Condition = field(default_factory=threading.Condition)

    def emit(self, event: str, data: dict[str, Any]) -> None:
        with self._cv:
            self._events.append({"event": event, "data": data})
            self._cv.notify_all()

    def finish(self) -> None:
        with self._cv:
            self._finished = True
            self._cv.notify_all()

    @property
    def finished(self) -> bool:
        with self._cv:
            return self._finished

    def since(self, index: int) -> list[dict[str, Any]]:
        with self._cv:
            return self._events[index:]

    async def stream(self, start: int = 0) -> AsyncIterator[dict[str, Any]]:
        """从第 start 条开始，先补历史再等新事件，直到任务结束。"""
        index = start
        while True:
            for item in self.since(index):
                index += 1
                yield item
            if self.finished:
                # 收尾：finish 之后可能还有一条刚 emit 的事件，再取一遍
                tail = self.since(index)
                if not tail:
                    return
                for item in tail:
                    index += 1
                    yield item
                continue
            await asyncio.sleep(_POLL_SECONDS)


_JOBS: dict[str, Job] = {}
_MAX_JOBS = 50  # 只留最近 50 批的事件，防止长跑之后内存一直涨


def create(batch_id: str) -> Job:
    job = Job(batch_id)
    _JOBS[batch_id] = job
    if len(_JOBS) > _MAX_JOBS:
        # 先淘汰已经跑完的老批次；还在跑的一张都不能动
        for old_id, old in list(_JOBS.items()):
            if old.finished:
                _JOBS.pop(old_id, None)
                if len(_JOBS) <= _MAX_JOBS:
                    break
    return job


def get(batch_id: str) -> Job | None:
    return _JOBS.get(batch_id)


def forget(batch_id: str) -> None:
    """释放某个批次的事件缓存（测试用；线上留着换页面刷新能补发）。"""
    _JOBS.pop(batch_id, None)


def reset() -> None:
    """测试用：清空所有任务与事件。"""
    _JOBS.clear()


def start_job(coro: Any, name: str = "batch") -> threading.Thread:
    """在新线程里跑一个协程：批次寿命与请求无关。"""

    def _run() -> None:
        try:
            asyncio.run(coro)
        except Exception:  # pragma: no cover - 兜底日志，正常由 runner 收口
            logger.exception("批次任务异常退出：%s", name)

    thread = threading.Thread(target=_run, name=name, daemon=True)
    thread.start()
    return thread