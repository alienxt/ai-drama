from pathlib import Path

from aidrama_desktop.config.settings import Settings
from aidrama_desktop.gui.app import DesktopWindow
from aidrama_desktop.gui.state import AppStatus, desktop_nav_items, settings_rows, update_settings


def test_app_status_uses_settings_and_login_state(tmp_path: Path):
    settings = Settings(
        server_url="http://server/api",
        device_id="device-1",
        local_agent_port=19000,
        work_dir=tmp_path / "work",
        browser_profile_dir=tmp_path / "profiles",
        token_file=tmp_path / "token",
    )

    status = AppStatus.from_settings(settings, logged_in=True)

    assert status.server_url == "http://server/api"
    assert status.device_id == "device-1"
    assert status.login_state == "已登录"


def test_status_bar_text_hides_server_url():
    status = AppStatus(server_url="http://server/api", device_id="device-1", login_state="未登录")

    assert DesktopWindow.status_bar_text(status) == "未登录"
    assert "http" not in DesktopWindow.status_bar_text(status)


def test_status_bar_disclaimer_text():
    assert DesktopWindow.status_bar_disclaimer_text() == "平台内容均来自互联网，请勿随意转发"


def test_desktop_nav_items_cover_core_gui_pages():
    assert [item.key for item in desktop_nav_items()] == [
        "dramas",
        "media",
        "contracts",
        "tasks",
        "settings",
        "logs",
    ]


def test_update_settings_supports_pydantic_settings(tmp_path: Path):
    settings = Settings(
        server_url="http://old/api",
        work_dir=tmp_path / "work",
        browser_profile_dir=tmp_path / "profiles",
        token_file=tmp_path / "token",
    )

    updated = update_settings(settings, server_url="http://new/api")

    assert updated.server_url == "http://new/api"
    assert settings.server_url == "http://old/api"


def test_settings_rows_marks_directory_values(tmp_path: Path):
    settings = Settings(
        work_dir=tmp_path / "work",
        browser_profile_dir=tmp_path / "profiles",
        token_file=tmp_path / "token",
    )

    rows = settings_rows(settings)
    directory_labels = {row.label for row in rows if row.kind == "directory"}
    file_labels = {row.label for row in rows if row.kind == "file"}

    assert "工作根目录" in directory_labels
    assert "合同目录" in directory_labels
    assert "浏览器登录态目录" in directory_labels
    assert "Token 文件" in file_labels
    assert "服务地址" not in directory_labels
    assert all(row.label != "本地服务端口" for row in rows)


def test_settings_rows_include_current_desktop_version(tmp_path: Path):
    settings = Settings(
        work_dir=tmp_path / "work",
        browser_profile_dir=tmp_path / "profiles",
        token_file=tmp_path / "token",
    )

    rows = settings_rows(settings)

    assert any(row.label == "当前版本" and row.value for row in rows)
