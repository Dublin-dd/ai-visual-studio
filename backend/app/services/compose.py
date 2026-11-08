"""成片合成：把已生成的镜头片段 + 旁白 + 字幕 + BGM 合成一条竖屏成片。

流程：
1. 每个镜头：视频 + 该镜头口播 TTS → 对齐成统一规格片段
2. 按镜头顺序拼接
3. 生成 ASS 字幕（时间轴按各段实际时长累加）
4. 最终编码：烧字幕 + 混 BGM

任一步失败都抛 MediaError，由任务层转成可读错误，不影响已生成的片段素材。
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from .. import config
from . import media, tts_client


class ComposeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def compose(
    shots: list[dict],
    out_path: Path,
    bgm_path: Path | None = None,
    voice: str | None = None,
) -> dict:
    """shots: [{index, video_path, voiceover}] 按顺序。

    返回 {"duration": float, "subtitles": bool, "segments": int}
    """
    if not shots:
        raise ComposeError("NO_SHOTS", "没有可用于合成的镜头")

    work = config.FINAL_DIR / f".work-{uuid.uuid4().hex}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        segment_files: list[Path] = []
        subtitle_rows: list[dict] = []
        cursor = 0.0

        for item in shots:
            video_path = Path(item["video_path"])
            if not video_path.exists():
                raise ComposeError("VIDEO_MISSING", "有镜头视频文件丢失，请重新生成该镜头")

            audio_path: Path | None = work / f"voice-{item['index']}.mp3"
            voiceover = (item.get("voiceover") or "").strip()
            if voiceover:
                try:
                    audio = tts_client.synthesize(
                        voiceover, voice=voice, speed=config.TTS_SPEED
                    )
                    audio_path.write_bytes(audio)
                except tts_client.TTSError as exc:
                    raise ComposeError(exc.code, exc.message)
            else:
                audio_path = None

            seg_out = work / f"seg-{item['index']:02d}.mp4"
            dur = media.mux_segment(video_path, audio_path, seg_out, work)
            segment_files.append(seg_out)
            # 字幕以实际旁白长度为界，不占用补齐的视频尾帧/静音。
            voice_duration = media.duration_of(audio_path) if audio_path else 0.0
            if voiceover and voice_duration > 0:
                subtitle_rows.append({"text": voiceover, "start": cursor,
                                      "end": cursor + min(dur, voice_duration)})
            cursor += dur

        base = work / "base.mp4"
        media.concat_segments(segment_files, base, work)

        ass_path = work / "subtitle.ass"
        ass_path.write_text(media.build_ass(subtitle_rows), encoding="utf-8")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        burned = media.finalize(base, out_path, work, ass_path=ass_path, bgm_path=bgm_path)

        return {
            "duration": round(media.duration_of(out_path), 2),
            "subtitles": burned,
            "segments": len(segment_files),
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
