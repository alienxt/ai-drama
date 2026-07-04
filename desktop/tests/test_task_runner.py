import json
import threading
import time
import urllib.error
from pathlib import Path

from aidrama_desktop.tasks.runner import TaskRunner, download_episodes, episode_video_filename


class FakeApi:
    base_url = "http://server/api"

    def __init__(self):
        self.calls = []
        self.download_token = "token-1"

    def post(self, path, payload=None):
        self.calls.append(("POST", path, payload))
        if path == "/desktop/tasks/publish-next":
            return {"id": "task-1", "dramaId": "drama-1", "mediaAccountId": "media-1"}
        if path == "/desktop/tasks/task-1/prepare":
            return {"prepared": True, "preparing": False, "failed": False, "message": "AI 素材已准备完成", "retryAfterSeconds": 0}
        if path.endswith("/pause") or path.endswith("/skip"):
            return {"id": "task-1", "status": "PENDING"}
        if path.endswith("/force-stop"):
            return {"id": "task-1", "status": "CANCELLED"}
        if path.endswith("/result"):
            return {"ok": True}
        return {}

    def get(self, path):
        self.calls.append(("GET", path, None))
        return {
            "dramaId": "drama-1",
            "title": "神医归来",
            "summary": "简介",
            "aiSummary": "AI简介...",
            "totalMinutes": 20,
            "costAmountWan": 3,
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
    def __init__(self):
        self.calls = []
        self.dimensions = {}

    def transcode_for_wechat_video(self, source: Path, target: Path, cover_path: Path | None = None) -> Path:
        self.calls.append((source, target, cover_path))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.name)
        return target

    def video_dimensions(self, source: Path):
        return self.dimensions.get(source.name)


class LowBitrateProcessor(FakeProcessor):
    def needs_wechat_video_bitrate_transcode(self, source: Path) -> bool:
        return source.name == "001.mp4"


class FakePublisher:
    def __init__(self):
        self.title = None
        self.files = []
        self.summary = None
        self.metadata = None

    def publish(self, media_files, title, summary=None, metadata=None):
        self.files = media_files
        self.title = title
        self.summary = summary
        self.metadata = metadata
        return "published-1"


class FailingPublisher:
    def publish(self, media_files, title, summary=None, metadata=None):
        raise RuntimeError("upload failed")


class DraftPausedPublisher:
    def publish(self, media_files, title, summary=None, metadata=None):
        from aidrama_desktop.platforms.base import PlatformPublishPaused

        raise PlatformPublishPaused("剧目提审第一步表单已填好，暂未进入下一步或提交。")


class PlayletReadyPublisher:
    def publish(self, media_files, title, summary=None, metadata=None):
        from aidrama_desktop.platforms.base import PlatformPublishPaused

        raise PlatformPublishPaused("剧目提审第二步视频已上传完成，已停留在第二步剧集文件选取。")


def test_publish_once_prepares_task_and_downloads_each_episode(tmp_path, monkeypatch):
    api = FakeApi()
    processor = FakeProcessor()
    publisher = FakePublisher()
    progress_events = []

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None, should_pause=None, should_skip=None, max_concurrent_downloads=6):
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
        processor=processor,
        publisher=publisher,
        work_dir=tmp_path,
        device_id="device-1",
        progress_callback=lambda stage, task_id, task=None: progress_events.append((stage, task_id)),
    )

    result = runner.publish_once()

    assert result == "succeeded"
    assert ("POST", "/desktop/tasks/publish-next", {"deviceId": "device-1", "asyncPreparation": True}) in api.calls
    assert ("POST", "/desktop/tasks/task-1/prepare", None) in api.calls
    assert ("GET", "/desktop/dramas/drama-1/download-plan", None) in api.calls
    assert publisher.title == "神医归来"
    assert len(publisher.files) == 2
    assert all(str(file).startswith(str(tmp_path / "dramas" / "downloads" / "drama-1")) for file in publisher.files)
    assert processor.calls == []
    assert ("当前短剧：神医归来", "task-1") in progress_events
    assert ("下载：神医归来 第 1/2 集 5.0/10.0 MB（50%）", "task-1") in progress_events
    assert ("发布：神医归来", "task-1") in progress_events


