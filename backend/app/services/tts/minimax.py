"""MiniMax 语音合成（speech-02 系列）。

契约：POST {base}/v1/t2a_v2
  body: {model, text, stream:false, voice_setting:{voice_id,speed,vol,pitch},
         audio_setting:{sample_rate,bitrate,format,channel}}
  返回：{"data": {"audio": "<hex>"}, "base_resp": {"status_code": 0, "status_msg": "success"}}
注意：audio 是十六进制字符串，需要 bytes.fromhex 还原。
"""

from __future__ import annotations

import os

import httpx

from ... import config
from .errors import TTSError


def _api_key() -> str:
    return (os.getenv("MINIMAX_API_KEY") or "").strip()


def _base_url() -> str:
    return (os.getenv("MINIMAX_BASE_URL") or "https://api.minimaxi.com").rstrip("/")


def _group_id() -> str:
    return (os.getenv("MINIMAX_GROUP_ID") or "").strip()


def synthesize(text: str, voice: str | None = None, speed: float = 1.0) -> bytes:
    key = _api_key()
    if not key:
        raise TTSError("TTS_KEY_MISSING", "未配置 MINIMAX_API_KEY，请在 backend/.env 填写")

    model = (os.getenv("MINIMAX_TTS_MODEL") or "speech-02-hd").strip()
    voice_id = (voice or os.getenv("MINIMAX_VOICE_ID") or "female-chengshu").strip()

    payload = {
        "model": model,
        "text": text[:2000],
        "stream": False,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": float(speed),
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }
    url = f"{_base_url()}/v1/t2a_v2"
    gid = _group_id()
    if gid:
        url += f"?GroupId={gid}"

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    last: TTSError | None = None
    for _attempt in range(2):
        try:
            resp = httpx.post(
                url, json=payload, headers=headers,
                timeout=config.TTS_TIMEOUT_SECONDS * 2, trust_env=False,
            )
        except httpx.TimeoutException:
            last = TTSError("TTS_TIMEOUT", "配音超时，请稍后重试")
            continue
        except httpx.HTTPError:
            last = TTSError("TTS_NETWORK", "配音服务连接失败，请稍后重试")
            continue

        if resp.status_code == 401:
            raise TTSError("TTS_KEY_INVALID", "MiniMax 鉴权失败，请检查 API Key")
        if resp.status_code == 429:
            last = TTSError("TTS_RATE_LIMIT", "MiniMax 限流，请稍后重试")
            continue
        if resp.status_code >= 500:
            last = TTSError("TTS_UPSTREAM", "MiniMax 暂时不可用，请稍后重试")
            continue
        if resp.status_code != 200:
            raise TTSError("TTS_BAD_REQUEST", f"MiniMax 配音请求被拒绝（{resp.status_code}）")

        try:
            body = resp.json()
        except ValueError:
            last = TTSError("TTS_BAD_RESPONSE", "MiniMax 返回结构异常")
            continue

        base_resp = body.get("base_resp") or {}
        if base_resp.get("status_code") not in (0, None):
            raise TTSError(
                "TTS_API_ERROR",
                f"MiniMax 配音失败：{base_resp.get('status_msg') or base_resp.get('status_code')}",
            )

        hex_audio = (body.get("data") or {}).get("audio") or ""
        if not hex_audio:
            last = TTSError("TTS_EMPTY_AUDIO", "MiniMax 返回空音频")
            continue
        try:
            return bytes.fromhex(hex_audio)
        except ValueError:
            last = TTSError("TTS_BAD_RESPONSE", "MiniMax 音频数据无法解析")
            continue

    assert last is not None
    raise last
