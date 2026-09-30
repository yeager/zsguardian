"""Main dashboard window for ZSGuardian."""

import asyncio
import logging
from functools import partial

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QColor
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
    read_keychain,
    write_keychain,
    delete_keychain,
)
from mcp_client import ZscalerMCPClient
from styles.theme import DARK_THEME, LIGHT_THEME, get_stylesheet
from widgets.score_gauge import SecurityScoreGauge
from widgets.status_cards import StatusCard, StatusCardRow
from widgets.policy_map import PolicyMapWidget, PolicyNode
from widgets.findings import FindingsPanel, Finding

logger = logging.getLogger(__name__)


# ─── Settings Dialog ──────────────────────────────────────────

class SettingsDialog(QDialog):
    """Credentials & preferences settings dialog."""

    def __init__(self, credentials: ZscalerCredentials, write_tools: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("ZSGuardian Settings")
        self.setMinimumSize(520, 480)
        self._credentials = ZscalerCredentials(**vars(credentials))
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
            label.setFont(QFont(".AppleSystemUIFont", 12, QFont.Weight.Medium))
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

        self._write_tools_check = QCheckBox("Enable write tools (explicit allowlist required)")
        self._write_tools_check.setChecked(bool(write_tools))
        layout.addWidget(self._write_tools_check)

        self._write_pattern = QLineEdit()
        self._write_pattern.setPlaceholderText("Write tools pattern (e.g., 'update_*')")
        self._write_pattern.setText(write_tools)
        self._write_pattern.setEnabled(bool(write_tools))
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
        patterns = [part.strip() for part in self._write_pattern.text().split(",")]
        if self._write_tools_check.isChecked() and (
            not any(patterns) or any(not pattern for pattern in patterns)
        ):
            QMessageBox.warning(self, "Write tools", "Enter an explicit write-tool allowlist, or leave write tools disabled.")
            return
        for field_key, line in self._fields.items():
            setattr(self._credentials, field_key, line.text().strip())

        pattern = ",".join(patterns) if self.write_tools_enabled() else ""
        prefs_saved = (
            write_keychain("zsguardian-write-tools-pattern", pattern)
            if pattern else delete_keychain("zsguardian-write-tools-pattern")
        )
        if save_credentials(self._credentials) and prefs_saved:
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
    """The main ZSGuardian dashboard window."""

    request_refresh = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ZSGuardian")
        self.setMinimumSize(1100, 720)
        self.resize(1360, 880)

        self._dark_mode = True
        self._theme = DARK_THEME
        self._credentials = load_credentials()
        self._mcp: ZscalerMCPClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        # Store raw data for cross-referencing
        self._raw_data: dict = {}
        self._data_errors: dict[str, str] = {}
        self._write_tools = read_keychain("zsguardian-write-tools-pattern") or ""

        self._build_ui()
        self._apply_theme()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def shutdown(self):
        if self._mcp:
            self._mcp.terminate_now()

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
        logo = QLabel("ZSGuardian")
        logo.setFont(QFont(".AppleSystemUIFont", 16, QFont.Weight.Bold))
        logo.setStyleSheet("color: #00D4AA; padding: 8px;")
        sidebar_layout.addWidget(logo)

        version = QLabel("v2.0.0 — Zero Trust Dashboard")
        version.setObjectName("subtitle")
        version.setStyleSheet("padding-left: 8px; font-size: 10px;")
        sidebar_layout.addWidget(version)

        sidebar_layout.addSpacing(20)

        # Nav buttons
        self._nav_buttons: list[QPushButton] = []
        pages = [
            ("Overview", 0),
            ("Threats & Insights", 1),
            ("Policies", 2),
            ("Findings & Anomalies", 3),
            ("Connectors", 4),
            ("Application Segments", 5),
            ("MCP Tools", 6),
            ("Event Log", 7),
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
        self._conn_indicator.setFont(QFont(".AppleSystemUIFont", 11))
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
        self._stack.addWidget(self._build_overview_page())        # 0
        self._stack.addWidget(self._build_threats_page())          # 1
        self._stack.addWidget(self._build_policies_page())         # 2
        self._stack.addWidget(self._build_findings_page())         # 3
        self._stack.addWidget(self._build_connectors_page())       # 4
        self._stack.addWidget(self._build_app_segments_page())     # 5
        self._stack.addWidget(self._build_tools_page())            # 6
        self._stack.addWidget(self._build_log_page())              # 7

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

        gauge_col = QVBoxLayout()
        self._gauge = SecurityScoreGauge()
        self._gauge.setFixedSize(240, 240)
        self._gauge.set_score(0)
        gauge_col.addWidget(self._gauge, 0, Qt.AlignmentFlag.AlignCenter)

        # Score breakdown panel
        self._score_breakdown = QLabel("")
        self._score_breakdown.setObjectName("subtitle")
        self._score_breakdown.setWordWrap(True)
        self._score_breakdown.setFont(QFont(".AppleSystemUIFont", 10))
        self._score_breakdown.setFixedWidth(240)
        gauge_col.addWidget(self._score_breakdown)

        top.addLayout(gauge_col)

        cards_col = QVBoxLayout()
        self._overview_cards = StatusCardRow()
        self._overview_cards.add_card("tools", "MCP Tools Available", icon="🔧", accent="#0076CE")
        self._overview_cards.add_card("policies", "Active Policies", icon="🛡", accent="#00D4AA")
        self._overview_cards.add_card("connectors", "Connectors", icon="🔗", accent="#FFB347")
        self._overview_cards.add_card("segments", "App Segments", icon="📦", accent="#00E676")
        cards_col.addWidget(self._overview_cards)

        # Second row of cards
        self._overview_cards2 = StatusCardRow()
        self._overview_cards2.add_card("firewall", "Firewall Rules", icon="🔥", accent="#FF6B6B")
        self._overview_cards2.add_card("dlp", "DLP Rules", icon="🔍", accent="#BB86FC")
        self._overview_cards2.add_card("ssl", "SSL Inspection", icon="🔐", accent="#64B5F6")
        self._overview_cards2.add_card("url", "URL Filtering", icon="🌐", accent="#FFD54F")
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

        # Recommendations
        self._recommendations_label = QLabel("")
        self._recommendations_label.setWordWrap(True)
        self._recommendations_label.setFont(QFont(".AppleSystemUIFont", 11))
        layout.addWidget(self._recommendations_label)

        layout.addStretch()
        return page

    def _build_threats_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        header = QLabel("Threats & Insights")
        header.setObjectName("sectionTitle")
        layout.addWidget(header)

        # Threat summary cards
        self._threat_cards = StatusCardRow()
        self._threat_cards.add_card("incidents", "Cyber Incidents", icon="🚨", accent="#FF6B6B")
        self._threat_cards.add_card("threats", "Threat Categories", icon="☠️", accent="#FFB347")
        self._threat_cards.add_card("shadow_it", "Shadow IT Apps", icon="👻", accent="#BB86FC")
        self._threat_cards.add_card("atp", "Malicious URLs", icon="🔗", accent="#FF4444")
        layout.addWidget(self._threat_cards)

        # Scrollable detail area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._threats_container = QWidget()
        self._threats_layout = QVBoxLayout(self._threats_container)
        self._threats_layout.setSpacing(8)
        self._threats_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self._threats_container)
        layout.addWidget(scroll, 1)

        self._threats_placeholder = QLabel("Connect to load threat intelligence data from ZInsights.")
        self._threats_placeholder.setObjectName("subtitle")
        self._threats_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._threats_layout.addWidget(self._threats_placeholder)
        self._threats_layout.addStretch()

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

    def _build_findings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        self._findings_panel = FindingsPanel()
        layout.addWidget(self._findings_panel, 1)
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
        self._log_view.setFont(QFont("Menlo", 11))
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
        dialog = SettingsDialog(self._credentials, self._write_tools, self)
        dialog.setStyleSheet(get_stylesheet(self._theme))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._credentials = dialog.get_credentials()
            self._write_tools = dialog.write_tools_pattern() if dialog.write_tools_enabled() else ""
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

        self._mcp = ZscalerMCPClient(self._credentials, write_tools=self._write_tools)
        try:
            ok = await self._mcp.connect()
        except Exception as e:
            self._log(f"MCP startup failed: {e}")
            await self._mcp.disconnect()
            self._mcp = None
            ok = False

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
        self._data_errors = {}

        tools = self._mcp.tools
        self._populate_tools_list(tools)

        # Overview card: tools
        card = self._overview_cards.card("tools")
        if card:
            card.set_value(str(len(tools)))
            zpa = sum(1 for t in tools if "zpa" in t.name.lower())
            zia = sum(1 for t in tools if "zia" in t.name.lower())
            zdx = sum(1 for t in tools if "zdx" in t.name.lower())
            card.set_detail(f"ZPA: {zpa}  ZIA: {zia}  ZDX: {zdx}")

        self._load_progress.setValue(10)

        # ── Phase 1: Core policy/config data (parallel) ──
        self._log("Fetching core policy and configuration data...")
        results = await asyncio.gather(
            self._safe_call("zpa_list_access_policy_rules"),
            self._safe_call("zpa_list_forwarding_policy_rules"),
            self._safe_call("zpa_list_app_connector_groups"),
            self._safe_call("zpa_list_application_segments"),
            self._safe_call("zpa_list_segment_groups"),
            self._safe_call("zpa_list_server_groups"),
            self._safe_call("zia_list_cloud_firewall_rules"),
            self._safe_call("zia_list_web_dlp_rules"),
            self._safe_call("zia_list_ssl_inspection_rules"),
            self._safe_call("zia_list_url_filtering_rules"),
            return_exceptions=True,
        )

        (access_policies, forwarding_rules, connector_groups, segments,
         segment_groups, server_groups, firewall_rules, dlp_rules,
         ssl_rules, url_rules) = [
            r if not isinstance(r, Exception) else None for r in results
        ]

        self._load_progress.setValue(40)

        # Store raw data for anomaly detection
        self._raw_data = {
            "access_policies": access_policies,
            "forwarding_rules": forwarding_rules,
            "connector_groups": connector_groups,
            "segments": segments,
            "segment_groups": segment_groups,
            "server_groups": server_groups,
            "firewall_rules": firewall_rules,
            "dlp_rules": dlp_rules,
            "ssl_rules": ssl_rules,
            "url_rules": url_rules,
        }
        core_tool_keys = {
            "zpa_list_access_policy_rules": "access_policies",
            "zpa_list_forwarding_policy_rules": "forwarding_rules",
            "zpa_list_app_connector_groups": "connector_groups",
            "zpa_list_application_segments": "segments",
            "zpa_list_segment_groups": "segment_groups",
            "zpa_list_server_groups": "server_groups",
            "zia_list_cloud_firewall_rules": "firewall_rules",
            "zia_list_web_dlp_rules": "dlp_rules",
            "zia_list_ssl_inspection_rules": "ssl_rules",
            "zia_list_url_filtering_rules": "url_rules",
        }
        self._mark_missing_responses(core_tool_keys)

        # ── Phase 2: Threat intelligence (parallel) ──
        self._log("Fetching threat intelligence from ZInsights...")
        threat_results = await asyncio.gather(
            self._safe_call("zinsights_get_cyber_incidents"),
            self._safe_call("zinsights_get_threat_class"),
            self._safe_call("zinsights_get_shadow_it_apps"),
            self._safe_call("zia_list_atp_malicious_urls"),
            self._safe_call("zeasm_list_findings"),
            self._safe_call("zeasm_list_lookalike_domains"),
            self._safe_call("zia_list_auth_exempt_urls"),
            return_exceptions=True,
        )

        (incidents, threat_classes, shadow_it, atp_urls,
         zeasm_findings, lookalike_domains, auth_exempt) = [
            r if not isinstance(r, Exception) else None for r in threat_results
        ]

        self._raw_data.update({
            "incidents": incidents,
            "threat_classes": threat_classes,
            "shadow_it": shadow_it,
            "atp_urls": atp_urls,
            "zeasm_findings": zeasm_findings,
            "lookalike_domains": lookalike_domains,
            "auth_exempt": auth_exempt,
        })
        self._mark_missing_responses({
            "zinsights_get_cyber_incidents": "incidents",
            "zinsights_get_threat_class": "threat_classes",
            "zinsights_get_shadow_it_apps": "shadow_it",
            "zia_list_atp_malicious_urls": "atp_urls",
            "zeasm_list_findings": "zeasm_findings",
            "zeasm_list_lookalike_domains": "lookalike_domains",
            "zia_list_auth_exempt_urls": "auth_exempt",
        })

        self._load_progress.setValue(70)

        # ── Update UI ──
        self._update_overview_cards()
        self._update_policy_flow()
        self._populate_connectors_from_groups()
        self._populate_segments_list()
        self._update_threats_page()
        self._detect_anomalies()
        self._compute_smart_score()

        self._load_progress.setValue(100)
        QTimer.singleShot(800, lambda: self._load_progress.setVisible(False))
        if self._data_errors:
            self._log(f"Data refresh incomplete: {len(self._data_errors)} MCP calls failed.")
        else:
            self._log("Data refresh complete.")

    def _mark_missing_responses(self, tool_keys: dict[str, str]):
        """Keep failed calls distinct from successful empty API responses."""
        for tool_name, data_key in tool_keys.items():
            if self._raw_data.get(data_key) is None:
                self._data_errors.setdefault(tool_name, "No usable response")

    # ── Update helpers ──

    def _safe_list(self, data) -> list:
        """Extract a list from various API response formats."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("list", "items", "rules", "findings", "apps", "domains",
                        "urls", "connectors", "groups", "segments", "policies"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            # Some endpoints wrap in totalPages/list
            if "totalPages" in data and "list" in data:
                return data["list"] if isinstance(data["list"], list) else []
        return []

    def _update_overview_cards(self):
        d = self._raw_data

        # Policies
        policies = self._safe_list(d.get("access_policies"))
        card = self._overview_cards.card("policies")
        if card:
            card.set_value("—" if d.get("access_policies") is None else str(len(policies)))
            active = sum(1 for p in policies if isinstance(p, dict) and
                         p.get("action", "").upper() == "ALLOW")
            card.set_detail("Data unavailable" if d.get("access_policies") is None else f"{active} allow, {len(policies) - active} other")

        # Connectors
        groups = self._safe_list(d.get("connector_groups"))
        total_connectors = 0
        for g in groups:
            if isinstance(g, dict):
                conns = g.get("connectors", [])
                if isinstance(conns, list):
                    total_connectors += len(conns)
        card = self._overview_cards.card("connectors")
        if card:
            card.set_value("—" if d.get("connector_groups") is None else str(total_connectors))
            card.set_detail("Data unavailable" if d.get("connector_groups") is None else f"in {len(groups)} groups")

        # Segments
        segs = self._safe_list(d.get("segments"))
        card = self._overview_cards.card("segments")
        if card:
            card.set_value("—" if d.get("segments") is None else str(len(segs)))
            enabled = sum(1 for s in segs if isinstance(s, dict) and s.get("enabled"))
            card.set_detail("Data unavailable" if d.get("segments") is None else f"{enabled} enabled")

        # Firewall
        fw = self._safe_list(d.get("firewall_rules"))
        card = self._overview_cards2.card("firewall")
        if card:
            card.set_value("—" if d.get("firewall_rules") is None else str(len(fw)))
            active = sum(1 for r in fw if isinstance(r, dict) and r.get("state") == "ENABLED")
            card.set_detail("Data unavailable" if d.get("firewall_rules") is None else f"{active} active")

        # DLP
        dlp = self._safe_list(d.get("dlp_rules"))
        card = self._overview_cards2.card("dlp")
        if card:
            card.set_value("—" if d.get("dlp_rules") is None else str(len(dlp)))
            card.set_detail("Data unavailable" if d.get("dlp_rules") is None else "")

        # SSL
        ssl = self._safe_list(d.get("ssl_rules"))
        card = self._overview_cards2.card("ssl")
        if card:
            card.set_value("—" if d.get("ssl_rules") is None else str(len(ssl)))
            card.set_detail("Data unavailable" if d.get("ssl_rules") is None else "")

        # URL filtering
        url = self._safe_list(d.get("url_rules"))
        card = self._overview_cards2.card("url")
        if card:
            card.set_value("—" if d.get("url_rules") is None else str(len(url)))
            card.set_detail("Data unavailable" if d.get("url_rules") is None else "")

    def _update_policy_flow(self):
        """Build real policy flow: Access Policies → Segment Groups → App Segments → Server Groups → Connectors."""
        d = self._raw_data
        columns: dict[str, list[PolicyNode]] = {}
        connections: list[tuple[str, str, str, str]] = []
        anomalies: list[str] = []

        # Access Policies
        policies = self._safe_list(d.get("access_policies"))
        policy_nodes = []
        policy_segment_map: dict[str, list[str]] = {}
        for p in policies:
            if not isinstance(p, dict):
                continue
            name = p.get("name", "Unknown Policy")
            action = p.get("action", "")
            status = "active" if action.upper() == "ALLOW" else "warning" if action else "disabled"
            policy_nodes.append(PolicyNode(name=name, category="Access Policies",
                                           status=status, detail=action))
            # Extract referenced app segments / segment groups
            conditions = p.get("conditions", [])
            if isinstance(conditions, list):
                for cond in conditions:
                    if isinstance(cond, dict):
                        operands = cond.get("operands", [])
                        if isinstance(operands, list):
                            for op in operands:
                                if isinstance(op, dict) and "APP_GROUP" in str(op.get("objectType", "")):
                                    seg_name = op.get("name", "")
                                    if seg_name:
                                        policy_segment_map.setdefault(name, []).append(seg_name)
        if policy_nodes:
            columns["Access Policies"] = policy_nodes

        # Segment Groups
        seg_groups = self._safe_list(d.get("segment_groups"))
        sg_nodes = []
        sg_app_map: dict[str, list[str]] = {}
        for sg in seg_groups:
            if not isinstance(sg, dict):
                continue
            name = sg.get("name", "Unknown")
            enabled = sg.get("enabled", True)
            apps = sg.get("applications", [])
            app_names = []
            if isinstance(apps, list):
                for a in apps:
                    if isinstance(a, dict):
                        app_names.append(a.get("name", ""))
            sg_nodes.append(PolicyNode(name=name, category="Segment Groups",
                                        status="active" if enabled else "disabled",
                                        count=len(app_names)))
            sg_app_map[name] = app_names
            # Connect policies to segment groups
            for pol_name, seg_names in policy_segment_map.items():
                if name in seg_names:
                    connections.append(("Access Policies", pol_name, "Segment Groups", name))
        if sg_nodes:
            columns["Segment Groups"] = sg_nodes

        # Application Segments
        segments = self._safe_list(d.get("segments"))
        seg_nodes = []
        seg_server_map: dict[str, list[str]] = {}
        segments_with_policies = set()
        for s in segments:
            if not isinstance(s, dict):
                continue
            name = s.get("name", "Unknown")
            enabled = s.get("enabled", False)
            seg_nodes.append(PolicyNode(name=name, category="App Segments",
                                         status="active" if enabled else "disabled"))
            # Check server groups
            sgs = s.get("serverGroups", [])
            if isinstance(sgs, list):
                for sg_ref in sgs:
                    if isinstance(sg_ref, dict):
                        sg_name = sg_ref.get("name", "")
                        if sg_name:
                            seg_server_map.setdefault(name, []).append(sg_name)
            # Track which segments are referenced by segment groups
            for sg_name, app_names in sg_app_map.items():
                if name in app_names:
                    connections.append(("Segment Groups", sg_name, "App Segments", name))
                    segments_with_policies.add(name)
        if seg_nodes:
            columns["App Segments"] = seg_nodes

        # Detect segments without policies
        for s in seg_nodes:
            if s.name not in segments_with_policies and s.status == "active":
                anomalies.append(f"Segment '{s.name}' has no associated policy")
                s.status = "warning"

        # Server Groups
        srv_groups = self._safe_list(d.get("server_groups"))
        srv_nodes = []
        for sg in srv_groups:
            if not isinstance(sg, dict):
                continue
            name = sg.get("name", "Unknown")
            enabled = sg.get("enabled", True)
            srv_nodes.append(PolicyNode(name=name, category="Server Groups",
                                         status="active" if enabled else "disabled"))
            # Connect segments to server groups
            for seg_name, sg_names in seg_server_map.items():
                if name in sg_names:
                    connections.append(("App Segments", seg_name, "Server Groups", name))
        if srv_nodes:
            columns["Server Groups"] = srv_nodes

        # Connectors
        conn_groups = self._safe_list(d.get("connector_groups"))
        conn_nodes = []
        for cg in conn_groups:
            if not isinstance(cg, dict):
                continue
            name = cg.get("name", "Unknown")
            connectors = cg.get("connectors", [])
            enabled_count = 0
            if isinstance(connectors, list):
                enabled_count = sum(1 for c in connectors if isinstance(c, dict) and c.get("enabled"))
            total = len(connectors) if isinstance(connectors, list) else 0
            status = "active" if enabled_count == total and total > 0 else "warning" if enabled_count > 0 else "disabled"
            conn_nodes.append(PolicyNode(name=name, category="Connectors",
                                          status=status, count=total,
                                          detail=f"{enabled_count}/{total} enabled"))
        if conn_nodes:
            columns["Connectors"] = conn_nodes

        # Forwarding rules
        fwd = self._safe_list(d.get("forwarding_rules"))
        if fwd and not policy_nodes:
            fwd_nodes = []
            for r in fwd:
                if isinstance(r, dict):
                    name = r.get("name", "Unknown")
                    fwd_nodes.append(PolicyNode(name=name, category="Forwarding Rules", status="active"))
            if fwd_nodes:
                columns["Forwarding Rules"] = fwd_nodes

        self._policy_map.set_flow_data(columns, connections, anomalies)

    def _populate_connectors_from_groups(self):
        """Populate connectors page from connector groups data."""
        groups = self._safe_list(self._raw_data.get("connector_groups"))

        while self._connectors_container.count():
            item = self._connectors_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not groups:
            lbl = QLabel("Connector data unavailable." if self._raw_data.get("connector_groups") is None else "No connector groups found.")
            lbl.setObjectName("subtitle")
            self._connectors_container.addWidget(lbl)
            self._connectors_container.addStretch()
            return

        for group in groups:
            if not isinstance(group, dict):
                continue

            # Group header
            group_card = QFrame()
            group_card.setObjectName("glassCard")
            gl = QVBoxLayout(group_card)
            gl.setContentsMargins(16, 12, 16, 12)
            gl.setSpacing(4)

            group_name = group.get("name", "Unknown Group")
            name_lbl = QLabel(group_name)
            name_lbl.setFont(QFont(".AppleSystemUIFont", 14, QFont.Weight.Bold))
            gl.addWidget(name_lbl)

            connectors = group.get("connectors", [])
            if isinstance(connectors, list) and connectors:
                for conn in connectors:
                    if not isinstance(conn, dict):
                        continue
                    row = QHBoxLayout()
                    cname = conn.get("name", "Unknown")
                    cl = QLabel(f"  {cname}")
                    cl.setFont(QFont(".AppleSystemUIFont", 12))
                    row.addWidget(cl, 1)

                    enabled = conn.get("enabled", False)
                    status_lbl = QLabel("Enabled" if enabled else "Disabled")
                    status_lbl.setObjectName("statusGood" if enabled else "statusWarn")
                    row.addWidget(status_lbl)
                    gl.addLayout(row)
            else:
                no_conn = QLabel("  No connectors in this group")
                no_conn.setObjectName("subtitle")
                gl.addWidget(no_conn)

            self._connectors_container.addWidget(group_card)

        self._connectors_container.addStretch()

    def _populate_segments_list(self):
        segments = self._safe_list(self._raw_data.get("segments"))

        while self._segments_container.count():
            item = self._segments_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not segments:
            lbl = QLabel("Application segment data unavailable." if self._raw_data.get("segments") is None else "No application segments found.")
            lbl.setObjectName("subtitle")
            self._segments_container.addWidget(lbl)
            self._segments_container.addStretch()
            return

        for seg in segments[:50]:
            if not isinstance(seg, dict):
                continue
            card = QFrame()
            card.setObjectName("glassCard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            cl.setSpacing(4)

            name = seg.get("name", "Unknown Segment")
            name_lbl = QLabel(name)
            name_lbl.setFont(QFont(".AppleSystemUIFont", 13, QFont.Weight.Medium))
            cl.addWidget(name_lbl)

            domain_names = seg.get("domainNames", [])
            if domain_names and isinstance(domain_names, list):
                domains_str = ", ".join(domain_names[:5])
                if len(domain_names) > 5:
                    domains_str += f" (+{len(domain_names) - 5} more)"
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

    def _update_threats_page(self):
        """Populate threats & insights page."""
        d = self._raw_data

        # Update summary cards
        incidents = self._safe_list(d.get("incidents"))
        card = self._threat_cards.card("incidents")
        if card:
            card.set_value("—" if d.get("incidents") is None else str(len(incidents)))

        threats = self._safe_list(d.get("threat_classes"))
        card = self._threat_cards.card("threats")
        if card:
            card.set_value("—" if d.get("threat_classes") is None else str(len(threats)))

        shadow = self._safe_list(d.get("shadow_it"))
        card = self._threat_cards.card("shadow_it")
        if card:
            card.set_value("—" if d.get("shadow_it") is None else str(len(shadow)))

        atp = self._safe_list(d.get("atp_urls"))
        card = self._threat_cards.card("atp")
        if card:
            card.set_value("—" if d.get("atp_urls") is None else str(len(atp)))

        # Populate detail area
        while self._threats_layout.count():
            item = self._threats_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        has_data = False

        # Cyber incidents
        if incidents:
            has_data = True
            section = QLabel("Recent Cyber Incidents")
            section.setObjectName("cardTitle")
            self._threats_layout.addWidget(section)

            for inc in incidents[:20]:
                if not isinstance(inc, dict):
                    continue
                card = QFrame()
                card.setObjectName("glassCard")
                cl = QHBoxLayout(card)
                cl.setContentsMargins(14, 8, 14, 8)

                severity = inc.get("severity", inc.get("riskScore", ""))
                sev_lbl = QLabel(str(severity))
                sev_lbl.setStyleSheet("color: #FF6B6B; font-weight: 700;")
                sev_lbl.setFixedWidth(50)
                cl.addWidget(sev_lbl)

                name = inc.get("name", inc.get("category", inc.get("type", "Unknown")))
                n_lbl = QLabel(str(name))
                n_lbl.setFont(QFont(".AppleSystemUIFont", 11))
                n_lbl.setWordWrap(True)
                cl.addWidget(n_lbl, 1)

                count = inc.get("count", inc.get("totalCount", ""))
                if count:
                    c_lbl = QLabel(str(count))
                    c_lbl.setStyleSheet("color: #FFB347; font-weight: 600;")
                    cl.addWidget(c_lbl)

                self._threats_layout.addWidget(card)

        # Threat categories
        if threats:
            has_data = True
            section = QLabel("Threat Categories")
            section.setObjectName("cardTitle")
            self._threats_layout.addWidget(section)

            for t in threats[:15]:
                if not isinstance(t, dict):
                    continue
                card = QFrame()
                card.setObjectName("glassCard")
                cl = QHBoxLayout(card)
                cl.setContentsMargins(14, 8, 14, 8)

                name = t.get("name", t.get("threatClass", str(t)))
                n_lbl = QLabel(str(name))
                n_lbl.setFont(QFont(".AppleSystemUIFont", 11))
                cl.addWidget(n_lbl, 1)

                count = t.get("count", t.get("totalCount", ""))
                if count:
                    c_lbl = QLabel(str(count))
                    c_lbl.setStyleSheet("color: #FFB347; font-weight: 600;")
                    cl.addWidget(c_lbl)

                self._threats_layout.addWidget(card)

        # Shadow IT
        if shadow:
            has_data = True
            section = QLabel("Shadow IT Applications Detected")
            section.setObjectName("cardTitle")
            self._threats_layout.addWidget(section)

            for app in shadow[:15]:
                if not isinstance(app, dict):
                    continue
                card = QFrame()
                card.setObjectName("glassCard")
                cl = QHBoxLayout(card)
                cl.setContentsMargins(14, 8, 14, 8)

                name = app.get("name", app.get("appName", str(app)))
                n_lbl = QLabel(str(name))
                n_lbl.setFont(QFont(".AppleSystemUIFont", 11))
                cl.addWidget(n_lbl, 1)

                risk = app.get("riskScore", app.get("risk", ""))
                if risk:
                    r_lbl = QLabel(f"Risk: {risk}")
                    r_lbl.setStyleSheet("color: #BB86FC; font-weight: 600;")
                    cl.addWidget(r_lbl)

                self._threats_layout.addWidget(card)

        # ATP Malicious URLs
        if atp:
            has_data = True
            section = QLabel("ATP Malicious URLs")
            section.setObjectName("cardTitle")
            self._threats_layout.addWidget(section)

            for url in atp[:10]:
                if isinstance(url, dict):
                    url_str = url.get("url", str(url))
                else:
                    url_str = str(url)
                card = QFrame()
                card.setObjectName("glassCard")
                cl = QHBoxLayout(card)
                cl.setContentsMargins(14, 8, 14, 8)
                lbl = QLabel(str(url_str))
                lbl.setFont(QFont("Menlo", 10))
                lbl.setStyleSheet("color: #FF4444;")
                lbl.setWordWrap(True)
                cl.addWidget(lbl)
                self._threats_layout.addWidget(card)

        if not has_data:
            threat_keys = ("incidents", "threat_classes", "shadow_it", "atp_urls",
                           "zeasm_findings", "lookalike_domains")
            message = (
                "Threat data is incomplete because one or more MCP requests failed. Retry the refresh."
                if any(d.get(key) is None for key in threat_keys)
                else "No threat data available. This may be normal if ZInsights tools returned empty results."
            )
            lbl = QLabel(message)
            lbl.setObjectName("subtitle")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setWordWrap(True)
            self._threats_layout.addWidget(lbl)

        self._threats_layout.addStretch()

    def _detect_anomalies(self):
        """Run anomaly detection across all collected data."""
        d = self._raw_data
        findings: list[Finding] = []

        # 1. Disabled connectors
        groups = self._safe_list(d.get("connector_groups"))
        for g in groups:
            if not isinstance(g, dict):
                continue
            connectors = g.get("connectors", [])
            if isinstance(connectors, list):
                for c in connectors:
                    if isinstance(c, dict) and not c.get("enabled", True):
                        findings.append(Finding(
                            severity="high",
                            title=f"Connector disabled: {c.get('name', 'Unknown')}",
                            detail=f"In group '{g.get('name', '?')}'. Disabled connectors cannot serve traffic.",
                            source="Connector Health",
                        ))

        # 2. Segments without server groups (no backend)
        segments = self._safe_list(d.get("segments"))
        for s in segments if d.get("segments") is not None else []:
            if not isinstance(s, dict) or not s.get("enabled"):
                continue
            sgs = s.get("serverGroups", [])
            if not sgs or (isinstance(sgs, list) and len(sgs) == 0):
                findings.append(Finding(
                    severity="medium",
                    title=f"Segment has no server groups: {s.get('name', '?')}",
                    detail="Active segment without backend servers may not route traffic.",
                    source="Policy Audit",
                ))

        # 3. Firewall rules without DLP
        fw_rules = self._safe_list(d.get("firewall_rules"))
        dlp_rules = self._safe_list(d.get("dlp_rules"))
        if d.get("firewall_rules") is not None and d.get("dlp_rules") is not None and fw_rules and not dlp_rules:
            findings.append(Finding(
                severity="medium",
                title="Firewall rules exist but no DLP rules configured",
                detail="Consider adding DLP rules to prevent data exfiltration.",
                source="Policy Audit",
            ))

        # 4. No SSL inspection
        ssl_rules = self._safe_list(d.get("ssl_rules"))
        if d.get("ssl_rules") is not None and not ssl_rules:
            findings.append(Finding(
                severity="high",
                title="No SSL inspection rules configured",
                detail="Without SSL inspection, encrypted traffic cannot be analyzed for threats.",
                source="Policy Audit",
            ))

        # 5. Auth exempt URLs
        auth_exempt = self._safe_list(d.get("auth_exempt"))
        if d.get("auth_exempt") is not None and auth_exempt:
            findings.append(Finding(
                severity="medium",
                title=f"{len(auth_exempt)} authentication-exempt URLs configured",
                detail="Auth-exempt URLs bypass authentication. Review if all are still needed.",
                source="ZIA Config",
            ))
            for url_entry in auth_exempt[:5]:
                url_str = url_entry.get("url", str(url_entry)) if isinstance(url_entry, dict) else str(url_entry)
                findings.append(Finding(
                    severity="low",
                    title=f"Auth-exempt URL: {url_str}",
                    detail="",
                    source="ZIA Config",
                ))

        # 6. ATP malicious URLs found
        atp = self._safe_list(d.get("atp_urls"))
        if d.get("atp_urls") is not None and atp:
            findings.append(Finding(
                severity="high",
                title=f"{len(atp)} malicious URLs detected by ATP",
                detail="These URLs have been flagged as malicious. Ensure they are blocked.",
                source="ZIA ATP",
            ))

        # 7. ZEASM findings
        zeasm = self._safe_list(d.get("zeasm_findings"))
        for f in zeasm[:20] if d.get("zeasm_findings") is not None else []:
            if not isinstance(f, dict):
                continue
            sev = str(f.get("severity", f.get("risk", "medium"))).lower()
            if sev not in ("critical", "high", "medium", "low", "info"):
                sev = "medium"
            findings.append(Finding(
                severity=sev,
                title=f.get("title", f.get("name", f.get("finding", "ZEASM Finding"))),
                detail=f.get("description", f.get("detail", "")),
                source="ZEASM",
            ))

        # 8. Lookalike domains
        lookalikes = self._safe_list(d.get("lookalike_domains"))
        if d.get("lookalike_domains") is not None and lookalikes:
            findings.append(Finding(
                severity="high",
                title=f"{len(lookalikes)} lookalike domains detected",
                detail="These domains may be used for phishing attacks targeting your organization.",
                source="ZEASM",
            ))
            for dom in lookalikes[:5]:
                dname = dom.get("domain", str(dom)) if isinstance(dom, dict) else str(dom)
                findings.append(Finding(
                    severity="medium",
                    title=f"Lookalike domain: {dname}",
                    detail="",
                    source="ZEASM",
                ))

        # 9. Shadow IT apps
        shadow = self._safe_list(d.get("shadow_it"))
        if d.get("shadow_it") is not None and shadow:
            high_risk = [a for a in shadow if isinstance(a, dict) and
                         (a.get("riskScore", 0) or 0) >= 7]
            if high_risk:
                findings.append(Finding(
                    severity="high",
                    title=f"{len(high_risk)} high-risk Shadow IT applications detected",
                    detail="These unsanctioned apps pose security risks.",
                    source="ZInsights",
                ))

        # 10. Segment groups without policies
        seg_groups = self._safe_list(d.get("segment_groups"))
        policies = self._safe_list(d.get("access_policies"))
        if d.get("segment_groups") is not None and d.get("access_policies") is not None and seg_groups and not policies:
            findings.append(Finding(
                severity="high",
                title="Segment groups exist but no access policies found",
                detail="Without access policies, segment groups may not be properly protected.",
                source="Policy Audit",
            ))

        self._findings_panel.set_findings(findings, incomplete=bool(self._data_errors))
        self._log(f"Anomaly detection complete: {len(findings)} findings")

    def _compute_smart_score(self):
        """Compute security posture score with detailed breakdown."""
        d = self._raw_data
        score = 0
        breakdown = []
        recommendations = []

        score_inputs = ("ssl_rules", "dlp_rules", "url_rules", "firewall_rules",
                        "access_policies", "connector_groups", "atp_urls", "segments")
        unavailable = [key for key in score_inputs if d.get(key) is None]
        if unavailable:
            self._gauge.set_available(False)
            self._score_breakdown.setText("Score unavailable: data could not be loaded for " + ", ".join(unavailable))
            self._recommendations_label.setText("Some MCP requests failed. Retry the refresh before relying on a security score.")
            return
        self._gauge.set_available(True)

        # SSL Inspection (+10)
        ssl = self._safe_list(d.get("ssl_rules"))
        if ssl:
            score += 10
            breakdown.append(f"+10  SSL inspection ({len(ssl)} rules)")
        else:
            breakdown.append("+0   No SSL inspection")
            recommendations.append("Add SSL inspection rules to analyze encrypted traffic")

        # DLP Rules (+10)
        dlp = self._safe_list(d.get("dlp_rules"))
        if dlp:
            score += 10
            breakdown.append(f"+10  DLP rules ({len(dlp)})")
        else:
            breakdown.append("+0   No DLP rules")
            recommendations.append("Configure DLP rules to prevent data leakage")

        # URL Filtering (+10)
        url = self._safe_list(d.get("url_rules"))
        if url:
            score += 10
            breakdown.append(f"+10  URL filtering ({len(url)} rules)")
        else:
            breakdown.append("+0   No URL filtering")
            recommendations.append("Add URL filtering rules")

        # Firewall Rules (+10)
        fw = self._safe_list(d.get("firewall_rules"))
        if fw:
            score += 10
            breakdown.append(f"+10  Firewall rules ({len(fw)})")
        else:
            breakdown.append("+0   No firewall rules")
            recommendations.append("Configure cloud firewall rules")

        # Access Policies (+10)
        policies = self._safe_list(d.get("access_policies"))
        if policies:
            score += 10
            breakdown.append(f"+10  Access policies ({len(policies)})")
        else:
            breakdown.append("+0   No access policies")
            recommendations.append("Create ZPA access policies")

        # Connectors health (+5 per group with all enabled, max 20)
        groups = self._safe_list(d.get("connector_groups"))
        healthy_groups = 0
        total_disabled = 0
        for g in groups:
            if not isinstance(g, dict):
                continue
            conns = g.get("connectors", [])
            if isinstance(conns, list) and conns:
                all_enabled = all(c.get("enabled", False) for c in conns if isinstance(c, dict))
                if all_enabled:
                    healthy_groups += 1
                else:
                    total_disabled += sum(1 for c in conns if isinstance(c, dict) and not c.get("enabled"))
        connector_score = min(20, healthy_groups * 5)
        score += connector_score
        breakdown.append(f"+{connector_score:<3d} Connector health ({healthy_groups} healthy groups)")
        if total_disabled:
            score -= min(10, total_disabled * 2)
            breakdown.append(f"-{min(10, total_disabled * 2):<3d} Disabled connectors ({total_disabled})")
            recommendations.append(f"Enable {total_disabled} disabled connectors")

        # Sandbox/ATP (+5)
        atp = self._safe_list(d.get("atp_urls"))
        # Having ATP configured is good, but malicious URLs reduce score
        if d.get("atp_urls") is not None:  # API responded (even if empty)
            score += 5
            breakdown.append("+5   ATP active")
            if atp:
                penalty = min(10, len(atp))
                score -= penalty
                breakdown.append(f"-{penalty:<3d} Malicious URLs detected ({len(atp)})")
        else:
            breakdown.append("+0   ATP status unknown")

        # Segment coverage (+10)
        segments = self._safe_list(d.get("segments"))
        enabled_segs = [s for s in segments if isinstance(s, dict) and s.get("enabled")]
        if enabled_segs:
            score += min(10, len(enabled_segs))
            breakdown.append(f"+{min(10, len(enabled_segs)):<3d} Active segments ({len(enabled_segs)})")

        # Clamp
        score = max(0, min(100, score))

        # Update gauge
        self._gauge.set_score(score)

        # Update breakdown text
        breakdown_text = "\n".join(breakdown)
        self._score_breakdown.setText(breakdown_text)

        # Update recommendations
        if recommendations:
            rec_text = "<b>Recommendations:</b><br>"
            for r in recommendations:
                rec_text += f"  • {r}<br>"
            self._recommendations_label.setText(rec_text)
        else:
            self._recommendations_label.setText(
                "<span style='color: #00E676; font-weight: 600;'>All key security controls are in place.</span>"
            )

        self._log(f"Security posture score: {score}/100")

    async def _safe_call(self, tool_name: str, args: dict | None = None):
        if not self._mcp:
            return None
        try:
            self._log(f"Calling {tool_name}...")
            result = await self._mcp.call_tool(tool_name, args)
            if isinstance(result, dict) and "_rpc_error" in result:
                raise RuntimeError(f"MCP RPC error: {result['_rpc_error']}")
            if isinstance(result, str):
                self._data_errors[tool_name] = result[:500] or "Unstructured tool response"
                self._log(f"Invalid response from {tool_name}.")
                return None
            return result
        except Exception as e:
            self._data_errors[tool_name] = str(e)[:500]
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
            name_label.setFont(QFont("Menlo", 12, QFont.Weight.Bold))
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