def test_publish_once_waits_for_async_preparation_before_download(tmp_path, monkeypatch):
    api = FakeApi()
    prepare_calls = []

    def post(path, payload=None):
        api.calls.append(("POST", path, payload))
        if path == "/desktop/tasks/publish-next":
            return {"id": "task-1", "dramaId": "drama-1", "mediaAccountId": "media-1"}
        if path == "/desktop/tasks/task-1/prepare":
            prepare_calls.append(path)
            if len(prepare_calls) == 1:
                return {
                    "prepared": False,
                    "preparing": True,
                    "failed": False,
                    "message": "AI 素材准备中，请稍候",
                    "retryAfterSeconds": 1,
                }
            return {"prepared": True, "preparing": False, "failed": False, "message": "AI 素材已准备完成", "retryAfterSeconds": 0}
        if path.endswith("/result"):
            return {"ok": True}
        return {}

    api.post = post
    monkeypatch.setattr("aidrama_desktop.tasks.runner.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", lambda *args, **kwargs: [tmp_path / "001.mp4"])
    (tmp_path / "001.mp4").write_text("video")
    progress_events = []
    runner = TaskRunner(
        api=api,
        processor=FakeProcessor(),
        publisher=FakePublisher(),
        work_dir=tmp_path,
        device_id="device-1",
        progress_callback=lambda stage, task_id, task=None: progress_events.append((stage, task_id)),
    )

    assert runner.publish_once() == "succeeded"

    assert len(prepare_calls) == 2
    assert ("AI 素材准备中，请稍候", "task-1") in progress_events
    assert ("AI素材准备完成", "task-1") in progress_events


def test_publish_once_notifies_claimed_media_account(tmp_path, monkeypatch):
    api = FakeApi()
    publisher = FakePublisher()
    progress_events = []

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None, should_pause=None, should_skip=None, max_concurrent_downloads=6):
        target = target_dir / "001.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("video")
        return [target]

    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", fake_download)
    runner = TaskRunner(
        api=api,
        processor=FakeProcessor(),
        publisher=publisher,
        work_dir=tmp_path,
        device_id="device-1",
        progress_callback=lambda stage, task_id, task=None: progress_events.append((stage, task_id, task)),
    )

    assert runner.publish_once() == "succeeded"

    assert ("任务已领取", "task-1", {"id": "task-1", "dramaId": "drama-1", "mediaAccountId": "media-1"}) in progress_events


def test_publish_once_passes_playlet_metadata_to_publisher(tmp_path, monkeypatch):
    api = FakeApi()
    publisher = FakePublisher()
    cover_file = tmp_path / "dramas" / "downloads" / "drama-1" / "fengmian.jpg"

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None, should_pause=None, should_skip=None, max_concurrent_downloads=6):
        cover_file.parent.mkdir(parents=True, exist_ok=True)
        cover_file.write_text("cover")
        targets = []
        for episode in download_plan["episodes"]:
            target = target_dir / f"{episode['episodeNo']:03d}.mp4"
            target.write_text("video")
            targets.append(target)
        return targets

    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", fake_download)
    runner = TaskRunner(
        api=api,
        processor=FakeProcessor(),
        publisher=publisher,
        work_dir=tmp_path,
        device_id="device-1",
    )

    assert runner.publish_once() == "succeeded"

    assert publisher.summary == "AI简介..."
    assert publisher.metadata["dramaId"] == "drama-1"
    assert publisher.metadata["publishTitle"] == "神医归来"
    assert publisher.metadata["coverFile"] == cover_file
    assert publisher.metadata["totalMinutes"] == 20
    assert publisher.metadata["costAmountWan"] == 3
    assert publisher.metadata["productionCostWan"] == 3
    assert publisher.metadata["producerName"] == "乙方公司"
    assert publisher.metadata["aiContentDeclaration"] is True
    assert publisher.metadata["monetizationType"] == "IAA_AD"
    assert publisher.metadata["monetizationLabel"] == "IAA广告变现"
    assert publisher.metadata["freeEpisodeCount"] == 2
    assert publisher.metadata["episodeCount"] == 2
    assert publisher.metadata["episodes"] == [
        {"episodeNo": 1, "title": None, "file": tmp_path / "dramas" / "downloads" / "drama-1" / "001.mp4"},
        {"episodeNo": 2, "title": None, "file": tmp_path / "dramas" / "downloads" / "drama-1" / "002.mp4"},
    ]


