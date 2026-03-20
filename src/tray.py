"""System tray icon for ZSGuardian."""

from PySide6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor, QFont, QRadialGradient
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtCore import Signal, QObject, Qt, QRect


def create_tray_icon_pixmap(connected: bool = False) -> QPixmap:
    """Generate a shield-shaped tray icon programmatically."""
    size = 64
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Shield shape via gradient circle
    color = QColor("#00D4AA") if connected else QColor("#484F58")
    grad = QRadialGradient(size / 2, size / 2, size / 2)
    grad.setColorAt(0.0, color.lighter(130))
    grad.setColorAt(0.8, color)
    grad.setColorAt(1.0, color.darker(150))

    painter.setBrush(grad)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, size - 8, size - 8)

    # "Z" letter
    painter.setPen(QColor("white"))
    painter.setFont(QFont("SF Pro Display", 28, QFont.Weight.Bold))
    painter.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "Z")

    painter.end()
    return pm


class TrayManager(QObject):
    show_dashboard = Signal()
    show_settings = Signal()
    quit_app = Signal()
    refresh_data = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tray = QSystemTrayIcon(parent)
        self._tray.setIcon(QIcon(create_tray_icon_pixmap(False)))
        self._tray.setToolTip("ZSGuardian — Disconnected")

        self._menu = QMenu()

        self._status_action = QAction("Status: Disconnected")
        self._status_action.setEnabled(False)
        self._menu.addAction(self._status_action)
        self._menu.addSeparator()

        open_action = QAction("Open Dashboard")
        open_action.triggered.connect(self.show_dashboard.emit)
        self._menu.addAction(open_action)

        refresh_action = QAction("Refresh Data")
        refresh_action.triggered.connect(self.refresh_data.emit)
        self._menu.addAction(refresh_action)

        self._menu.addSeparator()

        settings_action = QAction("Settings...")
        settings_action.triggered.connect(self.show_settings.emit)
        self._menu.addAction(settings_action)

        self._menu.addSeparator()

        quit_action = QAction("Quit ZSGuardian")
        quit_action.triggered.connect(self.quit_app.emit)
        self._menu.addAction(quit_action)

        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)

    def show(self):
        self._tray.show()

    def set_connected(self, connected: bool, tool_count: int = 0):
        self._tray.setIcon(QIcon(create_tray_icon_pixmap(connected)))
        if connected:
            self._status_action.setText(f"Connected ({tool_count} tools)")
            self._tray.setToolTip(f"ZSGuardian — Connected ({tool_count} tools)")
        else:
            self._status_action.setText("Status: Disconnected")
            self._tray.setToolTip("ZSGuardian — Disconnected")

    def notify(self, title: str, message: str):
        self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_dashboard.emit()
