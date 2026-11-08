from app import config


def test_create_project(client):
    resp = client.post("/api/projects", json={"name": "  我的第一个项目  "})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "我的第一个项目"
    assert data["owner_id"] == config.DEFAULT_OWNER_ID
    assert data["id"]


def test_create_project_default_name(client):
    resp = client.post("/api/projects", json={})
    assert resp.status_code == 201
    assert resp.json()["name"] == "未命名项目"


def test_list_projects(client):
    client.post("/api/projects", json={"name": "A"})
    client.post("/api/projects", json={"name": "B"})
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


def test_get_project_not_found(client):
    resp = client.get("/api/projects/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


def test_validation_error_shape(client):
    resp = client.post("/api/projects", json={"name": "x" * 300})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_project_cover_is_scoped_and_persisted(client):
    from tests.conftest import make_project, upload
    project = make_project(client)
    other = make_project(client)
    asset = upload(client, project).json()["id"]
    url = f"/api/projects/{project}"
    assert client.put(url + "/cover", json={"asset_id": asset}).status_code == 200
    assert client.get(url).json()["cover_asset_id"] == asset
    assert client.put(f"/api/projects/{other}/cover", json={"asset_id": asset}).status_code == 400
    assert client.put(url + "/cover", json={"asset_id": None}).json()["cover_asset_id"] is None
