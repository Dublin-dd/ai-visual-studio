"""生成任务调度：任务先落库再执行，单 worker 串行消费，重启后可恢复。

状态机：QUEUED → RUNNING → SUCCEEDED | FAILED
"""

import logging
import threading
import time
from datetime import datetime, timezone

from pathlib import Path

from sqlalchemy import func, select

from .. import config, models
from ..db import SessionLocal
from . import alpha, edit_client, image_client, storage, storyboard, tts_client, video_client, watermark
from .compose import ComposeError
from .media import MediaError

log = logging.getLogger("task_runner")

# 商品保真护栏：追加到每个带货镜头的提示词末尾。
# 图生视频模型只见过首帧一个角度，被要求转体时会“猜”没见过的面而失真，
# 因此这里统一禁止旋转/翻面，只允许推拉与轻微平移。
PRODUCT_FIDELITY_GUARD = (
    "\n\n【商品保真约束】商品全程正面朝向镜头，不旋转、不翻面、不展示背面或侧面；"
    "商品的外观、颜色、材质、比例、logo 文字必须保持完全不变，"
    "不得变形、拉伸、压扁、融化，不得增加或减少镜头、按钮等结构；画面稳定。"
)

_stop = threading.Event()
_thread: threading.Thread | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def reset_running_tasks() -> int:
    """服务启动时把残留的 RUNNING 任务重置为 QUEUED（断点续跑，不丢稿）。"""
    db = SessionLocal()
    try:
        rows = db.scalars(select(models.Task).where(models.Task.status == "RUNNING")).all()
        for t in rows:
            t.status = "QUEUED"
        db.commit()
        if rows:
            log.info("重置 %d 个中断任务为排队状态", len(rows))
        return len(rows)
    finally:
        db.close()


def today_task_count() -> int:
    """今日已创建的生成任务数，用于成本护栏。"""
    db = SessionLocal()
    try:
        start = _now().replace(hour=0, minute=0, second=0, microsecond=0)
        return (
            db.scalar(
                select(func.count())
                .select_from(models.Task)
                .where(models.Task.created_at >= start)
            )
            or 0
        )
    finally:
        db.close()


def claim_one() -> str | None:
    """原子地领一个排队任务并标为 RUNNING。返回任务 id。"""
    db = SessionLocal()
    try:
        task = db.scalars(
            select(models.Task)
            .where(models.Task.status == "QUEUED")
            .order_by(models.Task.created_at)
            .limit(1)
        ).first()
        if task is None:
            return None
        task.status = "RUNNING"
        task.attempts = (task.attempts or 0) + 1
        task.updated_at = _now()
        db.commit()
        return task.id
    finally:
        db.close()


