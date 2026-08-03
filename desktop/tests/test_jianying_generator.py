import json
import subprocess

from aidrama_desktop.jianying.generator import JianyingProjectGenerator


def test_jianying_generator_passes_sibling_ffprobe_to_tool(monkeypatch, tmp_path):
    video = tmp_path / "episode.mp4"
    tool = tmp_path / "create-jianying-project.js"
    screenshot = tmp_path / "proof.png"
    result = tmp_path / "result.json"
    jianying_app = tmp_path / "JianyingPro.exe"
    video.write_text("video")
    tool.write_text("tool")
    jianying_app.write_text("app")
    commands: list[list[str]] = []

    def fake_run(command, check=False, capture_output=False, text=False, timeout=None, **kwargs):
        commands.append(command)
        screenshot.write_bytes(b"png")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "screenshot_path": str(screenshot),
                    "draft_dir": str(tmp_path / "draft"),
                    "result_path": str(result),
                    "warnings": [],
                }
            ),
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    generator = JianyingProjectGenerator(
        ffmpeg_path="/opt/homebrew/bin/ffmpeg",
        node_path="/opt/homebrew/bin/node",
        tool_path=tool,
        jianying_app=jianying_app,
    )

    generator.generate_project_screenshot(
        video=video,
        draft_name="测试工程",
        output_dir=tmp_path,
        screenshot_path=screenshot,
    )

    command = commands[0]
    assert command[command.index("--ffmpeg") + 1] == "/opt/homebrew/bin/ffmpeg"
    assert command[command.index("--ffprobe") + 1] == "/opt/homebrew/bin/ffprobe"
    assert command[command.index("--jianying-app") + 1] == str(jianying_app)
