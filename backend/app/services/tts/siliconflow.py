"""SiliconFlow TTS（CosyVoice2）：便宜、可用，音质一般。"""

from __future__ import annotations

import httpx

from ... import config
from .errors import TTSError


def _ensure_key() -> None:
    if not config.IMAGE_API_KEY.strip():
        raise TTSError("TTS_KEY_MISSING", "未配置模型 API Key，请在 backend/.env 填写 IMAGE_API_KEY")


def synthesize(text: str, voice: str | None = None, speed: float = 1.0) -> bytes:
    _ensure_key()
    payload = {
        "model": config.TTS_MODEL,
        "input": text[:2000],
        "voice": voice or config.TTS_VOICE,
        "response_format": "mp3",
        "speed": speed,
    }
    headers = {
        "Authorization": f"Bearer {config.IMAGE_API_KEY}",
        "Content-Type": "application/json",
    }

    last: TTSError | None = None
    for _attempt in range(2):
        try:
            resp = httpx.post(
                f"{config.IMAGE_API_BASE_URL}/audio/speech",
                json=payload,
                headers=headers,
                timeout=config.TTS_TIMEOUT_SECONDS,
                trust_env=False,
            )
        except httpx.TimeoutException:
            last = TTSError("TTS_TIMEOUT", "配音超时，请稍后重试")
            continue
        except httpx.HTTPError:
            last = TTSError("TTS_NETWORK", "配音服务连接失败，请稍后重试")
            continue

        if resp.status_code == 401:
            raise TTSError("TTS_KEY_INVALID", "配音服务鉴权失败，请检查 API Key")
        if resp.status_code == 429:
            last = TTSError("TTS_RATE_LIMIT", "配音服务限流，请稍后重试")
            continue
        if resp.status_code >= 500:
            last = TTSError("TTS_UPSTREAM", "配音服务暂时不可用，请稍后重试")
            continue
        if resp.status_code != 200:
            raise TTSError("TTS_BAD_REQUEST", "配音请求被拒绝，请检查文案")
        if not resp.content:
            last = TTSError("TTS_EMPTY_AUDIO", "配音服务返回空音频")
            continue
        return resp.content

    assert last is not None
    raise last
