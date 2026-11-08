"""带货脚本生成：输入商品名 + 卖家卖点，LLM 扩写成 30 秒带货脚本 + 分镜。

与 storyboard.py（短剧分镜）同构，但字段与 prompt 面向「商品展示」而非「人物剧情」。
输出经归一化后才入库，不靠反复重试烧钱。
"""

import re

from .llm_client import LLMError, chat_json

SCENES = ["远景", "全景", "中景", "近景", "特写"]
# 镜头运动：只允许不会暴露“未见过角度”的运动。
# 图生视频模型只见过首帧一个角度，旋转/摇镜会逼它“猜”侧背面而失真（PoC 实测）。
CAMERAS = ["固定", "缓慢推近", "缓慢拉远", "轻微平移"]

# 视频风格 → 文案调性指令（决定整个脚本怎么说话，不只是 CTA）
STYLES = {
    "叫卖式": "叫卖式：文案热情、有感染力、口语化，强钩子强催单，营造紧迫感",
    "种草式": "种草式：文案真实、亲切，像朋友推荐，讲使用体验和感受，不夸张",
    "品牌式": "品牌式：文案克制、有格调，讲生活方式和质感，不催单，不要提价格、购买、链接",
}

# 发布平台 → 结尾引导（CTA）
PLATFORM_CTA = {
    "抖音": "结尾引导「点击小黄车」或「点开评论区」",
    "淘宝": "结尾引导「进店看看」或「加购」",
    "拼多多": "结尾引导「领券下单」",
    "其他": "结尾做中性收尾，不挂车，不提购买渠道",
}

_SYSTEM = "你是一位资深电商带货短视频编导，只输出 JSON，不输出任何解释文字。"

_PROMPT = """请为一个商品写一条约 30 秒的带货短视频脚本，并拆成分镜。

# 商品信息
商品名：{product_name}
卖家提供的卖点：{selling_points}

# 文案风格（必须严格遵守）
{style_instruction}

# 结尾引导
{cta_instruction}

# 结构要求
- 前 3 秒用钩子抓住注意力 → 逐个讲卖点 → 结尾按上面的引导收尾
- 口播文案总时长约 30 秒

# 分镜画面铁律（最重要）
视频是“拿这张商品图当首帧”生成的，模型只能延续首帧里已有的东西。因此：
- 每个镜头必须是「商品本身」的展示：商品始终在画面里
- **相邻镜头必须有明显差异**：至少在两件事上不同——
  景别（特写/近景/中景/全景）、光位（顺光/侧光/逆光/柔光）、背景明暗与氛围、
  商品在画面中的位置与占比、镜头运动（固定/缓慢推近/缓慢拉远/轻微平移）
- 构图要有节奏：不要每个镜头都是“商品居中直立”的同一种拍法
- 禁止：出现首帧里没有的人、手、道具、其他商品；禁止要求商品被手拿、被使用、被倒入、被涂抹、被拆开；禁止转动商品展示背面/侧面
- 禁止在画面描述里要求出现任何叠加文字、字样、字幕、价格、标语、箭头贴纸——文字统一由后期字幕完成
- 卖点靠口播表达，不靠凭空造新画面

# 输出格式（严格 JSON，不要 Markdown 代码块）
{{"product_name":"商品名","audience":"目标人群","hook":"开头钩子一句话","selling_points":["卖点1","卖点2"],"script_text":"完整口播文案","shots":[{{"no":1,"scene":"近景","camera":"缓慢推近","description":"画面：商品如何展示","voiceover":"该镜头口播文案","duration":5}}]}}

# 约束
- 镜头数 5~6 个，总时长 25~35 秒
- scene 只能取：远景/全景/中景/近景/特写
- camera 只能取：固定/缓慢推近/缓慢拉远/轻微平移（禁止旋转、环绕、摇镜、跟拍）
- duration 为 2~10 的整数（秒）
- description 必须是能直接拍出来的商品展示画面，不要写"交代背景"这类抽象话
- description 里禁止出现“旋转、环绕、翻转、背面、侧面、转身”这类要求展示未见过角度的描述
- description 里禁止出现手、人物、其他道具、使用动作（涂抹/倒出/喷洒等），只能描述商品本身的呈现与镜头运动
- voiceover 是该镜头对应的口播文案，不能为空
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
    # 先匹配更长的词，避免“缓慢推近”被“推”抢先命中
    for c in sorted(CAMERAS, key=len, reverse=True):
        if c in text:
            return c
    # 模型擅用旋转/摇镜时统一降级为固定机位，避免商品失真
    return "固定"


def _sanitize_description(text: str) -> str:
    """清理画面描述里的两类危险要求。

    1. 转体/展示背面：图生视频只见过首帧一个角度，写到就会失真 → 追加禁止说明。
       2. 叠加文字/字样/字幕：模型不会渲染文字，会把字编成占位图形 → 直接删除该分句。
    文字统一交给后期字幕完成。
    """
    out = text.strip()

    bad_text = ["字样", "文字", "字幕", "标语", "价格标签", "弹幕", "贴纸", "关键词浮"]
    if any(w in out for w in bad_text):
        parts = re.split(r"([，,。；;])", out)
        kept: list[str] = []
        i = 0
        while i < len(parts):
            seg = parts[i]
            sep = parts[i + 1] if i + 1 < len(parts) else ""
            if not any(w in seg for w in bad_text):
                kept.append(seg + sep)
            i += 2
        cleaned = "".join(kept).strip(" ，,。；;")
        if len(cleaned) >= 8:  # 删完后还成句才用，否则保留原文
            out = cleaned

    bad_angle = ["旋转", "环绕", "翻转", "翻面", "背面", "侧面", "转身", "绕一圈"]
    if any(w in out for w in bad_angle):
        out += "（商品正面朝向镜头，不旋转、不展示背面或侧面）"

    return out


def normalize_sale_script(raw: dict, max_shots: int | None = None) -> dict:
    """把模型输出规整成可入库的结构。不抛异常，尽量修。"""
    max_shots = max_shots or 8

    selling_points = raw.get("selling_points") or []
    if isinstance(selling_points, str):
        selling_points = [p for p in re.split(r"[;；\n]+", selling_points) if p.strip()]
    selling_points = [str(p).strip() for p in selling_points if str(p).strip()][:10]

    items = raw.get("shots") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise LLMError("LLM_BAD_STRUCTURE", "脚本分镜结构不正确（缺少 shots 数组）")

    shots: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        desc = str(item.get("description") or "").strip()
        voice = str(item.get("voiceover") or "").strip()
        if not desc or not voice:
            continue
        shots.append(
            {
                "index": len(shots) + 1,
                "scene": _normalize_scene(item.get("scene")),
                "camera": _normalize_camera(item.get("camera")),
                "description": _sanitize_description(desc)[:2000],
                "voiceover": voice[:2000],
                "duration": _clamp_int(item.get("duration"), 2, 10, 5),
            }
        )
        if len(shots) >= max_shots:
            break

    if not shots:
        raise LLMError("LLM_EMPTY_STORYBOARD", "模型没有给出可用分镜，请把卖点写得更具体一些")

    # 对重复镜头做确定性修正，不能只依赖模型遵守提示词。
    rhythm = [("全景", "固定"), ("特写", "固定"), ("中景", "轻微平移"),
              ("近景", "缓慢拉远"), ("全景", "固定"), ("特写", "固定")]
    pushes = 0
    for index, shot in enumerate(shots):
        previous = shots[index - 1] if index else None
        if previous and shot["scene"] == previous["scene"]:
            shot["scene"] = rhythm[index % len(rhythm)][0]
            if shot["scene"] == previous["scene"]:
                shot["scene"] = "特写" if previous["scene"] != "特写" else "全景"
        if shot["camera"] == "缓慢推近":
            pushes += 1
            if pushes > 1:
                shot["camera"] = rhythm[index % len(rhythm)][1]
        if previous and shot["camera"] == previous["camera"] and shot["camera"] != "固定":
            shot["camera"] = "固定"

    script_text = str(raw.get("script_text") or "").strip()
    if not script_text:
        script_text = "".join(s["voiceover"] for s in shots)

    return {
        "product_name": str(raw.get("product_name") or "").strip()[:255],
        "audience": str(raw.get("audience") or "").strip()[:255],
        "hook": str(raw.get("hook") or "").strip()[:500],
        "selling_points": selling_points,
        "script_text": script_text[:8000],
        "shots": shots,
    }


_PARSE_SYSTEM = "你是带货视频需求的解析助手，从用户的话里提取结构化信息，只输出 JSON。"

_PARSE_PROMPT = """从用户的话里提取四样信息：
- product_name：商品名（是什么商品）
- selling_points：卖点列表（商品有什么优点，用户提到的）
- style：视频风格，只能是 叫卖式/种草式/品牌式 之一；没提默认 种草式
- platform：发布平台，只能是 抖音/淘宝/拼多多/其他 之一；「暂不发」「不挂车」「不发布」等表示不挂车，归为 其他；没提默认 其他

