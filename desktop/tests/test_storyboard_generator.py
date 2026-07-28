from PySide6.QtGui import QColor, QImage
import httpx

from aidrama_desktop.storyboard import infer_storyboard_style
from aidrama_desktop.storyboard.generator import (
    DEEPSEEK_READ_TIMEOUT_SECONDS,
    StoryboardGenerationConfig,
    StoryboardGenerator,
    build_deepseek_request,
    render_ai_production_proof_image,
    sample_consecutive_shot_indexes,
)


def test_infers_costume_storyboard_style_from_title():
    assert infer_storyboard_style(title="桃枝入旧朝") == "真人风格-古代"


def test_infers_costume_storyboard_style_from_category():
    assert infer_storyboard_style(title="神医归来", category_ids=["costume"]) == "真人风格-古代"


def test_custom_storyboard_style_is_not_overridden():
    assert (
        infer_storyboard_style(title="桃枝入旧朝", configured_style="真人风格-赛博朋克")
        == "真人风格-赛博朋克"
    )


def test_deepseek_prompt_requests_long_storyboard_summary():
    request = build_deepseek_request(
        {
            "drama": {"title": "桃枝入旧朝"},
            "episode": {"title": "#10集"},
            "source": {"duration": 180, "width": 720, "height": 1280, "fps": 30},
            "workspace": {"style": "真人风格-古代"},
            "shots": [{"index": 1, "startTimecode": "00:00", "endTimecode": "00:10", "durationSeconds": 10}],
        },
        "deepseek-v4-pro",
    )

    prompt = request["messages"][1]["content"]
    assert "summary 控制 150-300 个中文字符" in prompt
    assert "至少达到原合格长度的 5 倍" in prompt


def test_samples_consecutive_shots(monkeypatch):
    monkeypatch.setattr("aidrama_desktop.storyboard.generator.random.randint", lambda start, end: 4)

    assert sample_consecutive_shot_indexes(10, 3) == [4, 5, 6]
    assert sample_consecutive_shot_indexes(2, 3) == [1, 2]
    assert sample_consecutive_shot_indexes(0, 3) == []


def test_render_ai_production_proof_image_stacks_three_screenshots(tmp_path):
    source_images = []
    for index, color in enumerate(("red", "green", "blue"), start=1):
        image = QImage(200, 100, QImage.Format.Format_RGB32)
        image.fill(QColor(color))
        path = tmp_path / f"shot-{index}.png"
        assert image.save(str(path), "PNG")
        source_images.append(path)

    target = tmp_path / "AI制作证明.jpg"
    result = render_ai_production_proof_image(source_images, target, max_width=100)

    proof = QImage(str(result))
    assert result == target
    assert target.exists()
    assert target.stat().st_size < 10 * 1024 * 1024
    assert proof.width() == 100
    assert proof.height() == 150


def test_deepseek_analysis_retries_read_timeout(monkeypatch):
    attempts = []
    timeouts = []

    class FakeResponse:
        text = ""
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"shots":[]}'}}]}

    class FakeClient:
        def __init__(self, timeout):
            timeouts.append(timeout)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def post(self, url, json=None, headers=None):
            attempts.append((url, json, headers))
            if len(attempts) == 1:
                request = httpx.Request("POST", url)
                raise httpx.ReadTimeout("The read operation timed out", request=request)
            return FakeResponse()

    monkeypatch.setattr("aidrama_desktop.storyboard.generator.httpx.Client", FakeClient)
    monkeypatch.setattr("aidrama_desktop.storyboard.generator.time.sleep", lambda seconds: None)

    storyboard = {
        "drama": {"title": "退场后的光"},
        "episode": {"title": "#1集"},
        "source": {"duration": 60, "width": 720, "height": 1280, "fps": 30},
        "workspace": {"style": "真人风格-国产都市"},
        "shots": [{"index": 1, "title": "1-1 自动分镜"}],
    }
    config = StoryboardGenerationConfig(
        enabled=True,
        deepseek_api_key="key",
        deepseek_model="deepseek-v4-pro",
    )

    result = StoryboardGenerator()._enrich_with_deepseek(storyboard, config)

    assert len(attempts) == 2
    assert timeouts[0].read == DEEPSEEK_READ_TIMEOUT_SECONDS
    assert result["deepseekInference"]["status"] == "completed"


def test_deepseek_analysis_falls_back_after_repeated_read_timeout(monkeypatch):
    attempts = []

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def post(self, url, json=None, headers=None):
            attempts.append(url)
            request = httpx.Request("POST", url)
            raise httpx.ReadTimeout("The read operation timed out", request=request)

    monkeypatch.setattr("aidrama_desktop.storyboard.generator.httpx.Client", FakeClient)
    monkeypatch.setattr("aidrama_desktop.storyboard.generator.time.sleep", lambda seconds: None)

    storyboard = {
        "drama": {"title": "退场后的光"},
        "episode": {"title": "#1集"},
        "source": {"duration": 60, "width": 720, "height": 1280, "fps": 30},
        "workspace": {"style": "真人风格-国产都市"},
        "shots": [{"index": 1, "title": "1-1 自动分镜", "summary": ""}],
    }
    config = StoryboardGenerationConfig(
        enabled=True,
        deepseek_api_key="key",
        deepseek_model="deepseek-v4-pro",
    )

    result = StoryboardGenerator()._enrich_with_deepseek(storyboard, config)

    assert len(attempts) == 2
    assert result["deepseekInference"]["status"] == "fallback"
    assert "读取响应超时" in result["deepseekInference"]["reason"]
    assert len(result["shots"][0]["summary"]) >= 150
