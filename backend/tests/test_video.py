from unittest.mock import patch

from app.services import image_client, video_client
from tests.conftest import png_bytes


def _drama(client, name="短剧V"):
    return client.post("/api/projects", json={"name": name, "workspace": "drama"}).json()["id"]


def _shots(client, pid, n=2):
    client.put(
        f"/api/drama/projects/{pid}/shots",
        json={"shots": [{"description": f"镜头{i + 1}", "duration": 5} for i in range(n)]},
    )
    return client.get(f"/api/drama/projects/{pid}/shots").json()["items"]


def _character_with_ref(client, pid, name="林晚"):
    cid = client.post(f"/api/drama/projects/{pid}/characters", json={"name": name}).json()["id"]
    client.post(
        f"/api/drama/projects/{pid}/characters/{cid}/ref",
        files={"file": ("face.png", png_bytes(), "image/png")},
    )
    return cid


def test_video_task_requires_shot(client):
    pid = _drama(client)
    resp = client.post(f"/api/drama/projects/{pid}/shots/nope/video")
    assert resp.status_code == 404


def test_single_video_task_created(client):
    pid = _drama(client)
    shot = _shots(client, pid, 1)[0]
    resp = client.post(f"/api/drama/projects/{pid}/shots/{shot['id']}/video")
    assert resp.status_code == 201
    assert resp.json()["kind"] == "video_generate"


def test_batch_creates_all_shots(client):
    pid = _drama(client)
    _shots(client, pid, 3)
    resp = client.post(f"/api/drama/projects/{pid}/videos/batch", json={})
    assert resp.status_code == 201
    data = resp.json()
    assert data["count"] == 3
    assert data["estimated_cost"] > 0


def test_batch_limit(client):
    pid = _drama(client)
    _shots(client, pid, 21)
    resp = client.post(f"/api/drama/projects/{pid}/videos/batch", json={})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "TOO_MANY_SHOTS"


def test_batch_without_shots(client):
    pid = _drama(client)
    resp = client.post(f"/api/drama/projects/{pid}/videos/batch", json={})
    assert resp.status_code == 400


def test_worker_video_i2v_uses_character_ref(client):
    from app.services import task_runner

    pid = _drama(client)
    _character_with_ref(client, pid, "林晚")
    client.put(
        f"/api/drama/projects/{pid}/shots",
        json={"shots": [{"description": "林晚推门", "character_names": ["林晚"]}]},
    )
    shot = client.get(f"/api/drama/projects/{pid}/shots").json()["items"][0]
    tid = client.post(f"/api/drama/projects/{pid}/shots/{shot['id']}/video").json()["id"]

    captured = {}

    def fake_submit(*, prompt, image_bytes=None, model=None):
        captured["image"] = image_bytes
        return "req-1", "Wan-AI/Wan2.2-I2V-A14B"

    with patch("app.services.task_runner.video_client.submit", fake_submit), patch(
        "app.services.task_runner.video_client.wait_and_download",
        return_value=b"fake-mp4-bytes",
    ):
        task_runner.process_pending()

    task = client.get(f"/api/tasks/{tid}").json()
    assert task["status"] == "SUCCEEDED"
    assert captured["image"] is not None
    assert task["params"]["mode"] == "i2v"
    assert task["params"]["first_frame_character"] == "林晚"
    assert task["assets"][0]["mime"] == "video/mp4"


def test_worker_video_t2v_without_ref(client):
    from app.services import task_runner

    pid = _drama(client)
    client.put(
        f"/api/drama/projects/{pid}/shots",
        json={"shots": [{"description": "空镜：雨夜的街道", "character_names": []}]},
    )
    shot = client.get(f"/api/drama/projects/{pid}/shots").json()["items"][0]
    tid = client.post(f"/api/drama/projects/{pid}/shots/{shot['id']}/video").json()["id"]

    captured = {}

    def fake_submit(*, prompt, image_bytes=None, model=None):
        captured["image"] = image_bytes
        return "req-2", "Wan-AI/Wan2.2-T2V-A14B"

    with patch("app.services.task_runner.video_client.submit", fake_submit), patch(
        "app.services.task_runner.video_client.wait_and_download",
        return_value=b"mp4",
    ):
        task_runner.process_pending()

    task = client.get(f"/api/tasks/{tid}").json()
    assert task["status"] == "SUCCEEDED"
    assert captured["image"] is None
    assert task["params"]["mode"] == "t2v"


