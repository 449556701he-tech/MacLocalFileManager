from __future__ import annotations

import ctypes
import ctypes.util
import sys
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QAction, QColor, QCursor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
)

from database import FileDatabase
from i18n import tr


HOTKEY_ENABLED_SETTING = "global_hotkey_enabled"
DEFAULT_HOTKEY = "Control+F"
F_KEY_CODE = 3
CARBON_CONTROL_MODIFIER = 1 << 12
CARBON_HOTKEY_PRESSED = 5
CARBON_EVENT_CLASS_KEYBOARD = "keyb"


def _four_char_code(value: str) -> int:
    return int.from_bytes(value.encode("ascii"), "big")


class EventHotKeyID(ctypes.Structure):
    _fields_ = [
        ("signature", ctypes.c_uint32),
        ("id", ctypes.c_uint32),
    ]


class EventTypeSpec(ctypes.Structure):
    _fields_ = [
        ("eventClass", ctypes.c_uint32),
        ("eventKind", ctypes.c_uint32),
    ]


EventHandlerUPP = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)


class NoopHotkeyRegistrar:
    backend_name = "none"

    def register(self, callback) -> None:
        return None

    def unregister(self) -> None:
        return None


class CarbonGlobalHotkeyRegistrar:
    backend_name = "Carbon"

    def __init__(
        self,
        carbon_api=None,
        key_code: int = F_KEY_CODE,
        modifiers: int = CARBON_CONTROL_MODIFIER,
        hotkey_id: int = 1,
    ) -> None:
        self.carbon_api = carbon_api or self._load_carbon_api()
        self.key_code = int(key_code)
        self.modifiers = int(modifiers)
        self.hotkey_id = int(hotkey_id)
        self.callback = None
        self.hotkey_ref = ctypes.c_void_p()
        self.handler_ref = ctypes.c_void_p()
        self.handler_callback = None
        self._configure_carbon_api()

    def _load_carbon_api(self):
        path = ctypes.util.find_library("Carbon")
        if not path:
            raise RuntimeError(tr("当前系统不可用 Carbon 全局快捷键接口"))
        return ctypes.CDLL(path)

    def _configure_carbon_api(self) -> None:
        specs = {
            "GetApplicationEventTarget": (ctypes.c_void_p, []),
            "InstallEventHandler": (
                ctypes.c_int,
                [
                    ctypes.c_void_p,
                    EventHandlerUPP,
                    ctypes.c_uint32,
                    ctypes.POINTER(EventTypeSpec),
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_void_p),
                ],
            ),
            "RegisterEventHotKey": (
                ctypes.c_int,
                [ctypes.c_uint32, ctypes.c_uint32, EventHotKeyID, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)],
            ),
            "UnregisterEventHotKey": (ctypes.c_int, [ctypes.c_void_p]),
            "RemoveEventHandler": (ctypes.c_int, [ctypes.c_void_p]),
        }
        for name, (restype, argtypes) in specs.items():
            func = getattr(self.carbon_api, name, None)
            if func is None:
                raise RuntimeError(tr("当前系统不可用 Carbon 全局快捷键接口"))
            try:
                func.restype = restype
                func.argtypes = argtypes
            except AttributeError:
                continue

    def register(self, callback) -> None:
        self.unregister()
        self.callback = callback
        self.handler_callback = EventHandlerUPP(self._handle_event)
        event_type = EventTypeSpec(_four_char_code(CARBON_EVENT_CLASS_KEYBOARD), CARBON_HOTKEY_PRESSED)
        target = self.carbon_api.GetApplicationEventTarget()
        handler_ref = ctypes.c_void_p()
        status = self.carbon_api.InstallEventHandler(
            target,
            self.handler_callback,
            1,
            ctypes.byref(event_type),
            None,
            ctypes.byref(handler_ref),
        )
        if status != 0:
            self.callback = None
            self.handler_callback = None
            raise RuntimeError(f"InstallEventHandler {status}")

        hotkey_id = EventHotKeyID(_four_char_code("MLFM"), self.hotkey_id)
        hotkey_ref = ctypes.c_void_p()
        status = self.carbon_api.RegisterEventHotKey(
            self.key_code,
            self.modifiers,
            hotkey_id,
            target,
            0,
            ctypes.byref(hotkey_ref),
        )
        if status != 0:
            self.carbon_api.RemoveEventHandler(handler_ref)
            self.callback = None
            self.handler_callback = None
            raise RuntimeError(f"RegisterEventHotKey {status}")

        self.handler_ref = handler_ref
        self.hotkey_ref = hotkey_ref

    def unregister(self) -> None:
        if self.hotkey_ref.value:
            self.carbon_api.UnregisterEventHotKey(self.hotkey_ref)
            self.hotkey_ref = ctypes.c_void_p()
        if self.handler_ref.value:
            self.carbon_api.RemoveEventHandler(self.handler_ref)
            self.handler_ref = ctypes.c_void_p()
        self.callback = None
        self.handler_callback = None

    def _handle_event(self, _next_handler, _event, _user_data) -> int:
        if self.callback is not None:
            self.callback()
        return 0