def test_publish_once_transcodes_low_bitrate_video_before_upload(tmp_path, monkeypatch):
    api = FakeApi()
    publisher = FakePublisher()
    processor = LowBitrateProcessor()

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None, should_pause=None, should_skip=None, max_concurrent_downloads=6):
        files = []
        for episode in download_plan["episodes"]:
            target = target_dir / f"{episode['episodeNo']:03d}.mp4"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("video")
            files.append(target)
        return files

    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", fake_download)
    runner = TaskRunner(
        api=api,
        processor=processor,
        publisher=publisher,
        work_dir=tmp_path,
        device_id="device-1",
    )

    assert runner.publish_once() == "succeeded"

    processed_file = tmp_path / "dramas" / "processed" / "drama-1" / "001.mp4"
    assert publisher.files == [processed_file, tmp_path / "dramas" / "downloads" / "drama-1" / "002.mp4"]
    assert processor.calls == [(tmp_path / "dramas" / "downloads" / "drama-1" / "001.mp4", processed_file, None)]
    assert publisher.metadata["episodes"][0]["file"] == processed_file
    assert publisher.metadata["episodes"][1]["file"] == tmp_path / "dramas" / "downloads" / "drama-1" / "002.mp4"


def test_publish_once_adds_cover_frame_to_processed_videos(tmp_path, monkeypatch):
    api = FakeApi()
    publisher = FakePublisher()
    processor = LowBitrateProcessor()
    processor.dimensions = {"001.mp4": (720, 1280)}
    cover_file = tmp_path / "dramas" / "downloads" / "drama-1" / "fengmian.jpg"

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None, should_pause=None, should_skip=None, max_concurrent_downloads=6):
        cover_file.parent.mkdir(parents=True, exist_ok=True)
        cover_file.write_text("cover")
        files = []
        for episode in download_plan["episodes"]:
            target = target_dir / f"{episode['episodeNo']:03d}.mp4"
            target.write_text("video")
            files.append(target)
        return files

    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", fake_download)
    runner = TaskRunner(
        api=api,
        processor=processor,
        publisher=publisher,
        work_dir=tmp_path,
        device_id="device-1",
    )

    assert runner.publish_once() == "succeeded"

    processed_1 = tmp_path / "dramas" / "processed" / "drama-1" / "001.mp4"
    processed_2 = tmp_path / "dramas" / "processed" / "drama-1" / "002.mp4"
    assert publisher.files == [processed_1, processed_2]
    assert processor.calls == [
        (tmp_path / "dramas" / "downloads" / "drama-1" / "001.mp4", processed_1, cover_file),
        (tmp_path / "dramas" / "downloads" / "drama-1" / "002.mp4", processed_2, cover_file),
    ]
    marker = processed_2.with_name("002.mp4.aidrama.json")
    assert json.loads(marker.read_text(encoding="utf-8"))["cover"] == str(cover_file)


