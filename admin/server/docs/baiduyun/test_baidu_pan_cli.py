import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import baidu_pan_cli as cli


class FakeResponse:
    def __init__(self, payload=None, body=b""):
        self._payload = payload
        self._body = body

    def read(self):
        if self._payload is not None:
            return json.dumps(self._payload).encode("utf-8")
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class BaiduPanCliTests(unittest.TestCase):
    def make_config(self, tmpdir):
        return {
            "client_id": "client-id",
            "client_secret": "client-secret",
            "access_token": "old-token",
            "refresh_token": "refresh-token",
            "expires_in": 10,
            "token_obtained_at": 0,
            "app_name": "demo-app",
            "config_path": str(Path(tmpdir) / "config.json"),
        }

    @patch("baidu_pan_cli.time.time", return_value=1000)
    @patch("baidu_pan_cli.urlopen")
    def test_ensure_access_token_refreshes_expired_token(self, mock_urlopen, _mock_time):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.make_config(tmpdir)
            mock_urlopen.return_value = FakeResponse(
                {
                    "access_token": "new-token",
                    "refresh_token": "new-refresh-token",
                    "expires_in": 2592000,
                }
            )

            token = cli.ensure_access_token(config)

            self.assertEqual(token, "new-token")
            self.assertEqual(config["access_token"], "new-token")
            self.assertEqual(config["refresh_token"], "new-refresh-token")
            self.assertEqual(config["token_obtained_at"], 1000)

    @patch("baidu_pan_cli.urlopen")
    def test_get_entry_by_path_finds_file_in_parent_directory(self, mock_urlopen):
        mock_urlopen.return_value = FakeResponse(
            {
                "errno": 0,
                "list": [
                    {"path": "/apps/demo/video.mp4", "fs_id": 123, "isdir": 0},
                    {"path": "/apps/demo/other.txt", "fs_id": 456, "isdir": 0},
                ],
            }
        )

        entry = cli.get_entry_by_path("token-1", "/apps/demo/video.mp4")

        self.assertEqual(entry["fs_id"], 123)
        self.assertEqual(entry["path"], "/apps/demo/video.mp4")

    @patch("baidu_pan_cli.time.time", return_value=1000)
    @patch("baidu_pan_cli.urlopen")
    def test_download_file_resolves_dlink_and_writes_file(self, mock_urlopen, _mock_time):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = self.make_config(tmpdir)
            target = Path(tmpdir) / "video.mp4"

            mock_urlopen.side_effect = [
                FakeResponse(
                    {
                        "access_token": "fresh-token",
                        "refresh_token": "fresh-refresh-token",
                        "expires_in": 2592000,
                    }
                ),
                FakeResponse(
                    {
                        "errno": 0,
                        "list": [
                            {
                                "path": "/apps/demo/video.mp4",
                                "fs_id": 123,
                                "isdir": 0,
                                "size": 5,
                            }
                        ],
                    }
                ),
                FakeResponse(
                    {
                        "errno": 0,
                        "list": [{"dlink": "https://example.com/file.bin"}],
                    }
                ),
                FakeResponse(body=b"hello"),
            ]

            result = cli.download_file(config, "/apps/demo/video.mp4", str(target))

            self.assertEqual(result, target)
            self.assertEqual(target.read_bytes(), b"hello")


if __name__ == "__main__":
    unittest.main()
