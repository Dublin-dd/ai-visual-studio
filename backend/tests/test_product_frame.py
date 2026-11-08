"""商品首帧预处理测试：9:16 画布、白底判断、主体完整不裁切。"""

import io

from PIL import Image

from app.services.product_frame import TARGET_H, TARGET_W, to_vertical_canvas


def _solid(w: int, h: int, color=(255, 255, 255)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG")
    return buf.getvalue()


def test_square_image_becomes_vertical():
    out = to_vertical_canvas(_solid(600, 600))
    im = Image.open(io.BytesIO(out))
    assert im.size == (TARGET_W, TARGET_H)
    assert abs(im.width / im.height - 9 / 16) < 1e-6


def test_wide_image_becomes_vertical():
    out = to_vertical_canvas(_solid(1600, 900))
    im = Image.open(io.BytesIO(out))
    assert im.size == (TARGET_W, TARGET_H)


def test_tall_image_becomes_vertical():
    out = to_vertical_canvas(_solid(800, 2000))
    im = Image.open(io.BytesIO(out))
    assert im.size == (TARGET_W, TARGET_H)


def test_white_background_detected_uses_white_canvas():
    """白底图的画布边角应该是纯白，不带模糊背景色。"""
    out = to_vertical_canvas(_solid(600, 800, (255, 255, 255)))
    im = Image.open(io.BytesIO(out)).convert("RGB")
    corner = im.getpixel((3, 3))
    assert all(c >= 250 for c in corner), corner


def test_non_white_background_is_cover_cropped():
    """非白底场景图按 9:16 裁切铺满，不造模糊边框。"""
    from PIL import ImageDraw

    src = Image.new("RGB", (600, 600), (200, 200, 200))
    draw = ImageDraw.Draw(src)
    draw.rectangle([0, 0, 600, 299], fill=(20, 20, 20))
    draw.rectangle([0, 300, 600, 599], fill=(240, 240, 240))
    buf = io.BytesIO()
    src.save(buf, format="PNG")

    out = to_vertical_canvas(buf.getvalue())
    im = Image.open(io.BytesIO(out)).convert("RGB")
    assert im.size == (TARGET_W, TARGET_H)
    # 上下两侧应该延续原场景（上暗下亮），而不是统一的模糊底色
    top = im.getpixel((TARGET_W // 2, 10))
    bottom = im.getpixel((TARGET_W // 2, TARGET_H - 10))
    assert sum(top) / 3 < sum(bottom) / 3


def test_output_is_png():
    out = to_vertical_canvas(_solid(500, 500))
    assert out[:8] == b"\x89PNG\r\n\x1a\n"


def test_zoom_for_scene():
    from app.services.product_frame import DEFAULT_ZOOM, zoom_for_scene

    assert zoom_for_scene("特写") > zoom_for_scene("近景") > zoom_for_scene("中景")
    assert zoom_for_scene("中景") > zoom_for_scene("远景")
    assert zoom_for_scene("") == DEFAULT_ZOOM
    assert zoom_for_scene("奇怪的景别") == DEFAULT_ZOOM


def test_scene_zoom_changes_composition():
    """同一张图，不同景别应产生不同的商品占比（画面像素不同）。"""
    import io

    from PIL import Image, ImageDraw

    # 白底 + 中间一个小方块当商品，四周留白很大
    src = Image.new("RGB", (800, 800), (255, 255, 255))
    draw = ImageDraw.Draw(src)
    draw.rectangle([300, 300, 500, 620], fill=(180, 120, 40))
    buf = io.BytesIO()
    src.save(buf, format="PNG")
    raw = buf.getvalue()

    close = to_vertical_canvas(raw, scene="特写")
    wide = to_vertical_canvas(raw, scene="远景")
    assert close != wide

    def brown_area(data: bytes) -> int:
        im = Image.open(io.BytesIO(data)).convert("RGB")
        px = im.load()
        count = 0
        for y in range(0, im.height, 4):
            for x in range(0, im.width, 4):
                r, g, b = px[x, y]
                if r > 120 and g < 180 and b < 120 and r - b > 40:
                    count += 1
        return count

    assert brown_area(close) > brown_area(wide)


def test_plain_background_subject_is_cropped_and_enlarged():
    """白底大留白图：应先裁到主体再放大，主体占比明显提升。"""
    import io

    from PIL import Image, ImageDraw

    src = Image.new("RGB", (1000, 1000), (255, 255, 255))
    draw = ImageDraw.Draw(src)
    draw.rectangle([430, 430, 570, 700], fill=(160, 60, 40))
    buf = io.BytesIO()
    src.save(buf, format="PNG")

    out = to_vertical_canvas(buf.getvalue(), scene="近景")
    im = Image.open(io.BytesIO(out)).convert("RGB")
    px = im.load()
    red = sum(
        1
        for y in range(0, im.height, 3)
        for x in range(0, im.width, 3)
        if px[x, y][0] > 120 and px[x, y][1] < 120
    )
    total = (im.width // 3) * (im.height // 3)
    assert red / total > 0.15, "主体应占据画面相当比例"


def test_scene_image_zoom_direction_not_inverted():
    """场景图：特写的商品占比必须大于全景（防止方向写反）。"""
    import io

    from PIL import Image, ImageDraw

    # 非白底场景图（灰色背景 + 大理石感），中间一个显眼的红色方块当商品
    src = Image.new("RGB", (1000, 1000), (170, 170, 175))
    draw = ImageDraw.Draw(src)
    for i in range(0, 1000, 100):
        draw.rectangle([i, 600, i + 50, 1000], fill=(200, 200, 205))
    draw.rectangle([430, 380, 570, 660], fill=(200, 40, 40))
    buf = io.BytesIO()
    src.save(buf, format="PNG")
    raw = buf.getvalue()

    def red_ratio(data: bytes) -> float:
        im = Image.open(io.BytesIO(data)).convert("RGB")
        px = im.load()
        red = 0
        total = 0
        for y in range(0, im.height, 4):
            for x in range(0, im.width, 4):
                r, g, b = px[x, y]
                total += 1
                if r > 150 and g < 110 and b < 110:
                    red += 1
        return red / max(1, total)

    close = red_ratio(to_vertical_canvas(raw, scene="特写"))
    wide = red_ratio(to_vertical_canvas(raw, scene="全景"))
    assert close > wide * 1.5, (close, wide)
