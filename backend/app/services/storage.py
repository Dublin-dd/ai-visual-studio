"""文件落盘：安全文件名、格式与大小校验、真实类型校验。"""

import io
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .. import config

_EXT_BY_FORMAT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}


class UploadRejected(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def validate_image_bytes(data: bytes) -> tuple[str, int, int]:
    """校验真实图片类型，返回 (format, width, height)。不信任 Content-Type。"""
    if not data:
        raise UploadRejected("EMPTY_FILE", "文件为空")
    if len(data) > config.MAX_UPLOAD_BYTES:
        limit_mb = config.MAX_UPLOAD_BYTES // (1024 * 1024)
        raise UploadRejected("FILE_TOO_LARGE", f"文件超过 {limit_mb}MB 限制")
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = (im.format or "").upper()
            im.verify()
        # verify() 之后需要重新打开才能读尺寸
        with Image.open(io.BytesIO(data)) as im2:
            width, height = im2.size
    except (UnidentifiedImageError, OSError):
        raise UploadRejected("UNSUPPORTED_FORMAT", "不支持的图片格式，仅支持 JPG / PNG / WebP")
    if fmt not in config.ALLOWED_UPLOAD_FORMAT:
        raise UploadRejected("UNSUPPORTED_FORMAT", "不支持的图片格式，仅支持 JPG / PNG / WebP")
    return fmt, width, height


def save_upload(data: bytes, fmt: str) -> tuple[Path, str, int]:
    """用服务端生成的 UUID 做文件名，杜绝路径遍历。返回 (path, filename, size)。"""
    ext = _EXT_BY_FORMAT.get(fmt, ".bin")
    name = f"{uuid.uuid4().hex}{ext}"
    path = config.UPLOAD_DIR / name
    path.write_bytes(data)
    return path, name, len(data)


def save_generated(data: bytes, fmt_hint: str = "PNG") -> tuple[Path, str, int, int, str]:
    """保存生成图，返回 (path, filename, width, height, mime)。"""
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt = (im.format or fmt_hint).upper()
            width, height = im.size
    except (UnidentifiedImageError, OSError):
        raise UploadRejected("BAD_IMAGE", "生成服务返回的内容不是有效图片")
    ext = _EXT_BY_FORMAT.get(fmt, ".png")
    mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(fmt, "image/png")
    name = f"{uuid.uuid4().hex}{ext}"
    path = config.GENERATED_DIR / name
    path.write_bytes(data)
    return path, name, width, height, mime