def test_worker_video_failure_no_asset(client):
    from app.services import task_runner

    pid = _drama(client)
    shot = _shots(client, pid, 1)[0]
    tid = client.post(f"/api/drama/projects/{pid}/shots/{shot['id']}/video").json()["id"]
    with patch(
        "app.services.task_runner.video_client.submit",
        side_effect=image_client.ImageServiceError("VIDEO_UPSTREAM", "视频服务不可用"),
    ):
        task_runner.process_pending()
    task = client.get(f"/api/tasks/{tid}").json()
    assert task["status"] == "FAILED"
    assert task["error"]["code"] == "VIDEO_UPSTREAM"
    assert task["assets"] == []


def test_videos_list_latest_per_shot(client):
    from app.services import task_runner

    pid = _drama(client)
    shot = _shots(client, pid, 1)[0]
    client.post(f"/api/drama/projects/{pid}/shots/{shot['id']}/video")
    with patch(
        "app.services.task_runner.video_client.submit", return_value=("r", "m")
    ), patch(
        "app.services.task_runner.video_client.wait_and_download", return_value=b"mp4"
    ):
        task_runner.process_pending()
    items = client.get(f"/api/drama/projects/{pid}/videos").json()["items"]
    assert len(items) == 1
    assert items[0]["asset"]["mime"] == "video/mp4"


# ---------- video_client 单测 ----------


def test_wait_and_download_success(monkeypatch):
    calls = {"n": 0}

    def fake_status(rid):
        calls["n"] += 1
        if calls["n"] < 2:
            return {"status": "InProgress"}
        return {"status": "Succeed", "results": {"videos": [{"url": "http://x/v.mp4"}]}}

    class FakeResp:
        content = b"video-bytes"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(video_client, "status", fake_status)
    monkeypatch.setattr(video_client.httpx, "get", lambda *a, **k: FakeResp())
    assert video_client.wait_and_download("r", max_wait=10, interval=0) == b"video-bytes"


def test_wait_and_download_failed(monkeypatch):
    monkeypatch.setattr(
        video_client, "status", lambda rid: {"status": "Failed", "reason": "内容不合规"}
    )
    try:
        video_client.wait_and_download("r", max_wait=5, interval=0)
    except image_client.ImageServiceError as e:
        assert e.code == "VIDEO_FAILED"
        assert "不合规" in e.message
    else:
        raise AssertionError("应抛错")


def test_wait_and_download_timeout(monkeypatch):
    monkeypatch.setattr(video_client, "status", lambda rid: {"status": "InQueue"})
    try:
        video_client.wait_and_download("r", max_wait=0.1, interval=0)
    except image_client.ImageServiceError as e:
        assert e.code == "VIDEO_TIMEOUT"
    else:
        raise AssertionError("应抛错")


def test_submit_without_key(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "IMAGE_API_KEY", "")
    try:
        video_client.submit(prompt="x")
    except image_client.ImageServiceError as e:
        assert e.code == "VIDEO_KEY_MISSING"
    else:
        raise AssertionError("应抛错")


def test_wait_and_download_tolerates_transient_errors(monkeypatch):
    """单次网络抖动不应判定失败（真实事故：5 分钟的生成因一次抖动被判失败）。"""
    calls = {"n": 0}

    def flaky_status(rid):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise image_client.ImageServiceError("VIDEO_NETWORK", "网络抖动")
        return {"status": "Succeed", "results": {"videos": [{"url": "http://x/v.mp4"}]}}

    class FakeResp:
        content = b"ok"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(video_client, "status", flaky_status)
    monkeypatch.setattr(video_client.httpx, "get", lambda *a, **k: FakeResp())
    assert video_client.wait_and_download("r", max_wait=10, interval=0) == b"ok"


def test_wait_and_download_gives_up_after_many_errors(monkeypatch):
    def always_fail(rid):
        raise image_client.ImageServiceError("VIDEO_NETWORK", "网络不通")

    monkeypatch.setattr(video_client, "status", always_fail)
    try:
        video_client.wait_and_download("r", max_wait=10, interval=0)
    except image_client.ImageServiceError as e:
        assert e.code == "VIDEO_NETWORK"
    else:
        raise AssertionError("连续失败应放弃")
