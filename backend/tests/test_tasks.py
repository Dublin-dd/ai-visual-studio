from unittest.mock import patch

from app import models
from app.db import SessionLocal
from app.services import image_client, task_runner
from tests.conftest import make_project, png_bytes, upload


def _create_task(client, pid, **kw):
    body = {
        "project_id": pid,
        "prompt": "白色背景下商品置于大理石台面，柔和灯光",
        "width": 1024,
        "height": 1024,
        "count": 1,
        "tier": "standard",
    }
    body.update(kw)
    return client.post("/api/tasks", json=body)


def test_create_task_queued(client):
    pid = make_project(client)
    resp = _create_task(client, pid)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["status"] == "QUEUED"
    assert data["error"] is None


def test_create_task_empty_prompt(client):
    pid = make_project(client)
    resp = _create_task(client, pid, prompt="   ")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_create_task_over_count(client):
    pid = make_project(client)
    resp = _create_task(client, pid, count=9)
    assert resp.status_code == 422


def test_create_task_project_not_found(client):
    resp = _create_task(client, "no-such")
    assert resp.status_code == 404


def test_create_task_daily_limit(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "DAILY_TASK_LIMIT", 1)
    pid = make_project(client)
    assert _create_task(client, pid).status_code == 201
    resp = _create_task(client, pid)
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "DAILY_LIMIT_REACHED"


def test_worker_success_creates_asset(client):
    pid = make_project(client)
    tid = _create_task(client, pid).json()["id"]

    with patch(
        "app.services.task_runner.image_client.generate_image",
        return_value=(png_bytes(32, 32), "black-forest-labs/FLUX.1-schnell"),
    ):
        assert task_runner.process_pending() == 1

    data = client.get(f"/api/tasks/{tid}").json()
    assert data["status"] == "SUCCEEDED"
    assert data["model"] == "black-forest-labs/FLUX.1-schnell"
    assert len(data["assets"]) == 1
    assert data["assets"][0]["kind"] == "generated"
    assert data["cost_estimate"] > 0


def test_worker_multiple_count(client):
    pid = make_project(client)
    tid = _create_task(client, pid, count=2).json()["id"]
    with patch(
        "app.services.task_runner.image_client.generate_image",
        return_value=(png_bytes(20, 20), "m"),
    ):
        task_runner.process_pending()
    data = client.get(f"/api/tasks/{tid}").json()
    assert data["status"] == "SUCCEEDED"
    assert len(data["assets"]) == 2


def test_worker_failure_marks_task(client):
    pid = make_project(client)
    tid = _create_task(client, pid).json()["id"]
    with patch(
        "app.services.task_runner.image_client.generate_image",
        side_effect=image_client.ImageServiceError("IMAGE_UPSTREAM", "图像服务暂时不可用，请稍后重试"),
    ):
        task_runner.process_pending()
    data = client.get(f"/api/tasks/{tid}").json()
    assert data["status"] == "FAILED"
    assert data["error"]["code"] == "IMAGE_UPSTREAM"
    assert "稍后重试" in data["error"]["message"]


def test_worker_without_key_does_not_fake_result(client):
    """无 Key 时必须如实失败，不能返回假图（底线 10）。"""
    pid = make_project(client)
    tid = _create_task(client, pid).json()["id"]
    task_runner.process_pending()
    data = client.get(f"/api/tasks/{tid}").json()
    assert data["status"] == "FAILED"
    assert data["error"]["code"] == "IMAGE_KEY_MISSING"
    assert data["assets"] == []


def test_worker_bad_image_payload(client):
    pid = make_project(client)
    tid = _create_task(client, pid).json()["id"]
    with patch(
        "app.services.task_runner.image_client.generate_image",
        return_value=(b"not-an-image", "m"),
    ):
        task_runner.process_pending()
    data = client.get(f"/api/tasks/{tid}").json()
    assert data["status"] == "FAILED"
    assert data["error"]["code"] == "BAD_IMAGE"


def test_task_not_found(client):
    resp = client.get("/api/tasks/nope")
    assert resp.status_code == 404


def test_running_tasks_reset_on_restart(client):
    pid = make_project(client)
    tid = _create_task(client, pid).json()["id"]
    db = SessionLocal()
    try:
        task = db.get(models.Task, tid)
        task.status = "RUNNING"
        db.commit()
    finally:
        db.close()

    assert task_runner.reset_running_tasks() == 1
    assert client.get(f"/api/tasks/{tid}").json()["status"] == "QUEUED"


def test_project_assets_list(client):
    pid = make_project(client)
    upload(client, pid)
    resp = client.get(f"/api/projects/{pid}/assets")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1
