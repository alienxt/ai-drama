from __future__ import annotations

import sys
import threading
import traceback
from collections.abc import Callable
from hashlib import sha256
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import httpx
from PySide6.QtCore import QDate, QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from aidrama_desktop.api.client import ApiClient
from aidrama_desktop import __version__
from aidrama_desktop.auth.remembered_login import RememberedLoginStore
from aidrama_desktop.auth.token_store import TokenStore
from aidrama_desktop.browser.chrome import ChromeController, find_chrome
from aidrama_desktop.config.settings import Settings, load_settings
from aidrama_desktop.contracts import (
    ContractConfigStore,
    ContractRenderInput,
    all_required_contract_templates_configured,
    build_contract_output_path,
    build_contract_template_download_path,
    contract_template_key,
    copy_contract_template,
    required_contract_template_types,
    render_contract_docx,
)
from aidrama_desktop.gui.state import AppStatus, SettingsRow, desktop_nav_items, settings_rows, update_settings
from aidrama_desktop.local_agent import create_local_agent_server
from aidrama_desktop.platforms.registry import get_publisher, platform_login_url
from aidrama_desktop.tasks.runner import TaskRunner
from aidrama_desktop.update import UpdateInfo, detect_platform, download_installer, open_installer
from aidrama_desktop.video.ffmpeg import FfmpegProcessor


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
                chrome.open_platform_login(platform, platform_login_url(platform), account_id)
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