def test_publish_once_uses_video_cover_for_horizontal_videos(tmp_path, monkeypatch):
    api = FakeApi()
    publisher = FakePublisher()
    processor = LowBitrateProcessor()
    processor.dimensions = {"001.mp4": (1280, 720)}
    cover_file = tmp_path / "dramas" / "downloads" / "drama-1" / "fengmian.jpg"
    video_cover_file = tmp_path / "dramas" / "downloads" / "drama-1" / "video-cover.jpg"

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None, should_pause=None, should_skip=None, max_concurrent_downloads=6):
        cover_file.parent.mkdir(parents=True, exist_ok=True)
        cover_file.write_text("poster-cover")
        video_cover_file.write_text("video-cover")
        files = []
        for episode in download_plan["episodes"]:
            target = target_dir / f"{episode['episodeNo']:03d}.mp4"
            target.write_text("video")
            files.append(target)
        return files

    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", fake_download)
    runner = TaskRunner(
        api=api,
        processor=processor,
        publisher=publisher,
        work_dir=tmp_path,
        device_id="device-1",
    )

    assert runner.publish_once() == "succeeded"

    processed_1 = tmp_path / "dramas" / "processed" / "drama-1" / "001.mp4"
    assert processor.calls[0] == (
        tmp_path / "dramas" / "downloads" / "drama-1" / "001.mp4",
        processed_1,
        video_cover_file,
    )
    marker = processed_1.with_name("001.mp4.aidrama.json")
    assert json.loads(marker.read_text(encoding="utf-8"))["cover"] == str(video_cover_file)


def test_publish_metadata_uses_stable_free_episode_count():
    assert TaskRunner._free_episode_count({"freeEpisodeCount": 6}, 49) == 6
    assert TaskRunner._free_episode_count({}, 49) == 10
    assert TaskRunner._free_episode_count({}, 80) == 16
    assert TaskRunner._free_episode_count({}, 120) == 20
    assert TaskRunner._free_episode_count({}, 2) == 2


def test_publish_once_generates_contract_materials_before_upload(tmp_path, monkeypatch):
    from docx import Document

    api = FakeApi()
    publisher = FakePublisher()
    templates = {}
    for contract_type in ("cost", "purchase", "rights"):
        template = tmp_path / f"{contract_type}.docx"
        document = Document()
        document.add_paragraph(
            "{{contractType}} {{agreementNumber}} {{dramaTitle}} {{episodeCount}} {{episodeMinutes}} {{price}} {{halfPrice}}"
        )
        document.save(template)
        templates[f"wechat_video:{contract_type}"] = template

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None, should_pause=None, should_skip=None, max_concurrent_downloads=6):
        target = target_dir / "001.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("video")
        return [target]

    def fake_image_converter(docx_path: Path, image_dir: Path, image_stem: str | None = None):
        image_dir.mkdir(parents=True, exist_ok=True)
        image = image_dir / f"{image_stem or docx_path.stem}.png"
        image.write_bytes(b"png")
        return [image]

    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", fake_download)
    runner = TaskRunner(
        api=api,
        processor=FakeProcessor(),
        publisher=publisher,
        work_dir=tmp_path,
        device_id="device-1",
        contract_templates=templates,
        contracts_dir=tmp_path / "contracts",
        contract_buyer="甲方",
        contract_seller="乙方",
        contract_image_converter=fake_image_converter,
    )

    assert runner.publish_once() == "succeeded"

    assert publisher.metadata["purchaseContractDocx"].exists()
    assert publisher.metadata["costContractDocx"].exists()
    assert publisher.metadata["rightsStatementDocx"].exists()
    assert len(publisher.metadata["purchaseContractImages"]) == 1
    assert len(publisher.metadata["rightsStatementImages"]) == 1
    assert len(publisher.metadata["buyDramaContractImages"]) == 2
    assert len(publisher.metadata["costConfigReportImages"]) == 1
    assert publisher.metadata["buyDramaContractImages"][0].exists()
    assert publisher.metadata["buyDramaContractImages"][1].exists()
    assert publisher.metadata["costConfigReportImages"][0].exists()
    purchase_number = Document(publisher.metadata["purchaseContractDocx"]).paragraphs[0].text.split()[1]
    cost_number = Document(publisher.metadata["costContractDocx"]).paragraphs[0].text.split()[1]
    rights_number = Document(publisher.metadata["rightsStatementDocx"]).paragraphs[0].text.split()[1]
    assert purchase_number.startswith("HZ-")
    assert cost_number == purchase_number
    assert rights_number == purchase_number


