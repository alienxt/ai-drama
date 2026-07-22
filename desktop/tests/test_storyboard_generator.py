from aidrama_desktop.storyboard import infer_storyboard_style
from aidrama_desktop.storyboard.generator import build_deepseek_request


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
