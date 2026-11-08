"""Agent 编排层测试：意图识别、商品信息解析、状态机流转、确认点不可绕过。"""

from app.services import agent
from tests.conftest import make_project, upload

MOCK_SCRIPT = {
    "product_name": "保温杯",
    "audience": "上班族",
    "hook": "冬天到了，你需要一个保温杯",
    "selling_points": ["保温12小时", "不漏水"],
    "script_text": "冬天到了，你需要一个保温杯。保温12小时，还不漏水。",
    "shots": [
        {"index": 1, "scene": "特写", "camera": "固定", "description": "保温杯特写", "voiceover": "这是保温杯", "duration": 5},
        {"index": 2, "scene": "中景", "camera": "推", "description": "使用场景", "voiceover": "保温12小时", "duration": 5},
    ],
}


def test_detect_intent():
    assert agent.detect_intent("帮我做带货视频") == "start"
    assert agent.detect_intent("确认") == "confirm"
    assert agent.detect_intent("重做") == "redo"
    # 单字"行"不应误判：行李箱不是确认
    assert agent.detect_intent("商品是行李箱，卖点是轻便") == "other"


def test_parse_product_info():
    name, points, style, platform = agent._parse_product_request(
        "商品是保温杯，卖点是保温12小时、不漏水，品牌式，发抖音"
    )
    assert name == "保温杯"
    assert points == ["保温12小时", "不漏水"]
    assert style == "品牌式"
    assert platform == "抖音"


def test_parse_product_info_returns_empty_without_markers():
    name, points, style, platform = agent._parse_product_request("确认")
    assert name == ""
    assert points == []
    assert style == "种草式"
    assert platform == "其他"