def test_publish_once_uses_media_account_specific_publisher(tmp_path, monkeypatch):
    api = FakeApi()
    publishers = {}

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None, should_pause=None, should_skip=None, max_concurrent_downloads=6):
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

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None, should_pause=None, should_skip=None, max_concurrent_downloads=6):
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

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None, should_pause=None, should_skip=None, max_concurrent_downloads=6):
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
        "POST",
        "/desktop/tasks/task-1/force-stop",
        None,
    ) in api.calls


def test_publish_once_pauses_task_without_cancelling(tmp_path, monkeypatch):
    api = FakeApi()

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None, should_pause=None, should_skip=None, max_concurrent_downloads=6):
        from aidrama_desktop.tasks.runner import TaskPaused

        raise TaskPaused("用户暂停任务")

    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", fake_download)
    runner = TaskRunner(
        api=api,
        processor=FakeProcessor(),
        publisher=FakePublisher(),
        work_dir=tmp_path,
        device_id="device-1",
    )

    assert runner.publish_once() == "paused"
    assert ("POST", "/desktop/tasks/task-1/pause", {"deviceId": "device-1"}) in api.calls
    assert not any(call[1] == "/desktop/tasks/task-1/progress" and call[2]["status"] == "CANCELLED" for call in api.calls)


def test_publish_once_fails_upload_when_playlet_first_step_is_ready(tmp_path, monkeypatch):
    api = FakeApi()

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None, should_pause=None, should_skip=None, max_concurrent_downloads=6):
        target = target_dir / "001.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("video")
        return [target]

    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", fake_download)
    runner = TaskRunner(
        api=api,
        processor=FakeProcessor(),
        publisher=DraftPausedPublisher(),
        work_dir=tmp_path,
        device_id="device-1",
    )

    assert runner.publish_once() == "failed"
    assert (
        "PUT",
        "/desktop/tasks/task-1/result",
        {
            "success": False,
            "platformPublishId": None,
            "failureReason": "剧目提审第一步表单已填好，暂未进入下一步或提交。",
        },
    ) in api.calls
    assert ("POST", "/desktop/tasks/task-1/pause", {"deviceId": "device-1"}) not in api.calls


def test_publish_once_marks_playlet_ready_for_review_when_second_step_upload_is_done(tmp_path, monkeypatch):
    api = FakeApi()
    progress_events = []

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None, should_pause=None, should_skip=None, max_concurrent_downloads=6):
        target = target_dir / "001.mp4"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("video")
        return [target]

    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", fake_download)
    runner = TaskRunner(
        api=api,
        processor=FakeProcessor(),
        publisher=PlayletReadyPublisher(),
        work_dir=tmp_path,
        device_id="device-1",
        progress_callback=lambda stage, task_id, task=None: progress_events.append((stage, task_id)),
    )

    assert runner.publish_once() == "ready-for-review"
    assert (
        "PUT",
        "/desktop/tasks/task-1/result",
        {
            "success": True,
            "platformPublishId": "wechat-video-playlet-draft:task-1",
            "failureReason": None,
        },
    ) in api.calls
    assert ("视频已全部上传，等待确认提审", "task-1") in progress_events