class MacGlobalHotkeyRegistrar:
    backend_name = "AppKit"

    def __init__(
        self,
        event_api=None,
        control_modifier: int | None = None,
        modifier_mask: int | None = None,
    ) -> None:
        if event_api is None:
            import AppKit

            event_api = AppKit.NSEvent
            control_modifier = AppKit.NSControlKeyMask
            modifier_mask = AppKit.NSDeviceIndependentModifierFlagsMask
        self.event_api = event_api
        self.control_modifier = int(control_modifier or 0)
        self.modifier_mask = int(modifier_mask or 0)
        self.monitors: list[object] = []
        self.callback = None

    def register(self, callback) -> None:
        self.callback = callback
        key_mask = self.event_api.NSEventMaskKeyDown
        global_monitor = self.event_api.addGlobalMonitorForEventsMatchingMask_handler_(key_mask, self._handle_event)
        local_monitor = self.event_api.addLocalMonitorForEventsMatchingMask_handler_(key_mask, self._handle_local_event)
        if global_monitor is None and local_monitor is None:
            raise RuntimeError(tr("需要在系统设置中允许辅助功能权限"))
        self.monitors = [token for token in (global_monitor, local_monitor) if token is not None]

    def unregister(self) -> None:
        for token in self.monitors:
            self.event_api.removeMonitor_(token)
        self.monitors = []
        self.callback = None

    def event_matches(self, event) -> bool:
        modifiers = int(event.modifierFlags()) & self.modifier_mask
        return int(event.keyCode()) == F_KEY_CODE and modifiers == self.control_modifier

    def _handle_event(self, event) -> None:
        if self.event_matches(event) and self.callback is not None:
            self.callback()

    def _handle_local_event(self, event):
        if self.event_matches(event) and self.callback is not None:
            self.callback()
            return None
        return event


