"""应用入口。

本地启动（在 backend 目录下）：
    uvicorn app.main:app --reload --port 8000
打开 http://127.0.0.1:8000/docs 看全部接口，可以直接点“Try it out”。
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import batches, dashboard, extract, invoices, mock_media, policies, system

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "AI 报销审核台后端。**D2 起上传的发票是真识别的**"
        "（图片压缩 → 视觉模型 → 四道关校验 → 置信度闸门）。"
        "`?demo=true` 仍走固定演示批次，保证答辩演示稳定。"
    ),
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (system, batches, extract, invoices, policies, dashboard, mock_media):
    app.include_router(module.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """统一错误形状，前端不用猜是 detail 还是 message。"""
    code = {
        400: "BAD_REQUEST",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        413: "FILE_TOO_LARGE",
        422: "VALIDATION_ERROR",
        502: "UPSTREAM_ERROR",
    }.get(exc.status_code, "ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": code, "message": str(exc.detail)},
    )


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "app": settings.app_name,
        "stage": settings.stage,
        "docs": "/docs",
        "health": "/api/health",
        "extract": "/api/extract",
        "demo_batch": "/api/batches/B20261104-001/results",
    }
