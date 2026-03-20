"""Policy visualization widget — renders real ZPA policy flow as a visual map.

Shows: User → Access Policies → Segment Groups → Application Segments → Server Groups → Connectors
Highlights anomalies like segments without policies or policies without segments.
"""

import math
from dataclasses import dataclass, field
from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QLinearGradient
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame


@dataclass
class PolicyNode:
    """Represents a single policy element in the visual map."""
    name: str
    category: str
    status: str = "active"  # active, warning, disabled
    count: int = 0
    children: list[str] = field(default_factory=list)
    detail: str = ""


class PolicyFlowWidget(QWidget):
    """Draws an animated policy flow visualization with columns for each layer."""

    COLUMN_LABELS = ["Access Policies", "Segment Groups", "App Segments", "Server Groups", "Connectors"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns: dict[str, list[PolicyNode]] = {}
        self._connections: list[tuple[str, str, str, str]] = []  # (from_col, from_name, to_col, to_name)
        self._anomalies: list[str] = []
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(30)
        self.setMinimumHeight(400)
        self.setMinimumWidth(900)

    def set_flow_data(self, columns: dict[str, list[PolicyNode]],
                      connections: list[tuple[str, str, str, str]],
                      anomalies: list[str]):
        self._columns = columns
        self._connections = connections
        self._anomalies = anomalies
        max_nodes = max((len(v) for v in columns.values()), default=5)
        self.setMinimumHeight(max(400, max_nodes * 52 + 120))
        self.update()

    def _animate(self):
        self._phase += 0.02
        if self._phase > 2 * math.pi:
            self._phase -= 2 * math.pi
        self.update()

    def _status_color(self, status: str) -> QColor:
        if status == "active":
            return QColor("#00E676")
        elif status == "warning":
            return QColor("#FFB347")
        return QColor("#484F58")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        if not self._columns:
            # Draw placeholder
            painter.setPen(QColor("#8B949E"))
            painter.setFont(QFont(".AppleSystemUIFont", 13))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                             "Connect to MCP server and load policies to visualize flow")
            painter.end()
            return

        visible_cols = [c for c in self.COLUMN_LABELS if c in self._columns and self._columns[c]]
        if not visible_cols:
            painter.setPen(QColor("#8B949E"))
            painter.setFont(QFont(".AppleSystemUIFont", 13))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter,
                             "No policy data available")
            painter.end()
            return

        col_count = len(visible_cols)
        margin_x = 24
        margin_y = 50
        col_w = (w - 2 * margin_x) / col_count
        node_h = 38
        node_spacing = 8
        node_w = min(200, col_w - 30)

        # Build position map for connections
        pos_map: dict[tuple, QPointF] = {}

        for ci, col_name in enumerate(visible_cols):
            col_x = margin_x + ci * col_w
            nodes = self._columns.get(col_name, [])

            # Column header
            painter.setPen(QColor("#8B949E"))
            painter.setFont(QFont(".AppleSystemUIFont", 10, QFont.Weight.DemiBold))
            painter.drawText(QRectF(col_x, 10, col_w, 25), Qt.AlignmentFlag.AlignCenter,
                             col_name.upper())

            # Header underline
            grad = QLinearGradient(col_x + 10, 0, col_x + col_w - 10, 0)
            grad.setColorAt(0.0, QColor(0, 212, 170, 0))
            grad.setColorAt(0.5, QColor(0, 212, 170, 80))
            grad.setColorAt(1.0, QColor(0, 212, 170, 0))
            painter.setPen(QPen(grad, 1))
            painter.drawLine(QPointF(col_x + 10, 36), QPointF(col_x + col_w - 10, 36))

            for ni, node in enumerate(nodes[:12]):  # limit display
                nx = col_x + (col_w - node_w) / 2
                ny = margin_y + ni * (node_h + node_spacing)
                rect = QRectF(nx, ny, node_w, node_h)

                # Glass bg
                glass = QColor(30, 38, 50, 100)
                painter.setBrush(glass)
                painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
                painter.drawRoundedRect(rect, 8, 8)

                # Status dot with pulse
                dot_color = self._status_color(node.status)
                pulse = 0.6 + 0.4 * math.sin(self._phase + ni * 0.5)
                dot_color.setAlphaF(pulse)
                painter.setBrush(dot_color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(nx + 12, ny + node_h / 2), 4, 4)

                # Name (truncate with ellipsis)
                painter.setPen(QColor("#E6EDF3"))
                painter.setFont(QFont(".AppleSystemUIFont", 10))
                text_rect = QRectF(nx + 22, ny, node_w - 28, node_h)
                display_name = node.name
                fm = painter.fontMetrics()
                elided = fm.elidedText(display_name, Qt.TextElideMode.ElideRight, int(node_w - 28))
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, elided)

                # Store position for connections (right edge midpoint)
                center_y = ny + node_h / 2
                pos_map[(col_name, node.name)] = QPointF(nx + node_w, center_y)
                pos_map[(col_name, node.name, "left")] = QPointF(nx, center_y)

            # "and X more" label
            if len(nodes) > 12:
                more_y = margin_y + 12 * (node_h + node_spacing)
                painter.setPen(QColor("#8B949E"))
                painter.setFont(QFont(".AppleSystemUIFont", 9))
                painter.drawText(QRectF(col_x, more_y, col_w, 20), Qt.AlignmentFlag.AlignCenter,
                                 f"+ {len(nodes) - 12} more")

        # Draw connections between columns
        for from_col, from_name, to_col, to_name in self._connections:
            from_pt = pos_map.get((from_col, from_name))
            to_pt = pos_map.get((to_col, to_name, "left"))
            if from_pt and to_pt:
                conn_color = QColor(0, 212, 170, 50)
                painter.setPen(QPen(conn_color, 1, Qt.PenStyle.DashLine))
                painter.drawLine(from_pt, to_pt)

        # Anomaly banner at bottom
        if self._anomalies:
            banner_y = h - len(self._anomalies) * 20 - 10
            painter.setPen(QColor("#FFB347"))
            painter.setFont(QFont(".AppleSystemUIFont", 10, QFont.Weight.DemiBold))
            painter.drawText(QRectF(margin_x, banner_y - 22, w, 20),
                             Qt.AlignmentFlag.AlignLeft, "ANOMALIES DETECTED:")
            painter.setFont(QFont(".AppleSystemUIFont", 10))
            for i, anomaly in enumerate(self._anomalies[:8]):
                painter.drawText(QRectF(margin_x + 12, banner_y + i * 18, w - 40, 18),
                                 Qt.AlignmentFlag.AlignLeft, f"  {anomaly}")

        painter.end()


class PolicyMapWidget(QFrame):
    """Scrollable policy map container."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("glassCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)

        title = QLabel("  Policy Flow Map")
        title.setObjectName("cardTitle")
        title.setFont(QFont(".AppleSystemUIFont", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        self._subtitle = QLabel("  User → Access Policies → Segments → Servers → Connectors")
        self._subtitle.setObjectName("subtitle")
        layout.addWidget(self._subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._flow = PolicyFlowWidget()
        scroll.setWidget(self._flow)
        layout.addWidget(scroll)

    def set_policies(self, nodes: list[PolicyNode]):
        """Legacy compat — convert flat list to columns."""
        columns: dict[str, list[PolicyNode]] = {}
        for n in nodes:
            columns.setdefault(n.category, []).append(n)
        self._flow.set_flow_data(columns, [], [])

    def set_flow_data(self, columns: dict[str, list[PolicyNode]],
                      connections: list[tuple[str, str, str, str]],
                      anomalies: list[str]):
        count = sum(len(v) for v in columns.values())
        self._subtitle.setText(f"  {count} policy elements across {len(columns)} layers")
        self._flow.set_flow_data(columns, connections, anomalies)
