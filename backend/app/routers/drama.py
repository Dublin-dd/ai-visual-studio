"""短剧工作台：剧本 / 分镜表 / 角色库。"""

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, models, schemas_drama
from ..db import get_db
from ..errors import err
from ..services import storage, task_runner
from ..services.presenters import asset_out, task_out

router = APIRouter(prefix="/api/drama", tags=["drama"])


def _project(db: Session, project_id: str) -> models.Project | None:
    return db.scalars(
        select(models.Project).where(
            models.Project.id == project_id,
            models.Project.owner_id == config.DEFAULT_OWNER_ID,
        )
    ).first()


def _require_drama(db: Session, project_id: str):
    project = _project(db, project_id)
    if project is None:
        return None, err(404, "NOT_FOUND", "项目不存在")
    if project.workspace != "drama":
        return None, err(400, "WORKSPACE_MISMATCH", "该项目不是短剧工作台项目")
    return project, None


def script_out(s: models.Script) -> dict:
    return {
        "id": s.id,
        "project_id": s.project_id,
        "title": s.title,
        "content": s.content,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def shot_out(s: models.Shot) -> dict:
    return {
        "id": s.id,
        "index": s.index,
        "scene": s.scene,
        "camera": s.camera,
        "description": s.description,
        "dialogue": s.dialogue,
        "duration": s.duration,
        "character_names": s.character_names or [],
    }


def character_out(c: models.Character, asset: models.Asset | None) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "description": c.description,
        "ref_asset": asset_out(asset) if asset else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


# ---------- 剧本 ----------


@router.post("/projects/{project_id}/script")
def save_script(project_id: str, body: schemas_drama.ScriptIn, db: Session = Depends(get_db)):
    project, error = _require_drama(db, project_id)
    if error:
        return error
    content = body.content.strip()
    if not content:
        return err(400, "VALIDATION_ERROR", "剧本内容不能为空")

    script = db.scalars(
        select(models.Script).where(models.Script.project_id == project_id)
    ).first()
    if script is None:
        script = models.Script(project_id=project_id)
        db.add(script)
    script.title = (body.title or "").strip()[:255]
    script.content = content
    db.commit()
    db.refresh(script)
    return script_out(script)


@router.get("/projects/{project_id}/script")
def get_script(project_id: str, db: Session = Depends(get_db)):
    _, error = _require_drama(db, project_id)
    if error:
        return error
    script = db.scalars(
        select(models.Script).where(models.Script.project_id == project_id)
    ).first()
    return {"script": script_out(script) if script else None}


# ---------- 分镜 ----------


@router.post("/projects/{project_id}/storyboard", status_code=201)
def create_storyboard_task(project_id: str, db: Session = Depends(get_db)):
    _, error = _require_drama(db, project_id)
    if error:
        return error

    script = db.scalars(
        select(models.Script).where(models.Script.project_id == project_id)
    ).first()
    if script is None or not script.content.strip():
        return err(400, "SCRIPT_REQUIRED", "请先保存剧本再生成分镜")

    running = db.scalar(
        select(func.count())
        .select_from(models.Task)
        .where(
            models.Task.project_id == project_id,
            models.Task.kind == "storyboard",
            models.Task.status.in_(("QUEUED", "RUNNING")),
        )
    )
    if running:
        return err(409, "TASK_RUNNING", "已有分镜任务在生成中，请稍候")

    task = models.Task(
        owner_id=config.DEFAULT_OWNER_ID,
        project_id=project_id,
        kind="storyboard",
        status="QUEUED",
        prompt=script.title or "分镜生成",
        params={"script_id": script.id},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task_out(task)


@router.get("/projects/{project_id}/shots")
def list_shots(project_id: str, db: Session = Depends(get_db)):
    _, error = _require_drama(db, project_id)
    if error:
        return error
    rows = db.scalars(
        select(models.Shot)
        .where(models.Shot.project_id == project_id)
        .order_by(models.Shot.index)
    ).all()
    return {"items": [shot_out(s) for s in rows]}


@router.put("/projects/{project_id}/shots")
def replace_shots(
    project_id: str, body: schemas_drama.ShotsReplace, db: Session = Depends(get_db)
):
    _, error = _require_drama(db, project_id)
    if error:
        return error
    if len(body.shots) > config.MAX_SHOTS:
        return err(400, "TOO_MANY_SHOTS", f"镜头数超过上限（{config.MAX_SHOTS}）")

    for old in db.scalars(
        select(models.Shot).where(models.Shot.project_id == project_id)
    ).all():
        db.delete(old)
    db.flush()

    for i, item in enumerate(body.shots, start=1):
        db.add(
            models.Shot(
                project_id=project_id,
                index=i,
                scene=item.scene,
                camera=item.camera,
                description=item.description.strip(),
                dialogue=item.dialogue.strip(),
                duration=item.duration,
                character_names=[n.strip() for n in item.character_names if n.strip()],
            )
        )
    db.commit()
    return list_shots(project_id, db)


# ---------- 角色库 ----------


@router.get("/projects/{project_id}/characters")
def list_characters(project_id: str, db: Session = Depends(get_db)):
    _, error = _require_drama(db, project_id)
    if error:
        return error
    rows = db.scalars(
        select(models.Character)
        .where(models.Character.project_id == project_id)
        .order_by(models.Character.created_at)
    ).all()
    assets = {
        a.id: a
        for a in db.scalars(
            select(models.Asset).where(models.Asset.project_id == project_id)
        ).all()
    }
    return {
        "items": [
            character_out(c, assets.get(c.ref_asset_id) if c.ref_asset_id else None)
            for c in rows
        ]
    }


@router.post("/projects/{project_id}/characters", status_code=201)
def create_character(
    project_id: str, body: schemas_drama.CharacterIn, db: Session = Depends(get_db)
):
    _, error = _require_drama(db, project_id)
    if error:
        return error
    name = body.name.strip()
    if not name:
        return err(400, "VALIDATION_ERROR", "角色名不能为空")
    exists = db.scalars(
        select(models.Character).where(
            models.Character.project_id == project_id, models.Character.name == name
        )
    ).first()
    if exists:
        return err(400, "DUPLICATE_NAME", "同名角色已存在")

    c = models.Character(
        project_id=project_id, name=name, description=body.description.strip()
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return character_out(c, None)


@router.patch("/projects/{project_id}/characters/{cid}")
def patch_character(
    project_id: str,
    cid: str,
    body: schemas_drama.CharacterPatch,
    db: Session = Depends(get_db),
):
    _, error = _require_drama(db, project_id)
    if error:
        return error
    c = db.scalars(
        select(models.Character).where(
            models.Character.id == cid, models.Character.project_id == project_id
        )
    ).first()
    if c is None:
        return err(404, "NOT_FOUND", "角色不存在")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            return err(400, "VALIDATION_ERROR", "角色名不能为空")
        dup = db.scalars(
            select(models.Character).where(
                models.Character.project_id == project_id,
                models.Character.name == name,
                models.Character.id != cid,
            )
        ).first()
        if dup:
            return err(400, "DUPLICATE_NAME", "同名角色已存在")
        c.name = name
    if body.description is not None:
        c.description = body.description.strip()
    db.commit()
    db.refresh(c)
    asset = db.get(models.Asset, c.ref_asset_id) if c.ref_asset_id else None
    return character_out(c, asset)


@router.delete("/projects/{project_id}/characters/{cid}")
def delete_character(project_id: str, cid: str, db: Session = Depends(get_db)):
    _, error = _require_drama(db, project_id)
    if error:
        return error
    c = db.scalars(
        select(models.Character).where(
            models.Character.id == cid, models.Character.project_id == project_id
        )
    ).first()
    if c is None:
        return err(404, "NOT_FOUND", "角色不存在")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/characters/{cid}/ref")
async def upload_character_ref(
    project_id: str,
    cid: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    _, error = _require_drama(db, project_id)
    if error:
        return error
    c = db.scalars(
        select(models.Character).where(
            models.Character.id == cid, models.Character.project_id == project_id
        )
    ).first()
    if c is None:
        return err(404, "NOT_FOUND", "角色不存在")

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > config.MAX_UPLOAD_BYTES:
            limit_mb = config.MAX_UPLOAD_BYTES // (1024 * 1024)
            return err(400, "FILE_TOO_LARGE", f"文件超过 {limit_mb}MB 限制")
        chunks.append(chunk)

    try:
        fmt, width, height = storage.validate_image_bytes(b"".join(chunks))
        path, name, size = storage.save_upload(b"".join(chunks), fmt)
    except storage.UploadRejected as e:
        return err(400, e.code, e.message)

    asset = models.Asset(
        owner_id=config.DEFAULT_OWNER_ID,
        project_id=project_id,
        kind="upload",
        filename=name,
        path=str(path),
        mime={"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(
            fmt, "image/png"
        ),
        width=width,
        height=height,
        size_bytes=size,
    )
    db.add(asset)
    db.flush()
    c.ref_asset_id = asset.id
    db.commit()
    db.refresh(c)
    return character_out(c, asset)


# ---------- 视频出片（2-4） ----------


def _shot(db: Session, project_id: str, shot_id: str) -> models.Shot | None:
    return db.scalars(
        select(models.Shot).where(
            models.Shot.id == shot_id, models.Shot.project_id == project_id
        )
    ).first()


@router.post("/projects/{project_id}/shots/{shot_id}/video", status_code=201)
def create_shot_video_task(
    project_id: str, shot_id: str, db: Session = Depends(get_db)
):
    """单镜头出片。首帧优先用该镜头出场角色的定妆照。"""
    _, error = _require_drama(db, project_id)
    if error:
        return error
    shot = _shot(db, project_id, shot_id)
    if shot is None:
        return err(404, "NOT_FOUND", "分镜不存在")

    running = db.scalar(
        select(func.count())
        .select_from(models.Task)
        .where(
            models.Task.project_id == project_id,
            models.Task.kind == "video_generate",
            models.Task.status.in_(("QUEUED", "RUNNING")),
        )
    )
    if running and running >= config.MAX_VIDEOS_PER_BATCH:
        return err(409, "TOO_MANY_RUNNING", "排队中的视频任务太多，请等待完成")

    if task_runner.today_task_count() >= config.DAILY_TASK_LIMIT:
        return err(429, "DAILY_LIMIT_REACHED", "今日任务额度已用完，请明天再试或调整配置")

    task = models.Task(
        owner_id=config.DEFAULT_OWNER_ID,
        project_id=project_id,
        kind="video_generate",
        status="QUEUED",
        prompt=shot.description,
        params={"shot_id": shot.id, "shot_index": shot.index},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task_out(task)


class BatchVideoIn(BaseModel):
    shot_ids: list[str] = Field(default_factory=list, max_length=60)


@router.post("/projects/{project_id}/videos/batch", status_code=201)
def create_batch_video_tasks(
    project_id: str, body: BatchVideoIn, db: Session = Depends(get_db)
):
    """批量出片：把所有（或指定）镜头排入视频任务队列。"""
    _, error = _require_drama(db, project_id)
    if error:
        return error

    stmt = select(models.Shot).where(models.Shot.project_id == project_id)
    if body.shot_ids:
        stmt = stmt.where(models.Shot.id.in_(body.shot_ids))
    shots = db.scalars(stmt.order_by(models.Shot.index)).all()
    if not shots:
        return err(400, "NO_SHOTS", "没有可出片的镜头")

    if len(shots) > config.MAX_VIDEOS_PER_BATCH:
        return err(
            400,
            "TOO_MANY_SHOTS",
            f"单次最多出片 {config.MAX_VIDEOS_PER_BATCH} 个镜头",
        )

    tasks = []
    for shot in shots:
        task = models.Task(
            owner_id=config.DEFAULT_OWNER_ID,
            project_id=project_id,
            kind="video_generate",
            status="QUEUED",
            prompt=shot.description,
            params={"shot_id": shot.id, "shot_index": shot.index},
        )
        db.add(task)
        tasks.append(task)
    db.commit()
    return {
        "count": len(tasks),
        "estimated_cost": round(len(tasks) * config.VIDEO_COST_PER_CLIP, 2),
        "items": [task_out(t) for t in tasks],
    }


@router.get("/projects/{project_id}/videos")
def list_videos(project_id: str, db: Session = Depends(get_db)):
    _, error = _require_drama(db, project_id)
    if error:
        return error
    # 每个镜头最新一条视频
    rows = db.scalars(
        select(models.Task)
        .where(
            models.Task.project_id == project_id,
            models.Task.kind == "video_generate",
            models.Task.status == "SUCCEEDED",
        )
        .order_by(models.Task.created_at.desc())
        .limit(100)
    ).all()
    out: dict[str, dict] = {}
    for t in rows:
        shot_id = (t.params or {}).get("shot_id")
        if not shot_id or shot_id in out:
            continue
        ids = t.asset_ids or []
        asset = db.get(models.Asset, ids[0]) if ids else None
        out[shot_id] = {
            "task_id": t.id,
            "shot_id": shot_id,
            "asset": asset_out(asset) if asset else None,
            "mode": (t.params or {}).get("mode"),
            "model": t.model,
        }
    return {"items": list(out.values())}
