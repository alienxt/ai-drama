from __future__ import annotations

import faulthandler
import json
import re
import sys
import threading
import traceback
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import httpx
from PySide6.QtCore import QDate, QObject, QRectF, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QBrush, QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from aidrama_desktop.api.client import ApiClient
from aidrama_desktop.api.diagnostics import diagnose_server, write_diagnostic_report
from aidrama_desktop import __version__
from aidrama_desktop.auth.remembered_login import RememberedLoginStore
from aidrama_desktop.auth.token_store import TokenStore
from aidrama_desktop.browser.chrome import ChromeController, find_chrome
from aidrama_desktop.config.settings import (
    DEFAULT_JIANYING_PROJECT_STRATEGY,
    DEFAULT_SUBTITLE_PROVIDER,
    JIANYING_PROJECT_STRATEGY_PREFERENCES,
    SUBTITLE_PROVIDER_FASTER_WHISPER,
    SUBTITLE_PROVIDER_OPENAI_WHISPER,
    Settings,
    jianying_project_strategy_preference_label,
    load_settings,
    normalize_jianying_project_strategy_preference,
    normalize_subtitle_provider,
    resolve_faster_whisper_python_path,
    resolve_ffmpeg_path,
    save_tool_path_config,
)
from aidrama_desktop.contracts import (
    ContractConfigStore,
    CONTRACT_TEMPLATE_TYPES,
    ContractRenderInput,
    build_contract_output_path,
    build_contract_template_download_path,
    contract_party_key,
    contract_template_key,
    convert_contract_docx_images,
    copy_contract_template,
    generate_agreement_number,
    generate_contract_start_date,
    merge_pngs_vertically,
    normalize_contract_docx_for_rendering,
    required_contract_party_fields,
    required_contract_template_types,
    render_contract_docx,
    safe_contract_filename,
    should_normalize_contract_for_rendering,
)
from aidrama_desktop.gui.state import AppStatus, SettingsRow, desktop_nav_items, settings_rows, update_settings
from aidrama_desktop.jianying import JianyingProjectGenerator
from aidrama_desktop.local_agent import create_local_agent_server
from aidrama_desktop.platforms.registry import get_publisher
from aidrama_desktop.storyboard import StoryboardGenerator
from aidrama_desktop.tasks.runner import (
    JIANYING_PROJECT_PREVIEW_DIRNAME,
    JIANYING_PROJECT_STRATEGIES,
    JIANYING_PROJECT_STRATEGY_LABELS,
    VIDEO_REASSEMBLY_DIRNAME,
    TaskRunner,
    drama_directory_name,
    read_download_episode_manifest,
)
from aidrama_desktop.tasks.cache_cleanup import (
    UploadCacheCleanupResult,
    cleanup_uploaded_drama_cache as cleanup_uploaded_drama_cache_dirs,
)
from aidrama_desktop.update import UpdateInfo, detect_platform, download_installer, open_installer
from aidrama_desktop.video.ffmpeg import FfmpegProcessor
from aidrama_desktop.video.reassembly import (
    VIDEO_REASSEMBLY_METHOD_NONE,
    VIDEO_REASSEMBLY_METHOD_REASSEMBLE,
    VideoReassemblyConfig,
    VideoReassemblyConfigStore,
)


CHINA_TIMEZONE = timezone(timedelta(hours=8))
LOG_TIME_PREFIX_PATTERN = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\s")
LOG_MAX_BLOCK_COUNT = 5_000
_CRASH_LOG_FILE = None


class WorkerSignals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    def __init__(self, task: Callable[[], Any]):
        super().__init__()
        self.setAutoDelete(False)
        self.task = task
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            self.signals.done.emit(self.task())
        except Exception:  # noqa: BLE001
            self.signals.failed.emit(traceback.format_exc())


class AgentController(QObject):
    log = Signal(str)
    changed = Signal(bool)

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self._server = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self) -> None:
        if self.running:
            self.log.emit("本地服务已在运行。")
            return

        def open_media(platform: str, account_id: str | None = None) -> None:
            chrome = ChromeController(find_chrome(self.settings.chrome_path), self.settings.browser_profile_dir)
            if account_id:
                get_publisher(platform, chrome, account_id).open_login()
            else:
                get_publisher(platform, chrome).open_login()

        self._server = create_local_agent_server(self.settings.local_agent_port, open_media)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        self.log.emit(f"本地服务已启动：http://127.0.0.1:{self.settings.local_agent_port}")
        self.changed.emit(True)

    def stop(self) -> None:
        if not self._server:
            self.log.emit("本地服务未运行。")
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._thread = None
        self.log.emit("本地服务已停止。")
        self.changed.emit(False)


