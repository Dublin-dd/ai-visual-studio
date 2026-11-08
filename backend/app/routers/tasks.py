from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, models, schemas
from ..db import get_db
from ..errors import err
from ..services import task_runner
from ..services.presenters import asset_out, task_out

router = APIRouter(prefix="/api", tags=["tasks"])



def _with_assets(db: Session, task: models.Task) -> dict:
    """任务详情统一附带素材（列表接口也需要，前端据 asset_ids 回填画布）。"""
    data = task_out(task)
    ids = task.asset_ids or []
    if ids:
        assets = db.scalars(select(models.Asset).where(models.Asset.id.in_(ids))).all()
        order = {aid: i for i, aid in enumerate(ids)}
        data["assets"] = [
            asset_out(a) for a in sorted(assets, key=lambda a: order.get(a.id, 0))
        ]
    else:
        data["assets"] = []
    return data

EDIT_KINDS = ("cutout", "image_edit", "sku_variants")


@router.post("/tasks", status_code=201)
def create_task(body: schemas.TaskCreate, db: Session = Depends(get_db)):
    prompt = body.prompt.strip()
    kind = body.kind
    params: dict = {}

    if kind == "image_generate":
        if not prompt:
            return err(400, "VALIDATION_ERROR", "提示词不能为空")
        if body.count > config.MAX_IMAGES_PER_TASK:
            return err(400, "VALIDATION_ERROR", f"单次最多生成 {config.MAX_IMAGES_PER_TASK} 张")
    else:
        # 编辑类任务必须有源素材，切必须属于本项目
        if not body.source_asset_id:
            return err(400, "SOURCE_REQUIRED", "请先选择要编辑的商品图")
        source = db.scalars(
            select(models.Asset).where(
                models.Asset.id == body.source_asset_id,
                models.Asset.owner_id == config.DEFAULT_OWNER_ID,
            )
        ).first()
        if source is None or source.project_id != body.project_id:
            return err(404, "SOURCE_NOT_FOUND", "源素材不存在或不属于本项目")
        params["source_asset_id"] = source.id

        if kind == "image_edit" and not prompt:
            return err(400, "PROMPT_REQUIRED", "请描述想要的背景场景")
        if kind == "sku_variants":
            colors = [c.strip() for c in body.colors if c.strip()]
            if not colors:
                return err(400, "VALIDATION_ERROR", "请至少填写一个颜色")
            if len(colors) > config.MAX_SKU_VARIANTS:
                return err(
                    400,
                    "VALIDATION_ERROR",
                    f"单次最多生成 {config.MAX_SKU_VARIANTS} 个 SKU 变体",
                )
            params["colors"] = colors
            body.count = len(colors)
        if body.seed is not None:
            params["seed"] = body.seed

    project = db.scalars(
        select(models.Project).where(
            models.Project.id == body.project_id,
            models.Project.owner_id == config.DEFAULT_OWNER_ID,
        )
    ).first()
    if project is None:
        return err(404, "NOT_FOUND", "项目不存在")

    if task_runner.today_task_count() >= config.DAILY_TASK_LIMIT:
        return err(429, "DAILY_LIMIT_REACHED", "今日生成额度已用完，请明天再试或调整配置")

    task = models.Task(
        owner_id=config.DEFAULT_OWNER_ID,
        project_id=body.project_id,
        kind=kind,
        status="QUEUED",
        prompt=prompt,
        width=body.width,
        height=body.height,
        count=body.count,
        tier=body.tier,
        params=params,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task_out(task)


@router.get("/tasks/{task_id}")
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.scalars(
        select(models.Task).where(
            models.Task.id == task_id,
            models.Task.owner_id == config.DEFAULT_OWNER_ID,
        )
    ).first()
    if task is None:
        return err(404, "NOT_FOUND", "任务不存在")
    return _with_assets(db, task)


@router.get("/projects/{project_id}/assets")
def list_project_assets(
    project_id: str, kind: str | None = None, db: Session = Depends(get_db)
):
    if kind is not None and kind not in ("upload", "generated", "export", "video"):
        return err(
            422, "VALIDATION_ERROR", "kind 只能是 upload / generated / export / video"
        )
    stmt = select(models.Asset).where(
        models.Asset.project_id == project_id,
        models.Asset.owner_id == config.DEFAULT_OWNER_ID,
    )
    if kind:
        stmt = stmt.where(models.Asset.kind == kind)
    rows = db.scalars(stmt.order_by(models.Asset.created_at.desc()).limit(200)).all()
    return {"items": [asset_out(a) for a in rows]}


@router.get("/projects/{project_id}/tasks")
def list_project_tasks(project_id: str, db: Session = Depends(get_db)):
    project = db.scalars(
        select(models.Project).where(
            models.Project.id == project_id,
            models.Project.owner_id == config.DEFAULT_OWNER_ID,
        )
    ).first()
    if project is None:
        return err(404, "NOT_FOUND", "项目不存在")
    rows = db.scalars(
        select(models.Task)
        .where(
            models.Task.project_id == project_id,
            models.Task.owner_id == config.DEFAULT_OWNER_ID,
        )
        .order_by(models.Task.created_at.desc())
        .limit(50)
    ).all()
    return {"items": [_with_assets(db, t) for t in rows]}
