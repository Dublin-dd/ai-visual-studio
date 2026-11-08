"""图像生成服务客户端（SiliconFlow，OpenAI 兼容 /images/generations）。

约束：
- 无 Key 时直接抛错，不用假图冒充。
- 失败按「有限重试 + 档位降档」处理。
"""

import base64
import time

import httpx

from .. import config


class ImageServiceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_TIER_MODEL = {
    "draft": lambda: config.IMAGE_MODEL_DRAFT or config.IMAGE_MODEL,
    "standard": lambda: config.IMAGE_MODEL,
    "hq": lambda: config.IMAGE_MODEL_HQ or config.IMAGE_MODEL,
}


def model_for_tier(tier: str) -> str:
    return _TIER_MODEL.get(tier, _TIER_MODEL["standard"])()


def _ensure_key() -> None:
    if not config.IMAGE_API_KEY.strip():
        raise ImageServiceError(
            "IMAGE_KEY_MISSING",
            "未配置图像生成 API Key，请在 backend/.env 填写 IMAGE_API_KEY",
        )


def _request_once(*, prompt: str, width: int, height: int, model: str) -> bytes:
    url = f"{config.IMAGE_API_BASE_URL}/images/generations"
    payload = {
        "model": model,
        "prompt": prompt,
        "image_size": f"{width}x{height}",
        "batch_size": 1,
        "num_inference_steps": 8 if "Turbo" in model or "schnell" in model else 28,
    }
    headers = {
        "Authorization": f"Bearer {config.IMAGE_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.post(
            url,
            json=payload,
            headers=headers,
            timeout=config.IMAGE_TIMEOUT_SECONDS,
            trust_env=False,  # 直连国内服务，保证商品图不出境
        )
    except httpx.TimeoutException:
        raise ImageServiceError("IMAGE_TIMEOUT", "图像生成超时，请稍后重试")
    except httpx.HTTPError:
        raise ImageServiceError("IMAGE_NETWORK", "图像生成服务连接失败，请稍后重试")

    if resp.status_code == 401:
        raise ImageServiceError("IMAGE_KEY_INVALID", "图像服务鉴权失败，请检查 API Key")
    if resp.status_code == 429:
        raise ImageServiceError("IMAGE_RATE_LIMIT", "图像服务限流，请稍后重试")
    if resp.status_code >= 500:
        raise ImageServiceError("IMAGE_UPSTREAM", "图像服务暂时不可用，请稍后重试")
    if resp.status_code != 200:
        raise ImageServiceError("IMAGE_BAD_REQUEST", "图像生成请求被拒绝，请检查提示词与尺寸")

    try:
        item = resp.json()["images"][0]
    except (KeyError, IndexError, ValueError):
        raise ImageServiceError("IMAGE_BAD_RESPONSE", "图像服务返回结构异常")

    if item.get("url"):
        try:
            img = httpx.get(item["url"], timeout=config.IMAGE_TIMEOUT_SECONDS, trust_env=False)
            img.raise_for_status()
            return img.content
        except httpx.HTTPError:
            raise ImageServiceError("IMAGE_DOWNLOAD_FAILED", "生成结果下载失败，请重试")
    if item.get("b64_json"):
        try:
            return base64.b64decode(item["b64_json"])
        except (ValueError, TypeError):
            raise ImageServiceError("IMAGE_BAD_RESPONSE", "图像服务返回结构异常")
    raise ImageServiceError("IMAGE_BAD_RESPONSE", "图像服务未返回图片")


def generate_image(
    *, prompt: str, width: int, height: int, tier: str = "standard"
) -> tuple[bytes, str]:
    """生成一张图，返回 (图片字节, 实际使用的模型名)。

    重试策略：同档重试 1 次；仍失败则降档一次（hq→standard→draft）。
    """
    _ensure_key()
    order = [tier]
    if tier == "hq":
        order.append("standard")
    if tier in ("hq", "standard"):
        order.append("draft")

    last: ImageServiceError | None = None
    for t in order:
        model = model_for_tier(t)
        for attempt in range(2):
            try:
                return _request_once(prompt=prompt, width=width, height=height, model=model), model
            except ImageServiceError as e:
                last = e
                # 鉴权/参数类错误重试无意义，直接抛出
                if e.code in ("IMAGE_KEY_MISSING", "IMAGE_KEY_INVALID", "IMAGE_BAD_REQUEST"):
                    raise
                if attempt == 0:
                    time.sleep(1.2)
                    continue
                break
    assert last is not None
    raise last
