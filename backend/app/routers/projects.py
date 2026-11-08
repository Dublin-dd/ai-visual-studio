from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, models, schemas
from ..db import get_db
from ..errors import err
from ..services.presenters import layer_out

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _get_project(db: Session, project_id: str) -> models.Project | None:
    """只在当前使用者范围内查，前端隐藏不算权限控制。"""
    return db.scalars(
        select(models.Project).where(
            models.Project.id == project_id,
            models.Project.owner_id == config.DEFAULT_OWNER_ID,
        )
    ).first()


def project_out(p: models.Project, asset_count: int | None = None) -> dict:
    data = {
        "id": p.id,
        "name": p.name,
        "workspace": p.workspace,
        "cover_asset_id": p.cover_asset_id,
        "background_color": p.background_color,
        "owner_id": p.owner_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
    if asset_count is not None:
        data["asset_count"] = asset_count
    return data


@router.post("", status_code=201)
def create_project(body: schemas.ProjectCreate, db: Session = Depends(get_db)):
    name = (body.name or "").strip() or "未命名项目"
    project = models.Project(
        owner_id=config.DEFAULT_OWNER_ID,
        name=name[:255],
        workspace=body.workspace,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project_out(project)


@router.get("")
def list_projects(workspace: str | None = None, db: Session = Depends(get_db)):
    if workspace is not None and workspace not in ("ecommerce", "drama"):
        return err(422, "VALIDATION_ERROR", "workspace 只能是 ecommerce 或 drama")

    stmt = select(models.Project).where(models.Project.owner_id == config.DEFAULT_OWNER_ID)
    if workspace:
        stmt = stmt.where(models.Project.workspace == workspace)
    rows = db.scalars(stmt.order_by(models.Project.updated_at.desc()).limit(100)).all()

    counts = dict(
        db.execute(
            select(models.Asset.project_id, func.count())
            .where(models.Asset.owner_id == config.DEFAULT_OWNER_ID)
            .group_by(models.Asset.project_id)
        ).all()
    )
    return {"items": [project_out(p, counts.get(p.id, 0)) for p in rows]}


@router.get("/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = _get_project(db, project_id)
    if project is None:
        return err(404, "NOT_FOUND", "项目不存在")
    return project_out(project)


@router.patch("/{project_id}")
def rename_project(
    project_id: str, body: schemas.ProjectRename, db: Session = Depends(get_db)
):
    project = _get_project(db, project_id)
    if project is None:
        return err(404, "NOT_FOUND", "项目不存在")
    name = body.name.strip()
    if not name:
        return err(400, "VALIDATION_ERROR", "项目名不能为空")
    project.name = name[:255]
    db.commit()
    db.refresh(project)
    return project_out(project)


@router.put("/{project_id}/cover")
def set_project_cover(project_id: str, body: schemas.ProjectCover, db: Session = Depends(get_db)):
    project = _get_project(db, project_id)
    if project is None:
        return err(404, "NOT_FOUND", "项目不存在")
    if body.asset_id is not None:
        asset = db.get(models.Asset, body.asset_id)
        if (asset is None or asset.project_id != project_id or asset.owner_id != project.owner_id
                or not asset.mime.startswith("image/")):
            return err(400, "INVALID_COVER", "请选择当前项目的图片")
    project.cover_asset_id = body.asset_id
    db.commit()
    return project_out(project)


@router.put("/{project_id}/background")
def set_board_background(project_id: str, body: schemas.BoardBackground, db: Session = Depends(get_db)):
    project = _get_project(db, project_id)
    if project is None:
        return err(404, "NOT_FOUND", "项目不存在")
    project.background_color = body.color.upper()
    db.commit()
    return project_out(project)


@router.get("/{project_id}/layers")
def get_layers(project_id: str, db: Session = Depends(get_db)):
    project = _get_project(db, project_id)
    if project is None:
        return err(404, "NOT_FOUND", "项目不存在")
    rows = db.scalars(
        select(models.Layer)
        .where(models.Layer.project_id == project_id)
        .order_by(models.Layer.z, models.Layer.created_at)
    ).all()
    assets = {
        a.id: a
        for a in db.scalars(
            select(models.Asset).where(models.Asset.project_id == project_id)
        ).all()
    }
    return {"items": [layer_out(layer, assets.get(layer.asset_id)) for layer in rows]}


@router.put("/{project_id}/layers")
def replace_layers(
    project_id: str, body: schemas.LayersUpdate, db: Session = Depends(get_db)
):
    project = _get_project(db, project_id)
    if project is None:
        return err(404, "NOT_FOUND", "项目不存在")

    if len(body.layers) > config.MAX_LAYERS_PER_PROJECT:
        return err(
            400,
            "TOO_MANY_LAYERS",
            f"图层数量超过上限（{config.MAX_LAYERS_PER_PROJECT}）",
        )

    asset_ids = {layer.asset_id for layer in body.layers}
    owned = set(
        db.scalars(
            select(models.Asset.id).where(
                models.Asset.project_id == project_id,
                models.Asset.id.in_(asset_ids) if asset_ids else False,
            )
        ).all()
    )
    missing = asset_ids - owned
    if missing:
        return err(400, "ASSET_NOT_IN_PROJECT", "存在不属于本项目的素材，无法保存画布")

    for old in db.scalars(
        select(models.Layer).where(models.Layer.project_id == project_id)
    ).all():
        db.delete(old)
    db.flush()

    for item in body.layers:
        db.add(
            models.Layer(
                project_id=project_id,
                asset_id=item.asset_id,
                x=item.x,
                y=item.y,
                width=item.width,
                height=item.height,
                z=item.z,
                rotation=item.rotation,
            )
        )
    db.commit()
    return get_layers(project_id, db)
