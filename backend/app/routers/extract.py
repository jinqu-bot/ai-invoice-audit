"""抽取接口。前端「上传一张看识别结果」走的这里。"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

from app.config import settings
from app.services import store
from app.services.extract import ExtractionError, extract_one
from app.services.image import ImageError

router = APIRouter(prefix="/api", tags=["抽取"])

MAX_BYTES = settings.upload_max_mb * 1024 * 1024


@router.post("/extract", summary="识别单张发票")
async def extract_single(file: UploadFile = File(..., description="发票图片，JPG/PNG")):
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="文件是空的，请重新选择")
    if len(raw) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"图片超过 {settings.upload_max_mb}MB，请压缩后再传",
        )

    try:
        result = await extract_one(raw)
    except ImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ExtractionError as exc:
        raise HTTPException(status_code=502, detail=f"识别失败：{exc}") from exc

    image_id = store.save_image(raw, store.guess_mime(file.filename or ""))
    return {
        "extraction": result.model_dump(),
        "image_url": f"/api/files/{image_id}.jpg",
    }


@router.get("/files/{filename}", summary="回显已上传的图片")
async def get_file(filename: str):
    image_id = filename.rsplit(".", 1)[0]
    hit = store.get_image(image_id)
    if hit is None:
        raise HTTPException(status_code=404, detail="图片不存在或服务已重启")
    raw, mime = hit
    return Response(content=raw, media_type=mime, headers={"Cache-Control": "max-age=3600"})