"""商品首帧预处理：把任意比例的商品图放进 9:16 竖屏画布。

为什么需要：视频模型输出分辨率跟随首帧。带货视频要发抖音，必须 9:16；
用户上传的商品图往往是方图或横图，直接当首帧会得到非竖屏结果。

两个关键能力：
1. 智能裁到主体：纯色/白底商品图往往四周留白很多，先裁到商品外接框，
   再按景别缩放，商品才不会在画面里显得很小。
2. 按景别控制占比：特写/近景/中景/远景对应不同的商品占比，
   同一个商品图能产出构图明显不同的首帧，让成片里的镜头有真实变化。

纯本地运算，零成本，不调用任何模型。
"""

from __future__ import annotations

import io

from PIL import Image, ImageChops

# 抖音 / 快手竖屏标准
TARGET_W = 720
TARGET_H = 1280

# 景别 → 商品目标占比（相对画布高度）
SCENE_ZOOM = {
    "特写": 0.95,
    "近景": 0.80,
    "中景": 0.62,
    "全景": 0.46,
    "远景": 0.34,
}
DEFAULT_ZOOM = 0.72


def zoom_for_scene(scene: str) -> float:
    text = str(scene or "").strip()
    for key, value in SCENE_ZOOM.items():
        if key in text:
            return value
    return DEFAULT_ZOOM


def _border_color(src: Image.Image) -> tuple[int, int, int]:
    """取四条边像素的中位数作为背景色估计。"""
    w, h = src.size
    step = max(1, min(w, h) // 50)
    samples: list[tuple[int, int, int]] = []
    for x in range(0, w, step):
        samples.append(src.getpixel((x, 0)))
        samples.append(src.getpixel((x, h - 1)))
    for y in range(0, h, step):
        samples.append(src.getpixel((0, y)))
        samples.append(src.getpixel((w - 1, y)))
    if not samples:
        return (255, 255, 255)
    rs = sorted(p[0] for p in samples)
    gs = sorted(p[1] for p in samples)
    bs = sorted(p[2] for p in samples)
    mid = len(rs) // 2
    return (rs[mid], gs[mid], bs[mid])


def _is_plain_background(src: Image.Image, threshold: int = 238) -> bool:
    """粗判商品图是否为纯色（白底）背景：看四条边上的像素。"""
    w, h = src.size
    step = max(1, min(w, h) // 40)
    samples: list[int] = []
    for x in range(0, w, step):
        for y in (0, h - 1):
            px = src.getpixel((x, y))
            samples.append(sum(px) // 3)
    for y in range(0, h, step):
        for x in (0, w - 1):
            px = src.getpixel((x, y))
            samples.append(sum(px) // 3)
    if not samples:
        return False
    avg = sum(samples) / len(samples)
    return avg >= threshold and (max(samples) - min(samples)) <= 20


def _subject_bbox(src: Image.Image, tol: int = 18) -> tuple[int, int, int, int] | None:
    """纯色背景下找出主体外接框；找不到或过大过小时返回 None。

    用 PIL 的 difference + getbbox，C 层实现，速度足够。
    """
    bg = Image.new("RGB", src.size, _border_color(src))
    diff = ImageChops.difference(src, bg).convert("L")
    mask = diff.point(lambda v: 255 if v > tol else 0)
    box = mask.getbbox()
    if box is None:
        return None
    left, top, right, bottom = box
    w = right - left
    h = bottom - top
    if w <= 0 or h <= 0:
        return None
    # 主体过小（噪声）或几乎整图（判断不可靠）时不裁
    if w * h < src.width * src.height * 0.01:
        return None
    if w > src.width * 0.98 and h > src.height * 0.98:
        return None
    return box


def _expand(box: tuple[int, int, int, int], pad_ratio: float, w: int, h: int):
    left, top, right, bottom = box
    pw = int((right - left) * pad_ratio)
    ph = int((bottom - top) * pad_ratio)
    return (
        max(0, left - pw),
        max(0, top - ph),
        min(w, right + pw),
        min(h, bottom + ph),
    )


def to_vertical_canvas(
    image_bytes: bytes,
    target_w: int = TARGET_W,
    target_h: int = TARGET_H,
    zoom: float | None = None,
    scene: str | None = None,
) -> bytes:
    """把商品图转成 target_w×target_h 的竖屏首帧，返回 PNG 字节。

    zoom 为商品目标占比（相对画布高度）；也可传 scene（特写/近景/中景/全景/远景）自动换算。
    - 白底图：先裁到主体，再按 zoom 缩放居中，背景纯白
    - 场景图：按 9:16 居中裁切，再按 zoom 放大
    """
    if zoom is None:
        zoom = zoom_for_scene(scene) if scene else DEFAULT_ZOOM
    zoom = max(0.2, min(1.0, float(zoom)))

    with Image.open(io.BytesIO(image_bytes)) as im:
        src = im.convert("RGB")

    plain = _is_plain_background(src)

    if plain:
        box = _subject_bbox(src)
        if box is not None:
            src = src.crop(_expand(box, 0.06, src.width, src.height))

        canvas = Image.new("RGB", (target_w, target_h), (255, 255, 255))
        target_h_px = target_h * zoom
        scale = min(target_w / src.width, target_h_px / src.height)
        fg_w = max(1, int(src.width * scale))
        fg_h = max(1, int(src.height * scale))
        fg = src.resize((fg_w, fg_h), Image.LANCZOS)
        canvas.paste(fg, ((target_w - fg_w) // 2, (target_h - fg_h) // 2))
    else:
        # 场景图：先铺满 9:16，再按景别做中心裁切后放大。
        # 注意方向：zoom 越大（特写）→ 保留的画面区域越小 → 商品越大。
        # 把 zoom(0.34~0.95) 映射到保留比例(1.0~0.55)。
        keep = 1.0 - (zoom - 0.34) * (0.45 / 0.61)
        keep = max(0.35, min(1.0, keep))
        base = _cover(src, target_w, target_h)
        if keep >= 0.99:
            canvas = base
        else:
            crop_w = max(2, int(target_w * keep))
            crop_h = max(2, int(target_h * keep))
            left = (target_w - crop_w) // 2
            top = (target_h - crop_h) // 2
            canvas = base.crop((left, top, left + crop_w, top + crop_h)).resize(
                (target_w, target_h), Image.LANCZOS
            )

    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _cover(src: Image.Image, w: int, h: int) -> Image.Image:
    """等比缩放到完全覆盖 w×h 后居中裁剪。"""
    scale = max(w / src.width, h / src.height)
    nw = max(1, int(src.width * scale))
    nh = max(1, int(src.height * scale))
    resized = src.resize((nw, nh), Image.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return resized.crop((left, top, left + w, top + h))