@dataclass
class MacOSAppController:
    app: QApplication
    window: object
    db: FileDatabase
    hotkey_registrar: object | None = None
    tray_icon_factory: object = QSystemTrayIcon
    tray_available: object = QSystemTrayIcon.isSystemTrayAvailable
    cursor_position_provider: object | None = None
    screen_geometry_provider: object | None = None

    def __post_init__(self) -> None:
        self.tray_icon = None
        self.tray_menu = None
        self.quick_menu = None
        self.hotkey_status = "not-installed"
        self.hotkey_backend = ""
        self.hotkey_error = ""
        if self.hotkey_registrar is None:
            self.hotkey_registrar = create_default_hotkey_registrars()
        if self.cursor_position_provider is None:
            self.cursor_position_provider = QCursor.pos

    def install(self) -> None:
        self.app.setQuitOnLastWindowClosed(False)
        self.window.close_to_background = True
        self._install_tray_icon()
        self._install_hotkey()

    def _install_tray_icon(self) -> None:
        if not self.tray_available():
            return
        self.tray_icon = self.tray_icon_factory(create_status_icon(), self.app)
        self.tray_icon.setToolTip("MacLocalFileManager")
        activated = getattr(self.tray_icon, "activated", None)
        if activated is not None:
            activated.connect(lambda _reason=None: self.toggle_quick_menu())
        self.tray_icon.show()

    def toggle_quick_menu(self) -> None:
        if self.quick_menu is not None and self.quick_menu.isVisible():
            self.quick_menu.hide()
            return
        self.show_quick_menu()

    def show_quick_menu(self) -> None:
        if self.quick_menu is None:
            self.quick_menu = self._build_quick_menu()
        self.quick_menu.adjustSize()
        self._position_quick_menu_near(self.cursor_position_provider())
        self.quick_menu.show()
        self.quick_menu.raise_()

    def _position_quick_menu_near(self, anchor: QPoint) -> None:
        if self.quick_menu is None:
            return
        rect = self._available_geometry_for(anchor)
        if rect is None:
            return
        margin = 8
        width = self.quick_menu.width()
        height = self.quick_menu.height()
        x = anchor.x() - width // 2
        y = anchor.y() + 18
        if y + height + margin > rect.bottom():
            y = anchor.y() - height - 12
        x = max(rect.left() + margin, min(x, rect.right() - width - margin))
        y = max(rect.top() + margin, min(y, rect.bottom() - height - margin))
        self.quick_menu.move(x, y)

    def _available_geometry_for(self, anchor: QPoint) -> QRect | None:
        if self.screen_geometry_provider is not None:
            return self.screen_geometry_provider(anchor)
        screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
        if screen is None:
            return None
        return screen.availableGeometry()

    def _build_quick_menu(self) -> QFrame:
        panel = QFrame()
        panel.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        panel.setAttribute(Qt.WA_TranslucentBackground, True)
        panel.setAutoFillBackground(False)
        panel.setObjectName("trayQuickMenu")
        outer_layout = QVBoxLayout(panel)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        surface = QFrame(panel)
        surface.setObjectName("trayQuickMenuSurface")
        outer_layout.addWidget(surface)

        layout = QVBoxLayout(surface)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(2)

        for label, callback in [
            (tr("显示/隐藏搜索"), self._quick_toggle_window),
            (tr("扫描设置"), self._quick_open_settings),
            (tr("刷新文件索引"), self._quick_rescan),
            (tr("退出"), self.quit_app),
        ]:
            button = QPushButton(label, panel)
            button.clicked.connect(callback)
            layout.addWidget(button)

        self.hotkey_status_label = QLabel(self._hotkey_status_text(), panel)
        self.hotkey_status_label.setObjectName("trayHotkeyStatus")
        layout.addWidget(self.hotkey_status_label)

        panel.setStyleSheet(
            """
            QFrame#trayQuickMenu {
                background: transparent;
                border: 0;
            }
            QFrame#trayQuickMenuSurface {
                background-color: #ffffff;
                border: 1px solid #c8c8c8;
                border-radius: 14px;
            }
            QFrame#trayQuickMenu QPushButton {
                background: #ffffff;
                border: 0;
                border-radius: 8px;
                color: #000000;
                font-size: 15px;
                font-weight: 500;
                min-width: 176px;
                padding: 10px 14px;
                text-align: left;
            }
            QFrame#trayQuickMenu QPushButton:hover {
                background: #e9f2ff;
            }
            QFrame#trayQuickMenu QLabel#trayHotkeyStatus {
                background: #ffffff;
                color: #666666;
                font-size: 12px;
                padding: 6px 14px 4px 14px;
            }
            """
        )
        return panel

    def _hotkey_status_text(self) -> str:
        if self.hotkey_status == "registered":
            return f"{tr('快捷键')}：⌃F · {self.hotkey_backend}"
        if self.hotkey_status == "disabled":
            return f"{tr('快捷键')}：{tr('已关闭')}"
        if self.hotkey_status == "failed":
            return f"{tr('快捷键')}：{tr('未启用')}"
        return f"{tr('快捷键')}：⌃F"

    def _quick_toggle_window(self) -> None:
        if self.quick_menu is not None:
            self.quick_menu.hide()
        self.toggle_window()

    def _quick_open_settings(self) -> None:
        if self.quick_menu is not None:
            self.quick_menu.hide()
        self.show_search()
        self.window.open_settings_dialog()

    def _quick_rescan(self) -> None:
        if self.quick_menu is not None:
            self.quick_menu.hide()
        self.show_search()
        self.window.rescan_index()

    def _install_hotkey(self) -> None:
        if not self.db.get_bool_setting(HOTKEY_ENABLED_SETTING, True):
            self.hotkey_status = "disabled"
            return
        registrars = self.hotkey_registrar
        if not isinstance(registrars, (list, tuple)):
            registrars = [registrars]
        errors = []
        for registrar in registrars:
            try:
                registrar.register(self.toggle_window)
            except Exception as exc:  # noqa: BLE001 - missing macOS permission should not prevent startup.
                errors.append(f"{getattr(registrar, 'backend_name', registrar.__class__.__name__)}: {exc}")
                continue
            self.hotkey_registrar = registrar
            self.hotkey_status = "registered"
            self.hotkey_backend = getattr(registrar, "backend_name", registrar.__class__.__name__)
            return
        self.hotkey_status = "failed"
        self.hotkey_error = "；".join(errors)
        self.window.status_label.show()
        self.window.status_label.setText(f"{tr('全局快捷键未启用')}：{self.hotkey_error}")

    def toggle_window(self) -> None:
        if self.window.isVisible() and self.window.isActiveWindow():
            self.window.hide()
            return
        if self.window.isVisible():
            self.window.hide()
            return
        self.show_search()

    def show_search(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.window.search_input.setFocus()
        self.window.search_focus_requested = True

    def quit_app(self) -> None:
        self.window.close_to_background = False
        self.window.is_closing = True
        unregister = getattr(self.hotkey_registrar, "unregister", None)
        if callable(unregister):
            unregister()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.window.close()
        self.app.quit()


def should_install_macos_integration() -> bool:
    return sys.platform == "darwin"


def create_default_hotkey_registrars():
    if not should_install_macos_integration():
        return [NoopHotkeyRegistrar()]
    registrars = []
    try:
        registrars.append(CarbonGlobalHotkeyRegistrar())
    except Exception:  # noqa: BLE001 - older macOS/Python builds can still use AppKit fallback.
        pass
    try:
        registrars.append(MacGlobalHotkeyRegistrar())
    except Exception:  # noqa: BLE001 - packaging or permissions may not expose AppKit.
        pass
    return registrars or [NoopHotkeyRegistrar()]


def create_default_hotkey_registrar():
    registrars = create_default_hotkey_registrars()
    return registrars[0]


def create_status_icon() -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(45, 52, 60), 3)
    painter.setPen(pen)
    painter.drawEllipse(6, 6, 14, 14)
    painter.drawLine(18, 18, 26, 26)
    painter.end()
    return QIcon(pixmap)
