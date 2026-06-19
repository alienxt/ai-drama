import json
from pathlib import Path

from aidrama_desktop.tasks.runner import TaskRunner, download_episodes


class FakeApi:
    base_url = "http://server/api"

    def __init__(self):
        self.calls = []
        self.download_token = "token-1"

    def post(self, path, payload=None):
        self.calls.append(("POST", path, payload))
        if path == "/desktop/tasks/publish-next":
            return {"id": "task-1", "dramaId": "drama-1", "mediaAccountId": "media-1"}
        if path.endswith("/result"):
            return {"ok": True}
        return {}

    def get(self, path):
        self.calls.append(("GET", path, None))
        return {
            "dramaId": "drama-1",
            "title": "神医归来",
            "summary": "简介",
            "episodes": [
                {"episodeNo": 1, "downloadUrl": "/files/1.mp4"},
                {"episodeNo": 2, "downloadUrl": "/files/2.mp4"},
            ],
        }

    def put(self, path, payload=None):
        self.calls.append(("PUT", path, payload))
        return {}

    def download_headers(self):
        return {"Authorization": f"Bearer {self.download_token}"}


class FakeProcessor:
    def transcode_for_wechat_video(self, source: Path, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.name)
        return target


class FakePublisher:
    def __init__(self):
        self.title = None
        self.files = []

    def publish(self, media_files, title, summary=None):
        self.files = media_files
        self.title = title
        return "published-1"


class FailingPublisher:
    def publish(self, media_files, title, summary=None):
        raise RuntimeError("upload failed")


def test_publish_once_prepares_task_and_downloads_each_episode(tmp_path, monkeypatch):
    api = FakeApi()
    publisher = FakePublisher()
    progress_events = []

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None):
        files = []
        total = len(download_plan["episodes"])
        for index, episode in enumerate(download_plan["episodes"], start=1):
            if progress_callback:
                progress_callback(index, total, episode, 5 * 1024 * 1024, 10 * 1024 * 1024)
            target = target_dir / f"{episode['episodeNo']:03d}.mp4"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(headers["Authorization"] + " " + episode["downloadUrl"])
            files.append(target)
        return files

    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", fake_download)

    runner = TaskRunner(
        api=api,
        processor=FakeProcessor(),
        publisher=publisher,
        work_dir=tmp_path,
        device_id="device-1",
        progress_callback=lambda stage, task_id: progress_events.append((stage, task_id)),
    )

    result = runner.publish_once()

    assert result == "succeeded"
    assert ("POST", "/desktop/tasks/publish-next", {"deviceId": "device-1"}) in api.calls
    assert ("GET", "/desktop/dramas/drama-1/download-plan", None) in api.calls
    assert publisher.title == "神医归来"
    assert len(publisher.files) == 2
    assert all(str(file).startswith(str(tmp_path / "dramas" / "processed" / "drama-1")) for file in publisher.files)
    assert ("下载：神医归来 第 1/2 集 5.0/10.0 MB（50%）", "task-1") in progress_events
    assert ("处理：神医归来 第 1/2 集", "task-1") in progress_events
    assert ("发布：神医归来", "task-1") in progress_events


def test_publish_once_uses_media_account_specific_publisher(tmp_path, monkeypatch):
    api = FakeApi()
    publishers = {}

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None):
        target = target_dir / "001.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("video")
        return [target]

    def publisher_factory(media_account_id):
        publisher = FakePublisher()
        publishers[media_account_id] = publisher
        return publisher

    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", fake_download)
    runner = TaskRunner(
        api=api,
        processor=FakeProcessor(),
        publisher=FakePublisher(),
        work_dir=tmp_path,
        device_id="device-1",
        publisher_factory=publisher_factory,
    )

    assert runner.publish_once() == "succeeded"
    assert "media-1" in publishers
    assert publishers["media-1"].title == "神医归来"


def test_publish_once_marks_task_failed_when_upload_fails(tmp_path, monkeypatch):
    api = FakeApi()

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None):
        target = target_dir / "001.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("video")
        return [target]

    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", fake_download)
    runner = TaskRunner(
        api=api,
        processor=FakeProcessor(),
        publisher=FailingPublisher(),
        work_dir=tmp_path,
        device_id="device-1",
    )

    result = runner.publish_once()

    assert result == "failed"
    assert (
        "PUT",
        "/desktop/tasks/task-1/result",
        {"success": False, "platformPublishId": None, "failureReason": "upload failed"},
    ) in api.calls


def test_publish_once_marks_task_cancelled_when_download_is_stopped(tmp_path, monkeypatch):
    api = FakeApi()

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None):
        from aidrama_desktop.tasks.runner import TaskCancelled

        raise TaskCancelled("用户停止下载")

    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", fake_download)
    runner = TaskRunner(
        api=api,
        processor=FakeProcessor(),
        publisher=FakePublisher(),
        work_dir=tmp_path,
        device_id="device-1",
    )

    assert runner.publish_once() == "cancelled"
    assert (
        "PUT",
        "/desktop/tasks/task-1/progress",
        {"status": "CANCELLED", "progress": 0},
    ) in api.calls


def test_download_episodes_writes_cover_and_metadata(tmp_path, monkeypatch):
    opened_urls = []

    class FakeResponse:
        def __init__(self, body: bytes):
            self.body = body
            self.offset = 0
            self.headers = {"Content-Length": str(len(body))}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size: int) -> bytes:
            if self.offset >= len(self.body):
                return b""
            chunk = self.body[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

    def fake_urlopen(request):
        opened_urls.append(request.full_url)
        if request.full_url.endswith("/uploads/covers/drama.jpg"):
            return FakeResponse(b"cover")
        return FakeResponse(b"video")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    download_plan = {
        "dramaId": "drama-1",
        "title": "神医归来",
        "aiTitle": "神医归来AI",
        "summary": "简介",
        "effectiveCoverUrl": "/uploads/covers/drama.jpg",
        "rating": 5,
        "categoryIds": ["urban"],
        "episodes": [
            {"episodeNo": 1, "title": "第一集", "sourcePath": "/pan/001.mp4", "downloadUrl": "/files/1.mp4"},
        ],
    }

    files = download_episodes(download_plan, tmp_path / "drama-1", "http://server/api")

    assert files == [tmp_path / "drama-1" / "001.mp4"]
    assert (tmp_path / "drama-1" / "fengmian.jpg").read_bytes() == b"cover"
    assert (tmp_path / "drama-1" / "001.mp4").read_bytes() == b"video"
    metadata = json.loads((tmp_path / "drama-1" / "meta.json").read_text(encoding="utf-8"))
    assert metadata["title"] == "神医归来"
    assert metadata["publishTitle"] == "神医归来AI"
    assert metadata["summary"] == "简介"
    assert metadata["coverFile"] == "fengmian.jpg"
    assert metadata["episodeCount"] == 1
    assert metadata["episodes"][0]["fileName"] == "001.mp4"
    assert opened_urls == ["http://server/uploads/covers/drama.jpg", "http://server/files/1.mp4"]
