from __future__ import annotations

import time
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QSpacerItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from actions import open_file, reveal_in_finder
from database import FileDatabase
from file_categories import (
    CATEGORY_ALL,
    CATEGORY_APPS,
    CATEGORY_ARCHIVES,
    CATEGORY_BILLS,
    CATEGORY_CAD,
    CATEGORY_DOCUMENTS,
    CATEGORY_DRAWINGS,
    CATEGORY_IMAGES,
    CATEGORY_OTHER,
    CATEGORY_WEB,
    CATEGORY_LABELS,
    category_label,
)
from indexer import FileIndexer
from i18n import tr
from ocr_indexer import OCR_ENABLED_SETTING
from searcher import FileSearcher
from semantic.config import (
    MODALITY_IMAGE,
    MODALITY_IMAGE_OCR_TEXT,
    MODALITY_IMAGE_SIMILARITY,
    MODALITY_PDF_TEXT,
    SEMANTIC_ENABLED_SETTING,
    SEMANTIC_IMAGE_ENABLED_SETTING,
    SEMANTIC_PDF_ENABLED_SETTING,
)
from semantic.search import SemanticSearcher

ENGINEERING_MODE_SETTING = "engineering_filters_enabled"
ENGINEERING_FILTER_CATEGORIES = (CATEGORY_DRAWINGS, CATEGORY_CAD, CATEGORY_BILLS)
DEFAULT_FILTER_CATEGORIES = (
    CATEGORY_ALL,
    CATEGORY_IMAGES,
    CATEGORY_DOCUMENTS,
    CATEGORY_APPS,
    CATEGORY_ARCHIVES,
    CATEGORY_WEB,
    CATEGORY_OTHER,
)
HOME_GOLDEN_CENTER_RATIO = 0.382


class ScanWorker(QObject):
    progress = Signal(str)
    finished = Signal(object, float)
    failed = Signal(str)

    def __init__(self, db_path, include_content: bool = False, include_ocr: bool = False) -> None:
        super().__init__()
        self.db_path = db_path
        self.include_content = include_content
        self.include_ocr = include_ocr

    def run(self) -> None:
        started = time.time()
        try:
            worker_db = FileDatabase(self.db_path)
            stats = FileIndexer(worker_db).scan_all(
                progress_callback=self.progress.emit,
                include_content=self.include_content,
                include_ocr=self.include_ocr,
            )
            self.finished.emit(stats, time.time() - started)
        except Exception as exc:  # noqa: BLE001 - show failures without freezing the app.
            self.failed.emit(str(exc))


class SearchWorker(QObject):
    finished = Signal(int, str, object, float)
    failed = Signal(int, str, str)

    def __init__(
        self,
        search_id: int,
        db_path,
        query: str,
        limit: int = 200,
        category: str = CATEGORY_ALL,
        semantic: bool = False,
    ) -> None:
        super().__init__()
        self.search_id = search_id
        self.db_path = db_path
        self.query = query
        self.limit = limit
        self.category = category
        self.semantic = semantic

    def run(self) -> None:
        started = time.time()
        try:
            worker_db = FileDatabase(self.db_path)
            results = FileSearcher(worker_db).search(
                self.query,
                self.limit,
                category=self.category,
                semantic=self.semantic,
            )
            self.finished.emit(self.search_id, self.query, results, time.time() - started)
        except Exception as exc:  # noqa: BLE001 - keep search failures out of the UI thread.
            self.failed.emit(self.search_id, self.query, str(exc))


