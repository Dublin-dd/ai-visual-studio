import io

from PIL import Image, ImageDraw

from app.services import watermark


def _img_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _with_fake_watermark() -> bytes:
    """白色背景 + 右下角画一块灰色"水印"文字块。"""
    img = Image.new("RGB", (400, 300), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([300, 275, 390, 292], fill=(220, 220, 220))
    return _img_bytes(img)


def test_uniform_background_gets_patched():
    data = _with_fake_watermark()
    out, patched = watermark.strip_old_watermark(data)
    assert patched is True
    # 处理后该区域应更接近纯白（水印块被覆盖）
    assert watermark.watermark_region_stddev(out) <= watermark.watermark_region_stddev(data)


def test_busy_region_is_skipped():
    """角落被商品占据时不覆盖，避免擦坏商品。"""
    img = Image.new("RGB", (400, 300), (255, 255, 255))
    d = ImageDraw.Draw(img)
    # 右下角放一块高对比的花纹
    for x in range(300, 400, 4):
        d.line([(x, 270), (x + 4, 300)], fill=(10, 10, 10), width=3)
    data = _img_bytes(img)
    out, patched = watermark.strip_old_watermark(data)
    assert patched is False
    assert out == data


def test_size_unchanged():
    out, _ = watermark.strip_old_watermark(_with_fake_watermark())
    with Image.open(io.BytesIO(out)) as im:
        assert im.size == (400, 300)


def test_small_image_skipped():
    tiny = _img_bytes(Image.new("RGB", (40, 40), (255, 255, 255)))
    out, patched = watermark.strip_old_watermark(tiny)
    assert patched is False
    assert out == tiny


def test_disabled_by_config(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "WATERMARK_CLEAN_ENABLED", False)
    data = _with_fake_watermark()
    out, patched = watermark.strip_old_watermark(data)
    assert patched is False
    assert out == data
