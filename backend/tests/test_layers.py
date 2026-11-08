from tests.conftest import make_project, upload


def _layer(asset_id, **kw):
    base = {"asset_id": asset_id, "x": 10, "y": 20, "width": 300, "height": 300, "z": 1, "rotation": 0}
    base.update(kw)
    return base


def test_save_and_read_layers(client):
    pid = make_project(client)
    aid = upload(client, pid).json()["id"]
    resp = client.put(f"/api/projects/{pid}/layers", json={"layers": [_layer(aid)]})
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["asset_id"] == aid
    assert items[0]["x"] == 10
    assert items[0]["asset"]["url"] == f"/api/files/{aid}"

    got = client.get(f"/api/projects/{pid}/layers").json()["items"]
    assert len(got) == 1
    assert got[0]["width"] == 300


def test_replace_layers_clears_old(client):
    pid = make_project(client)
    a1 = upload(client, pid).json()["id"]
    a2 = upload(client, pid).json()["id"]
    client.put(f"/api/projects/{pid}/layers", json={"layers": [_layer(a1)]})
    client.put(f"/api/projects/{pid}/layers", json={"layers": [_layer(a2, z=2)]})
    items = client.get(f"/api/projects/{pid}/layers").json()["items"]
    assert len(items) == 1
    assert items[0]["asset_id"] == a2


def test_layer_with_foreign_asset_rejected(client):
    pid = make_project(client)
    other = make_project(client)
    foreign_asset = upload(client, other).json()["id"]
    resp = client.put(f"/api/projects/{pid}/layers", json={"layers": [_layer(foreign_asset)]})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "ASSET_NOT_IN_PROJECT"


def test_layer_invalid_size(client):
    pid = make_project(client)
    aid = upload(client, pid).json()["id"]
    resp = client.put(
        f"/api/projects/{pid}/layers", json={"layers": [_layer(aid, width=-5)]}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_layers_project_not_found(client):
    resp = client.get("/api/projects/nope/layers")
    assert resp.status_code == 404


def test_empty_layers_allowed(client):
    pid = make_project(client)
    resp = client.put(f"/api/projects/{pid}/layers", json={"layers": []})
    assert resp.status_code == 200
    assert resp.json()["items"] == []
