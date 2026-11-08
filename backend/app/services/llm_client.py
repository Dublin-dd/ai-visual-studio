"""文本大模型客户端（SiliconFlow 的 chat/completions，与图像共用同一把 Key）。

用于短剧分镜脚本生成。JSON 模式下返回结构由调用方校验。
"""

import json

import httpx

from .. import config


class LLMError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _ensure_key() -> None:
    if not config.IMAGE_API_KEY.strip():
        raise LLMError("LLM_KEY_MISSING", "未配置模型 API Key，请在 backend/.env 填写 IMAGE_API_KEY")


def chat_json(messages: list[dict], temperature: float = 0.4, max_tokens: int = 3000) -> dict:
    """调用聊天模型并返回解析后的 JSON 对象。"""
    _ensure_key()
    url = f"{config.IMAGE_API_BASE_URL}/chat/completions"
    payload = {
        "model": config.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {config.IMAGE_API_KEY}",
        "Content-Type": "application/json",
    }

    last: LLMError | None = None
    for attempt in range(2):
        try:
            resp = httpx.post(
                url,
                json=payload,
                headers=headers,
                timeout=config.LLM_TIMEOUT_SECONDS,
                trust_env=False,  # 直连国内服务，剧本不出境
            )
        except httpx.TimeoutException:
            last = LLMError("LLM_TIMEOUT", "分镜生成超时，请稍后重试")
            continue
        except httpx.HTTPError:
            last = LLMError("LLM_NETWORK", "分镜服务连接失败，请稍后重试")
            continue

        if resp.status_code == 401:
            raise LLMError("LLM_KEY_INVALID", "模型服务鉴权失败，请检查 API Key")
        if resp.status_code == 429:
            last = LLMError("LLM_RATE_LIMIT", "模型服务限流，请稍后重试")
            continue
        if resp.status_code >= 500:
            last = LLMError("LLM_UPSTREAM", "模型服务暂时不可用，请稍后重试")
            continue
        if resp.status_code != 200:
            raise LLMError("LLM_BAD_REQUEST", "分镜请求被拒绝，请检查剧本长度")

        try:
            content = resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError):
            raise LLMError("LLM_BAD_RESPONSE", "模型返回结构异常")
        try:
            return parse_json_object(content)
        except ValueError:
            last = LLMError("LLM_BAD_JSON", "模型没有返回合法 JSON，已重试仍失败")
            continue

    assert last is not None
    raise last


def parse_json_object(text: str) -> dict:
    """宽容解析：去掉 ```json 围栏、截取第一个完整 JSON 对象。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("空内容")
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("无 JSON 对象")
    return json.loads(text[start : end + 1])
