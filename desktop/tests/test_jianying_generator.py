import json
import subprocess
from pathlib import Path

from aidrama_desktop.jianying.generator import JianyingProjectGenerator


def test_windows_draft_open_matches_legacy_full_description_flow():
    tool = Path(__file__).parents[2] / "scripts" / "jianying" / "create-jianying-project.js"
    source = tool.read_text(encoding="utf-8")
    windows_open = source.split("function winOpenDraftByTitle", 1)[1].split(
        "function openFirstDraftCard", 1
    )[0]
    windows_launch = source.split("function openJianying", 1)[1].split(
        "function sleep", 1
    )[0]
    legacy_open = windows_open.split("function Wait-LegacyWindowClass", 1)[1]
    editor_check = source.split("function windowsJianyingEditorReady", 1)[1].split(
        "function postCreateAutomation", 1
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
    assert "assertWindowsJianyingAutomationCompatible(appPath)" in windows_launch
    assert "spawn(appPath, []," in windows_launch
    assert "--force-renderer-accessibility=complete" not in source
    assert "RECOMMENDED_WINDOWS_JIANYING_VERSION = '5.9.0.11632'" in source
    assert "MAX_UIA_AUTOMATION_JIANYING_MAJOR = 6" in source
    assert "Jianying 7 or above is not supported" in source
    assert "AutomationProperty]::LookupById(30159)" in windows_open
    assert "function Get-ElementFullDescription" in windows_open
    assert "GetCurrentPropertyValue($property, $true)" in windows_open
    assert '$targetDescription = "HomePageDraftTitle:$draftName"' in legacy_open
    assert "PropertyCondition]::new" in windows_open
    assert "function Find-ExactLegacyDraftTitle" in legacy_open
    assert "$levelOne = $walker.GetFirstChild($root)" in legacy_open
    assert "$levelTwo = $walker.GetFirstChild($levelOne)" in legacy_open
    assert "$levelTwo.Current.ControlType -eq [System.Windows.Automation.ControlType]::Text" in legacy_open
    assert "(Get-ElementFullDescription $levelTwo) -eq $targetDescription" in legacy_open
    assert "TreeWalker]::ControlViewWalker.GetParent($titleElement)" in legacy_open
    assert "Click-Element $draftCard 1" in legacy_open
    assert "Wait-LegacyWindowClass 'MainWindow' 35" in legacy_open
    assert "Find-UniqueEllipsizedDraftTitleElement" not in legacy_open
    assert "Try-OpenFromDraftDetail" not in legacy_open
    assert "OCR" not in source.upper()
    assert "$rootName -eq '剪映专业版' -and $rootClassName -match 'MainWindow'" in editor_check
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
