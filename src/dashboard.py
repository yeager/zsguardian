"""Main dashboard window for ZscalerGuardian."""

import asyncio
import logging
from functools import partial

from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QFont, QColor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QComboBox,
    QCheckBox,
    QProgressBar,
)

from keychain import (
    KEYCHAIN_KEYS,
    LABELS,
    ZscalerCredentials,
    load_credentials,
    save_credentials,
)
from mcp_client import ZscalerMCPClient
from styles.theme import DARK_THEME, LIGHT_THEME, get_stylesheet
from widgets.score_gauge import SecurityScoreGauge
from widgets.status_cards import StatusCard, StatusCardRow
from widgets.policy_map import PolicyMapWidget, PolicyNode

logger = logging.getLogger(__name__)


# ─── Settings Dialog ──────────────────────────────────────────

class SettingsDialog(QDialog):
    """Credentials & preferences settings dialog."""

    def __init__(self, credentials: ZscalerCredentials, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ZscalerGuardian Settings")
        self.setMinimumSize(520, 480)
        self._credentials = credentials
        self._fields: dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(28, 28, 28, 28)

        # Title
        title = QLabel("Zscaler Credentials")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        subtitle = QLabel("Stored securely in macOS Keychain. Never written to disk.")
        subtitle.setObjectName("subtitle")
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        # Credential fields
        for field_key in KEYCHAIN_KEYS:
            label = QLabel(LABELS[field_key])
            label.setFont(QFont("SF Pro Display", 12, QFont.Weight.Medium))
            layout.addWidget(label)

            line = QLineEdit()
            line.setPlaceholderText(f"Enter {LABELS[field_key]}...")
            if "secret" in field_key:
                line.setEchoMode(QLineEdit.EchoMode.Password)
            current = getattr(self._credentials, field_key, "")
            if current:
                line.setText(current)
            self._fields[field_key] = line
            layout.addWidget(line)

        layout.addSpacing(12)

        # Advanced section
        adv_label = QLabel("Advanced")
        adv_label.setObjectName("cardTitle")
        layout.addWidget(adv_label)

        self._write_tools_check = QCheckBox("Enable write tools (requires --enable-write-tools)")
        layout.addWidget(self._write_tools_check)

        self._write_pattern = QLineEdit()
        self._write_pattern.setPlaceholderText("Write tools pattern (e.g., 'update_*')")
        self._write_pattern.setEnabled(False)
        self._write_tools_check.toggled.connect(self._write_pattern.setEnabled)
        layout.addWidget(self._write_pattern)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save to Keychain")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def _save(self):
        for field_key, line in self._fields.items():
            setattr(self._credentials, field_key, line.text().strip())

        if save_credentials(self._credentials):
            self.accept()
        else:
            QMessageBox.warning(self, "Error", "Failed to save some credentials to Keychain.")

    def get_credentials(self) -> ZscalerCredentials:
        return self._credentials

    def write_tools_enabled(self) -> bool:
        return self._write_tools_check.isChecked()

    def write_tools_pattern(self) -> str:
        return self._write_pattern.text().strip()


# ─── Main Dashboard ──────────────────────────────────────────

class DashboardWindow(QMainWindow):
    """The main ZscalerGuardian dashboard window."""

    request_refresh = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ZscalerGuardian")
        self.setMinimumSize(1100, 720)
        self.resize(1280, 820)

        self._dark_mode = True
        self._theme = DARK_THEME
        self._credentials = load_credentials()
        self._mcp: ZscalerMCPClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        self._build_ui()
        self._apply_theme()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    # ── UI Construction ──

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 20, 12, 20)
        sidebar_layout.setSpacing(4)

        # Logo area
        logo = QLabel("ZscalerGuardian")
        logo.setFont(QFont("SF Pro Display", 16, QFont.Weight.Bold))
        logo.setStyleSheet("color: #00D4AA; padding: 8px;")
        sidebar_layout.addWidget(logo)

        version = QLabel("v1.0.0 — Zero Trust Dashboard")
        version.setObjectName("subtitle")
        version.setStyleSheet("padding-left: 8px; font-size: 10px;")
        sidebar_layout.addWidget(version)

        sidebar_layout.addSpacing(20)

        # Nav buttons
        self._nav_buttons: list[QPushButton] = []
        pages = [
            ("Overview", 0),
            ("Policies", 1),
            ("Connectors", 2),
            ("Application Segments", 3),
            ("MCP Tools", 4),
            ("Event Log", 5),
        ]

        self._stack = QStackedWidget()

        for label, idx in pages:
            btn = QPushButton(f"  {label}")
            btn.setObjectName("sidebarButton")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(partial(self._navigate, idx))
            sidebar_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        sidebar_layout.addStretch()

        # Connection status
        self._conn_indicator = QLabel("  Disconnected")
        self._conn_indicator.setObjectName("statusBad")
        self._conn_indicator.setFont(QFont("SF Pro Display", 11))
        sidebar_layout.addWidget(self._conn_indicator)

        # Bottom buttons
        connect_btn = QPushButton("Connect")
        connect_btn.setObjectName("primaryButton")
        connect_btn.clicked.connect(self._on_connect)
        sidebar_layout.addWidget(connect_btn)
        self._connect_btn = connect_btn

        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.show_settings)
        sidebar_layout.addWidget(settings_btn)

        theme_btn = QPushButton("Toggle Theme")
        theme_btn.clicked.connect(self._toggle_theme)
        sidebar_layout.addWidget(theme_btn)

        root.addWidget(sidebar)

        # Pages
        self._stack.addWidget(self._build_overview_page())
        self._stack.addWidget(self._build_policies_page())
        self._stack.addWidget(self._build_connectors_page())
        self._stack.addWidget(self._build_app_segments_page())
        self._stack.addWidget(self._build_tools_page())
        self._stack.addWidget(self._build_log_page())

        root.addWidget(self._stack, 1)
        self._navigate(0)

    def _navigate(self, idx: int):
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._nav_buttons):
            btn.setObjectName("sidebarButtonActive" if i == idx else "sidebarButton")
        self._apply_theme()

    # ── Pages ──

    def _build_overview_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)

        header = QLabel("Security Overview")
        header.setObjectName("sectionTitle")
        layout.addWidget(header)

        # Top row: gauge + cards
        top = QHBoxLayout()

        self._gauge = SecurityScoreGauge()
        self._gauge.setFixedSize(240, 240)
        self._gauge.set_score(0)
        top.addWidget(self._gauge, 0, Qt.AlignmentFlag.AlignCenter)

        cards_col = QVBoxLayout()
        self._overview_cards = StatusCardRow()
        self._overview_cards.add_card("tools", "MCP Tools Available", icon="🔧", accent="#0076CE")
        self._overview_cards.add_card("policies", "Active Policies", icon="🛡", accent="#00D4AA")
        self._overview_cards.add_card("connectors", "Connectors", icon="🔗", accent="#FFB347")
        self._overview_cards.add_card("segments", "App Segments", icon="📦", accent="#00E676")
        cards_col.addWidget(self._overview_cards)

        # Second row of cards
        self._overview_cards2 = StatusCardRow()
        self._overview_cards2.add_card("users", "ZPA Users", icon="👤", accent="#BB86FC")
        self._overview_cards2.add_card("dlp", "DLP Engines", icon="🔍", accent="#FF6B6B")
        self._overview_cards2.add_card("url", "URL Categories", icon="🌐", accent="#64B5F6")
        self._overview_cards2.add_card("idp", "Identity Providers", icon="🔐", accent="#FFD54F")
        cards_col.addWidget(self._overview_cards2)

        top.addLayout(cards_col, 1)
        layout.addLayout(top)

        # Progress bar for data loading
        self._load_progress = QProgressBar()
        self._load_progress.setRange(0, 100)
        self._load_progress.setValue(0)
        self._load_progress.setVisible(False)
        self._load_progress.setFixedHeight(6)
        self._load_progress.setTextVisible(False)
        layout.addWidget(self._load_progress)

        layout.addStretch()
        return page

    def _build_policies_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QLabel("Policy Management")
        header.setObjectName("sectionTitle")
        layout.addWidget(header)

        self._policy_map = PolicyMapWidget()
        layout.addWidget(self._policy_map, 1)
        return page

    def _build_connectors_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QLabel("Connector Health")
        header.setObjectName("sectionTitle")
        layout.addWidget(header)

        self._connectors_container = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setLayout(self._connectors_container)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)

        self._no_connectors_label = QLabel("Connect to MCP server to view connector status.")
        self._no_connectors_label.setObjectName("subtitle")
        self._no_connectors_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._connectors_container.addWidget(self._no_connectors_label)
        self._connectors_container.addStretch()
        return page

    def _build_app_segments_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QLabel("Application Segments")
        header.setObjectName("sectionTitle")
        layout.addWidget(header)

        self._segments_container = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner.setLayout(self._segments_container)
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)

        self._no_segments_label = QLabel("Connect to MCP server to view application segments.")
        self._no_segments_label.setObjectName("subtitle")
        self._no_segments_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._segments_container.addWidget(self._no_segments_label)
        self._segments_container.addStretch()
        return page

    def _build_tools_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QLabel("MCP Tools Explorer")
        header.setObjectName("sectionTitle")
        layout.addWidget(header)

        # Search bar
        search_row = QHBoxLayout()
        self._tool_search = QLineEdit()
        self._tool_search.setPlaceholderText("Search tools...")
        self._tool_search.textChanged.connect(self._filter_tools)
        search_row.addWidget(self._tool_search)

        self._tool_count_label = QLabel("0 tools")
        self._tool_count_label.setObjectName("subtitle")
        search_row.addWidget(self._tool_count_label)
        layout.addLayout(search_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._tools_list_widget = QWidget()
        self._tools_list_layout = QVBoxLayout(self._tools_list_widget)
        self._tools_list_layout.setSpacing(8)
        self._tools_list_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self._tools_list_widget)
        layout.addWidget(scroll, 1)

        return page

    def _build_log_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QLabel("Event Log")
        header.setObjectName("sectionTitle")
        layout.addWidget(header)

        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFont("SF Mono", 11))
        layout.addWidget(self._log_view, 1)

        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self._log_view.clear)
        layout.addWidget(clear_btn, 0, Qt.AlignmentFlag.AlignRight)
        return page

    # ── Theme ──

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        self._theme = DARK_THEME if self._dark_mode else LIGHT_THEME
        self._apply_theme()

    def _apply_theme(self):
        self.setStyleSheet(get_stylesheet(self._theme))

    # ── Settings ──

    def show_settings(self):
        dialog = SettingsDialog(self._credentials, self)
        dialog.setStyleSheet(get_stylesheet(self._theme))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._credentials = dialog.get_credentials()
            self._log("Settings saved to Keychain.")

    # ── Connection ──

    def _on_connect(self):
        if self._mcp and self._mcp.connected:
            self._schedule_async(self._disconnect())
        else:
            if not self._credentials.is_complete():
                self.show_settings()
                self._credentials = load_credentials()
                if not self._credentials.is_complete():
                    return
            self._schedule_async(self._connect())

    async def _connect(self):
        self._log("Connecting to zscaler-mcp server...")
        self._connect_btn.setText("Connecting...")
        self._connect_btn.setEnabled(False)

        self._mcp = ZscalerMCPClient(self._credentials)
        ok = await self._mcp.connect()

        if ok:
            tool_count = len(self._mcp.tools)
            self._conn_indicator.setText(f"  Connected ({tool_count} tools)")
            self._conn_indicator.setObjectName("statusGood")
            self._connect_btn.setText("Disconnect")
            self._log(f"Connected! Discovered {tool_count} MCP tools.")
            self._apply_theme()
            await self._refresh_data()
        else:
            self._conn_indicator.setText("  Connection Failed")
            self._conn_indicator.setObjectName("statusBad")
            self._connect_btn.setText("Retry Connect")
            self._log("Connection failed. Check credentials and that uvx is installed.")
            self._apply_theme()

        self._connect_btn.setEnabled(True)

    async def _disconnect(self):
        if self._mcp:
            await self._mcp.disconnect()
            self._mcp = None
        self._conn_indicator.setText("  Disconnected")
        self._conn_indicator.setObjectName("statusBad")
        self._connect_btn.setText("Connect")
        self._log("Disconnected from MCP server.")
        self._apply_theme()

    # ── Data Refresh ──

    async def refresh(self):
        if self._mcp and self._mcp.connected:
            await self._refresh_data()

    async def _refresh_data(self):
        if not self._mcp or not self._mcp.connected:
            return

        self._load_progress.setVisible(True)
        self._load_progress.setValue(5)

        tools = self._mcp.tools
        self._populate_tools_list(tools)

        # Overview card: tools
        card = self._overview_cards.card("tools")
        if card:
            card.set_value(str(len(tools)))
            # Categorize tools
            zpa = sum(1 for t in tools if "zpa" in t.name.lower())
            zia = sum(1 for t in tools if "zia" in t.name.lower())
            zdx = sum(1 for t in tools if "zdx" in t.name.lower())
            card.set_detail(f"ZPA: {zpa}  ZIA: {zia}  ZDX: {zdx}")

        self._load_progress.setValue(15)

        # Fetch data from various tools
        score = 50  # Base score

        # Try fetching policies
        policies_data = await self._safe_call("list_access_policies")
        policy_count = 0
        policy_nodes = []
        if isinstance(policies_data, list):
            policy_count = len(policies_data)
            for p in policies_data[:20]:
                name = p.get("name", "Unknown") if isinstance(p, dict) else str(p)
                policy_nodes.append(PolicyNode(
                    name=name,
                    category="Access Policies",
                    status="active",
                    count=1,
                ))
            score += min(15, policy_count)
        elif isinstance(policies_data, dict) and "list" in str(policies_data):
            # handle wrapped responses
            items = policies_data.get("list", policies_data.get("items", []))
            if isinstance(items, list):
                policy_count = len(items)

        self._load_progress.setValue(30)

        card = self._overview_cards.card("policies")
        if card:
            card.set_value(str(policy_count))

        # Connectors
        connectors_data = await self._safe_call("list_connectors")
        connector_count = 0
        if isinstance(connectors_data, list):
            connector_count = len(connectors_data)
            self._populate_connectors(connectors_data)
            healthy = sum(1 for c in connectors_data
                          if isinstance(c, dict) and c.get("enabled", True))
            score += min(10, healthy * 2)
        card = self._overview_cards.card("connectors")
        if card:
            card.set_value(str(connector_count))

        self._load_progress.setValue(45)

        # App segments
        segments_data = await self._safe_call("list_application_segments")
        segment_count = 0
        if isinstance(segments_data, list):
            segment_count = len(segments_data)
            self._populate_segments(segments_data)
            score += min(10, segment_count)
            for s in segments_data[:10]:
                name = s.get("name", "Unknown") if isinstance(s, dict) else str(s)
                policy_nodes.append(PolicyNode(
                    name=name,
                    category="Application Segments",
                    status="active",
                ))
        card = self._overview_cards.card("segments")
        if card:
            card.set_value(str(segment_count))

        self._load_progress.setValue(60)

        # DLP engines
        dlp_data = await self._safe_call("list_dlp_engines")
        dlp_count = 0
        if isinstance(dlp_data, list):
            dlp_count = len(dlp_data)
            score += min(10, dlp_count * 2)
        card = self._overview_cards2.card("dlp")
        if card:
            card.set_value(str(dlp_count))

        # URL categories
        url_data = await self._safe_call("list_url_categories")
        url_count = 0
        if isinstance(url_data, list):
            url_count = len(url_data)
            score += min(5, url_count // 5)
            for u in url_data[:5]:
                name = u.get("configuredName", u.get("name", "Category")) if isinstance(u, dict) else str(u)
                policy_nodes.append(PolicyNode(name=name, category="URL Categories", status="active"))
        card = self._overview_cards2.card("url")
        if card:
            card.set_value(str(url_count))

        self._load_progress.setValue(75)

        # IdP
        idp_data = await self._safe_call("list_idps")
        idp_count = 0
        if isinstance(idp_data, list):
            idp_count = len(idp_data)
            score += min(5, idp_count * 5)
        card = self._overview_cards2.card("idp")
        if card:
            card.set_value(str(idp_count))

        # Server groups (as proxy for ZPA users)
        sg_data = await self._safe_call("list_server_groups")
        sg_count = 0
        if isinstance(sg_data, list):
            sg_count = len(sg_data)
        card = self._overview_cards2.card("users")
        if card:
            card.set_value(str(sg_count))
            card.set_detail("Server Groups")

        self._load_progress.setValue(90)

        # Update policy map
        self._policy_map.set_policies(policy_nodes)

        # Finalize score
        score = min(100, max(0, score))
        self._gauge.set_score(score)

        self._load_progress.setValue(100)
        QTimer.singleShot(800, lambda: self._load_progress.setVisible(False))

        self._log(f"Data refresh complete. Score: {score}/100")

    async def _safe_call(self, tool_name: str, args: dict | None = None):
        if not self._mcp:
            return None
        try:
            self._log(f"Calling {tool_name}...")
            return await self._mcp.call_tool(tool_name, args)
        except Exception as e:
            self._log(f"Error calling {tool_name}: {e}")
            return None

    # ── Populate widgets ──

    def _populate_tools_list(self, tools):
        # Clear existing
        while self._tools_list_layout.count():
            item = self._tools_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._all_tool_widgets = []
        for tool in tools:
            card = QFrame()
            card.setObjectName("glassCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 10, 14, 10)
            card_layout.setSpacing(4)

            name_label = QLabel(tool.name)
            name_label.setFont(QFont("SF Mono", 12, QFont.Weight.Bold))
            name_label.setStyleSheet("color: #00D4AA;")
            card_layout.addWidget(name_label)

            if tool.description:
                desc = QLabel(tool.description[:200])
                desc.setObjectName("subtitle")
                desc.setWordWrap(True)
                card_layout.addWidget(desc)

            self._tools_list_layout.addWidget(card)
            self._all_tool_widgets.append((tool.name, tool.description, card))

        self._tools_list_layout.addStretch()
        self._tool_count_label.setText(f"{len(tools)} tools")

    def _filter_tools(self, text: str):
        text = text.lower()
        visible = 0
        for name, desc, widget in getattr(self, '_all_tool_widgets', []):
            match = text in name.lower() or text in (desc or "").lower()
            widget.setVisible(match)
            if match:
                visible += 1
        self._tool_count_label.setText(f"{visible} tools")

    def _populate_connectors(self, data: list):
        # Clear
        while self._connectors_container.count():
            item = self._connectors_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not data:
            lbl = QLabel("No connectors found.")
            lbl.setObjectName("subtitle")
            self._connectors_container.addWidget(lbl)
            return

        for conn in data[:50]:
            if not isinstance(conn, dict):
                continue
            card = QFrame()
            card.setObjectName("glassCard")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)

            name = conn.get("name", "Unknown")
            enabled = conn.get("enabled", False)

            name_lbl = QLabel(name)
            name_lbl.setFont(QFont("SF Pro Display", 13, QFont.Weight.Medium))
            cl.addWidget(name_lbl, 1)

            status_lbl = QLabel("Enabled" if enabled else "Disabled")
            status_lbl.setObjectName("statusGood" if enabled else "statusWarn")
            cl.addWidget(status_lbl)

            self._connectors_container.addWidget(card)

        self._connectors_container.addStretch()

    def _populate_segments(self, data: list):
        while self._segments_container.count():
            item = self._segments_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not data:
            lbl = QLabel("No application segments found.")
            lbl.setObjectName("subtitle")
            self._segments_container.addWidget(lbl)
            return

        for seg in data[:50]:
            if not isinstance(seg, dict):
                continue
            card = QFrame()
            card.setObjectName("glassCard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            cl.setSpacing(4)

            name = seg.get("name", "Unknown Segment")
            name_lbl = QLabel(name)
            name_lbl.setFont(QFont("SF Pro Display", 13, QFont.Weight.Medium))
            cl.addWidget(name_lbl)

            domain_names = seg.get("domainNames", [])
            if domain_names and isinstance(domain_names, list):
                domains_str = ", ".join(domain_names[:5])
                domains_lbl = QLabel(domains_str)
                domains_lbl.setObjectName("subtitle")
                domains_lbl.setWordWrap(True)
                cl.addWidget(domains_lbl)

            enabled = seg.get("enabled", False)
            status_lbl = QLabel("Active" if enabled else "Inactive")
            status_lbl.setObjectName("statusGood" if enabled else "statusWarn")
            cl.addWidget(status_lbl)

            self._segments_container.addWidget(card)

        self._segments_container.addStretch()

    # ── Helpers ──

    def _log(self, message: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        if hasattr(self, '_log_view'):
            self._log_view.append(f"[{ts}] {message}")
        logger.info(message)

    def _schedule_async(self, coro):
        if self._loop:
            asyncio.ensure_future(coro, loop=self._loop)
