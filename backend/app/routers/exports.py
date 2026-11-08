from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, models, schemas
from ..db import get_db
from ..errors import err
from ..services import render
from ..services.presenters import asset_out

router = APIRouter(prefix="/api/projects", tags=["exports"])


@router.post("/{project_id}/export", status_code=201)
def export_canvas(project_id: str, db: Session = Depends(get_db)):
    project = db.scalars(
        select(models.Project).where(
            models.Project.id == project_id,
            models.Project.owner_id == config.DEFAULT_OWNER_ID,
        )
    ).first()
    if project is None:
        return err(404, "NOT_FOUND", "项目不存在")

    layers = db.scalars(
        select(models.Layer)
        .where(models.Layer.project_id == project_id)
        .order_by(models.Layer.z, models.Layer.created_at)
    ).all()
    if not layers:
        return err(400, "EMPTY_CANVAS", "画布为空，先添加素材再导出")

    assets = {
        a.id: a
        for a in db.scalars(
            select(models.Asset).where(models.Asset.project_id == project_id)
        ).all()
    }

    specs = []
    for layer in layers:
        asset = assets.get(layer.asset_id)
        if asset is None:
            continue
        specs.append(
            {
                "path": asset.path,
                "x": layer.x,
                "y": layer.y,
                "width": layer.width,
                "height": layer.height,
                "z": layer.z,
                "rotation": layer.rotation,
            }
        )

    try:
        image = render.render_canvas(specs, background=project.background_color)
        path, name, size = render.save_export(image)
    except render.RenderError as e:
        return err(400, e.code, e.message)
    except Exception:  # noqa: BLE001  兜底：不向客户端泄露堆栈
        return err(500, "EXPORT_FAILED", "导出失败，请稍后重试")

    asset = models.Asset(
        owner_id=config.DEFAULT_OWNER_ID,
        project_id=project_id,
        kind="export",
        filename=name,
        path=str(path),
        mime="image/png",
        width=image.width,
        height=image.height,
        size_bytes=size,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return {"asset": asset_out(asset)}
