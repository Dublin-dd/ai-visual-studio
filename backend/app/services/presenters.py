"""资产与任务的服务端到客户端映射（供各 router 复用）。"""

from .. import models


def asset_out(asset: models.Asset) -> dict:
    return {
        "id": asset.id,
        "kind": asset.kind,
        "filename": asset.filename,
        "mime": asset.mime,
        "width": asset.width,
        "height": asset.height,
        "size_bytes": asset.size_bytes,
        "url": f"/api/files/{asset.id}",
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


def task_out(task: models.Task) -> dict:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "kind": task.kind,
        "status": task.status,
        "prompt": task.prompt,
        "width": task.width,
        "height": task.height,
        "count": task.count,
        "tier": task.tier,
        "model": task.model,
        "asset_ids": task.asset_ids or [],
        "params": task.params or {},
        "cost_estimate": task.cost_estimate,
        "error": (
            {"code": task.error_code, "message": task.error_message}
            if task.error_code
            else None
        ),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def layer_out(layer: models.Layer, asset: models.Asset | None) -> dict:
    return {
        "id": layer.id,
        "asset_id": layer.asset_id,
        "x": layer.x,
        "y": layer.y,
        "width": layer.width,
        "height": layer.height,
        "z": layer.z,
        "rotation": layer.rotation,
        "asset": asset_out(asset) if asset else None,
    }