def test_publish_once_skips_task_without_cancelling(tmp_path, monkeypatch):
    api = FakeApi()

    def fake_download(download_plan, target_dir, base_url, headers=None, progress_callback=None, should_stop=None, should_pause=None, should_skip=None, max_concurrent_downloads=6):
        from aidrama_desktop.tasks.runner import TaskSkipped

        raise TaskSkipped("用户跳过任务")

    monkeypatch.setattr("aidrama_desktop.tasks.runner.download_episodes", fake_download)
    runner = TaskRunner(
        api=api,
        processor=FakeProcessor(),
        publisher=FakePublisher(),
        work_dir=tmp_path,
        device_id="device-1",
    )

    assert runner.publish_once() == "skipped"
    assert ("POST", "/desktop/tasks/task-1/skip", {"deviceId": "device-1"}) in api.calls
    assert not any(call[1] == "/desktop/tasks/task-1/progress" and call[2]["status"] == "CANCELLED" for call in api.calls)


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
        if request.full_url.endswith("/uploads/covers/video.jpg"):
            return FakeResponse(b"video-cover")
        return FakeResponse(b"video")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    download_plan = {
        "dramaId": "drama-1",
        "title": "神医归来",
        "aiTitle": "神医归来AI",
        "summary": "简介",
        "aiSummary": "AI简介...",
        "effectiveCoverUrl": "/uploads/covers/drama.jpg",
        "aiVideoCoverUrl": "/uploads/covers/video.jpg",
        "rating": 5,
        "categoryIds": ["urban"],
        "episodes": [
            {"episodeNo": 1, "title": "第一集", "sourcePath": "/pan/001.mp4", "downloadUrl": "/files/1.mp4"},
        ],
    }

    files = download_episodes(download_plan, tmp_path / "drama-1", "http://server/api")

    episode_file = tmp_path / "drama-1" / "神医归来AI-第1集.mp4"
    assert files == [episode_file]
    assert (tmp_path / "drama-1" / "fengmian.jpg").read_bytes() == b"cover"
    assert (tmp_path / "drama-1" / "video-cover.jpg").read_bytes() == b"video-cover"
    assert episode_file.read_bytes() == b"video"
    metadata = json.loads((tmp_path / "drama-1" / "meta.json").read_text(encoding="utf-8"))
    assert metadata["title"] == "神医归来"
    assert metadata["publishTitle"] == "神医归来AI"
    assert metadata["summary"] == "AI简介..."
    assert metadata["aiSummary"] == "AI简介..."
    assert metadata["originalSummary"] == "简介"
    assert metadata["coverFile"] == "fengmian.jpg"
    assert metadata["videoCoverFile"] == "video-cover.jpg"
    assert metadata["videoCoverUrl"] == "/uploads/covers/video.jpg"
    assert metadata["episodeCount"] == 1
    assert metadata["episodes"][0]["fileName"] == "神医归来AI-第1集.mp4"
    assert metadata["episodes"][0]["size"] is None
    assert opened_urls == [
        "http://server/uploads/covers/drama.jpg",
        "http://server/uploads/covers/video.jpg",
        "http://server/files/1.mp4",
    ]


def test_download_episodes_skips_complete_existing_episode(tmp_path, monkeypatch):
    target_dir = tmp_path / "drama-1"
    target_dir.mkdir()
    legacy_file = target_dir / "001.mp4"
    legacy_file.write_bytes(b"already-downloaded")
    expected_file = target_dir / "续传短剧-第1集.mp4"
    opened_urls = []

    def fake_urlopen(request):
        opened_urls.append(request.full_url)
        raise AssertionError("complete episode should not be downloaded again")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    download_plan = {
        "dramaId": "drama-1",
        "title": "续传短剧",
        "episodes": [
            {
                "episodeNo": 1,
                "sourcePath": "/pan/001.mp4",
                "size": len(b"already-downloaded"),
                "downloadUrl": "/files/1.mp4",
            },
        ],
    }

    files = download_episodes(download_plan, target_dir, "http://server/api")

    assert files == [expected_file]
    assert expected_file.read_bytes() == b"already-downloaded"
    assert not legacy_file.exists()
    assert opened_urls == []


