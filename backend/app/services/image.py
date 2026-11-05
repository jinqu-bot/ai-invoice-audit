"""图片处理：指纹、压缩、转 base64。

为什么要压：手机拍一张 5MB，直接丢给模型又慢又贵。压到 1024 长边，
票面文字仍然清楚，体积降到 10%~20%，延迟和费用都下来了。
"""

from __future__ import annotations

import base64
import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError


class ImageError(Exception):
    """图片不可用（不是图片、损坏、尺寸异常）。"""


@dataclass
class PreparedImage:
    data: bytes
    mime: str
    width: int
    height: int
    original_bytes: int

    @property
    def compressed_bytes(self) -> int:
        return len(self.data)

    @property
    def b64(self) -> str:
        return base64.b64encode(self.data).decode()

    @property
    def data_uri(self) -> str:
        return f"data:{self.mime};base64,{self.b64}"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def prepare_image(raw: bytes, max_edge: int = 1024, quality: int = 85) -> PreparedImage:
    """打开 → 修正方向 → 缩到 max_edge → 转 JPEG。

    统一转 JPEG 是因为不同模型对 PNG/WebP/HEIC 的兼容性参差不齐，
    JPEG 是最稳的。透明通道铺白底，避免转出来是黑块。
    """
    if not raw:
        raise ImageError("空文件")

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageError("无法识别的图片格式，请上传 JPG / PNG") from exc

    img = ImageOps.exif_transpose(img)

    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        img = background
    else:
        img = img.convert("RGB")

    # thumbnail 会保持比例，且不会把小图放大
    img.thumbnail((max_edge, max_edge), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)

    return PreparedImage(
        data=buf.getvalue(),
        mime="image/jpeg",
        width=img.width,
        height=img.height,
        original_bytes=len(raw),
    )
