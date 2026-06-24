from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog, QLabel, QPushButton

from database import FileDatabase
from ui.main_window import MainWindow


class FakeHotkeyRegistrar:
    backend_name = "fake"

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.registered = False
        self.unregistered = False
        self.callback = None

    def register(self, callback) -> None:
        if self.fail:
            raise RuntimeError("需要在系统设置中允许辅助功能权限")
        self.callback = callback
        self.registered = True

    def unregister(self) -> None:
        self.unregistered = True

    def trigger(self) -> None:
        if self.callback is not None:
            self.callback()


class FakeTrayIcon:
    class FakeSignal:
        def __init__(self) -> None:
            self.callback = None

        def connect(self, callback) -> None:
            self.callback = callback

        def emit(self, reason=None) -> None:
            if self.callback is not None:
                self.callback(reason)

    def __init__(self, icon=None, parent=None) -> None:
        self.icon = icon
        self.parent = parent
        self.tooltip = ""
        self.menu = None
        self.visible = False
        self.activated = self.FakeSignal()

    def setToolTip(self, text: str) -> None:
        self.tooltip = text

    def setContextMenu(self, menu) -> None:
        self.menu = menu

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False


class MacOSIntegrationTest(unittest.TestCase):
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
        self.window.is_closing = True
        self.window.close()
        self.app.processEvents()
        self.temp_dir.cleanup()

    def test_controller_installs_menu_bar_status_icon_and_global_hotkey(self) -> None:
        from macos_integration import MacOSAppController

        hotkey = FakeHotkeyRegistrar()
        controller = MacOSAppController(
            self.app,
            self.window,
            self.db,
            hotkey_registrar=hotkey,
            tray_icon_factory=FakeTrayIcon,
            tray_available=lambda: True,
        )

        controller.install()

        self.assertFalse(self.app.quitOnLastWindowClosed())
        self.assertTrue(self.window.close_to_background)
        self.assertTrue(hotkey.registered)
        self.assertIsNotNone(controller.tray_icon)
        self.assertTrue(controller.tray_icon.visible)
        self.assertEqual(controller.tray_icon.tooltip, "MacLocalFileManager")
        self.assertIsNone(controller.tray_icon.menu)

    def test_status_icon_activation_opens_custom_menu_panel_without_native_menu(self) -> None:
        from macos_integration import MacOSAppController

        controller = MacOSAppController(
            self.app,
            self.window,
            self.db,
            hotkey_registrar=FakeHotkeyRegistrar(),
            tray_icon_factory=FakeTrayIcon,
            tray_available=lambda: True,
        )
        controller.install()

        controller.tray_icon.activated.emit(None)
        self.app.processEvents()
        self.assertIsNotNone(controller.quick_menu)
        self.assertTrue(controller.quick_menu.isVisible())
        self.assertIsNone(controller.tray_icon.menu)

        controller.tray_icon.activated.emit(None)
        self.app.processEvents()
        self.assertFalse(controller.quick_menu.isVisible())

    def test_custom_menu_panel_exposes_actions_including_quit(self) -> None:
        from macos_integration import MacOSAppController

        hotkey = FakeHotkeyRegistrar()
        hotkey.backend_name = "fake"
        controller = MacOSAppController(
            self.app,
            self.window,
            self.db,
            hotkey_registrar=hotkey,
            tray_icon_factory=FakeTrayIcon,
            tray_available=lambda: True,
        )
        controller.install()
        controller.show_quick_menu()

        labels = [button.text() for button in controller.quick_menu.findChildren(QPushButton)]
        status = controller.quick_menu.findChild(QLabel, "trayHotkeyStatus")

        self.assertIn("显示/隐藏搜索", labels)
        self.assertIn("扫描设置", labels)
        self.assertIn("刷新文件索引", labels)
        self.assertIn("退出", labels)
        self.assertEqual(status.text(), "快捷键：⌃F · fake")

    def test_custom_menu_panel_positions_near_clicked_menu_bar_icon(self) -> None:
        from macos_integration import MacOSAppController

        controller = MacOSAppController(
            self.app,
            self.window,
            self.db,
            hotkey_registrar=FakeHotkeyRegistrar(),
            tray_icon_factory=FakeTrayIcon,
            tray_available=lambda: True,
            cursor_position_provider=lambda: QPoint(620, 12),
            screen_geometry_provider=lambda _anchor: QRect(0, 0, 800, 600),
        )
        controller.install()

        controller.show_quick_menu()
        self.app.processEvents()

        self.assertIsNotNone(controller.quick_menu)
        panel_center_x = controller.quick_menu.x() + controller.quick_menu.width() // 2
        self.assertLess(abs(panel_center_x - 620), 16)
        self.assertGreaterEqual(controller.quick_menu.y(), 8)

    def test_custom_menu_panel_clamps_to_screen_edges(self) -> None:
        from macos_integration import MacOSAppController

        controller = MacOSAppController(
            self.app,
            self.window,
            self.db,
            hotkey_registrar=FakeHotkeyRegistrar(),
            tray_icon_factory=FakeTrayIcon,
            tray_available=lambda: True,
            cursor_position_provider=lambda: QPoint(790, 12),
            screen_geometry_provider=lambda _anchor: QRect(0, 0, 800, 600),
        )
        controller.install()

        controller.show_quick_menu()
        self.app.processEvents()

        self.assertLessEqual(controller.quick_menu.x() + controller.quick_menu.width(), 792)

    def test_custom_menu_panel_uses_more_readable_opaque_style(self) -> None:
        from macos_integration import MacOSAppController

        controller = MacOSAppController(
            self.app,
            self.window,
            self.db,
            hotkey_registrar=FakeHotkeyRegistrar(),
            tray_icon_factory=FakeTrayIcon,
            tray_available=lambda: True,
        )

        panel = controller._build_quick_menu()
        surface = panel.findChild(type(panel), "trayQuickMenuSurface")

        self.assertIsNotNone(surface)
        self.assertIn("QFrame#trayQuickMenu {\n                background: transparent", panel.styleSheet())
        self.assertIn("QFrame#trayQuickMenuSurface", panel.styleSheet())
        self.assertIn("background-color: #ffffff", panel.styleSheet())
        self.assertIn("border-radius: 14px", panel.styleSheet())
        self.assertIn("color: #000000", panel.styleSheet())

    def test_controller_toggles_window_from_hotkey(self) -> None:
        from macos_integration import MacOSAppController

        hotkey = FakeHotkeyRegistrar()
        controller = MacOSAppController(
            self.app,
            self.window,
            self.db,
            hotkey_registrar=hotkey,
            tray_icon_factory=FakeTrayIcon,
            tray_available=lambda: True,
        )
        controller.install()

        hotkey.trigger()
        self.app.processEvents()
        self.assertFalse(self.window.isVisible())

        hotkey.trigger()
        self.app.processEvents()
        self.assertTrue(self.window.isVisible())
        self.assertTrue(self.window.search_focus_requested)

    def test_hotkey_registration_failure_keeps_app_usable(self) -> None:
        from macos_integration import MacOSAppController

        controller = MacOSAppController(
            self.app,
            self.window,
            self.db,
            hotkey_registrar=FakeHotkeyRegistrar(fail=True),
            tray_icon_factory=FakeTrayIcon,
            tray_available=lambda: True,
        )

        controller.install()

        self.assertEqual(controller.hotkey_status, "failed")
        self.assertIn("全局快捷键未启用", self.window.status_label.text())
        self.assertTrue(self.window.isVisible())

    def test_hotkey_registration_falls_back_to_next_backend(self) -> None:
        from macos_integration import MacOSAppController

        failing = FakeHotkeyRegistrar(fail=True)
        working = FakeHotkeyRegistrar()
        working.backend_name = "working"
        controller = MacOSAppController(
            self.app,
            self.window,
            self.db,
            hotkey_registrar=[failing, working],
            tray_icon_factory=FakeTrayIcon,
            tray_available=lambda: True,
        )

        controller.install()

        self.assertEqual(controller.hotkey_status, "registered")
        self.assertEqual(controller.hotkey_backend, "working")
        self.assertFalse(failing.registered)
        self.assertTrue(working.registered)

    def test_hotkey_can_be_disabled_from_settings(self) -> None:
        from macos_integration import HOTKEY_ENABLED_SETTING, MacOSAppController

        self.db.set_bool_setting(HOTKEY_ENABLED_SETTING, False)
        hotkey = FakeHotkeyRegistrar()
        controller = MacOSAppController(
            self.app,
            self.window,
            self.db,
            hotkey_registrar=hotkey,
            tray_icon_factory=FakeTrayIcon,
            tray_available=lambda: True,
        )

        controller.install()

        self.assertEqual(controller.hotkey_status, "disabled")
        self.assertFalse(hotkey.registered)

    def test_settings_dialog_exposes_global_hotkey_toggle(self) -> None:
        from macos_integration import HOTKEY_ENABLED_SETTING

        captured = {}

        def fake_exec(dialog) -> int:
            captured["dialog"] = dialog
            return 0

        with patch.object(QDialog, "exec", fake_exec):
            self.window.open_settings_dialog()

        dialog = captured["dialog"]
        checkbox = dialog.findChild(QCheckBox, "globalHotkeyCheckbox")
        self.assertIsNotNone(checkbox)
        self.assertEqual(checkbox.text(), "启用全局快捷键（⌃F）")
        self.assertTrue(checkbox.isChecked())

        checkbox.setChecked(False)

        self.assertFalse(self.db.get_bool_setting(HOTKEY_ENABLED_SETTING, True))

    def test_close_hides_to_background_when_controller_is_installed(self) -> None:
        from macos_integration import MacOSAppController

        controller = MacOSAppController(
            self.app,
            self.window,
            self.db,
            hotkey_registrar=FakeHotkeyRegistrar(),
            tray_icon_factory=FakeTrayIcon,
            tray_available=lambda: True,
        )
        controller.install()

        self.window.close()
        self.app.processEvents()

        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.window.is_closing)

    def test_global_hotkey_registrar_matches_control_f(self) -> None:
        from macos_integration import MacGlobalHotkeyRegistrar

        class FakeEvent:
            def __init__(self, key_code: int, modifiers: int) -> None:
                self._key_code = key_code
                self._modifiers = modifiers

            def keyCode(self) -> int:
                return self._key_code

            def modifierFlags(self) -> int:
                return self._modifiers

        registrar = MacGlobalHotkeyRegistrar(
            event_api=object(),
            control_modifier=0b001,
            modifier_mask=0b111,
        )

        self.assertTrue(registrar.event_matches(FakeEvent(3, 0b001)))
        self.assertFalse(registrar.event_matches(FakeEvent(3, 0b011)))
        self.assertFalse(registrar.event_matches(FakeEvent(49, 0b001)))

    def test_global_hotkey_registrar_unregisters_installed_monitors(self) -> None:
        from macos_integration import MacGlobalHotkeyRegistrar

        class FakeEventApi:
            NSEventMaskKeyDown = 1

            def __init__(self) -> None:
                self.removed = []

            def addGlobalMonitorForEventsMatchingMask_handler_(self, _mask, _handler):
                return "global-token"

            def addLocalMonitorForEventsMatchingMask_handler_(self, _mask, _handler):
                return "local-token"

            def removeMonitor_(self, token) -> None:
                self.removed.append(token)

        api = FakeEventApi()
        registrar = MacGlobalHotkeyRegistrar(event_api=api)

        registrar.register(lambda: None)
        registrar.unregister()

        self.assertEqual(api.removed, ["global-token", "local-token"])

    def test_carbon_global_hotkey_registers_control_f(self) -> None:
        from macos_integration import (
            CARBON_CONTROL_MODIFIER,
            F_KEY_CODE,
            CarbonGlobalHotkeyRegistrar,
        )

        class FakeCarbonApi:
            def __init__(self) -> None:
                self.registered = None
                self.unregistered = []
                self.removed_handlers = []
                self.handler_callback = None

            def GetApplicationEventTarget(self):
                return 111

            def InstallEventHandler(self, target, handler, count, event_types, user_data, handler_ref):
                self.handler_callback = handler
                handler_ref._obj.value = 222
                return 0

            def RegisterEventHotKey(self, key_code, modifiers, hotkey_id, target, options, hotkey_ref):
                self.registered = (key_code, modifiers, hotkey_id.id, target, options)
                hotkey_ref._obj.value = 333
                return 0

            def UnregisterEventHotKey(self, hotkey_ref):
                self.unregistered.append(hotkey_ref.value)
                return 0

            def RemoveEventHandler(self, handler_ref):
                self.removed_handlers.append(handler_ref.value)
                return 0

        api = FakeCarbonApi()
        registrar = CarbonGlobalHotkeyRegistrar(carbon_api=api)
        calls = []

        registrar.register(lambda: calls.append("open"))
        registrar._handle_event(None, None, None)
        registrar.unregister()

        self.assertEqual(api.registered[:2], (F_KEY_CODE, CARBON_CONTROL_MODIFIER))
        self.assertEqual(api.registered[2], 1)
        self.assertEqual(api.unregistered, [333])
        self.assertEqual(api.removed_handlers, [222])
        self.assertEqual(calls, ["open"])

    def test_carbon_global_hotkey_registration_failure_reports_status(self) -> None:
        from macos_integration import CarbonGlobalHotkeyRegistrar

        class FakeCarbonApi:
            def GetApplicationEventTarget(self):
                return 111

            def InstallEventHandler(self, target, handler, count, event_types, user_data, handler_ref):
                handler_ref._obj.value = 222
                return 0

            def RegisterEventHotKey(self, key_code, modifiers, hotkey_id, target, options, hotkey_ref):
                return -9876

            def UnregisterEventHotKey(self, hotkey_ref):
                return 0

            def RemoveEventHandler(self, handler_ref):
                self.removed = handler_ref.value
                return 0

        registrar = CarbonGlobalHotkeyRegistrar(carbon_api=FakeCarbonApi())

        with self.assertRaisesRegex(RuntimeError, "RegisterEventHotKey -9876"):
            registrar.register(lambda: None)


if __name__ == "__main__":
    unittest.main()
