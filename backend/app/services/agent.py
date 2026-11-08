"""Agent 编排层：工作流状态机 + 意图识别 + 对话推进。

带货视频流程相对固定，主 Agent 用确定性状态机驱动（借鉴 ArcReel 的编排思路，
但不引入重框架）：

    idle → awaiting_product → script_draft → script_confirmed → （后续接报价/出片）

LLM 只负责「动脑」（卖点分析、脚本、分镜），状态流转与确认点由代码写死，
花钱的动作在后续阶段由确定性代码 + 人工确认约束。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config, models
from .llm_client import LLMError
from .sale_script import generate_sale_script, parse_product_request_llm

# 工作流阶段
W_IDLE = "idle"
W_AWAITING_PRODUCT = "awaiting_product"
W_SCRIPT_DRAFT = "script_draft"
W_SCRIPT_CONFIRMED = "script_confirmed"
W_AWAITING_PRODUCT_IMAGE = "awaiting_product_image"
W_QUOTE_DRAFT = "quote_draft"
W_GENERATING = "generating"
W_COMPOSING = "composing"
W_FINAL_REVIEW = "final_review"
W_DONE = "done"

_START_KEYWORDS = ["带货视频", "卖货视频", "做视频", "广告视频", "带货", "推广视频", "短视频"]
_CONFIRM_KEYWORDS = ["确认", "可以", "ok", "就这样", "没问题", "通过", "同意", "行吧"]
_REDO_KEYWORDS = ["重做", "重新", "换一个", "重写", "再来", "不行", "不好", "不满意"]

_GUIDE_AWAITING = (
    "好的！为了写出符合你需要的脚本，先确认三件事：\n\n"
    "1️⃣ 视频风格（三选一）\n"
    "　· 叫卖式——热情催单：「家人们这个真的绝了，赶紧冲！」\n"
    "　· 种草式——真实亲切：「我用了两周，说说真实感受」\n"
    "　· 品牌式——大牌质感：「有些东西，用过就回不去」\n\n"
    "2️⃣ 发到哪个平台：抖音 / 淘宝 / 拼多多 / 其他\n\n"
    "3️⃣ 商品信息：商品名 + 卖点\n\n"
    "可以一条消息全告诉我，例如：\n"
    "「商品是保温杯，卖点是保温12小时，品牌式，发抖音」"
)
_GUIDE_DRAFT = "请回复「确认」继续，或「重做」让我重新生成脚本。"


def detect_intent(message: str) -> str:
    """确定性意图识别。带货视频意图明确，无需 LLM。"""
    m = (message or "").strip().lower()
    if m in _CONFIRM_KEYWORDS:
        return "confirm"
    if any(k in m for k in _REDO_KEYWORDS):
        return "redo"
    if any(k in m for k in _START_KEYWORDS):
        return "start"
    return "other"


def get_or_create_session(db: Session, project_id: str, owner_id: str) -> models.AgentSession:
    session = db.scalars(
        select(models.AgentSession).where(
            models.AgentSession.project_id == project_id,
            models.AgentSession.owner_id == owner_id,
        )
    ).first()
    if session is None:
        session = models.AgentSession(owner_id=owner_id, project_id=project_id)
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def add_message(
    db: Session,
    session: models.AgentSession,
    role: str,
    kind: str,
    content: str = "",
    payload: dict | None = None,
) -> models.AgentMessage:
    msg = models.AgentMessage(
        session_id=session.id, role=role, kind=kind, content=content, payload=payload or {}
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def _reply(content: str, workflow: str, kind: str = "text", payload: dict | None = None) -> dict:
    return {"kind": kind, "content": content, "payload": payload or {}, "workflow": workflow}


def _detect_style(text: str) -> str:
    """从文本识别视频风格，默认种草式。"""
    if any(k in text for k in ["叫卖", "催单", "硬广"]):
        return "叫卖式"
    if any(k in text for k in ["品牌", "大牌", "高端", "质感"]):
        return "品牌式"
    return "种草式"


def _detect_platform(text: str) -> str:
    """从文本识别发布平台，默认其他。"""
    if "抖音" in text:
        return "抖音"
    if "淘宝" in text or "天猫" in text:
        return "淘宝"
    if "拼多多" in text:
        return "拼多多"
    return "其他"


_STOP_WORDS = {
    "叫卖式", "叫卖", "种草式", "种草", "品牌式", "品牌", "大牌",
    "抖音", "淘宝", "拼多多", "天猫", "发抖音", "发淘宝", "发拼多多",
}


def _parse_product_request(message: str) -> tuple[str, list[str], str, str]:
    """从自由文本里提取 商品名 / 卖点 / 风格 / 平台。

    预期格式举例：「商品是保温杯，卖点是保温12小时、不漏水，品牌式，发抖音」。
    """
    import re

    text = message.strip()
    name = ""
    points: list[str] = []

    # 商品名：取「商品是 X」之后、逗号/句号/卖点之前的一段
    m = re.search(r"商品[是：:]\s*([^，。,。；;]+)", text)
    if m:
        name = m.group(1).strip()

    # 卖点：取「卖点是 X」之后整段，按顿号/逗号/空白拆，并过滤风格/平台词
    m2 = re.search(r"卖点[是：:]\s*(.+)$", text)
    if m2:
        raw = m2.group(1).strip()
        points = [p for p in re.split(r"[、,，;；\s]+", raw) if p and p not in _STOP_WORDS]

    # 没有明确「商品是」标记时不猜，返回空让上层引导，避免误生成
    return name, points, _detect_style(text), _detect_platform(text)


def current_workflow(db: Session, session: models.AgentSession) -> str:
    """只读对账：由当前分镜和合成产物推导展示阶段，不创建任务或调用模型。"""
    if session.workflow not in (W_GENERATING, W_COMPOSING):
        return session.workflow
    done, total = _generation_progress(db, session.project_id)
    if not total or done != total:
        return W_GENERATING
    script = _current_script(db, session.project_id)
    if script and script.final_asset_id and db.get(models.Asset, script.final_asset_id):
        return W_FINAL_REVIEW
    return W_COMPOSING


def handle_chat(db: Session, session: models.AgentSession, message: str) -> dict:
    """处理一条用户消息，推进状态机，返回 Agent 回复。"""
    intent = detect_intent(message)
    workflow = current_workflow(db, session)
    session.workflow = workflow

    # 0) 单镜头重做：任何已出片的阶段都允许（会产生费用）
    import re as _re

    m = _re.search(r"重做(?:第)?\s*(?:镜头)?\s*(\d+)", message.strip())
    if m and workflow in (W_GENERATING, W_COMPOSING, W_FINAL_REVIEW, W_DONE, W_QUOTE_DRAFT):
        return _redo_shot(db, session, int(m.group(1)))

    # 1) 启动带货视频流程
    if intent == "start" and workflow in (W_IDLE, W_AWAITING_PRODUCT):
        session.workflow = W_AWAITING_PRODUCT
        db.commit()
        return _reply(_GUIDE_AWAITING, W_AWAITING_PRODUCT)

    # 2) 脚本草稿阶段的确认 / 重做
    if workflow == W_SCRIPT_DRAFT:
        if intent == "confirm":
            script = _current_script(db, session.project_id)
            if script is not None:
                script.status = "confirmed"
            session.workflow = W_AWAITING_PRODUCT_IMAGE
            db.commit()
            return _reply(
                "脚本已确认 ✅ 请上传商品图（会作为每个镜头的首帧）。上传后告诉我「图传好了」。",
                W_AWAITING_PRODUCT_IMAGE,
            )
        if intent == "redo":
            return _regenerate(db, session)
        return _reply(_GUIDE_DRAFT, W_SCRIPT_DRAFT)

    # 3) 等待商品信息阶段：尝试从消息里提取商品信息并生成脚本
    if workflow == W_AWAITING_PRODUCT:
        name, points, style, platform = _parse_product_request(message)
        if name:
            return _generate_script(db, session, name, points, style, platform)
        # 正则没提取到商品名，用 LLM 兜底理解自然表达（如「小米手机 续航三天」）
        try:
            parsed = parse_product_request_llm(message)
            if parsed["product_name"]:
                return _generate_script(
                    db,
                    session,
                    parsed["product_name"],
                    parsed["selling_points"],
                    parsed["style"],
                    parsed["platform"],
                )
        except LLMError:
            pass
        return _reply(_GUIDE_AWAITING, W_AWAITING_PRODUCT)

    # 4) 等待商品图 → 出报价单
    if workflow == W_AWAITING_PRODUCT_IMAGE:
        product_asset = _latest_upload_asset(db, session.project_id)
        if product_asset is None:
            return _reply(
                "还没找到商品图，请先上传商品图，然后告诉我「图传好了」。",
                W_AWAITING_PRODUCT_IMAGE,
            )
        return _make_quote(db, session, product_asset)

    # 5) 报价单：确认出片 / 重做脚本
    if workflow == W_QUOTE_DRAFT:
        if intent == "confirm":
            return _start_generation(db, session)
        if intent == "redo":
            return _regenerate(db, session)
        return _reply("请回复「确认」开始出片（会产生费用），或「重做」重新生成脚本。", W_QUOTE_DRAFT)

    # 6) 出片中：报进度；全部完成后进入合成
    if workflow == W_GENERATING:
        # 「重试下载」：网络恢复后只补下载，不重复计费
        if any(k in message for k in ("重试下载", "重新下载", "补下载")):
            return _retry_downloads(db, session)
        done, total = _generation_progress(db, session.project_id)
        if total > 0 and done >= total:
            session.workflow = W_COMPOSING
            db.commit()
            return _reply(
                f"{total} 段视频已全部生成 ✅ 正在配音、写字幕、合成成片（约 1~2 分钟）。稍后问我「进度」。",
                W_COMPOSING,
            )
        return _reply(
            f"出片进行中：已完成 {done}/{total} 段（每段约 3~6 分钟），稍后再问我「进度」。",
            W_GENERATING,
        )

    # 7) 合成中：查成片
    if workflow == W_COMPOSING:
        if message.strip() == "重试合成":
            return _reply("重新合成会再次调用配音，可能产生配音费用。确认后回复「确认重试合成」。", workflow)
        if message.strip() == "确认重试合成":
            script = _current_script(db, session.project_id)
            done, total = _generation_progress(db, session.project_id)
            if not script or not total or done != total:
                return _reply("请先完成所有镜头。", workflow)
            pending = db.scalars(select(models.Task).where(
                models.Task.project_id == session.project_id,
                models.Task.kind == "sale_compose",
                models.Task.status.in_(("QUEUED", "RUNNING")))).first()
            if not pending:
                db.add(models.Task(owner_id=session.owner_id, project_id=session.project_id,
                    kind="sale_compose", status="QUEUED", prompt="重试合成",
                    params={"script_id": script.id}, cost_estimate=0.0))
                db.commit()
            return _reply("已排队合成，不重新生成视频；配音仍可能产生费用。", workflow)
        return _check_final(db, session)

    if workflow == W_FINAL_REVIEW:
        if message.strip() == "进度":
            return _check_final(db, session)
        if intent == "confirm":
            session.workflow = W_DONE
            session.status = "done"
            db.commit()
            return handle_chat(db, session, "进度")
        return _reply("请预览成片后回复「确认」，或指定「重做镜头 N」。", W_FINAL_REVIEW)

    # 8) 完成态
    if workflow == W_DONE:
        script = _current_script(db, session.project_id)
        asset = db.get(models.Asset, script.final_asset_id) if script and script.final_asset_id else None
        if asset:
            return _reply(
                "成片已就绪 ✅ 可在右侧预览与下载。如需重做某个镜头，告诉我镜头序号。",
                W_DONE,
                kind="final_card",
                payload={"total": len(_shots(db, session.project_id)), "video_url": f"/api/files/{asset.id}", "asset_id": asset.id},
            )
        return _reply("成片已生成。如需新的一条，重新开始即可。", W_DONE)

    # 9) 默认：引导
    if workflow == W_SCRIPT_CONFIRMED:
        return _reply("脚本已确认，请上传商品图开始出片。", W_AWAITING_PRODUCT_IMAGE)
    if workflow in (W_IDLE,):
        return _reply("你好！想做带货视频的话，直接说「帮我做带货视频」即可。", W_IDLE)
    return _reply(_GUIDE_AWAITING, workflow or W_IDLE)


def _shots(db: Session, project_id: str) -> list[models.SaleShot]:
    return db.scalars(
        select(models.SaleShot)
        .where(models.SaleShot.project_id == project_id)
        .order_by(models.SaleShot.index)
    ).all()


def _redo_shot(db: Session, session: models.AgentSession, index: int) -> dict:
    """重做单个镜头：清掉该镜头旧视频并重新提交生成（会产生费用）。"""
    shots = _shots(db, session.project_id)
    if not shots:
        return _reply("还没有分镜，请先生成脚本。", W_AWAITING_PRODUCT)
    target = next((s for s in shots if s.index == index), None)
    if target is None:
        numbers = "、".join(str(s.index) for s in shots)
        return _reply(f"没有第 {index} 个镜头。可选：{numbers}。", session.workflow)

    script = _current_script(db, session.project_id)
    if script is None or not script.product_asset_id:
        return _reply("缺少商品图，请先上传商品图。", W_AWAITING_PRODUCT_IMAGE)

    pending = db.scalars(select(models.Task).where(
        models.Task.project_id == session.project_id,
        models.Task.kind == "sale_video_generate",
        models.Task.status.in_(("QUEUED", "RUNNING")))).all()
    if any((task.params or {}).get("sale_shot_id") == target.id for task in pending):
        return _reply("该镜头正在排队或生成中，请等待完成。", session.workflow)
    compose_pending = db.scalars(select(models.Task).where(
        models.Task.project_id == session.project_id,
        models.Task.kind == "sale_compose",
        models.Task.status.in_(("QUEUED", "RUNNING")))).first()
    if compose_pending:
        return _reply("成片正在合成，请完成后再重做镜头。", session.workflow)
    target.video_asset_id = None
    script.final_asset_id = None
    session.status = "active"
    db.add(
        models.Task(
            owner_id=session.owner_id,
            project_id=session.project_id,
            kind="sale_video_generate",
            status="QUEUED",
            prompt=target.description,
            params={"sale_shot_id": target.id, "product_asset_id": script.product_asset_id},
            cost_estimate=config.VIDEO_COST_PER_CLIP,
        )
    )
    session.workflow = W_GENERATING
    db.commit()
    return _reply(
        f"已重新提交第 {index} 个镜头的生成（预计 ¥{config.VIDEO_COST_PER_CLIP:.1f}，约 3~6 分钟）。"
        f"完成后会自动重新合成成片。",
        W_GENERATING,
    )


def _retry_downloads(db: Session, session: models.AgentSession) -> dict:
    """网络恢复后补下载已生成的视频；不重新提交、不重复计费。"""
    from . import task_runner

    tasks = db.scalars(
        select(models.Task).where(
            models.Task.project_id == session.project_id,
            models.Task.kind == "sale_video_generate",
            models.Task.status == "FAILED",
        )
    ).all()
    candidates = [t for t in tasks if (t.params or {}).get("request_id")]
    if not candidates:
        return _reply(
            "没有可补下载的片段（可能都需要重新生成）。",
            W_GENERATING,
        )

    ok = 0
    for t in candidates:
        if task_runner.resume_download(t.id):
            ok += 1
    done, total = _generation_progress(db, session.project_id)
    if total > 0 and done >= total:
        session.workflow = W_COMPOSING
        db.commit()
        return _reply(
            f"补下载完成（{ok}/{len(candidates)}）✅ 全部镜头已就绪，正在合成成片。",
            W_COMPOSING,
        )
    return _reply(
        f"补下载完成 {ok}/{len(candidates)} 段，当前进度 {done}/{total}。如仍失败，请检查网络后再试。",
        W_GENERATING,
    )


def _check_final(db: Session, session: models.AgentSession) -> dict:
    """查询成片合成任务状态；完成则升为 DONE 并返回成片链接。"""
    task = db.scalars(
        select(models.Task)
        .where(
            models.Task.project_id == session.project_id,
            models.Task.kind == "sale_compose",
        )
        .order_by(models.Task.created_at.desc())
        .limit(1)
    ).first()

    if task is None:
        return _reply("镜头已全部生成，正在排队合成成片…", W_COMPOSING)
    if task.status in ("QUEUED", "RUNNING"):
        return _reply("正在配音、写字幕、合成成片（约 1~2 分钟），请稍候再问我「进度」。", W_COMPOSING)
    if task.status == "FAILED":
        return _reply(
            f"成片合成失败：{task.error_message or '未知原因'}。可以回复「重试合成」再试一次。",
            W_COMPOSING,
        )

    script = _current_script(db, session.project_id)
    asset = db.get(models.Asset, script.final_asset_id) if script and script.final_asset_id else None
    if asset is None:
        return _reply("成片文件缺失，请回复「重试合成」。", W_COMPOSING)
    session.workflow = W_FINAL_REVIEW
    db.commit()
    payload = {"total": len(_shots(db, session.project_id)), "confirmed": False}
    if asset:
        payload.update({"video_url": f"/api/files/{asset.id}", "asset_id": asset.id})
    return _reply(
        "成片已生成，请预览后回复「确认」，或指定重做镜头。",
        W_FINAL_REVIEW,
        kind="final_card",
        payload=payload,
    )


def _latest_upload_asset(db: Session, project_id: str) -> models.Asset | None:
    """项目里最近上传的一张图，作为带货视频的商品图。"""
    return db.scalars(
        select(models.Asset)
        .where(models.Asset.project_id == project_id, models.Asset.kind == "upload")
        .order_by(models.Asset.created_at.desc())
        .limit(1)
    ).first()


def _make_quote(db: Session, session: models.AgentSession, product_asset: models.Asset) -> dict:
    """按分镜数计算出片报价，生成报价单卡片。"""
    shots = db.scalars(
        select(models.SaleShot).where(models.SaleShot.project_id == session.project_id)
    ).all()
    if not shots:
        return _reply("脚本分镜不存在，请先重新生成脚本。", W_AWAITING_PRODUCT)
    count = len(shots)
    unit = config.VIDEO_COST_PER_CLIP
    total = round(count * unit, 2)
    script = _current_script(db, session.project_id)
    if script is not None:
        script.product_asset_id = product_asset.id
    session.workflow = W_QUOTE_DRAFT
    db.commit()
    payload = {
        "shot_count": count,
        "unit_cost": unit,
        "total_cost": total,
        "product_asset_id": product_asset.id,
    }
    return _reply(
        f"出片报价：共 {count} 个镜头，每段约 ¥{unit}，合计约 ¥{total}。\n确认开始出片吗？回复「确认」会产生费用，「重做」则重新生成脚本。",
        W_QUOTE_DRAFT,
        kind="quote_card",
        payload=payload,
    )


def _start_generation(db: Session, session: models.AgentSession) -> dict:
    """为每个分镜创建一个出片任务，进入生成态。"""
    script = _current_script(db, session.project_id)
    shots = db.scalars(
        select(models.SaleShot)
        .where(models.SaleShot.project_id == session.project_id)
        .order_by(models.SaleShot.index)
    ).all()
    if script is None or not script.product_asset_id:
        return _reply("缺少商品图，请先上传商品图。", W_AWAITING_PRODUCT_IMAGE)
    if not shots:
        return _reply("脚本分镜不存在，请先重新生成脚本。", W_AWAITING_PRODUCT)
    for s in shots:
        db.add(
            models.Task(
                owner_id=session.owner_id,
                project_id=session.project_id,
                kind="sale_video_generate",
                status="QUEUED",
                prompt=s.description,
                params={"sale_shot_id": s.id, "product_asset_id": script.product_asset_id},
                cost_estimate=config.VIDEO_COST_PER_CLIP,
            )
        )
    session.workflow = W_GENERATING
    db.commit()
    return _reply(
        f"已提交 {len(shots)} 个出片任务，正在逐个生成（每段约 6 分钟）。完成后问我「进度」即可。",
        W_GENERATING,
    )


def _generation_progress(db: Session, project_id: str) -> tuple[int, int]:
    """只统计当前分镜，历史重做任务不增加镜头数。"""
    shots = _shots(db, project_id)
    return sum(bool(shot.video_asset_id) for shot in shots), len(shots)


def _current_script(db: Session, project_id: str) -> models.SaleScript | None:
    return db.scalars(
        select(models.SaleScript).where(models.SaleScript.project_id == project_id)
    ).first()


def _generate_script(
    db: Session,
    session: models.AgentSession,
    name: str,
    points: list[str],
    style: str = "种草式",
    platform: str = "其他",
) -> dict:
    """调 LLM 生成脚本 + 分镜，落库，返回脚本卡片。"""
    result = generate_sale_script(name, points, style=style, platform=platform)

    # 覆盖式更新：先删旧脚本与旧分镜，保证失败时不产生半套数据
    old_script = _current_script(db, session.project_id)
    if old_script is not None:
        for old_shot in db.scalars(
            select(models.SaleShot).where(models.SaleShot.script_id == old_script.id)
        ).all():
            db.delete(old_shot)
        db.delete(old_script)
        db.flush()

    script = models.SaleScript(
        project_id=session.project_id,
        product_name=result["product_name"] or name,
        selling_points=result["selling_points"],
        audience=result["audience"],
        script_text=result["script_text"],
        style=style,
        platform=platform,
        status="draft",
    )
    db.add(script)
    db.flush()

    shots_payload = []
    for s in result["shots"]:
        db.add(
            models.SaleShot(
                script_id=script.id,
                project_id=session.project_id,
                index=s["index"],
                scene=s["scene"],
                camera=s["camera"],
                description=s["description"],
                voiceover=s["voiceover"],
                duration=s["duration"],
            )
        )
        shots_payload.append(s)

    session.workflow = W_SCRIPT_DRAFT
    db.commit()

    payload = {
        "script_id": script.id,
        "product_name": script.product_name,
        "audience": script.audience,
        "hook": result.get("hook", ""),
        "selling_points": script.selling_points,
        "script_text": script.script_text,
        "shots": shots_payload,
    }
    return _reply(
        "带货脚本已生成，请审阅。确认没问题就回复「确认」，不满意回复「重做」。",
        W_SCRIPT_DRAFT,
        kind="script_card",
        payload=payload,
    )


def _regenerate(db: Session, session: models.AgentSession) -> dict:
    """用上一份脚本的商品信息与风格重新生成。"""
    script = _current_script(db, session.project_id)
    if script is None:
        return _reply(_GUIDE_AWAITING, W_AWAITING_PRODUCT)
    return _generate_script(
        db,
        session,
        script.product_name,
        list(script.selling_points or []),
        style=script.style or "种草式",
        platform=script.platform or "其他",
    )
