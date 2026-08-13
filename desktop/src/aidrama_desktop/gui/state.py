from __future__ import annotations

from dataclasses import dataclass

from aidrama_desktop import __version__
from aidrama_desktop.config.settings import Settings, jianying_project_strategy_preference_label


@dataclass(frozen=True)
class AppStatus:
    device_id: str
    login_state: str

    @classmethod
    def from_settings(cls, settings: Settings, logged_in: bool) -> "AppStatus":
        return cls(
            device_id=settings.device_id,
            login_state="已登录" if logged_in else "未登录",
        )


@dataclass(frozen=True)
class NavItem:
    key: str
    title: str
    description: str


@dataclass(frozen=True)
class SettingsRow:
    label: str
    value: str
    kind: str = "text"


def desktop_nav_items() -> list[NavItem]:
    return [
        NavItem("dramas", "短剧库", "可分发短剧列表，默认展示近 7 天更新内容"),
        NavItem("media", "媒体号", "视频号账号、登录态与浏览器打开"),
        NavItem("contracts", "合同配置", "成本合同、购买合同、权利声明 Word 模板与本地生成"),
        NavItem("tasks", "任务管理", "任务历史、重试与自动发布"),
        NavItem("settings", "系统设置", "设备 ID 和工具路径"),
        NavItem("logs", "运行日志", "桌面端操作与错误记录"),
    ]


def settings_rows(settings: Settings) -> list[SettingsRow]:
    return [
        SettingsRow("当前版本", __version__),
        SettingsRow("设备 ID", settings.device_id),
        SettingsRow("工作根目录", str(settings.work_dir), "directory"),
        SettingsRow("配置目录", str(settings.config_dir), "directory"),
        SettingsRow("Token 文件", str(settings.token_file), "file"),
        SettingsRow("记住登录文件", str(settings.remembered_login_file), "file"),
        SettingsRow("短剧目录", str(settings.dramas_dir), "directory"),
        SettingsRow("下载原片目录", str(settings.downloads_dir), "directory"),
        SettingsRow("转码成品目录", str(settings.processed_dir), "directory"),
        SettingsRow("合同目录", str(settings.contracts_dir), "directory"),
        SettingsRow("临时目录", str(settings.temp_dir), "directory"),
        SettingsRow("更新包目录", str(settings.updates_dir), "directory"),
        SettingsRow("浏览器登录态目录", str(settings.browser_profile_dir), "directory"),
        SettingsRow("FFmpeg", settings.ffmpeg_path),
        SettingsRow("字幕引擎", settings.subtitle_provider),
        SettingsRow("faster-whisper Python", settings.faster_whisper_python_path or "自动探测"),
        SettingsRow("openai-whisper", settings.whisper_path or "自动探测"),
        SettingsRow("Node.js", settings.node_path or "自动探测"),
        SettingsRow("剪映草稿目录", str(settings.jianying_draft_root) if settings.jianying_draft_root else "自动探测"),
        SettingsRow("剪映程序地址", str(settings.jianying_app) if settings.jianying_app else "自动探测"),
        SettingsRow("剪映音乐目录", str(settings.jianying_music_dir) if settings.jianying_music_dir else "默认目录"),
        SettingsRow("剪映图策略", jianying_project_strategy_preference_label(settings.jianying_project_strategy)),
        SettingsRow("视频号日上传上限", f"{settings.wechat_video_daily_upload_limit} 次"),
        SettingsRow(
            "免费集数比例覆盖",
            f"{settings.free_episode_ratio_override:.0%}" if settings.free_episode_ratio_override is not None else "跟随后台默认",
        ),
        SettingsRow("LibreOffice", settings.soffice_path),
    ]


def update_settings(settings: Settings, **values: object) -> Settings:
    values.pop("server_url", None)
    return settings.model_copy(update=values)
