from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def find_chrome(explicit_path: str | None = None) -> str:
    if explicit_path:
        return explicit_path
    candidates: list[str] = []
    if sys.platform == "darwin":
        candidates.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    elif sys.platform.startswith("win"):
        candidates.extend(
            [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            ]
        )
    candidates.extend(["google-chrome", "chrome", "chromium"])
    for candidate in candidates:
        resolved = shutil.which(candidate) or candidate
        if Path(resolved).exists() or shutil.which(resolved):
            return resolved
    raise FileNotFoundError("Chrome not found. Set AIDRAMA_CHROME_PATH.")


@dataclass
class ChromeController:
    chrome_path: str
    profile_root: Path

    def platform_profile_dir(self, platform: str, account_id: str | None = None) -> Path:
        profile_dir = self.profile_root / platform.lower()
        if account_id:
            profile_dir = profile_dir / account_id
        profile_dir.mkdir(parents=True, exist_ok=True)
        return profile_dir

    def open_platform_login(
        self,
        platform: str,
        url: str,
        account_id: str | None = None,
        remote_debugging_port: int | None = None,
    ) -> subprocess.Popen[bytes]:
        profile_dir = self.platform_profile_dir(platform, account_id)
        return self.open_profile(profile_dir, url, remote_debugging_port)

    def open_profile(
        self,
        profile_dir: Path,
        url: str,
        remote_debugging_port: int | None = None,
    ) -> subprocess.Popen[bytes]:
        profile_dir.mkdir(parents=True, exist_ok=True)
        args = [
            self.chrome_path,
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--disable-default-apps",
        ]
        if remote_debugging_port is not None:
            args.append("--remote-debugging-address=127.0.0.1")
            args.append(f"--remote-debugging-port={remote_debugging_port}")
        args.append(url)
        return subprocess.Popen(
            args
        )

    def login_state_ref(self, platform: str, account_id: str | None = None) -> str:
        return str(self.platform_profile_dir(platform, account_id))