def process_task(task_id: str) -> None:
    """执行单个任务。失败写入可读错误，不抛出。"""
    db = SessionLocal()
    try:
        task = db.get(models.Task, task_id)
        if task is None or task.status != "RUNNING":
            return
        asset_ids: list[str] = []
        used_model = ""
        cost = 0.0
        try:
            if task.kind == "image_generate":
                for _ in range(task.count):
                    data, used_model = image_client.generate_image(
                        prompt=task.prompt,
                        width=task.width,
                        height=task.height,
                        tier=task.tier,
                    )
                    asset_ids.append(_save_asset(db, task, data))
                    cost += config.IMAGE_COST_PER_IMAGE

            elif task.kind == "cutout":
                source = _source_bytes(db, task)
                data, _seed = edit_client.edit_image(
                    prompt=edit_client.cutout_prompt(), image_bytes=source
                )
                used_model = config.EDIT_MODEL
                cost += config.IMAGE_COST_PER_IMAGE
                asset_ids.append(_save_asset(db, task, data))
                # 本地把纯白背景转透明，产出第二张透明底图
                try:
                    alpha_bytes = alpha.white_to_alpha(data)
                    asset_ids.append(_save_asset(db, task, alpha_bytes, suffix="_alpha"))
                except Exception:  # noqa: BLE001  透明底失败不影响白底图产出
                    log.warning("透明底生成失败，已保留白底图", exc_info=True)

            elif task.kind == "image_edit":
                source = _source_bytes(db, task)
                seed = (task.params or {}).get("seed")
                used_model = config.EDIT_MODEL
                for _ in range(task.count):
                    data, _seed = edit_client.edit_image(
                        prompt=edit_client.scene_prompt(task.prompt),
                        image_bytes=source,
                        seed=seed,
                    )
                    asset_ids.append(_save_asset(db, task, data))
                    cost += config.IMAGE_COST_PER_IMAGE

            elif task.kind == "sku_variants":
                source = _source_bytes(db, task)
                colors = (task.params or {}).get("colors") or []
                seed = (task.params or {}).get("seed")
                used_model = config.EDIT_MODEL
                for color in colors:
                    data, _seed = edit_client.edit_image(
                        prompt=edit_client.sku_prompt(color),
                        image_bytes=source,
                        seed=seed,
                    )
                    asset_ids.append(_save_asset(db, task, data))
                    cost += config.IMAGE_COST_PER_IMAGE

            elif task.kind == "storyboard":
                script_id = (task.params or {}).get("script_id")
                script = db.get(models.Script, script_id) if script_id else None
                if script is None:
                    raise ValueError("剧本不存在")
                names = [
                    c.name
                    for c in db.scalars(
                        select(models.Character).where(
                            models.Character.project_id == task.project_id
                        )
                    ).all()
                ]
                shots = storyboard.generate_storyboard(script.content, names)

                # 先删旧分镜再写入，保证失败时不产生半套数据
                for old in db.scalars(
                    select(models.Shot).where(models.Shot.project_id == task.project_id)
                ).all():
                    db.delete(old)
                db.flush()
                for item in shots:
                    db.add(
                        models.Shot(
                            project_id=task.project_id,
                            index=item["index"],
                            scene=item["scene"],
                            camera=item["camera"],
                            description=item["description"],
                            dialogue=item["dialogue"],
                            duration=item["duration"],
                            character_names=item["character_names"],
                        )
                    )
                used_model = config.LLM_MODEL
                cost += config.LLM_COST_PER_CALL
                task.count = len(shots)

            elif task.kind == "video_generate":
                shot_id = (task.params or {}).get("shot_id")
                shot = db.get(models.Shot, shot_id) if shot_id else None
                if shot is None:
                    raise ValueError("分镜不存在")

                # 首帧参考：取该镜头出场角色里第一个有定妆照的
                names = shot.character_names or []
                first_frame = None
                used_character = ""
                for name in names:
                    ch = db.scalars(
                        select(models.Character).where(
                            models.Character.project_id == task.project_id,
                            models.Character.name == name,
                        )
                    ).first()
                    if ch and ch.ref_asset_id:
                        asset = db.get(models.Asset, ch.ref_asset_id)
                        if asset and Path(asset.path).exists():
                            first_frame = Path(asset.path).read_bytes()
                            used_character = name
                            break

                prompt = task.prompt or shot.description
                request_id, used_model = video_client.submit(
                    prompt=prompt, image_bytes=first_frame
                )
                task.params = {
                    **(task.params or {}),
                    "request_id": request_id,
                    "first_frame_character": used_character,
                    "mode": "i2v" if first_frame else "t2v",
                }
                db.commit()

                data = video_client.wait_and_download(request_id)
                asset_ids.append(_save_video(db, task, data, shot))
                cost += config.VIDEO_COST_PER_CLIP

            elif task.kind == "sale_video_generate":
                # 带货视频出片：首帧 = 商品图，prompt = 分镜画面描述
                sale_shot_id = (task.params or {}).get("sale_shot_id")
                product_asset_id = (task.params or {}).get("product_asset_id")
                sale_shot = db.get(models.SaleShot, sale_shot_id) if sale_shot_id else None
                if sale_shot is None:
                    raise ValueError("带货分镜不存在")
                product_asset = db.get(models.Asset, product_asset_id) if product_asset_id else None
                if product_asset is None or not Path(product_asset.path).exists():
                    raise ValueError("商品图不存在，请先上传商品图")

                first_frame = Path(product_asset.path).read_bytes()
                # 统一转成 9:16 竖屏首帧：视频输出比例跟随首帧，带货视频必须是竖屏
                from .product_frame import to_vertical_canvas

                try:
                    # 按景别控制商品占比：同一张商品图能产出构图不同的首帧
                    first_frame = to_vertical_canvas(first_frame, scene=sale_shot.scene)
                except Exception:  # noqa: BLE001  预处理失败时退回原图，不让任务因此失败
                    log.warning("商品图 9:16 预处理失败，使用原图作首帧", exc_info=True)

                # 断点续跑：已经提交过的任务直接继续轮询，绝不重复提交（会二次计费）
                existing_rid = (task.params or {}).get("request_id")
                if existing_rid:
                    request_id = existing_rid
                    used_model = config.VIDEO_MODEL_I2V
                    log.info("任务 %s 继续轮询已提交的视频 %s（不重复计费）", task.id, request_id)
                else:
                    # 商品保真护栏：禁止模型展示未见过角度、擅改外观
                    # 实际视频请求必须使用分镜的运动字段，不能只把它显示在UI。
                    movement = {
                        "固定": "固定机位，保持当前构图，不推近、不拉远、不平移。",
                        "缓慢推近": "仅做一次轻微缓慢推近，不改变商品朝向。",
                        "缓慢拉远": "缓慢轻微拉远，逐渐增加留白，不改变商品朝向。",
                        "轻微平移": "轻微水平平移，保持同一正面视角，不环绕商品。",
                    }.get(sale_shot.camera, "固定机位，保持当前构图。")
                    prompt = (f"本镜头使用{sale_shot.scene}首帧。运动以此为准：{movement}\n"
                              + (task.prompt or sale_shot.description) + PRODUCT_FIDELITY_GUARD)
                    request_id, used_model = video_client.submit(
                        prompt=prompt, image_bytes=first_frame
                    )
                    task.params = {
                        **(task.params or {}),
                        "request_id": request_id,
                        "mode": "i2v",
                        "frame_normalized": True,
                    }
                    db.commit()

                data = video_client.wait_and_download(request_id)
                asset_id = _save_video(db, task, data, sale_shot)
                asset_ids.append(asset_id)
                sale_shot.video_asset_id = asset_id
                cost += config.VIDEO_COST_PER_CLIP

            elif task.kind == "sale_compose":
                # 成片合成：镜头片段 + 旁白 + 字幕 + BGM
                from . import compose as compose_svc

                script_id = (task.params or {}).get("script_id")
                script = db.get(models.SaleScript, script_id) if script_id else None
                if script is None:
                    raise ValueError("带货脚本不存在")
                shots = db.scalars(
                    select(models.SaleShot)
                    .where(models.SaleShot.script_id == script.id)
                    .order_by(models.SaleShot.index)
                ).all()
                shot_payload = []
                for s in shots:
                    if not s.video_asset_id:
                        raise ValueError(f"镜头{s.index}还没有视频，无法合成")
                    va = db.get(models.Asset, s.video_asset_id)
                    if va is None or not Path(va.path).exists():
                        raise ValueError(f"镜头{s.index}的视频文件丢失")
                    shot_payload.append(
                        {"index": s.index, "video_path": va.path, "voiceover": s.voiceover}
                    )

                bgm = db.scalars(
                    select(models.Bgm)
                    .where(models.Bgm.project_id == task.project_id)
                    .order_by(models.Bgm.created_at.desc())
                    .limit(1)
                ).first()
                bgm_path = Path(bgm.path) if bgm and Path(bgm.path).exists() else None

                out_name = f"{task.id}.mp4"
                out_path = config.FINAL_DIR / out_name
                result = compose_svc.compose(shot_payload, out_path, bgm_path=bgm_path)

                final_asset = models.Asset(
                    owner_id=task.owner_id,
                    project_id=task.project_id,
                    kind="final",
                    filename=out_name,
                    path=str(out_path),
                    mime="video/mp4",
                    width=720,
                    height=1280,
                    size_bytes=out_path.stat().st_size,
                )
                db.add(final_asset)
                db.flush()
                script.final_asset_id = final_asset.id
                asset_ids.append(final_asset.id)
                task.params = {**(task.params or {}), "duration": result["duration"]}
                used_model = "ffmpeg"
                cost += config.TTS_COST_PER_CALL * max(1, len(shot_payload))

            else:
                raise ValueError(f"未知任务类型 {task.kind}")

            if task.kind != "storyboard" and not asset_ids:
                raise ValueError("任务没有产出任何结果")

            task.model = used_model
            task.asset_ids = asset_ids
            task.cost_estimate = round(cost, 4)
            task.status = "SUCCEEDED"
            task.error_code = ""
            task.error_message = ""
        except storage.UploadRejected as e:
            task.status = "FAILED"
            task.error_code = e.code
            task.error_message = e.message
        except (
            image_client.ImageServiceError,
            edit_client.ImageServiceError,
            storyboard.LLMError,
            tts_client.TTSError,
            ComposeError,
            MediaError,
        ) as e:
            task.status = "FAILED"
            task.error_code = e.code
            task.error_message = e.message
        except Exception as e:  # noqa: BLE001  兜底：任何异常都转成可读错误
            task.status = "FAILED"
            task.error_code = "TASK_INTERNAL_ERROR"
            # 自己抛的 ValueError 文案是写给用户看的，直接透出；其余不泄露内部细节
            if isinstance(e, ValueError) and str(e):
                task.error_message = str(e)
            else:
                task.error_message = f"生成失败（{type(e).__name__}）"
        task.updated_at = _now()
        db.commit()
        if task.status == "SUCCEEDED" and task.kind == "sale_video_generate":
            _maybe_enqueue_compose(db, task)
        log.info(
            "任务 %s → %s（模型=%s，成本估算=%.2f 元）",
            task.id,
            task.status,
            task.model or "-",
            task.cost_estimate or 0.0,
        )
    finally:
        db.close()


