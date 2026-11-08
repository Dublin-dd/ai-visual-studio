"""Exercise project, uploaded asset, canvas and queued task across a real restart.
Runs only against the temporary database selected by restart-check.sh; no model calls.
"""
import io
import json
import sys
import urllib.request
from pathlib import Path

from PIL import Image

phase, base, directory = sys.argv[1:]
manifest = Path(directory) / "fixture.json"


def request(path, body=None, method=None, content_type="application/json"):
    raw = json.dumps(body).encode() if isinstance(body, dict) else body
    req = urllib.request.Request(base + path, data=raw, method=method,
                                 headers={"Content-Type": content_type})
    with urllib.request.urlopen(req, timeout=10) as response:
        content = response.read()
        return json.loads(content) if "json" in response.headers.get("Content-Type", "") else content


if phase == "write":
    project = request("/api/projects", {"name": "restart-canvas-check"})
    pid = project["id"]
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), (80, 100, 120)).save(buffer, format="PNG")
    boundary = "studioPersistenceBoundary"
    data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"project_id\"\r\n\r\n{pid}\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"fixture.png\"\r\n"
            "Content-Type: image/png\r\n\r\n").encode() + buffer.getvalue() + f"\r\n--{boundary}--\r\n".encode()
    asset = request("/api/assets/upload", data, content_type=f"multipart/form-data; boundary={boundary}")
    layer = {"asset_id": asset["id"], "x": 133, "y": 207, "width": 180, "height": 240, "z": 1, "rotation": 0}
    request(f"/api/projects/{pid}/layers", {"layers": [layer]}, method="PUT")
    task = request("/api/tasks", {"project_id": pid, "prompt": "persistence fixture - worker disabled"})
    manifest.write_text(json.dumps({"project": project, "asset": asset, "layer": layer, "task": task}))
    print("第一次启动：已写入独立测试项目、图片、画布图层与排队任务（worker 关闭，无模型费用）。")
else:
    data = json.loads(manifest.read_text())
    pid = data["project"]["id"]
    assert request(f"/api/projects/{pid}")["name"] == "restart-canvas-check"
    layers = request(f"/api/projects/{pid}/layers")["items"]
    assert len(layers) == 1
    assert all(layers[0][key] == value for key, value in data["layer"].items())
    asset = data["asset"]
    assert request(asset["url"]).startswith(b"\x89PNG")
    task = request("/api/tasks/" + data["task"]["id"])
    assert task["status"] == "QUEUED" and task["project_id"] == pid
    print("第二次启动：项目、图片文件、图层坐标/尺寸/关联和排队任务全部恢复一致。")
