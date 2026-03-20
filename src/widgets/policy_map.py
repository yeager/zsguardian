"""Policy visualization widget — renders policy rules as a visual flow map."""

import math
from PySide6.QtCore import Qt, QRectF, QPointF, QTimer, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPainterPath, QLinearGradient
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QSizePolicy


class PolicyNode:
    """Represents a single policy element in the visual map."""

    def __init__(self, name: str, category: str, status: str = "active", count: int = 0):
        self.name = name
        self.category = category
        self.status = status  # active, warning, disabled
        self.count = count


class PolicyFlowWidget(QWidget):
    """Draws an animated policy flow visualization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._nodes: list[PolicyNode] = []
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(30)
        self.setMinimumHeight(300)

    def set_nodes(self, nodes: list[PolicyNode]):
        self._nodes = nodes
        self.setMinimumHeight(max(300, len(nodes) * 60 + 100))
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
        if not self._nodes:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        margin = 30
        node_h = 44
        node_w = min(320, w - 2 * margin - 60)
        spacing = 56
        start_y = 30

        # Categorize nodes
        categories: dict[str, list[PolicyNode]] = {}
        for node in self._nodes:
            categories.setdefault(node.category, []).append(node)

        y = start_y
        cat_positions: list[tuple[str, float]] = []

        for cat, nodes in categories.items():
            cat_positions.append((cat, y))

            # Category label
            painter.setPen(QColor("#8B949E"))
            painter.setFont(QFont("SF Pro Display", 11, QFont.Weight.DemiBold))
            painter.drawText(QRectF(margin, y, node_w, 22), Qt.AlignmentFlag.AlignLeft, cat.upper())
            y += 28

            for i, node in enumerate(nodes):
                x = margin + 10
                rect = QRectF(x, y, node_w, node_h)

                # Glass background
                glass = QColor(30, 38, 50, 100)
                painter.setBrush(glass)
                painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
                painter.drawRoundedRect(rect, 10, 10)

                # Status dot
                dot_color = self._status_color(node.status)
                pulse = 0.6 + 0.4 * math.sin(self._phase + i * 0.5)
                dot_color.setAlphaF(pulse)
                painter.setBrush(dot_color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(x + 18, y + node_h / 2), 5, 5)

                # Node name
                painter.setPen(QColor("#E6EDF3"))
                painter.setFont(QFont("SF Pro Display", 12, QFont.Weight.Medium))
                painter.drawText(QRectF(x + 32, y, node_w - 80, node_h),
                                 Qt.AlignmentFlag.AlignVCenter, node.name)

                # Count badge
                if node.count > 0:
                    badge_text = str(node.count)
                    painter.setPen(QColor("#00D4AA"))
                    painter.setFont(QFont("SF Mono", 10, QFont.Weight.Bold))
                    painter.drawText(QRectF(x + node_w - 60, y, 50, node_h),
                                     Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                                     badge_text)

                y += spacing

            y += 10

        # Connection lines between categories
        if len(cat_positions) > 1:
            painter.setPen(QPen(QColor(0, 212, 170, 40), 1, Qt.PenStyle.DashLine))
            for i in range(len(cat_positions) - 1):
                _, y1 = cat_positions[i]
                _, y2 = cat_positions[i + 1]
                cx = margin + 5
                painter.drawLine(QPointF(cx, y1 + 28), QPointF(cx, y2))

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
        title.setFont(QFont("SF Pro Display", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._flow = PolicyFlowWidget()
        scroll.setWidget(self._flow)
        layout.addWidget(scroll)

    def set_policies(self, nodes: list[PolicyNode]):
        self._flow.set_nodes(nodes)