def resume_download(task_id: str) -> bool:
    """网络恢复后，只重试“下载”已生成的视频，不重新提交任务、不重复计费。

    仅对保存了 request_id 的带货镜头任务有效。成功返回 True。
    """
    db = SessionLocal()
    try:
        task = db.get(models.Task, task_id)
        if task is None or task.kind != "sale_video_generate":
            return False
        request_id = (task.params or {}).get("request_id")
        sale_shot_id = (task.params or {}).get("sale_shot_id")
        if not request_id or not sale_shot_id:
            return False
        shot = db.get(models.SaleShot, sale_shot_id)
        if shot is None:
            return False

        task.status = "RUNNING"
        task.updated_at = _now()
        db.commit()
        try:
            data = video_client.wait_and_download(request_id)
            asset_id = _save_video(db, task, data, shot)
            shot.video_asset_id = asset_id
            task.asset_ids = [asset_id]
            task.status = "SUCCEEDED"
            task.error_code = ""
            task.error_message = ""
            task.cost_estimate = 0.0  # 本次仅为下载，未产生新的生成费用
            db.commit()
            _maybe_enqueue_compose(db, task)
            return True
        except Exception as exc:  # noqa: BLE001
            task.status = "FAILED"
            task.error_code = "VIDEO_DOWNLOAD_FAILED"
            task.error_message = f"重新下载仍然失败：{exc}"
            task.updated_at = _now()
            db.commit()
            return False
    finally:
        db.close()


