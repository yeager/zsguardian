"""Radial security score gauge widget with animated gradient arc."""

import math

from PySide6.QtCore import (
    QPropertyAnimation,
    QEasingCurve,
    QRectF,
    Property,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QFont,
    QPainter,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QWidget


class SecurityScoreGauge(QWidget):
    """A circular gauge that displays 0–100 security posture score with glow effects."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._score = 0.0
        self._display_score = 0.0
        self._animation = QPropertyAnimation(self, b"display_score")
        self._animation.setDuration(1200)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.setMinimumSize(220, 220)

        # Pulse timer for glow effect
        self._pulse_phase = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse_tick)
        self._pulse_timer.start(30)

    def _get_display_score(self) -> float:
        return self._display_score

    def _set_display_score(self, value: float):
        self._display_score = value
        self.update()

    display_score = Property(float, _get_display_score, _set_display_score)

    def set_score(self, score: float):
        self._score = max(0.0, min(100.0, score))
        self._animation.stop()
        self._animation.setStartValue(self._display_score)
        self._animation.setEndValue(self._score)
        self._animation.start()

    def _pulse_tick(self):
        self._pulse_phase += 0.05
        if self._pulse_phase > 2 * math.pi:
            self._pulse_phase -= 2 * math.pi
        self.update()

    def _score_color(self) -> QColor:
        s = self._display_score
        if s >= 80:
            return QColor("#00E676")
        elif s >= 60:
            return QColor("#00D4AA")
        elif s >= 40:
            return QColor("#FFB347")
        else:
            return QColor("#FF6B6B")

    def _grade(self) -> str:
        s = self._display_score
        if s >= 90:
            return "A+"
        elif s >= 80:
            return "A"
        elif s >= 70:
            return "B"
        elif s >= 60:
            return "C"
        elif s >= 40:
            return "D"
        else:
            return "F"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        side = min(w, h)
        margin = 20
        arc_width = 14

        cx, cy = w / 2, h / 2
        radius = (side - 2 * margin) / 2

        # Outer glow
        pulse = 0.4 + 0.3 * math.sin(self._pulse_phase)
        glow_color = self._score_color()
        glow_color.setAlphaF(pulse * 0.15)
        glow_grad = QRadialGradient(cx, cy, radius + 20)
        glow_grad.setColorAt(0.7, glow_color)
        glow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow_grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - radius - 20, cy - radius - 20,
                                    (radius + 20) * 2, (radius + 20) * 2))

        # Track (background ring)
        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        track_pen = QPen(QColor(255, 255, 255, 15), arc_width)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(rect, 225 * 16, -270 * 16)

        # Score arc with conical gradient
        fraction = self._display_score / 100.0
        sweep = -270.0 * fraction

        grad = QConicalGradient(cx, cy, 225)
        color = self._score_color()
        grad.setColorAt(0.0, color.lighter(130))
        grad.setColorAt(0.5, color)
        grad.setColorAt(1.0, color.darker(130))

        arc_pen = QPen(grad, arc_width)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        painter.drawArc(rect, 225 * 16, int(sweep * 16))

        # Center text — score
        painter.setPen(QColor("#E6EDF3"))
        font = QFont("SF Pro Display", int(side * 0.18), QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(0, cy - side * 0.18, w, side * 0.28),
                         Qt.AlignmentFlag.AlignCenter,
                         f"{int(self._display_score)}")

        # Grade label
        grade_font = QFont("SF Pro Display", int(side * 0.07), QFont.Weight.DemiBold)
        painter.setFont(grade_font)
        painter.setPen(self._score_color())
        painter.drawText(QRectF(0, cy + side * 0.06, w, side * 0.14),
                         Qt.AlignmentFlag.AlignCenter,
                         self._grade())

        # Label below
        label_font = QFont("SF Pro Display", int(side * 0.045))
        painter.setFont(label_font)
        painter.setPen(QColor("#8B949E"))
        painter.drawText(QRectF(0, cy + side * 0.17, w, side * 0.1),
                         Qt.AlignmentFlag.AlignCenter,
                         "Security Posture")

        painter.end()
