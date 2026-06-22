import os
import pytest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget

from aidrama_desktop.config.settings import API_BASE_URL, Settings
from aidrama_desktop.gui.app import DesktopWindow, LoginPage


def test_desktop_drama_list_path_uses_client_endpoint_without_category_filter():
    path = DesktopWindow.build_drama_list_path(page=2, size=10)

    assert path == "/desktop/dramas?page=2&size=10&sort=updatedAt,desc"


def test_login_page_hides_fixed_service_address(tmp_path):
    QApplication.instance() or QApplication([])
    settings = Settings(
        work_dir=tmp_path / "work",
        browser_profile_dir=tmp_path / "profiles",
        token_file=tmp_path / "token",
    )

    page = LoginPage(settings)
    label_texts = {label.text() for label in page.findChildren(QLabel)}
    input_texts = {editor.text() for editor in page.findChildren(QLineEdit)}

    assert "服务地址" not in label_texts
    assert API_BASE_URL not in input_texts


def test_desktop_drama_list_path_supports_title_keyword_search():
    path = DesktopWindow.build_drama_list_path(page=0, size=10, keyword="神医 太子")

    assert path == "/desktop/dramas?page=0&size=10&sort=updatedAt,desc&keyword=%E7%A5%9E%E5%8C%BB+%E5%A4%AA%E5%AD%90"


def test_desktop_task_history_path_supports_keyword_and_status():
    path = DesktopWindow.build_task_history_path(page=1, size=20, keyword="神医", status="FAILED")

    assert path == "/desktop/tasks?page=1&size=20&sort=createdAt,desc&keyword=%E7%A5%9E%E5%8C%BB&status=FAILED"


def test_desktop_distribution_task_status_label():
    assert DesktopWindow.distribution_task_status_label("FAILED") == "失败"
    assert DesktopWindow.distribution_task_status_label("UPLOADING") == "上传中"


def test_desktop_task_history_chain_summary_pinpoints_failed_step():
    window = DesktopWindow.__new__(DesktopWindow)

    assert window.task_history_chain_summary({"status": "FAILED", "progress": 75}) == "上传失败"
    assert window.task_history_chain_summary({"status": "FAILED", "progress": 10}) == "下载失败"
    assert window.task_history_chain_summary({"status": "SUCCEEDED", "progress": 100}) == "已完成"


def test_desktop_drama_row_values_include_rating_and_hide_status_and_updated_at():
    values = DesktopWindow.drama_row_values(
        {
            "title": "原剧名",
            "aiTitle": "新剧名",
            "summary": "一段简介",
            "rating": 4,
            "categoryIds": ["sci-fi"],
            "categoryNames": ["科幻"],
            "episodes": [{}, {}],
            "status": "READY",
            "createdAt": "2026-06-14T16:42:03Z",
            "updatedAt": "2026-06-15T12:02:48Z",
        }
    )

    assert values == ["新剧名", "一段简介", "4分", "科幻", "2", "-", "-", "2026-06-14 16:42:03"]


def test_desktop_drama_row_values_use_episode_count_summary_without_episodes():
    values = DesktopWindow.drama_row_values(
        {
            "title": "新剧名",
            "summary": "一段简介",
            "rating": 4,
            "categoryNames": ["科幻"],
            "episodeCount": 12,
            "createdAt": "2026-06-14T16:42:03Z",
        }
    )

    assert values[4] == "12"


def test_desktop_drama_row_values_defaults_missing_rating_to_five():
    values = DesktopWindow.drama_row_values(
        {
            "title": "原剧名",
            "summary": "一段简介",
            "categoryNames": ["科幻"],
            "episodes": [],
            "createdAt": "2026-06-14T16:42:03Z",
        }
    )

    assert values[2] == "5分"


def test_drama_download_info_counts_only_completed_episodes(tmp_path):
    window = DesktopWindow.__new__(DesktopWindow)
    window.settings = SimpleNamespace(downloads_dir=tmp_path)
    drama = {
        "id": "drama-1",
        "episodes": [
            {"episodeNo": 1, "size": 10},
            {"episodeNo": 2, "size": 10},
        ],
    }
    target = tmp_path / "drama-1"
    target.mkdir()
    (target / "001.mp4").write_bytes(b"x" * 10)
    (target / "002.mp4").write_bytes(b"x" * 4)

    assert DesktopWindow.drama_download_info(window, drama) == ("下载中", 1, 2)


