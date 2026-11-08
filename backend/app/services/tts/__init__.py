"""语音合成分发：按 TTS_PROVIDER 选择具体供应商实现。

对外只暴露 `synthesize(text, voice, speed)`，业务代码不关心底层是哪家。
新增供应商：在本目录加一个模块，实现 `synthesize(...) -> bytes`，然后在 _PROVIDERS 注册。

供应商：
- siliconflow：CosyVoice2（便宜，音质一般）
- minimax：speech-02 系列（音质好，推荐做带货口播）
"""

from __future__ import annotations

import os

from .errors import TTSError
from .minimax import synthesize as _minimax
from .siliconflow import synthesize as _siliconflow

_PROVIDERS = {
    "siliconflow": _siliconflow,
    "minimax": _minimax,
}

__all__ = ["TTSError", "active_provider", "synthesize", "PROVIDERS"]

PROVIDERS = tuple(_PROVIDERS)


def active_provider() -> str:
    return (os.getenv("TTS_PROVIDER") or "siliconflow").strip().lower()


def synthesize(text: str, voice: str | None = None, speed: float = 1.0) -> bytes:
    """把一段口播文案合成为音频字节（mp3）。"""
    text = (text or "").strip()
    if not text:
        raise TTSError("TTS_EMPTY_TEXT", "口播文案为空，无法配音")

    provider = active_provider()
    impl = _PROVIDERS.get(provider)
    if impl is None:
        raise TTSError(
            "TTS_PROVIDER_UNKNOWN",
            f"未支持的配音供应商：{provider}（可选：{', '.join(_PROVIDERS)}）",
        )
    return impl(text, voice=voice, speed=speed)
