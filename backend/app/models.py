import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    cover_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    background_color: Mapped[str] = mapped_column(String(7), default="#FFFFFF", server_default="#FFFFFF")
    workspace: Mapped[str] = mapped_column(String(32), default="ecommerce", index=True)
    name: Mapped[str] = mapped_column(String(255), default="未命名项目")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Asset(Base):
    """上传的或生成的图片。文件落盘，元数据入库。"""

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="upload")  # upload / generated / export
    filename: Mapped[str] = mapped_column(String(255), default="")
    path: Mapped[str] = mapped_column(String(500), default="")
    mime: Mapped[str] = mapped_column(String(64), default="image/png")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Task(Base):
    """生成任务。先落库再执行，进程重启后可恢复。"""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="image_generate")
    status: Mapped[str] = mapped_column(String(16), default="QUEUED", index=True)
    prompt: Mapped[str] = mapped_column(Text, default="")
    width: Mapped[int] = mapped_column(Integer, default=1024)
    height: Mapped[int] = mapped_column(Integer, default=1024)
    count: Mapped[int] = mapped_column(Integer, default=1)
    tier: Mapped[str] = mapped_column(String(16), default="standard")  # draft / standard / hq
    model: Mapped[str] = mapped_column(String(120), default="")
    error_code: Mapped[str] = mapped_column(String(64), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    asset_ids: Mapped[list] = mapped_column(JSON, default=list)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Layer(Base):
    """画布图层：图片 + 位置 + 尺寸 + 层级。"""

    __tablename__ = "layers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id"))
    x: Mapped[float] = mapped_column(Float, default=0.0)
    y: Mapped[float] = mapped_column(Float, default=0.0)
    width: Mapped[float] = mapped_column(Float, default=300.0)
    height: Mapped[float] = mapped_column(Float, default=300.0)
    z: Mapped[int] = mapped_column(Integer, default=1)
    rotation: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Script(Base):
    """短剧剧本：一个项目一份，重复保存即覆盖。"""

    __tablename__ = "scripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class Shot(Base):
    """分镜：一条对应一个镜头（2-4 出片的输入单位）。"""

    __tablename__ = "shots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    index: Mapped[int] = mapped_column(Integer, default=1)
    scene: Mapped[str] = mapped_column(String(16), default="中景")
    camera: Mapped[str] = mapped_column(String(16), default="固定")
    description: Mapped[str] = mapped_column(Text, default="")
    dialogue: Mapped[str] = mapped_column(Text, default="")
    duration: Mapped[int] = mapped_column(Integer, default=5)
    character_names: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Character(Base):
    """角色档案：定妆照是 2-4 图生视频的首帧。"""

    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    ref_asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("assets.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AgentSession(Base):
    """Agent 对话会话：一个带货视频项目对应一个进行中的会话。"""

    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / done
    workflow: Mapped[str] = mapped_column(String(32), default="idle")  # 当前工作流阶段
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class AgentMessage(Base):
    """对话消息：用户指令 + Agent 回复（文本或卡片）。"""

    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("agent_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="user")  # user / assistant
    kind: Mapped[str] = mapped_column(String(32), default="text")  # text / script_card / quote_card / final_card
    content: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class SaleScript(Base):
    """带货脚本：一个项目一份，重复生成即覆盖。"""

    __tablename__ = "sale_scripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    product_name: Mapped[str] = mapped_column(String(255), default="")
    selling_points: Mapped[list] = mapped_column(JSON, default=list)  # 卖家提供的卖点文字
    audience: Mapped[str] = mapped_column(String(255), default="")
    script_text: Mapped[str] = mapped_column(Text, default="")  # 完整口播文案
    style: Mapped[str] = mapped_column(String(16), default="种草式")  # 叫卖式/种草式/品牌式
    platform: Mapped[str] = mapped_column(String(16), default="其他")  # 抖音/淘宝/拼多多/其他
    product_asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("assets.id"), nullable=True
    )  # 商品图（出片首帧）
    final_asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("assets.id"), nullable=True
    )  # 成片
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft / confirmed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class SaleShot(Base):
    """带货分镜：一条对应一个镜头，出片的输入单位。"""

    __tablename__ = "sale_shots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    script_id: Mapped[str] = mapped_column(String(36), ForeignKey("sale_scripts.id"), index=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    index: Mapped[int] = mapped_column(Integer, default=1)
    scene: Mapped[str] = mapped_column(String(16), default="中景")
    camera: Mapped[str] = mapped_column(String(16), default="固定")
    description: Mapped[str] = mapped_column(Text, default="")  # 画面：商品如何展示
    voiceover: Mapped[str] = mapped_column(Text, default="")    # 该镜头口播文案
    duration: Mapped[int] = mapped_column(Integer, default=5)
    video_asset_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("assets.id"), nullable=True
    )  # 出片结果
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Bgm(Base):
    """项目级背景音乐：用户上传，合成时混入。"""

    __tablename__ = "bgm"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255), default="")
    path: Mapped[str] = mapped_column(String(500), default="")
    duration: Mapped[float] = mapped_column(Float, default=0.0)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
