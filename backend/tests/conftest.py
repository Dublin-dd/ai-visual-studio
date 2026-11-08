import io
import os
import tempfile

# 必须在导入 app 之前设置：临时数据目录 + 临时数据库 + 关闭 worker + 不使用真实 Key
_tmp = tempfile.mkdtemp()
os.environ["DATA_DIR"] = os.path.join(_tmp, "data")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["WORKER_ENABLED"] = "0"
os.environ["IMAGE_API_KEY"] = ""
os.environ["DAILY_TASK_LIMIT"] = "200"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def png_bytes(width: int = 64, height: int = 64, color=(200, 120, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def jpeg_bytes(width: int = 48, height: int = 48) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (10, 20, 30)).save(buf, format="JPEG")
    return buf.getvalue()


def make_project(client) -> str:
    resp = client.post("/api/projects", json={"name": "商品素材项目"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def upload(client, project_id: str, data: bytes | None = None, filename: str = "p.png"):
    return client.post(
        "/api/assets/upload",
        data={"project_id": project_id},
        files={"file": (filename, data if data is not None else png_bytes(), "image/png")},
    )
