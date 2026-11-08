"""健康检查与元信息。B 用它确认后端通不通。"""

from datetime import datetime

from fastapi import APIRouter

from app.config import settings
from app.schemas import Health

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=Health, summary="健康检查")
def health() -> Health:
    return Health(
        app=settings.app_name,
        version=settings.version,
        stage=settings.stage,
        recognition_provider="openai-compat" if settings.has_vlm else "mock-vlm",
        demo_mode=settings.demo_mode,
        server_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
