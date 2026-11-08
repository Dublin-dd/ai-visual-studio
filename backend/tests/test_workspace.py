from app import config, models
from app.db import SessionLocal
from tests.conftest import make_project, png_bytes, upload


def _project(client, name="素材项目", workspace="ecommerce"):
    resp = client.post("/api/projects", json={"name": name, "workspace": workspace})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_project_default_workspace(client):
    data = _project(client)
    assert data["workspace"] == "ecommerce"


def test_create_project_drama_workspace(client):
    data = _project(client, "短剧项目", "drama")
    assert data["workspace"] == "drama"


def test_create_project_bad_workspace(client):
    resp = client.post("/api/projects", json={"name": "x", "workspace": "video"})
    assert resp.status_code == 422


def test_list_projects_filtered_by_workspace(client):
    _project(client, "电商A", "ecommerce")
    _project(client, "短剧B", "drama")

    ecom = client.get("/api/projects?workspace=ecommerce").json()["items"]
    drama = client.get("/api/projects?workspace=drama").json()["items"]
    assert [p["name"] for p in ecom] == ["电商A"]
    assert [p["name"] for p in drama] == ["短剧B"]
    assert len(client.get("/api/projects").json()["items"]) == 2


def test_list_projects_invalid_workspace(client):
    resp = client.get("/api/projects?workspace=xxx")
    assert resp.status_code == 422


def test_list_projects_asset_count(client):
    pid = _project(client)["id"]
    upload(client, pid)
    items = client.get("/api/projects?workspace=ecommerce").json()["items"]
    assert items[0]["asset_count"] == 1


def test_rename_project(client):
    pid = _project(client)["id"]
    resp = client.patch(f"/api/projects/{pid}", json={"name": "  新名字  "})
    assert resp.status_code == 200
    assert resp.json()["name"] == "新名字"


def test_rename_project_empty(client):
    pid = _project(client)["id"]
    resp = client.patch(f"/api/projects/{pid}", json={"name": "   "})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_rename_project_not_found(client):
    resp = client.patch("/api/projects/nope", json={"name": "x"})
    assert resp.status_code == 404


def test_asset_count_excludes_other_projects(client):
    p1 = _project(client, "A")["id"]
    _project(client, "B")
    upload(client, p1)
    items = {p["name"]: p["asset_count"] for p in client.get("/api/projects").json()["items"]}
    assert items["A"] == 1
    assert items["B"] == 0
