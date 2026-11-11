"""健康检查与元信息。B 用它确认后端通不通。

11/11 起这里多带三个字段：`model_ok` / `last_error` / `consecutive_failures`。
理由很具体——那天账户余额 -0.01，`recognition_provider` 照样报 `openai-compat`，
健康检查全绿，直到用户上传才炸。**配着 key 不等于模型能用。**
"""

from datetime import datetime

from fastapi import APIRouter

from app.config import settings
from app.schemas import Health
from app.services import model_health

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=Health, summary="健康检查")
def health() -> Health:
    mh = model_health.snapshot()
    return Health(
        app=settings.app_name,
        version=settings.version,
        stage=settings.stage,
        recognition_provider="openai-compat" if settings.has_vlm else "mock-vlm",
        demo_mode=settings.demo_mode,
        server_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        model_ok=bool(mh.get("model_ok")),
        last_ok_at=mh.get("last_ok_at"),
        last_error=mh.get("last_error"),
        consecutive_failures=int(mh.get("consecutive_failures") or 0),
    )