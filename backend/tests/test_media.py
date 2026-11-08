"""字幕与媒体处理测试：ASS 生成、折行、片段对齐与成片合成。"""

import subprocess
from pathlib import Path

from app.services import media


def _make_video(path: Path, seconds: int = 2, color: str = "red") -> None:
    subprocess.run(
        [
            media.ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=360x640:d={seconds}:r=30",
            "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path),
        ],
        check=True,
    )


def _make_audio(path: Path, seconds: int = 1) -> None:
    subprocess.run(
        [
            media.ffmpeg_exe(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-c:a", "libmp3lame", str(path),
        ],
        check=True,
    )


def test_wrap_cjk_keeps_punctuation_with_text():
    lines = media._wrap_cjk("冬天到了，你需要一个保温杯。保温十二小时，还不漏水。", width=10)
    assert lines
    assert all(len(x) <= 11 for x in lines)
    # 标点不应成为行首
    for line in lines:
        assert not line.startswith(("，", "。", "！", "？"))


def test_build_ass_contains_timeline():
    ass = media.build_ass(
        [
            {"text": "第一句口播", "start": 0, "end": 3.5},
            {"text": "第二句口播", "start": 3.5, "end": 8.25},
        ]
    )
    assert "[Script Info]" in ass
    assert "Dialogue: 0,0:00:00.00,0:00:03.50" in ass
    assert "Dialogue: 0,0:00:03.50,0:00:08.25" in ass
    assert "第一句口播" in ass


def test_build_ass_escapes_braces():
    ass = media.build_ass([{"text": "价格{特惠}", "start": 0, "end": 1}])
    assert "\\{特惠\\}" in ass


def test_build_ass_skips_empty_text():
    ass = media.build_ass([{"text": "  ", "start": 0, "end": 2}])
    assert "Dialogue:" not in ass


def test_duration_of(tmp_path):
    video = tmp_path / "a.mp4"
    _make_video(video, seconds=2)
    assert 1.8 < media.duration_of(video) < 2.3


def test_mux_segment_extends_video_for_longer_voice(tmp_path):
    """旁白比画面长时，画面应被延长到旁白长度。"""
    video = tmp_path / "v.mp4"
    audio = tmp_path / "a.mp3"
    out = tmp_path / "seg.mp4"
    _make_video(video, seconds=2)
    _make_audio(audio, seconds=4)

    total = media.mux_segment(video, audio, out, tmp_path)
    assert total > 3.5
    assert out.exists()
    assert media.duration_of(out) > 3.5


def test_concat_and_finalize(tmp_path):
    v1 = tmp_path / "v1.mp4"
    v2 = tmp_path / "v2.mp4"
    _make_video(v1, seconds=1, color="red")
    _make_video(v2, seconds=1, color="blue")

    s1 = tmp_path / "s1.mp4"
    s2 = tmp_path / "s2.mp4"
    media.mux_segment(v1, None, s1, tmp_path)
    media.mux_segment(v2, None, s2, tmp_path)

    base = tmp_path / "base.mp4"
    media.concat_segments([s1, s2], base, tmp_path)

    ass = tmp_path / "sub.ass"
    ass.write_text(
        media.build_ass([{"text": "测试字幕", "start": 0, "end": 2}]), encoding="utf-8"
    )
    final = tmp_path / "final.mp4"
    burned = media.finalize(base, final, tmp_path, ass_path=ass)

    assert final.exists()
    assert media.duration_of(final) > 1.8
    assert burned is True, "中文字幕应该能正常烧制（测试环境字体完整）"


def test_mux_segment_trims_video_to_voice(tmp_path):
    """旁白比画面短时，应剪短画面，避免句间长空白。"""
    video = tmp_path / "v.mp4"
    audio = tmp_path / "a.mp3"
    out = tmp_path / "seg.mp4"
    _make_video(video, seconds=5)
    _make_audio(audio, seconds=3)

    total = media.mux_segment(video, audio, out, tmp_path)
    assert 3.0 < total < 3.6, total
    assert 3.0 < media.duration_of(out) < 3.7


def test_mux_segment_keeps_min_duration(tmp_path):
    """旁白极短时，段长不低于下限，避免一闪而过。"""
    video = tmp_path / "v.mp4"
    audio = tmp_path / "a.mp3"
    out = tmp_path / "seg.mp4"
    _make_video(video, seconds=5)
    _make_audio(audio, seconds=1)

    total = media.mux_segment(video, audio, out, tmp_path)
    assert total >= 2.0


def test_long_subtitles_are_sequential_and_preserve_text():
    text = "金致焕活精华液，以精纯能量，温和抚平岁月印记，让肌肤重获紧致轮廓。"
    cues = media.subtitle_cues(text, 3.25, 11.75)
    assert len(cues) >= 4
    assert "".join(cue["text"] for cue in cues) == text
    assert cues[0]["start"] == 3.25
    assert cues[-1]["end"] == 11.75
    assert all(len(cue["text"]) <= 15 for cue in cues)
    assert all(left["end"] == right["start"] for left, right in zip(cues, cues[1:]))
    assert all(cue["end"] > cue["start"] for cue in cues)


def test_subtitle_cues_invalid_time():
    assert media.subtitle_cues("测试", 2, 1) == []
    assert media.subtitle_cues("测试", 0, float("nan")) == []


def test_subtitle_punctuation_not_on_own_screen():
    cues = media.subtitle_cues("一二三四五六七八九十一二三四，继续说。", 0, 5)
    assert all(cue["text"][0] not in "，。！？" for cue in cues)


def test_compose_subtitles_stop_at_voice_end(tmp_path, monkeypatch):
    from app.services import compose
    from app import config
    captured = []
    monkeypatch.setattr(config, 'FINAL_DIR', tmp_path)
    monkeypatch.setattr(compose.tts_client, 'synthesize', lambda *a, **k: b'audio')
    monkeypatch.setattr(media, 'mux_segment', lambda *a: 2.25)
    monkeypatch.setattr(media, 'concat_segments', lambda *a: None)
    monkeypatch.setattr(media, 'finalize', lambda *a, **k: True)
    monkeypatch.setattr(media, 'duration_of', lambda p: 2.0)
    original = media.build_ass
    def capture(rows):
        captured.extend(rows)
        return original(rows)
    monkeypatch.setattr(media, 'build_ass', capture)
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'video')
    compose.compose([{'index': 1, 'video_path': source, 'voiceover': '第一句'},
                     {'index': 2, 'video_path': source, 'voiceover': '第二句'}], tmp_path / 'out.mp4')
    assert captured == [{'text': '第一句', 'start': 0.0, 'end': 2.0},
                        {'text': '第二句', 'start': 2.25, 'end': 4.25}]