def test_drama_download_info_marks_all_complete(tmp_path):
    window = DesktopWindow.__new__(DesktopWindow)
    window.settings = SimpleNamespace(downloads_dir=tmp_path)
    drama = {
        "id": "drama-1",
        "episodes": [
            {"episodeNo": 1, "size": 10},
            {"episodeNo": 2, "size": 10},
        ],
    }
    target = tmp_path / "drama-1"
    target.mkdir()
    (target / "001.mp4").write_bytes(b"x" * 10)
    (target / "002.mp4").write_bytes(b"x" * 10)

    assert DesktopWindow.drama_download_info(window, drama) == ("已下载", 2, 2)


def test_drama_download_info_uses_episode_count_summary_without_episodes(tmp_path):
    window = DesktopWindow.__new__(DesktopWindow)
    window.settings = SimpleNamespace(downloads_dir=tmp_path)
    drama = {"id": "drama-1", "episodeCount": 2}
    target = tmp_path / "drama-1"
    target.mkdir()
    (target / "001.mp4").write_bytes(b"x" * 10)
    (target / "002.mp4").write_bytes(b"x" * 10)

    assert DesktopWindow.drama_download_info(window, drama) == ("已下载", 2, 2)


def test_drama_cover_widget_returns_immediately_and_loads_async(monkeypatch):
    app = QApplication.instance() or QApplication([])
    window = DesktopWindow.__new__(DesktopWindow)
    window.cover_cache = {}
    window.cover_loading = {}
    calls = []

    def fail_sync_fetch(*_args, **_kwargs):
        raise AssertionError("cover widget must not fetch synchronously")

    def record_async_load(url, label):
        calls.append((url, label.text()))

    monkeypatch.setattr("aidrama_desktop.gui.app.httpx.get", fail_sync_fetch)
    window.load_cover_async = record_async_load

    label = DesktopWindow.drama_cover_widget(window, "https://example.test/cover.jpg")

    assert app is not None
    assert label.text() == "封面\n加载中"
    assert calls == [("https://example.test/cover.jpg", "封面\n加载中")]


def test_drama_cover_widget_uses_cached_failure_without_async_load():
    app = QApplication.instance() or QApplication([])
    window = DesktopWindow.__new__(DesktopWindow)
    window.cover_cache = {"https://example.test/missing.jpg": None}
    window.cover_loading = {}
    calls = []
    window.load_cover_async = lambda url, label: calls.append((url, label))

    label = DesktopWindow.drama_cover_widget(window, "https://example.test/missing.jpg")

    assert app is not None
    assert label.text() == "封面\n加载失败"
    assert calls == []