用户的话：{message}

只输出 JSON，不要任何其他文字：
{{"product_name":"...","selling_points":["..."],"style":"...","platform":"..."}}"""


def parse_product_request_llm(message: str) -> dict:
    """LLM 兜底解析：正则看不懂的自然表达（如「品牌式 暂不发 小米手机 续航三天」）。"""
    messages = [
        {"role": "system", "content": _PARSE_SYSTEM},
        {"role": "user", "content": _PARSE_PROMPT.format(message=message[:1000])},
    ]
    raw = chat_json(messages, temperature=0.1, max_tokens=500)

    name = str(raw.get("product_name") or "").strip()
    points = raw.get("selling_points") or []
    if isinstance(points, str):
        points = [p for p in re.split(r"[、,，;；\s]+", points) if p]
    points = [str(p).strip() for p in points if str(p).strip()][:10]

    style = str(raw.get("style") or "种草式").strip()
    if style not in STYLES:
        style = "种草式"
    platform = str(raw.get("platform") or "其他").strip()
    if platform not in PLATFORM_CTA:
        platform = "其他"

    return {"product_name": name, "selling_points": points, "style": style, "platform": platform}


def generate_sale_script(
    product_name: str,
    selling_points: list[str],
    style: str = "种草式",
    platform: str = "其他",
) -> dict:
    """调用 LLM 生成并规整带货脚本。失败抛 LLMError。

    style 决定文案调性（叫卖式/种草式/品牌式），platform 决定结尾 CTA。
    """
    points = "、".join(selling_points) if selling_points else "（卖家未提供，请根据商品名合理推断）"
    style_instruction = STYLES.get(style, STYLES["种草式"])
    cta_instruction = PLATFORM_CTA.get(platform, PLATFORM_CTA["其他"])
    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": _PROMPT.format(
                product_name=product_name[:200],
                selling_points=points,
                style_instruction=style_instruction,
                cta_instruction=cta_instruction,
            ),
        },
    ]
    raw = chat_json(messages, temperature=0.5, max_tokens=4000)
    return normalize_sale_script(raw)
