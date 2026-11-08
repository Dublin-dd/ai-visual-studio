from PIL import Image

from app import config
from app.services import render
from tests.conftest import make_project, png_bytes, upload


def _png(path, size=(40, 40), color=(200, 10, 10)):
    Image.new("RGB", size, color).save(path)
    return path


def test_render_single_layer(tmp_path):
    p = _png(tmp_path / "a.png")
    img = render.render_canvas(
        [{"path": str(p), "x": 0, "y": 0, "width": 100, "height": 100, "z": 1, "rotation": 0}],
        scale=1,
    )
    assert img.size == (config.BOARD_WIDTH, config.BOARD_HEIGHT)
    # 左上角 (5,5) 应是图层的红色
    assert img.convert("RGB").getpixel((5, 5)) == (200, 10, 10)
    # 远处应是白底
    assert img.convert("RGB").getpixel((900, 700)) == (255, 255, 255)


def test_render_respects_position(tmp_path):
    p = _png(tmp_path / "b.png", color=(0, 200, 0))
    img = render.render_canvas(
        [{"path": str(p), "x": 500, "y": 300, "width": 100, "height": 100, "z": 1, "rotation": 0}],
        scale=1,
    ).convert("RGB")
    assert img.getpixel((510, 310)) == (0, 200, 0)
    assert img.getpixel((10, 10)) == (255, 255, 255)


def test_render_layer_order(tmp_path):
    red = _png(tmp_path / "red.png", color=(255, 0, 0))
    blue = _png(tmp_path / "blue.png", color=(0, 0, 255))
    layers = [
        {"path": str(red), "x": 0, "y": 0, "width": 200, "height": 200, "z": 1, "rotation": 0},
        {"path": str(blue), "x": 0, "y": 0, "width": 200, "height": 200, "z": 2, "rotation": 0},
    ]
    img = render.render_canvas(layers, scale=1).convert("RGB")
    assert img.getpixel((50, 50)) == (0, 0, 255)


def test_render_scale(tmp_path):
    p = _png(tmp_path / "c.png")
    img = render.render_canvas(
        [{"path": str(p), "x": 0, "y": 0, "width": 100, "height": 100, "z": 1, "rotation": 0}],
        scale=2,
    )
    assert img.size == (config.BOARD_WIDTH * 2, config.BOARD_HEIGHT * 2)


def test_render_out_of_bounds_is_clipped(tmp_path):
    p = _png(tmp_path / "d.png")
    img = render.render_canvas(
        [{"path": str(p), "x": 900, "y": 600, "width": 400, "height": 400, "z": 1, "rotation": 0}],
        scale=1,
    )
    assert img.size == (config.BOARD_WIDTH, config.BOARD_HEIGHT)


def test_render_rotation_does_not_crash(tmp_path):
    p = _png(tmp_path / "e.png", size=(60, 30))
    img = render.render_canvas(
        [{"path": str(p), "x": 100, "y": 100, "width": 200, "height": 100, "z": 1, "rotation": 30}],
        scale=1,
    )
    assert img.size == (config.BOARD_WIDTH, config.BOARD_HEIGHT)


def test_render_empty_raises():
    try:
        render.render_canvas([])
    except render.RenderError as e:
        assert e.code == "EMPTY_CANVAS"
    else:
        raise AssertionError("空画布应抛错")


def test_render_missing_file(tmp_path):
    try:
        render.render_canvas(
            [{"path": str(tmp_path / "nope.png"), "x": 0, "y": 0, "width": 10, "height": 10, "z": 1}],
            scale=1,
        )
    except render.RenderError as e:
        assert e.code == "LAYER_FILE_MISSING"
    else:
        raise AssertionError("缺文件应抛错")


def test_render_zero_size_guard(tmp_path):
    p = _png(tmp_path / "f.png")
    img = render.render_canvas(
        [{"path": str(p), "x": 0, "y": 0, "width": 0, "height": 0, "z": 1, "rotation": 0}],
        scale=1,
    )
    assert img.size == (config.BOARD_WIDTH, config.BOARD_HEIGHT)


# --- API 层 ---


def test_export_creates_asset(client):
    pid = make_project(client)
    aid = upload(client, pid).json()["id"]
    client.put(
        f"/api/projects/{pid}/layers",
        json={"layers": [{"asset_id": aid, "x": 10, "y": 10, "width": 100, "height": 100, "z": 1, "rotation": 0}]},
    )
    resp = client.post(f"/api/projects/{pid}/export")
    assert resp.status_code == 201, resp.text
    asset = resp.json()["asset"]
    assert asset["kind"] == "export"
    assert asset["width"] == config.BOARD_WIDTH * config.EXPORT_SCALE
    assert asset["height"] == config.BOARD_HEIGHT * config.EXPORT_SCALE
    # 能读回文件
    got = client.get(asset["url"])
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("image/")


def test_export_empty_canvas(client):
    pid = make_project(client)
    resp = client.post(f"/api/projects/{pid}/export")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "EMPTY_CANVAS"


def test_export_project_not_found(client):
    resp = client.post("/api/projects/nope/export")
    assert resp.status_code == 404


def test_export_appears_in_asset_list(client):
    pid = make_project(client)
    aid = upload(client, pid).json()["id"]
    client.put(
        f"/api/projects/{pid}/layers",
        json={"layers": [{"asset_id": aid, "x": 0, "y": 0, "width": 50, "height": 50, "z": 1, "rotation": 0}]},
    )
    client.post(f"/api/projects/{pid}/export")
    exports = client.get(f"/api/projects/{pid}/assets?kind=export").json()["items"]
    assert len(exports) == 1
    assert exports[0]["kind"] == "export"


def test_asset_list_bad_kind(client):
    pid = make_project(client)
    resp = client.get(f"/api/projects/{pid}/assets?kind=audio")
    assert resp.status_code == 422


def test_saved_board_color_matches_export(client):
    from io import BytesIO
    pid = make_project(client)
    url = f"/api/projects/{pid}"
    assert client.get(url).json()["background_color"] == "#FFFFFF"
    aid = upload(client, pid).json()["id"]
    client.put(url + "/layers", json={"layers": [{"asset_id": aid, "x": 10, "y": 10}]})
    for color in ("#EAE6DF", "#134B62"):
        assert client.put(url + "/background", json={"color": color}).status_code == 200
        assert client.get(url).json()["background_color"] == color
        asset = client.post(url + "/export").json()["asset"]
        with Image.open(BytesIO(client.get(asset["url"]).content)) as img:
            assert img.getpixel((0, 0)) == tuple(bytes.fromhex(color[1:]))
    assert client.put(url + "/background", json={"color": "unknown"}).status_code == 422
