import json
import subprocess
from pathlib import Path

from aidrama_desktop.jianying.generator import JianyingProjectGenerator


def test_windows_draft_open_matches_legacy_full_description_flow():
    tool = Path(__file__).parents[2] / "scripts" / "jianying" / "create-jianying-project.js"
    helper = (
        Path(__file__).parents[1]
        / "src"
        / "aidrama_desktop"
        / "jianying"
        / "windows_uia_helper.py"
    )
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    pyinstaller_spec = (
        Path(__file__).parents[1] / "packaging" / "pyinstaller" / "ai-drama-desktop.spec"
    )
    gui_app = Path(__file__).parents[1] / "src" / "aidrama_desktop" / "gui" / "app.py"
    source = tool.read_text(encoding="utf-8")
    helper_source = helper.read_text(encoding="utf-8")
    pyproject_source = pyproject.read_text(encoding="utf-8")
    pyinstaller_source = pyinstaller_spec.read_text(encoding="utf-8")
    gui_source = gui_app.read_text(encoding="utf-8")
    windows_open = source.split("function runWindowsUiaHelper", 1)[1].split(
        "function openFirstDraftCard", 1
    )[0]
    windows_launch = source.split("function openJianying", 1)[1].split(
        "function sleep", 1
    )[0]
    editor_check = source.split("function windowsJianyingEditorReady", 1)[1].split(
        "function postCreateAutomation", 1
    )[0]
    windows_debug = source.split("function debugWindowsOpen", 1)[1].split(
        "function createProject", 1
    )[0]
    assert "assertWindowsJianyingAutomationCompatible(appPath)" in windows_launch
    assert "spawn(appPath, []," in windows_launch
    assert "--force-renderer-accessibility=complete" not in source
    assert "RECOMMENDED_WINDOWS_JIANYING_VERSION = '5.9.0.11632'" in source
    assert "MAX_UIA_AUTOMATION_JIANYING_MAJOR = 6" in source
    assert "Jianying 7 or above is not supported" in source
    assert "runWindowsUiaHelper(helperCommandJson, appPath, draftName)" in windows_open
    assert "--progress-file" in windows_open
    assert "Bundled Python uiautomation helper" in windows_open
    assert "execPowerShellScript" not in windows_open
    assert "LookupById(30159)" not in source
    assert 'importlib.import_module("uiautomation")' in helper_source
    assert 'target_description = f"HomePageDraftTitle:{draft_name}"' in helper_source
    assert "app.TextControl(searchDepth=2, Compare=compare)" in helper_source
    assert "control.GetPropertyValue(30159)" in helper_source
    assert "title.GetParentControl()" in helper_source
    assert "draft_card.Click(simulateMove=False)" in helper_source
    assert 'if depth != 2:' in helper_source
    assert 'if "homepage" in lowered_class:' in helper_source
    assert 'if "mainwindow" in lowered_class:' in helper_source
    assert "python-uia-draft-title-observed" in helper_source
    assert '"uiautomation>=2; sys_platform == \'win32\'"' in pyproject_source
    assert 'hiddenimports=["uiautomation"] if sys.platform.startswith("win") else []' in (
        pyinstaller_source
    )
    assert 'if "--jianying-uia-helper" in argv:' in gui_source
    assert "OCR" not in source.upper()
    assert "OCR" not in helper_source.upper()
    assert "$draftReady" in editor_check
    assert "jianying-editor-ready" in editor_check
    assert "Click-WindowRatio" not in windows_debug
    assert "winOpenDraftByTitle(appPath, draftName, args.windowsUiaHelperCommand)" in windows_debug


def test_jianying_tool_registers_platform_safe_and_competitor_native_strategies():
    tool = Path(__file__).parents[2] / "scripts" / "jianying" / "create-jianying-project.js"
    source = tool.read_text(encoding="utf-8")
    platform_safe_config = source.split("id: 'platform-safe-v1'", 1)[1].split(
        "id: 'layered-proof-v1'", 1
    )[0]
    competitor_config = source.split("id: 'competitor-native-v1'", 1)[1].split(
        "const DEFAULT_TIMELINE_STRATEGY_ID", 1
    )[0]

    assert "id: 'platform-safe-v1'" in source
    assert "label: '平台安全工程'" in source
    assert "const DEFAULT_TIMELINE_STRATEGY_ID = 'platform-safe-v1'" in source
    assert "sourceClipCount: 12" in platform_safe_config
    assert "timelineClipCount: 12" in platform_safe_config
    assert "maxTimelineAudioTracks: 2" in platform_safe_config
    assert "maxBgmAudioTracks: 1" in platform_safe_config
    assert "name: '调色'" in platform_safe_config
    assert "nativeEffectTracks" not in platform_safe_config
    assert "nativeStickerTracks" not in platform_safe_config
    assert "id: 'competitor-native-v1'" in source
    assert "label: '竞品原生工程'" in source
    assert "sourceClipCount: 5" in source
    assert "timelineClipCount: 10" in source
    assert "dialogueAudioMode: 'source-clips'" in source
    assert "hideAudioInMediaPanel: true" in competitor_config
    assert "bgmPlan: 'staggered-beds'" in source
    assert "metetype: 'none'" in source
    assert "auxiliaryTextTracks" not in competitor_config
    assert "nativeFilterTracks" in competitor_config
    assert "nativeEffectTracks" in competitor_config
    assert "nativeStickerTracks" in competitor_config
    assert "NATIVE_FILTERS" in source
    assert "NATIVE_VIDEO_EFFECTS" in source
    assert "type: 'filter'" in source
    assert "type: meta.effectType || 'video_effect'" in source
    assert "type: 'sticker'" in source
    assert source.index("subtitleTracks.forEach") < source.index("nativeVisualTracks.filterTracks.forEach")
    assert source.index("subtitleTracks.forEach") < source.index("nativeVisualTracks.effectTracks.forEach")
    assert source.index("subtitleTracks.forEach") < source.index("nativeVisualTracks.stickerTracks.forEach")


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
    monkeypatch.setattr(
        "aidrama_desktop.jianying.generator._windows_uia_helper_command",
        lambda: ["AI Drama Desktop.exe", "--jianying-uia-helper"],
    )

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
    helper_command = json.loads(command[command.index("--windows-uia-helper-command") + 1])
    assert helper_command == ["AI Drama Desktop.exe", "--jianying-uia-helper"]


def test_jianying_generator_passes_strategy_to_tool(monkeypatch, tmp_path):
    video = tmp_path / "episode.mp4"
    tool = tmp_path / "create-jianying-project.js"
    screenshot = tmp_path / "proof.png"
    video.write_text("video")
    tool.write_text("tool")
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
                    "strategy_id": "competitor-native-v1",
                    "strategy_label": "竞品原生工程",
                    "warnings": [],
                }
            ),
        )

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
        strategy="competitor-native-v1",
    )

    command = commands[0]
    assert command[command.index("--strategy") + 1] == "competitor-native-v1"
    assert result.strategy_id == "competitor-native-v1"
    assert result.strategy_label == "竞品原生工程"


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
