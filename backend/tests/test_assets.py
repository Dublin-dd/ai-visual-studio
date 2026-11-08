import io

from PIL import Image

from tests.conftest import jpeg_bytes, make_project, png_bytes, upload


def test_upload_png_ok(client):
    pid = make_project(client)
    resp = upload(client, pid)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["kind"] == "upload"
    assert data["width"] == 64
    assert data["height"] == 64
    assert data["url"] == f"/api/files/{data['id']}"


def test_upload_jpeg_ok(client):
    pid = make_project(client)
    resp = upload(client, pid, jpeg_bytes(), "photo.jpg")
    assert resp.status_code == 201
    assert resp.json()["mime"] == "image/jpeg"


def test_upload_not_image(client):
    pid = make_project(client)
    resp = upload(client, pid, b"this is not an image", "fake.png")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FORMAT"


def test_upload_empty(client):
    pid = make_project(client)
    resp = upload(client, pid, b"", "empty.png")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "EMPTY_FILE"


def test_upload_too_large(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
    pid = make_project(client)
    resp = upload(client, pid, png_bytes())
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_upload_project_not_found(client):
    resp = upload(client, "no-such-project")
    assert resp.status_code == 404


def test_upload_ignores_path_traversal_filename(client):
    pid = make_project(client)
    resp = upload(client, pid, png_bytes(), "../../etc/passwd.png")
    assert resp.status_code == 201
    filename = resp.json()["filename"]
    assert "/" not in filename and ".." not in filename
    assert filename.endswith(".png")


def test_get_file(client):
    pid = make_project(client)
    aid = upload(client, pid).json()["id"]
    resp = client.get(f"/api/files/{aid}")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")


def test_get_file_not_found(client):
    resp = client.get("/api/files/missing")
    assert resp.status_code == 404


def test_gif_rejected(client):
    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, format="GIF")
    pid = make_project(client)
    resp = upload(client, pid, buf.getvalue(), "a.gif")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FORMAT"
