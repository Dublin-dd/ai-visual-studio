"""画布合成：把图层按位置/尺寸/旋转贴到一张画布上，导出 PNG。

纯本地运算，不调用模型，零成本。
坐标约定：画布左上角为原点；导出时整体按 EXPORT_SCALE 放大。
"""

import uuid
from pathlib import Path

from PIL import Image

from .. import config


class RenderError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _target_size(layer: dict, scale: int) -> tuple[int, int]:
    return (
        max(1, int(round(float(layer.get("width", 0)) * scale))),
        max(1, int(round(float(layer.get("height", 0)) * scale))),
    )


def _load_layer_image(layer: dict, scale: int) -> Image.Image:
    path = Path(layer["path"])
    if not path.exists():
        raise RenderError("LAYER_FILE_MISSING", "有图层文件已丢失，请先移除该图层")
    with Image.open(path) as im:
        img = im.convert("RGBA")
    target = _target_size(layer, scale)
    if img.size != target:
        img = img.resize(target, Image.LANCZOS)
    rotation = float(layer.get("rotation", 0) or 0)
    if rotation:
        # CSS 的 rotate 为顺时针，PIL 为逆时针，故取负值
        img = img.rotate(-rotation, expand=True, resample=Image.BICUBIC)
    return img


def render_canvas(layers: list[dict], scale: int | None = None, *, background: str = "#FFFFFF") -> Image.Image:
    """合成画布。

    layers 每项：{path, x, y, width, height, z, rotation}（可带 index 保持同 z 顺序）。
    返回 RGBA 图片，尺寸为 BOARD_WIDTH*scale × BOARD_HEIGHT*scale。
    """
    if not layers:
        raise RenderError("EMPTY_CANVAS", "画布为空，先添加素材再导出")

    scale = scale or config.EXPORT_SCALE
    board_w = config.BOARD_WIDTH * scale
    board_h = config.BOARD_HEIGHT * scale
    canvas = Image.new("RGBA", (board_w, board_h), background)

    ordered = sorted(
        enumerate(layers), key=lambda pair: (pair[1].get("z", 0), pair[0])
    )
    for _, layer in ordered:
        img = _load_layer_image(layer, scale)
        x = float(layer.get("x", 0)) * scale
        y = float(layer.get("y", 0)) * scale
        # 以图层原始框的中心为锚点贴回，旋转后仍居中
        target_w, target_h = _target_size(layer, scale)
        cx = x + target_w / 2
        cy = y + target_h / 2
        left = int(round(cx - img.width / 2))
        top = int(round(cy - img.height / 2))

        # 先贴到同尺寸透明层再叠加，避免 paste 覆盖下方图层的透明区域
        tile = Image.new("RGBA", (board_w, board_h), (0, 0, 0, 0))
        tile.paste(img, (left, top), img)
        canvas = Image.alpha_composite(canvas, tile)

    return canvas


def save_export(img: Image.Image, directory: Path | None = None) -> tuple[Path, str, int]:
    """保存导出文件（PNG），返回 (路径, 文件名, 字节数)。"""
    directory = directory or config.EXPORT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{uuid.uuid4().hex}.png"
    path = directory / name
    img.convert("RGB").save(path, format="PNG", optimize=True)
    return path, name, path.stat().st_size