def test_download_episodes_retries_retryable_download_error(tmp_path, monkeypatch):
    opened_urls = []
    attempts = 0

    class FakeResponse:
        headers = {"Content-Length": "5"}

        def __enter__(self):
            self.offset = 0
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size: int) -> bytes:
            if self.offset:
                return b""
            self.offset += 1
            return b"video"

    def fake_urlopen(request):
        nonlocal attempts
        opened_urls.append(request.full_url)
        attempts += 1
        if attempts == 1:
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    download_plan = {
        "dramaId": "drama-1",
        "title": "重试短剧",
        "episodes": [
            {"episodeNo": 1, "sourcePath": "/pan/001.mp4", "size": 5, "downloadUrl": "/files/1.mp4"},
        ],
    }

    files = download_episodes(
        download_plan,
        tmp_path / "drama-1",
        "http://server/api",
        episode_retry_count=2,
        retry_delay_seconds=0,
    )

    episode_file = tmp_path / "drama-1" / "重试短剧-第1集.mp4"
    assert files == [episode_file]
    assert episode_file.read_bytes() == b"video"
    assert not (tmp_path / "drama-1" / "重试短剧-第1集.mp4.part").exists()
    assert opened_urls == ["http://server/files/1.mp4", "http://server/files/1.mp4"]


def test_download_resources_use_baidu_download_headers(tmp_path, monkeypatch):
    opened_headers = []

    class FakeResponse:
        headers = {"Content-Length": "5"}

        def __enter__(self):
            self.offset = 0
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self, size: int) -> bytes:
            if self.offset:
                return b""
            self.offset += 1
            return b"video"

    def fake_urlopen(request):
        opened_headers.append(dict(request.header_items()))
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    download_plan = {
        "dramaId": "drama-1",
        "title": "百度下载头",
        "effectiveCoverUrl": "/covers/drama.jpg",
        "episodes": [
            {"episodeNo": 1, "sourcePath": "/pan/001.mp4", "size": 5, "downloadUrl": "/files/1.mp4"},
        ],
    }

    download_episodes(
        download_plan,
        tmp_path / "drama-1",
        "http://server/api",
        headers={"Authorization": "Bearer token"},
    )

    assert len(opened_headers) == 2
    for headers in opened_headers:
        assert headers["User-agent"] == "pan.baidu.com"
        assert headers["Referer"] == "https://pan.baidu.com/"
        assert headers["Authorization"] == "Bearer token"


def test_download_episodes_downloads_episodes_concurrently_with_limit(tmp_path, monkeypatch):
    active = 0
    max_active = 0
    lock = threading.Lock()
    opened_urls = []

    class FakeResponse:
        def __init__(self, body: bytes, is_video: bool):
            self.body = body
            self.offset = 0
            self.is_video = is_video
            self.entered = False
            self.headers = {"Content-Length": str(len(body))}

        def __enter__(self):
            nonlocal active, max_active
            if self.is_video:
                with lock:
                    active += 1
                    max_active = max(max_active, active)
            self.entered = True
            return self

        def __exit__(self, exc_type, exc, traceback):
            nonlocal active
            if self.is_video and self.entered:
                with lock:
                    active -= 1
            return False

        def read(self, size: int) -> bytes:
            time.sleep(0.02)
            if self.offset >= len(self.body):
                return b""
            chunk = self.body[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

    def fake_urlopen(request):
        opened_urls.append(request.full_url)
        is_video = "/files/" in request.full_url
        return FakeResponse(request.full_url.encode(), is_video)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    download_plan = {
        "dramaId": "drama-1",
        "title": "并发短剧",
        "episodes": [
            {"episodeNo": episode_no, "downloadUrl": f"/files/{episode_no}.mp4"}
            for episode_no in range(1, 9)
        ],
    }

    files = download_episodes(download_plan, tmp_path / "drama-1", "http://server/api")

    assert files == [tmp_path / "drama-1" / f"并发短剧-第{episode_no}集.mp4" for episode_no in range(1, 9)]
    assert max_active == 6
    assert {url for url in opened_urls if "/files/" in url} == {
        f"http://server/files/{episode_no}.mp4" for episode_no in range(1, 9)
    }


def test_episode_video_filename_uses_ai_title_and_episode_number():
    assert (
        episode_video_filename(
            {"title": "原始剧名", "aiTitle": "AI剧名"},
            {"episodeNo": 12},
            1,
        )
        == "AI剧名-第12集.mp4"
    )
