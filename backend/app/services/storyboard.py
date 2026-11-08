"""分镜脚本：Prompt、解析与校验。

LLM 输出不可信是常态：这里做格式归一 + 取值约束，不靠反复重试烧钱。
"""

import re

from .. import config
from .llm_client import LLMError, chat_json

SCENES = ["远景", "全景", "中景", "近景", "特写"]
CAMERAS = ["固定", "推", "拉", "摇", "移", "跟"]

_SYSTEM = "你是一位资深短剧分镜师，只输出 JSON，不输出任何解释文字。"

_PROMPT = """请把下面的剧本拆成可拍摄的分镜脚本。

# 剧本
{script}

# 角色名清单（若为空则你自行命名，但同一人必须始终用同一个名字）
{characters}

# 输出格式（严格 JSON，不要 Markdown 代码块）
{{"shots":[{{"no":1,"scene":"近景","camera":"缓慢推近","description":"画面里发生什么，含人物动作与场景","dialogue":"该镜头台词，没有就留空","duration":5,"characters":["角色名"]}}]}}

# 约束
- 镜头数 8~12 个；剧本很短时也不要少于 6 个。
- scene 只能取：远景/全景/中景/近景/特写
- camera 只能取：固定/推/拉/摇/移/跟
- duration 为 2~10 的整数（秒）
- characters 只能取自上面的角色名清单；清单为空时可以用"人物A""人物B"
- description 必须是能直接拍出来的画面，不要写"交代背景"这类抽象话
"""


def _clamp_int(value, low: int, high: int, default: int) -> int:
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, v))


def _normalize_scene(value: str) -> str:
    text = str(value or "").strip()
    for s in SCENES:
        if s in text:
            return s
    return "中景"


def _normalize_camera(value: str) -> str:
    text = str(value or "").strip()
    for c in CAMERAS:
        if c in text:
            return c
    return "固定"


def normalize_shots(raw: dict, max_shots: int | None = None) -> list[dict]:
    """把模型输出规整成可入库的镜头列表。不抛异常，尽量修。"""
    max_shots = max_shots or config.MAX_SHOTS
    items = raw.get("shots") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise LLMError("LLM_BAD_STRUCTURE", "分镜结果结构不正确（缺少 shots 数组）")

    shots: list[dict] = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        desc = str(item.get("description") or "").strip()
        if not desc:
            continue
        chars = item.get("characters") or []
        if isinstance(chars, str):
            chars = [c for c in re.split(r"[,，、/\s]+", chars) if c]
        chars = [str(c).strip() for c in chars if str(c).strip()][:8]
        shots.append(
            {
                "index": len(shots) + 1,
                "scene": _normalize_scene(item.get("scene")),
                "camera": _normalize_camera(item.get("camera")),
                "description": desc[:2000],
                "dialogue": str(item.get("dialogue") or "").strip()[:2000],
                "duration": _clamp_int(item.get("duration"), 2, 10, 5),
                "character_names": chars,
            }
        )
        if len(shots) >= max_shots:
            break

    if not shots:
        raise LLMError("LLM_EMPTY_STORYBOARD", "模型没有给出可用的分镜，请把剧本写得更具体一些")
    return shots


def generate_storyboard(script_text: str, character_names: list[str]) -> list[dict]:
    """调用 LLM 生成并规整分镜。失败抛 LLMError。"""
    names = "、".join(character_names) if character_names else "（空）"
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _PROMPT.format(script=script_text[:8000], characters=names)},
    ]
    raw = chat_json(messages, temperature=0.4, max_tokens=3000)
    return normalize_shots(raw)
