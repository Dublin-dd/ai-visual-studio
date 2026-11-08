"""镜头运动与画面描述的保真约束测试。"""

from app.services.sale_script import _normalize_camera, _sanitize_description


def test_camera_prefers_longer_match():
    assert _normalize_camera("缓慢推近") == "缓慢推近"
    assert _normalize_camera("镜头缓慢推近，最后停下") == "缓慢推近"
    assert _normalize_camera("固定机位") == "固定"
    assert _normalize_camera("轻微平移") == "轻微平移"


def test_camera_rotation_downgraded_to_fixed():
    """旋转/摇镜会暴露未见过角度，统一降级为固定机位。"""
    assert _normalize_camera("环绕旋转") == "固定"
    assert _normalize_camera("摇镜头") == "固定"
    assert _normalize_camera("跟拍") == "固定"
    assert _normalize_camera("") == "固定"


def test_sanitize_description_appends_guard():
    text = "商品在台面上缓慢旋转一周，展示背面"
    out = _sanitize_description(text)
    assert "不旋转" in out
    assert out.startswith(text)


def test_sanitize_description_keeps_safe_text():
    text = "镜头缓慢推近瓶身，突出金色瓶盖反光"
    assert _sanitize_description(text) == text


def test_sanitize_strips_on_screen_text():
    """模型不会渲染文字，要求叠字的分句应被直接删除（文字交给后期字幕）。"""
    out = _sanitize_description(
        "画面：镜头轻微平移，完整展示瓶身，背景出现半透明的“淡纹紧致”字样，随即淡出。"
    )
    assert "字样" not in out
    assert "瓶身" in out


def test_sanitize_allows_existing_label_text():
    """描述商品自身的标签不算叠加文字。"""
    text = "镜头推近至瓶身标签，光线聚焦在瓶盖上"
    assert _sanitize_description(text) == text


def test_repetitive_shots_get_distinct_scenes_and_limited_pushes():
    from app.services.sale_script import normalize_sale_script
    raw = {"shots": [{"scene":"近景", "camera":"缓慢推近", "description":"商品正面展示", "voiceover":"商品展示"} for _ in range(5)]}
    shots = normalize_sale_script(raw)["shots"]
    assert all(a["scene"] != b["scene"] for a,b in zip(shots,shots[1:]))
    assert sum(s["camera"] == "缓慢推近" for s in shots) <= 1
    assert len(shots) == 5
    assert all(s["voiceover"] == "商品展示" for s in shots)
