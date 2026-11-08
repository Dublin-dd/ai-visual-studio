import io
from unittest.mock import patch

from PIL import Image

from app.services import alpha, edit_client, task_runner
from tests.conftest import make_project, png_bytes, upload


# ---------- alpha 纯函数 ----------


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_white_becomes_transparent():
    img = Image.new("RGB", (20, 20), (255, 255, 255))
    out = alpha.white_to_alpha(_png_bytes(img))
    assert alpha.alpha_ratio(out) > 0.99


def test_solid_color_stays_opaque():
    img = Image.new("RGB", (20, 20), (10, 20, 200))
    out = alpha.white_to_alpha(_png_bytes(img))
    assert alpha.alpha_ratio(out) < 0.01


def test_mixed_image_keeps_subject():
    img = Image.new("RGB", (40, 40), (255, 255, 255))
    for x in range(10, 30):
        for y in range(10, 30):
            img.putpixel((x, y), (120, 60, 30))
    out = alpha.white_to_alpha(_png_bytes(img))
    ratio = alpha.alpha_ratio(out)
    assert 0.2 < ratio < 0.9


def test_gray_edge_is_semi_transparent():
    img = Image.new("RGB", (10, 10), (240, 240, 240))
    out = alpha.white_to_alpha(_png_bytes(img), threshold=245, feather=10)
    img2 = Image.open(io.BytesIO(out)).convert("RGBA")
    a = img2.getpixel((5, 5))[3]
    assert 0 < a < 255


def test_threshold_high_keeps_more():
    img = Image.new("RGB", (10, 10), (250, 250, 250))
    low = alpha.alpha_ratio(alpha.white_to_alpha(_png_bytes(img), threshold=240, feather=5))
    high = alpha.alpha_ratio(alpha.white_to_alpha(_png_bytes(img), threshold=255, feather=5))
    assert low > high


# ---------- 任务校验 ----------


def _create(client, pid, **kw):
    body = {"project_id": pid, "prompt": "场景", "width": 1024, "height": 1024, "count": 1}
    body.update(kw)
    return client.post("/api/tasks", json=body)


def test_cutout_requires_source(client):
    pid = make_project(client)
    resp = _create(client, pid, kind="cutout")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SOURCE_REQUIRED"


def test_image_edit_requires_prompt(client):
    pid = make_project(client)
    aid = upload(client, pid).json()["id"]
    resp = _create(client, pid, kind="image_edit", source_asset_id=aid, prompt="")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "PROMPT_REQUIRED"


def test_source_from_other_project_rejected(client):
    pid = make_project(client)
    other = make_project(client)
    foreign = upload(client, other).json()["id"]
    resp = _create(client, pid, kind="cutout", source_asset_id=foreign)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SOURCE_NOT_FOUND"


def test_sku_requires_colors(client):
    pid = make_project(client)
    aid = upload(client, pid).json()["id"]
    resp = _create(client, pid, kind="sku_variants", source_asset_id=aid, colors=[])
    assert resp.status_code == 400


def test_sku_too_many_colors(client):
    pid = make_project(client)
    aid = upload(client, pid).json()["id"]
    resp = _create(
        client, pid, kind="sku_variants", source_asset_id=aid, colors=["a", "b", "c", "d", "e"]
    )
    assert resp.status_code == 400


def test_bad_kind(client):
    pid = make_project(client)
    resp = _create(client, pid, kind="hack")
    assert resp.status_code == 422


def test_sku_count_matches_colors(client):
    pid = make_project(client)
    aid = upload(client, pid).json()["id"]
    resp = _create(
        client, pid, kind="sku_variants", source_asset_id=aid, colors=["淡粉", "浅蓝", "薄荷绿"]
    )
    assert resp.status_code == 201
    assert resp.json()["count"] == 3
    assert resp.json()["params"]["colors"] == ["淡粉", "浅蓝", "薄荷绿"]


# ---------- worker 分发 ----------


def test_worker_cutout_produces_white_and_alpha(client):
    pid = make_project(client)
    aid = upload(client, pid).json()["id"]
    tid = _create(client, pid, kind="cutout", source_asset_id=aid).json()["id"]

    white = png_bytes(32, 32, (240, 250, 255))
    with patch(
        "app.services.task_runner.edit_client.edit_image",
        return_value=(white, 1234),
    ):
        assert task_runner.process_pending() == 1

    data = client.get(f"/api/tasks/{tid}").json()
    assert data["status"] == "SUCCEEDED"
    assert len(data["assets"]) == 2
    names = [a["filename"] for a in data["assets"]]
    assert any("_alpha" in n for n in names)


def test_worker_image_edit_success(client):
    pid = make_project(client)
    aid = upload(client, pid).json()["id"]
    tid = _create(
        client, pid, kind="image_edit", source_asset_id=aid, prompt="浅色大理石台面"
    ).json()["id"]
    with patch(
        "app.services.task_runner.edit_client.edit_image",
        return_value=(png_bytes(24, 24), 1),
    ):
        task_runner.process_pending()
    data = client.get(f"/api/tasks/{tid}").json()
    assert data["status"] == "SUCCEEDED"
    assert len(data["assets"]) == 1


def test_worker_sku_produces_n_assets(client):
    pid = make_project(client)
    aid = upload(client, pid).json()["id"]
    tid = _create(
        client, pid, kind="sku_variants", source_asset_id=aid, colors=["红", "蓝"]
    ).json()["id"]
    calls = []

    def fake_edit(*, prompt, image_bytes, seed=None, image_size=None):
        calls.append(prompt)
        return png_bytes(20, 20), seed

    with patch("app.services.task_runner.edit_client.edit_image", fake_edit):
        task_runner.process_pending()
    data = client.get(f"/api/tasks/{tid}").json()
    assert data["status"] == "SUCCEEDED"
    assert len(data["assets"]) == 2
    assert all("只把商品主色改为" in c for c in calls)


def test_worker_edit_failure_no_fake_asset(client):
    pid = make_project(client)
    aid = upload(client, pid).json()["id"]
    tid = _create(client, pid, kind="image_edit", source_asset_id=aid, prompt="x").json()["id"]
    with patch(
        "app.services.task_runner.edit_client.edit_image",
        side_effect=edit_client.ImageServiceError("EDIT_UPSTREAM", "编辑服务不可用"),
    ):
        task_runner.process_pending()
    data = client.get(f"/api/tasks/{tid}").json()
    assert data["status"] == "FAILED"
    assert data["error"]["code"] == "EDIT_UPSTREAM"
    assert data["assets"] == []


def test_cutout_without_key_fails_honestly(client):
    pid = make_project(client)
    aid = upload(client, pid).json()["id"]
    tid = _create(client, pid, kind="cutout", source_asset_id=aid).json()["id"]
    task_runner.process_pending()
    data = client.get(f"/api/tasks/{tid}").json()
    assert data["status"] == "FAILED"
    assert data["error"]["code"] == "IMAGE_KEY_MISSING"
    assert data["assets"] == []


def test_edit_prompt_templates():
    assert "纯白" in edit_client.cutout_prompt()
    assert "大理石" in edit_client.scene_prompt("大理石")
    assert "淡粉" in edit_client.sku_prompt("淡粉")
