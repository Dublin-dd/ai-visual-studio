"""媒体处理：ffmpeg 路径、时长探测、ASS 字幕生成、片段拼接与成片合成。

设计原则：
- 每段先“对齐”成统一规格（720x1280 / 30fps / AAC 44.1k 立体声），再用 concat 拼接，
  避免不同来源片段的编码参数不一致导致拼接失败。
- 旁白比画面长时，用 tpad 复制最后一帧延长画面；画面比旁白长时，用 apad 补静音。
- 成片阶段统一烧字幕、混 BGM，只做一次最终编码。
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from .. import config

OUT_W = 720
OUT_H = 1280
FPS = 30
SAMPLE_RATE = 44100


class MediaError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def ffmpeg_exe() -> str:
    """优先用配置指定的 ffmpeg，其次用 imageio-ffmpeg 自带的静态构建。"""
    if config.FFMPEG_BIN:
        return config.FFMPEG_BIN
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001  回退到系统 PATH
        return "ffmpeg"


def _run(args: list[str], timeout: float = 600) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        raise MediaError("FFMPEG_MISSING", "服务器未安装 ffmpeg，无法合成视频")
    except subprocess.TimeoutExpired:
        raise MediaError("FFMPEG_TIMEOUT", "视频合成超时，请稍后重试")


def duration_of(path: Path) -> float:
    """用 ffmpeg 读取媒体时长（秒）。解析失败返回 0。"""
    proc = _run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], timeout=60)
    text = (proc.stderr or "") + (proc.stdout or "")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not m:
        return 0.0
    h, mnt, sec = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mnt * 60 + sec


def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _wrap_cjk(text: str, width: int = 14) -> list[str]:
    """中文按字数折行；标点不落在行首。"""
    text = text.strip()
    if not text:
        return []
    no_lead = "，。！？；：、,.!?;:）】》”’"
    lines: list[str] = []
    cur = ""
    for ch in text:
        if ch in no_lead:
            if cur:
                cur += ch
            elif lines:
                # 上一行已经排满并落行了，标点要跟回上一行，不能做行首
                lines[-1] += ch
                continue
            else:
                cur += ch
            if len(cur) >= width:
                lines.append(cur)
                cur = ""
            continue
        cur += ch
        if len(cur) >= width:
            lines.append(cur)
            cur = ""
    if cur:
        lines.append(cur)
    return lines


def _escape_ass(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def subtitle_cues(text: str, start: float, end: float) -> list[dict]:
    """短语分屏，按字数比例估算时间；不是逐字语音对齐。"""
    import re
    import math
    if not math.isfinite(start) or not math.isfinite(end) or end <= start:
        return []
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    phrases = re.findall(r"[^，。！？；、,.!?;]+[，。！？；、,.!?;]*", text)
    chunks = []
    for phrase in phrases:
        chunks.extend(_wrap_cjk(phrase.strip(), width=14))
    chunks = [chunk for chunk in chunks if chunk]
    if not chunks:
        return []
    weights = [max(1, len(chunk)) for chunk in chunks]
    total = sum(weights)
    cursor = start
    elapsed = 0
    cues = []
    for index, (chunk, weight) in enumerate(zip(chunks, weights)):
        elapsed += weight
        stop = end if index == len(chunks) - 1 else start + (end - start) * elapsed / total
        # ASS 精度为百分之一秒，过滤舍入后无时长的极短事件。
        if round(stop, 2) > round(cursor, 2):
            cues.append({"text": chunk, "start": cursor, "end": stop})
        elif cues:
            cues[-1]["text"] += chunk
            cues[-1]["end"] = stop
        cursor = stop
    return cues


def build_ass(segments: list[dict], font: str | None = None, font_size: int | None = None) -> str:
    """segments: [{text, start, end}] → ASS 字幕文本。"""
    font = font or config.SUBTITLE_FONT
    import sys
    if sys.platform == "darwin" and font == "PingFang SC" and Path("/System/Library/Fonts/Hiragino Sans GB.ttc").exists():
        # 静态 ffmpeg 可能不识别按需下载的苹方；使用本机可读中文字库。
        font = "Hiragino Sans GB"
    font_size = font_size or config.SUBTITLE_FONT_SIZE
    head = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {OUT_W}",
        f"PlayResY: {OUT_H}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,{font},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        "1,0,0,0,100,100,0,0,1,3,1,2,40,40,90,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    events: list[str] = []
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        for cue in subtitle_cues(text, float(seg['start']), float(seg['end'])):
            body = "\\N".join(_escape_ass(line) for line in _wrap_cjk(cue["text"]))
            events.append(
                f"Dialogue: 0,{_ass_time(cue['start'])},{_ass_time(cue['end'])},Default,,0,0,0,,{body}"
            )
    return "\n".join(head + events) + "\n"


def mux_segment(
    video_path: Path,
    audio_path: Path | None,
    out_path: Path,
    workspace: Path,
) -> float:
    """把一段视频与旁白对齐成统一规格，返回该段最终时长。

    以旁白为主：段长 = 旁白时长 + 小尾巴；旁白短则剪短画面（避免句间长空白），
    旁白长则复制最后一帧延长画面。没有旁白时保持原画面长度。
    """
    TAIL = 0.25      # 句尾留一点呼吸感
    MIN_SEG = 2.0    # 单段最短，避免一闪而过

    vdur = duration_of(video_path)
    if vdur <= 0:
        raise MediaError("BAD_VIDEO", "片段无法读取，请重试生成")
    adur = duration_of(audio_path) if audio_path else 0.0

    if adur > 0:
        total = max(adur + TAIL, MIN_SEG)
    else:
        total = vdur

    vf = f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
    vf += f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:color=white,fps={FPS}"
    if total > vdur + 0.02:
        vf += f",tpad=stop_mode=clone:stop_duration={total - vdur:.3f}"

    cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(video_path)]
    if audio_path is not None:
        cmd += ["-i", str(audio_path)]

    if audio_path is not None:
        af = f"aresample={SAMPLE_RATE},apad,atrim=0:{total:.3f},asetpts=N/SR/TB"
        cmd += [
            "-filter_complex",
            f"[0:v]{vf}[v];[{1}:a]{af}[a]",
            "-map", "[v]", "-map", "[a]",
        ]
    else:
        cmd += [
            "-filter_complex",
            f"[0:v]{vf}[v];anullsrc=channel_layout=stereo:sample_rate={SAMPLE_RATE},"
            f"atrim=0:{total:.3f}[a]",
            "-map", "[v]", "-map", "[a]",
        ]

    cmd += [
        "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", str(SAMPLE_RATE), "-ac", "2",
        "-movflags", "+faststart",
        str(out_path),
    ]
    proc = _run(cmd, timeout=900)
    if proc.returncode != 0 or not out_path.exists():
        raise MediaError("SEGMENT_FAILED", f"片段处理失败：{(proc.stderr or '')[-300:]}")
    return total


def concat_segments(segments: list[Path], out_path: Path, workspace: Path) -> None:
    """按顺序拼接已统一规格的片段。"""
    list_file = workspace / "concat.txt"
    list_file.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in segments), encoding="utf-8"
    )
    cmd = [
        ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-c", "copy", "-movflags", "+faststart", str(out_path),
    ]
    proc = _run(cmd, timeout=900)
    if proc.returncode != 0 or not out_path.exists():
        raise MediaError("CONCAT_FAILED", f"片段拼接失败：{(proc.stderr or '')[-300:]}")


def finalize(
    base_path: Path,
    out_path: Path,
    workspace: Path,
    ass_path: Path | None = None,
    bgm_path: Path | None = None,
    bgm_volume: float | None = None,
) -> bool:
    """最终编码：烧字幕 + 混入 BGM。字幕烧制失败时退回无字幕输出。

    返回是否真的烧上了字幕（降级时为 False，不得谎报）。
    """
    volume = config.BGM_DEFAULT_VOLUME if bgm_volume is None else bgm_volume

    def _run_final(with_subs: bool) -> subprocess.CompletedProcess:
        cmd = [ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(base_path)]
        if bgm_path is not None:
            cmd += ["-stream_loop", "-1", "-i", str(bgm_path)]
        vf = []
        if with_subs and ass_path is not None:
            # 路径中的特殊字符需要转义后交给 filter
            safe = ass_path.as_posix().replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
            import os
            import sys
            font_dir = os.getenv("SUBTITLE_FONTS_DIR", "")
            if not font_dir and sys.platform == "darwin":
                font_dir = "/System/Library/Fonts"
            font_option = ""
            if font_dir and Path(font_dir).is_dir():
                escaped = Path(font_dir).as_posix().replace(":", "\\:").replace("'", "\\'")
                font_option = f":fontsdir='{escaped}'"
            vf.append(f"subtitles='{safe}'{font_option}")
        af = []
        if bgm_path is not None:
            af.append(f"[1:a]volume={volume}[bg]")
            af.append("[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[aout]")
        args = list(cmd)
        filt = []
        if vf:
            filt.append("[0:v]" + ",".join(vf) + "[vout]")
        if af:
            filt.extend(af)
        if filt:
            args += ["-filter_complex", ";".join(filt)]
            if vf:
                args += ["-map", "[vout]"]
            else:
                args += ["-map", "0:v"]
            if af:
                args += ["-map", "[aout]"]
            else:
                args += ["-map", "0:a"]
        args += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", str(SAMPLE_RATE), "-ac", "2",
            "-shortest", "-movflags", "+faststart", str(out_path),
        ]
        return _run(args, timeout=1200)

    proc = _run_final(with_subs=True)
    if proc.returncode == 0 and out_path.exists():
        return True

    # 字幕烧制失败（常见原因：容器内缺中文字体）→ 退回无字幕，保证用户拿到成片
    proc2 = _run_final(with_subs=False)
    if proc2.returncode != 0 or not out_path.exists():
        raise MediaError("FINALIZE_FAILED", f"成片合成失败：{(proc2.stderr or '')[-300:]}")
    return False
