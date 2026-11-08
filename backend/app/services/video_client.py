"""视频生成客户端（SiliconFlow Wan2.2，异步任务）。

契约：
- POST /video/submit  {model, prompt, image?}         -> {requestId}
- POST /video/status  {requestId}                     -> {status, results:{videos:[{url}]}, reason}
  status: InQueue / InProgress / Succeed / Failed
"""

import base64
import time

import httpx

from .. import config
from .image_client import ImageServiceError


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.IMAGE_API_KEY}",
        "Content-Type": "application/json",
    }


def _ensure_key() -> None:
    if not config.IMAGE_API_KEY.strip():
        raise ImageServiceError(
            "VIDEO_KEY_MISSING", "未配置视频 API Key，请在 backend/.env 填写 IMAGE_API_KEY"
        )


def submit(
    *, prompt: str, image_bytes: bytes | None = None, model: str | None = None
) -> tuple[str, str]:
    """提交视频任务，返回 (requestId, 使用的模型)。"""
    _ensure_key()
    use_model = model or (config.VIDEO_MODEL_I2V if image_bytes else config.VIDEO_MODEL_T2V)
    payload: dict = {"model": use_model, "prompt": prompt}
    if image_bytes:
        payload["image"] = "data:image/png;base64," + base64.b64encode(image_bytes).decode()

    try:
        resp = httpx.post(
            f"{config.IMAGE_API_BASE_URL}/video/submit",
            json=payload,
            headers=_headers(),
            timeout=config.VIDEO_TIMEOUT_SECONDS,
            trust_env=False,  # 直连国内服务，剧本与商品图不出境
        )
    except httpx.TimeoutException:
        raise ImageServiceError("VIDEO_TIMEOUT", "视频任务提交超时，请稍后重试")
    except httpx.HTTPError:
        raise ImageServiceError("VIDEO_NETWORK", "视频服务连接失败，请稍后重试")

    if resp.status_code == 401:
        raise ImageServiceError("VIDEO_KEY_INVALID", "视频服务鉴权失败，请检查 API Key")
    if resp.status_code == 429:
        raise ImageServiceError("VIDEO_RATE_LIMIT", "视频服务限流，请稍后重试")
    if resp.status_code >= 500:
        raise ImageServiceError("VIDEO_UPSTREAM", "视频服务暂时不可用，请稍后重试")
    if resp.status_code != 200:
        raise ImageServiceError("VIDEO_BAD_REQUEST", "视频生成请求被拒绝，请检查描述与首帧图")

    try:
        request_id = resp.json()["requestId"]
    except (KeyError, ValueError):
        raise ImageServiceError("VIDEO_BAD_RESPONSE", "视频服务返回结构异常")
    if not request_id:
        raise ImageServiceError("VIDEO_BAD_RESPONSE", "视频服务未返回任务号")
    return request_id, use_model


def status(request_id: str) -> dict:
    try:
        resp = httpx.post(
            f"{config.IMAGE_API_BASE_URL}/video/status",
            json={"requestId": request_id},
            headers=_headers(),
            timeout=config.VIDEO_STATUS_TIMEOUT_SECONDS,
            trust_env=False,
        )
    except httpx.HTTPError:
        raise ImageServiceError("VIDEO_NETWORK", "视频服务连接失败，请稍后重试")
    if resp.status_code != 200:
        raise ImageServiceError("VIDEO_BAD_RESPONSE", "视频状态查询失败")
    try:
        return resp.json()
    except ValueError:
        raise ImageServiceError("VIDEO_BAD_RESPONSE", "视频服务返回结构异常")


def wait_and_download(
    request_id: str, max_wait: float | None = None, interval: float | None = None
) -> bytes:
    """轮询直到完成并下载视频字节。超时或失败抛 ImageServiceError。"""
    max_wait = config.VIDEO_MAX_WAIT_SECONDS if max_wait is None else max_wait
    interval = config.VIDEO_POLL_INTERVAL if interval is None else interval
    deadline = time.time() + max_wait
    last_status = ""
    consecutive_errors = 0

    while time.time() < deadline:
        try:
            data = status(request_id)
            consecutive_errors = 0
        except ImageServiceError as e:
            # 视频任务动辄数分钟，单次网络抖动不应判定失败；连续多次才放弃
            if e.code in ("VIDEO_NETWORK", "VIDEO_TIMEOUT", "VIDEO_BAD_RESPONSE"):
                consecutive_errors += 1
                if consecutive_errors >= 5:
                    raise
                time.sleep(interval)
                continue
            raise
        st = (data or {}).get("status") or ""
        last_status = st
        if st == "Succeed":
            videos = ((data.get("results") or {}).get("videos")) or []
            if not videos or not videos[0].get("url"):
                raise ImageServiceError("VIDEO_NO_RESULT", "视频生成完成但没有返回文件")
            url = videos[0]["url"]
            # 视频文件较大，下载重试 + 长超时，避免单次网络抖动就判失败。
            # 多条路径：先直连（数据不出境），失败再走系统代理（部分 VPN/TUN 只放行代理端口）。
            last_err: Exception | None = None
            for trust_env in (False, True, True):
                try:
                    resp = httpx.get(
                        url,
                        timeout=300.0,
                        trust_env=trust_env,
                        follow_redirects=True,
                    )
                    resp.raise_for_status()
                    return resp.content
                except httpx.HTTPError as exc:
                    last_err = exc
                    time.sleep(3)
            raise ImageServiceError(
                "VIDEO_DOWNLOAD_FAILED",
                "视频已生成，但下载失败（网络或代理拦截了视频域名 s3.6scloud.com）。"
                "请把代理切到全局模式或关闭代理后重试。",
            )
        if st == "Failed":
            reason = (data or {}).get("reason") or "未知原因"
            raise ImageServiceError("VIDEO_FAILED", f"视频生成失败：{reason[:120]}")
        time.sleep(interval)

    raise ImageServiceError(
        "VIDEO_TIMEOUT", f"视频生成超时（当前状态 {last_status or '未知'}），请稍后查看"
    )
