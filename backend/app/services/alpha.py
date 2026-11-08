"""白底图转透明底（Pillow，不调用模型）。

思路：取 RGB 三通道的最小值作为"接近白色程度"，
高于阈值 → 全透明，低于阈值-feather → 不透明，之间线性过渡。
对硬边商品（瓶装/盒装/电子产品）效果好；白色商品区域可能被误透明（可调阈值）。
"""

import io

from PIL import Image, ImageChops

from .. import config


def white_to_alpha(
    data: bytes, threshold: int | None = None, feather: int | None = None
) -> bytes:
    """返回带 alpha 通道的 PNG 字节。"""
    threshold = config.CUTOUT_WHITE_THRESHOLD if threshold is None else threshold
    feather = config.CUTOUT_FEATHER if feather is None else feather

    with Image.open(io.BytesIO(data)) as im:
        rgb = im.convert("RGB")

    r, g, b = rgb.split()
    # 三通道取最小值：越白 → 值越大
    min_channel = ImageChops.darker(ImageChops.darker(r, g), b)

    low = max(0, threshold - max(1, feather))

    def _alpha(v: int) -> int:
        if v >= threshold:
            return 0
        if v <= low:
            return 255
        # 线性过渡：low → 255, threshold → 0
        span = max(1, threshold - low)
        return int(round(255 * (threshold - v) / span))

    alpha = min_channel.point(_alpha)
    out = rgb.convert("RGBA")
    out.putalpha(alpha)

    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def alpha_ratio(data: bytes) -> float:
    """透明像素占比（测试与质检用）。"""
    with Image.open(io.BytesIO(data)) as im:
        alpha = im.convert("RGBA").split()[-1]
        hist = alpha.histogram()
    total = sum(hist)
    if total == 0:
        return 0.0
    return hist[0] / total
