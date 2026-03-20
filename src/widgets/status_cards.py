"""Glass-morphism status cards for dashboard metrics."""

from PySide6.QtCore import (
    QPropertyAnimation,
    QEasingCurve,
    Property,
    Qt,
    QRectF,
)
from PySide6.QtGui import QColor, QFont, QPainter, QLinearGradient
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
    QGraphicsOpacityEffect,
    QSizePolicy,
)


class StatusCard(QFrame):
    """A single glass-morphism metric card."""

    def __init__(self, title: str, value: str = "—", icon: str = "", accent: str = "#00D4AA",
                 parent=None):
        super().__init__(parent)
        self.setObjectName("glassCard")
        self.setFixedHeight(130)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._accent = accent

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(6)

        # Top row: icon + title
        top = QHBoxLayout()
        if icon:
            icon_lbl = QLabel(icon)
            icon_lbl.setFont(QFont("SF Pro Display", 16))
            top.addWidget(icon_lbl)
        title_lbl = QLabel(title)
        title_lbl.setObjectName("subtitle")
        title_lbl.setFont(QFont("SF Pro Display", 12, QFont.Weight.Medium))
        top.addWidget(title_lbl)
        top.addStretch()
        layout.addLayout(top)

        # Value
        self._value_label = QLabel(value)
        self._value_label.setObjectName("cardValue")
        self._value_label.setStyleSheet(f"color: {accent}; font-size: 28px; font-weight: 700;")
        layout.addWidget(self._value_label)

        # Subtitle / detail line
        self._detail_label = QLabel("")
        self._detail_label.setObjectName("subtitle")
        self._detail_label.setFont(QFont("SF Pro Display", 11))
        layout.addWidget(self._detail_label)

        # Fade-in animation
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        self._fade = QPropertyAnimation(effect, b"opacity")
        self._fade.setDuration(600)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.start()

    def set_value(self, value: str):
        self._value_label.setText(value)

    def set_detail(self, text: str):
        self._detail_label.setText(text)

    def paintEvent(self, event):
        super().paintEvent(event)
        # Draw accent stripe on top
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, self.width(), 0)
        color = QColor(self._accent)
        grad.setColorAt(0.0, color)
        color2 = QColor(self._accent)
        color2.setAlphaF(0.3)
        grad.setColorAt(1.0, color2)
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(0, 0, self.width(), 3), 1.5, 1.5)
        painter.end()


class StatusCardRow(QWidget):
    """Horizontal row of status cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(16)
        self._cards: dict[str, StatusCard] = {}

    def add_card(self, key: str, title: str, icon: str = "", accent: str = "#00D4AA") -> StatusCard:
        card = StatusCard(title, icon=icon, accent=accent, parent=self)
        self._cards[key] = card
        self._layout.addWidget(card)
        return card

    def card(self, key: str) -> StatusCard | None:
        return self._cards.get(key)
