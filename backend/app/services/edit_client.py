"""商品图编辑客户端（Qwen-Image-Edit，OpenAI 兼容 /images/generations）。

与文生图的区别：需要把参考图以 base64 data URL 传入。
"""

import base64
import time

import httpx

from .. import config
from .image_client import ImageServiceError, _ensure_key


def _data_url(image_bytes: bytes, mime: str = "image/png") -> str:
    return f"data:{mime};base64," + base64.b64encode(image_bytes).decode()


def _request_once(
    *, prompt: str, image_bytes: bytes, seed: int | None, image_size: str | None
) -> tuple[bytes, int | None]:
    url = f"{config.IMAGE_API_BASE_URL}/images/generations"
    payload: dict = {
        "model": config.EDIT_MODEL,
        "prompt": prompt,
        "image": _data_url(image_bytes),
    }
    if seed is not None:
        payload["seed"] = seed
    if image_size:
        payload["image_size"] = image_size

    headers = {
        "Authorization": f"Bearer {config.IMAGE_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.post(
            url,
            json=payload,
            headers=headers,
            timeout=config.EDIT_TIMEOUT_SECONDS,
            trust_env=False,  # 直连国内服务，商品图不出境
        )
    except httpx.TimeoutException:
        raise ImageServiceError("EDIT_TIMEOUT", "图片编辑超时，请稍后重试")
    except httpx.HTTPError:
        raise ImageServiceError("EDIT_NETWORK", "图片编辑服务连接失败，请稍后重试")

    if resp.status_code == 401:
        raise ImageServiceError("IMAGE_KEY_INVALID", "图像服务鉴权失败，请检查 API Key")
    if resp.status_code == 429:
        raise ImageServiceError("IMAGE_RATE_LIMIT", "图像服务限流，请稍后重试")
    if resp.status_code >= 500:
        raise ImageServiceError("EDIT_UPSTREAM", "图片编辑服务暂时不可用，请稍后重试")
    if resp.status_code != 200:
        raise ImageServiceError("EDIT_BAD_REQUEST", "图片编辑请求被拒绝，请检查图片与描述")

    try:
        body = resp.json()
        item = body["images"][0]
        used_seed = body.get("seed")
    except (KeyError, IndexError, ValueError):
        raise ImageServiceError("EDIT_BAD_RESPONSE", "图片编辑服务返回结构异常")

    if item.get("url"):
        try:
            img = httpx.get(item["url"], timeout=config.EDIT_TIMEOUT_SECONDS, trust_env=False)
            img.raise_for_status()
            return img.content, used_seed
        except httpx.HTTPError:
            raise ImageServiceError("EDIT_DOWNLOAD_FAILED", "编辑结果下载失败，请重试")
    if item.get("b64_json"):
        try:
            return base64.b64decode(item["b64_json"]), used_seed
        except (ValueError, TypeError):
            raise ImageServiceError("EDIT_BAD_RESPONSE", "图片编辑服务返回结构异常")
    raise ImageServiceError("EDIT_BAD_RESPONSE", "图片编辑服务未返回图片")


def edit_image(
    *,
    prompt: str,
    image_bytes: bytes,
    seed: int | None = None,
    image_size: str | None = None,
) -> tuple[bytes, int | None]:
    """对参考图执行编辑，返回 (图片字节, 实际 seed)。

    重试策略：失败重试 1 次（编辑耗时较长，不做多档降级）。
    """
    _ensure_key()
    last: ImageServiceError | None = None
    for attempt in range(2):
        try:
            return _request_once(
                prompt=prompt, image_bytes=image_bytes, seed=seed, image_size=image_size
            )
        except ImageServiceError as e:
            last = e
            if e.code in ("IMAGE_KEY_MISSING", "IMAGE_KEY_INVALID", "EDIT_BAD_REQUEST"):
                raise
            if attempt == 0:
                time.sleep(2.0)
                continue
    assert last is not None
    raise last


def cutout_prompt() -> str:
    return (
        "把图片中的商品完整抠出，背景替换为纯白色（#FFFFFF），"
        "商品本身保持完全不变，不改变形状、文字、颜色与光影"
    )


def scene_prompt(scene: str) -> str:
    return (
        "保持图片中的商品完全不变（形状、标签文字、颜色、比例），"
        f"把背景替换为：{scene}"
    )


def sku_prompt(color: str) -> str:
    return (
        "保持商品形状、标签文字与构图完全不变，"
        f"只把商品主色改为{color}，纯白色背景"
    )
