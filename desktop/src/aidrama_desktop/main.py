from __future__ import annotations

import getpass

import typer

from aidrama_desktop.api.client import ApiClient
from aidrama_desktop.auth.token_store import TokenStore
from aidrama_desktop.browser.chrome import ChromeController, find_chrome
from aidrama_desktop.config.settings import load_settings
from aidrama_desktop.local_agent import serve_local_agent
from aidrama_desktop.platforms.registry import get_publisher, platform_login_url
from aidrama_desktop.tasks.runner import TaskRunner, download_episodes
from aidrama_desktop.video.ffmpeg import FfmpegProcessor

app = typer.Typer(help="AI Drama desktop agent")


def build_api() -> ApiClient:
    settings = load_settings()
    return ApiClient(settings.server_url, TokenStore(settings.token_file))


def build_chrome() -> ChromeController:
    settings = load_settings()
    return ChromeController(find_chrome(settings.chrome_path), settings.browser_profile_dir)


@app.command()
def login(username: str, password: str | None = None) -> None:
    """Login to the backend and save token locally."""
    settings = load_settings()
    api = ApiClient(settings.server_url, TokenStore(settings.token_file))
    api.login(username, password or getpass.getpass("Password: "), settings.device_id)
    typer.echo("logged-in")


@app.command("bind-wechat-video")
def bind_wechat_video(display_name: str = "视频号", external_account_id: str = "") -> None:
    """Open Chrome for WeChat Video login and register the media account."""
    settings = load_settings()
    api = build_api()
    chrome = build_chrome()
    media = api.post(
        "/desktop/media-accounts",
        {
            "platform": "WECHAT_VIDEO",
            "displayName": display_name,
            "externalAccountId": external_account_id,
            "deviceId": settings.device_id,
        },
    )
    chrome.open_platform_login("WECHAT_VIDEO", platform_login_url("WECHAT_VIDEO"), media["id"])
    login_state_ref = chrome.login_state_ref("WECHAT_VIDEO", media["id"])
    typer.echo("Chrome 已打开。请扫码登录视频号，登录完成后回到这里按 Enter。")
    input()
    api.put(
        f"/desktop/media-accounts/{media['id']}/login-state",
        {"loginStateRef": login_state_ref, "deviceId": settings.device_id, "verified": True},
    )
    typer.echo(f"media-account-bound:{media['id']}")


@app.command("open-media")
def open_media(platform: str = "WECHAT_VIDEO") -> None:
    """Open a platform browser profile; existing login state is reused."""
    publisher = get_publisher(platform, build_chrome())
    publisher.open_login()
    typer.echo("opened")


@app.command("agent")
def agent(port: int | None = None) -> None:
    """Run a local helper so the admin UI can open platform browser profiles."""
    settings = load_settings()
    actual_port = port or settings.local_agent_port

    def open_platform(platform: str, account_id: str | None = None) -> None:
        chrome = build_chrome()
        if account_id:
            chrome.open_platform_login(platform, platform_login_url(platform), account_id)
        else:
            get_publisher(platform, chrome).open_login()

    typer.echo(f"local-agent-listening:http://127.0.0.1:{actual_port}")
    serve_local_agent(actual_port, open_platform)


@app.command("categories")
def categories() -> None:
    """List backend drama categories."""
    for category in build_api().get("/desktop/categories"):
        typer.echo(f"{category['id'] or category['code']}\t{category['code']}\t{category['name']}")


@app.command("media-accounts")
def media_accounts() -> None:
    """List media accounts bound by this desktop user."""
    for media in build_api().get("/desktop/media-accounts"):
        policy = media.get("distributionPolicy") or {}
        typer.echo(
            f"{media['id']}\t{media['platform']}\t{media['displayName']}\t"
            f"{media['status']}\tcategories={','.join(policy.get('categoryIds') or [])}"
        )


@app.command("set-policy")
def set_policy(
    media_account_id: str,
    category_ids: str = typer.Option("", help="Comma separated category ids/codes"),
    daily_limit: int = 3,
    interval_minutes: int = 120,
    enabled: bool = True,
) -> None:
    """Set category and rate policy for a social account."""
    category_list = [item.strip() for item in category_ids.split(",") if item.strip()]
    build_api().put(
        f"/desktop/media-accounts/{media_account_id}/policy",
        {
            "categoryIds": category_list,
            "dailyLimit": daily_limit,
            "intervalMinutes": interval_minutes,
            "enabled": enabled,
            "transcodePreset": "wechat-video-default",
        },
    )
    typer.echo("policy-updated")


@app.command("download-drama")
def download_drama(drama_id: str) -> None:
    """Fetch real Baidu download links from backend and download the drama locally."""
    settings = load_settings()
    api = build_api()
    plan = api.get(f"/desktop/dramas/{drama_id}/download-plan")
    files = download_episodes(plan, settings.downloads_dir / drama_id, api.base_url)
    for file in files:
        typer.echo(str(file))


@app.command("run-once")
def run_once(platform: str = "WECHAT_VIDEO") -> None:
    """Claim and execute a single distribution task."""
    runner = build_runner(platform)
    typer.echo(runner.run_once())


@app.command("publish")
def publish(platform: str = "WECHAT_VIDEO") -> None:
    """Generate, claim and publish the next matched drama for this desktop user."""
    runner = build_runner(platform)
    typer.echo(runner.publish_once())


def build_runner(platform: str = "WECHAT_VIDEO") -> TaskRunner:
    settings = load_settings()
    return TaskRunner(
        api=build_api(),
        processor=FfmpegProcessor(settings.ffmpeg_path),
        publisher=get_publisher(platform, build_chrome()),
        work_dir=settings.work_dir,
        device_id=settings.device_id,
        downloads_dir=settings.downloads_dir,
        processed_dir=settings.processed_dir,
    )


@app.command("heartbeat")
def heartbeat() -> None:
    build_runner().heartbeat()
    typer.echo("ok")


if __name__ == "__main__":
    app()