class LoginPage(QWidget):
    logged_in = Signal()

    def __init__(self, settings: Settings):
        super().__init__()
        self.setObjectName("loginRoot")
        self.settings = settings
        self.username_input = QLineEdit("test")
        self.username_input.setObjectName("loginInput")
        self.username_input.setPlaceholderText("桌面端用户名")
        self.password_input = QLineEdit()
        self.password_input.setObjectName("loginInput")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("请输入密码")
        self.remember_store = RememberedLoginStore(settings.remembered_login_file)
        self.remember_checkbox = QCheckBox("记住密码 1 天")
        self.remember_checkbox.setObjectName("rememberCheck")
        remembered = self.remember_store.get()
        if remembered:
            username, password = remembered
            self.username_input.setText(username)
            self.password_input.setText(password)
            self.remember_checkbox.setChecked(True)
        self.login_button = QPushButton("登录桌面端")
        self.login_button.setObjectName("primaryButton")
        self.login_button.clicked.connect(self._login)
        self.diagnose_button = QPushButton("网络诊断")
        self.diagnose_button.setObjectName("secondaryButton")
        self.diagnose_button.clicked.connect(self._diagnose_network)
        self.active_workers: list[Worker] = []

        panel = QFrame()
        panel.setObjectName("loginPanel")
        panel_layout = QHBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        brand = QFrame()
        brand.setObjectName("loginBrandPanel")
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(34, 34, 30, 34)
        brand_layout.setSpacing(14)

        icon_label = QLabel()
        icon_label.setObjectName("loginLogo")
        icon_label.setPixmap(app_icon().pixmap(42, 42))
        brand_title = QLabel("AI Drama\nDesktop")
        brand_title.setObjectName("loginBrandTitle")
        brand_subtitle = QLabel("短剧分发平台")
        brand_subtitle.setObjectName("loginBrandSubtitle")
        brand_hint = QLabel("本机设备已用于账号绑定校验")
        brand_hint.setObjectName("loginBrandHint")
        device_label = QLabel(self._short_device_label(settings.device_id))
        device_label.setObjectName("deviceBadge")

        brand_layout.addWidget(icon_label)
        brand_layout.addSpacing(8)
        brand_layout.addWidget(brand_title)
        brand_layout.addWidget(brand_subtitle)
        brand_layout.addStretch(1)
        brand_layout.addWidget(brand_hint)
        brand_layout.addWidget(device_label)

        form_panel = QFrame()
        form_panel.setObjectName("loginFormPanel")
        form_layout = QVBoxLayout(form_panel)
        form_layout.setContentsMargins(42, 36, 42, 34)
        form_layout.setSpacing(10)

        title = QLabel("登录桌面端")
        title.setObjectName("loginTitle")

        form_layout.addWidget(title)
        form_layout.addSpacing(18)
        form_layout.addWidget(self._field_row("用户名", self.username_input))
        form_layout.addWidget(self._field_row("密码", self.password_input))
        form_layout.addWidget(self.remember_checkbox)
        form_layout.addSpacing(8)
        form_layout.addWidget(self.login_button)
        form_layout.addWidget(self.diagnose_button)
        form_layout.addStretch(1)

        panel_layout.addWidget(brand)
        panel_layout.addWidget(form_panel, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.addStretch(1)
        layout.addWidget(panel, alignment=Qt.AlignCenter)
        layout.addStretch(1)

    @staticmethod
    def _field_row(label_text: str, editor: QLineEdit) -> QWidget:
        field = QWidget()
        field.setObjectName("loginField")
        field.setFixedHeight(88)
        row = QVBoxLayout(field)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.setAlignment(Qt.AlignTop)
        label = QLabel(label_text)
        label.setObjectName("fieldLabel")
        label.setFixedHeight(20)
        editor.setFixedHeight(44)
        row.addWidget(label)
        row.addWidget(editor)
        return field

    @staticmethod
    def _short_device_label(device_id: str) -> str:
        if len(device_id) <= 14:
            return f"设备号 {device_id}"
        return f"设备号 {device_id[:8]}...{device_id[-6:]}"

    def _login(self) -> None:
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username or not password:
            QMessageBox.warning(self, "登录失败", "请填写用户名和密码。")
            return
        settings = update_settings(self.settings)
        try:
            ApiClient(settings.server_url, TokenStore(settings.token_file)).login(username, password, settings.device_id)
        except Exception as exception:  # noqa: BLE001
            QMessageBox.critical(self, "登录失败", str(exception))
            return
        if self.remember_checkbox.isChecked():
            self.remember_store.set(username, password)
        else:
            self.remember_store.clear()
        self.logged_in.emit()

    def _diagnose_network(self) -> None:
        settings = update_settings(self.settings)
        self.diagnose_button.setEnabled(False)
        self.diagnose_button.setText("诊断中...")

        def task() -> tuple[str, str]:
            report = diagnose_server(settings.server_url)
            report_path = write_diagnostic_report(report, settings.work_dir)
            return report.to_text(), str(report_path)

        worker = Worker(task)
        self.active_workers.append(worker)
        worker.signals.done.connect(lambda result, item=worker: self._show_diagnostic_report(item, result))
        worker.signals.failed.connect(lambda error, item=worker: self._show_diagnostic_error(item, error))
        QThreadPool.globalInstance().start(worker)

    def _finish_diagnostic_worker(self, worker: Worker) -> None:
        if worker in self.active_workers:
            self.active_workers.remove(worker)
        self.diagnose_button.setEnabled(True)
        self.diagnose_button.setText("网络诊断")

    def _show_diagnostic_report(self, worker: Worker, result: object) -> None:
        self._finish_diagnostic_worker(worker)
        report_text, report_path = result if isinstance(result, tuple) else ("", "")
        message = QMessageBox(self)
        message.setWindowTitle("网络诊断")
        message.setIcon(QMessageBox.Information)
        message.setText("网络诊断已完成。")
        message.setInformativeText(f"报告已保存到：{report_path}")
        message.setDetailedText(str(report_text))
        message.exec()

    def _show_diagnostic_error(self, worker: Worker, error: str) -> None:
        self._finish_diagnostic_worker(worker)
        message = QMessageBox(self)
        message.setWindowTitle("网络诊断失败")
        message.setIcon(QMessageBox.Critical)
        message.setText("网络诊断没有完成。")
        message.setDetailedText(error)
        message.exec()


class DesktopWindow(QMainWindow):
    task_progress_requested = Signal(str, object, object)
    worker_done_requested = Signal(object)
    worker_failed_requested = Signal(object)

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.token_store = TokenStore(settings.token_file)
        self.token_store.clear()
        self.current_username = ""
        self.update_check_manual = False
        self.thread_pool = QThreadPool.globalInstance()
        self.agent = AgentController(settings)
        self.agent.log.connect(self.append_log)
        self.agent.changed.connect(lambda _: self.refresh_status())
        self.task_progress_requested.connect(self._apply_task_progress)
        self.worker_done_requested.connect(self._handle_worker_done_requested)
        self.worker_failed_requested.connect(self._handle_worker_failed_requested)
        self._task_progress_signal_ready = True
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.document().setMaximumBlockCount(LOG_MAX_BLOCK_COUNT)
        self.media_accounts: list[dict[str, Any]] = []
        self.media_categories: list[dict[str, Any]] = []
        self.current_drama_rows: list[dict[str, Any]] = []
        self.drama_page = 0
        self.drama_size = 10
        self.drama_total_pages = 1
        self.drama_total_elements = 0
        self.cover_cache: dict[str, bytes | None] = {}
        self.cover_loading: dict[str, list[QLabel]] = {}
        self.active_workers: list[Worker] = []
        self.contract_drama_options: list[dict[str, Any]] = []
        self.auto_task_enabled = False
        self.auto_task_busy = False
        self.manual_publish_busy = False
        self.jianying_preview_busy = False
        self.current_task_id: str | None = None
        self.current_task_snapshot: dict[str, Any] | None = None
        self.current_media_account_id: str | None = None
        self.current_media_account_snapshot: dict[str, Any] | None = None
        self.current_drama_title: str | None = None
        self.task_paused = False
        self.resume_auto_after_pause = False
        self.task_history_rows: list[dict[str, Any]] = []
        self.task_history_page = 0
        self.task_history_size = 10
        self.task_history_total_pages = 1
        self.task_history_total_elements = 0
        self.last_task_error_message: str | None = None
        self.last_auto_error_popup_message: str | None = None
        self.task_cancel_event = threading.Event()
        self.task_pause_event = threading.Event()
        self.task_skip_event = threading.Event()
        self.contract_store = ContractConfigStore(settings.config_dir / "contract-templates.json")
        self.contract_templates = self.contract_store.load()
        self.video_reassembly_store = VideoReassemblyConfigStore(settings.config_dir / "video-processing.json")
        self.video_reassembly_config = self.video_reassembly_store.load()
        self.last_contract_path: Path | None = None
        self.last_contract_paths: list[Path] = []
        self.upload_cache_cleanup_busy = False
        self.auto_task_timer = QTimer(self)
        self.auto_task_timer.setInterval(30_000)
        self.auto_task_timer.timeout.connect(self.run_auto_task_cycle)
        self.list_refresh_timer = QTimer(self)
        self.list_refresh_timer.setInterval(30_000)
        self.list_refresh_timer.timeout.connect(self.refresh_visible_list)
        self.upload_cache_cleanup_timer = QTimer(self)
        self.upload_cache_cleanup_timer.setInterval(60 * 60 * 1000)
        self.upload_cache_cleanup_timer.timeout.connect(self.run_scheduled_upload_cache_cleanup)

        self.setWindowTitle(f"AI Drama Desktop {__version__}")
        self.resize(1120, 720)
        self.setMinimumSize(980, 640)
        self.stack = QStackedWidget()
        self.login_page = LoginPage(settings)
        self.login_page.logged_in.connect(self.on_logged_in)
        self.main_page = self._build_main_page()
        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.main_page)
        self.setCentralWidget(self.stack)
        self._build_menu()
        self.refresh_status()

    def _build_menu(self) -> None:
        app_menu = self.menuBar().addMenu("账户")
        logout_action = QAction("退出登录", self)
        logout_action.triggered.connect(self.logout)
        app_menu.addAction(logout_action)
        quit_action = QAction("退出应用", self)
        quit_action.triggered.connect(self.quit_app)
        app_menu.addAction(quit_action)

        service_menu = self.menuBar().addMenu("服务")
        service_menu.addAction("检查更新", lambda: self.check_for_updates(manual=True))
        service_menu.addAction("打开视频号", lambda: self.open_platform("WECHAT_VIDEO"))
        service_menu.addAction("发送心跳", self.heartbeat)

        self.status_disclaimer_label = QLabel(self.status_bar_disclaimer_text())
        self.status_disclaimer_label.setAlignment(Qt.AlignCenter)
        self.statusBar().addPermanentWidget(self.status_disclaimer_label, 1)
        self.statusBar().showMessage("就绪")

    def _build_main_page(self) -> QWidget:
        page = QWidget()
        page.setObjectName("appRoot")
        shell = QHBoxLayout(page)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 18, 14, 14)
        sidebar_layout.setSpacing(14)
        brand_row = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(app_icon().pixmap(34, 34))
        brand_text = QLabel("AI Drama Desktop")
        brand_text.setObjectName("brandTitle")
        brand_row.addWidget(icon_label)
        brand_row.addWidget(brand_text, 1)
        sidebar_layout.addLayout(brand_row)
        self.nav = QListWidget()
        self.nav.setObjectName("navList")
        self.nav.setSpacing(2)
        self.nav.setIconSize(QSize(18, 18))
        for item in desktop_nav_items():
            row = QListWidgetItem(item.title)
            row.setIcon(self.nav_icon(item.key))
            row.setData(Qt.UserRole, item.key)
            self.nav.addItem(row)
        sidebar_layout.addWidget(self.nav, 1)
        account_panel = QFrame()
        account_panel.setObjectName("sidebarAccount")
        account_layout = QVBoxLayout(account_panel)
        account_layout.setContentsMargins(12, 12, 12, 12)
        account_layout.setSpacing(8)
        self.current_username_label = QLabel("当前登录：未登录")
        self.current_username_label.setObjectName("accountHint")
        self.current_username_label.setWordWrap(True)
        logout_button = QPushButton("退出登录")
        logout_button.setObjectName("sidebarDangerButton")
        logout_button.clicked.connect(self.logout)
        quit_button = QPushButton("退出应用")
        quit_button.setObjectName("sidebarGhostButton")
        quit_button.clicked.connect(self.quit_app)
        account_layout.addWidget(self.current_username_label)
        account_layout.addWidget(logout_button)
        account_layout.addWidget(quit_button)
        sidebar_layout.addWidget(account_panel)

        content = QFrame()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 28, 24)
        content_layout.setSpacing(18)
        header = QHBoxLayout()
        header_text = QVBoxLayout()
        self.header_title = QLabel("短剧库")
        self.header_title.setObjectName("pageTitle")
        self.header_subtitle = QLabel("可分发短剧列表，默认展示近 7 天更新内容")
        self.header_subtitle.setObjectName("mutedText")
        header_text.addWidget(self.header_title)
        header_text.addWidget(self.header_subtitle)
        header.addLayout(header_text, 1)
        content_layout.addLayout(header)

        self.pages = QStackedWidget()
        self.pages.setObjectName("pageStack")
        self.pages.addWidget(self._dramas_page())
        self.pages.addWidget(self._media_page())
        self.pages.addWidget(self._contracts_page())
        self.pages.addWidget(self._tasks_page())
        self.pages.addWidget(self._settings_page())
        self.pages.addWidget(self._logs_page())
        content_layout.addWidget(self.pages, 1)

        shell.addWidget(sidebar)
        shell.addWidget(content, 1)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self.show_page)
        return page

    def nav_icon(self, key: str) -> QIcon:
        if key in {"contracts", "tasks", "settings"}:
            return self.colored_nav_icon(key)
        icons = {
            "dramas": QStyle.StandardPixmap.SP_DirHomeIcon,
            "media": QStyle.StandardPixmap.SP_DriveNetIcon,
            "logs": QStyle.StandardPixmap.SP_FileDialogInfoView,
        }
        return self.style().standardIcon(icons.get(key, QStyle.StandardPixmap.SP_FileIcon))

    @staticmethod
    def colored_nav_icon(key: str) -> QIcon:
        pixmap = QPixmap(22, 22)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        if key == "contracts":
            painter.setPen(QPen(QColor("#2563eb"), 1.6))
            painter.setBrush(QBrush(QColor("#dbeafe")))
            painter.drawRoundedRect(4, 2, 12, 17, 2, 2)
            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.drawRect(7, 7, 6, 1)
            painter.drawRect(7, 11, 6, 1)
            painter.setPen(QPen(QColor("#dc2626"), 1.5))
            painter.setBrush(QBrush(QColor("#fee2e2")))
            painter.drawEllipse(QRectF(12, 12, 7, 7))
        elif key == "tasks":
            painter.setPen(QPen(QColor("#0f766e"), 1.8))
            painter.setBrush(QBrush(QColor("#ccfbf1")))
            painter.drawRoundedRect(3, 3, 16, 16, 4, 4)
            painter.setPen(QPen(QColor("#0f766e"), 1.7))
            for y in (8, 13):
                painter.drawLine(8, y, 16, y)
                painter.drawEllipse(QRectF(5, y - 1.5, 3, 3))
        elif key == "settings":
            painter.setPen(QPen(QColor("#7c3aed"), 1.8))
            painter.setBrush(QBrush(QColor("#ede9fe")))
            painter.drawEllipse(QRectF(5, 5, 12, 12))
            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.drawEllipse(QRectF(9, 9, 4, 4))
            painter.setPen(QPen(QColor("#7c3aed"), 1.6))
            painter.drawLine(11, 1, 11, 5)
            painter.drawLine(11, 17, 11, 21)
            painter.drawLine(1, 11, 5, 11)
            painter.drawLine(17, 11, 21, 11)
        painter.end()
        return QIcon(pixmap)

    def _dramas_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        list_panel, list_layout = self._panel("短剧列表")
        filters = QHBoxLayout()
        filters.addWidget(QLabel("剧名"))
        self.drama_keyword_input = QLineEdit()
        self.drama_keyword_input.setPlaceholderText("搜索剧名")
        self.drama_keyword_input.setFixedWidth(220)
        self.drama_keyword_input.returnPressed.connect(lambda: self.load_dramas(page=0))
        filters.addWidget(self.drama_keyword_input)
        search_button = QPushButton("搜索")
        search_button.clicked.connect(lambda: self.load_dramas(page=0))
        filters.addWidget(search_button)
        clear_search_button = QPushButton("清空")
        clear_search_button.clicked.connect(self.clear_drama_keyword)
        filters.addWidget(clear_search_button)
        filters.addWidget(QLabel("下载状态"))
        self.drama_download_filter = QComboBox()
        self.drama_download_filter.addItem("全部", "ALL")
        self.drama_download_filter.addItem("已下载", "已下载")
        self.drama_download_filter.addItem("下载中", "下载中")
        self.drama_download_filter.addItem("未下载", "未下载")
        self.drama_download_filter.addItem("已优先", "PRIORITIZED")
        self.drama_download_filter.currentIndexChanged.connect(lambda: self.load_dramas(page=0))
        filters.addWidget(self.drama_download_filter)
        filters.addStretch(1)
        list_layout.addLayout(filters)

        self.drama_table = QTableWidget(0, 13)
        self.drama_table.setHorizontalHeaderLabels(["封面", "短剧名称", "剧源", "AI简介", "评分", "分类", "集数", "成本金额", "素材状态", "下载状态", "已下载集数", "上架时间", "操作"])
        self.align_table_header_left(self.drama_table)
        self.drama_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.drama_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.drama_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(9, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(10, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(11, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(12, QHeaderView.Fixed)
        self.drama_table.setColumnWidth(0, 82)
        self.drama_table.setColumnWidth(2, 100)
        self.drama_table.setColumnWidth(4, 64)
        self.drama_table.setColumnWidth(5, 120)
        self.drama_table.setColumnWidth(6, 70)
        self.drama_table.setColumnWidth(7, 90)
        self.drama_table.setColumnWidth(8, 110)
        self.drama_table.setColumnWidth(9, 110)
        self.drama_table.setColumnWidth(10, 110)
        self.drama_table.setColumnWidth(11, 165)
        self.drama_table.setColumnWidth(12, 170)
        self.drama_table.verticalHeader().setVisible(False)
        self.drama_table.setAlternatingRowColors(True)
        self.drama_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.drama_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.drama_table.setWordWrap(True)
        self.drama_table.cellDoubleClicked.connect(self.show_drama_detail)
        pager = QHBoxLayout()
        self.drama_page_label = QLabel("共 0 条")
        previous_page = QPushButton("上一页")
        next_page = QPushButton("下一页")
        previous_page.clicked.connect(lambda: self.load_dramas(page=max(self.drama_page - 1, 0)))
        next_page.clicked.connect(lambda: self.load_dramas(page=min(self.drama_page + 1, max(self.drama_total_pages - 1, 0))))
        pager.addWidget(self.drama_page_label)
        pager.addStretch(1)
        pager.addWidget(previous_page)
        pager.addWidget(next_page)
        list_layout.addWidget(self.drama_table, 1)
        list_layout.addLayout(pager)

        layout.addWidget(list_panel, 1)
        return page

    def _panel(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        panel = QFrame()
        panel.setObjectName("panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 18)
        panel_layout.setSpacing(14)
        if title:
            title_label = QLabel(title)
            title_label.setObjectName("panelTitle")
            panel_layout.addWidget(title_label)
        return panel, panel_layout

    def _metric_card(self, grid: QGridLayout, row: int, column: int, title: str, value: str) -> QLabel:
        card = QFrame()
        card.setObjectName("metricCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        value_label.setWordWrap(True)
        card_layout.addWidget(title_label)
        card_layout.addWidget(value_label)
        grid.addWidget(card, row, column)
        return value_label

    def _media_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        actions = QHBoxLayout()
        create_media = QPushButton(self.media_page_action_labels()[0])
        refresh = QPushButton(self.media_page_action_labels()[1])
        create_media.clicked.connect(self.open_create_media_dialog)
        refresh.clicked.connect(self.load_media_accounts)
        actions.addWidget(create_media)
        actions.addWidget(refresh)
        actions.addStretch(1)
        self.media_table = QTableWidget(0, 11)
        self.media_table.setHorizontalHeaderLabels(
            [
                "名称",
                "平台",
                "媒体号 ID",
                "状态",
                "绑定设备",
                "绑定时间",
                "登录态",
                "每日上限（条）",
                "处理间隔（分钟）",
                "分类",
                "操作",
            ]
        )
        self.align_table_header_left(self.media_table)
        self.configure_media_table_columns(self.media_table)
        self.media_table.verticalHeader().setVisible(False)
        self.media_table.setAlternatingRowColors(True)
        self.media_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.media_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.media_table.setWordWrap(False)
        panel, panel_layout = self._panel("媒体号列表")
        panel_layout.addLayout(actions)
        panel_layout.addWidget(self.media_table)
        layout.addWidget(panel, 1)
        self.media_create_dialog = self._build_media_create_dialog()
        return page

    @staticmethod
    def media_page_action_labels() -> list[str]:
        return ["新增媒体号", "刷新媒体号"]

    @staticmethod
    def configure_media_table_columns(table: QTableWidget) -> None:
        widths = [160, 90, 170, 86, 190, 165, 88, 105, 130, 150, 250]
        for column, width in enumerate(widths):
            table.horizontalHeader().setSectionResizeMode(column, QHeaderView.Fixed)
            table.setColumnWidth(column, width)

    def _build_media_create_dialog(self) -> QDialog:
        dialog = QDialog(self)
        dialog.setWindowTitle("新增媒体号")
        dialog.setModal(True)
        dialog.setMinimumWidth(440)
        dialog_layout = QVBoxLayout(dialog)
        dialog_layout.setContentsMargins(18, 18, 18, 18)
        dialog_layout.setSpacing(12)

        hint = QLabel("创建后会自动打开独立浏览器窗口；登录信息会保存到该媒体号的独立浏览器目录。")
        hint.setObjectName("mutedText")
        hint.setWordWrap(True)
        dialog_layout.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        self.media_platform_input = QComboBox()
        for value, label in self.media_platform_options():
            self.media_platform_input.addItem(label, value)
        self.media_name_input = QLineEdit()
        self.media_name_input.setPlaceholderText("例如：主账号")
        self.media_external_id_input = QLineEdit()
        self.media_external_id_input.setPlaceholderText("视频号 ID")
        form.addRow("平台", self.media_platform_input)
        form.addRow("名称", self.media_name_input)
        form.addRow("平台侧账号 ID", self.media_external_id_input)
        dialog_layout.addLayout(form)

        self.media_platform_input.currentIndexChanged.connect(self.update_media_create_fields)
        self.update_media_create_fields()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("新增并打开浏览器")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.create_media_account)
        buttons.rejected.connect(dialog.reject)
        dialog_layout.addWidget(buttons)
        return dialog

    def _contracts_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        template_panel, template_layout = self._panel("")
        template_header = QHBoxLayout()
        template_title = QLabel("合同模版")
        template_title.setObjectName("panelTitle")
        placeholder_help = QPushButton("?")
        placeholder_help.setObjectName("helpButton")
        placeholder_help.setFixedSize(24, 24)
        placeholder_help.clicked.connect(self.show_contract_placeholder_help)
        template_header.addWidget(template_title)
        template_header.addWidget(placeholder_help)
        template_header.addStretch(1)

        type_row = QHBoxLayout()
        self.contract_platform_input = QComboBox()
        self.contract_platform_input.addItem("视频号", "WECHAT_VIDEO")
        self.contract_platform_input.addItem("TikTok", "TIKTOK")
        self.contract_platform_input.setMinimumHeight(34)
        self.contract_platform_input.setMinimumWidth(140)
        self.contract_platform_input.setMaximumWidth(200)
        self.contract_platform_input.currentIndexChanged.connect(self.load_selected_contract_template)
        type_row.addWidget(QLabel("媒体号类型"))
        type_row.addWidget(self.contract_platform_input)
        type_row.addStretch(1)

        self.contract_buyer_input = QLineEdit()
        self.contract_buyer_input.setPlaceholderText("请输入买方/甲方")
        self.contract_buyer_input.setMinimumHeight(34)
        self.contract_buyer_input.textChanged.connect(self.update_contract_generate_button)
        self.contract_buyer_input.editingFinished.connect(self.save_contract_party_config)
        self.contract_seller_input = QLineEdit()
        self.contract_seller_input.setPlaceholderText("请输入卖方/乙方")
        self.contract_seller_input.setMinimumHeight(34)
        self.contract_seller_input.textChanged.connect(self.update_contract_generate_button)
        self.contract_seller_input.editingFinished.connect(self.save_contract_party_config)
        self.contract_party_widget = QWidget()
        party_row = QHBoxLayout(self.contract_party_widget)
        party_row.setContentsMargins(0, 0, 0, 0)
        party_row.setSpacing(8)
        party_row.addWidget(QLabel("买方/甲方"))
        party_row.addWidget(self.contract_buyer_input, 1)
        party_row.addWidget(QLabel("卖方/乙方"))
        party_row.addWidget(self.contract_seller_input, 1)

        self.contract_template_path_inputs: dict[str, QLineEdit] = {}
        self.contract_template_label_widgets: dict[str, QLabel] = {}
        self.contract_template_row_widgets: dict[str, QWidget] = {}
        self.contract_template_rows_layout = QVBoxLayout()
        self.contract_template_rows_layout.setSpacing(8)
        for contract_type in CONTRACT_TEMPLATE_TYPES:
            row_widget = QWidget()
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            path_input = QLineEdit()
            path_input.setReadOnly(True)
            label_widget = QLabel(self.contract_type_name(contract_type))
            choose_template = QPushButton("选择")
            choose_template.clicked.connect(lambda _checked=False, key=contract_type: self.choose_contract_template(key))
            download_template = QPushButton("下载系统模版")
            download_template.clicked.connect(lambda _checked=False, key=contract_type: self.download_contract_template(key))
            open_template = QPushButton("打开")
            open_template.clicked.connect(lambda _checked=False, key=contract_type: self.open_contract_template(key))
            clear_template = QPushButton("清空")
            clear_template.clicked.connect(lambda _checked=False, key=contract_type: self.clear_contract_template(key))
            row.addWidget(label_widget)
            row.addWidget(path_input, 1)
            row.addWidget(download_template)
            row.addWidget(choose_template)
            row.addWidget(open_template)
            row.addWidget(clear_template)
            self.contract_template_path_inputs[contract_type] = path_input
            self.contract_template_label_widgets[contract_type] = label_widget
            self.contract_template_row_widgets[contract_type] = row_widget
            self.contract_template_rows_layout.addWidget(row_widget)

        template_note = QLabel(
            "1. 下载并打开系统模版，将主体的盖章和法人签名（透明底图片），添加到指定的位置上；\n"
            "2. 点击“选择”回传整理后的 .docx 模版后，才可以生成合同。"
        )
        template_note.setObjectName("mutedText")
        template_note.setWordWrap(True)
        template_layout.addLayout(template_header)
        template_layout.addLayout(type_row)
        template_layout.addWidget(template_note)
        template_layout.addWidget(self.contract_party_widget)
        template_layout.addLayout(self.contract_template_rows_layout)
        template_layout.addStretch(1)

        preview_panel, preview_layout = self._panel("测试生成")
        form = QGridLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.contract_drama_input = QComboBox()
        self.contract_drama_input.setEditable(True)
        self.contract_drama_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.contract_drama_input.setMaxVisibleItems(20)
        self.contract_drama_input.setMinimumHeight(36)
        self.contract_drama_input.addItem("正在加载短剧库...", None)
        completer = self.contract_drama_input.completer()
        if completer:
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        line_editor = self.contract_drama_input.lineEdit()
        if line_editor:
            line_editor.editingFinished.connect(self.on_contract_drama_selected)
        self.contract_drama_input.currentIndexChanged.connect(self.on_contract_drama_selected)
        self.contract_episode_input = QLineEdit("0")
        self.contract_episode_minutes_input = QLineEdit("0")
        self.contract_price_input = QLineEdit("0")
        self.contract_date_input = QDateEdit()
        self.contract_date_input.setCalendarPopup(True)
        self.contract_date_input.setDisplayFormat("yyyy-MM-dd")
        self.contract_date_input.setDate(QDate.currentDate().addDays(-1))
        self._add_contract_form_field(form, 0, 0, "剧名", self.contract_drama_input, column_span=2)
        self._add_contract_form_field(form, 0, 2, "剧集", self.contract_episode_input)
        self._add_contract_form_field(form, 0, 3, "总时长（分钟）", self.contract_episode_minutes_input)
        self._add_contract_form_field(form, 0, 4, "价格（万）", self.contract_price_input)
        self._add_contract_form_field(form, 0, 5, "签署日期", self.contract_date_input)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(2, 1)
        form.setColumnStretch(3, 1)
        form.setColumnStretch(4, 1)
        form.setColumnStretch(5, 1)
        actions = QHBoxLayout()
        self.contract_generate_button = QPushButton("生成合同")
        self.contract_generate_button.clicked.connect(self.generate_contract)
        self.contract_generate_images_button = QPushButton("生成图片")
        self.contract_generate_images_button.setEnabled(False)
        self.contract_generate_images_button.clicked.connect(self.generate_last_contract_images)
        actions.addWidget(self.contract_generate_button)
        actions.addWidget(self.contract_generate_images_button)
        actions.addStretch(1)
        self.contract_preview = QTextEdit()
        self.contract_preview.setReadOnly(True)
        self.contract_preview.setMinimumHeight(300)
        self.generated_contract_actions_layout = QVBoxLayout()
        self.generated_contract_actions_layout.setSpacing(6)
        preview_layout.addLayout(form)
        preview_layout.addLayout(actions)
        preview_layout.addWidget(self.contract_preview, 1)
        preview_layout.addLayout(self.generated_contract_actions_layout)

        layout.addWidget(template_panel)
        layout.addWidget(preview_panel, 1)
        QTimer.singleShot(0, self.load_selected_contract_template)
        return page

    @staticmethod
    def _add_contract_form_field(
        form: QGridLayout,
        row: int,
        column: int,
        label_text: str,
        editor: QWidget,
        *,
        column_span: int = 1,
    ) -> None:
        field = QWidget()
        field_layout = QVBoxLayout(field)
        field_layout.setContentsMargins(0, 0, 0, 0)
        field_layout.setSpacing(6)
        label = QLabel(label_text)
        label.setObjectName("fieldLabel")
        editor.setMinimumHeight(36)
        field_layout.addWidget(label)
        field_layout.addWidget(editor)
        form.addWidget(field, row, column, 1, column_span)

    def _tasks_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        actions = QHBoxLayout()
        self.publish_next_button = QPushButton("发布下一条")
        self.auto_task_button = QPushButton("启动自动执行")
        self.pause_task_button = QPushButton("暂停")
        self.skip_task_button = QPushButton("跳过")
        self.publish_next_button.clicked.connect(self.publish_next)
        self.auto_task_button.clicked.connect(self.toggle_auto_tasks)
        self.pause_task_button.clicked.connect(self.toggle_task_pause)
        self.skip_task_button.clicked.connect(self.skip_current_task)
        self.pause_task_button.setEnabled(False)
        self.skip_task_button.setEnabled(False)
        actions.addWidget(self.publish_next_button)
        actions.addWidget(self.auto_task_button)
        actions.addWidget(self.pause_task_button)
        actions.addWidget(self.skip_task_button)
        actions.addStretch(1)
        self.auto_task_state = QLabel("自动执行：未启动")
        self.auto_task_state.setObjectName("mutedText")
        self.current_task_label = QLabel("当前任务：-")
        self.current_task_label.setObjectName("mutedText")
        self.current_drama_label = QLabel("当前短剧：-")
        self.current_drama_label.setObjectName("mutedText")
        drama_row = QHBoxLayout()
        drama_row.addWidget(self.current_drama_label)
        drama_row.addStretch(1)
        self.current_media_account_label = QLabel("当前媒体号：-")
        self.current_media_account_label.setObjectName("mutedText")
        self.current_media_backend_button = QPushButton("打开媒体后台")
        self.current_media_backend_button.setEnabled(False)
        self.current_media_backend_button.clicked.connect(self.open_current_media_account_backend)
        media_account_row = QHBoxLayout()
        media_account_row.addWidget(self.current_media_account_label)
        media_account_row.addWidget(self.current_media_backend_button)
        media_account_row.addStretch(1)
        self.task_stage_label = QLabel("当前阶段：空闲")
        self.task_stage_label.setObjectName("mutedText")
        self.task_error_label = QLabel("最近错误：-")
        self.task_error_label.setObjectName("mutedText")
        note = QLabel("自动执行会定时发送心跳，空闲时自动发布下一条。")
        note.setObjectName("mutedText")
        panel, panel_layout = self._panel("任务操作")
        panel_layout.addLayout(actions)
        task_summary = QGridLayout()
        task_summary.setContentsMargins(0, 0, 0, 0)
        task_summary.setHorizontalSpacing(18)
        task_summary.setVerticalSpacing(6)
        task_summary.addWidget(self.auto_task_state, 0, 0)
        task_summary.addWidget(self.current_task_label, 0, 1)
        task_summary.addLayout(drama_row, 0, 2)
        task_summary.addLayout(media_account_row, 1, 0)
        task_summary.addWidget(self.task_stage_label, 1, 1)
        task_summary.addWidget(self.task_error_label, 1, 2)
        task_summary.addWidget(note, 2, 0, 1, 3)
        task_summary.setColumnStretch(0, 1)
        task_summary.setColumnStretch(1, 1)
        task_summary.setColumnStretch(2, 2)
        panel_layout.addLayout(task_summary)
        layout.addWidget(panel, 1)

        history_panel, history_layout = self._panel("历史任务")
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.task_history_keyword = QLineEdit()
        self.task_history_keyword.setPlaceholderText("搜索任务、短剧或媒体号")
        self.task_history_keyword.returnPressed.connect(lambda: self.load_task_history(page=0))
        filters.addWidget(self.task_history_keyword, 1)
        self.task_history_status = QComboBox()
        for label, value in self.distribution_task_status_options():
            self.task_history_status.addItem(label, value)
        self.task_history_status.currentIndexChanged.connect(lambda: self.load_task_history(page=0))
        filters.addWidget(self.task_history_status)
        refresh = QPushButton("刷新")
        refresh.clicked.connect(lambda: self.load_task_history(page=self.task_history_page))
        filters.addWidget(refresh)
        history_layout.addLayout(filters)

        self.task_history_table = QTableWidget(0, 9)
        self.task_history_table.setHorizontalHeaderLabels(
            ["短剧", "剧源", "媒体号", "状态", "执行链路", "失败原因", "创建时间", "结束时间", "操作"]
        )
        self.task_history_table.verticalHeader().setVisible(False)
        self.task_history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.task_history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.task_history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.task_history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.task_history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.task_history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.task_history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.task_history_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.task_history_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
        self.task_history_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Fixed)
        self.task_history_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.Fixed)
        self.task_history_table.setColumnWidth(1, 100)
        self.task_history_table.setColumnWidth(2, 130)
        self.task_history_table.setColumnWidth(3, 92)
        self.task_history_table.setColumnWidth(4, 380)
        self.task_history_table.setColumnWidth(6, 150)
        self.task_history_table.setColumnWidth(7, 150)
        self.task_history_table.setColumnWidth(8, 300)
        self.align_table_header_left(self.task_history_table)
        self.task_history_table.itemSelectionChanged.connect(self.on_task_history_selection_changed)
        history_layout.addWidget(self.task_history_table, 1)

        pager = QHBoxLayout()
        self.task_history_page_label = QLabel("共 0 条 · 第 1/1 页")
        self.task_history_page_label.setObjectName("mutedText")
        previous_page = QPushButton("上一页")
        previous_page.clicked.connect(lambda: self.load_task_history(page=max(self.task_history_page - 1, 0)))
        next_page = QPushButton("下一页")
        next_page.clicked.connect(
            lambda: self.load_task_history(
                page=min(self.task_history_page + 1, self.task_history_total_pages - 1)
            )
        )
        pager.addWidget(self.task_history_page_label)
        pager.addStretch(1)
        pager.addWidget(previous_page)
        pager.addWidget(next_page)
        history_layout.addLayout(pager)
        layout.addWidget(history_panel, 4)
        return page

    def _settings_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        scroll.setWidget(page)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._tool_path_settings_panel())
        layout.addWidget(self._video_reassembly_settings_panel())
        panel, panel_layout = self._panel("运行配置")
        update_row = QHBoxLayout()
        update_hint = QLabel(f"当前版本：{__version__}")
        update_hint.setObjectName("mutedText")
        self.update_check_button = QPushButton("检查更新")
        self.update_check_button.clicked.connect(lambda _checked=False: self.check_for_updates(manual=True))
        update_row.addWidget(update_hint)
        update_row.addStretch(1)
        update_row.addWidget(self.update_check_button)
        cleanup_row = QHBoxLayout()
        cleanup_hint = QLabel("自动每小时清理短剧缓存，仅保留 48 小时内的数据")
        cleanup_hint.setObjectName("mutedText")
        self.cleanup_data_button = QPushButton("清理数据")
        self.cleanup_data_button.clicked.connect(self.clean_upload_cache_now)
        cleanup_row.addWidget(cleanup_hint)
        cleanup_row.addStretch(1)
        cleanup_row.addWidget(self.cleanup_data_button)
        rows = settings_rows(self.settings)
        table = QTableWidget(len(rows), 3)
        table.setObjectName("settingsTable")
        table.setHorizontalHeaderLabels(["配置项", "值", "操作"])
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setWordWrap(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        table.setColumnWidth(0, 170)
        table.setColumnWidth(2, 92)
        table.cellDoubleClicked.connect(lambda row, column: self.open_settings_row(rows[row]) if column == 1 else None)
        for row, setting in enumerate(rows):
            label_item = QTableWidgetItem(setting.label)
            value_item = QTableWidgetItem(setting.value)
            label_item.setToolTip(setting.label)
            value_item.setToolTip(setting.value)
            table.setItem(row, 0, label_item)
            table.setItem(row, 1, value_item)
            if setting.kind == "directory":
                open_button = QPushButton("打开")
                open_button.setObjectName("tableActionButton")
                open_button.clicked.connect(lambda _=False, item=setting: self.open_settings_row(item))
                table.setCellWidget(row, 2, open_button)
            table.setRowHeight(row, 38)
        table.setMinimumHeight(360)
        note = QLabel("目录类配置可以点击“打开”进入 Finder；双击目录值也可以打开。")
        note.setObjectName("mutedText")
        panel_layout.addLayout(update_row)
        panel_layout.addLayout(cleanup_row)
        panel_layout.addWidget(note)
        panel_layout.addWidget(table, 1)
        layout.addWidget(panel)
        layout.addStretch(1)
        return scroll

    def _tool_path_settings_panel(self) -> QFrame:
        panel, panel_layout = self._panel("工具路径")
        hint = QLabel(
            "FFmpeg、字幕引擎和剪映路径保存后会优先使用。"
            "默认使用 faster-whisper；未安装时会自动回退到原 Whisper 命令。"
            "剪映图策略只影响自动任务，任务管理里的手动剪映图不受影响。"
        )
        hint.setObjectName("mutedText")
        panel_layout.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)

        self.ffmpeg_path_input = QLineEdit(str(self.settings.ffmpeg_path or ""))
        self.ffmpeg_path_input.setPlaceholderText(
            r"例如：D:\software\ffmpeg\bin\ffmpeg.exe 或 /opt/homebrew/bin/ffmpeg"
        )
        form.addRow("FFmpeg", self._path_input_row(self.ffmpeg_path_input, self.choose_ffmpeg_path))

        self.subtitle_provider_input = QComboBox()
        self.subtitle_provider_input.addItem("faster-whisper（推荐）", SUBTITLE_PROVIDER_FASTER_WHISPER)
        self.subtitle_provider_input.addItem("openai-whisper（兼容）", SUBTITLE_PROVIDER_OPENAI_WHISPER)
        self._set_combo_current_data(
            self.subtitle_provider_input,
            normalize_subtitle_provider(self.settings.subtitle_provider),
        )
        form.addRow("字幕引擎", self.subtitle_provider_input)

        self.faster_whisper_python_path_input = QLineEdit(
            str(self.settings.faster_whisper_python_path or "")
        )
        self.faster_whisper_python_path_input.setPlaceholderText(
            r"例如：C:\AI-Drama\faster-whisper-venv\Scripts\python.exe 或 ~/AI-Drama/faster-whisper-venv/bin/python"
        )
        form.addRow(
            "faster-whisper Python",
            self._path_input_row(
                self.faster_whisper_python_path_input,
                self.choose_faster_whisper_python_path,
            ),
        )

        self.whisper_path_input = QLineEdit(str(self.settings.whisper_path or ""))
        self.whisper_path_input.setPlaceholderText(
            r"兼容兜底，例如：C:\AI-Drama\whisper-venv\Scripts\whisper.exe"
        )
        form.addRow("openai-whisper 命令", self._path_input_row(self.whisper_path_input, self.choose_whisper_path))

        self.node_path_input = QLineEdit(str(self.settings.node_path or ""))
        self.node_path_input.setPlaceholderText("例如：/opt/homebrew/bin/node")
        form.addRow("Node.js", self._path_input_row(self.node_path_input, self.choose_node_path))

        self.jianying_draft_root_input = QLineEdit(str(self.settings.jianying_draft_root or ""))
        self.jianying_draft_root_input.setPlaceholderText(
            "例如：/Users/mac/Movies/JianyingPro/User Data/Projects/com.lveditor.draft"
        )
        form.addRow("剪映草稿目录", self._path_input_row(self.jianying_draft_root_input, self.choose_jianying_draft_root))

        self.jianying_app_input = QLineEdit(str(self.settings.jianying_app or ""))
        self.jianying_app_input.setPlaceholderText(
            r"例如：C:\Users\user\AppData\Local\JianyingPro\JianyingPro.exe"
        )
        form.addRow("剪映程序地址", self._path_input_row(self.jianying_app_input, self.choose_jianying_app))

        self.jianying_music_dir_input = QLineEdit(str(self.settings.jianying_music_dir or ""))
        self.jianying_music_dir_input.setPlaceholderText(
            "例如：/Users/mac/Library/Application Support/ai-drama-desktop/work/dramas/wav"
        )
        form.addRow("剪映音乐目录", self._path_input_row(self.jianying_music_dir_input, self.choose_jianying_music_dir))

        self.jianying_project_strategy_input = QComboBox()
        for strategy in JIANYING_PROJECT_STRATEGY_PREFERENCES:
            self.jianying_project_strategy_input.addItem(
                jianying_project_strategy_preference_label(strategy),
                strategy,
            )
        self._set_combo_current_data(
            self.jianying_project_strategy_input,
            normalize_jianying_project_strategy_preference(self.settings.jianying_project_strategy),
        )
        form.addRow("剪映图策略", self.jianying_project_strategy_input)
        panel_layout.addLayout(form)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        save_button = QPushButton("保存工具配置")
        save_button.clicked.connect(self.save_tool_path_settings)
        action_row.addWidget(save_button)
        panel_layout.addLayout(action_row)
        return panel

    def _path_input_row(self, input_widget: QLineEdit, choose_callback: Callable[[], None]) -> QHBoxLayout:
        input_widget.setMinimumHeight(34)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(input_widget, 1)
        browse_button = QPushButton("选择")
        browse_button.setMinimumHeight(34)
        browse_button.clicked.connect(choose_callback)
        clear_button = QPushButton("清空")
        clear_button.setMinimumHeight(34)
        clear_button.clicked.connect(lambda: input_widget.clear())
        row.addWidget(browse_button)
        row.addWidget(clear_button)
        return row

    def _video_reassembly_settings_panel(self) -> QFrame:
        panel, panel_layout = self._panel("视频生成配置")
        if not hasattr(self, "video_reassembly_store"):
            self.video_reassembly_store = VideoReassemblyConfigStore(
                self.settings.config_dir / "video-processing.json",
            )
        if not hasattr(self, "video_reassembly_config"):
            self.video_reassembly_config = self.video_reassembly_store.load()
        config = self.video_reassembly_config.normalized()
        self.video_reassembly_summary_label = QLabel(f"当前方案：{config.summary()}")
        self.video_reassembly_summary_label.setObjectName("mutedText")
        panel_layout.addWidget(self.video_reassembly_summary_label)

        self.video_reassembly_method_input = QComboBox()
        self.video_reassembly_method_input.addItem("重组分集", VIDEO_REASSEMBLY_METHOD_REASSEMBLE)
        self.video_reassembly_method_input.addItem("不启用", VIDEO_REASSEMBLY_METHOD_NONE)
        self._set_combo_current_data(self.video_reassembly_method_input, config.method)

        self.reassembly_min_seconds_input = self._seconds_spin_box(1.0, 3600.0, config.segment_min_seconds)
        self.reassembly_max_seconds_input = self._seconds_spin_box(1.0, 3600.0, config.segment_max_seconds)
        self.reassembly_trim_head_input = self._seconds_spin_box(0.0, 60.0, config.trim_head_seconds)
        self.reassembly_trim_tail_input = self._seconds_spin_box(0.0, 60.0, config.trim_tail_seconds)
        self.reassembly_speed_min_input = self._percent_spin_box(config.speed_min_percent)
        self.reassembly_speed_max_input = self._percent_spin_box(config.speed_max_percent)
        self.reassembly_swap_input = QCheckBox("强制横竖互换（会改变输出方向）")
        self.reassembly_swap_input.setChecked(config.swap_orientation)
        self.reassembly_bgm_dir_input = QLineEdit(str(config.bgm_directory or ""))
        self.reassembly_bgm_dir_input.setPlaceholderText("例如：D:/短剧/音乐 或 /Users/mac/Music/drama-bgm")
        self.reassembly_bgm_volume_input = self._percent_spin_box(config.bgm_volume_percent, minimum=0.0, maximum=100.0)
        self.reassembly_pitch_input = self._number_spin_box(-12.0, 12.0, config.audio_pitch_semitones, suffix=" 个半音")
        self.reassembly_border_input = self._percent_spin_box(config.border_percent, minimum=0.0, maximum=20.0)
        self.reassembly_mirror_input = QCheckBox("水平镜像翻转")
        self.reassembly_mirror_input.setChecked(config.mirror_horizontal)
        self.reassembly_rotate_input = self._number_spin_box(-10.0, 10.0, config.rotate_degrees, suffix=" °")

        range_row = QHBoxLayout()
        range_row.addWidget(self.reassembly_min_seconds_input)
        range_row.addWidget(QLabel("至"))
        range_row.addWidget(self.reassembly_max_seconds_input)
        range_row.addStretch(1)

        trim_row = QHBoxLayout()
        trim_row.addWidget(QLabel("片头"))
        trim_row.addWidget(self.reassembly_trim_head_input)
        trim_row.addSpacing(12)
        trim_row.addWidget(QLabel("片尾"))
        trim_row.addWidget(self.reassembly_trim_tail_input)
        trim_row.addStretch(1)

        speed_row = QHBoxLayout()
        speed_row.addWidget(self.reassembly_speed_min_input)
        speed_row.addWidget(QLabel("至"))
        speed_row.addWidget(self.reassembly_speed_max_input)
        speed_row.addStretch(1)

        left_form = QFormLayout()
        left_form.setLabelAlignment(Qt.AlignLeft)
        left_form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        left_form.setHorizontalSpacing(18)
        left_form.setVerticalSpacing(10)
        left_form.addRow("生成方式", self.video_reassembly_method_input)
        left_form.addRow("切分时长", range_row)
        left_form.addRow("去头去尾", trim_row)
        left_form.addRow("变速区间", speed_row)

        right_form = QFormLayout()
        right_form.setLabelAlignment(Qt.AlignLeft)
        right_form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        right_form.setHorizontalSpacing(18)
        right_form.setVerticalSpacing(10)
        right_form.addRow("背景音乐目录", self._path_input_row(self.reassembly_bgm_dir_input, self.choose_reassembly_bgm_dir))
        right_form.addRow("背景音乐音量", self.reassembly_bgm_volume_input)
        right_form.addRow("音调偏移", self.reassembly_pitch_input)
        right_form.addRow("四周黑边", self.reassembly_border_input)
        right_form.addRow("轻微旋转", self.reassembly_rotate_input)

        checkbox_column = QVBoxLayout()
        checkbox_column.setSpacing(8)
        checkbox_column.addWidget(self.reassembly_swap_input)
        checkbox_column.addWidget(self.reassembly_mirror_input)
        checkbox_column.addStretch(1)
        right_form.addRow("镜像翻转", checkbox_column)

        columns = QGridLayout()
        columns.setHorizontalSpacing(28)
        columns.setVerticalSpacing(0)
        left_widget = QWidget()
        left_widget.setLayout(left_form)
        right_widget = QWidget()
        right_widget.setLayout(right_form)
        columns.addWidget(left_widget, 0, 0)
        columns.addWidget(right_widget, 0, 1)
        columns.setColumnStretch(0, 1)
        columns.setColumnStretch(1, 1)

        panel_layout.addLayout(columns)
        hint = QLabel(
            "全剧按集序接成一条时间线，在切分区间内滚动切出新集；"
            "剩余不足 30 秒会并入上一集。默认保持原始横竖方向；只有勾选“强制横竖互换”时才会把横屏改成竖版或反过来。"
        )
        hint.setObjectName("mutedText")
        hint.setWordWrap(True)
        panel_layout.addWidget(hint)

        actions = QHBoxLayout()
        actions.addStretch(1)
        save_button = QPushButton("保存配置")
        save_button.clicked.connect(self.save_video_reassembly_config)
        actions.addWidget(save_button)
        panel_layout.addLayout(actions)
        return panel

    def _seconds_spin_box(self, minimum: float, maximum: float, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setSuffix(" s")
        spin.setValue(value)
        return spin

    def _percent_spin_box(self, value: float, *, minimum: float = -50.0, maximum: float = 50.0) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setSuffix(" %")
        spin.setValue(value)
        return spin

    def _number_spin_box(self, minimum: float, maximum: float, value: float, *, suffix: str = "") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(1)
        spin.setSingleStep(0.1)
        spin.setSuffix(suffix)
        spin.setValue(value)
        return spin

    @staticmethod
    def _set_combo_current_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def save_video_reassembly_config(self) -> None:
        config = VideoReassemblyConfig(
            method=str(self.video_reassembly_method_input.currentData() or VIDEO_REASSEMBLY_METHOD_NONE),
            segment_min_seconds=self.reassembly_min_seconds_input.value(),
            segment_max_seconds=self.reassembly_max_seconds_input.value(),
            trim_head_seconds=self.reassembly_trim_head_input.value(),
            trim_tail_seconds=self.reassembly_trim_tail_input.value(),
            speed_min_percent=self.reassembly_speed_min_input.value(),
            speed_max_percent=self.reassembly_speed_max_input.value(),
            swap_orientation=self.reassembly_swap_input.isChecked(),
            bgm_directory=self.reassembly_bgm_dir_input.text().strip() or None,
            bgm_volume_percent=self.reassembly_bgm_volume_input.value(),
            audio_pitch_semitones=self.reassembly_pitch_input.value(),
            border_percent=self.reassembly_border_input.value(),
            mirror_horizontal=self.reassembly_mirror_input.isChecked(),
            rotate_degrees=self.reassembly_rotate_input.value(),
        ).normalized()
        self.video_reassembly_store.save(config)
        self.video_reassembly_config = config
        self.video_reassembly_summary_label.setText(f"当前方案：{config.summary()}")
        self.append_log(f"视频生成配置已保存：{config.summary()}")
        QMessageBox.information(self, "视频生成配置", "视频生成配置已保存。")

    def choose_whisper_path(self) -> None:
        self._choose_file_path(self.whisper_path_input, "选择 Whisper 命令")

    def choose_faster_whisper_python_path(self) -> None:
        self._choose_file_path(self.faster_whisper_python_path_input, "选择 faster-whisper Python")

    def choose_ffmpeg_path(self) -> None:
        self._choose_file_path(self.ffmpeg_path_input, "选择 FFmpeg 命令")

    def choose_node_path(self) -> None:
        self._choose_file_path(self.node_path_input, "选择 Node.js 命令")

    def choose_jianying_draft_root(self) -> None:
        self._choose_directory_path(self.jianying_draft_root_input, "选择剪映草稿目录")

    def choose_jianying_app(self) -> None:
        self._choose_file_path(self.jianying_app_input, "选择剪映程序")

    def choose_jianying_music_dir(self) -> None:
        self._choose_directory_path(self.jianying_music_dir_input, "选择剪映音乐目录")

    def choose_reassembly_bgm_dir(self) -> None:
        self._choose_directory_path(self.reassembly_bgm_dir_input, "选择背景音乐目录")

    def _choose_file_path(self, input_widget: QLineEdit, title: str) -> None:
        start_dir = str(Path(input_widget.text()).expanduser().parent) if input_widget.text() else ""
        path, _ = QFileDialog.getOpenFileName(self, title, start_dir)
        if path:
            input_widget.setText(path)

    def _choose_directory_path(self, input_widget: QLineEdit, title: str) -> None:
        start_dir = input_widget.text().strip() or str(self.settings.work_dir)
        path = QFileDialog.getExistingDirectory(self, title, start_dir)
        if path:
            input_widget.setText(path)

    def save_tool_path_settings(self) -> None:
        ffmpeg_path = self.ffmpeg_path_input.text().strip() or None
        subtitle_provider = str(
            self.subtitle_provider_input.currentData() or DEFAULT_SUBTITLE_PROVIDER
        )
        faster_whisper_python_path = self.faster_whisper_python_path_input.text().strip() or None
        whisper_path = self.whisper_path_input.text().strip() or None
        node_path = self.node_path_input.text().strip() or None
        jianying_draft_root = self.jianying_draft_root_input.text().strip() or None
        jianying_app = self.jianying_app_input.text().strip() or None
        jianying_music_dir = self.jianying_music_dir_input.text().strip() or None
        jianying_project_strategy = normalize_jianying_project_strategy_preference(
            str(self.jianying_project_strategy_input.currentData() or DEFAULT_JIANYING_PROJECT_STRATEGY)
        )
        save_tool_path_config(
            self.settings.config_dir,
            ffmpeg_path=ffmpeg_path,
            whisper_path=whisper_path,
            subtitle_provider=subtitle_provider,
            faster_whisper_python_path=faster_whisper_python_path,
            node_path=node_path,
            jianying_draft_root=jianying_draft_root,
            jianying_app=jianying_app,
            jianying_music_dir=jianying_music_dir,
            jianying_project_strategy=jianying_project_strategy,
        )
        self.settings = update_settings(
            self.settings,
            ffmpeg_path=resolve_ffmpeg_path(ffmpeg_path or "ffmpeg"),
            subtitle_provider=normalize_subtitle_provider(subtitle_provider),
            faster_whisper_python_path=resolve_faster_whisper_python_path(
                faster_whisper_python_path
            ),
            whisper_path=whisper_path,
            node_path=node_path,
            jianying_draft_root=Path(jianying_draft_root).expanduser() if jianying_draft_root else None,
            jianying_app=Path(jianying_app).expanduser() if jianying_app else None,
            jianying_music_dir=Path(jianying_music_dir).expanduser() if jianying_music_dir else None,
            jianying_project_strategy=jianying_project_strategy,
        )
        self.append_log(
            "工具路径已保存："
            f"FFmpeg={self.settings.ffmpeg_path or '自动探测'}，"
            f"字幕引擎={self.settings.subtitle_provider}，"
            f"faster-whisper Python={self.settings.faster_whisper_python_path or '自动探测'}，"
            f"openai-whisper={whisper_path or '自动探测'}，"
            f"Node.js={node_path or '自动探测'}，"
            f"剪映草稿目录={jianying_draft_root or '自动探测'}，"
            f"剪映程序地址={jianying_app or '自动探测'}，"
            f"剪映音乐目录={jianying_music_dir or '默认目录'}，"
            f"剪映图策略={jianying_project_strategy_preference_label(self.settings.jianying_project_strategy)}"
        )
        QMessageBox.information(self, "保存工具配置", "工具配置已保存，后续任务会使用新的配置。")

    def _logs_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        clear = QPushButton("清空日志")
        clear.clicked.connect(self.log_view.clear)
        panel, panel_layout = self._panel("运行日志")
        panel_layout.addWidget(clear, alignment=Qt.AlignRight)
        panel_layout.addWidget(self.log_view)
        layout.addWidget(panel)
        return page

    def show_page(self, index: int) -> None:
        if index < 0:
            return
        if hasattr(self, "stack") and self.stack.currentWidget() != self.main_page:
            return
        item = desktop_nav_items()[index]
        self.header_title.setText(item.title)
        self.header_subtitle.setText(item.description)
        self.pages.setCurrentIndex(index)
        if item.key == "media":
            self.load_media_accounts()
        if item.key == "dramas" and hasattr(self, "drama_table"):
            self.load_dramas(page=self.drama_page)
        if item.key == "tasks" and hasattr(self, "task_history_table"):
            self.load_media_accounts()
            self.load_task_history(page=self.task_history_page)
        if item.key == "contracts" and hasattr(self, "contract_drama_input"):
            self.load_contract_dramas()
        self.refresh_status()

    def current_page_key(self) -> str | None:
        if not hasattr(self, "nav"):
            return None
        index = self.nav.currentRow()
        items = desktop_nav_items()
        if index < 0 or index >= len(items):
            return None
        return items[index].key

    def refresh_visible_list(self) -> None:
        if not hasattr(self, "stack") or self.stack.currentWidget() != self.main_page:
            return
        page_key = self.current_page_key()
        if page_key == "dramas" and hasattr(self, "drama_table"):
            self.load_dramas(page=self.drama_page, silent=True)
        elif page_key == "tasks" and hasattr(self, "task_history_table"):
            self.load_task_history(page=self.task_history_page, silent=True)

    def handle_silent_refresh_failed(self, error: str) -> None:
        message = self.clean_error_message(error)
        self.statusBar().showMessage(f"自动刷新失败：{message}", 5000)

    def on_logged_in(self) -> None:
        self.settings = update_settings(self.settings)
        self.agent.settings = self.settings
        self.current_username = self.login_page.username_input.text().strip()
        self.update_current_username_label()
        self.append_log("登录成功。")
        self.stack.setCurrentWidget(self.main_page)
        self.show_page(self.nav.currentRow())
        self.list_refresh_timer.start()
        self.upload_cache_cleanup_timer.start()
        self.refresh_status()
        QTimer.singleShot(600, self.check_for_updates)

    def logout(self) -> None:
        self.list_refresh_timer.stop()
        self.upload_cache_cleanup_timer.stop()
        self.token_store.clear()
        self.current_username = ""
        self.update_current_username_label()
        self.stack.setCurrentWidget(self.login_page)
        self.append_log("已退出登录。")
        self.refresh_status()

    def update_current_username_label(self) -> None:
        if hasattr(self, "current_username_label"):
            self.current_username_label.setText(f"当前登录：{self.current_username or '未登录'}")

    def quit_app(self) -> None:
        self.list_refresh_timer.stop()
        self.upload_cache_cleanup_timer.stop()
        if self.agent.running:
            self.agent.stop()
        QApplication.instance().quit()

    def api(self) -> ApiClient:
        return ApiClient(self.settings.server_url, self.token_store, auth_refresher=self.refresh_auth_token)

    def refresh_auth_token(self) -> bool:
        remembered = RememberedLoginStore(self.settings.remembered_login_file).get()
        if not remembered:
            return False
        username, password = remembered
        try:
            ApiClient(self.settings.server_url, self.token_store).login(username, password, self.settings.device_id)
        except Exception:  # noqa: BLE001
            return False
        return True

    def check_for_updates(self, manual: bool = False) -> None:
        platform = detect_platform()
        if not platform:
            self.append_log("当前平台暂不支持自动更新检查。")
            if manual:
                QMessageBox.information(self, "检查更新", "当前平台暂不支持自动更新检查。")
            return
        self.update_check_manual = manual
        if manual:
            self.set_update_check_busy(True)
        self.run_async(
            "检查桌面端更新",
            lambda: (platform, self.api().check_update(platform, __version__), manual),
            self.handle_update_check,
            log_result=False,
        )

    def handle_update_check(self, result: tuple[str, dict[str, Any]] | tuple[str, dict[str, Any], bool]) -> None:
        platform, payload, manual = result if len(result) == 3 else (*result, getattr(self, "update_check_manual", False))
        self.set_update_check_busy(False)
        self.update_check_manual = False
        update = UpdateInfo.from_api(payload)
        if not update:
            self.append_log(f"当前已是最新版本：{__version__}")
            if manual:
                QMessageBox.information(self, "检查更新", f"当前已是最新版本：{__version__}")
            return
        self.prompt_update(platform, update)

    def set_update_check_busy(self, busy: bool) -> None:
        if not hasattr(self, "update_check_button"):
            return
        self.update_check_button.setEnabled(not busy)
        self.update_check_button.setText("检查中..." if busy else "检查更新")

    def prompt_update(self, platform: str, update: UpdateInfo) -> None:
        message = QMessageBox(self)
        message.setWindowTitle("发现新版本")
        message.setIcon(QMessageBox.Information)
        message.setText(f"发现 AI Drama Desktop {update.version}")
        notes = update.release_notes or "暂无更新说明"
        size = f"{update.file_size / 1024 / 1024:.1f} MB" if update.file_size else "未知大小"
        message.setInformativeText(f"{notes}\n\n安装包大小：{size}")
        update_button = message.addButton("立即更新", QMessageBox.AcceptRole)
        if not update.mandatory:
            message.addButton("稍后", QMessageBox.RejectRole)
        message.exec()
        if message.clickedButton() == update_button:
            self.download_update(platform, update)

    def download_update(self, platform: str, update: UpdateInfo) -> None:
        token = self.token_store.get()
        headers = {"Authorization": f"Bearer {token}"} if token else None
        self.run_async(
            f"下载桌面端 {update.version}",
            lambda: download_installer(update, self.settings.updates_dir, self.settings.server_url, headers=headers),
            lambda path: self.open_downloaded_update(platform, Path(path)),
            log_result=False,
        )

    def open_downloaded_update(self, platform: str, path: Path) -> None:
        open_installer(path, platform)
        self.append_log(f"安装包已打开：{path}")
        self.quit_app()

    def runner(self) -> TaskRunner:
        chrome_path = find_chrome(self.settings.chrome_path)
        chrome = ChromeController(chrome_path, self.settings.browser_profile_dir)
        return TaskRunner(
            api=self.api(),
            processor=FfmpegProcessor(self.settings.ffmpeg_path),
            publisher=get_publisher("WECHAT_VIDEO", chrome),
            publisher_factory=lambda media_account_id: self.publisher_for_media_account(chrome, media_account_id),
            work_dir=self.settings.work_dir,
            device_id=self.settings.device_id,
            downloads_dir=self.settings.downloads_dir,
            processed_dir=self.settings.processed_dir,
            progress_callback=self.update_task_progress,
            cancel_checker=self.task_cancel_event.is_set,
            pause_checker=self.task_pause_event.is_set,
            skip_checker=self.task_skip_event.is_set,
            download_concurrency=self.settings.download_concurrency,
            contract_templates=dict(self.contract_templates),
            contracts_dir=self.settings.contracts_dir,
            contract_platform="WECHAT_VIDEO",
            contract_buyer=self.contract_party_value("WECHAT_VIDEO", "buyer"),
            contract_seller=self.contract_party_value("WECHAT_VIDEO", "seller"),
            soffice_path=self.settings.soffice_path,
            video_reassembly_config=self.video_reassembly_config,
            storyboard_generator=StoryboardGenerator(self.settings.ffmpeg_path, chrome_path),
            storyboards_dir=self.settings.work_dir / "storyboards",
            jianying_generator=JianyingProjectGenerator(
                ffmpeg_path=self.settings.ffmpeg_path,
                node_path=self.settings.node_path,
                draft_root=self.settings.jianying_draft_root,
                jianying_app=self.settings.jianying_app,
            ),
            subtitle_provider=self.settings.subtitle_provider,
            whisper_path=self.settings.whisper_path,
            faster_whisper_python_path=self.settings.faster_whisper_python_path,
            jianying_music_dir=self.settings.jianying_music_dir,
            jianying_project_strategy=self.settings.jianying_project_strategy,
        )

    def publisher_for_media_account(self, chrome: ChromeController, media_account_id: str):
        account = next(
            (
                item
                for item in self.media_accounts
                if str(item.get("id") or "") == str(media_account_id)
            ),
            None,
        )
        if not account:
            return get_publisher("WECHAT_VIDEO", chrome, media_account_id)

        platform = str(account.get("platform") or "WECHAT_VIDEO")
        profile_key = self.media_profile_key(account, media_account_id)
        login_state_ref = str(account.get("loginStateRef") or "").strip()
        profile_dir = Path(login_state_ref) if login_state_ref else None
        return get_publisher(platform, chrome, profile_key, profile_dir=profile_dir)

    def run_async(
        self,
        title: str,
        task: Callable[[], Any],
        on_done: Callable[[Any], None] | None = None,
        *,
        log_result: bool = True,
        log_activity: bool = True,
        on_failed: Callable[[str], None] | None = None,
    ) -> None:
        if log_activity:
            self.append_log(f"开始：{title}")
        worker = Worker(task)
        worker.signals.done.connect(
            lambda result, item=worker: self.worker_done_requested.emit(
                (item, title, result, on_done, log_result, log_activity)
            )
        )
        worker.signals.failed.connect(
            lambda error, item=worker: self.worker_failed_requested.emit(
                (item, title, error, on_failed, log_activity)
            )
        )
        self.active_workers.append(worker)
        self.thread_pool.start(worker)

    def _handle_worker_done_requested(self, payload: object) -> None:
        worker, title, result, on_done, log_result, log_activity = payload
        try:
            self._task_done(title, result, on_done, log_result=log_result, log_activity=log_activity)
        finally:
            self._release_worker(worker)

    def _handle_worker_failed_requested(self, payload: object) -> None:
        worker, title, error, on_failed, log_activity = payload
        try:
            self._task_failed(title, error, on_failed=on_failed, log_activity=log_activity)
        finally:
            self._release_worker(worker)

    def _release_worker(self, worker: Worker) -> None:
        if worker in self.active_workers:
            self.active_workers.remove(worker)

    def _task_done(
        self,
        title: str,
        result: Any,
        on_done: Callable[[Any], None] | None,
        *,
        log_result: bool = True,
        log_activity: bool = True,
    ) -> None:
        if log_activity:
            if log_result and result is not None:
                self.append_log(f"完成：{title} {self.summarize_task_result(result)}")
            else:
                self.append_log(f"完成：{title}")
        if on_done:
            on_done(result)

    @staticmethod
    def summarize_task_result(result: Any) -> str:
        if isinstance(result, list):
            return f"共 {len(result)} 条"
        if isinstance(result, dict):
            content = result.get("content")
            if isinstance(content, list):
                total = result.get("totalElements")
                if isinstance(total, int):
                    return f"共 {total} 条"
                return f"共 {len(content)} 条"
        return str(result)

    def _task_failed(
        self,
        title: str,
        error: str,
        on_failed: Callable[[str], None] | None = None,
        *,
        log_activity: bool = True,
    ) -> None:
        if log_activity:
            self.append_log(f"失败：{title}\n{error}")
        if on_failed:
            on_failed(error)
            return
        if title == "检查桌面端更新":
            self.set_update_check_busy(False)
            self.update_check_manual = False
        if title == "自动执行任务":
            self.auto_task_busy = False
            self.update_task_progress("任务失败：自动执行请求失败", self.current_task_id)
        if title in {"检查发布条件", "发布下一条", "检查重试条件", "重试任务"}:
            self.set_manual_publish_busy(False)
            if title == "检查发布条件":
                self.update_task_progress("发布未启动：服务请求失败", None)
            elif title == "检查重试条件":
                self.update_task_progress("重试未启动：服务请求失败", None)
            else:
                self.update_task_progress("任务失败：发布执行异常", self.current_task_id)
            if title in {"检查重试条件", "重试任务"} and hasattr(self, "task_history_table"):
                self.load_task_history(page=self.task_history_page)
        QMessageBox.critical(self, title, self.clean_error_message(error))

    @staticmethod
    def build_task_history_path(
        page: int = 0,
        size: int = 10,
        keyword: str = "",
        status: str = "ALL",
    ) -> str:
        params = [("page", str(page)), ("size", str(size)), ("sort", "createdAt,desc")]
        if keyword.strip():
            params.append(("keyword", keyword.strip()))
        if status and status != "ALL":
            params.append(("status", status))
        return f"/desktop/tasks?{urlencode(params, safe=',')}"

    def load_task_history(self, page: int = 0, *, silent: bool = False) -> None:
        if not hasattr(self, "task_history_table"):
            return
        keyword = self.task_history_keyword.text().strip() if hasattr(self, "task_history_keyword") else ""
        status = str(self.task_history_status.currentData() or "ALL") if hasattr(self, "task_history_status") else "ALL"
        path = self.build_task_history_path(page=page, size=self.task_history_size, keyword=keyword, status=status)

        def render(result: dict[str, Any]) -> None:
            rows = result.get("content") or []
            self.task_history_page = int(result.get("page") or 0)
            self.task_history_total_pages = max(int(result.get("totalPages") or 1), 1)
            self.task_history_total_elements = int(result.get("totalElements") or 0)
            self.render_task_history_table(rows)
            page_text = (
                f"共 {self.task_history_total_elements} 条 · "
                f"第 {self.task_history_page + 1}/{self.task_history_total_pages} 页"
            )
            self.task_history_page_label.setText(page_text)

        self.run_async(
            "加载任务历史",
            lambda: self.api().get(path),
            render,
            log_result=False,
            log_activity=not silent,
            on_failed=self.handle_silent_refresh_failed if silent else None,
        )

    def render_task_history_table(self, rows: list[dict[str, Any]]) -> None:
        self.task_history_rows = rows
        self.task_history_table.setRowCount(len(rows))
        for row_index, task in enumerate(rows):
            values = self.task_history_row_values(task)
            for column, value in enumerate(values):
                item = self.left_aligned_table_item(value)
                item.setToolTip(value)
                self.task_history_table.setItem(row_index, column, item)
            self.task_history_table.setCellWidget(row_index, 4, self.task_history_chain_widget(task))
            self.task_history_table.setCellWidget(row_index, 8, self.task_history_actions_widget(task))
            self.task_history_table.setRowHeight(row_index, 46)

    def on_task_history_selection_changed(self) -> None:
        if not hasattr(self, "task_history_table"):
            return
        row = self.task_history_table.currentRow()
        if row < 0 or row >= len(self.task_history_rows):
            return
        task = self.task_history_rows[row]
        task_id = str(task.get("id") or "").strip() or None
        self.update_task_progress("已选择历史任务", task_id, task)

    def task_history_row_values(self, task: dict[str, Any]) -> list[str]:
        return [
            str(task.get("dramaTitle") or task.get("dramaId") or "-"),
            self.drama_source_label(task),
            str(task.get("mediaAccountName") or task.get("mediaAccountId") or "-"),
            self.distribution_task_status_label(str(task.get("status") or "")),
            self.task_history_chain_summary(task),
            str(task.get("failureReason") or "-"),
            self.format_datetime(str(task.get("createdAt") or "")),
            self.format_datetime(str(task.get("finishedAt") or "")),
        ]

    def task_history_chain_widget(self, task: dict[str, Any]) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(2)
        labels = self.task_history_chain_labels(task)
        for index, label in enumerate(labels):
            state = self.task_history_chain_state(task, index)
            badge = QLabel(label)
            badge.setAlignment(Qt.AlignCenter)
            badge.setMinimumWidth(46)
            badge.setMaximumWidth(60)
            badge.setStyleSheet(self.task_history_chain_style(state))
            layout.addWidget(badge)
            if index < len(labels) - 1:
                arrow = QLabel("-")
                arrow.setObjectName("mutedText")
                arrow.setFixedWidth(8)
                arrow.setAlignment(Qt.AlignCenter)
                layout.addWidget(arrow)
        layout.addStretch(1)
        return wrapper

    def task_history_chain_labels(self, task: dict[str, Any]) -> list[str]:
        labels = ["排队", "领取", "下载", "处理", "上传", "完成"]
        status = str(task.get("status") or "")
        if status == "FAILED":
            labels[self.task_history_problem_step(task)] += "失败"
        elif status == "CANCELLED":
            labels[self.task_history_problem_step(task)] += "停止"
        elif status in {"DOWNLOADING", "UPLOADING", "PROCESSING"}:
            labels[self.task_history_active_step(task)] += "中"
        return labels

    def task_history_chain_state(self, task: dict[str, Any], step: int) -> str:
        status = str(task.get("status") or "")
        if status == "SUCCEEDED":
            return "done"
        if status == "FAILED":
            failed_step = self.task_history_problem_step(task)
            if step < failed_step:
                return "done"
            return "failed" if step == failed_step else "waiting"
        if status == "CANCELLED":
            stopped_step = self.task_history_problem_step(task)
            if step < stopped_step:
                return "done"
            return "cancelled" if step == stopped_step else "waiting"
        active_step = self.task_history_active_step(task)
        if step < active_step:
            return "done"
        if step == active_step:
            return "active"
        return "waiting"

    def task_history_chain_summary(self, task: dict[str, Any]) -> str:
        labels = self.task_history_chain_labels(task)
        states = [
            self.task_history_chain_state(task, index)
            for index in range(len(labels))
        ]
        if "failed" in states:
            return labels[states.index("failed")]
        if "cancelled" in states:
            return labels[states.index("cancelled")]
        if str(task.get("status") or "") == "SUCCEEDED":
            return "已完成"
        if "active" in states:
            return labels[states.index("active")]
        return "-"

    @staticmethod
    def task_history_chain_style(state: str) -> str:
        styles = {
            "done": ("#14532d", "#dcfce7", "#86efac"),
            "active": ("#1d4ed8", "#dbeafe", "#93c5fd"),
            "failed": ("#991b1b", "#fee2e2", "#fca5a5"),
            "cancelled": ("#92400e", "#fef3c7", "#fcd34d"),
            "waiting": ("#64748b", "#f1f5f9", "#cbd5e1"),
        }
        color, background, border = styles.get(state, styles["waiting"])
        return (
            "QLabel {"
            f" color: {color};"
            f" background: {background};"
            f" border: 1px solid {border};"
            " border-radius: 4px;"
            " padding: 2px 4px;"
            " font-size: 12px;"
            "}"
        )

    def task_history_active_step(self, task: dict[str, Any]) -> int:
        status = str(task.get("status") or "")
        status_steps = {
            "PENDING": 0,
            "CLAIMED": 1,
            "DOWNLOADING": 2,
            "PROCESSING": 3,
            "UPLOADING": 4,
            "SUCCEEDED": 5,
        }
        return status_steps.get(status, self.task_history_problem_step(task))

    def task_history_problem_step(self, task: dict[str, Any]) -> int:
        try:
            progress = int(task.get("progress") or 0)
        except (TypeError, ValueError):
            progress = 0
        if progress >= 75:
            return 4
        if progress >= 70:
            return 3
        if progress >= 10:
            return 2
        if str(task.get("status") or "") == "PENDING":
            return 0
        return 1

    def task_history_actions_widget(self, task: dict[str, Any]) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        retry = QPushButton("重试")
        if self.should_retry_from_upload_cache(task):
            retry.setToolTip("从上传阶段继续，复用本地已处理视频")
        retry.setEnabled(self.is_task_retryable(task) and not self.is_current_task_running(str(task.get("id") or "")))
        retry.clicked.connect(lambda _=False, item=task: self.retry_distribution_task(item))
        layout.addWidget(retry)
        force_stop = QPushButton("强停")
        force_stop.setToolTip("取消待执行任务，或把卡住的执行中任务标记为已取消")
        force_stop.setEnabled(self.is_task_force_stoppable(task))
        force_stop.clicked.connect(lambda _=False, item=task: self.force_stop_distribution_task(item))
        layout.addWidget(force_stop)
        jianying_preview = QPushButton("剪映图")
        unavailable_reason = self.jianying_preview_unavailable_reason(task)
        jianying_preview.setEnabled(True)
        if unavailable_reason is None:
            jianying_preview.setToolTip(f"从 processed/reassembled 生成到 {JIANYING_PROJECT_PREVIEW_DIRNAME}-V1/V2/V3")
        else:
            jianying_preview.setToolTip(unavailable_reason)
        jianying_preview.clicked.connect(lambda _=False, item=task: self.generate_jianying_preview_for_task(item))
        layout.addWidget(jianying_preview)
        layout.addStretch(1)
        return wrapper

    def has_local_reassembled_cache(self, task: dict[str, Any]) -> bool:
        return self.jianying_preview_cache_unavailable_reason(task) is None

    def jianying_preview_unavailable_reason(self, task: dict[str, Any]) -> str | None:
        task_id = str(task.get("id") or "").strip()
        if not task_id:
            return "任务 ID 为空，无法生成剪映工程图。"
        if str(task.get("platform") or "WECHAT_VIDEO") != "WECHAT_VIDEO":
            return "剪映工程图预览当前只支持视频号任务。"
        if getattr(self, "jianying_preview_busy", False):
            return "已有剪映工程图正在生成，请等待完成后再试。"
        if getattr(self, "manual_publish_busy", False) or getattr(self, "auto_task_busy", False):
            return "当前已有任务在执行，请等待完成后再生成剪映工程图。"
        return self.jianying_preview_cache_unavailable_reason(task)

    def jianying_preview_cache_unavailable_reason(self, task: dict[str, Any]) -> str | None:
        settings = getattr(self, "settings", None)
        processed_dir = getattr(settings, "processed_dir", None)
        if not processed_dir:
            return "本机未配置 processed 目录，无法查找 reassembled 缓存。"
        processed_dir = Path(processed_dir)
        if not processed_dir.is_dir():
            return f"本机 processed 目录不存在：{processed_dir}"
        checked_dirs: list[Path] = []
        unreadable_dirs: list[Path] = []
        for drama_dir in self.contract_drama_dir_candidates(processed_dir, task):
            reassembled_dir = drama_dir / VIDEO_REASSEMBLY_DIRNAME
            checked_dirs.append(reassembled_dir)
            if not reassembled_dir.is_dir():
                continue
            try:
                if any(
                    path.is_file()
                    and path.suffix.lower() in {".mp4", ".mov", ".m4v"}
                    and not path.name.startswith(".")
                    and not path.name.endswith(".part")
                    for path in reassembled_dir.iterdir()
                ):
                    return None
            except OSError:
                unreadable_dirs.append(reassembled_dir)
                continue
        if unreadable_dirs:
            checked = "\n".join(str(path) for path in unreadable_dirs[:3])
            return f"reassembled 目录读取失败，请检查权限：\n{checked}"
        checked = "\n".join(str(path) for path in checked_dirs[:3])
        if not checked:
            return f"本机 processed 下未找到这个任务的 reassembled 目录：{processed_dir}"
        return f"本机 processed/reassembled 未找到可用重组视频，已检查：\n{checked}"

    def generate_jianying_preview_for_task(self, task: dict[str, Any]) -> None:
        task_id = str(task.get("id") or "")
        if not task_id:
            QMessageBox.warning(self, "剪映工程图", "任务 ID 为空，无法生成剪映工程图。")
            return
        unavailable_reason = self.jianying_preview_unavailable_reason(task)
        if unavailable_reason is not None:
            QMessageBox.information(self, "剪映工程图", unavailable_reason)
            return
        strategy = self.choose_jianying_project_strategy()
        if strategy is None:
            return
        self.jianying_preview_busy = True
        self.update_task_progress("正在生成剪映工程图预览", task_id, task)
        self.load_task_history(page=self.task_history_page, silent=True)
        self.run_async(
            "生成剪映工程图预览",
            lambda: self.runner().generate_jianying_project_preview_from_cache(task, strategy=strategy or None),
            self.handle_jianying_preview_done,
            log_result=False,
            on_failed=self.handle_jianying_preview_failed,
        )

    def choose_jianying_project_strategy(self) -> str | None:
        options = [("随机选择", "")]
        options.extend(
            (f"{JIANYING_PROJECT_STRATEGY_LABELS.get(strategy, strategy)}（{strategy}）", strategy)
            for strategy in JIANYING_PROJECT_STRATEGIES
        )
        labels = [label for label, _strategy in options]
        selected, ok = QInputDialog.getItem(
            self,
            "剪映工程图",
            "选择工程策略",
            labels,
            0,
            False,
        )
        if not ok:
            return None
        return dict(options).get(selected, "")

    def handle_jianying_preview_done(self, metadata: dict[str, object]) -> None:
        self.jianying_preview_busy = False
        output_dir = self.jianying_preview_output_dir(metadata)
        screenshots = [
            Path(str(path))
            for path in metadata.get("jianyingProjectScreenshots", [])
            if path
        ] if isinstance(metadata, dict) else []
        strategy_label = str(metadata.get("jianyingProjectStrategyLabel") or "默认工程")
        if output_dir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_dir)))
        self.load_task_history(page=self.task_history_page, silent=True)
        QMessageBox.information(
            self,
            "剪映工程图",
            f"已生成 {len(screenshots)} 张剪映工程图（{strategy_label}）。\n{output_dir or ''}",
        )

    def handle_jianying_preview_failed(self, error: str) -> None:
        self.jianying_preview_busy = False
        self.load_task_history(page=self.task_history_page, silent=True)
        QMessageBox.critical(self, "剪映工程图", self.clean_error_message(error))

    @staticmethod
    def jianying_preview_output_dir(metadata: dict[str, object]) -> Path | None:
        if not isinstance(metadata, dict):
            return None
        output_dir = str(metadata.get("jianyingProjectOutputDir") or "").strip()
        if output_dir:
            return Path(output_dir)
        screenshots = metadata.get("jianyingProjectScreenshots")
        if isinstance(screenshots, list) and screenshots:
            return Path(str(screenshots[0])).parent
        return None

    def force_stop_distribution_task(self, task: dict[str, Any]) -> None:
        task_id = str(task.get("id") or "")
        if not task_id:
            QMessageBox.warning(self, "强制停止", "任务 ID 为空，无法停止。")
            return
        if not self.is_task_force_stoppable(task):
            QMessageBox.information(self, "强制停止", "只有待执行或执行中的任务可以强制停止。")
            return
        drama_title = str(task.get("dramaTitle") or task.get("dramaId") or "当前任务")
        answer = QMessageBox.question(
            self,
            "强制停止",
            f"确定强制停止「{drama_title}」吗？\n\n任务会被标记为已取消，不会自动重新入队。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        if self.is_current_task_running(task_id):
            self.task_cancel_event.set()
            self.task_pause_event.clear()
            self.task_skip_event.clear()
            self.update_task_progress("正在强制停止当前任务...", task_id, task)
            self.update_task_control_buttons()
        self.run_async(
            "强制停止任务",
            lambda: self.api().post(f"/desktop/tasks/{task_id}/force-stop"),
            lambda _task: self.handle_task_force_stopped(task_id),
            log_result=False,
        )

    def handle_task_force_stopped(self, task_id: str) -> None:
        if self.current_task_id == task_id:
            self.update_task_progress("任务已强制停止", task_id)
        self.load_task_history(page=self.task_history_page)
        self.update_task_control_buttons()
        QMessageBox.information(self, "强制停止", "任务已强制停止。")

    def retry_distribution_task(self, task: dict[str, Any]) -> None:
        task_id = str(task.get("id") or "")
        if not task_id:
            QMessageBox.warning(self, "重试任务", "任务 ID 为空，无法重试。")
            return
        if not self.is_task_retryable(task):
            QMessageBox.information(self, "重试任务", "只有失败、已取消或执行中的任务可以重试。")
            return
        if self.is_current_task_running(task_id):
            QMessageBox.information(self, "重试任务", "这个任务正在本机执行中，请先暂停或跳过后再重试。")
            return
        if self.manual_publish_busy or self.auto_task_busy:
            QMessageBox.information(
                self,
                "重试任务",
                "已有发布任务在执行中，请等待当前任务结束。",
            )
            return
        self.set_manual_publish_busy(True)
        self.task_cancel_event.clear()
        self.task_pause_event.clear()
        self.task_skip_event.clear()
        self.task_paused = False
        self.update_task_progress("正在检查重试条件", task_id)
        self.run_async(
            "检查重试条件",
            lambda: self.api().get("/desktop/media-accounts"),
            lambda media_accounts: self.retry_task_if_ready(task, media_accounts),
            log_result=False,
        )

    def retry_task_if_ready(self, task: dict[str, Any], media_accounts: list[dict[str, Any]]) -> None:
        self.media_accounts = media_accounts
        block_reason = self.auto_task_block_reason(media_accounts) or self.contract_task_block_reason(media_accounts)
        task_id = str(task.get("id") or "")
        if block_reason:
            self.set_manual_publish_busy(False)
            QMessageBox.warning(self, "重试任务", block_reason)
            self.update_task_progress("重试未启动", task_id)
            return
        self.update_task_progress("重试请求已受理，正在执行任务", task_id)
        self.run_async(
            "重试任务",
            lambda: self.retry_task_once(task),
            self.handle_retry_task_done,
        )

    @staticmethod
    def is_task_retryable(task: dict[str, Any]) -> bool:
        return str(task.get("status") or "") in {
            "FAILED",
            "CANCELLED",
            "CLAIMED",
            "DOWNLOADING",
            "PROCESSING",
            "UPLOADING",
        }

    @staticmethod
    def is_task_force_stoppable(task: dict[str, Any]) -> bool:
        return str(task.get("status") or "") in {
            "CLAIMED",
            "PENDING",
            "DOWNLOADING",
            "PROCESSING",
            "UPLOADING",
        }

    def is_current_task_running(self, task_id: str) -> bool:
        return bool(
            task_id
            and task_id == self.current_task_id
            and (self.manual_publish_busy or self.auto_task_busy)
        )

    @staticmethod
    def should_retry_from_upload_cache(task: dict[str, Any]) -> bool:
        if not DesktopWindow.is_task_retryable(task):
            return False
        try:
            progress = int(task.get("progress") or 0)
        except (TypeError, ValueError):
            progress = 0
        return progress >= 75 or str(task.get("status") or "") == "UPLOADING"

    def retry_task_once(self, task: dict[str, Any]) -> str:
        task_id = str(task.get("id") or "")
        claimed_task = self.api().post(
            f"/desktop/tasks/{task_id}/retry",
            {"deviceId": self.settings.device_id, "asyncPreparation": True},
        )
        runner = self.runner()
        if self.should_retry_from_upload_cache(task):
            return runner.execute_task_from_upload_cache(claimed_task)
        return runner.execute_task(claimed_task)

    def handle_retry_task_done(self, result: str) -> None:
        self.set_manual_publish_busy(False)
        if result == "failed":
            self.update_task_progress("任务失败", self.current_task_id)
            reason = self.current_task_error_message() or "发布任务执行失败，请查看最近错误或日志。"
            QMessageBox.warning(self, "重试任务", f"任务重试失败：\n{reason}")
        elif result == "cancelled":
            self.task_cancel_event.clear()
            self.update_task_progress("任务已停止，可重新分发", self.current_task_id)
            QMessageBox.information(self, "重试任务", "任务已停止，可重新分发。")
        elif result == "paused":
            self.task_paused = True
            self.update_task_progress("任务已暂停，可恢复执行", self.current_task_id)
            QMessageBox.information(self, "重试任务", "任务已暂停，可点击“恢复”继续。")
        elif result == "skipped":
            self.task_paused = False
            self.task_skip_event.clear()
            self.update_task_progress("任务已跳过，已放回池里", None)
            QMessageBox.information(self, "重试任务", "任务已跳过，并已放回待执行池。")
        elif result == "ready-for-review":
            self.update_task_progress("提审未自动提交，任务未完成", self.current_task_id)
            QMessageBox.warning(self, "重试任务", "视频已上传但提审未自动提交，请重试任务或查看日志。")
        else:
            self.update_task_progress("任务完成", self.current_task_id)
            QMessageBox.information(self, "重试任务", "任务已重新执行完成。")
        self.load_task_history(page=self.task_history_page)

    @staticmethod
    def clean_error_message(error: str) -> str:
        if not error:
            return "操作失败"
        lines = [line.strip() for line in error.splitlines() if line.strip()]
        if not lines:
            return "操作失败"
        playwright_hint = DesktopWindow.playwright_error_hint(lines)
        if playwright_hint:
            return playwright_hint
        message = lines[-1] if lines[0].startswith("Traceback") else lines[0]
        if ": " in message:
            prefix, detail = message.split(": ", 1)
            if prefix.endswith("Error") or prefix.endswith("Exception"):
                return detail
        return message or "操作失败"

    @staticmethod
    def playwright_error_hint(lines: list[str]) -> str | None:
        joined = "\n".join(lines)
        hints = []
        if "Target page, context or browser has been closed" in joined:
            hints.append("浏览器页面已关闭")
        if "变现类型|收益类型|付费类型" in joined or "变现类型" in joined:
            hints.append("等待变现类型控件失败")
        return " / ".join(hints) if hints else None

    def load_dramas(self, page: int = 0, *, silent: bool = False) -> None:
        filter_value = self.current_drama_download_filter()
        keyword = self.current_drama_keyword()
        request_page = 0
        request_size = 1000
        path = self.build_drama_list_path(page=request_page, size=request_size, keyword=keyword)

        def render(result: dict[str, Any]) -> None:
            rows = self.filter_recent_dramas(result.get("content") or [])
            if filter_value == "PRIORITIZED":
                rows = [row for row in rows if self.is_drama_prioritized(row)]
                self.drama_page = 0
                self.drama_total_pages = 1
                self.drama_total_elements = len(rows)
            elif filter_value != "ALL":
                rows = [row for row in rows if self.drama_download_status(row) == filter_value]
                self.drama_page = 0
                self.drama_total_pages = 1
                self.drama_total_elements = len(rows)
            else:
                self.drama_page = 0
                self.drama_total_pages = 1
                self.drama_total_elements = len(rows)
            self.render_drama_table(rows)
            self.drama_page_label.setText(
                f"共 {self.drama_total_elements} 条 · 第 {self.drama_page + 1}/{self.drama_total_pages} 页"
            )

        self.run_async(
            "加载短剧库",
            lambda: self.api().get(path),
            render,
            log_result=False,
            log_activity=not silent,
            on_failed=self.handle_silent_refresh_failed if silent else None,
        )

    @classmethod
    def filter_recent_dramas(cls, rows: list[Any], days: int = 7) -> list[dict[str, Any]]:
        cutoff = datetime.now().astimezone() - timedelta(days=days)
        recent: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            listed_at = cls.drama_listed_at(row)
            if listed_at and listed_at >= cutoff:
                recent.append(row)
        return recent

    @classmethod
    def drama_listed_at(cls, drama: dict[str, Any]) -> datetime | None:
        for key in ("listedAt", "publishedAt", "createdAt"):
            value = drama.get(key)
            if not value:
                continue
            parsed = cls.parse_server_datetime(value)
            if parsed:
                return parsed
        return None

    def render_drama_table(self, rows: list[dict[str, Any]]) -> None:
        self.current_drama_rows = rows
        self.drama_table.setRowCount(len(rows))
        for row_index, drama in enumerate(rows):
            cover_url = self.resolve_resource_url(str(drama.get("coverUrl") or ""))
            self.drama_table.setCellWidget(row_index, 0, self.drama_cover_widget(cover_url))
            values = self.drama_row_values(drama)
            download_status, downloaded_count, _ = self.drama_download_info(drama)
            values[8] = download_status
            values[9] = str(downloaded_count)
            for column, value in enumerate(values, start=1):
                item = self.left_aligned_table_item(value)
                item.setToolTip(value)
                self.drama_table.setItem(row_index, column, item)
            self.drama_table.setCellWidget(row_index, 12, self.drama_actions_widget(drama))
            self.drama_table.setRowHeight(row_index, 86)

    def show_drama_detail(self, row: int, _: int = 0) -> None:
        if row < 0 or row >= len(self.current_drama_rows):
            return
        drama = self.current_drama_rows[row]
        title = str(drama.get("aiTitle") or drama.get("title") or "短剧详情")
        original_title = str(drama.get("title") or "")
        summary = str(drama.get("aiSummary") or drama.get("summary") or "暂无AI简介")
        categories = "，".join(str(name) for name in drama.get("categoryNames") or [])
        if not categories:
            categories = "，".join(str(code) for code in drama.get("categoryIds") or [])
        status, downloaded_count, total_count = self.drama_download_info(drama)
        total_count = total_count or self.drama_episode_count(drama)

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(False)
        dialog.setMinimumSize(760, 520)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(16)
        cover_url = self.resolve_resource_url(str(drama.get("coverUrl") or ""))
        top.addWidget(self.drama_detail_cover_widget(cover_url), alignment=Qt.AlignTop)

        info = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("panelTitle")
        title_label.setWordWrap(True)
        info.addWidget(title_label)
        if original_title and original_title != title:
            original = QLabel(f"原名：{original_title}")
            original.setObjectName("mutedText")
            original.setWordWrap(True)
            info.addWidget(original)
        info.addWidget(QLabel(f"分类：{categories or '-'}"))
        info.addWidget(QLabel(f"评分：{self.format_rating(drama.get('rating'))}"))
        info.addWidget(QLabel(f"剧源：{self.drama_source_label(drama)}"))
        info.addWidget(QLabel(f"集数：{total_count}"))
        info.addWidget(QLabel(f"成本金额：{self.format_cost_amount_wan(drama)}"))
        info.addWidget(QLabel(f"素材状态：{self.drama_preparation_status_label(drama)}"))
        info.addWidget(QLabel(f"下载状态：{status}"))
        info.addWidget(QLabel(f"已下载集数：{downloaded_count}/{total_count}"))
        info.addWidget(QLabel(f"上架时间：{self.format_datetime(self.drama_listed_at_value(drama))}"))
        info.addStretch(1)
        top.addLayout(info, 1)
        layout.addLayout(top)

        summary_title = QLabel("AI简介")
        summary_title.setObjectName("panelTitle")
        layout.addWidget(summary_title)
        summary_text = QTextEdit()
        summary_text.setReadOnly(True)
        summary_text.setPlainText(summary)
        summary_text.setMinimumHeight(180)
        layout.addWidget(summary_text, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.show()

    def current_drama_download_filter(self) -> str:
        if not hasattr(self, "drama_download_filter"):
            return "ALL"
        return str(self.drama_download_filter.currentData() or "ALL")

    def current_drama_keyword(self) -> str:
        if not hasattr(self, "drama_keyword_input"):
            return ""
        return self.drama_keyword_input.text().strip()

    def clear_drama_keyword(self) -> None:
        self.drama_keyword_input.clear()
        self.load_dramas(page=0)

    @staticmethod
    def build_drama_list_path(page: int, size: int, keyword: str = "") -> str:
        params = [("page", str(page)), ("size", str(size)), ("sort", "updatedAt,desc")]
        if keyword.strip():
            params.append(("keyword", keyword.strip()))
        return f"/desktop/dramas?{urlencode(params, safe=',')}"

    @classmethod
    def drama_row_values(cls, drama: dict[str, Any]) -> list[str]:
        categories = "，".join(str(name) for name in drama.get("categoryNames") or [])
        if not categories:
            categories = "，".join(str(code) for code in drama.get("categoryIds") or [])
        return [
            str(drama.get("aiTitle") or drama.get("title") or "-"),
            cls.drama_source_label(drama),
            str(drama.get("aiSummary") or drama.get("summary") or "-"),
            cls.format_rating(drama.get("rating")),
            categories or "-",
            str(cls.drama_episode_count(drama)),
            cls.format_cost_amount_wan(drama),
            cls.drama_preparation_status_label(drama),
            "-",
            "-",
            cls.format_datetime(cls.drama_listed_at_value(drama)),
        ]

    @staticmethod
    def drama_listed_at_value(drama: dict[str, Any]) -> Any:
        return drama.get("listedAt") or drama.get("publishedAt") or drama.get("createdAt") or ""

    @classmethod
    def drama_source_label(cls, drama: dict[str, Any]) -> str:
        provider = str(drama.get("providerName") or drama.get("dramaProviderName") or "").strip()
        if provider:
            return cls.drama_provider_label(provider)
        source = str(drama.get("source") or drama.get("dramaSource") or "").strip()
        if source in ("", "BAIDU_PAN"):
            return "网盘"
        if source == "HONGGUO_52API":
            return "红果"
        return source

    @staticmethod
    def drama_provider_label(provider: str) -> str:
        labels = {
            "HONGGUO": "红果",
            "52API_HONGGUO": "红果",
            "52API_HEMA": "河马短剧",
            "52API_XIFAN": "喜番短剧",
            "52API_HUOLONG": "火龙漫剧",
            "52API_DONGLI": "东梨短剧",
            "52API_XINGYA": "星芽短剧",
            "52API_WEIGUAN": "围观短剧",
            "52API_DOUYIN": "抖音短剧",
            "52API_QIMAO": "七猫短剧",
            "52API_BAIDU": "百度短剧",
        }
        return labels.get(provider, provider)

    @classmethod
    def drama_preparation_status_label(cls, drama: dict[str, Any]) -> str:
        preparation_status = str(drama.get("preparationStatus") or "").strip().upper()
        status = str(drama.get("status") or "").strip().upper()
        if preparation_status == "PENDING_AI_ASSETS" or status == "DRAFT":
            return "待生成素材"
        if preparation_status == "READY" or status == "READY":
            return "可分发"
        return cls.drama_status_label(status)

    @classmethod
    def format_cost_amount_wan(cls, drama: dict[str, Any]) -> str:
        value = cls.drama_cost_amount_wan(drama)
        return f"{value}万" if value > 0 else "-"

    @staticmethod
    def drama_cost_amount_wan(drama: dict[str, Any]) -> int:
        for key in ("costAmountWan", "priceWan", "price", "cost"):
            value = drama.get(key)
            if value is not None:
                try:
                    return max(int(float(str(value))), 0)
                except (TypeError, ValueError):
                    pass
        return 0

    @staticmethod
    def drama_episode_count(drama: dict[str, Any]) -> int:
        episode_count = drama.get("episodeCount")
        if episode_count is not None:
            try:
                return max(int(episode_count), 0)
            except (TypeError, ValueError):
                return 0
        return len(drama.get("episodes") or [])

    @classmethod
    def drama_total_minutes(cls, drama: dict[str, Any]) -> int:
        for key in ("episodeMinutes", "totalMinutes", "durationMinutes", "totalDurationMinutes"):
            value = drama.get(key)
            if value is not None:
                try:
                    return max(int(value), 0)
                except (TypeError, ValueError):
                    pass
        episodes = drama.get("episodes") or []
        total_seconds = 0
        for episode in episodes:
            if not isinstance(episode, dict):
                continue
            value = episode.get("durationSeconds") or episode.get("seconds")
            if value is None:
                continue
            try:
                total_seconds += max(int(value), 0)
            except (TypeError, ValueError):
                pass
        if total_seconds:
            return max(round(total_seconds / 60), 1)
        return cls.drama_episode_count(drama)

    @staticmethod
    def contract_drama_title(drama: dict[str, Any]) -> str:
        return str(drama.get("aiTitle") or drama.get("title") or drama.get("publishTitle") or "未命名短剧")

    @staticmethod
    def non_negative_int(value: object, default: int = 0) -> int:
        if value is None:
            return default
        try:
            return max(int(float(str(value))), 0)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def non_negative_float(value: object, default: float = 0.0) -> float:
        if value is None:
            return default
        try:
            return max(float(str(value)), 0.0)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def estimate_contract_cost_amount_wan(total_minutes: int) -> int:
        if total_minutes <= 0:
            return 0
        cost = (total_minutes + 9) // 10
        return max(2, min(20, cost))

    @classmethod
    def contract_minutes_from_seconds(cls, total_seconds: float) -> int:
        if total_seconds <= 0:
            return 0
        return max(round(total_seconds / 60), 1)

    def contract_drama_parameter_values(self, drama: dict[str, Any]) -> dict[str, int]:
        local_parameters = self.local_contract_drama_parameters(drama) or {}
        local_episode_count = self.non_negative_int(local_parameters.get("episodeCount"))
        local_total_minutes = self.non_negative_int(local_parameters.get("totalMinutes"))
        episode_count = local_episode_count or self.drama_episode_count(drama)
        total_minutes = local_total_minutes or self.drama_total_minutes(drama)
        if local_total_minutes > 0:
            cost_amount_wan = self.estimate_contract_cost_amount_wan(local_total_minutes)
        else:
            cost_amount_wan = self.drama_cost_amount_wan(drama)
            if cost_amount_wan <= 0 and total_minutes > 0:
                cost_amount_wan = self.estimate_contract_cost_amount_wan(total_minutes)
        return {
            "episodeCount": episode_count,
            "totalMinutes": total_minutes,
            "priceWan": cost_amount_wan,
        }

    def local_contract_drama_parameters(self, drama: dict[str, Any]) -> dict[str, int] | None:
        settings = getattr(self, "settings", None)
        base_dirs = [
            getattr(settings, "processed_dir", None),
            getattr(settings, "downloads_dir", None),
        ]
        for base_dir in base_dirs:
            if not base_dir:
                continue
            for drama_dir in self.contract_drama_dir_candidates(Path(base_dir), drama):
                parameters = self.contract_parameters_from_reassembled_dir(
                    drama_dir / VIDEO_REASSEMBLY_DIRNAME
                )
                if parameters:
                    return parameters
        return None

    @classmethod
    def contract_drama_dir_candidates(cls, base_dir: Path, drama: dict[str, Any]) -> list[Path]:
        drama_id = str(drama.get("dramaId") or drama.get("id") or "").strip()
        download_plan = {**drama, "dramaId": drama_id}
        candidates: list[Path] = []

        def add_candidate(path: Path) -> None:
            if path not in candidates:
                candidates.append(path)

        add_candidate(base_dir / drama_directory_name(download_plan))
        if drama_id:
            add_candidate(base_dir / drama_id)
        if drama_id and not any(path.exists() for path in candidates) and base_dir.is_dir():
            suffix = f"-{drama_id}"
            try:
                for child in base_dir.iterdir():
                    if child.is_dir() and (child.name == drama_id or child.name.endswith(suffix)):
                        add_candidate(child)
            except OSError:
                pass
        return candidates

    @classmethod
    def contract_parameters_from_reassembled_dir(cls, directory: Path) -> dict[str, int] | None:
        manifest = read_download_episode_manifest(directory)
        if manifest:
            parameters = cls.contract_parameters_from_episode_manifest(manifest)
            if parameters:
                return parameters
        return cls.contract_parameters_from_reassembled_files(directory)

    @classmethod
    def contract_parameters_from_episode_manifest(cls, manifest: dict[str, Any]) -> dict[str, int] | None:
        raw_files = manifest.get("files")
        files = [entry for entry in raw_files if isinstance(entry, dict)] if isinstance(raw_files, list) else []
        episode_count = cls.non_negative_int(manifest.get("episodeCount"))
        if episode_count <= 0:
            episode_count = len(files)
        total_minutes = cls.non_negative_int(
            manifest.get("totalMinutes") or manifest.get("durationMinutes") or manifest.get("episodeMinutes")
        )
        total_seconds = cls.total_seconds_from_manifest_entries(files)
        if total_seconds > 0:
            total_minutes = cls.contract_minutes_from_seconds(total_seconds)
        if episode_count > 0 or total_minutes > 0:
            return {"episodeCount": episode_count, "totalMinutes": total_minutes}
        return None

    @classmethod
    def total_seconds_from_manifest_entries(cls, entries: list[dict[str, Any]]) -> float:
        total_seconds = 0.0
        for entry in entries:
            episode = entry.get("episode") if isinstance(entry.get("episode"), dict) else {}
            duration_candidates = (
                entry.get("durationSeconds"),
                entry.get("seconds"),
                episode.get("durationSeconds"),
                episode.get("seconds"),
                episode.get("duration"),
            )
            for value in duration_candidates:
                duration = cls.non_negative_float(value)
                if duration > 0:
                    total_seconds += duration
                    break
        return total_seconds

    @classmethod
    def contract_parameters_from_reassembled_files(cls, directory: Path) -> dict[str, int] | None:
        if not directory.is_dir():
            return None
        files = sorted(
            path
            for path in directory.glob("*.mp4")
            if path.is_file() and not path.name.startswith(".")
        )
        if not files:
            return None
        total_seconds = cls.total_seconds_from_reassembled_signature(files)
        return {
            "episodeCount": len(files),
            "totalMinutes": cls.contract_minutes_from_seconds(total_seconds),
        }

    @classmethod
    def total_seconds_from_reassembled_signature(cls, files: list[Path]) -> float:
        file_names = {path.name for path in files}
        for file in files:
            signature = cls.read_contract_json_file(file.with_name(f"{file.name}.aidrama.json"))
            segments = signature.get("segments") if isinstance(signature, dict) else None
            if not isinstance(segments, list):
                continue
            total_seconds = 0.0
            matched_count = 0
            for segment in segments:
                if not isinstance(segment, dict) or segment.get("file") not in file_names:
                    continue
                duration = cls.non_negative_float(segment.get("durationSeconds"))
                if duration <= 0:
                    continue
                total_seconds += duration
                matched_count += 1
            if matched_count > 0:
                return total_seconds
        return 0.0

    @staticmethod
    def read_contract_json_file(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def contract_drama_display_label(self, drama: dict[str, Any]) -> str:
        title = self.contract_drama_title(drama)
        count = self.contract_drama_parameter_values(drama).get("episodeCount", 0)
        return f"{title}（{count}集）" if count > 0 else title

    @staticmethod
    def normalize_contract_drama_combo_text(text: str) -> str:
        value = text.strip()
        if value.endswith("集）") and "（" in value:
            return value.rsplit("（", 1)[0].strip()
        return value

    def current_contract_drama(self) -> dict[str, Any] | None:
        drama = self.contract_drama_input.currentData()
        if isinstance(drama, dict):
            return drama
        current_text = self.normalize_contract_drama_combo_text(self.contract_drama_input.currentText())
        if not current_text:
            return None
        for option in getattr(self, "contract_drama_options", []):
            if not isinstance(option, dict):
                continue
            if current_text == self.contract_drama_title(option):
                return option
        return None

    def drama_download_status(self, drama: dict[str, Any]) -> str:
        return self.drama_download_info(drama)[0]

    @staticmethod
    def is_drama_prioritized(drama: dict[str, Any]) -> bool:
        return bool(drama.get("prioritized"))

    def drama_download_info(self, drama: dict[str, Any]) -> tuple[str, int, int]:
        drama_id = str(drama.get("id") or "")
        episodes = drama.get("episodes") or []
        expected_count = self.drama_episode_count(drama)
        target_dir = self.settings.downloads_dir / drama_id
        if not drama_id or not target_dir.exists():
            return "未下载", 0, expected_count
        files = sorted(target_dir.glob("*.mp4"))
        if not files:
            return "未下载", 0, expected_count
        by_episode = {f"{int(item.get('episodeNo') or 0):03d}.mp4": int(item.get("size") or 0) for item in episodes}
        downloaded_count = 0
        for file in files:
            expected_size = by_episode.get(file.name)
            if expected_size and file.stat().st_size < expected_size:
                continue
            downloaded_count += 1
        if expected_count and downloaded_count >= expected_count:
            return "已下载", downloaded_count, expected_count
        return "下载中", downloaded_count, expected_count

    def drama_actions_widget(self, drama: dict[str, Any]) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        status = self.drama_download_status(drama)
        if status in {"已下载", "下载中"}:
            open_button = QPushButton("打开目录")
            open_button.clicked.connect(lambda _=False, item=drama: self.open_drama_download_dir(item))
            layout.addWidget(open_button)
        priority_button = QPushButton("优先")
        if self.is_drama_prioritized(drama):
            priority_button.setText("已优先")
            priority_button.setObjectName("dangerButton")
        priority_button.clicked.connect(lambda _=False, item=drama: self.prioritize_drama(item))
        layout.addWidget(priority_button)
        layout.addStretch(1)
        return widget

    def open_drama_download_dir(self, drama: dict[str, Any]) -> None:
        drama_id = str(drama.get("id") or "")
        if not drama_id:
            return
        target_dir = self.settings.downloads_dir / drama_id
        target_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_dir)))

    def prioritize_drama(self, drama: dict[str, Any]) -> None:
        drama_id = str(drama.get("id") or "")
        title = str(drama.get("aiTitle") or drama.get("title") or drama_id)
        if not drama_id:
            return
        self.run_async(
            f"优先分发 {title}",
            lambda: self.api().post(f"/desktop/dramas/{drama_id}/prioritize", {}),
            lambda _: self.on_drama_prioritized(title),
            log_result=False,
        )

    def on_drama_prioritized(self, title: str) -> None:
        self.append_log(f"已加入优先分发：{title}")
        QMessageBox.information(self, "优先分发", "已加入优先队列，点击发布下一条执行。")
        self.load_dramas(page=self.drama_page)

    @staticmethod
    def format_rating(value: Any) -> str:
        try:
            rating = int(value) if value is not None else 5
        except (TypeError, ValueError):
            rating = 5
        rating = min(max(rating, 1), 5)
        return f"{rating}分"

    def resolve_resource_url(self, value: str) -> str:
        if not value:
            return ""
        if urlparse(value).scheme in {"http", "https"}:
            return value
        server_root = self.settings.server_url.rstrip("/")
        if server_root.endswith("/api"):
            server_root = server_root[:-4]
        return urljoin(f"{server_root}/", value.lstrip("/"))

    @staticmethod
    def empty_drama_cover_label(text: str = "无封面") -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setFixedSize(64, 76)
        label.setObjectName("coverThumb")
        return label

    def drama_cover_widget(self, cover_url: str) -> QLabel:
        label = self.empty_drama_cover_label()
        if not cover_url:
            return label
        label.setProperty("coverUrl", cover_url)
        if cover_url in self.cover_cache:
            self.apply_drama_cover_bytes(label, self.cover_cache[cover_url])
            return label
        cached_cover = self.read_cached_drama_cover(cover_url)
        if cached_cover:
            self.cover_cache[cover_url] = cached_cover
            self.apply_drama_cover_bytes(label, cached_cover)
            return label
        label.setText("封面\n加载中")
        self.load_cover_async(cover_url, label)
        return label

    def drama_cover_cache_path(self, cover_url: str) -> Path:
        cache_dir = self.settings.work_dir / "dramas" / "covers"
        return cache_dir / f"{sha256(cover_url.encode('utf-8')).hexdigest()}.img"

    def read_cached_drama_cover(self, cover_url: str) -> bytes | None:
        if not hasattr(self, "settings"):
            return None
        try:
            cache_path = self.drama_cover_cache_path(cover_url)
            if cache_path.is_file():
                return cache_path.read_bytes()
        except OSError:
            return None
        return None

    def write_cached_drama_cover(self, cover_url: str, content: bytes | None) -> None:
        if not content:
            return
        if not hasattr(self, "settings"):
            return
        try:
            cache_path = self.drama_cover_cache_path(cover_url)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = cache_path.with_suffix(".tmp")
            temp_path.write_bytes(content)
            temp_path.replace(cache_path)
        except OSError:
            return

    def load_cover_async(self, cover_url: str, label: QLabel) -> None:
        pending = self.cover_loading.setdefault(cover_url, [])
        pending.append(label)
        if len(pending) > 1:
            return

        def fetch_cover() -> tuple[str, bytes | None]:
            try:
                response = httpx.get(cover_url, timeout=5)
                response.raise_for_status()
                return cover_url, response.content
            except Exception:  # noqa: BLE001
                return cover_url, None

        worker = Worker(fetch_cover)
        worker.signals.done.connect(self.on_cover_loaded)
        worker.signals.failed.connect(lambda _: self.on_cover_loaded((cover_url, None)))
        worker.signals.done.connect(lambda _: self._release_worker(worker))
        worker.signals.failed.connect(lambda _: self._release_worker(worker))
        self.active_workers.append(worker)
        self.thread_pool.start(worker)

    def on_cover_loaded(self, result: object) -> None:
        if not isinstance(result, tuple) or len(result) != 2:
            return
        cover_url, content = result
        if not isinstance(cover_url, str):
            return
        cover_bytes = content if isinstance(content, bytes) else None
        self.cover_cache[cover_url] = cover_bytes
        self.write_cached_drama_cover(cover_url, cover_bytes)
        labels = self.cover_loading.pop(cover_url, [])
        for label in labels:
            if label.property("coverUrl") == cover_url:
                self.apply_drama_cover_bytes(label, cover_bytes)

    @staticmethod
    def apply_drama_cover_bytes(label: QLabel, content: bytes | None) -> None:
        if not content:
            label.setPixmap(QPixmap())
            label.setText("封面\n加载失败")
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(content):
            label.setText("")
            label.setPixmap(pixmap.scaled(56, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            return
        label.setPixmap(QPixmap())
        label.setText("封面\n加载失败")

    @staticmethod
    def drama_detail_cover_widget(cover_url: str) -> QLabel:
        label = QLabel("无封面")
        label.setAlignment(Qt.AlignCenter)
        label.setFixedSize(180, 240)
        label.setObjectName("coverThumb")
        if not cover_url:
            return label
        try:
            response = httpx.get(cover_url, timeout=5)
            response.raise_for_status()
            pixmap = QPixmap()
            if pixmap.loadFromData(response.content):
                label.setText("")
                label.setPixmap(pixmap.scaled(172, 232, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        except Exception:  # noqa: BLE001
            label.setText("封面\n加载失败")
        return label

    @staticmethod
    def drama_status_label(status: str) -> str:
        labels = {
            "DRAFT": "草稿",
            "READY": "可分发",
            "DISTRIBUTING": "分发中",
            "ARCHIVED": "归档",
        }
        return labels.get(status, status or "-")

    @staticmethod
    def media_platform_options() -> list[tuple[str, str]]:
        return [
            ("WECHAT_VIDEO", "视频号"),
            ("DOUYIN", "抖音"),
            ("TIKTOK", "TikTok"),
        ]

    @staticmethod
    def media_platform_label(platform: str) -> str:
        labels = dict(DesktopWindow.media_platform_options())
        return labels.get(platform, platform or "-")

    @staticmethod
    def media_status_label(status: str) -> str:
        labels = {
            "BINDING": "绑定中",
            "ACTIVE": "可用",
            "PAUSED": "暂停",
            "EXPIRED": "登录过期",
            "DISABLED": "已停用",
        }
        return labels.get(status, status or "-")

    @staticmethod
    def distribution_task_status_options() -> list[tuple[str, str]]:
        return [
            ("全部状态", "ALL"),
            ("待执行", "PENDING"),
            ("已领取", "CLAIMED"),
            ("下载中", "DOWNLOADING"),
            ("上传中", "UPLOADING"),
            ("成功", "SUCCEEDED"),
            ("失败", "FAILED"),
            ("已取消", "CANCELLED"),
        ]

    @staticmethod
    def distribution_task_status_label(status: str) -> str:
        labels = {
            "PENDING": "待执行",
            "CLAIMED": "已领取",
            "DOWNLOADING": "下载中",
            "PROCESSING": "处理中",
            "UPLOADING": "上传中",
            "SUCCEEDED": "成功",
            "FAILED": "失败",
            "CANCELLED": "已取消",
        }
        return labels.get(status, status or "-")

    def media_category_label(self, category_ids: list[str] | None) -> str:
        if not category_ids:
            return "全部分类"
        names_by_code = {str(item.get("code") or item.get("id")): str(item.get("name") or item.get("code") or item.get("id")) for item in self.media_categories}
        return "，".join(names_by_code.get(str(category_id), str(category_id)) for category_id in category_ids)

    def media_row_values(self, item: dict[str, Any], policy: dict[str, Any]) -> list[str]:
        return [
            str(item.get("displayName", "")),
            self.media_platform_label(str(item.get("platform") or "")),
            str(item.get("externalAccountId", "") or "-"),
            self.media_status_label(str(item.get("status") or "")),
            str(item.get("deviceId", "") or "-"),
            self.format_datetime(str(item.get("lastVerifiedAt") or "")),
            "已保存" if item.get("loginStateRef") else "未保存",
            str(policy.get("dailyLimit", "-")),
            self.interval_minutes_label(policy.get("intervalMinutes")),
            self.media_category_label(policy.get("categoryIds") or []),
        ]

    @staticmethod
    def table_text_alignment() -> Qt.AlignmentFlag:
        return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter

    @classmethod
    def left_aligned_table_item(cls, value: str) -> QTableWidgetItem:
        item = QTableWidgetItem(value)
        item.setTextAlignment(cls.table_text_alignment())
        return item

    @classmethod
    def align_table_header_left(cls, table: QTableWidget) -> None:
        for column in range(table.columnCount()):
            header_item = table.horizontalHeaderItem(column)
            if header_item:
                header_item.setTextAlignment(cls.table_text_alignment())

    @staticmethod
    def interval_minutes_label(value: Any) -> str:
        if value in (None, ""):
            return "-"
        return f"{value} 分钟"

    @staticmethod
    def parse_server_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
            text = str(value).strip()
            if not text:
                return None
            normalized = text.replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(CHINA_TIMEZONE)

    @classmethod
    def format_datetime(cls, value: Any) -> str:
        parsed = cls.parse_server_datetime(value)
        if parsed:
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        if not value:
            return "-"
        return str(value).replace("T", " ")[:19]

    def open_create_media_dialog(self) -> None:
        self.media_platform_input.setCurrentIndex(0)
        self.media_name_input.clear()
        self.media_external_id_input.clear()
        self.update_media_create_fields()
        self.media_create_dialog.open()

    def update_media_create_fields(self) -> None:
        platform = str(self.media_platform_input.currentData() or "WECHAT_VIDEO")
        if platform == "WECHAT_VIDEO":
            self.media_name_input.setPlaceholderText("例如：主视频号")
            self.media_external_id_input.setPlaceholderText("视频号 ID")
            self.media_external_id_input.setEnabled(True)
            return
        self.media_name_input.setPlaceholderText(f"例如：{self.media_platform_label(platform)}主账号")
        self.media_external_id_input.setPlaceholderText("平台侧账号 ID")
        self.media_external_id_input.setEnabled(True)

    def load_media_accounts(self) -> None:
        if not self.media_categories:
            try:
                self.media_categories = self.api().get("/desktop/categories")
            except Exception as exception:  # noqa: BLE001
                self.append_log(f"加载分类失败：{exception}")

        def render(items: list[dict[str, Any]]) -> None:
            self.media_accounts = items
            self.media_table.setRowCount(len(items))
            for row, item in enumerate(items):
                policy = item.get("distributionPolicy") or {}
                values = self.media_row_values(item, policy)
                for column, value in enumerate(values):
                    table_item = self.left_aligned_table_item(str(value))
                    table_item.setToolTip(str(value))
                    self.media_table.setItem(row, column, table_item)
                self.media_table.setCellWidget(row, 10, self.media_actions_widget(item))
                self.media_table.setRowHeight(row, 38)
            if hasattr(self, "current_media_account_label"):
                self.current_media_account_label.setText(f"当前媒体号：{self.current_media_account_display()}")
            if hasattr(self, "current_media_backend_button"):
                self.current_media_backend_button.setEnabled(self.current_media_account() is not None)

        self.run_async("刷新媒体号", lambda: self.api().get("/desktop/media-accounts"), render)

    def media_actions_widget(self, account: dict[str, Any]) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        status = str(account.get("status") or "")
        toggle = QPushButton("启用" if status == "PAUSED" else "暂停")
        toggle.setEnabled(status in {"ACTIVE", "PAUSED"})
        toggle.clicked.connect(lambda _=False, item=account: self.toggle_media_enabled(item))
        open_browser = QPushButton("打开浏览器")
        open_browser.clicked.connect(lambda _=False, item=account: self.open_media_account(item))
        policy = QPushButton("编辑策略")
        policy.clicked.connect(lambda _=False, item=account: self.open_media_policy_dialog(item))
        layout.addWidget(toggle)
        layout.addWidget(open_browser)
        layout.addWidget(policy)
        layout.addStretch(1)
        return wrapper

    def toggle_media_enabled(self, account: dict[str, Any]) -> None:
        account_id = account.get("id")
        new_status = "ACTIVE" if account.get("status") == "PAUSED" else "PAUSED"

        def done(_: Any) -> None:
            self.load_media_accounts()

        self.run_async(
            "切换媒体号状态",
            lambda: self.api().patch(f"/desktop/media-accounts/{account_id}/status", {"status": new_status}),
            done,
        )

    def open_media_policy_dialog(self, account: dict[str, Any]) -> None:
        if not self.media_categories:
            try:
                self.media_categories = self.api().get("/desktop/categories")
            except Exception as exception:  # noqa: BLE001
                QMessageBox.critical(self, "编辑策略", f"加载分类失败：{exception}")
                return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"编辑策略 - {account.get('displayName') or '媒体号'}")
        dialog.setModal(True)
        dialog.setMinimumWidth(480)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        policy = account.get("distributionPolicy") or {}
        enabled_input = QCheckBox("参与自动上架")
        enabled_input.setChecked(bool(policy.get("enabled", True)) and account.get("status") != "PAUSED")
        layout.addWidget(enabled_input)

        hint = QLabel("不勾选分类表示全部分类都可以分发；勾选后只接收对应分类。")
        hint.setObjectName("mutedText")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        selected = {str(item) for item in policy.get("categoryIds") or []}
        category_list = QListWidget()
        category_list.setMinimumHeight(220)
        for category in self.media_categories:
            code = str(category.get("code") or category.get("id") or "")
            if not code:
                continue
            item = QListWidgetItem(str(category.get("name") or code))
            item.setData(Qt.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if code in selected else Qt.Unchecked)
            category_list.addItem(item)
        layout.addWidget(category_list)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(lambda: self.save_media_policy(dialog, account, enabled_input, category_list))
        layout.addWidget(buttons)
        dialog.open()

    def save_media_policy(
        self,
        dialog: QDialog,
        account: dict[str, Any],
        enabled_input: QCheckBox,
        category_list: QListWidget,
    ) -> None:
        account_id = account.get("id")
        current_policy = account.get("distributionPolicy") or {}
        category_ids = [
            str(category_list.item(index).data(Qt.UserRole))
            for index in range(category_list.count())
            if category_list.item(index).checkState() == Qt.Checked
        ]
        policy = {
            "categoryIds": category_ids,
            "dailyLimit": current_policy.get("dailyLimit", 3),
            "intervalMinutes": current_policy.get("intervalMinutes", 120),
            "enabled": enabled_input.isChecked(),
            "transcodePreset": current_policy.get("transcodePreset", "wechat-video-default"),
        }
        status = "ACTIVE" if enabled_input.isChecked() else "PAUSED"

        def task() -> dict[str, Any]:
            updated = self.api().put(f"/desktop/media-accounts/{account_id}/policy", policy)
            if account.get("status") in {"ACTIVE", "PAUSED"} and account.get("loginStateRef"):
                updated = self.api().patch(f"/desktop/media-accounts/{account_id}/status", {"status": status})
            return updated

        def done(_: Any) -> None:
            dialog.accept()
            self.load_media_accounts()

        self.run_async("保存媒体号策略", task, done)

    def create_media_account(self) -> None:
        display_name = self.media_name_input.text().strip()
        external_id = self.media_external_id_input.text().strip()
        platform = self.media_platform_input.currentData()
        if not display_name:
            QMessageBox.warning(self, "新增媒体号", "请填写媒体号名称。")
            return
        payload = {
            "platform": platform,
            "displayName": display_name,
            "externalAccountId": external_id,
            "deviceId": self.settings.device_id,
        }

        def task() -> dict[str, Any]:
            media = self.api().post("/desktop/media-accounts", payload)
            account_id = media.get("id")
            chrome = ChromeController(find_chrome(self.settings.chrome_path), self.settings.browser_profile_dir)
            profile_key = self.media_profile_key({**media, "externalAccountId": external_id}, account_id)
            login_state_ref = get_publisher(platform, chrome, profile_key).open_login()
            login_payload = {
                "loginStateRef": login_state_ref,
                "deviceId": self.settings.device_id,
                "verified": True,
            }
            return self.api().put(f"/desktop/media-accounts/{account_id}/login-state", login_payload)

        def done(_: Any) -> None:
            self.media_name_input.clear()
            self.media_external_id_input.clear()
            self.media_create_dialog.accept()
            self.load_media_accounts()

        self.run_async("新增媒体号", task, done)

    def selected_media_account(self) -> dict[str, Any] | None:
        row = self.media_table.currentRow()
        if row < 0 or row >= len(self.media_accounts):
            QMessageBox.warning(self, "媒体号", "请先选中一个媒体号。")
            return None
        return self.media_accounts[row]

    def bind_selected_media_account(self) -> None:
        account = self.selected_media_account()
        if not account:
            return
        self.open_media_account(account)

    def save_selected_media_login_state(self) -> None:
        account = self.selected_media_account()
        if not account:
            return
        self.save_media_login_state(account)

    def save_media_login_state(self, account: dict[str, Any]) -> None:
        account_id = account.get("id")
        chrome = ChromeController(find_chrome(self.settings.chrome_path), self.settings.browser_profile_dir)
        profile_key = self.media_profile_key(account, account_id)
        payload = {
            "loginStateRef": str(self.media_profile_dir(chrome, account, profile_key)),
            "deviceId": self.settings.device_id,
            "verified": True,
        }

        def done(_: Any) -> None:
            self.load_media_accounts()

        self.run_async(
            "保存登录信息",
            lambda: self.api().put(f"/desktop/media-accounts/{account_id}/login-state", payload),
            done,
        )

    def open_media_account(self, account: dict[str, Any]) -> None:
        platform = account.get("platform", "WECHAT_VIDEO")
        account_id = account.get("id")
        display_name = account.get("displayName", "")

        def task() -> str:
            chrome = ChromeController(find_chrome(self.settings.chrome_path), self.settings.browser_profile_dir)
            profile_key = self.media_profile_key(account, account_id)
            profile_dir = self.media_profile_dir(chrome, account, profile_key)
            login_state_ref = get_publisher(platform, chrome, profile_key, profile_dir=profile_dir).open_login()
            payload = {
                "loginStateRef": login_state_ref,
                "deviceId": self.settings.device_id,
                "verified": True,
            }
            self.api().put(f"/desktop/media-accounts/{account_id}/login-state", payload)
            return f"{display_name} 浏览器已打开，登录信息已保存"

        self.run_async("绑定媒体号", task)

    def open_current_media_account_backend(self) -> None:
        account = self.current_media_account()
        if not account:
            QMessageBox.warning(self, "媒体后台", "当前任务没有可用的媒体号信息。")
            return
        self.open_media_account(account)

    @staticmethod
    def media_profile_key(account: dict[str, Any], fallback: Any) -> str | None:
        external_id = str(account.get("externalAccountId") or "").strip()
        if external_id:
            return external_id
        if fallback:
            return str(fallback)
        return None

    @staticmethod
    def media_profile_dir(
        chrome: ChromeController,
        account: dict[str, Any],
        profile_key: str | None,
    ) -> Path:
        saved_ref = str(account.get("loginStateRef") or "").strip()
        if saved_ref:
            return Path(saved_ref)
        return chrome.platform_profile_dir(str(account.get("platform") or "WECHAT_VIDEO"), profile_key)

    def current_contract_key(self, contract_type: str) -> str:
        return contract_template_key(self.current_contract_platform(), contract_type)

    def current_contract_party_key(self, party: str) -> str:
        return contract_party_key(self.current_contract_platform(), party)

    def current_contract_platform(self) -> str:
        if not hasattr(self, "contract_platform_input"):
            return "WECHAT_VIDEO"
        return str(self.contract_platform_input.currentData() or "WECHAT_VIDEO")

    def current_contract_platform_name(self) -> str:
        if not hasattr(self, "contract_platform_input"):
            return "视频号"
        return self.contract_platform_input.currentText() or "视频号"

    def contract_type_name(self, contract_type: str) -> str:
        for key, label in required_contract_template_types(self.current_contract_platform()):
            if key == contract_type:
                return label
        return "购买合同"

    @staticmethod
    def contract_api_type(key: str) -> str:
        mapping = {
            "cost": "COST_CONTRACT",
            "purchase": "PURCHASE_CONTRACT",
            "rights": "RIGHTS_STATEMENT",
        }
        return mapping.get(key, "PURCHASE_CONTRACT")

    def current_contract_template_path(self, contract_type: str) -> Path | None:
        value = self.contract_templates.get(self.current_contract_key(contract_type))
        return Path(value) if value else None

    def contract_party_value(self, platform: str, party: str) -> str:
        editor_name = f"contract_{party}_input"
        if platform == self.current_contract_platform() and hasattr(self, editor_name):
            editor = getattr(self, editor_name)
            if isinstance(editor, QLineEdit):
                return editor.text().strip()
        return str(self.contract_templates.get(contract_party_key(platform, party)) or "").strip()

    def save_contract_party_config(self) -> None:
        if not hasattr(self, "contract_buyer_input") or not hasattr(self, "contract_seller_input"):
            return
        self.contract_templates[self.current_contract_party_key("buyer")] = self.contract_buyer_input.text().strip()
        self.contract_templates[self.current_contract_party_key("seller")] = self.contract_seller_input.text().strip()
        self.contract_store.save(self.contract_templates)
        self.load_selected_contract_template()

    def load_selected_contract_template(self) -> None:
        required_types = dict(required_contract_template_types(self.current_contract_platform()))
        if hasattr(self, "contract_party_widget"):
            self.contract_party_widget.setVisible(bool(required_contract_party_fields(self.current_contract_platform())))
        if hasattr(self, "contract_buyer_input") and hasattr(self, "contract_seller_input"):
            self.contract_buyer_input.setText(
                str(self.contract_templates.get(self.current_contract_party_key("buyer")) or "")
            )
            self.contract_seller_input.setText(
                str(self.contract_templates.get(self.current_contract_party_key("seller")) or "")
            )
        for contract_type, row_widget in getattr(self, "contract_template_row_widgets", {}).items():
            row_widget.setVisible(contract_type in required_types)
        for contract_type, label in required_types.items():
            if contract_type in getattr(self, "contract_template_label_widgets", {}):
                self.contract_template_label_widgets[contract_type].setText(label)
            template = self.current_contract_template_path(contract_type)
            display = str(template) if template else "未配置，请选择 .docx Word 模板"
            if contract_type in getattr(self, "contract_template_path_inputs", {}):
                self.contract_template_path_inputs[contract_type].setText(display)
        self.update_contract_generate_button()
        if hasattr(self, "contract_preview"):
            self.contract_preview.setPlainText(
                "点击“下载系统模版”获取后台模板并整理盖章签名。"
                "整理完成后点击“选择”回传本机 .docx 模板。当前媒体号需要的合同都配置后，才可以生成合同。"
            )

    def update_contract_generate_button(self) -> None:
        if hasattr(self, "contract_generate_button"):
            self.contract_generate_button.setEnabled(not self.missing_contract_config_labels(self.current_contract_platform()))

    def load_contract_dramas(self) -> None:
        if not hasattr(self, "contract_drama_input"):
            return
        self.contract_drama_input.blockSignals(True)
        self.contract_drama_input.clear()
        self.contract_drama_input.addItem("正在加载短剧库...", None)
        self.contract_drama_input.setEnabled(False)
        self.contract_drama_input.blockSignals(False)
        self.contract_episode_input.setText("0")
        self.contract_episode_minutes_input.setText("0")
        self.contract_price_input.setText("0")

        def render(result: dict[str, Any]) -> None:
            rows = result.get("content") or []
            self.contract_drama_options = [row for row in rows if isinstance(row, dict)]
            self.contract_drama_input.blockSignals(True)
            self.contract_drama_input.clear()
            if not self.contract_drama_options:
                self.contract_drama_input.addItem("暂无可选短剧", None)
                self.contract_drama_input.setEnabled(False)
            else:
                for drama in self.contract_drama_options:
                    self.contract_drama_input.addItem(self.contract_drama_display_label(drama), drama)
                self.contract_drama_input.setEnabled(True)
            self.contract_drama_input.blockSignals(False)
            self.on_contract_drama_selected()

        self.run_async(
            "加载合同短剧列表",
            lambda: self.api().get(self.build_drama_list_path(page=0, size=1000)),
            render,
            log_result=False,
        )

    def on_contract_drama_selected(self) -> None:
        drama = self.current_contract_drama()
        if not isinstance(drama, dict):
            self.contract_episode_input.setText("0")
            self.contract_episode_minutes_input.setText("0")
            self.contract_price_input.setText("0")
            return
        values = self.contract_drama_parameter_values(drama)
        self.contract_episode_input.setText(str(values["episodeCount"]))
        self.contract_episode_minutes_input.setText(str(values["totalMinutes"]))
        self.contract_price_input.setText(str(values["priceWan"]))

    def show_contract_placeholder_help(self) -> None:
        QMessageBox.information(
            self,
            "Word 模版占位符",
            "Word 模版里可用占位符：\n\n"
            "{{agreementNumber}}：协议编号\n"
            "{{dramaTitle}}：剧名\n"
            "{{episodeCount}}：集数\n"
            "{{episodeMinutes}}：总时长（分钟）\n"
            "{{price}}：价格（万）\n"
            "{{halfPrice}}：价格的一半（万）\n"
            "{{buyer}}：买方/甲方\n"
            "{{seller}}：卖方/乙方\n"
            "{{date}}：签署日期\n"
            "{{contractType}}：合同类型",
        )

    def choose_contract_template(self, contract_type: str) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "选择 Word 合同模板", "", "Word 文档 (*.docx)")
        if not filename:
            return
        try:
            target = copy_contract_template(
                Path(filename),
                self.settings.config_dir / "contract-templates",
                self.current_contract_key(contract_type),
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "合同模板", str(exc))
            return
        self.contract_templates[self.current_contract_key(contract_type)] = target
        self.contract_store.save(self.contract_templates)
        self.load_selected_contract_template()
        self.append_log(f"合同模板已保存：{target}")
        QMessageBox.information(self, "合同配置", f"合同模板已保存：{target}")

    def download_contract_template(self, contract_type: str) -> None:
        key = self.current_contract_key(contract_type)
        label = f"{self.current_contract_platform_name()}{self.contract_type_name(contract_type)}"
        query = urlencode({"platform": self.current_contract_platform(), "type": self.contract_api_type(contract_type)})
        self.run_async(
            f"加载{label}系统模版",
            lambda: (key, label, self.api().get(f"/desktop/contract-templates?{query}")),
            self.download_best_contract_template,
            log_result=False,
        )

    def download_best_contract_template(self, result: tuple[str, str, dict[str, Any] | None]) -> None:
        key, label, template = result
        if not template or not template.get("downloadUrl"):
            QMessageBox.information(self, "下载系统模版", f"后台还没有配置可下载的{label}系统模版。")
            return
        self.download_remote_contract_template(key, label, template)

    def download_remote_contract_template(self, key: str, label: str, template: dict[str, Any]) -> None:
        download_url = str(template.get("downloadUrl") or "")
        if not download_url:
            QMessageBox.warning(self, "下载系统模版", "这套系统模版没有可下载文件。")
            return
        directory = QFileDialog.getExistingDirectory(
            self,
            "选择系统模版保存目录",
            str(self.settings.contracts_dir),
        )
        if not directory:
            return
        url = self.resolve_resource_url(download_url)
        headers = self.api().download_headers()
        target_dir = Path(directory)
        self.run_async(
            f"下载{label}系统模版",
            lambda: self.fetch_remote_contract_template(target_dir, key, template, url, headers),
            lambda path: self.on_contract_template_downloaded(key, Path(path)),
            log_result=False,
        )

    def fetch_remote_contract_template(
        self,
        target_dir: Path,
        key: str,
        template: dict[str, Any],
        url: str,
        headers: dict[str, str],
    ) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        target = build_contract_template_download_path(target_dir, key, template)
        try:
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
        except httpx.RequestError as exception:
            raise RuntimeError("无法下载合同系统模版，请稍后重试。") from exception
        if response.status_code >= 400:
            raise RuntimeError(f"合同系统模版下载失败（HTTP {response.status_code}）。")
        target.write_bytes(response.content)
        return target

    def on_contract_template_downloaded(self, key: str, path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self.append_log(f"合同系统模版已下载并打开：{path}")
        QMessageBox.information(self, "下载系统模版", f"合同系统模版已下载并打开：{path}\n\n请整理盖章签名后点击“选择”回传该 .docx 模版。")

    def open_contract_template(self, contract_type: str) -> None:
        template = self.current_contract_template_path(contract_type)
        if not template or not template.exists():
            QMessageBox.warning(self, "合同模板", "请先选择 Word 模板。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(template)))

    def clear_contract_template(self, contract_type: str) -> None:
        self.contract_templates[self.current_contract_key(contract_type)] = None
        self.contract_store.save(self.contract_templates)
        self.load_selected_contract_template()
        self.append_log("合同模板已清空。")

    def contract_render_input(self, contract_type: str, agreement_number: str | None = None) -> ContractRenderInput:
        drama = self.current_contract_drama()
        drama_title = ""
        if isinstance(drama, dict):
            drama_title = self.contract_drama_title(drama)
        if not drama_title:
            drama_title = self.normalize_contract_drama_combo_text(self.contract_drama_input.currentText())
        sign_date = self.contract_date_input.date().toString("yyyy-MM-dd")
        agreement = agreement_number or generate_agreement_number(sign_date)
        return ContractRenderInput(
            contract_type=self.contract_type_name(contract_type),
            drama_title=drama_title or "未命名短剧",
            episode_count=self.contract_episode_input.text().strip() or "0",
            episode_minutes=self.contract_episode_minutes_input.text().strip() or "0",
            price=self.contract_price_input.text().strip() or "0",
            buyer=self.contract_party_value(self.current_contract_platform(), "buyer"),
            seller=self.contract_party_value(self.current_contract_platform(), "seller"),
            sign_date=sign_date,
            start_date=generate_contract_start_date(sign_date, f"{contract_type}:{drama_title}:{agreement}"),
            agreement_number=agreement,
        )

    def generate_contract(self) -> list[Path] | None:
        try:
            return self._generate_contract()
        except Exception as exception:  # noqa: BLE001
            self.show_contract_generation_error(exception)
            return None

    def _generate_contract(self) -> list[Path] | None:
        self.save_contract_party_config()
        missing_labels = self.missing_contract_config_labels(self.current_contract_platform())
        if missing_labels:
            QMessageBox.warning(self, "合同生成", f"请先配置：{'、'.join(missing_labels)}。")
            return None
        generated_paths: list[Path] = []
        sign_date = self.contract_date_input.date().toString("yyyy-MM-dd")
        agreement_number = generate_agreement_number(sign_date)
        for contract_type, _label in required_contract_template_types(self.current_contract_platform()):
            template = self.current_contract_template_path(contract_type)
            if not template:
                QMessageBox.warning(self, "合同生成", "请先配置当前媒体号所需的全部 Word 合同模板。")
                return None
            data = self.contract_render_input(contract_type, agreement_number)
            output = self.contract_test_output_path(data, agreement_number)
            generated_paths.append(
                render_contract_docx(
                    template,
                    output,
                    data,
                    normalize_for_rendering=should_normalize_contract_for_rendering(contract_type),
                )
            )
        self.last_contract_path = generated_paths[-1] if generated_paths else None
        self.last_contract_paths = generated_paths
        if hasattr(self, "contract_preview"):
            self.contract_preview.setPlainText("已生成 Word 合同：\n" + "\n".join(str(path) for path in generated_paths))
        self.update_generated_contract_actions(generated_paths)
        self.append_log("合同已生成：" + "，".join(str(path) for path in generated_paths))
        QMessageBox.information(self, "合同生成", "合同已生成：\n" + "\n".join(str(path) for path in generated_paths))
        return generated_paths

    def contract_test_output_path(self, data: ContractRenderInput, agreement_number: str) -> Path:
        output = build_contract_output_path(self.settings.contracts_dir, data)
        if not sys.platform.startswith("win") or not output.exists():
            return output
        suffix = safe_contract_filename(agreement_number)
        return output.with_name(f"{output.stem}-{suffix}{output.suffix}")

    def show_contract_generation_error(self, exception: Exception) -> None:
        details = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        message = self.clean_error_message(str(exception) or details)
        if hasattr(self, "contract_preview"):
            self.contract_preview.setPlainText(f"合同生成失败：\n{message}")
        self.append_log(f"合同生成失败：\n{details}")
        QMessageBox.critical(self, "合同生成失败", message)

    def generate_and_open_contract(self) -> None:
        generated = self.generate_contract()
        if generated:
            for path in generated:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_last_contract(self) -> None:
        existing_paths = [path for path in self.last_contract_paths if path.exists()]
        if not existing_paths:
            generated = self.generate_contract()
            if not generated:
                return
            existing_paths = [path for path in generated if path.exists()]
        for path in existing_paths:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def update_generated_contract_actions(self, paths: list[Path]) -> None:
        if hasattr(self, "contract_generate_images_button"):
            self.contract_generate_images_button.setEnabled(any(path.exists() for path in paths))
        if not hasattr(self, "generated_contract_actions_layout"):
            return
        while self.generated_contract_actions_layout.count():
            item = self.generated_contract_actions_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for path in paths:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            name = QLabel(path.name)
            name.setToolTip(str(path))
            full_path = QLineEdit(str(path))
            full_path.setReadOnly(True)
            open_button = QPushButton("打开")
            open_button.clicked.connect(lambda _checked=False, target=path: self.open_generated_contract_file(target))
            image_button = QPushButton("生成图片")
            image_button.clicked.connect(lambda _checked=False, target=path: self.generate_generated_contract_images(target))
            row_layout.addWidget(name)
            row_layout.addWidget(full_path, 1)
            row_layout.addWidget(image_button)
            row_layout.addWidget(open_button)
            self.generated_contract_actions_layout.addWidget(row)

    def generate_last_contract_images(self) -> None:
        existing_paths = [path for path in self.last_contract_paths if path.exists()]
        if not existing_paths:
            QMessageBox.warning(self, "生成图片", "请先生成合同。")
            return
        self.run_async(
            "生成合同图片",
            lambda: [(path, self.build_generated_contract_images(path)) for path in existing_paths],
            self.open_generated_contract_image_batches,
            log_result=False,
        )

    def open_generated_contract_file(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.warning(self, "打开合同", f"文件不存在：{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def generate_generated_contract_images(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.warning(self, "生成图片", f"文件不存在：{path}")
            return
        self.run_async(
            "生成合同图片",
            lambda: self.build_generated_contract_images(path),
            lambda image_paths: self.open_generated_contract_images(path, image_paths),
            log_result=False,
        )

    def build_generated_contract_images(self, path: Path) -> list[Path]:
        contract_type = self.infer_contract_type_from_path(path)
        if should_normalize_contract_for_rendering(contract_type):
            normalize_contract_docx_for_rendering(path)
        image_dir = path.parent / "images"
        image_stem = safe_contract_filename(path.stem)
        image_paths = convert_contract_docx_images(
            contract_type,
            path,
            image_dir,
            image_stem,
            soffice_path=self.settings.soffice_path,
        )
        if len(image_paths) > 1:
            image_paths = [merge_pngs_vertically(image_paths, image_dir / f"{image_stem}.png")]
        if not image_paths or any(not image_path.exists() for image_path in image_paths):
            raise RuntimeError("合同图片生成失败。")
        return image_paths

    def open_generated_contract_images(self, contract_path: Path, image_paths: list[Path]) -> None:
        if hasattr(self, "contract_preview"):
            self.contract_preview.append("\n已生成合同图片：\n" + "\n".join(str(path) for path in image_paths))
        for image_path in image_paths:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(image_path)))
        self.append_log("合同图片已生成：" + "，".join(str(path) for path in image_paths))
        QMessageBox.information(
            self,
            "生成图片",
            f"{contract_path.name} 的图片已生成并打开：\n" + "\n".join(str(path) for path in image_paths),
        )

    def open_generated_contract_image_batches(self, batches: list[tuple[Path, list[Path]]]) -> None:
        all_images = [image_path for _contract_path, image_paths in batches for image_path in image_paths]
        if hasattr(self, "contract_preview"):
            self.contract_preview.append("\n已生成合同图片：\n" + "\n".join(str(path) for path in all_images))
        for image_path in all_images:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(image_path)))
        self.append_log("合同图片已生成：" + "，".join(str(path) for path in all_images))
        QMessageBox.information(
            self,
            "生成图片",
            "合同图片已生成并打开：\n" + "\n".join(str(path) for path in all_images),
        )

    @staticmethod
    def infer_contract_type_from_path(path: Path) -> str:
        name = path.stem
        if "权利声明" in name or "rights" in name.lower():
            return "rights"
        if "购买合同" in name or "purchase" in name.lower():
            return "purchase"
        return "cost"

    def open_settings_row(self, row: SettingsRow) -> None:
        if row.kind != "directory":
            return
        path = Path(row.value)
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_platform(self, platform: str) -> None:
        def task() -> str:
            chrome = ChromeController(find_chrome(self.settings.chrome_path), self.settings.browser_profile_dir)
            get_publisher(platform, chrome).open_login()
            return "浏览器已打开"

        self.run_async("打开视频号浏览器", task)

    def heartbeat(self) -> None:
        self.run_async("发送心跳", lambda: self.runner().heartbeat())

    def set_manual_publish_busy(self, busy: bool) -> None:
        self.manual_publish_busy = busy
        if hasattr(self, "publish_next_button"):
            self.publish_next_button.setEnabled(not busy)
            self.publish_next_button.setText("发布中..." if busy else "发布下一条")
        if hasattr(self, "auto_task_button"):
            self.auto_task_button.setEnabled(not busy)
        self.update_task_control_buttons()

    def publish_next(self) -> None:
        if self.manual_publish_busy:
            QMessageBox.information(self, "发布下一条", "已有发布任务在执行中，请等待当前任务结束。")
            return
        self.task_paused = False
        self.set_manual_publish_busy(True)
        self.task_cancel_event.clear()
        self.task_pause_event.clear()
        self.task_skip_event.clear()
        self.update_task_progress("正在检查发布条件", self.current_task_id)
        self.run_async(
            "检查发布条件",
            lambda: self.api().get("/desktop/media-accounts"),
            self.publish_next_if_ready,
            log_result=False,
        )

    def publish_next_if_ready(self, media_accounts: list[dict[str, Any]]) -> None:
        self.media_accounts = media_accounts
        self.save_contract_party_config()
        block_reason = self.auto_task_block_reason(media_accounts) or self.contract_task_block_reason(media_accounts)
        if block_reason:
            self.set_manual_publish_busy(False)
            QMessageBox.warning(self, "发布下一条", block_reason)
            self.update_task_progress("发布未启动", None)
            return
        self.update_task_progress("发布请求已受理，正在领取任务", self.current_task_id)
        self.run_async(
            "发布下一条",
            lambda: self.runner().publish_once(),
            self.handle_manual_publish_done,
        )

    def handle_manual_publish_done(self, result: str) -> None:
        self.set_manual_publish_busy(False)
        if result == "no-task":
            self.update_task_progress("空闲：没有可发布任务", None)
            QMessageBox.information(self, "发布下一条", "当前没有可发布任务。请确认短剧可分发，且媒体号策略匹配。")
        elif result == "failed":
            self.update_task_progress("任务失败", self.current_task_id)
            reason = self.current_task_error_message() or "发布任务执行失败，请查看最近错误或日志。"
            QMessageBox.warning(self, "发布下一条", f"发布任务执行失败：\n{reason}")
        elif result == "cancelled":
            self.task_cancel_event.clear()
            self.update_task_progress("任务已停止，可重新分发", self.current_task_id)
            QMessageBox.information(self, "发布下一条", "发布任务已停止，可重新分发。")
        elif result == "paused":
            self.task_paused = True
            self.update_task_progress("任务已暂停，可恢复执行", self.current_task_id)
            QMessageBox.information(self, "发布下一条", "任务已暂停，可点击“恢复”继续。")
        elif result == "skipped":
            self.task_paused = False
            self.task_skip_event.clear()
            self.update_task_progress("任务已跳过，已放回池里", None)
            QMessageBox.information(self, "发布下一条", "任务已跳过，并已放回待执行池。")
        elif result == "ready-for-review":
            self.update_task_progress("提审未自动提交，任务未完成", self.current_task_id)
            QMessageBox.warning(self, "发布下一条", "视频已上传但提审未自动提交，请重试任务或查看日志。")
        else:
            self.update_task_progress("任务完成", self.current_task_id)
            QMessageBox.information(self, "发布下一条", "发布任务已执行完成。")
        self.update_task_control_buttons()

    def run_once(self) -> None:
        self.run_async("领取并执行", lambda: self.runner().run_once())

    def toggle_auto_tasks(self) -> None:
        if self.auto_task_enabled:
            self.auto_task_enabled = False
            self.task_cancel_event.set()
            self.task_pause_event.clear()
            self.task_skip_event.clear()
            self.auto_task_timer.stop()
            self.auto_task_button.setText("启动自动执行")
            stage = "正在停止当前下载..." if self.auto_task_busy else "自动执行已停止"
            self.update_task_progress(stage, self.current_task_id)
            return
        self.task_cancel_event.clear()
        self.run_async("检查自动执行条件", lambda: self.api().get("/desktop/media-accounts"), self.start_auto_tasks_if_ready)

    def start_auto_tasks_if_ready(self, media_accounts: list[dict[str, Any]]) -> None:
        self.task_cancel_event.clear()
        self.task_pause_event.clear()
        self.task_skip_event.clear()
        self.task_paused = False
        self.media_accounts = media_accounts
        self.save_contract_party_config()
        block_reason = self.auto_task_block_reason(media_accounts) or self.contract_task_block_reason(media_accounts)
        if block_reason:
            QMessageBox.warning(self, "自动执行", block_reason)
            self.update_task_progress("自动执行未启动", None)
            return
        self.auto_task_enabled = True
        self.auto_task_timer.start()
        self.auto_task_button.setText("停止自动执行")
        self.set_task_error_message(None)
        self.update_task_progress("自动执行已启动", self.current_task_id)
        self.run_auto_task_cycle()

    @staticmethod
    def auto_task_block_reason(media_accounts: list[dict[str, Any]]) -> str | None:
        if not media_accounts:
            return "请先新增媒体号并完成登录。"
        active_accounts = [
            item
            for item in media_accounts
            if item.get("status") == "ACTIVE" and (item.get("distributionPolicy") or {}).get("enabled", True)
        ]
        if not active_accounts:
            return "没有可用的媒体号，请先确认媒体号状态为可用。"
        if not any(item.get("loginStateRef") for item in active_accounts):
            return "媒体号未保存登录信息，请先完成媒体号登录。"
        return None

    def contract_task_block_reason(self, media_accounts: list[dict[str, Any]]) -> str | None:
        missing_parts = []
        for platform, label in (("WECHAT_VIDEO", "视频号"), ("TIKTOK", "TikTok")):
            if not self.has_active_platform(media_accounts, platform):
                continue
            missing_labels = self.missing_contract_config_labels(platform)
            if missing_labels:
                missing_parts.append(f"{label}所需的{'、'.join(missing_labels)}")
        if not missing_parts:
            return None
        return f"请先在“合同配置”中配置{'；'.join(missing_parts)}。"

    def missing_contract_config_labels(self, platform: str) -> list[str]:
        return self.missing_contract_party_labels(platform) + self.missing_contract_template_labels(platform)

    def missing_contract_party_labels(self, platform: str) -> list[str]:
        missing: list[str] = []
        for party, label in required_contract_party_fields(platform):
            if not self.contract_party_value(platform, party):
                missing.append(label)
        return missing

    def missing_contract_template_labels(self, platform: str) -> list[str]:
        missing: list[str] = []
        for contract_type, label in required_contract_template_types(platform):
            value = self.contract_templates.get(contract_template_key(platform, contract_type))
            if not value or not Path(value).exists():
                missing.append(label)
        return missing

    @staticmethod
    def has_active_platform(media_accounts: list[dict[str, Any]], platform: str) -> bool:
        return any(
            item.get("status") == "ACTIVE"
            and (item.get("distributionPolicy") or {}).get("enabled", True)
            and str(item.get("platform") or "WECHAT_VIDEO") == platform
            for item in media_accounts
        )

    def run_auto_task_cycle(self) -> None:
        if not self.auto_task_enabled or self.auto_task_busy or self.manual_publish_busy:
            return
        self.auto_task_busy = True
        self.set_task_error_message(None)
        self.update_task_progress("发送心跳", self.current_task_id)
        self.run_async(
            "自动执行任务",
            self.auto_task_once,
            self.handle_auto_task_done,
            log_result=False,
            on_failed=self.handle_auto_task_failed,
        )

    def auto_task_once(self) -> str:
        runner = self.runner()
        runner.heartbeat()
        return runner.publish_once()

    def handle_auto_task_done(self, result: str) -> None:
        self.auto_task_busy = False
        self.last_auto_error_popup_message = None
        if result == "no-task":
            self.update_task_progress("空闲，等待下一轮", None)
        elif result == "failed":
            message = self.current_task_error_message()
            if message and self.is_auto_stop_error(message):
                self.stop_auto_task_for_error(message)
                self.show_auto_error_once("自动执行", message)
                self.update_task_control_buttons()
                return
            self.update_task_progress("任务失败，等待下一轮", self.current_task_id)
        elif result == "cancelled":
            self.task_cancel_event.clear()
            self.update_task_progress("任务已停止，可重新分发", self.current_task_id)
        elif result == "paused":
            self.task_paused = True
            self.update_task_progress("任务已暂停，可恢复执行", self.current_task_id)
        elif result == "skipped":
            self.task_paused = False
            self.task_skip_event.clear()
            self.update_task_progress("任务已跳过，已放回池里", None)
        else:
            self.update_task_progress("任务完成，等待下一轮", self.current_task_id)
        self.update_task_control_buttons()

    def handle_auto_task_failed(self, error: str) -> None:
        self.auto_task_busy = False
        message = self.clean_error_message(error)
        self.set_task_error_message(message)
        if self.is_auto_stop_error(message):
            self.stop_auto_task_for_error(message)
            self.show_auto_error_once("自动执行", message)
            return
        self.update_task_progress(f"任务失败：{message}", self.current_task_id)
        self.show_auto_error_once("自动执行", message)

    def stop_auto_task_for_error(self, message: str) -> None:
        if self.auto_task_enabled:
            self.auto_task_enabled = False
            self.auto_task_timer.stop()
            if hasattr(self, "auto_task_button"):
                self.auto_task_button.setText("启动自动执行")
        self.update_task_progress(f"自动执行已停止：{message}", None)

    def run_scheduled_upload_cache_cleanup(self) -> None:
        if self.manual_publish_busy or self.auto_task_busy or self.upload_cache_cleanup_busy:
            return
        self.upload_cache_cleanup_busy = True
        self.run_async(
            "自动清理缓存",
            self.cleanup_uploaded_drama_cache,
            self.handle_upload_cache_cleanup_done,
            log_result=False,
            log_activity=False,
            on_failed=self.handle_upload_cache_cleanup_failed,
        )

    def clean_upload_cache_now(self) -> None:
        if self.upload_cache_cleanup_busy:
            return
        self.upload_cache_cleanup_busy = True
        self.set_cleanup_data_busy(True)
        self.run_async(
            "手动清理数据",
            self.cleanup_uploaded_drama_cache,
            self.handle_manual_upload_cache_cleanup_done,
            log_result=False,
            on_failed=self.handle_manual_upload_cache_cleanup_failed,
        )

    def cleanup_uploaded_drama_cache(self) -> UploadCacheCleanupResult:
        return cleanup_uploaded_drama_cache_dirs(
            self.settings.downloads_dir,
            self.settings.processed_dir,
            protected_dirs=self.current_upload_cache_protected_dirs(),
        )

    def current_upload_cache_protected_dirs(self) -> list[Path]:
        if not (getattr(self, "manual_publish_busy", False) or getattr(self, "auto_task_busy", False)):
            return []
        protected: list[Path] = []
        settings = getattr(self, "settings", None)
        base_dirs = [
            getattr(settings, "downloads_dir", None),
            getattr(settings, "processed_dir", None),
        ]
        task = getattr(self, "current_task_snapshot", None)
        if task:
            for base_dir in base_dirs:
                if base_dir:
                    protected.extend(self.contract_drama_dir_candidates(Path(base_dir), task))
        title = str(getattr(self, "current_drama_title", None) or "").strip()
        if title:
            title_prefix = drama_directory_name({"dramaId": "", "title": title})
            for base_dir in base_dirs:
                if not base_dir:
                    continue
                root = Path(base_dir)
                if not root.is_dir():
                    continue
                try:
                    protected.extend(
                        child
                        for child in root.iterdir()
                        if child.is_dir() and (child.name == title_prefix or child.name.startswith(f"{title_prefix}-"))
                    )
                except OSError:
                    pass
        return protected

    def handle_upload_cache_cleanup_done(self, result: UploadCacheCleanupResult) -> None:
        self.upload_cache_cleanup_busy = False
        if result.deleted_dirs <= 0 and not result.errors:
            return
        freed = TaskRunner._format_file_size(result.bytes_deleted)
        message = f"缓存清理完成：删除 {result.deleted_dirs} 个剧缓存目录，释放 {freed}"
        if result.errors:
            message += f"，跳过 {len(result.errors)} 项异常"
        self.append_log(message)

    def handle_upload_cache_cleanup_failed(self, error: str) -> None:
        self.upload_cache_cleanup_busy = False
        self.append_log(f"缓存清理失败：{self.clean_error_message(error)}")

    def handle_manual_upload_cache_cleanup_done(self, result: UploadCacheCleanupResult) -> None:
        self.handle_upload_cache_cleanup_done(result)
        self.set_cleanup_data_busy(False)
        freed = TaskRunner._format_file_size(result.bytes_deleted)
        QMessageBox.information(
            self,
            "清理数据",
            f"清理完成：删除 {result.deleted_dirs} 个剧缓存目录，释放 {freed}。",
        )

    def handle_manual_upload_cache_cleanup_failed(self, error: str) -> None:
        self.handle_upload_cache_cleanup_failed(error)
        self.set_cleanup_data_busy(False)
        QMessageBox.critical(self, "清理数据", self.clean_error_message(error))

    def set_cleanup_data_busy(self, busy: bool) -> None:
        if not hasattr(self, "cleanup_data_button"):
            return
        self.cleanup_data_button.setEnabled(not busy)
        self.cleanup_data_button.setText("清理中..." if busy else "清理数据")

    @staticmethod
    def is_auto_stop_error(message: str) -> bool:
        return (
            DesktopWindow.is_daily_publish_limit_error(message)
            or DesktopWindow.is_disk_space_error(message)
            or DesktopWindow.is_jianying_error(message)
        )

    @staticmethod
    def is_daily_publish_limit_error(message: str) -> bool:
        return (
            "今日发布次数已达" in message
            or "今日成功上传次数已达" in message
            or "今日领取任务次数已达" in message
            or "明天再发布" in message
            or "明天再执行" in message
        )

    @staticmethod
    def is_disk_space_error(message: str) -> bool:
        normalized = message.lower()
        return "no space left on device" in normalized or "磁盘空间不足" in message

    @staticmethod
    def is_jianying_error(message: str) -> bool:
        normalized = message.lower()
        return "剪映" in message or "jianying" in normalized or "could not open newest draft card" in normalized

    def set_task_error_message(self, message: str | None) -> None:
        self.last_task_error_message = message or None
        if hasattr(self, "task_error_label"):
            self.task_error_label.setText(f"最近错误：{message or '-'}")

    def show_auto_error_once(self, title: str, message: str) -> None:
        if getattr(self, "last_auto_error_popup_message", None) == message:
            return
        self.last_auto_error_popup_message = message
        QMessageBox.warning(self, title, message)

    def toggle_task_pause(self) -> None:
        if self.task_paused:
            self.resume_paused_task()
            return
        if not self.current_task_id or not (self.manual_publish_busy or self.auto_task_busy):
            QMessageBox.information(self, "暂停任务", "当前没有正在执行的任务。")
            return
        self.resume_auto_after_pause = self.auto_task_enabled
        self.auto_task_enabled = False
        self.auto_task_timer.stop()
        if hasattr(self, "auto_task_button"):
            self.auto_task_button.setText("启动自动执行")
        self.task_pause_event.set()
        self.task_skip_event.clear()
        self.update_task_progress("正在暂停当前任务...", self.current_task_id)
        self.update_task_control_buttons()

    def resume_paused_task(self) -> None:
        self.task_paused = False
        self.task_pause_event.clear()
        self.task_skip_event.clear()
        self.task_cancel_event.clear()
        if self.resume_auto_after_pause:
            self.resume_auto_after_pause = False
            self.run_async("检查自动执行条件", lambda: self.api().get("/desktop/media-accounts"), self.start_auto_tasks_if_ready)
            return
        self.publish_next()

    def skip_current_task(self) -> None:
        if not self.current_task_id:
            QMessageBox.information(self, "跳过任务", "当前没有可跳过的任务。")
            return
        self.task_paused = False
        self.task_pause_event.clear()
        self.task_skip_event.set()
        self.resume_auto_after_pause = False
        self.auto_task_enabled = False
        self.auto_task_timer.stop()
        if hasattr(self, "auto_task_button"):
            self.auto_task_button.setText("启动自动执行")
        if self.manual_publish_busy or self.auto_task_busy:
            self.update_task_progress("正在跳过当前任务...", self.current_task_id)
            self.update_task_control_buttons()
            return
        task_id = self.current_task_id
        self.run_async(
            "跳过任务",
            lambda: self.api().post(f"/desktop/tasks/{task_id}/skip", {"deviceId": self.settings.device_id}),
            lambda _task: self.handle_task_skipped(task_id),
            log_result=False,
        )

    def handle_task_skipped(self, task_id: str) -> None:
        self.task_skip_event.clear()
        if self.current_task_id == task_id:
            self.update_task_progress("任务已跳过，已放回池里", None)
        self.load_task_history(page=self.task_history_page)
        self.update_task_control_buttons()

    def update_task_control_buttons(self) -> None:
        running = bool(getattr(self, "manual_publish_busy", False) or getattr(self, "auto_task_busy", False))
        paused = bool(getattr(self, "task_paused", False))
        has_task = bool(getattr(self, "current_task_id", None))
        if hasattr(self, "pause_task_button"):
            self.pause_task_button.setText("恢复" if paused else "暂停")
            self.pause_task_button.setEnabled(paused or running)
        if hasattr(self, "skip_task_button"):
            self.skip_task_button.setEnabled(has_task and (running or paused))

    def update_task_progress(self, stage: str, task_id: str | None, task: dict[str, Any] | None = None) -> None:
        if getattr(self, "_task_progress_signal_ready", False):
            self.task_progress_requested.emit(stage, task_id, task)
            return
        self._apply_task_progress(stage, task_id, task)

    def _apply_task_progress(self, stage: str, task_id: str | None, task: dict[str, Any] | None = None) -> None:
        self.current_task_id = task_id
        if task:
            self.current_task_snapshot = dict(task)
        elif task_id is None:
            self.current_task_snapshot = None
        media_account_id = str((task or {}).get("mediaAccountId") or "").strip()
        if media_account_id:
            self.current_media_account_id = media_account_id
            self.current_media_account_snapshot = self.media_account_from_task(task or {})
        elif task_id is None:
            self.current_media_account_id = None
            self.current_media_account_snapshot = None
        drama_title = self.task_drama_title(stage, task)
        if drama_title:
            self.current_drama_title = drama_title
        elif task_id is None:
            self.current_drama_title = None
        display_stage = stage
        if stage.startswith("任务失败："):
            reason = self.clean_error_message(stage.removeprefix("任务失败："))
            display_stage = f"任务失败：{reason}"
            self.set_task_error_message(reason)
        if self.should_log_task_progress(display_stage):
            self.append_log(display_stage)
        if hasattr(self, "auto_task_state"):
            self.auto_task_state.setText(f"自动执行：{'运行中' if self.auto_task_enabled else '未启动'}")
        if hasattr(self, "current_task_label"):
            self.current_task_label.setText(f"当前任务：{task_id or '-'}")
        if hasattr(self, "current_drama_label"):
            self.current_drama_label.setText(f"当前短剧：{self.current_drama_display()}")
        if hasattr(self, "current_media_account_label"):
            self.current_media_account_label.setText(f"当前媒体号：{self.current_media_account_display()}")
        if hasattr(self, "current_media_backend_button"):
            self.current_media_backend_button.setEnabled(self.current_media_account() is not None)
        if hasattr(self, "task_stage_label"):
            self.task_stage_label.setText(f"当前阶段：{display_stage}")
        self.update_task_control_buttons()

    def should_log_task_progress(self, stage: str) -> bool:
        message = str(stage or "").strip()
        if not message or not hasattr(self, "log_view"):
            return False
        if message in {"DOWNLOADING", "PROCESSING", "UPLOADING"}:
            return False
        if message.startswith("下载：") and "（100%）" not in message:
            return False
        if message == getattr(self, "_last_task_progress_log", None):
            return False
        self._last_task_progress_log = message
        return True

    @staticmethod
    def task_drama_title(stage: str, task: dict[str, Any] | None = None) -> str:
        for key in ("dramaTitle", "title", "dramaName"):
            value = str((task or {}).get(key) or "").strip()
            if value:
                return value
        if stage.startswith("当前短剧："):
            return stage.removeprefix("当前短剧：").strip()
        return ""

    def current_drama_display(self) -> str:
        return str(getattr(self, "current_drama_title", None) or "-")

    def current_media_account(self) -> dict[str, Any] | None:
        media_account_id = str(getattr(self, "current_media_account_id", None) or "").strip()
        if not media_account_id:
            return None
        account = next(
            (
                item
                for item in getattr(self, "media_accounts", [])
                if str(item.get("id") or "") == media_account_id
            ),
            None,
        )
        if account:
            return account
        snapshot = getattr(self, "current_media_account_snapshot", None)
        if snapshot and str(snapshot.get("id") or "") == media_account_id:
            return snapshot
        return None

    @staticmethod
    def media_account_from_task(task: dict[str, Any]) -> dict[str, Any] | None:
        media_account_id = str(task.get("mediaAccountId") or "").strip()
        if not media_account_id:
            return None
        return {
            "id": media_account_id,
            "displayName": str(task.get("mediaAccountName") or media_account_id),
            "platform": str(task.get("platform") or "WECHAT_VIDEO"),
        }

    def current_media_account_display(self) -> str:
        media_account_id = str(getattr(self, "current_media_account_id", None) or "").strip()
        if not media_account_id:
            return "-"
        account = self.current_media_account()
        if not account:
            return media_account_id
        return str(account.get("displayName") or account.get("externalAccountId") or media_account_id)

    def current_task_error_message(self) -> str | None:
        if getattr(self, "last_task_error_message", None):
            return str(self.last_task_error_message)
        if not hasattr(self, "task_error_label"):
            return None
        text = self.task_error_label.text().removeprefix("最近错误：").strip()
        return text if text and text != "-" else None

    def refresh_status(self) -> None:
        status = AppStatus.from_settings(self.settings, logged_in=bool(self.token_store.get()))
        if hasattr(self, "login_value"):
            self.login_value.setText(status.login_state)
            self.device_value.setText(status.device_id)
        self.statusBar().showMessage(self.status_bar_text(status), 5000)

    @staticmethod
    def status_bar_text(status: AppStatus) -> str:
        return status.login_state

    @staticmethod
    def status_bar_disclaimer_text() -> str:
        return "平台内容均来自互联网，请勿随意转发"

    def append_log(self, message: str) -> None:
        display_message = self.format_log_message(message)
        self.log_view.append(display_message)
        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(display_message.splitlines()[0], 5000)

    @classmethod
    def format_log_message(cls, message: object, *, now: datetime | None = None) -> str:
        timestamp = cls.format_log_timestamp(now)
        lines = str(message).splitlines() or [""]
        return "\n".join(cls.format_log_line(line, timestamp) for line in lines)

    @staticmethod
    def format_log_timestamp(value: datetime | None = None) -> str:
        timestamp = value or datetime.now(CHINA_TIMEZONE)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=CHINA_TIMEZONE)
        return timestamp.astimezone(CHINA_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def format_log_line(line: str, timestamp: str) -> str:
        if LOG_TIME_PREFIX_PATTERN.match(line):
            return line
        return f"[{timestamp}] {line}"


def apply_style(app: QApplication) -> None:
    app.setStyleSheet(
        """
        QWidget {
            color: #1f2937;
            font-size: 13px;
            background: #f6f7f9;
        }
        QMainWindow {
            background: #f6f7f9;
        }
        QWidget#loginRoot {
            background: #eef2f7;
        }
        QFrame#loginPanel {
            background: #ffffff;
            border: 1px solid #dbe3ef;
            border-radius: 12px;
            min-width: 760px;
            max-width: 760px;
            min-height: 500px;
            max-height: 500px;
        }
        QFrame#loginBrandPanel {
            background: #111827;
            border-top-left-radius: 12px;
            border-bottom-left-radius: 12px;
            min-width: 280px;
            max-width: 280px;
        }
        QFrame#loginFormPanel {
            background: #ffffff;
            border: 0;
            border-top-right-radius: 12px;
            border-bottom-right-radius: 12px;
        }
        QLabel#loginLogo {
            background: transparent;
        }
        QLabel#loginBrandTitle {
            color: #ffffff;
            background: transparent;
            font-size: 28px;
            font-weight: 800;
            line-height: 115%;
        }
        QLabel#loginBrandSubtitle {
            color: #cbd5e1;
            background: transparent;
            font-size: 14px;
            font-weight: 600;
        }
        QLabel#loginBrandHint {
            color: #93a4ba;
            background: transparent;
            font-size: 12px;
        }
        QLabel#deviceBadge {
            color: #dbeafe;
            background: #1f2a44;
            border: 1px solid #334766;
            border-radius: 8px;
            padding: 8px 10px;
            font-size: 12px;
            font-weight: 600;
        }
        QLabel#loginTitle {
            color: #111827;
            background: transparent;
            font-size: 26px;
            font-weight: 800;
        }
        QLabel#loginSubtitle {
            color: #64748b;
            background: transparent;
            font-size: 13px;
        }
        QLabel#fieldLabel {
            color: #475569;
            background: transparent;
            font-size: 12px;
            font-weight: 700;
        }
        QWidget#loginField {
            background: transparent;
        }
        QLineEdit#loginInput {
            color: #111827;
            background: #ffffff;
            border: 1px solid #cfd8e6;
            border-radius: 8px;
            padding: 0 12px;
            min-height: 44px;
            max-height: 44px;
            font-size: 14px;
        }
        QLineEdit#loginInput:focus {
            border: 1px solid #2563eb;
            background: #fbfdff;
        }
        QCheckBox#rememberCheck {
            color: #475569;
            background: transparent;
            spacing: 8px;
            font-size: 13px;
            font-weight: 600;
            min-height: 24px;
        }
        QCheckBox#rememberCheck::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #b8c4d6;
            border-radius: 4px;
            background: #ffffff;
        }
        QCheckBox#rememberCheck::indicator:checked {
            background: #2563eb;
            border-color: #2563eb;
        }
        QPushButton#primaryButton {
            color: #ffffff;
            background: #2563eb;
            border: 1px solid #2563eb;
            border-radius: 8px;
            min-height: 46px;
            max-height: 46px;
            padding: 0 16px;
            font-size: 14px;
            font-weight: 800;
        }
        QPushButton#primaryButton:hover {
            background: #1d4ed8;
            border-color: #1d4ed8;
        }
        QPushButton#primaryButton:pressed {
            background: #1e40af;
            border-color: #1e40af;
        }
        QPushButton#secondaryButton {
            color: #1d4ed8;
            background: #ffffff;
            border: 1px solid #c7d2fe;
            border-radius: 8px;
            min-height: 40px;
            max-height: 40px;
            padding: 0 16px;
            font-size: 13px;
            font-weight: 800;
        }
        QPushButton#secondaryButton:hover {
            background: #eff6ff;
            border-color: #93c5fd;
        }
        QPushButton#secondaryButton:pressed {
            background: #dbeafe;
            border-color: #60a5fa;
        }
        QPushButton#secondaryButton:disabled {
            color: #94a3b8;
            background: #f8fafc;
            border-color: #e2e8f0;
        }
        QLabel#pageTitle {
            color: #111827;
            font-size: 24px;
            font-weight: 700;
        }
        QLabel#brandTitle {
            color: #111827;
            font-size: 15px;
            font-weight: 700;
            background: transparent;
        }
        QLabel#mutedText {
            color: #6b7280;
            background: transparent;
        }
        QFrame#sidebar {
            min-width: 230px;
            max-width: 230px;
            background: #eef5ff;
            border-right: 1px solid #d9dee8;
        }
        QFrame#content {
            background: #f6f7f9;
            border: 0;
        }
        QListWidget#navList {
            background: transparent;
            border: 0;
            color: #374151;
            outline: 0;
        }
        QListWidget#navList::item {
            min-height: 38px;
            padding: 8px 14px;
            border-radius: 7px;
        }
        QListWidget#navList::item:hover {
            background: #e1edff;
        }
        QListWidget#navList::item:selected {
            color: #0f3f8c;
            background: #d8eaff;
        }
        QFrame#sidebarAccount {
            background: #ffffff;
            border: 1px solid #dbe7f6;
            border-radius: 8px;
        }
        QLabel#accountTitle {
            color: #1f2937;
            background: transparent;
            font-size: 13px;
            font-weight: 800;
        }
        QLabel#accountHint {
            color: #64748b;
            background: transparent;
            font-size: 12px;
        }
        QPushButton {
            color: #1f2937;
            background: #ffffff;
            border: 1px solid #cfd6e2;
            border-radius: 7px;
            padding: 7px 12px;
            font-weight: 600;
        }
        QPushButton:hover {
            background: #f3f6fb;
            border-color: #b8c2d2;
        }
        QPushButton:pressed {
            background: #e8edf5;
        }
        QPushButton#ghostButton {
            color: #475569;
            background: #ffffff;
            border: 1px solid #cfd6e2;
            border-radius: 7px;
            padding: 7px 12px;
            font-weight: 700;
        }
        QPushButton#ghostButton:hover {
            color: #111827;
            background: #f8fafc;
            border-color: #b8c2d2;
        }
        QPushButton#dangerButton {
            color: #b42318;
            background: #fff7f5;
            border: 1px solid #ffd8d2;
            border-radius: 7px;
            padding: 7px 12px;
            font-weight: 700;
        }
        QPushButton#dangerButton:hover {
            color: #8f1d13;
            background: #ffebe7;
            border-color: #ffb9ae;
        }
        QPushButton#sidebarGhostButton {
            color: #334155;
            background: #f8fafc;
            border: 1px solid #d7e1ee;
            border-radius: 7px;
            padding: 7px 10px;
            font-size: 12px;
            font-weight: 700;
            text-align: left;
        }
        QPushButton#sidebarGhostButton:hover {
            color: #0f172a;
            background: #eef4fb;
            border-color: #c9d6e7;
        }
        QPushButton#sidebarDangerButton {
            color: #8f1d13;
            background: transparent;
            border: 1px solid transparent;
            border-radius: 7px;
            padding: 7px 10px;
            font-size: 12px;
            font-weight: 700;
            text-align: left;
        }
        QPushButton#sidebarDangerButton:hover {
            color: #b42318;
            background: #fff1ee;
            border-color: #ffd8d2;
        }
        QPushButton#tableActionButton {
            color: #0f3f8c;
            background: #eef6ff;
            border: 1px solid #cfe1ff;
            border-radius: 6px;
            padding: 5px 10px;
            font-size: 12px;
            font-weight: 700;
        }
        QPushButton#tableActionButton:hover {
            background: #dfeeff;
            border-color: #b8d4ff;
        }
        QPushButton#helpButton {
            color: #2563eb;
            background: #eff6ff;
            border: 1px solid #bfdbfe;
            border-radius: 12px;
            padding: 0;
            font-weight: 800;
        }
        QPushButton#helpButton:hover {
            background: #dbeafe;
            border-color: #93c5fd;
        }
        QLineEdit, QTextEdit, QTableWidget {
            background: #ffffff;
            border: 1px solid #d9dee8;
            border-radius: 7px;
            padding: 7px;
        }
        QLineEdit, QComboBox, QDoubleSpinBox {
            min-height: 30px;
        }
        QComboBox, QDoubleSpinBox {
            background: #ffffff;
            border: 1px solid #d9dee8;
            border-radius: 7px;
            padding: 4px 8px;
        }
        QTableWidget {
            gridline-color: #eef1f5;
            alternate-background-color: #f8fafc;
            selection-background-color: #dbeafe;
            selection-color: #0f172a;
        }
        QHeaderView::section {
            background: #f3f5f8;
            color: #4b5563;
            border: 0;
            border-bottom: 1px solid #d9dee8;
            padding: 7px;
            font-weight: 600;
        }
        QFrame#panel {
            background: #ffffff;
            border: 1px solid #dfe6f1;
            border-radius: 10px;
        }
        QLabel#panelTitle {
            color: #111827;
            background: transparent;
            font-size: 14px;
            font-weight: 700;
        }
        QFrame#metricCard {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
        }
        QLabel#metricTitle {
            color: #6b7280;
            background: transparent;
            font-size: 12px;
        }
        QLabel#metricValue {
            color: #111827;
            background: transparent;
            font-size: 15px;
            font-weight: 700;
        }
        QLabel#sectionTitle {
            color: #111827;
            background: transparent;
            font-size: 15px;
            font-weight: 700;
        }
        QLabel#badge {
            color: #0f3f8c;
            background: #eaf2ff;
            border: 1px solid #c9ddff;
            border-radius: 12px;
            padding: 5px 10px;
            font-size: 12px;
            font-weight: 600;
        }
        """
    )


def app_icon() -> QIcon:
    icon_path = resources.files("aidrama_desktop").joinpath("assets/app-icon.svg")
    return QIcon(str(icon_path))


def handle_non_gui_args(argv: list[str]) -> bool:
    if "--jianying-uia-helper" in argv:
        index = argv.index("--jianying-uia-helper")
        from aidrama_desktop.jianying.windows_uia_helper import run

        raise SystemExit(run(argv[index + 1 :]))
    if "--version" in argv:
        print(__version__)
        return True
    if "--write-version-file" in argv:
        index = argv.index("--write-version-file")
        if index + 1 >= len(argv):
            raise SystemExit("--write-version-file requires a target path")
        target = Path(argv[index + 1])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(__version__, encoding="utf-8")
        return True
    return False


def install_crash_diagnostics(settings: Settings) -> Path | None:
    global _CRASH_LOG_FILE
    try:
        log_dir = settings.work_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "desktop-crash.log"
        _CRASH_LOG_FILE = log_path.open("a", encoding="utf-8", buffering=1)
        started_at = datetime.now(CHINA_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        _CRASH_LOG_FILE.write(f"\n[{started_at}] AI Drama Desktop 启动，启用崩溃诊断。\n")
        faulthandler.enable(file=_CRASH_LOG_FILE, all_threads=True)
        previous_excepthook = sys.excepthook
        previous_threading_excepthook = threading.excepthook

        def write_unhandled_exception(exc_type, exc_value, exc_traceback) -> None:
            happened_at = datetime.now(CHINA_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            _CRASH_LOG_FILE.write(f"\n[{happened_at}] 未捕获异常：\n")
            traceback.print_exception(exc_type, exc_value, exc_traceback, file=_CRASH_LOG_FILE)
            _CRASH_LOG_FILE.flush()
            previous_excepthook(exc_type, exc_value, exc_traceback)

        def write_thread_exception(args: threading.ExceptHookArgs) -> None:
            happened_at = datetime.now(CHINA_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            _CRASH_LOG_FILE.write(f"\n[{happened_at}] 线程未捕获异常：{args.thread.name if args.thread else '-'}\n")
            traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback, file=_CRASH_LOG_FILE)
            _CRASH_LOG_FILE.flush()
            previous_threading_excepthook(args)

        sys.excepthook = write_unhandled_exception
        threading.excepthook = write_thread_exception
        return log_path
    except Exception:
        return None


def main() -> None:
    if handle_non_gui_args(sys.argv[1:]):
        return
    settings = load_settings()
    install_crash_diagnostics(settings)
    app = QApplication(sys.argv)
    app.setApplicationName("AI Drama Desktop")
    app.setWindowIcon(app_icon())
    apply_style(app)
    window = DesktopWindow(settings)
    window.setWindowIcon(app_icon())
    window.show()
    QTimer.singleShot(0, window.raise_)
    QTimer.singleShot(0, window.activateWindow)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
