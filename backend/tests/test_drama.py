from unittest.mock import patch

from app.services import llm_client, storyboard
from tests.conftest import make_project, png_bytes

FAKE_RAW = {
    "shots": [
        {
            "no": 1,
            "scene": "全景",
            "camera": "缓推",
            "description": "雨夜的旧公寓走廊，林晚拎着行李箱站在门口",
            "dialogue": "我回来了。",
            "duration": 6,
            "characters": ["林晚"],
        },
        {
            "no": 2,
            "scene": "特写镜头",
            "camera": "固定机位",
            "description": "她握紧门把手，指节发白",
            "dialogue": "",
            "duration": 3,
            "characters": "林晚,陈默",
        },
    ]
}


def _drama(client, name="短剧A"):
    resp = client.post("/api/projects", json={"name": name, "workspace": "drama"})
    assert resp.status_code == 201
    return resp.json()["id"]


def _script(client, pid, content="林晚回到旧公寓，遇见陈默。", title="第一集"):
    return client.post(
        f"/api/drama/projects/{pid}/script", json={"title": title, "content": content}
    )


# ---------- 解析与规整 ----------


def test_normalize_shots_fixes_scene_and_camera():
    shots = storyboard.normalize_shots(FAKE_RAW)
    assert len(shots) == 2
    assert shots[0]["scene"] == "全景"
    assert shots[0]["camera"] == "推"          # "缓推" -> 归一
    assert shots[1]["scene"] == "特写"          # "特写镜头" -> 归一
    assert shots[1]["camera"] == "固定"          # "固定机位" -> 归一
    assert shots[1]["character_names"] == ["林晚", "陈默"]  # 字符串分割


def test_normalize_rejects_bad_structure():
    try:
        storyboard.normalize_shots({"foo": 1})
    except llm_client.LLMError as e:
        assert e.code == "LLM_BAD_STRUCTURE"
    else:
        raise AssertionError("应抛错")


def test_normalize_skips_empty_description():
    raw = {"shots": [{"description": "  "}, {"description": "有效镜头"}]}
    shots = storyboard.normalize_shots(raw)
    assert len(shots) == 1
    assert shots[0]["description"] == "有效镜头"


def test_normalize_clamps_duration():
    raw = {"shots": [{"description": "x", "duration": 99}, {"description": "y", "duration": 0}]}
    shots = storyboard.normalize_shots(raw)
    assert shots[0]["duration"] == 10
    assert shots[1]["duration"] == 2


def test_normalize_truncates_to_max():
    raw = {"shots": [{"description": f"镜头{i}"} for i in range(50)]}
    shots = storyboard.normalize_shots(raw, max_shots=30)
    assert len(shots) == 30


def test_parse_json_with_fence():
    text = '```json\n{"shots": []}\n```'
    assert llm_client.parse_json_object(text) == {"shots": []}


def test_parse_json_with_noise():
    text = '好的，结果如下：{"shots":[{"description":"x"}]} 希望有帮助'
    assert "shots" in llm_client.parse_json_object(text)


def test_parse_json_invalid():
    try:
        llm_client.parse_json_object("没有 JSON")
    except ValueError:
        pass
    else:
        raise AssertionError("应抛错")


# ---------- 剧本 API ----------


def test_save_and_get_script(client):
    pid = _drama(client)
    resp = _script(client, pid)
    assert resp.status_code == 200
    assert resp.json()["title"] == "第一集"
    got = client.get(f"/api/drama/projects/{pid}/script").json()["script"]
    assert "林晚" in got["content"]


def test_script_overwrites(client):
    pid = _drama(client)
    _script(client, pid, "第一版")
    _script(client, pid, "第二版")
    got = client.get(f"/api/drama/projects/{pid}/script").json()["script"]
    assert got["content"] == "第二版"


def test_script_empty_rejected(client):
    pid = _drama(client)
    resp = client.post(f"/api/drama/projects/{pid}/script", json={"content": "   "})
    assert resp.status_code == 400