def test_drama_cover_widget_uses_local_disk_cache_without_async_load(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = DesktopWindow.__new__(DesktopWindow)
    window.settings = SimpleNamespace(work_dir=tmp_path)
    window.cover_cache = {}
    window.cover_loading = {}
    calls = []
    cover_url = "https://example.test/cover.jpg"
    cache_path = DesktopWindow.drama_cover_cache_path(window, cover_url)
    cache_path.parent.mkdir(parents=True)
    cache_path.write_bytes(b"cached-cover")
    window.load_cover_async = lambda url, label: calls.append((url, label))
    applied = []
    window.apply_drama_cover_bytes = lambda label, content: applied.append(content)

    label = DesktopWindow.drama_cover_widget(window, cover_url)

    assert app is not None
    assert calls == []
    assert applied == [b"cached-cover"]
    assert window.cover_cache[cover_url] == b"cached-cover"
    assert label.property("coverUrl") == cover_url


def test_on_cover_loaded_persists_success_to_local_cache(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = DesktopWindow.__new__(DesktopWindow)
    window.settings = SimpleNamespace(work_dir=tmp_path)
    window.cover_cache = {}
    window.cover_loading = {}
    cover_url = "https://example.test/cover.jpg"
    window.apply_drama_cover_bytes = lambda _label, _content: None

    DesktopWindow.on_cover_loaded(window, (cover_url, b"fresh-cover"))

    assert app is not None
    assert DesktopWindow.drama_cover_cache_path(window, cover_url).read_bytes() == b"fresh-cover"
    assert window.cover_cache[cover_url] == b"fresh-cover"


def test_task_done_can_omit_large_result_from_log():
    window = DesktopWindow.__new__(DesktopWindow)
    logs = []
    payload = {"content": [{"summary": "x" * 1000}], "totalElements": 1}
    handled = []
    window.append_log = logs.append

    DesktopWindow._task_done(window, "加载短剧库", payload, handled.append, log_result=False)

    assert logs == ["完成：加载短剧库"]
    assert handled == [payload]


def test_task_done_summarizes_list_result_in_log():
    window = DesktopWindow.__new__(DesktopWindow)
    logs = []
    window.append_log = logs.append

    DesktopWindow._task_done(window, "刷新媒体号", [{"id": "media-1"}, {"id": "media-2"}], None)

    assert logs == ["完成：刷新媒体号 共 2 条"]


def test_task_done_summarizes_page_result_in_log():
    window = DesktopWindow.__new__(DesktopWindow)
    logs = []
    window.append_log = logs.append

    DesktopWindow._task_done(window, "加载短剧库", {"content": [{"id": "drama-1"}], "totalElements": 131}, None)

    assert logs == ["完成：加载短剧库 共 131 条"]


def test_task_done_can_hide_update_check_payload_from_log():
    window = DesktopWindow.__new__(DesktopWindow)
    logs = []
    payload = ("MAC", {"updateAvailable": False, "downloadUrl": None})
    handled = []
    window.append_log = logs.append

    DesktopWindow._task_done(window, "检查桌面端更新", payload, handled.append, log_result=False)

    assert logs == ["完成：检查桌面端更新"]
    assert handled == [payload]


def test_create_media_account_opens_browser_for_created_account(tmp_path, monkeypatch):
    window = DesktopWindow.__new__(DesktopWindow)
    window.settings = SimpleNamespace(
        device_id="device-1",
        chrome_path=None,
        browser_profile_dir=tmp_path / "profiles",
    )
    cleared = []
    window.media_name_input = SimpleNamespace(text=lambda: "染柒剧作", clear=lambda: cleared.append("name"))
    window.media_external_id_input = SimpleNamespace(text=lambda: "sph-id", clear=lambda: cleared.append("external"))
    window.media_platform_input = SimpleNamespace(currentData=lambda: "WECHAT_VIDEO")
    accepted = []
    loaded = []
    window.media_create_dialog = SimpleNamespace(accept=lambda: accepted.append(True))
    window.load_media_accounts = lambda: loaded.append(True)

    posts = []
    puts = []

    class FakeApi:
        def post(self, path, payload):
            posts.append((path, payload))
            return {
                "id": "media-1",
                "displayName": payload["displayName"],
                "externalAccountId": payload["externalAccountId"],
                "platform": payload["platform"],
            }

        def put(self, path, payload):
            puts.append((path, payload))
            return {"id": "media-1", **payload}

    opened = []

    class FakeChromeController:
        def __init__(self, chrome_path, profile_root):
            self.chrome_path = chrome_path
            self.profile_root = profile_root

        def open_platform_login(self, platform, url, account_id, remote_debugging_port=None):
            opened.append((self.chrome_path, self.profile_root, platform, url, account_id, remote_debugging_port))

        def login_state_ref(self, platform, account_id):
            return str(self.profile_root / platform.lower() / account_id)

    monkeypatch.setattr("aidrama_desktop.gui.app.find_chrome", lambda chrome_path: "/Applications/Chrome")
    monkeypatch.setattr("aidrama_desktop.gui.app.ChromeController", FakeChromeController)
    window.api = lambda: FakeApi()
    window.run_async = lambda _title, task, done=None: done(task()) if done else task()

    DesktopWindow.create_media_account(window)

    assert posts == [
        (
            "/desktop/media-accounts",
            {
                "platform": "WECHAT_VIDEO",
                "displayName": "染柒剧作",
                "externalAccountId": "sph-id",
                "deviceId": "device-1",
            },
        )
    ]
    assert opened == [
        (
            "/Applications/Chrome",
            tmp_path / "profiles",
            "WECHAT_VIDEO",
            "https://channels.weixin.qq.com/platform",
            "sph-id",
            None,
        )
    ]
    assert puts == [
        (
            "/desktop/media-accounts/media-1/login-state",
            {
                "loginStateRef": str(tmp_path / "profiles" / "wechat_video" / "sph-id"),
                "deviceId": "device-1",
                "verified": True,
            },
        )
    ]
    assert accepted == [True]
    assert loaded == [True]
    assert cleared == ["name", "external"]


def test_media_row_values_include_binding_time():
    window = DesktopWindow.__new__(DesktopWindow)
    window.media_categories = [{"code": "urban", "name": "都市"}]

    values = DesktopWindow.media_row_values(
        window,
        {
            "displayName": "主账号",
            "platform": "WECHAT_VIDEO",
            "externalAccountId": "wx-1",
            "status": "ACTIVE",
            "deviceId": "device-1",
            "lastVerifiedAt": "2026-06-15T12:02:48Z",
            "loginStateRef": "profile.json",
        },
        {"dailyLimit": 5, "intervalMinutes": 30, "categoryIds": ["urban"]},
    )

    assert values == [
        "主账号",
        "视频号",
        "wx-1",
        "可用",
        "device-1",
        "2026-06-15 12:02:48",
        "已保存",
        "5",
        "30 分钟",
        "都市",
    ]


def test_media_page_action_labels_only_include_create_and_refresh():
    assert DesktopWindow.media_page_action_labels() == ["新增媒体号", "刷新媒体号"]


def test_media_row_actions_include_browser_and_policy_buttons():
    app = QApplication.instance() or QApplication([])
    window = DesktopWindow.__new__(DesktopWindow)
    window.toggle_media_enabled = lambda _account: None
    window.open_media_policy_dialog = lambda _account: None
    window.open_media_account = lambda _account: None

    widget = DesktopWindow.media_actions_widget(window, {"status": "BINDING"})
    button_texts = [button.text() for button in widget.findChildren(QPushButton)]

    assert app is not None
    assert button_texts == ["暂停", "打开浏览器", "编辑策略"]


def test_save_media_login_state_updates_backend_with_profile_ref(tmp_path, monkeypatch):
    window = DesktopWindow.__new__(DesktopWindow)
    window.settings = SimpleNamespace(
        device_id="device-1",
        chrome_path=None,
        browser_profile_dir=tmp_path / "profiles",
    )
    loaded = []
    window.load_media_accounts = lambda: loaded.append(True)
    puts = []

    class FakeApi:
        def put(self, path, payload):
            puts.append((path, payload))
            return {"id": "media-1"}

    class FakeChromeController:
        def __init__(self, chrome_path, profile_root):
            self.chrome_path = chrome_path
            self.profile_root = profile_root

        def platform_profile_dir(self, platform, account_id):
            return self.profile_root / platform.lower() / account_id

    monkeypatch.setattr("aidrama_desktop.gui.app.find_chrome", lambda chrome_path: "/Applications/Chrome")
    monkeypatch.setattr("aidrama_desktop.gui.app.ChromeController", FakeChromeController)
    window.api = lambda: FakeApi()
    window.run_async = lambda _title, task, done=None: done(task()) if done else task()

    DesktopWindow.save_media_login_state(
        window,
        {"id": "media-1", "platform": "WECHAT_VIDEO", "displayName": "染柒剧作"},
    )

    assert puts == [
        (
            "/desktop/media-accounts/media-1/login-state",
            {
                "loginStateRef": str(tmp_path / "profiles" / "wechat_video" / "media-1"),
                "deviceId": "device-1",
                "verified": True,
            },
        )
    ]
    assert loaded == [True]


def test_open_media_account_opens_browser_and_saves_profile_ref(tmp_path, monkeypatch):
    window = DesktopWindow.__new__(DesktopWindow)
    window.settings = SimpleNamespace(
        device_id="device-1",
        chrome_path=None,
        browser_profile_dir=tmp_path / "profiles",
    )
    opened = []
    puts = []
    saved_profile = tmp_path / "profiles" / "saved-wechat-profile"

    class FakeApi:
        def put(self, path, payload):
            puts.append((path, payload))
            return {"id": "media-1"}

    class FakeChromeController:
        def __init__(self, chrome_path, profile_root):
            self.chrome_path = chrome_path
            self.profile_root = profile_root

        def open_profile(self, profile_dir, url, remote_debugging_port=None):
            opened.append((profile_dir, url, remote_debugging_port))

        def platform_profile_dir(self, platform, account_id):
            return self.profile_root / platform.lower() / account_id

    monkeypatch.setattr("aidrama_desktop.gui.app.find_chrome", lambda chrome_path: "/Applications/Chrome")
    monkeypatch.setattr("aidrama_desktop.gui.app.ChromeController", FakeChromeController)
    results = []
    window.api = lambda: FakeApi()
    window.run_async = lambda _title, task, done=None, **_kwargs: results.append(task())
    account = {
        "id": "media-1",
        "platform": "WECHAT_VIDEO",
        "displayName": "染柒剧作",
        "loginStateRef": str(saved_profile),
    }

    DesktopWindow.open_media_account(window, account)

    assert opened == [(saved_profile, "https://channels.weixin.qq.com/platform", None)]
    assert puts == [
        (
            "/desktop/media-accounts/media-1/login-state",
            {
                "loginStateRef": str(saved_profile),
                "deviceId": "device-1",
                "verified": True,
            },
        )
    ]
    assert results == ["染柒剧作 浏览器已打开，登录信息已保存"]


def test_media_table_keeps_name_column_readable():
    app = QApplication.instance() or QApplication([])
    table = QTableWidget(0, 11)

    DesktopWindow.configure_media_table_columns(table)

    assert app is not None
    assert table.columnWidth(0) >= 160
    assert table.horizontalHeader().sectionResizeMode(0) == QHeaderView.Fixed
    assert all(table.horizontalHeader().sectionResizeMode(column) == QHeaderView.Fixed for column in range(11))


def test_clean_error_message_hides_exception_class_name():
    assert (
        DesktopWindow.clean_error_message(
            "Traceback...\naidrama_desktop.api.client.ApiError: 这部剧已经有分发任务"
        )
        == "这部剧已经有分发任务"
    )


def test_is_drama_prioritized_reads_backend_flag():
    assert DesktopWindow.is_drama_prioritized({"prioritized": True}) is True
    assert DesktopWindow.is_drama_prioritized({"prioritized": False}) is False
    assert DesktopWindow.is_drama_prioritized({}) is False


def test_auto_tasks_require_active_media_account_with_login_state():
    assert DesktopWindow.auto_task_block_reason([]) == "请先新增媒体号并完成登录。"
    assert (
        DesktopWindow.auto_task_block_reason(
            [{"status": "ACTIVE", "loginStateRef": "", "displayName": "主视频号"}]
        )
        == "媒体号未保存登录信息，请先完成媒体号登录。"
    )
    assert (
        DesktopWindow.auto_task_block_reason(
            [{"status": "EXPIRED", "loginStateRef": "profile", "displayName": "主视频号"}]
        )
        == "没有可用的媒体号，请先确认媒体号状态为可用。"
    )
    assert (
        DesktopWindow.auto_task_block_reason(
            [{"status": "PAUSED", "loginStateRef": "profile", "displayName": "主视频号"}]
        )
        == "没有可用的媒体号，请先确认媒体号状态为可用。"
    )
    assert (
        DesktopWindow.auto_task_block_reason(
            [
                {
                    "status": "ACTIVE",
                    "loginStateRef": "profile",
                    "displayName": "主视频号",
                    "distributionPolicy": {"enabled": False},
                }
            ]
        )
        == "没有可用的媒体号，请先确认媒体号状态为可用。"
    )
    assert (
        DesktopWindow.auto_task_block_reason(
            [{"status": "ACTIVE", "loginStateRef": "profile", "displayName": "主视频号"}]
        )
        is None
    )


def test_task_progress_displays_current_media_account_name():
    app = QApplication.instance() or QApplication([])
    window = DesktopWindow.__new__(DesktopWindow)
    window.auto_task_enabled = False
    window.media_accounts = [{"id": "media-1", "displayName": "染柒剧作"}]
    window.auto_task_state = QLabel()
    window.current_task_label = QLabel()
    window.current_media_account_label = QLabel()
    window.task_stage_label = QLabel()
    window.task_error_label = QLabel()

    DesktopWindow.update_task_progress(
        window,
        "任务已领取",
        "task-1",
        {"mediaAccountId": "media-1"},
    )

    assert app is not None
    assert window.current_task_label.text() == "当前任务：task-1"
    assert window.current_media_account_label.text() == "当前媒体号：染柒剧作"
