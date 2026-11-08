import pytest

from app.services import image_client


def test_model_for_tier():
    assert "Turbo" in image_client.model_for_tier("draft")
    assert "Turbo" in image_client.model_for_tier("standard")
    assert "Qwen" in image_client.model_for_tier("hq")


def test_generate_without_key_raises(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "IMAGE_API_KEY", "")
    with pytest.raises(image_client.ImageServiceError) as exc:
        image_client.generate_image(prompt="a cat", width=512, height=512)
    assert exc.value.code == "IMAGE_KEY_MISSING"


def test_generate_retries_then_degrades(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "IMAGE_API_KEY", "test-key")
    calls: list[str] = []

    def fake_once(*, prompt, width, height, model):
        calls.append(model)
        if len(calls) < 5:
            raise image_client.ImageServiceError("IMAGE_UPSTREAM", "上游错误")
        return b"img"

    monkeypatch.setattr(image_client, "_request_once", fake_once)
    monkeypatch.setattr(image_client.time, "sleep", lambda *_: None)

    data, model = image_client.generate_image(prompt="a", width=512, height=512, tier="hq")
    assert data == b"img"
    # hq 两次失败 → standard 两次失败 → draft 成功
    assert len(calls) == 5
    assert model == calls[-1]


def test_generate_auth_error_no_retry(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "IMAGE_API_KEY", "bad-key")
    calls: list[str] = []

    def fake_once(*, prompt, width, height, model):
        calls.append(model)
        raise image_client.ImageServiceError("IMAGE_KEY_INVALID", "鉴权失败")

    monkeypatch.setattr(image_client, "_request_once", fake_once)
    with pytest.raises(image_client.ImageServiceError):
        image_client.generate_image(prompt="a", width=512, height=512, tier="hq")
    assert len(calls) == 1