def test_script_on_ecommerce_project_rejected(client):
    pid = make_project(client)  # 电商项目
    resp = client.post(f"/api/drama/projects/{pid}/script", json={"content": "x"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "WORKSPACE_MISMATCH"


# ---------- 分镜 ----------


def test_storyboard_requires_script(client):
    pid = _drama(client)
    resp = client.post(f"/api/drama/projects/{pid}/storyboard")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "SCRIPT_REQUIRED"


def test_storyboard_task_created(client):
    pid = _drama(client)
    _script(client, pid)
    resp = client.post(f"/api/drama/projects/{pid}/storyboard")
    assert resp.status_code == 201
    assert resp.json()["kind"] == "storyboard"
    assert resp.json()["status"] == "QUEUED"


def test_storyboard_conflicts_when_running(client):
    pid = _drama(client)
    _script(client, pid)
    client.post(f"/api/drama/projects/{pid}/storyboard")
    resp = client.post(f"/api/drama/projects/{pid}/storyboard")
    assert resp.status_code == 409


def test_worker_storyboard_writes_shots(client):
    from app.services import task_runner

    pid = _drama(client)
    _script(client, pid)
    tid = client.post(f"/api/drama/projects/{pid}/storyboard").json()["id"]
    with patch(
        "app.services.task_runner.storyboard.generate_storyboard",
        return_value=storyboard.normalize_shots(FAKE_RAW),
    ):
        task_runner.process_pending()
    task = client.get(f"/api/tasks/{tid}").json()
    assert task["status"] == "SUCCEEDED"
    shots = client.get(f"/api/drama/projects/{pid}/shots").json()["items"]
    assert len(shots) == 2
    assert shots[0]["scene"] == "全景"


def test_worker_storyboard_failure_keeps_old_shots(client):
    from app.services import task_runner

    pid = _drama(client)
    _script(client, pid)
    client.put(
        f"/api/drama/projects/{pid}/shots",
        json={"shots": [{"description": "旧镜头"}]},
    )
    tid = client.post(f"/api/drama/projects/{pid}/storyboard").json()["id"]
    with patch(
        "app.services.task_runner.storyboard.generate_storyboard",
        side_effect=llm_client.LLMError("LLM_UPSTREAM", "模型不可用"),
    ):
        task_runner.process_pending()
    task = client.get(f"/api/tasks/{tid}").json()
    assert task["status"] == "FAILED"
    shots = client.get(f"/api/drama/projects/{pid}/shots").json()["items"]
    assert [s["description"] for s in shots] == ["旧镜头"]


def test_shots_edit_and_reorder(client):
    pid = _drama(client)
    resp = client.put(
        f"/api/drama/projects/{pid}/shots",
        json={
            "shots": [
                {"description": "A", "duration": 3},
                {"description": "B", "duration": 7, "character_names": ["林晚"]},
            ]
        },
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [s["index"] for s in items] == [1, 2]
    assert items[1]["character_names"] == ["林晚"]


def test_shots_too_many(client):
    pid = _drama(client)
    resp = client.put(
        f"/api/drama/projects/{pid}/shots",
        json={"shots": [{"description": f"x{i}"} for i in range(31)]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "TOO_MANY_SHOTS"


def test_shots_duration_out_of_range(client):
    pid = _drama(client)
    resp = client.put(
        f"/api/drama/projects/{pid}/shots",
        json={"shots": [{"description": "x", "duration": 30}]},
    )
    assert resp.status_code == 422


# ---------- 角色库 ----------


def test_character_crud(client):
    pid = _drama(client)
    r = client.post(
        f"/api/drama/projects/{pid}/characters",
        json={"name": "林晚", "description": "25岁，短发，米色风衣"},
    )
    assert r.status_code == 201
    cid = r.json()["id"]

    dup = client.post(f"/api/drama/projects/{pid}/characters", json={"name": "林晚"})
    assert dup.status_code == 400
    assert dup.json()["error"]["code"] == "DUPLICATE_NAME"

    patched = client.patch(
        f"/api/drama/projects/{pid}/characters/{cid}", json={"description": "改描述"}
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "改描述"

    assert len(client.get(f"/api/drama/projects/{pid}/characters").json()["items"]) == 1
    assert client.delete(f"/api/drama/projects/{pid}/characters/{cid}").status_code == 200
    assert client.get(f"/api/drama/projects/{pid}/characters").json()["items"] == []


def test_character_empty_name(client):
    pid = _drama(client)
    resp = client.post(f"/api/drama/projects/{pid}/characters", json={"name": "  "})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_character_upload_ref(client):
    pid = _drama(client)
    cid = client.post(f"/api/drama/projects/{pid}/characters", json={"name": "陈默"}).json()["id"]
    resp = client.post(
        f"/api/drama/projects/{pid}/characters/{cid}/ref",
        files={"file": ("face.png", png_bytes(), "image/png")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ref_asset"]["url"].startswith("/api/files/")
    # 列表里也能带出定妆照
    items = client.get(f"/api/drama/projects/{pid}/characters").json()["items"]
    assert items[0]["ref_asset"] is not None


def test_character_upload_not_image(client):
    pid = _drama(client)
    cid = client.post(f"/api/drama/projects/{pid}/characters", json={"name": "陈默"}).json()["id"]
    resp = client.post(
        f"/api/drama/projects/{pid}/characters/{cid}/ref",
        files={"file": ("a.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400


def test_character_cross_project_isolation(client):
    p1 = _drama(client, "剧A")
    p2 = _drama(client, "剧B")
    cid = client.post(f"/api/drama/projects/{p1}/characters", json={"name": "林晚"}).json()["id"]
    resp = client.patch(f"/api/drama/projects/{p2}/characters/{cid}", json={"name": "x"})
    assert resp.status_code == 404
