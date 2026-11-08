"""送编辑模型前清理旧水印，避免模型把旧水印当画面内容重画，产生"重影"。

合规说明：本模块**不删除**平台水印，而是在编辑输入阶段覆盖旧水印区域，
最终产物仍由平台打一次新的合规标识。目的是避免多重水印叠加，
不是规避标识要求。

安全策略：只在目标区域"足够平坦"（接近背景）时才覆盖；
如果该角落被商品本体占据，则跳过，宁可保留重影也不擦坏商品。
"""

import io

from PIL import Image, ImageFilter, ImageStat

from .. import config


def _region_box(w: int, h: int) -> tuple[int, int, int, int]:
    """右下角水印区域（按比例估算）。"""
    return (
        int(w * config.WATERMARK_X_RATIO),
        int(h * config.WATERMARK_Y_RATIO),
        w,
        h,
    )


def strip_old_watermark(data: bytes) -> tuple[bytes, bool]:
    """覆盖旧水印区域，返回 (处理后的 PNG 字节, 是否做了覆盖)。"""
    if not config.WATERMARK_CLEAN_ENABLED:
        return data, False

    with Image.open(io.BytesIO(data)) as im:
        img = im.convert("RGB")
    w, h = img.size
    if w < 64 or h < 64:
        return data, False

    left, top, right, bottom = _region_box(w, h)
    region_w = right - left
    region_h = bottom - top

    region = img.crop((left, top, right, bottom))
    # 先模糊再算标准差：忽略水印笔画这类细线，只看区域整体是否平坦
    blurred = region.convert("L").filter(ImageFilter.GaussianBlur(4))
    stat = ImageStat.Stat(blurred)
    if stat.stddev[0] > config.WATERMARK_MAX_STDDEV:
        return data, False

    # 用区域正上方同样大小的补丁填充（背景通常连续）
    src_top = max(0, top - region_h)
    patch = img.crop((left, src_top, right, src_top + region_h))
    if patch.size != (region_w, region_h):
        patch = patch.resize((region_w, region_h))
    img.paste(patch, (left, top))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), True


def watermark_region_stddev(data: bytes) -> float:
    """目标区域的标准差（测试与诊断用）。"""
    with Image.open(io.BytesIO(data)) as im:
        img = im.convert("RGB")
    w, h = img.size
    left, top, right, bottom = _region_box(w, h)
    region = img.crop((left, top, right, bottom)).convert("L")
    return ImageStat.Stat(region.filter(ImageFilter.GaussianBlur(4))).stddev[0]
