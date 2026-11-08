"""兼容层：旧的 `from . import tts_client` 仍然可用。

实际实现已迁到 `app/services/tts/` 包中，按 TTS_PROVIDER 分发。
"""

from .tts import PROVIDERS, TTSError, active_provider, synthesize

__all__ = ["TTSError", "active_provider", "synthesize", "PROVIDERS"]
