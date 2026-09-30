"""Anomaly and security findings panel widget."""

from dataclasses import dataclass
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
    QGraphicsOpacityEffect,
)


@dataclass
class Finding:
    """A single security finding or anomaly."""
    severity: str  # critical, high, medium, low, info
    title: str
    detail: str
    source: str = ""  # e.g. "ZEASM", "Policy Audit", "Connector Health"


SEVERITY_COLORS = {
    "critical": "#FF4444",
    "high": "#FF6B6B",
    "medium": "#FFB347",
    "low": "#64B5F6",
    "info": "#8B949E",
}

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


class FindingCard(QFrame):
    """A single finding card."""

    def __init__(self, finding: Finding, parent=None):
        super().__init__(parent)
        self.setObjectName("glassCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        # Severity badge
        color = SEVERITY_COLORS.get(finding.severity, "#8B949E")
        badge = QLabel(finding.severity.upper())
        badge.setFixedWidth(70)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFont(QFont(".AppleSystemUIFont", 9, QFont.Weight.Bold))
        badge.setStyleSheet(
            f"color: {color}; background: {color}22; "
            f"border: 1px solid {color}44; border-radius: 6px; padding: 4px 8px;"
        )
        layout.addWidget(badge)

        # Content
        content = QVBoxLayout()
        content.setSpacing(2)

        title_row = QHBoxLayout()
        title_lbl = QLabel(finding.title)
        title_lbl.setFont(QFont(".AppleSystemUIFont", 12, QFont.Weight.DemiBold))
        title_lbl.setWordWrap(True)
        title_row.addWidget(title_lbl, 1)

        if finding.source:
            src_lbl = QLabel(finding.source)
            src_lbl.setFont(QFont(".AppleSystemUIFont", 9))
            src_lbl.setStyleSheet("color: #8B949E; background: rgba(255,255,255,0.05); "
                                  "border-radius: 4px; padding: 2px 6px;")
            title_row.addWidget(src_lbl)

        content.addLayout(title_row)

        if finding.detail:
            detail_lbl = QLabel(finding.detail)
            detail_lbl.setObjectName("subtitle")
            detail_lbl.setWordWrap(True)
            content.addWidget(detail_lbl)

        layout.addLayout(content, 1)

        # Fade in
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(400)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()
        self._anim = anim  # prevent GC


class FindingsPanel(QFrame):
    """Scrollable panel showing all findings sorted by severity."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Header
        header_row = QHBoxLayout()
        self._title = QLabel("Security Findings")
        self._title.setObjectName("sectionTitle")
        header_row.addWidget(self._title)

        self._count_label = QLabel("0 findings")
        self._count_label.setObjectName("subtitle")
        header_row.addWidget(self._count_label)
        header_row.addStretch()
        layout.addLayout(header_row)

        # Summary badges
        self._summary_row = QHBoxLayout()
        self._severity_counts: dict[str, QLabel] = {}
        for sev in ["critical", "high", "medium", "low", "info"]:
            lbl = QLabel(f"{sev.upper()}: 0")
            lbl.setFont(QFont(".AppleSystemUIFont", 10, QFont.Weight.Bold))
            color = SEVERITY_COLORS[sev]
            lbl.setStyleSheet(
                f"color: {color}; background: {color}15; "
                f"border-radius: 6px; padding: 4px 10px;"
            )
            self._severity_counts[sev] = lbl
            self._summary_row.addWidget(lbl)
        self._summary_row.addStretch()
        layout.addLayout(self._summary_row)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setSpacing(6)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self._container)
        layout.addWidget(scroll, 1)

        self._placeholder = QLabel("Connect and refresh to detect anomalies and findings.")
        self._placeholder.setObjectName("subtitle")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._container_layout.addWidget(self._placeholder)
        self._container_layout.addStretch()

    def set_findings(self, findings: list[Finding], *, incomplete: bool = False):
        # Clear
        while self._container_layout.count():
            item = self._container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Sort by severity
        sorted_findings = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 5))

        # Count by severity
        counts: dict[str, int] = {}
        for f in sorted_findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1

        for sev, lbl in self._severity_counts.items():
            c = counts.get(sev, 0)
            lbl.setText(f"{sev.upper()}: {c}")

        self._count_label.setText(
            f"{len(sorted_findings)} findings · checks incomplete"
            if incomplete else f"{len(sorted_findings)} findings"
        )
        self._count_label.setObjectName("statusWarn" if incomplete else "subtitle")

        if not sorted_findings:
            lbl = QLabel(
                "Some checks could not be completed. Retry before treating this as a clean result."
                if incomplete else "No findings detected — looking good!"
            )
            lbl.setObjectName("statusWarn" if incomplete else "statusGood")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._container_layout.addWidget(lbl)
        else:
            for finding in sorted_findings:
                self._container_layout.addWidget(FindingCard(finding))

        self._container_layout.addStretch()
