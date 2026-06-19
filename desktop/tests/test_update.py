from pathlib import Path

from aidrama_desktop.update import (
    UpdateInfo,
    detect_platform,
    download_installer,
    installer_file_name,
    open_installer,
)


def test_detect_platform_maps_darwin_and_windows() -> None:
    assert detect_platform("Darwin") == "MAC"
    assert detect_platform("Windows") == "WINDOWS"
    assert detect_platform("Linux") is None


def test_installer_file_name_prefers_backend_file_name() -> None:
    update = UpdateInfo(
        version="0.2.0",
        release_notes="notes",
        mandatory=False,
        file_name="AI Drama.pkg",
        file_size=10,
        download_url="/uploads/app.pkg",
    )

    assert installer_file_name(update) == "AI Drama.pkg"


def test_download_installer_writes_response_bytes(tmp_path: Path, monkeypatch) -> None:
    calls = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield b"abc"
            yield b"123"

    class Stream:
        def __enter__(self):
            return Response()

        def __exit__(self, exc_type, exc, tb):
            return False

    class Client:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url):
            calls.append((method, url))
            return Stream()

    monkeypatch.setattr("aidrama_desktop.update.httpx.Client", Client)
    update = UpdateInfo(
        version="0.2.0",
        release_notes="notes",
        mandatory=False,
        file_name="AI Drama.pkg",
        file_size=6,
        download_url="/uploads/app.pkg",
    )

    path = download_installer(update, tmp_path, "http://server/api")

    assert calls == [("GET", "http://server/uploads/app.pkg")]
    assert path.read_bytes() == b"abc123"


def test_download_installer_sends_auth_headers(tmp_path: Path, monkeypatch) -> None:
    calls = []

    class Response:
        def raise_for_status(self) -> None:
            return None

        def iter_bytes(self):
            yield b"installer"

    class Stream:
        def __enter__(self):
            return Response()

        def __exit__(self, exc_type, exc, tb):
            return False

    class Client:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, headers=None):
            calls.append((method, url, headers))
            return Stream()

    monkeypatch.setattr("aidrama_desktop.update.httpx.Client", Client)
    update = UpdateInfo(
        version="0.2.0",
        release_notes="notes",
        mandatory=False,
        file_name="AI Drama.pkg",
        file_size=9,
        download_url="/uploads/app.pkg",
    )

    path = download_installer(update, tmp_path, "http://server/api", headers={"Authorization": "Bearer token"})

    assert calls == [("GET", "http://server/uploads/app.pkg", {"Authorization": "Bearer token"})]
    assert path.read_bytes() == b"installer"


def test_open_installer_uses_platform_opener(tmp_path: Path) -> None:
    opened = []
    installer = tmp_path / "AI Drama.pkg"
    installer.write_text("x")

    open_installer(installer, "MAC", opener=lambda command: opened.append(command))

    assert opened == [["open", str(installer)]]