def test_chat_full_flow(client, monkeypatch):
    pid = make_project(client)

    # 1) 启动流程
    resp = client.post("/api/agent/chat", json={"project_id": pid, "message": "帮我做带货视频"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["workflow"] == "awaiting_product"

    # 2) 提交商品信息 → 生成脚本（mock LLM，不花真实调用）
    monkeypatch.setattr(
        agent,
        "generate_sale_script",
        lambda name, points, style="种草式", platform="其他": MOCK_SCRIPT,
    )
    resp = client.post(
        "/api/agent/chat",
        json={"project_id": pid, "message": "商品是保温杯，卖点是保温12小时、不漏水"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["workflow"] == "script_draft"
    assert data["reply"]["kind"] == "script_card"
    assert len(data["reply"]["payload"]["shots"]) == 2

    # 3) 确认脚本 → 进入等待商品图
    resp = client.post("/api/agent/chat", json={"project_id": pid, "message": "确认"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["workflow"] == "awaiting_product_image"


def test_quote_and_start_generation(client, monkeypatch):
    """脚本确认 → 上传商品图 → 报价单 → 确认出片 → 创建任务。"""
    pid = make_project(client)
    client.post("/api/agent/chat", json={"project_id": pid, "message": "帮我做带货视频"})
    monkeypatch.setattr(
        agent,
        "generate_sale_script",
        lambda name, points, style="种草式", platform="其他": MOCK_SCRIPT,
    )
    client.post(
        "/api/agent/chat",
        json={"project_id": pid, "message": "商品是保温杯，卖点是保温12小时"},
    )
    # 确认脚本 → awaiting_product_image
    resp = client.post("/api/agent/chat", json={"project_id": pid, "message": "确认"})
    assert resp.json()["workflow"] == "awaiting_product_image"

    # 上传商品图
    upload(client, pid)

    # 说「图传好了」→ 出报价单
    resp = client.post("/api/agent/chat", json={"project_id": pid, "message": "图传好了"})
    data = resp.json()
    assert data["workflow"] == "quote_draft"
    assert data["reply"]["kind"] == "quote_card"
    assert data["reply"]["payload"]["shot_count"] == 2

    # 确认出片 → 创建 2 个任务
    resp = client.post("/api/agent/chat", json={"project_id": pid, "message": "确认"})
    assert resp.json()["workflow"] == "generating"

    from app.db import SessionLocal

    db = SessionLocal()
    try:
        done, total = agent._generation_progress(db, pid)
    finally:
        db.close()
    assert total == 2


def test_confirm_not_bypassable(client):
    """确认点不可绕过：未生成脚本时，确认不能跳到 confirmed。"""
    pid = make_project(client)
    resp = client.post("/api/agent/chat", json={"project_id": pid, "message": "帮我做带货视频"})
    assert resp.json()["workflow"] == "awaiting_product"

    # 还没生成脚本，直接说"确认"，应停留在引导，而不是 confirmed
    resp = client.post("/api/agent/chat", json={"project_id": pid, "message": "确认"})
    assert resp.json()["workflow"] != "script_confirmed"


def test_llm_fallback_parses_natural_language(client, monkeypatch):
    """正则看不懂的自然表达（无「商品是/卖点是」标记），用 LLM 兜底解析。"""
    pid = make_project(client)
    client.post("/api/agent/chat", json={"project_id": pid, "message": "帮我做带货视频"})

    monkeypatch.setattr(
        agent,
        "generate_sale_script",
        lambda name, points, style="种草式", platform="其他": MOCK_SCRIPT,
    )
    monkeypatch.setattr(
        agent,
        "parse_product_request_llm",
        lambda msg: {
            "product_name": "小米手机",
            "selling_points": ["续航三天", "人像模式超清晰"],
            "style": "品牌式",
            "platform": "其他",
        },
    )

    resp = client.post(
        "/api/agent/chat",
        json={"project_id": pid, "message": "品牌式 暂不发 小米手机 续航三天 人像模式超清晰"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["workflow"] == "script_draft"
    assert data["reply"]["kind"] == "script_card"


def test_redo_regenerates(client, monkeypatch):
    """重做会重新生成脚本。"""
    pid = make_project(client)
    client.post("/api/agent/chat", json={"project_id": pid, "message": "帮我做带货视频"})

    calls = {"n": 0}

    def fake_generate(name, points, style="种草式", platform="其他"):
        calls["n"] += 1
        return MOCK_SCRIPT

    monkeypatch.setattr(agent, "generate_sale_script", fake_generate)

    client.post(
        "/api/agent/chat",
        json={"project_id": pid, "message": "商品是保温杯，卖点是保温12小时"},
    )
    assert calls["n"] == 1

    client.post("/api/agent/chat", json={"project_id": pid, "message": "重做"})
    assert calls["n"] == 2


def _prepare_generating(client, monkeypatch, pid: str) -> None:
    client.post("/api/agent/chat", json={"project_id": pid, "message": "帮我做带货视频"})
    monkeypatch.setattr(
        agent, "generate_sale_script",
        lambda name, points, style="种草式", platform="其他": MOCK_SCRIPT,
    )
    client.post("/api/agent/chat", json={"project_id": pid, "message": "商品是保温杯，卖点是保温12小时"})
    client.post("/api/agent/chat", json={"project_id": pid, "message": "确认"})
    upload(client, pid)
    client.post("/api/agent/chat", json={"project_id": pid, "message": "图传好了"})
    client.post("/api/agent/chat", json={"project_id": pid, "message": "确认"})


def test_progress_then_compose(client, monkeypatch):
    """出片全部完成后，进度回复应转入合成阶段。"""
    from app import models
    from app.db import SessionLocal

    pid = make_project(client)
    _prepare_generating(client, monkeypatch, pid)

    db = SessionLocal()
    try:
        shots = db.query(models.SaleShot).filter(models.SaleShot.project_id == pid).all()
        asset = models.Asset(owner_id="local-user", project_id=pid, kind="video", path="/tmp/x.mp4")
        db.add(asset)
        db.flush()
        for s in shots:
            s.video_asset_id = asset.id
        for t in db.query(models.Task).filter(models.Task.project_id == pid).all():
            t.status = "SUCCEEDED"
        db.commit()
    finally:
        db.close()

    resp = client.post("/api/agent/chat", json={"project_id": pid, "message": "进度"})
    assert resp.status_code == 200
    assert resp.json()["workflow"] == "composing"


def test_bgm_upload_and_list(client, tmp_path):
    """背景音乐上传后可在列表中看到，并作为当前使用曲目。"""
    import subprocess

    from app.services import media

    pid = make_project(client)
    wav = tmp_path / "bgm.mp3"
    subprocess.run(
        [media.ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=330:duration=2", "-c:a", "libmp3lame", str(wav)],
        check=True,
    )
    with open(wav, "rb") as f:
        resp = client.post(
            f"/api/agent/projects/{pid}/bgm",
            files={"file": ("bgm.mp3", f, "audio/mpeg")},
        )
    assert resp.status_code == 201, resp.text
    assert resp.json()["duration"] > 1

    listed = client.get(f"/api/agent/projects/{pid}/bgm").json()
    assert len(listed["items"]) == 1
    assert listed["active_id"] == listed["items"][0]["id"]


def test_bgm_rejects_wrong_type(client):
    pid = make_project(client)
    resp = client.post(
        f"/api/agent/projects/{pid}/bgm",
        files={"file": ("evil.mp4", b"not audio", "video/mp4")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "BGM_TYPE_INVALID"


def test_redo_shot_creates_new_task(client, monkeypatch):
    """重做镜头：清掉旧视频并新提交一个任务，进入生成态。"""
    from app import models
    from app.db import SessionLocal
    from sqlalchemy import select

    pid = make_project(client)
    _prepare_generating(client, monkeypatch, pid)

    db = SessionLocal()
    try:
        shots = db.scalars(
            select(models.SaleShot).where(models.SaleShot.project_id == pid).order_by(models.SaleShot.index)
        ).all()
        asset = models.Asset(owner_id="local-user", project_id=pid, kind="video", path="/tmp/x.mp4")
        db.add(asset)
        db.flush()
        for s in shots:
            s.video_asset_id = asset.id
        for t in db.scalars(select(models.Task).where(models.Task.project_id == pid)).all():
            t.status = "SUCCEEDED"
        db.commit()
    finally:
        db.close()

    resp = client.post("/api/agent/chat", json={"project_id": pid, "message": "重做镜头 2"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["workflow"] == "generating"

    db = SessionLocal()
    try:
        shots = db.scalars(
            select(models.SaleShot).where(models.SaleShot.project_id == pid).order_by(models.SaleShot.index)
        ).all()
        assert shots[1].video_asset_id is None, "被重做的镜头应清空旧视频"
        assert shots[0].video_asset_id is not None, "其他镜头不受影响"
        queued = db.scalars(
            select(models.Task).where(
                models.Task.project_id == pid, models.Task.status == "QUEUED"
            )
        ).all()
        assert len(queued) == 1
    finally:
        db.close()


def test_redo_shot_out_of_range(client, monkeypatch):
    pid = make_project(client)
    _prepare_generating(client, monkeypatch, pid)
    resp = client.post("/api/agent/chat", json={"project_id": pid, "message": "重做镜头 99"})
    assert "没有第 99 个镜头" in resp.json()["reply"]["content"]


def test_shots_endpoint(client, monkeypatch):
    pid = make_project(client)
    _prepare_generating(client, monkeypatch, pid)
    data = client.get(f"/api/agent/projects/{pid}/shots").json()
    assert len(data["items"]) == 2
    assert all(item["status"] in ("pending", "queued", "running", "failed", "done") for item in data["items"])


def test_negative_confirmation():
    assert agent.detect_intent("不要确认") != "confirm"
    assert agent.detect_intent("确认前先修改") != "confirm"


def test_progress_ignores_historical_tasks(client, monkeypatch):
    from app import models
    from app.db import SessionLocal
    pid = make_project(client)
    _prepare_generating(client, monkeypatch, pid)
    with SessionLocal() as db:
        db.add(models.Task(owner_id="local-user", project_id=pid,
            kind="sale_video_generate", status="FAILED", prompt="旧任务"))
        db.commit()
        assert agent._generation_progress(db, pid) == (0, 2)


def test_retry_compose_is_idempotent(client, monkeypatch):
    from app import models
    from app.db import SessionLocal
    pid = make_project(client)
    _prepare_generating(client, monkeypatch, pid)
    with SessionLocal() as db:
        asset = models.Asset(owner_id="local-user", project_id=pid, kind="video", path="/tmp/mock.mp4")
        db.add(asset)
        db.flush()
        for shot in db.query(models.SaleShot).filter_by(project_id=pid):
            shot.video_asset_id = asset.id
        session = db.query(models.AgentSession).filter_by(project_id=pid).first()
        session.workflow = agent.W_COMPOSING
        db.commit()
    for _ in range(2):
        response = client.post("/api/agent/chat", json={"project_id": pid, "message": "确认重试合成"})
        assert response.status_code == 200
    with SessionLocal() as db:
        assert db.query(models.Task).filter_by(project_id=pid, kind="sale_compose").count() == 1


def test_redo_pending_does_not_duplicate(client, monkeypatch):
    from app import models
    from app.db import SessionLocal
    pid = make_project(client)
    _prepare_generating(client, monkeypatch, pid)
    for _ in range(2):
        response = client.post("/api/agent/chat", json={"project_id": pid, "message": "重做镜头 1"})
        assert "排队" in response.json()["reply"]["content"]
    with SessionLocal() as db:
        assert db.query(models.Task).filter_by(project_id=pid).count() == 2


def test_stale_card_rejected(client):
    pid = make_project(client)
    response = client.post("/api/agent/chat", json={"project_id": pid, "message": "确认", "card_id": "old-card"})
    assert response.status_code == 409


def test_retry_compose_requires_cost_confirmation(client, monkeypatch):
    from app import models
    from app.db import SessionLocal
    pid = make_project(client)
    _prepare_generating(client, monkeypatch, pid)
    with SessionLocal() as db:
        session = db.query(models.AgentSession).filter_by(project_id=pid).first()
        asset = models.Asset(owner_id="local-user", project_id=pid, kind="video", path="/tmp/mock.mp4")
        db.add(asset)
        db.flush()
        for shot in db.query(models.SaleShot).filter_by(project_id=pid):
            shot.video_asset_id = asset.id
        session.workflow = agent.W_COMPOSING
        db.commit()
    response = client.post("/api/agent/chat", json={"project_id": pid, "message": "重试合成"})
    assert "费用" in response.json()["reply"]["content"]
    with SessionLocal() as db:
        assert db.query(models.Task).filter_by(project_id=pid, kind="sale_compose").count() == 0


def test_concurrent_project_instruction_rejected(client):
    from app.services.project_gate import project_gate
    pid = make_project(client)
    with project_gate(pid) as acquired:
        assert acquired
        response = client.post("/api/agent/chat", json={"project_id": pid, "message": "确认"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "PROJECT_BUSY"
    response = client.post("/api/agent/chat", json={"project_id": pid, "message": "进度"})
    assert response.status_code == 200


def test_project_gate_released_on_exception(client):
    import pytest
    from app.services.project_gate import project_gate
    with pytest.raises(RuntimeError):
        with project_gate("release-test"):
            raise RuntimeError("test")
    with project_gate("release-test") as acquired:
        assert acquired


def test_read_only_workflow_reconciles_completed_shots(client, monkeypatch):
    from app import models
    from app.db import SessionLocal
    pid = make_project(client)
    _prepare_generating(client, monkeypatch, pid)
    with SessionLocal() as db:
        asset = models.Asset(owner_id="local-user", project_id=pid, kind="video", path="/tmp/mock.mp4")
        db.add(asset)
        db.flush()
        for shot in db.query(models.SaleShot).filter_by(project_id=pid):
            shot.video_asset_id = asset.id
        db.commit()
        before = db.query(models.Task).filter_by(project_id=pid).count()
    response = client.get(f"/api/agent/projects/{pid}/messages")
    assert response.json()["workflow"] == "composing"
    with SessionLocal() as db:
        assert db.query(models.Task).filter_by(project_id=pid).count() == before
        assert db.query(models.AgentSession).filter_by(project_id=pid).first().workflow == "generating"


def test_final_confirmation_survives_reload_and_rejects_stale(client, monkeypatch):
    from app import models
    from app.db import SessionLocal
    pid = make_project(client)
    _prepare_generating(client, monkeypatch, pid)
    with SessionLocal() as db:
        asset = models.Asset(owner_id="local-user", project_id=pid, kind="video", path="/tmp/mock.mp4")
        db.add(asset)
        db.flush()
        asset_id = asset.id
        for shot in db.query(models.SaleShot).filter_by(project_id=pid):
            shot.video_asset_id = asset_id
        script = db.query(models.SaleScript).filter_by(project_id=pid).first()
        script.final_asset_id = asset_id
        db.commit()
    body = {"project_id": pid, "message": "确认", "final_asset_id": "obsolete"}
    assert client.post("/api/agent/chat", json=body).status_code == 409
    body["final_asset_id"] = asset_id
    response = client.post("/api/agent/chat", json=body)
    assert response.status_code == 200
    assert response.json()["workflow"] == "done"
    assert client.get(f"/api/agent/projects/{pid}/messages").json()["workflow"] == "done"
    assert client.get(f"/api/agent/projects/{pid}/shots").json()["final_url"].endswith(asset_id)
    with SessionLocal() as db:
        assert db.query(models.Task).filter_by(project_id=pid).count() == 2