class MainWindow(QMainWindow):
    def __init__(self, db: FileDatabase) -> None:
        super().__init__()
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle("MacLocalFileManager")
        self.setMinimumSize(640, 160)
        self.db = db
        self.indexer = FileIndexer(db)
        self.searcher = FileSearcher(db)
        self.results = []
        self.scan_thread = None
        self.scan_worker = None
        self.scan_mode = "文件索引"
        self.search_thread = None
        self.search_worker = None
        self.search_id = 0
        self.pending_search: tuple[str, bool] | None = None
        self.close_after_search = False
        self.is_closing = False
        self._dragging_window = False
        self._drag_position = None
        self._user_moved_window = False
        self._syncing_result_selection = False
        self.active_category = CATEGORY_ALL
        self.category_buttons: dict[str, QPushButton] = {}

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.run_search)

        self._build_ui()
        self._apply_macos_style()
        self._load_settings()
        self._load_directories()
        QTimer.singleShot(1200, self.prompt_for_external_volumes)

    def _build_ui(self) -> None:
        central = QWidget(self)
        central.setObjectName("appRoot")
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(12)
        self.home_top_spacer = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        root_layout.addItem(self.home_top_spacer)

        self.search_shell = QWidget()
        self.search_shell.setObjectName("searchShell")
        self.search_shell.setMinimumWidth(640)
        self.search_shell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header_layout = QVBoxLayout(self.search_shell)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(10)
        self.search_shell.installEventFilter(self)

        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        self.hero_title = QLabel(tr("本地聚合搜索"))
        self.hero_title.setObjectName("heroTitle")
        self.hero_title.installEventFilter(self)
        self.quick_entry_label = QLabel(tr("本机文件 · 图片 · 文档 · 剪切板"))
        self.quick_entry_label.setObjectName("quickEntryHint")
        self.quick_entry_label.installEventFilter(self)
        self.settings_button = QPushButton(tr("设置"))
        self.settings_button.setObjectName("inlineSettingsButton")
        self.settings_button.setToolTip(tr("扫描、索引和工程分类设置"))
        self.settings_button.clicked.connect(self.open_settings_dialog)
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("inlineCloseButton")
        self.close_button.setToolTip(tr("关闭"))
        self.close_button.setFixedSize(24, 24)
        self.close_button.clicked.connect(self.close)
        title_row.addWidget(self.hero_title)
        title_row.addStretch(1)
        title_row.addWidget(self.quick_entry_label)
        title_row.addWidget(self.settings_button)
        title_row.addWidget(self.close_button)
        header_layout.addLayout(title_row)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchField")
        self.search_input.setPlaceholderText(tr("搜索本机文件、图片、文档、剪切板"))
        self.search_input.setMinimumHeight(54)
        self.search_input.textChanged.connect(lambda: self.search_timer.start(260))
        self.search_input.returnPressed.connect(self.run_search)
        self.search_button = QPushButton(tr("搜索"))
        self.search_button.setObjectName("primarySearchButton")
        self.search_button.setMinimumHeight(46)
        self.search_button.clicked.connect(self.run_search)
        search_row.addWidget(self.search_input, 1)
        search_row.addWidget(self.search_button)
        header_layout.addLayout(search_row)

        header_row = QHBoxLayout()
        header_row.addWidget(self.search_shell, 1)
        root_layout.addLayout(header_row)
        self.filter_bar = self._build_filter_bar()
        root_layout.addWidget(self.filter_bar)

        self.result_panel = self._build_result_panel()
        root_layout.addWidget(self.result_panel, 1)

        self.status_label = QLabel(tr("就绪"))
        self.status_label.setObjectName("statusLine")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        root_layout.addWidget(self.status_label)
        root_layout.addWidget(self.progress_bar)
        self.home_bottom_spacer = QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        root_layout.addItem(self.home_bottom_spacer)

        self._build_hidden_maintenance_controls(central)
        self.setCentralWidget(central)
        self._set_home_mode()
        self._build_menu()

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu(tr("文件"))
        settings_action = QAction(tr("扫描设置"), self)
        settings_action.triggered.connect(self.open_settings_dialog)
        file_menu.addAction(settings_action)
        rescan_action = QAction(tr("刷新文件索引"), self)
        rescan_action.triggered.connect(self.rescan_index)
        file_menu.addAction(rescan_action)
        self.menuBar().hide()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt override naming.
        if watched in (self.search_shell, self.hero_title, self.quick_entry_label):
            event_type = event.type()
            if event_type == event.Type.MouseButtonPress and event.button() == Qt.LeftButton:
                self._user_moved_window = True
                self._dragging_window = True
                self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
                return True
            if event_type == event.Type.MouseMove and self._dragging_window and event.buttons() & Qt.LeftButton:
                if self._drag_position is not None:
                    self.move(event.globalPosition().toPoint() - self._drag_position)
                event.accept()
                return True
            if event_type == event.Type.MouseButtonRelease and self._dragging_window:
                self._dragging_window = False
                self._drag_position = None
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def _available_screen_geometry(self):
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return self.frameGeometry()
        return screen.availableGeometry()

    def _move_to_automatic_position(self, mode: str) -> None:
        if self._user_moved_window:
            return
        screen_rect = self._available_screen_geometry()
        x = screen_rect.left() + (screen_rect.width() - self.width()) // 2
        if mode == "home":
            center_y = screen_rect.top() + round(screen_rect.height() * HOME_GOLDEN_CENTER_RATIO)
        else:
            center_y = screen_rect.top() + screen_rect.height() // 2
        y = round(center_y - (self.height() / 2))
        self.move(self._bounded_window_x(screen_rect, x), self._bounded_window_y(screen_rect, y))

    def _bounded_window_x(self, screen_rect, x: int) -> int:
        if self.width() >= screen_rect.width():
            return screen_rect.left()
        return max(screen_rect.left(), min(x, screen_rect.right() - self.width() + 1))

    def _bounded_window_y(self, screen_rect, y: int) -> int:
        if self.height() >= screen_rect.height():
            return screen_rect.top()
        return max(screen_rect.top(), min(y, screen_rect.bottom() - self.height() + 1))

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override naming.
        self.is_closing = True
        self.search_timer.stop()
        self.pending_search = None
        if self.search_thread is not None and self.search_thread.isRunning():
            self.close_after_search = True
            self.status_label.show()
            self.status_label.setText(tr("正在完成当前搜索，完成后关闭"))
            event.ignore()
            return
        self._stop_background_threads()
        super().closeEvent(event)

    def _stop_background_threads(self) -> None:
        self._stop_thread("search_thread", "search_worker")
        self._stop_thread("scan_thread", "scan_worker")

    def _stop_thread(self, thread_attr: str, worker_attr: str) -> None:
        thread = getattr(self, thread_attr, None)
        if thread is None:
            return
        if thread.isRunning():
            thread.requestInterruption()
            thread.quit()
            if not thread.wait(700):
                thread.terminate()
                thread.wait(1000)
        setattr(self, thread_attr, None)
        setattr(self, worker_attr, None)

    def _build_filter_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("filterBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.semantic_button = QPushButton(tr("语义搜索"), bar)
        self.semantic_button.setCheckable(True)
        self.semantic_button.hide()
        for category in (*DEFAULT_FILTER_CATEGORIES, *ENGINEERING_FILTER_CATEGORIES):
            label = CATEGORY_LABELS[category]
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("filterChip", True)
            if category in ENGINEERING_FILTER_CATEGORIES:
                button.setProperty("engineeringFilter", True)
            if category == CATEGORY_ALL:
                button.setChecked(True)
            button.clicked.connect(lambda _checked=False, value=category: self.set_category_filter(value))
            self.category_buttons[category] = button
            row.addWidget(button)
        row.addStretch(1)
        return bar

    def _apply_engineering_filter_visibility(self) -> None:
        enabled = self.db.get_bool_setting(ENGINEERING_MODE_SETTING, False)
        for category in ENGINEERING_FILTER_CATEGORIES:
            button = self.category_buttons.get(category)
            if button is not None:
                button.setVisible(enabled)
        if not enabled and self.active_category in ENGINEERING_FILTER_CATEGORIES:
            self.set_category_filter(CATEGORY_ALL)

    def _build_hidden_maintenance_controls(self, parent: QWidget) -> None:
        self.rescan_button = QPushButton(tr("刷新文件索引"), parent)
        self.rescan_button.clicked.connect(self.rescan_index)
        self.content_button = QPushButton(tr("索引文档内容"), parent)
        self.content_button.clicked.connect(self.rescan_content_index)
        self.ocr_checkbox = QCheckBox(tr("启用图片识别"), parent)
        self.ocr_checkbox.setToolTip(tr("图片识别会执行 OCR、图片标签和相似图片索引，适合后台慢慢跑。"))
        self.ocr_checkbox.toggled.connect(self.set_ocr_enabled)
        self.ocr_scan_button = QPushButton(tr("扫描图片识别"), parent)
        self.ocr_scan_button.clicked.connect(self.rescan_ocr_index)
        for widget in (
            self.rescan_button,
            self.content_button,
            self.ocr_checkbox,
            self.ocr_scan_button,
        ):
            widget.hide()

    def _build_directory_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        title = QLabel(tr("扫描范围"))
        title.setProperty("sidebarTitle", True)
        layout.addWidget(title)

        self.dir_list = QListWidget()
        self.dir_list.setObjectName("sidebarList")
        layout.addWidget(self.dir_list, 1)

        settings_button = QPushButton(tr("设置"))
        settings_button.clicked.connect(self.open_settings_dialog)
        layout.addWidget(settings_button)
        return panel

    def _build_result_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("resultPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.image_section_label = QLabel(tr("图片"))
        self.image_section_label.setProperty("sectionLabel", True)
        self.image_section_label.hide()
        layout.addWidget(self.image_section_label)

        self.image_list = QListWidget()
        self.image_list.setObjectName("imageList")
        self.image_list.setViewMode(QListWidget.IconMode)
        self.image_list.setIconSize(QSize(156, 112))
        self.image_list.setResizeMode(QListWidget.Adjust)
        self.image_list.setMovement(QListWidget.Static)
        self.image_list.setSpacing(12)
        self.image_list.setMaximumHeight(184)
        self.image_list.itemDoubleClicked.connect(lambda item: open_file(item.data(Qt.UserRole)))
        self.image_list.itemSelectionChanged.connect(self._on_image_selection_changed)
        self.image_list.hide()
        layout.addWidget(self.image_list)

        self.list_section_label = QLabel("文件")
        self.list_section_label.setProperty("sectionLabel", True)
        self.list_section_label.hide()
        layout.addWidget(self.list_section_label)

        self.result_table = QTableWidget(0, 7)
        self.result_table.setHorizontalHeaderLabels(
            [tr("名称"), tr("类型"), tr("路径"), tr("修改日期"), tr("大小"), tr("命中"), tr("内容摘要")]
        )
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.result_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table.setAlternatingRowColors(True)
        self.result_table.cellDoubleClicked.connect(lambda _row, _col: self.open_selected_file())
        self.result_table.itemSelectionChanged.connect(self._on_table_selection_changed)
        layout.addWidget(self.result_table, 1)

        action_row = QHBoxLayout()
        self.open_button = QPushButton(tr("打开文件"))
        self.open_button.clicked.connect(self.open_selected_file)
        self.open_button.setEnabled(False)
        self.reveal_button = QPushButton(tr("在 Finder 中显示"))
        self.reveal_button.clicked.connect(self.reveal_selected_file)
        self.reveal_button.setEnabled(False)
        self.copy_button = QPushButton(tr("复制完整路径"))
        self.copy_button.clicked.connect(self.copy_selected_path)
        self.copy_button.setEnabled(False)
        self.similar_button = QPushButton(tr("查找相似图片"))
        self.similar_button.clicked.connect(self.find_similar_selected_image)
        self.similar_button.setEnabled(False)
        action_row.addWidget(self.open_button)
        action_row.addWidget(self.reveal_button)
        action_row.addWidget(self.copy_button)
        action_row.addWidget(self.similar_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        return panel

    def _load_directories(self) -> None:
        if not hasattr(self, "dir_list"):
            return
        self.dir_list.clear()
        for path in self.db.list_managed_dirs():
            item = QListWidgetItem(display_scan_path(path))
            if path == "/":
                item.setToolTip("默认扫描 Mac 内置磁盘，已排除系统目录和外接磁盘。")
            item.setData(Qt.UserRole, path)
            self.dir_list.addItem(item)

    def _load_settings(self) -> None:
        self.ocr_checkbox.blockSignals(True)
        self.ocr_checkbox.setChecked(self.db.get_bool_setting(OCR_ENABLED_SETTING, False))
        self.ocr_checkbox.blockSignals(False)
        self.semantic_button.blockSignals(True)
        self.semantic_button.setChecked(self.db.get_bool_setting(SEMANTIC_ENABLED_SETTING, False))
        self.semantic_button.blockSignals(False)
        self._apply_engineering_filter_visibility()

    def set_ocr_enabled(self, enabled: bool) -> None:
        self.db.set_bool_setting(OCR_ENABLED_SETTING, enabled)
        status = tr("已启用图片识别，点击“扫描图片识别”后开始索引") if enabled else tr("已关闭图片识别")
        self.status_label.setText(status)

    def add_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择要管理的目录", str(Path.home()))
        if not path:
            return
        try:
            self.indexer.add_directory(path)
        except ValueError as exc:
            QMessageBox.warning(self, "无法添加目录", str(exc))
            return
        self._load_directories()
        self.rescan_index()

    def remove_selected_directory(self) -> None:
        if not hasattr(self, "dir_list"):
            return
        item = self.dir_list.currentItem()
        if item is None:
            return
        self.indexer.remove_directory(item.data(Qt.UserRole))
        self._load_directories()

    def open_settings_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(tr("扫描设置"))
        dialog.setMinimumWidth(560)
        layout = QVBoxLayout(dialog)

        title = QLabel(tr("默认全盘扫描"))
        title.setProperty("sidebarTitle", True)
        layout.addWidget(title)
        scan_hint = QLabel(tr("默认扫描 Macintosh HD 的用户文件，自动跳过系统、应用、缓存、安装镜像和开发依赖目录。U 盘和外接硬盘可在这里确认加入。"))
        scan_hint.setWordWrap(True)
        layout.addWidget(scan_hint)

        dir_list = QListWidget(dialog)
        layout.addWidget(dir_list, 1)

        def refresh_list() -> None:
            dir_list.clear()
            for managed_path in self.db.list_managed_dirs():
                item = QListWidgetItem(display_scan_path(managed_path))
                if managed_path == "/":
                    item.setToolTip("默认扫描 Mac 内置磁盘，已排除系统目录和外接磁盘。")
                item.setData(Qt.UserRole, managed_path)
                dir_list.addItem(item)

        def remove_selected() -> None:
            item = dir_list.currentItem()
            if item is None:
                return
            if item.data(Qt.UserRole) == "/":
                QMessageBox.information(dialog, tr("默认扫描"), tr("默认全盘扫描不能移除。"))
                return
            self.indexer.remove_directory(item.data(Qt.UserRole))
            refresh_list()
            self._load_directories()

        def add_external_volume() -> None:
            volumes = unmanaged_external_volumes(self.db.list_managed_dirs())
            if not volumes:
                QMessageBox.information(dialog, tr("外接磁盘"), tr("没有发现未加入扫描的外接磁盘。"))
                return
            for volume in volumes:
                answer = QMessageBox.question(
                    dialog,
                    tr("发现外接磁盘"),
                    f"{tr('是否将外接磁盘加入扫描？')} {volume.name}\n{volume}",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if answer == QMessageBox.Yes:
                    self._add_scan_directory(str(volume))
            refresh_list()

        button_row = QHBoxLayout()
        add_external_button = QPushButton(tr("加入外接磁盘"))
        add_external_button.clicked.connect(add_external_volume)
        remove_button = QPushButton(tr("移除选中外接磁盘"))
        remove_button.clicked.connect(remove_selected)
        close_button = QPushButton(tr("完成"))
        close_button.clicked.connect(dialog.accept)
        button_row.addWidget(add_external_button)
        button_row.addWidget(remove_button)
        button_row.addStretch(1)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        semantic_title = QLabel(tr("离线语义索引"))
        semantic_title.setProperty("sidebarTitle", True)
        layout.addWidget(semantic_title)

        semantic_enabled_checkbox = QCheckBox(tr("启用语义搜索"))
        semantic_enabled_checkbox.setChecked(self.db.get_bool_setting(SEMANTIC_ENABLED_SETTING, False))
        semantic_pdf_checkbox = QCheckBox(tr("PDF 语义"))
        semantic_pdf_checkbox.setChecked(self.db.get_bool_setting(SEMANTIC_PDF_ENABLED_SETTING, True))
        semantic_image_checkbox = QCheckBox(tr("图片语义"))
        semantic_image_checkbox.setChecked(self.db.get_bool_setting(SEMANTIC_IMAGE_ENABLED_SETTING, True))
        semantic_summary_label = QLabel()
        semantic_summary_label.setWordWrap(True)

        def refresh_semantic_summary() -> None:
            semantic_summary_label.setText(format_semantic_summary(self.db.fetch_semantic_summary()))

        def set_semantic_enabled(value: bool) -> None:
            self.db.set_bool_setting(SEMANTIC_ENABLED_SETTING, value)
            self.semantic_button.blockSignals(True)
            self.semantic_button.setChecked(value)
            self.semantic_button.blockSignals(False)
            self.run_search()

        def set_semantic_pdf_enabled(value: bool) -> None:
            self.db.set_bool_setting(SEMANTIC_PDF_ENABLED_SETTING, value)

        def set_semantic_image_enabled(value: bool) -> None:
            self.db.set_bool_setting(SEMANTIC_IMAGE_ENABLED_SETTING, value)

        semantic_enabled_checkbox.toggled.connect(set_semantic_enabled)
        semantic_pdf_checkbox.toggled.connect(set_semantic_pdf_enabled)
        semantic_image_checkbox.toggled.connect(set_semantic_image_enabled)

        semantic_row = QHBoxLayout()
        semantic_row.addWidget(semantic_enabled_checkbox)
        semantic_row.addWidget(semantic_pdf_checkbox)
        semantic_row.addWidget(semantic_image_checkbox)
        semantic_row.addStretch(1)
        layout.addLayout(semantic_row)
        layout.addWidget(semantic_summary_label)

        display_title = QLabel(tr("显示选项"))
        display_title.setProperty("sidebarTitle", True)
        layout.addWidget(display_title)
        engineering_checkbox = QCheckBox(tr("工程模式：显示图纸 / CAD / 清单分类"))
        engineering_checkbox.setChecked(self.db.get_bool_setting(ENGINEERING_MODE_SETTING, False))

        def set_engineering_mode_enabled(value: bool) -> None:
            self.db.set_bool_setting(ENGINEERING_MODE_SETTING, value)
            self._apply_engineering_filter_visibility()

        engineering_checkbox.toggled.connect(set_engineering_mode_enabled)
        layout.addWidget(engineering_checkbox)

        refresh_list()
        refresh_semantic_summary()
        dialog.exec()
        self._load_directories()
        self._load_settings()

    def _add_scan_directory(self, path: str) -> bool:
        try:
            self.indexer.add_directory(path)
        except ValueError as exc:
            QMessageBox.warning(self, tr("无法添加扫描位置"), str(exc))
            return False
        self._load_directories()
        return True

    def prompt_for_external_volumes(self) -> None:
        if self.is_closing or not self.isVisible():
            return
        try:
            volumes = unmanaged_external_volumes(self.db.list_managed_dirs())
        except Exception:  # noqa: BLE001 - this timer must not surface errors after shutdown.
            return
        for volume in volumes:
            setting_key = f"external_prompted:{volume}"
            if self.db.get_bool_setting(setting_key, False):
                continue
            self.db.set_bool_setting(setting_key, True)
            answer = QMessageBox.question(
                self,
                tr("发现外接磁盘"),
                f"{tr('是否将外接磁盘加入扫描？')} {volume.name}\n{volume}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer == QMessageBox.Yes and self._add_scan_directory(str(volume)):
                self.rescan_index()
            break

    def set_category_filter(self, category: str) -> None:
        self.active_category = category
        for key, button in self.category_buttons.items():
            button.setChecked(key == category)
        self.run_search()

    def on_semantic_toggled(self) -> None:
        self.db.set_bool_setting(SEMANTIC_ENABLED_SETTING, self.semantic_button.isChecked())
        self.run_search()

    def rescan_index(self) -> None:
        self._start_scan("文件索引", include_content=False, include_ocr=False)

    def rescan_content_index(self) -> None:
        self._start_scan("文档内容索引", include_content=True, include_ocr=False)

    def rescan_ocr_index(self) -> None:
        if not self.ocr_checkbox.isChecked():
            self.ocr_checkbox.setChecked(True)
        self._start_scan("OCR 扫描", include_content=False, include_ocr=True)

    def _start_scan(self, mode: str, include_content: bool, include_ocr: bool) -> None:
        if self.scan_thread is not None and self.scan_thread.isRunning():
            self.status_label.setText(tr("正在后台扫描，请稍候"))
            return

        self.rescan_button.setEnabled(False)
        self.content_button.setEnabled(False)
        self.ocr_scan_button.setEnabled(False)
        self.scan_mode = mode
        self.status_label.setText(f"{tr('正在后台运行')}{mode}，{tr('窗口可以继续操作')}")
        self.scan_thread = QThread(self)
        self.scan_worker = ScanWorker(self.db.db_path, include_content=include_content, include_ocr=include_ocr)
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.progress.connect(self.on_scan_progress)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.failed.connect(self.on_scan_failed)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_worker.failed.connect(self.scan_thread.quit)
        self.scan_thread.finished.connect(self.scan_worker.deleteLater)
        self.scan_thread.finished.connect(self.on_scan_thread_finished)
        self.scan_thread.start()

    def on_scan_progress(self, message: str) -> None:
        self.status_label.setText(message)
        self._update_progress_bar(message)

    def on_scan_finished(self, stats, elapsed: float) -> None:
        parts = [
            f"{self.scan_mode}完成",
            f"文件 {stats.scanned_files} 个",
            f"更新 {stats.updated_files} 个",
            f"缺失标记 {stats.missing_files} 个",
        ]
        if stats.content_indexed or stats.content_skipped or stats.content_failed:
            parts.append(
                f"内容索引 {stats.content_indexed} 个，跳过 {stats.content_skipped} 个，失败 {stats.content_failed} 个"
            )
        if stats.ocr_indexed or stats.ocr_skipped or stats.ocr_failed:
            parts.append(f"OCR {stats.ocr_indexed} 个，跳过 {stats.ocr_skipped} 个，失败 {stats.ocr_failed} 个")
        if stats.semantic_pdf_indexed or stats.semantic_pdf_skipped or stats.semantic_pdf_failed:
            parts.append(
                f"PDF语义 {stats.semantic_pdf_indexed} 个，跳过 {stats.semantic_pdf_skipped} 个，失败 {stats.semantic_pdf_failed} 个"
            )
        if stats.semantic_ocr_indexed or stats.semantic_ocr_skipped or stats.semantic_ocr_failed:
            parts.append(
                f"图片文字语义 {stats.semantic_ocr_indexed} 个，跳过 {stats.semantic_ocr_skipped} 个，失败 {stats.semantic_ocr_failed} 个"
            )
        if stats.semantic_image_indexed or stats.semantic_image_skipped or stats.semantic_image_failed:
            parts.append(
                f"图片视觉语义 {stats.semantic_image_indexed} 个，跳过 {stats.semantic_image_skipped} 个，失败 {stats.semantic_image_failed} 个"
            )
        if stats.semantic_similarity_indexed or stats.semantic_similarity_skipped or stats.semantic_similarity_failed:
            parts.append(
                f"相似图片 {stats.semantic_similarity_indexed} 个，跳过 {stats.semantic_similarity_skipped} 个，失败 {stats.semantic_similarity_failed} 个"
            )
        if stats.skipped_dirs:
            parts.append(f"跳过目录 {stats.skipped_dirs} 个")
        parts.append(f"用时 {elapsed:.2f}s")
        self.status_label.setText("；".join(parts))
        self.progress_bar.hide()
        self.run_search(update_status=False)

    def on_scan_failed(self, message: str) -> None:
        self.progress_bar.hide()
        self.status_label.setText(f"扫描失败：{message}")
        QMessageBox.warning(self, "扫描失败", message)

    def on_scan_thread_finished(self) -> None:
        self.rescan_button.setEnabled(True)
        self.content_button.setEnabled(True)
        self.ocr_scan_button.setEnabled(True)
        self.scan_thread = None
        self.scan_worker = None

    def run_search(self, update_status: bool = True) -> None:
        if self.is_closing:
            return
        query = self.search_input.text()
        if not query.strip():
            self._set_home_mode()
            self.pending_search = None
            self.results = []
            self._show_search_results([])
            return

        self._set_search_mode()
        if self.search_thread is not None and self.search_thread.isRunning():
            self.pending_search = (query, update_status)
            if update_status:
                self.status_label.setText(tr("正在搜索，继续输入不会卡住"))
            return

        self._start_search(query, update_status)

    def _start_search(self, query: str, update_status: bool) -> None:
        if self.is_closing:
            return
        self.search_id += 1
        current_id = self.search_id
        if update_status:
            self.status_label.setText(tr("正在搜索，窗口可以继续操作"))

        self.search_thread = QThread(self)
        self.search_worker = SearchWorker(
            current_id,
            self.db.db_path,
            query,
            category=self.active_category,
            semantic=self.semantic_button.isChecked(),
        )
        self.search_worker.moveToThread(self.search_thread)
        self.search_thread.started.connect(self.search_worker.run)
        self.search_worker.finished.connect(self.on_search_finished)
        self.search_worker.failed.connect(self.on_search_failed)
        self.search_worker.finished.connect(self.search_thread.quit)
        self.search_worker.failed.connect(self.search_thread.quit)
        self.search_thread.finished.connect(self.search_worker.deleteLater)
        self.search_thread.finished.connect(self.on_search_thread_finished)
        self.search_thread.start()

    def on_search_finished(self, search_id: int, query: str, results, elapsed: float) -> None:
        if search_id != self.search_id:
            return
        if query != self.search_input.text():
            self.pending_search = (self.search_input.text(), True)
            return

        self.results = results
        self._show_search_results(results)

        if self.scan_thread is not None and self.scan_thread.isRunning():
            self.status_label.setText(f"后台扫描中，当前显示已有索引结果：{len(results)} 条")
        elif len(results) == 0 and self.db.count_existing_files() == 0:
            self.status_label.setText("索引还未建立，正在后台扫描或请稍候")
        else:
            self.status_label.setText(f"搜索完成：{len(results)} 条结果，用时 {elapsed:.2f}s")

    def on_search_failed(self, search_id: int, query: str, message: str) -> None:
        if search_id == self.search_id:
            self.status_label.setText(f"搜索失败：{message}")

    def on_search_thread_finished(self) -> None:
        self.search_thread = None
        self.search_worker = None
        if self.close_after_search:
            self.close_after_search = False
            QTimer.singleShot(0, self.close)
            return
        if self.is_closing:
            return
        if self.pending_search is not None:
            query, update_status = self.pending_search
            self.pending_search = None
            if query.strip():
                QTimer.singleShot(0, lambda: self._start_search(query, update_status))

    def _show_search_results(self, results) -> None:
        if self.search_input.text().strip():
            self._set_search_mode()
        image_results = [result for result in results if result.category == CATEGORY_IMAGES]
        table_results = [result for result in results if result.category != CATEGORY_IMAGES]

        self.image_list.clear()
        for result in image_results[:24]:
            item = QListWidgetItem(QIcon(thumbnail_for(result.path)), result.filename)
            item.setToolTip(result.path)
            item.setData(Qt.UserRole, result.path)
            self.image_list.addItem(item)

        if image_results:
            self.image_section_label.setText(f"{tr('智能识别到')} {len(image_results)} {tr('张图片')}")
            self.image_section_label.show()
            self.image_list.show()
        else:
            self.image_section_label.hide()
            self.image_list.hide()

        self.list_section_label.setText(f"{tr('搜索到')} {len(table_results)} {tr('个文件')}")
        self.list_section_label.setVisible(bool(table_results))

        self.result_table.setUpdatesEnabled(False)
        self.result_table.clearContents()
        self.result_table.setRowCount(len(table_results))

        try:
            for row_index, result in enumerate(table_results):
                values = [
                    result.filename,
                    display_type(result),
                    result.parent_dir,
                    format_time(result.modified_at),
                    human_size(result.size),
                    result.match_type,
                    result.snippet or result.reason,
                ]
                for col_index, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.UserRole, result.path)
                    self.result_table.setItem(row_index, col_index, item)
        finally:
            self.result_table.setUpdatesEnabled(True)
        self._update_result_action_state()

    def _set_home_mode(self) -> None:
        self.filter_bar.hide()
        self.result_panel.hide()
        self.status_label.hide()
        self.progress_bar.hide()
        self.setMinimumSize(640, 160)
        self.resize(760, 190)
        self.search_shell.setMinimumWidth(0)
        self.search_shell.setMaximumWidth(16777215)
        self.search_input.setMinimumHeight(58)
        self.home_top_spacer.changeSize(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.home_bottom_spacer.changeSize(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.centralWidget().layout().invalidate()
        self._move_to_automatic_position("home")

    def _set_search_mode(self) -> None:
        self.filter_bar.show()
        self.result_panel.show()
        self.status_label.show()
        self.setMinimumSize(1100, 680)
        if self.width() < 1180 or self.height() < 760:
            self.resize(1180, 760)
        self.search_shell.setMinimumWidth(0)
        self.search_shell.setMaximumWidth(16777215)
        self.search_input.setMinimumHeight(54)
        self.home_top_spacer.changeSize(0, 0, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.home_bottom_spacer.changeSize(0, 0, QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.centralWidget().layout().invalidate()
        self._move_to_automatic_position("search")

    def _update_progress_bar(self, message: str) -> None:
        progress = parse_progress(message)
        if progress is None:
            self.progress_bar.setRange(0, 0)
        else:
            current, total = progress
            self.progress_bar.setRange(0, max(total, 1))
            self.progress_bar.setValue(current)
        self.progress_bar.show()

    def selected_path(self) -> str | None:
        image_items = self.image_list.selectedItems()
        if image_items:
            return image_items[0].data(Qt.UserRole)
        selected = self.result_table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        item = self.result_table.item(row, 0)
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def _on_image_selection_changed(self) -> None:
        if self._syncing_result_selection:
            self._update_result_action_state()
            return
        if self.image_list.selectedItems():
            self._syncing_result_selection = True
            self.result_table.clearSelection()
            self._syncing_result_selection = False
        self._update_result_action_state()

    def _on_table_selection_changed(self) -> None:
        if self._syncing_result_selection:
            self._update_result_action_state()
            return
        if self.result_table.selectedItems():
            self._syncing_result_selection = True
            self.image_list.clearSelection()
            self._syncing_result_selection = False
        self._update_result_action_state()

    def _update_result_action_state(self) -> None:
        if not hasattr(self, "similar_button"):
            return
        path = self.selected_path()
        has_selection = bool(path)
        self.open_button.setEnabled(has_selection)
        self.reveal_button.setEnabled(has_selection)
        self.copy_button.setEnabled(has_selection)
        is_image = bool(path and Path(path).suffix.lower().lstrip(".") in {"png", "jpg", "jpeg", "heic"})
        self.similar_button.setEnabled(is_image)

    def open_selected_file(self) -> None:
        path = self.selected_path()
        if path:
            open_file(path)

    def reveal_selected_file(self) -> None:
        path = self.selected_path()
        if path:
            reveal_in_finder(path)

    def copy_selected_path(self) -> None:
        path = self.selected_path()
        if path:
            QApplication.clipboard().setText(path)
            self.status_label.setText(tr("已复制完整路径"))

    def find_similar_selected_image(self) -> None:
        path = self.selected_path()
        if not path:
            self.status_label.setText(tr("请先选中一张图片"))
            return
        if Path(path).suffix.lower().lstrip(".") not in {"png", "jpg", "jpeg", "heic"}:
            self.status_label.setText(tr("相似图片只支持图片文件"))
            return
        if not self.db.get_bool_setting(SEMANTIC_ENABLED_SETTING, False):
            self.status_label.setText(tr("请先在设置中启用语义搜索并扫描图片语义"))
            return
        try:
            results = SemanticSearcher(self.db).search_similar_image(path, category=CATEGORY_IMAGES)
        except Exception as exc:  # noqa: BLE001 - UI action should report backend errors without crashing.
            self.status_label.setText(f"{tr('查找相似图片失败')}：{exc}")
            return

        self.results = results
        self.search_input.setText(Path(path).name)
        self._set_search_mode()
        self._show_search_results(results)
        self.status_label.setText(f"{tr('相似图片')}：{len(results)} {tr('条结果')}")

    def _apply_macos_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: transparent;
            }
            QWidget#appRoot {
                background: transparent;
            }
            QWidget {
                color: #1d1d1f;
                font-family: "Helvetica Neue", "Arial";
                font-size: 13px;
            }
            QWidget#searchShell {
                background: rgba(255, 255, 255, 0.74);
                border: 1px solid rgba(255, 255, 255, 0.88);
                border-radius: 16px;
            }
            QLabel#heroTitle {
                color: #111827;
                font-size: 19px;
                font-weight: 700;
            }
            QLabel#quickEntryHint {
                color: #6b7280;
                font-size: 12px;
            }
            QWidget#filterBar {
                background: transparent;
            }
            QWidget#resultPanel {
                background: rgba(255, 255, 255, 0.72);
                border: 1px solid rgba(255, 255, 255, 0.86);
                border-radius: 14px;
            }
            QLineEdit#searchField {
                background: rgba(255, 255, 255, 0.88);
                border: 1px solid rgba(205, 213, 224, 0.84);
                border-radius: 14px;
                padding: 11px 17px;
                font-size: 22px;
                selection-background-color: #0a84ff;
            }
            QLineEdit#searchField:focus {
                border: 1px solid rgba(10, 132, 255, 0.42);
                background: rgba(255, 255, 255, 0.94);
            }
            QPushButton#primarySearchButton {
                background: #0a84ff;
                border: 1px solid #0a84ff;
                border-radius: 14px;
                color: #ffffff;
                font-weight: 700;
                min-width: 76px;
                padding: 10px 17px;
            }
            QPushButton#primarySearchButton:hover {
                background: #0b74dc;
            }
            QPushButton#inlineSettingsButton {
                background: rgba(255, 255, 255, 0.68);
                border: 1px solid rgba(255, 255, 255, 0.78);
                border-radius: 10px;
                color: #59616d;
                padding: 5px 10px;
                font-size: 12px;
            }
            QPushButton#inlineSettingsButton:hover {
                background: rgba(255, 255, 255, 0.72);
            }
            QPushButton#inlineCloseButton {
                background: rgba(255, 255, 255, 0.66);
                border: 1px solid rgba(255, 255, 255, 0.78);
                border-radius: 12px;
                color: #6b7280;
                font-size: 16px;
                font-weight: 600;
                padding: 0;
            }
            QPushButton#inlineCloseButton:hover {
                background: rgba(255, 95, 86, 0.92);
                border: 1px solid rgba(255, 95, 86, 0.96);
                color: #ffffff;
            }
            QPushButton {
                background: rgba(255, 255, 255, 0.78);
                border: 1px solid rgba(255, 255, 255, 0.86);
                border-radius: 8px;
                padding: 8px 14px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.82);
            }
            QPushButton:pressed {
                background: rgba(229, 235, 244, 0.90);
            }
            QPushButton:disabled {
                color: #6f7682;
                background: rgba(237, 239, 242, 0.82);
                border: 1px solid rgba(210, 218, 230, 0.78);
            }
            QPushButton[utilityButton="true"] {
                background: rgba(255, 255, 255, 0.74);
                border: 1px solid rgba(214, 222, 233, 0.84);
                border-radius: 8px;
                color: #374151;
                min-height: 28px;
                padding: 6px 10px;
            }
            QPushButton[utilityButton="true"]:hover {
                background: rgba(255, 255, 255, 0.78);
            }
            QPushButton[filterChip="true"] {
                background: rgba(255, 255, 255, 0.88);
                border: 1px solid rgba(255, 255, 255, 0.94);
                border-radius: 12px;
                padding: 8px 15px;
            }
            QPushButton[filterChip="true"]:hover {
                background: rgba(255, 255, 255, 0.94);
                border: 1px solid rgba(255, 255, 255, 0.98);
            }
            QPushButton[filterChip="true"]:checked {
                background: rgba(10, 132, 255, 0.32);
                border: 1px solid rgba(10, 132, 255, 0.42);
                color: #075fb8;
                font-weight: 600;
            }
            QLabel[sidebarTitle="true"] {
                color: #3a3a3c;
                font-weight: 600;
                padding: 4px 0;
            }
            QLabel[sectionLabel="true"] {
                color: #5b6472;
                font-weight: 600;
                padding: 6px 10px 0 10px;
            }
            QLabel#semanticStatus {
                color: #58606f;
                background: rgba(245, 247, 250, 0.82);
                border: 1px solid rgba(218, 226, 236, 0.70);
                border-radius: 8px;
                padding: 6px 10px;
            }
            QCheckBox {
                spacing: 8px;
            }
            QListWidget#sidebarList {
                background: transparent;
                border: 0;
                color: #4b5563;
                padding: 6px 2px;
            }
            QListWidget#sidebarList::item {
                padding: 7px 8px;
                border-radius: 8px;
            }
            QListWidget#sidebarList::item:selected {
                background: #e8f2ff;
                color: #0a58ca;
            }
            QListWidget#imageList {
                background: rgba(255, 255, 255, 0.62);
                border: 0;
                border-radius: 10px;
                padding: 6px;
            }
            QTableWidget {
                background: rgba(255, 255, 255, 0.68);
                alternate-background-color: rgba(246, 248, 251, 0.76);
                border: 0;
                border-radius: 12px;
                gridline-color: rgba(225, 231, 240, 0.72);
                selection-background-color: rgba(10, 132, 255, 0.16);
                selection-color: #1d1d1f;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 14px;
                margin: 8px 2px 8px 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(82, 82, 88, 0.56);
                border-radius: 6px;
                min-height: 56px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(82, 82, 88, 0.72);
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
                background: transparent;
                border: 0;
            }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QListWidget#imageList::item {
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget#imageList::item:selected {
                background: #dbeafe;
            }
            QHeaderView::section {
                background: rgba(255, 255, 255, 0.82);
                border: 0;
                border-bottom: 1px solid rgba(210, 218, 230, 0.68);
                padding: 8px;
                font-weight: 600;
            }
            QTabWidget::pane {
                border: 0;
            }
            QTabBar::tab {
                background: #e9e9ed;
                border-radius: 8px;
                padding: 7px 16px;
                margin: 2px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                border: 1px solid #d2d2d7;
            }
            QProgressBar {
                background: rgba(198, 207, 220, 0.56);
                border: 0;
                border-radius: 3px;
                max-height: 6px;
            }
            QProgressBar::chunk {
                background: #0a84ff;
                border-radius: 3px;
            }
            QLabel#statusLine {
                color: #5f6673;
                padding: 2px 0;
            }
            """
        )


def human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def format_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def display_type(result) -> str:
    label = category_label(result.category)
    if result.extension:
        return f"{label} / {result.extension.upper()}"
    return label


def thumbnail_for(path: str) -> QPixmap:
    pixmap = QPixmap(path)
    if pixmap.isNull():
        pixmap = QPixmap(116, 86)
        pixmap.fill(Qt.lightGray)
    return pixmap.scaled(116, 86, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)


def display_scan_path(path: str) -> str:
    if path == "/":
        return "Macintosh HD（全盘）"
    return path


def format_semantic_summary(summary: dict[str, dict[str, int]]) -> str:
    labels = [
        (MODALITY_PDF_TEXT, "PDF语义"),
        (MODALITY_IMAGE_OCR_TEXT, "图片文字语义"),
        (MODALITY_IMAGE, "图片视觉语义"),
        (MODALITY_IMAGE_SIMILARITY, "相似图片"),
    ]
    parts = []
    for modality, label in labels:
        counts = summary.get(modality, {"items": 0, "errors": 0})
        parts.append(f"{label} {counts['items']} 项，错误 {counts['errors']} 项")
    return "；".join(parts)


def unmanaged_external_volumes(managed_dirs: list[str]) -> list[Path]:
    volumes_root = Path("/Volumes")
    if not volumes_root.exists():
        return []

    volumes = []
    for volume in volumes_root.iterdir():
        if volume.name.startswith(".") or not volume.is_dir():
            continue
        try:
            resolved = volume.resolve()
        except OSError:
            continue
        if not is_scannable_external_volume(resolved):
            continue
        if resolved == Path("/") or str(resolved).startswith("/System/Volumes"):
            continue
        if is_path_covered(str(volume), managed_dirs):
            continue
        volumes.append(volume)
    return volumes


def is_scannable_external_volume(volume: Path) -> bool:
    try:
        if not os.access(volume, os.W_OK):
            return False
        visible_items = [item for item in volume.iterdir() if not item.name.startswith(".")]
    except OSError:
        return False

    installer_suffixes = {".app", ".pkg", ".mpkg"}
    installer_items = [item for item in visible_items if item.suffix.lower() in installer_suffixes]
    if visible_items and len(visible_items) <= 5 and installer_items:
        return False
    return True


def is_path_covered(path: str, managed_dirs: list[str]) -> bool:
    candidate = Path(path).expanduser().resolve()
    for managed in managed_dirs:
        managed_path = Path(managed).expanduser().resolve()
        if managed_path == Path("/") and (candidate == Path("/Volumes") or Path("/Volumes") in candidate.parents):
            continue
        if candidate == managed_path or managed_path in candidate.parents:
            return True
    return False


def parse_progress(message: str) -> tuple[int, int] | None:
    marker = "处理 "
    if marker not in message:
        return None
    tail = message.split(marker, 1)[1]
    first = tail.split(" ", 1)[0]
    if "/" not in first:
        return None
    current_text, total_text = first.split("/", 1)
    if not current_text.isdigit() or not total_text.isdigit():
        return None
    return int(current_text), int(total_text)