class DesktopWindow(QMainWindow):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.token_store = TokenStore(settings.token_file)
        self.token_store.clear()
        self.thread_pool = QThreadPool.globalInstance()
        self.agent = AgentController(settings)
        self.agent.log.connect(self.append_log)
        self.agent.changed.connect(lambda _: self.refresh_status())
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
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
        self.current_task_id: str | None = None
        self.task_history_rows: list[dict[str, Any]] = []
        self.task_history_page = 0
        self.task_history_size = 10
        self.task_history_total_pages = 1
        self.task_history_total_elements = 0
        self.task_cancel_event = threading.Event()
        self.contract_store = ContractConfigStore(settings.config_dir / "contract-templates.json")
        self.contract_templates = self.contract_store.load()
        self.last_contract_path: Path | None = None
        self.last_contract_paths: list[Path] = []
        self.auto_task_timer = QTimer(self)
        self.auto_task_timer.setInterval(30_000)
        self.auto_task_timer.timeout.connect(self.run_auto_task_cycle)

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
        logout_button = QPushButton("退出登录")
        logout_button.setObjectName("sidebarDangerButton")
        logout_button.clicked.connect(self.logout)
        quit_button = QPushButton("退出应用")
        quit_button.setObjectName("sidebarGhostButton")
        quit_button.clicked.connect(self.quit_app)
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
        icons = {
            "dramas": QStyle.StandardPixmap.SP_DirHomeIcon,
            "media": QStyle.StandardPixmap.SP_DriveNetIcon,
            "contracts": QStyle.StandardPixmap.SP_FileIcon,
            "tasks": QStyle.StandardPixmap.SP_MediaPlay,
            "settings": QStyle.StandardPixmap.SP_FileDialogDetailedView,
            "logs": QStyle.StandardPixmap.SP_FileDialogInfoView,
        }
        return self.style().standardIcon(icons.get(key, QStyle.StandardPixmap.SP_FileIcon))

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

        self.drama_table = QTableWidget(0, 10)
        self.drama_table.setHorizontalHeaderLabels(["封面", "短剧名称", "简介", "评分", "分类", "集数", "下载状态", "已下载集数", "上架时间", "操作"])
        self.align_table_header_left(self.drama_table)
        self.drama_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.drama_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.drama_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.Fixed)
        self.drama_table.horizontalHeader().setSectionResizeMode(9, QHeaderView.Fixed)
        self.drama_table.setColumnWidth(0, 82)
        self.drama_table.setColumnWidth(3, 64)
        self.drama_table.setColumnWidth(4, 120)
        self.drama_table.setColumnWidth(5, 70)
        self.drama_table.setColumnWidth(6, 100)
        self.drama_table.setColumnWidth(7, 110)
        self.drama_table.setColumnWidth(8, 165)
        self.drama_table.setColumnWidth(9, 170)
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
        self.contract_platform_input.setMinimumHeight(34)
        self.contract_platform_input.setMinimumWidth(140)
        self.contract_platform_input.setMaximumWidth(200)
        self.contract_platform_input.currentIndexChanged.connect(self.load_selected_contract_template)
        type_row.addWidget(QLabel("媒体号类型"))
        type_row.addWidget(self.contract_platform_input)
        type_row.addStretch(1)

        self.contract_template_path_inputs: dict[str, QLineEdit] = {}
        self.contract_template_rows_layout = QVBoxLayout()
        self.contract_template_rows_layout.setSpacing(8)
        for contract_type, label in required_contract_template_types("WECHAT_VIDEO"):
            row = QHBoxLayout()
            path_input = QLineEdit()
            path_input.setReadOnly(True)
            choose_template = QPushButton("选择")
            choose_template.clicked.connect(lambda _checked=False, key=contract_type: self.choose_contract_template(key))
            download_template = QPushButton("下载系统模版")
            download_template.clicked.connect(lambda _checked=False, key=contract_type: self.download_contract_template(key))
            open_template = QPushButton("打开")
            open_template.clicked.connect(lambda _checked=False, key=contract_type: self.open_contract_template(key))
            clear_template = QPushButton("清空")
            clear_template.clicked.connect(lambda _checked=False, key=contract_type: self.clear_contract_template(key))
            row.addWidget(QLabel(label))
            row.addWidget(path_input, 1)
            row.addWidget(download_template)
            row.addWidget(choose_template)
            row.addWidget(open_template)
            row.addWidget(clear_template)
            self.contract_template_path_inputs[contract_type] = path_input
            self.contract_template_rows_layout.addLayout(row)

        template_note = QLabel(
            "1. 下载并打开系统模版，将主体的盖章和法人签名（透明底图片），添加到指定的位置上；\n"
            "2. 点击“选择”回传整理后的 .docx 模版后，才可以生成合同。"
        )
        template_note.setObjectName("mutedText")
        template_note.setWordWrap(True)
        template_layout.addLayout(template_header)
        template_layout.addLayout(type_row)
        template_layout.addWidget(template_note)
        template_layout.addLayout(self.contract_template_rows_layout)
        template_layout.addStretch(1)

        preview_panel, preview_layout = self._panel("测试生成")
        form = QGridLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.contract_drama_input = QComboBox()
        self.contract_drama_input.setMinimumHeight(36)
        self.contract_drama_input.addItem("正在加载短剧库...", None)
        self.contract_drama_input.currentIndexChanged.connect(self.on_contract_drama_selected)
        self.contract_episode_input = QLineEdit("0")
        self.contract_episode_input.setReadOnly(True)
        self.contract_episode_minutes_input = QLineEdit("0")
        self.contract_episode_minutes_input.setReadOnly(True)
        self.contract_price_input = QLineEdit("0.5")
        self.contract_buyer_input = QLineEdit("甲方公司")
        self.contract_seller_input = QLineEdit("乙方公司")
        self.contract_date_input = QDateEdit()
        self.contract_date_input.setCalendarPopup(True)
        self.contract_date_input.setDisplayFormat("yyyy-MM-dd")
        self.contract_date_input.setDate(QDate.currentDate())
        self._add_contract_form_field(form, 0, 0, "剧名", self.contract_drama_input, column_span=2)
        self._add_contract_form_field(form, 0, 2, "剧集", self.contract_episode_input)
        self._add_contract_form_field(form, 0, 3, "总时长（分钟）", self.contract_episode_minutes_input)
        self._add_contract_form_field(form, 0, 4, "价格（万）", self.contract_price_input)
        self._add_contract_form_field(form, 1, 0, "买方/甲方", self.contract_buyer_input, column_span=2)
        self._add_contract_form_field(form, 1, 2, "卖方/乙方", self.contract_seller_input, column_span=2)
        self._add_contract_form_field(form, 1, 4, "签署日期", self.contract_date_input)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(2, 1)
        form.setColumnStretch(3, 1)
        form.setColumnStretch(4, 1)
        actions = QHBoxLayout()
        self.contract_generate_button = QPushButton("生成合同")
        self.contract_generate_button.clicked.connect(self.generate_contract)
        actions.addWidget(self.contract_generate_button)
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
        self.publish_next_button.clicked.connect(self.publish_next)
        self.auto_task_button.clicked.connect(self.toggle_auto_tasks)
        actions.addWidget(self.publish_next_button)
        actions.addWidget(self.auto_task_button)
        actions.addStretch(1)
        self.auto_task_state = QLabel("自动执行：未启动")
        self.auto_task_state.setObjectName("mutedText")
        self.current_task_label = QLabel("当前任务：-")
        self.current_task_label.setObjectName("mutedText")
        self.task_stage_label = QLabel("当前阶段：空闲")
        self.task_stage_label.setObjectName("mutedText")
        self.task_error_label = QLabel("最近错误：-")
        self.task_error_label.setObjectName("mutedText")
        note = QLabel("自动执行会定时发送心跳，空闲时自动发布下一条。")
        note.setObjectName("mutedText")
        panel, panel_layout = self._panel("任务操作")
        panel_layout.addLayout(actions)
        panel_layout.addWidget(self.auto_task_state)
        panel_layout.addWidget(self.current_task_label)
        panel_layout.addWidget(self.task_stage_label)
        panel_layout.addWidget(self.task_error_label)
        panel_layout.addWidget(note)
        layout.addWidget(panel)

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

        self.task_history_table = QTableWidget(0, 8)
        self.task_history_table.setHorizontalHeaderLabels(
            ["短剧", "媒体号", "状态", "进度", "失败原因", "创建时间", "结束时间", "操作"]
        )
        self.task_history_table.verticalHeader().setVisible(False)
        self.task_history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.task_history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.task_history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.task_history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.task_history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.task_history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.task_history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.task_history_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Fixed)
        self.task_history_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)
        self.task_history_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Fixed)
        self.task_history_table.setColumnWidth(1, 130)
        self.task_history_table.setColumnWidth(2, 92)
        self.task_history_table.setColumnWidth(3, 80)
        self.task_history_table.setColumnWidth(5, 150)
        self.task_history_table.setColumnWidth(6, 150)
        self.task_history_table.setColumnWidth(7, 86)
        self.align_table_header_left(self.task_history_table)
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
        layout.addWidget(history_panel, 1)
        return page

    def _settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        panel, panel_layout = self._panel("运行配置")
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
        table.setMinimumHeight(560)
        note = QLabel("目录类配置可以点击“打开”进入 Finder；双击目录值也可以打开。")
        note.setObjectName("mutedText")
        panel_layout.addWidget(note)
        panel_layout.addWidget(table, 1)
        layout.addWidget(panel, 1)
        return page

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
            self.load_task_history(page=self.task_history_page)
        if item.key == "contracts" and hasattr(self, "contract_drama_input"):
            self.load_contract_dramas()
        self.refresh_status()

    def on_logged_in(self) -> None:
        self.settings = update_settings(self.settings)
        self.agent.settings = self.settings
        self.append_log("登录成功。")
        self.stack.setCurrentWidget(self.main_page)
        self.show_page(self.nav.currentRow())
        self.refresh_status()
        QTimer.singleShot(600, self.check_for_updates)

    def logout(self) -> None:
        self.token_store.clear()
        self.stack.setCurrentWidget(self.login_page)
        self.append_log("已退出登录。")
        self.refresh_status()

    def quit_app(self) -> None:
        if self.agent.running:
            self.agent.stop()
        QApplication.instance().quit()

    def api(self) -> ApiClient:
        return ApiClient(self.settings.server_url, self.token_store)

    def check_for_updates(self) -> None:
        platform = detect_platform()
        if not platform:
            self.append_log("当前平台暂不支持自动更新检查。")
            return
        self.run_async(
            "检查桌面端更新",
            lambda: (platform, self.api().check_update(platform, __version__)),
            self.handle_update_check,
            log_result=False,
        )

    def handle_update_check(self, result: tuple[str, dict[str, Any]]) -> None:
        platform, payload = result
        update = UpdateInfo.from_api(payload)
        if not update:
            self.append_log(f"当前已是最新版本：{__version__}")
            return
        self.prompt_update(platform, update)

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
        chrome = ChromeController(find_chrome(self.settings.chrome_path), self.settings.browser_profile_dir)
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
            download_concurrency=self.settings.download_concurrency,
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
    ) -> None:
        self.append_log(f"开始：{title}")
        worker = Worker(task)
        worker.signals.done.connect(lambda result: self._task_done(title, result, on_done, log_result=log_result))
        worker.signals.failed.connect(lambda error: self._task_failed(title, error))
        worker.signals.done.connect(lambda _: self._release_worker(worker))
        worker.signals.failed.connect(lambda _: self._release_worker(worker))
        self.active_workers.append(worker)
        self.thread_pool.start(worker)

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
    ) -> None:
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

    def _task_failed(self, title: str, error: str) -> None:
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
        self.append_log(f"失败：{title}\n{error}")
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

    def load_task_history(self, page: int = 0) -> None:
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

        self.run_async("加载任务历史", lambda: self.api().get(path), render, log_result=False)

    def render_task_history_table(self, rows: list[dict[str, Any]]) -> None:
        self.task_history_rows = rows
        self.task_history_table.setRowCount(len(rows))
        for row_index, task in enumerate(rows):
            values = self.task_history_row_values(task)
            for column, value in enumerate(values):
                item = self.left_aligned_table_item(value)
                item.setToolTip(value)
                self.task_history_table.setItem(row_index, column, item)
            self.task_history_table.setCellWidget(row_index, 7, self.task_history_actions_widget(task))
            self.task_history_table.setRowHeight(row_index, 38)

    def task_history_row_values(self, task: dict[str, Any]) -> list[str]:
        return [
            str(task.get("dramaTitle") or task.get("dramaId") or "-"),
            str(task.get("mediaAccountName") or task.get("mediaAccountId") or "-"),
            self.distribution_task_status_label(str(task.get("status") or "")),
            f"{int(task.get('progress') or 0)}%",
            str(task.get("failureReason") or "-"),
            self.format_datetime(str(task.get("createdAt") or "")),
            self.format_datetime(str(task.get("finishedAt") or "")),
        ]

    def task_history_actions_widget(self, task: dict[str, Any]) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        retry = QPushButton("重试")
        retry.setEnabled(str(task.get("status") or "") == "FAILED")
        retry.clicked.connect(lambda _=False, item=task: self.retry_distribution_task(item))
        layout.addWidget(retry)
        layout.addStretch(1)
        return wrapper

    def retry_distribution_task(self, task: dict[str, Any]) -> None:
        task_id = str(task.get("id") or "")
        if not task_id:
            QMessageBox.warning(self, "重试任务", "任务 ID 为空，无法重试。")
            return
        if str(task.get("status") or "") != "FAILED":
            QMessageBox.information(self, "重试任务", "只有失败任务可以重试。")
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
        self.update_task_progress("正在检查重试条件", task_id)
        self.run_async(
            "检查重试条件",
            lambda: self.api().get("/desktop/media-accounts"),
            lambda media_accounts: self.retry_task_if_ready(task_id, media_accounts),
            log_result=False,
        )

    def retry_task_if_ready(self, task_id: str, media_accounts: list[dict[str, Any]]) -> None:
        self.media_accounts = media_accounts
        block_reason = self.auto_task_block_reason(media_accounts)
        if block_reason:
            self.set_manual_publish_busy(False)
            QMessageBox.warning(self, "重试任务", block_reason)
            self.update_task_progress("重试未启动", task_id)
            return
        self.update_task_progress("重试请求已受理，正在执行任务", task_id)
        self.run_async(
            "重试任务",
            lambda: self.retry_task_once(task_id),
            self.handle_retry_task_done,
        )

    def retry_task_once(self, task_id: str) -> str:
        task = self.api().post(f"/desktop/tasks/{task_id}/retry", {"deviceId": self.settings.device_id})
        return self.runner().execute_task(task)

    def handle_retry_task_done(self, result: str) -> None:
        self.set_manual_publish_busy(False)
        if result == "failed":
            self.update_task_progress("任务失败", self.current_task_id)
            reason = self.current_task_error_message() or "发布任务执行失败，请查看最近错误或日志。"
            QMessageBox.warning(self, "重试任务", f"任务重试失败：\n{reason}")
        elif result == "cancelled":
            self.update_task_progress("任务已停止，可重新分发", self.current_task_id)
            QMessageBox.information(self, "重试任务", "任务已停止，可重新分发。")
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

    def load_dramas(self, page: int = 0) -> None:
        filter_value = self.current_drama_download_filter()
        keyword = self.current_drama_keyword()
        request_page = 0 if filter_value != "ALL" else page
        request_size = 1000 if filter_value != "ALL" else self.drama_size
        path = self.build_drama_list_path(page=request_page, size=request_size, keyword=keyword)

        def render(result: dict[str, Any]) -> None:
            rows = result.get("content") or []
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
                self.drama_page = int(result.get("page") or 0)
                self.drama_total_pages = max(int(result.get("totalPages") or 1), 1)
                self.drama_total_elements = int(result.get("totalElements") or 0)
            self.render_drama_table(rows)
            self.drama_page_label.setText(
                f"共 {self.drama_total_elements} 条 · 第 {self.drama_page + 1}/{self.drama_total_pages} 页"
            )

        self.run_async("加载短剧库", lambda: self.api().get(path), render, log_result=False)

    def render_drama_table(self, rows: list[dict[str, Any]]) -> None:
        self.current_drama_rows = rows
        self.drama_table.setRowCount(len(rows))
        for row_index, drama in enumerate(rows):
            cover_url = self.resolve_resource_url(str(drama.get("coverUrl") or ""))
            self.drama_table.setCellWidget(row_index, 0, self.drama_cover_widget(cover_url))
            values = self.drama_row_values(drama)
            download_status, downloaded_count, _ = self.drama_download_info(drama)
            values[5] = download_status
            values[6] = str(downloaded_count)
            for column, value in enumerate(values, start=1):
                item = self.left_aligned_table_item(value)
                item.setToolTip(value)
                self.drama_table.setItem(row_index, column, item)
            self.drama_table.setCellWidget(row_index, 9, self.drama_actions_widget(drama))
            self.drama_table.setRowHeight(row_index, 86)

    def show_drama_detail(self, row: int, _: int = 0) -> None:
        if row < 0 or row >= len(self.current_drama_rows):
            return
        drama = self.current_drama_rows[row]
        title = str(drama.get("aiTitle") or drama.get("title") or "短剧详情")
        original_title = str(drama.get("title") or "")
        summary = str(drama.get("summary") or "暂无简介")
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
        info.addWidget(QLabel(f"集数：{total_count}"))
        info.addWidget(QLabel(f"下载状态：{status}"))
        info.addWidget(QLabel(f"已下载集数：{downloaded_count}/{total_count}"))
        info.addWidget(QLabel(f"上架时间：{self.format_datetime(str(drama.get('createdAt') or ''))}"))
        info.addStretch(1)
        top.addLayout(info, 1)
        layout.addLayout(top)

        summary_title = QLabel("简介")
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
            str(drama.get("summary") or "-"),
            cls.format_rating(drama.get("rating")),
            categories or "-",
            str(cls.drama_episode_count(drama)),
            "-",
            "-",
            cls.format_datetime(str(drama.get("createdAt") or "")),
        ]

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
    def format_datetime(value: str) -> str:
        if not value:
            return "-"
        return value.replace("T", " ")[:19]

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
            chrome.open_platform_login(platform, platform_login_url(platform), profile_key)
            login_payload = {
                "loginStateRef": chrome.login_state_ref(platform, profile_key),
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
            chrome.open_profile(profile_dir, platform_login_url(platform))
            payload = {
                "loginStateRef": str(profile_dir),
                "deviceId": self.settings.device_id,
                "verified": True,
            }
            self.api().put(f"/desktop/media-accounts/{account_id}/login-state", payload)
            return f"{display_name} 浏览器已打开，登录信息已保存"

        self.run_async("绑定媒体号", task)

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

    def current_contract_platform(self) -> str:
        return str(self.contract_platform_input.currentData() or "WECHAT_VIDEO")

    def current_contract_platform_name(self) -> str:
        return self.contract_platform_input.currentText() or "视频号"

    @staticmethod
    def contract_type_name(contract_type: str) -> str:
        for key, label in required_contract_template_types("WECHAT_VIDEO"):
            if key == contract_type:
                return label
        return "购买合同"

    @staticmethod
    def contract_api_type(key: str) -> str:
        return "PURCHASE_CONTRACT" if key == "purchase" else "COST_CONTRACT"

    def current_contract_template_path(self, contract_type: str) -> Path | None:
        value = self.contract_templates.get(self.current_contract_key(contract_type))
        return Path(value) if value else None

    def load_selected_contract_template(self) -> None:
        for contract_type, _label in required_contract_template_types(self.current_contract_platform()):
            template = self.current_contract_template_path(contract_type)
            display = str(template) if template else "未配置，请选择 .docx Word 模板"
            if contract_type in getattr(self, "contract_template_path_inputs", {}):
                self.contract_template_path_inputs[contract_type].setText(display)
        if hasattr(self, "contract_generate_button"):
            self.contract_generate_button.setEnabled(
                all_required_contract_templates_configured(self.contract_templates, self.current_contract_platform())
            )
        if hasattr(self, "contract_preview"):
            self.contract_preview.setPlainText(
                "点击“下载系统模版”获取后台模板并整理盖章签名。"
                "整理完成后点击“选择”回传本机 .docx 模板。当前媒体号需要的合同都配置后，才可以生成合同。"
            )

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
                    title = str(drama.get("aiTitle") or drama.get("title") or "未命名短剧")
                    count = self.drama_episode_count(drama)
                    self.contract_drama_input.addItem(f"{title}（{count}集）", drama)
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
        drama = self.contract_drama_input.currentData()
        if not isinstance(drama, dict):
            self.contract_episode_input.setText("0")
            self.contract_episode_minutes_input.setText("0")
            return
        episode_count = self.drama_episode_count(drama)
        total_minutes = self.drama_total_minutes(drama)
        self.contract_episode_input.setText(str(episode_count))
        self.contract_episode_minutes_input.setText(str(total_minutes))

    def show_contract_placeholder_help(self) -> None:
        QMessageBox.information(
            self,
            "Word 模版占位符",
            "Word 模版里可用占位符：\n\n"
            "{{dramaTitle}}：剧名\n"
            "{{episodeCount}}：集数\n"
            "{{episodeMinutes}}：总时长（分钟）\n"
            "{{price}}：价格（万）\n"
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

    def contract_render_input(self, contract_type: str) -> ContractRenderInput:
        drama = self.contract_drama_input.currentData()
        drama_title = ""
        if isinstance(drama, dict):
            drama_title = str(drama.get("aiTitle") or drama.get("title") or "")
        if not drama_title:
            drama_title = self.contract_drama_input.currentText().strip()
        return ContractRenderInput(
            contract_type=self.contract_type_name(contract_type),
            drama_title=drama_title or "未命名短剧",
            episode_count=self.contract_episode_input.text().strip() or "0",
            episode_minutes=self.contract_episode_minutes_input.text().strip() or "0",
            price=self.contract_price_input.text().strip() or "0",
            buyer=self.contract_buyer_input.text().strip() or "甲方",
            seller=self.contract_seller_input.text().strip() or "乙方",
            sign_date=self.contract_date_input.date().toString("yyyy-MM-dd"),
        )

    def generate_contract(self) -> list[Path] | None:
        if not all_required_contract_templates_configured(self.contract_templates, self.current_contract_platform()):
            QMessageBox.warning(self, "合同生成", "请先配置当前媒体号所需的全部 Word 合同模板。")
            return None
        generated_paths: list[Path] = []
        for contract_type, _label in required_contract_template_types(self.current_contract_platform()):
            template = self.current_contract_template_path(contract_type)
            if not template:
                QMessageBox.warning(self, "合同生成", "请先配置当前媒体号所需的全部 Word 合同模板。")
                return None
            data = self.contract_render_input(contract_type)
            output = build_contract_output_path(self.settings.contracts_dir, data)
            generated_paths.append(render_contract_docx(template, output, data))
        self.last_contract_path = generated_paths[-1] if generated_paths else None
        self.last_contract_paths = generated_paths
        if hasattr(self, "contract_preview"):
            self.contract_preview.setPlainText("已生成 Word 合同：\n" + "\n".join(str(path) for path in generated_paths))
        self.update_generated_contract_actions(generated_paths)
        self.append_log("合同已生成：" + "，".join(str(path) for path in generated_paths))
        QMessageBox.information(self, "合同生成", "合同已生成：\n" + "\n".join(str(path) for path in generated_paths))
        return generated_paths

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
            row_layout.addWidget(name)
            row_layout.addWidget(full_path, 1)
            row_layout.addWidget(open_button)
            self.generated_contract_actions_layout.addWidget(row)

    def open_generated_contract_file(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.warning(self, "打开合同", f"文件不存在：{path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

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

    def publish_next(self) -> None:
        if self.manual_publish_busy:
            QMessageBox.information(self, "发布下一条", "已有发布任务在执行中，请等待当前任务结束。")
            return
        self.set_manual_publish_busy(True)
        self.task_cancel_event.clear()
        self.update_task_progress("正在检查发布条件", self.current_task_id)
        self.run_async(
            "检查发布条件",
            lambda: self.api().get("/desktop/media-accounts"),
            self.publish_next_if_ready,
            log_result=False,
        )
        QMessageBox.information(self, "发布下一条", "发布请求已收到，正在检查媒体号和任务队列。可在当前页面查看执行进度。")

    def publish_next_if_ready(self, media_accounts: list[dict[str, Any]]) -> None:
        self.media_accounts = media_accounts
        block_reason = self.auto_task_block_reason(media_accounts)
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
            self.update_task_progress("任务已停止，可重新分发", self.current_task_id)
            QMessageBox.information(self, "发布下一条", "发布任务已停止，可重新分发。")
        else:
            self.update_task_progress("任务完成", self.current_task_id)
            QMessageBox.information(self, "发布下一条", "发布任务已执行完成。")

    def run_once(self) -> None:
        self.run_async("领取并执行", lambda: self.runner().run_once())

    def toggle_auto_tasks(self) -> None:
        if self.auto_task_enabled:
            self.auto_task_enabled = False
            self.task_cancel_event.set()
            self.auto_task_timer.stop()
            self.auto_task_button.setText("启动自动执行")
            stage = "正在停止当前下载..." if self.auto_task_busy else "自动执行已停止"
            self.update_task_progress(stage, self.current_task_id)
            return
        self.task_cancel_event.clear()
        self.run_async("检查自动执行条件", lambda: self.api().get("/desktop/media-accounts"), self.start_auto_tasks_if_ready)

    def start_auto_tasks_if_ready(self, media_accounts: list[dict[str, Any]]) -> None:
        self.task_cancel_event.clear()
        self.media_accounts = media_accounts
        block_reason = self.auto_task_block_reason(media_accounts)
        if block_reason:
            QMessageBox.warning(self, "自动执行", block_reason)
            self.update_task_progress("自动执行未启动", None)
            return
        self.auto_task_enabled = True
        self.auto_task_timer.start()
        self.auto_task_button.setText("停止自动执行")
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

    def run_auto_task_cycle(self) -> None:
        if not self.auto_task_enabled or self.auto_task_busy or self.manual_publish_busy:
            return
        self.auto_task_busy = True
        self.update_task_progress("发送心跳", self.current_task_id)
        self.run_async("自动执行任务", self.auto_task_once, self.handle_auto_task_done, log_result=False)

    def auto_task_once(self) -> str:
        runner = self.runner()
        runner.heartbeat()
        return runner.publish_once()

    def handle_auto_task_done(self, result: str) -> None:
        self.auto_task_busy = False
        if result == "no-task":
            self.update_task_progress("空闲，等待下一轮", None)
        elif result == "failed":
            self.update_task_progress("任务失败，等待下一轮", self.current_task_id)
        elif result == "cancelled":
            self.update_task_progress("任务已停止，可重新分发", self.current_task_id)
        else:
            self.update_task_progress("任务完成，等待下一轮", self.current_task_id)

    def update_task_progress(self, stage: str, task_id: str | None) -> None:
        self.current_task_id = task_id
        display_stage = stage
        if stage.startswith("任务失败："):
            reason = self.clean_error_message(stage.removeprefix("任务失败："))
            display_stage = f"任务失败：{reason}"
            if hasattr(self, "task_error_label"):
                self.task_error_label.setText(f"最近错误：{reason}")
        if hasattr(self, "auto_task_state"):
            self.auto_task_state.setText(f"自动执行：{'运行中' if self.auto_task_enabled else '未启动'}")
        if hasattr(self, "current_task_label"):
            self.current_task_label.setText(f"当前任务：{task_id or '-'}")
        if hasattr(self, "task_stage_label"):
            self.task_stage_label.setText(f"当前阶段：{display_stage}")

    def current_task_error_message(self) -> str | None:
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
        self.log_view.append(message)
        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(message.splitlines()[0], 5000)


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


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("AI Drama Desktop")
    app.setWindowIcon(app_icon())
    apply_style(app)
    window = DesktopWindow(load_settings())
    window.setWindowIcon(app_icon())
    window.show()
    QTimer.singleShot(0, window.raise_)
    QTimer.singleShot(0, window.activateWindow)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