def _maybe_enqueue_compose(db, task: models.Task) -> None:
    """所有带货镜头都出片完成后，自动排一个成片合成任务。"""
    script = db.scalars(
        select(models.SaleScript).where(models.SaleScript.project_id == task.project_id)
    ).first()
    if script is None:
        return
    shots = db.scalars(
        select(models.SaleShot).where(models.SaleShot.script_id == script.id)
    ).all()
    if not shots or any(not s.video_asset_id for s in shots):
        return
    existing_pending = db.scalars(
        select(models.Task).where(
            models.Task.project_id == task.project_id,
            models.Task.kind == "sale_compose",
            models.Task.status.in_(("QUEUED", "RUNNING")),
        )
    ).first()
    if existing_pending is not None:
        return

    # 已有合成结果时，只有“镜头比成片新”才重新合成（例如重做了某个镜头）
    last_compose = db.scalars(
        select(models.Task)
        .where(
            models.Task.project_id == task.project_id,
            models.Task.kind == "sale_compose",
        )
        .order_by(models.Task.created_at.desc())
        .limit(1)
    ).first()
    if last_compose is not None:
        latest_video = db.scalars(
            select(models.Task)
            .where(
                models.Task.project_id == task.project_id,
                models.Task.kind == "sale_video_generate",
                models.Task.status == "SUCCEEDED",
            )
            .order_by(models.Task.updated_at.desc())
            .limit(1)
        ).first()
        if latest_video is None or last_compose.created_at >= latest_video.updated_at:
            return
    db.add(
        models.Task(
            owner_id=task.owner_id,
            project_id=task.project_id,
            kind="sale_compose",
            status="QUEUED",
            prompt="成片合成",
            params={"script_id": script.id},
            cost_estimate=0.0,
        )
    )
    db.commit()
    log.info("项目 %s 镜头已齐，已排入成片合成任务", task.project_id)


