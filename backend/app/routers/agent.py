"""Agent 对话：工作流推进 + 带货脚本生成（3-2-a）。"""

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config, models
from ..db import get_db
from ..errors import err
from ..services import agent, media
from ..services.project_gate import project_gate

router = APIRouter(prefix="/api/agent", tags=["agent"])


class ChatIn(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=36)
    card_id: str | None = None
    final_asset_id: str | None = Field(default=None, max_length=36)
    message: str = Field(..., min_length=1, max_length=4000)


def _project(db: Session, project_id: str) -> models.Project | None:
    return db.scalars(
        select(models.Project).where(
            models.Project.id == project_id,
            models.Project.owner_id == config.DEFAULT_OWNER_ID,
        )
    ).first()


def message_out(m: models.AgentMessage) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "kind": m.kind,
        "content": m.content,
        "payload": m.payload or {},
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.post("/chat")
def chat(body: ChatIn, db: Session = Depends(get_db)):
    with project_gate(body.project_id) as acquired:
        if not acquired:
            return err(409, "PROJECT_BUSY", "该项目正在处理另一条指令，请稍后查看进度再操作。")
        project = _project(db, body.project_id)
        if project is None:
            return err(404, "NOT_FOUND", "项目不存在")

        session = agent.get_or_create_session(db, body.project_id, config.DEFAULT_OWNER_ID)
        if body.final_asset_id:
            script = agent._current_script(db, body.project_id)
            if (script is None or script.final_asset_id != body.final_asset_id
                    or agent.current_workflow(db, session) != agent.W_FINAL_REVIEW):
                return err(409, "STALE_FINAL", "成片已更新，请刷新后预览最新成片再确认。")
        if body.card_id:
            latest = db.scalars(select(models.AgentMessage).where(
                models.AgentMessage.session_id == session.id,
                models.AgentMessage.role == "assistant",
            ).order_by(models.AgentMessage.created_at.desc())).first()
            if latest is None or latest.id != body.card_id:
                return err(409, "STALE_CARD", "这张卡片已过期，请使用最新的确认卡片。")
        agent.add_message(db, session, "user", "text", body.message)
        reply = agent.handle_chat(db, session, body.message)
        response_message = agent.add_message(db, session, "assistant", reply["kind"], reply["content"], reply["payload"])
        return {"reply": reply, "workflow": reply["workflow"], "message_id": response_message.id}


@router.get("/projects/{project_id}/messages")
def list_messages(project_id: str, db: Session = Depends(get_db)):
    project = _project(db, project_id)
    if project is None:
        return err(404, "NOT_FOUND", "项目不存在")

    session = db.scalars(
        select(models.AgentSession).where(
            models.AgentSession.project_id == project_id,
            models.AgentSession.owner_id == config.DEFAULT_OWNER_ID,
        )
    ).first()
    if session is None:
        return {"messages": [], "workflow": agent.W_IDLE}

    msgs = db.scalars(
        select(models.AgentMessage)
        .where(models.AgentMessage.session_id == session.id)
        .order_by(models.AgentMessage.created_at)
    ).all()
    return {"messages": [message_out(m) for m in msgs], "workflow": agent.current_workflow(db, session)}


ALLOWED_BGM_EXT = {".mp3", ".wav", ".m4a"}


@router.post("/projects/{project_id}/bgm", status_code=201)
async def upload_bgm(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传背景音乐（可选）。合成时自动混入，音量固定较低，不盖旁白。"""
    project = _project(db, project_id)
    if project is None:
        return err(404, "NOT_FOUND", "项目不存在")

    suffix = ("." + (file.filename or "").rsplit(".", 1)[-1].lower()) if "." in (file.filename or "") else ""
    if suffix not in ALLOWED_BGM_EXT:
        return err(400, "BGM_TYPE_INVALID", "背景音乐只支持 MP3 / WAV / M4A")

    data = await file.read()
    if not data:
        return err(400, "BGM_EMPTY", "上传的音乐文件是空的")
    if len(data) > config.MAX_BGM_BYTES:
        return err(413, "BGM_TOO_LARGE", f"背景音乐不能超过 {config.MAX_BGM_BYTES // (1024 * 1024)}MB")

    import uuid

    name = f"{uuid.uuid4().hex}{suffix}"
    path = config.BGM_DIR / name
    path.write_bytes(data)
    duration = media.duration_of(path)
    if duration <= 0:
        path.unlink(missing_ok=True)
        return err(400, "BGM_INVALID", "这个文件不是有效的音频，请换一个")

    bgm = models.Bgm(
        project_id=project_id,
        filename=(file.filename or name)[:255],
        path=str(path),
        duration=round(duration, 2),
        size_bytes=len(data),
    )
    db.add(bgm)
    db.commit()
    db.refresh(bgm)
    return {
        "id": bgm.id,
        "filename": bgm.filename,
        "duration": bgm.duration,
        "size_bytes": bgm.size_bytes,
        "created_at": bgm.created_at.isoformat() if bgm.created_at else None,
    }


@router.get("/projects/{project_id}/bgm")
def list_bgm(project_id: str, db: Session = Depends(get_db)):
    project = _project(db, project_id)
    if project is None:
        return err(404, "NOT_FOUND", "项目不存在")
    rows = db.scalars(
        select(models.Bgm)
        .where(models.Bgm.project_id == project_id)
        .order_by(models.Bgm.created_at.desc())
    ).all()
    return {
        "items": [
            {
                "id": b.id,
                "filename": b.filename,
                "duration": b.duration,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in rows
        ],
        # 合成时使用最新上传的一首
        "active_id": rows[0].id if rows else None,
    }


@router.get("/projects/{project_id}/shots")
def list_shots(project_id: str, db: Session = Depends(get_db)):
    """镜头列表 + 每个镜头的出片状态（前端据此显示进度与重做入口）。"""
    project = _project(db, project_id)
    if project is None:
        return err(404, "NOT_FOUND", "项目不存在")

    shots = db.scalars(
        select(models.SaleShot)
        .where(models.SaleShot.project_id == project_id)
        .order_by(models.SaleShot.index)
    ).all()

    # 每个镜头最近一次出片任务的状态
    tasks = db.scalars(
        select(models.Task)
        .where(
            models.Task.project_id == project_id,
            models.Task.kind == "sale_video_generate",
        )
        .order_by(models.Task.created_at.desc())
    ).all()
    latest: dict[str, models.Task] = {}
    for t in tasks:
        sid = (t.params or {}).get("sale_shot_id")
        if sid and sid not in latest:
            latest[sid] = t

    items = []
    for s in shots:
        t = latest.get(s.id)
        if s.video_asset_id:
            status = "done"
        elif t is None:
            status = "pending"
        else:
            status = {"QUEUED": "queued", "RUNNING": "running", "FAILED": "failed"}.get(
                t.status, "pending"
            )
        items.append(
            {
                "index": s.index,
                "scene": s.scene,
                "camera": s.camera,
                "voiceover": s.voiceover,
                "description": s.description,
                "status": status,
                "video_url": f"/api/files/{s.video_asset_id}" if s.video_asset_id else None,
                "error": (t.error_message or None) if t is not None and t.status == "FAILED" else None,
            }
        )

    script = db.scalars(
        select(models.SaleScript).where(models.SaleScript.project_id == project_id)
    ).first()
    final_url = None
    if script is not None and script.final_asset_id:
        final_url = f"/api/files/{script.final_asset_id}"
    return {"items": items, "final_url": final_url}
