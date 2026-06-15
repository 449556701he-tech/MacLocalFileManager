from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, QRect, Qt, QThread, QEvent

from database import FileDatabase
from models import FileRecord
from ui.main_window import ENGINEERING_MODE_SETTING, MainWindow


class MainWindowRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db = FileDatabase(self.root / "test.sqlite3")
        self.window = MainWindow(self.db)
        self.window.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.close()
        for _ in range(20):
            self.app.processEvents()
            if self.window.search_thread is None and self.window.scan_thread is None:
                break
            time.sleep(0.02)
        self.temp_dir.cleanup()

    def test_search_box_updates_results_from_background_search(self) -> None:
        self._add_indexed_file("60亩总平面图A版.pdf")
        self._add_indexed_file("60亩总平面图B版.pdf")

        self.window.search_input.setText("60亩")
        self.window.run_search()
        self._wait_for_search_results()

        filenames = [
            self.window.result_table.item(row, 0).text()
            for row in range(self.window.result_table.rowCount())
        ]
        self.assertIn("60亩总平面图A版.pdf", filenames)
        self.assertIn("60亩总平面图B版.pdf", filenames)

    def test_startup_does_not_begin_heavy_scan_automatically(self) -> None:
        managed = self.root / "managed"
        managed.mkdir()
        db = FileDatabase(self.root / "managed.sqlite3")
        db.add_managed_dir(managed, time.time())

        class CountingMainWindow(MainWindow):
            def __init__(self, db: FileDatabase) -> None:
                self.rescan_calls = 0
                super().__init__(db)

            def rescan_index(self) -> None:
                self.rescan_calls += 1

        window = CountingMainWindow(db)
        window.show()
        deadline = time.time() + 0.5
        while time.time() < deadline:
            self.app.processEvents()
            time.sleep(0.02)
        try:
            self.assertEqual(window.rescan_calls, 0)
        finally:
            window.close()

    def test_v8_spotlight_home_is_collapsed_until_query(self) -> None:
        self.assertEqual(self.window.search_shell.objectName(), "searchShell")
        self.assertEqual(self.window.search_input.placeholderText(), "搜索本机文件、图片、文档、剪切板")
        self.assertEqual(self.window.hero_title.text(), "本地聚合搜索")
        self.assertLessEqual(self.window.width(), 820)
        self.assertLessEqual(self.window.height(), 260)
        self.assertFalse(self.window.filter_bar.isVisible())
        self.assertFalse(self.window.result_panel.isVisible())
        self.assertFalse(self.window.semantic_button.isVisible())

    def test_english_launch_entry_uses_english_visible_labels(self) -> None:
        code = """
import os
import sys
import tempfile
from pathlib import Path
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['MACLOCALFILEMANAGER_LANG'] = 'en'
sys.path.insert(0, str(Path.cwd()))
from PySide6.QtWidgets import QApplication
from database import FileDatabase
from ui.main_window import MainWindow
app = QApplication([])
tmp = tempfile.TemporaryDirectory()
window = MainWindow(FileDatabase(Path(tmp.name) / 'test.sqlite3'))
app.processEvents()
labels = [button.text() for button in window.category_buttons.values()]
print(window.hero_title.text())
print(window.search_input.placeholderText())
print(window.settings_button.text())
print('|'.join(labels))
window.close()
tmp.cleanup()
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            timeout=10,
            check=True,
        )

        self.assertIn("Local Search", result.stdout)
        self.assertIn("Search local files, images, documents, clipboard", result.stdout)
        self.assertIn("Settings", result.stdout)
        self.assertIn("All|Images|Documents|Apps|Archives|Web|Other", result.stdout)

    def test_window_uses_frameless_spotlight_chrome(self) -> None:
        self.assertTrue(bool(self.window.windowFlags() & Qt.FramelessWindowHint))
        self.assertTrue(self.window.testAttribute(Qt.WA_TranslucentBackground))
        self.assertFalse(self.window.menuBar().isVisible())
        self.assertEqual(self.window.settings_button.text(), "设置")
        self.assertTrue(self.window.settings_button.isVisible())
        self.assertEqual(self.window.close_button.text(), "×")
        self.assertTrue(self.window.close_button.isVisible())

    def test_inline_close_button_closes_window(self) -> None:
        self.window.close_button.click()
        self.app.processEvents()

        self.assertFalse(self.window.isVisible())

    def test_v8_search_expands_with_general_categories_only(self) -> None:
        self.window.search_input.setText("付款截图")
        self.window.run_search()
        self.app.processEvents()

        self.assertTrue(self.window.filter_bar.isVisible())
        self.assertTrue(self.window.result_panel.isVisible())
        self.assertGreaterEqual(self.window.width(), 1100)
        self.assertGreaterEqual(self.window.height(), 680)
        self.assertGreaterEqual(self.window.search_shell.width(), 1040)
        self.assertLessEqual(self.window.width() - self.window.search_shell.width(), 80)
        visible_filters = [
            button.text()
            for button in self.window.category_buttons.values()
            if button.isVisible()
        ]
        self.assertIn("全部", visible_filters)
        self.assertIn("图片", visible_filters)
        self.assertIn("文档", visible_filters)
        self.assertNotIn("语义搜索", visible_filters)
        self.assertNotIn("图纸", visible_filters)
        self.assertNotIn("CAD", visible_filters)
        self.assertNotIn("清单", visible_filters)

    def test_engineering_categories_can_be_enabled_from_settings(self) -> None:
        self.window.search_input.setText("图纸")
        self.window.run_search()
        self.app.processEvents()

        visible_filters = [
            button.text()
            for button in self.window.category_buttons.values()
            if button.isVisible()
        ]
        self.assertNotIn("图纸", visible_filters)
        self.assertNotIn("CAD", visible_filters)
        self.assertNotIn("清单", visible_filters)

        self.db.set_bool_setting(ENGINEERING_MODE_SETTING, True)
        self.window._load_settings()
        self.app.processEvents()

        visible_filters = [
            button.text()
            for button in self.window.category_buttons.values()
            if button.isVisible()
        ]
        self.assertIn("图纸", visible_filters)
        self.assertIn("CAD", visible_filters)
        self.assertIn("清单", visible_filters)

    def test_v8_visual_style_uses_search_header_and_compact_utilities(self) -> None:
        style = self.window.styleSheet()
        self.assertIn("QWidget#searchShell", style)
        self.assertIn("QLabel#heroTitle", style)
        self.assertIn('QPushButton[filterChip="true"]', style)
        self.assertIn("QPushButton#inlineCloseButton", style)
        self.assertIn("rgba(255, 255, 255", style)
        self.assertIn("QScrollBar:vertical", style)
        self.assertIn("QScrollBar::handle:vertical", style)

    def test_filter_chips_are_opaque_enough_to_read(self) -> None:
        style = self.window.styleSheet()

        self.assertIn("QPushButton[filterChip=\"true\"] {\n                background: rgba(255, 255, 255, 0.82);", style)
        self.assertIn("border: 1px solid rgba(255, 255, 255, 0.90);", style)
        self.assertIn("QPushButton[filterChip=\"true\"]:checked {\n                background: rgba(10, 132, 255, 0.32);", style)

    def test_frameless_window_does_not_paint_rectangular_outer_frame(self) -> None:
        margins = self.window.centralWidget().layout().contentsMargins()
        self.assertLessEqual(margins.left(), 8)
        self.assertLessEqual(margins.top(), 8)
        self.assertLessEqual(margins.right(), 8)
        self.assertLessEqual(margins.bottom(), 8)

        style = self.window.styleSheet()
        self.assertIn("QMainWindow {\n                background: transparent;", style)
        self.assertIn("QWidget#appRoot {\n                background: transparent;", style)
        self.assertNotIn("qlineargradient", style)
        self.assertNotIn("#edf3f9", style)

    def test_search_shell_tracks_window_width_in_home_mode(self) -> None:
        self.app.processEvents()

        self.assertLessEqual(self.window.width() - self.window.search_shell.width(), 80)

    def test_frameless_window_can_start_dragging_from_header_text(self) -> None:
        press = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(20, 20),
            QPointF(120, 120),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        release = QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(20, 20),
            QPointF(120, 120),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )

        self.assertTrue(self.window.eventFilter(self.window.hero_title, press))
        self.assertTrue(self.window._dragging_window)
        self.assertTrue(self.window.eventFilter(self.window.hero_title, release))
        self.assertFalse(self.window._dragging_window)

    def test_home_mode_places_collapsed_window_on_upper_golden_line(self) -> None:
        self.window._available_screen_geometry = lambda: QRect(0, 0, 1440, 900)

        self.window._set_home_mode()

        self.assertEqual(self.window.x(), (1440 - self.window.width()) // 2)
        expected_center_y = round(900 * 0.382)
        self.assertLessEqual(abs(self.window.geometry().center().y() - expected_center_y), 2)

    def test_search_mode_centers_expanded_window_until_user_moves_it(self) -> None:
        self.window._available_screen_geometry = lambda: QRect(0, 0, 1440, 900)

        self.window._set_search_mode()

        self.assertLessEqual(abs(self.window.geometry().center().x() - 720), 2)
        self.assertLessEqual(abs(self.window.geometry().center().y() - 450), 2)

        self.window.move(40, 50)
        self.window._user_moved_window = True
        self.window._set_search_mode()

        self.assertEqual(self.window.pos().x(), 40)
        self.assertEqual(self.window.pos().y(), 50)

    def test_close_waits_for_running_search_thread(self) -> None:
        thread = QThread()
        thread.start()
        self.window.search_thread = thread
        self.window.pending_search = ("付款", True)

        self.window.close()
        self.app.processEvents()

        try:
            self.assertTrue(thread.isRunning())
            self.assertTrue(self.window.close_after_search)
            self.assertTrue(self.window.is_closing)
            self.assertIsNone(self.window.pending_search)
            self.assertTrue(self.window.isVisible())
        finally:
            thread.quit()
            thread.wait(1000)
            self.window.search_thread = None

    def _add_indexed_file(self, name: str) -> None:
        path = self.root / name
        path.write_text("fixture", encoding="utf-8")
        self.db.upsert_file(FileRecord.from_path(path, time.time()))

    def _wait_for_search_results(self) -> None:
        deadline = time.time() + 1.0
        while time.time() < deadline:
            self.app.processEvents()
            if self.window.search_thread is None and self.window.result_table.rowCount() > 0:
                return
            time.sleep(0.01)
        self.fail("search results did not reach the table within 1s")


if __name__ == "__main__":
    unittest.main()
