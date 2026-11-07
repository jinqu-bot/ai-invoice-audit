"""应用入口。

本地启动（在 backend 目录下）：
    uvicorn app.main:app --reload --port 8000
打开 http://127.0.0.1:8000/docs 看全部接口，可以直接点“Try it out”。
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import batches, dashboard, extract, invoices, mock_media, policies, rules, system
from app.services import db, store

# 建库建表（幂等）。放在这里而不是 startup 事件里：
# 这样连 TestClient 也能开到同一份库，测试不用额外准备。
db.init()

# D6：后台审核任务活在内存里，重启就没了。上一次停在 processing 的批次
# 不处理会永远转圈，所以启动时统一标成"中断"并写明原因。
_INTERRUPTED = store.recover_interrupted()

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "AI 报销审核台后端。**D2 起上传的发票是真识别的**"
        "（图片压缩 → 视觉模型 → 四道关校验 → 置信度闸门）；"
        "**D4 起 verdict 由规则引擎算出**（R0–R8），每条驳回都指得出制度第几条。"
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

for module in (system, batches, extract, invoices, policies, rules, dashboard, mock_media):
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """422 也走同一套 {code, message, details} 形状。

    不接管的话，缺字段、字段类型不对这类错误会直接吐 FastAPI 原生结构，
    前端按 code/message 解析就会拿不到值。这也是 B 联调时问的第 6 条。
    """
    details: list[dict[str, str]] = []
    for err in exc.errors():
        # loc 形如 ["body", "files", 0] 或 ["query", "q"]，去掉来源标记，
        # 剩下的才是业务字段名——前端要拿它直接定位表单格子。
        parts = [
            str(part)
            for part in err.get("loc", ())
            if part not in ("body", "query", "path", "header", "cookie")
        ]
        details.append({"field": ".".join(parts) or "request", "reason": str(err.get("msg", ""))})

    first = details[0] if details else {"field": "request", "reason": "参数不合法"}
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": f"{first['field']}：{first['reason']}",
            "details": details,
        },
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
