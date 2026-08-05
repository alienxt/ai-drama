import json
import subprocess
from pathlib import Path

from aidrama_desktop.jianying.generator import JianyingProjectGenerator


def test_windows_draft_open_uses_non_polluting_semantic_uia_actions():
    tool = Path(__file__).parents[2] / "scripts" / "jianying" / "create-jianying-project.js"
    source = tool.read_text(encoding="utf-8")
    windows_open = source.split("function winOpenDraftByTitle", 1)[1].split(
        "function openFirstDraftCard", 1
    )[0]
    windows_launch = source.split("function openJianying", 1)[1].split(
        "function sleep", 1
    )[0]
    windows_debug = source.split("function debugWindowsOpen", 1)[1].split(
        "function createProject", 1
    )[0]
    powershell_runner = source.split("function execPowerShellScript", 1)[1].split(
        "function normalizeKey", 1
    )[0]

    assert "Write-Output" not in windows_open
    assert "'-File'" in powershell_runner
    assert "mkdtempSync" in powershell_runner
    assert "\\uFEFF" in powershell_runner
    assert "rmSync" in powershell_runner
    assert "execPowerShellScript(script" in windows_open
    assert "'-Command', script" not in windows_open
    assert "function Write-ProgressLine" in windows_open
    assert "InvokePattern" in windows_open
    assert "LegacyIAccessiblePattern" in windows_open
    assert "SelectionItemPattern" in windows_open
    assert "--force-renderer-accessibility=complete" in windows_launch
    assert "PropertyCondition]::new" in windows_open
    assert ".FindFirst(" in windows_open
    assert "Find-ExactNamedElementInTargetWindow $root $draftNames" in windows_open
    assert "function Test-EllipsizedDraftTitleMatch" in windows_open
    assert "targetTitle.StartsWith($prefix) -and $targetTitle.EndsWith($suffix)" in windows_open
    assert "Find-UniqueEllipsizedDraftTitleElement $root $draftName 1200" in windows_open
    assert "draft-title-ellipsis-ambiguous" in windows_open
    assert "Find-ExactNamedElementInTargetWindow $initialRoot $initialDraftNames" in windows_open
    assert "-not $initialDraftElement -and -not (Wait-UiaTreeUsable $initialRoot 8)" in windows_open
    assert "uia-tree-unavailable-after-accessibility-launch" in windows_open
    assert "Write-UiaTreeSummary (Get-RootElement) 500 60" in windows_open
    assert "Try-OpenFirstDraftByHomeLayout" not in windows_open
    assert "Click-WindowRatio" not in windows_open
    assert "XRatio" not in windows_open
    assert "Click-WindowRatio" not in windows_debug
    assert "winOpenDraftByTitle(appPath, draftName)" in windows_debug


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


def test_jianying_generator_reads_result_file_when_stdout_is_empty(monkeypatch, tmp_path):
    video = tmp_path / "episode.mp4"
    tool = tmp_path / "create-jianying-project.js"
    screenshot = tmp_path / "proof.png"
    result_file = tmp_path / "jianying_project_result.json"
    draft_dir = tmp_path / "draft"
    video.write_text("video")
    tool.write_text("tool")
    draft_dir.mkdir()

    def fake_run(command, check=False, capture_output=False, text=False, timeout=None, **kwargs):
        screenshot.write_bytes(b"png")
        result_file.write_text(
            json.dumps(
                {
                    "screenshot_path": str(screenshot),
                    "draft_dir": str(draft_dir),
                    "result_path": str(result_file),
                    "warnings": [],
                }
            )
        )
        return subprocess.CompletedProcess(command, 0, stdout="")

    monkeypatch.setattr("subprocess.run", fake_run)

    generator = JianyingProjectGenerator(
        node_path="/opt/homebrew/bin/node",
        tool_path=tool,
    )

    result = generator.generate_project_screenshot(
        video=video,
        draft_name="测试工程",
        output_dir=tmp_path,
        screenshot_path=screenshot,
    )

    assert result.screenshot_path == screenshot
    assert result.draft_dir == draft_dir
    assert result.result_path == result_file