def _source_bytes(db, task: models.Task) -> bytes:
    """读取源素材文件内容。"""
    source_id = (task.params or {}).get("source_asset_id")
    if not source_id:
        raise ValueError("缺少源素材")
    asset = db.get(models.Asset, source_id)
    if asset is None:
        raise ValueError("源素材不存在")
    with open(asset.path, "rb") as f:
        raw = f.read()
    # 编辑前清理旧水印，避免模型重画旧水印造成重影
    cleaned, patched = watermark.strip_old_watermark(raw)
    if patched:
        log.info("源素材 %s 已清理旧水印区域", asset.id)
    return cleaned


def _save_video(db, task: models.Task, data: bytes, shot: models.Shot) -> str:
    """视频落盘（data/videos）并入库，kind=video。"""
    import uuid as _uuid

    name = f"{_uuid.uuid4().hex}.mp4"
    path = config.VIDEO_DIR / name
    path.write_bytes(data)
    asset = models.Asset(
        owner_id=task.owner_id,
        project_id=task.project_id,
        kind="video",
        filename=name,
        path=str(path),
        mime="video/mp4",
        width=0,
        height=0,
        size_bytes=len(data),
    )
    db.add(asset)
    db.flush()
    return asset.id


def _save_asset(db, task: models.Task, data: bytes, suffix: str = "") -> str:
    """把图片字节落盘并入库，返回资产 id。"""
    path, name, w, h, mime = storage.save_generated(data)
    if suffix:
        name = name.replace(".png", f"{suffix}.png")
        new_path = path.with_name(name)
        path.rename(new_path)
        path = new_path
    asset = models.Asset(
        owner_id=task.owner_id,
        project_id=task.project_id,
        kind="generated",
        filename=name,
        path=str(path),
        mime=mime,
        width=w,
        height=h,
        size_bytes=len(data),
    )
    db.add(asset)
    db.flush()
    return asset.id


def process_pending(limit: int = 10) -> int:
    """消费至多 limit 个排队任务，返回处理数。测试直接调用它，不起线程。"""
    done = 0
    for _ in range(limit):
        tid = claim_one()
        if tid is None:
            break
        process_task(tid)
        done += 1
    return done


def _loop() -> None:
    while not _stop.is_set():
        try:
            if process_pending(limit=5) == 0:
                _stop.wait(config.WORKER_POLL_SECONDS)
        except Exception:  # noqa: BLE001  worker 不能因单次异常退出
            log.exception("worker 循环异常")
            _stop.wait(config.WORKER_POLL_SECONDS)


def start_worker() -> None:
    global _thread
    if not config.WORKER_ENABLED or _thread is not None:
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="task-worker", daemon=True)
    _thread.start()


def stop_worker() -> None:
    global _thread
    _stop.set()
    if _thread is not None:
        _thread.join(timeout=3)
        _thread = None


def wait_until_idle(timeout: float = 30.0) -> bool:
    """等待队列清空（冒烟与测试用）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process_pending(limit=10) == 0:
            return True
        time.sleep(0.05)
    return False


def resume_failed_downloads(limit: int = 10) -> int:
    """启动时补下载：之前因网络失败但已生成的视频，免费救回。

    只处理带货镜头且保存了 request_id 的失败任务——不会重新提交、不重复计费。
    """
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(models.Task)
            .where(
                models.Task.kind == "sale_video_generate",
                models.Task.status == "FAILED",
            )
            .limit(limit)
        ).all()
        ids = [r.id for r in rows if (r.params or {}).get("request_id")]
    finally:
        db.close()

    ok = 0
    for tid in ids:
        if resume_download(tid):
            ok += 1
    if ids:
        log.info("启动补下载：成功 %d/%d", ok, len(ids))
    return ok
