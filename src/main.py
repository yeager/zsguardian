"""ZSGuardian — Zero Trust Security Dashboard for macOS.

Entry point: launches the PySide6 app with async event loop integration,
system tray icon, and main dashboard window.
"""

import asyncio
import logging
import sys
import os

# Ensure src/ is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
import qasync

from dashboard import DashboardWindow
from tray import TrayManager
from keychain import load_credentials

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ZSGuardian")


def main():
    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("ZSGuardian")
    app.setOrganizationName("ZSGuardian")
    app.setQuitOnLastWindowClosed(False)  # Keep running in tray

    # Async event loop integration
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    # Dashboard
    dashboard = DashboardWindow()
    dashboard.set_event_loop(loop)

    # System tray
    tray = TrayManager()
    tray.show_dashboard.connect(dashboard.show)
    tray.show_settings.connect(dashboard.show_settings)
    tray.quit_app.connect(app.quit)
    tray.refresh_data.connect(lambda: asyncio.ensure_future(dashboard.refresh()))
    app.aboutToQuit.connect(dashboard.shutdown)
    tray.show()

    # Check if credentials exist — show settings if not
    creds = load_credentials()
    if not creds.is_complete():
        logger.info("No complete credentials found. Opening settings...")
        dashboard.show()
        dashboard.show_settings()
    else:
        dashboard.show()
        # Auto-connect on launch
        asyncio.ensure_future(dashboard._connect())

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
