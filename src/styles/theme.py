"""Glassmorphism theme with dark/light mode support for ZscalerGuardian."""

from PySide6.QtGui import QColor, QLinearGradient, QFont

# Brand colors
ZSCALER_BLUE = "#0076CE"
ZSCALER_DARK = "#003366"
GUARDIAN_ACCENT = "#00D4AA"
GUARDIAN_WARN = "#FF6B6B"
GUARDIAN_AMBER = "#FFB347"
GUARDIAN_GREEN = "#00E676"

DARK_THEME = {
    "bg_primary": "#0D1117",
    "bg_secondary": "#161B22",
    "bg_card": "rgba(22, 27, 34, 0.75)",
    "bg_glass": "rgba(30, 38, 50, 0.55)",
    "border_glass": "rgba(255, 255, 255, 0.08)",
    "text_primary": "#E6EDF3",
    "text_secondary": "#8B949E",
    "text_muted": "#484F58",
    "accent": GUARDIAN_ACCENT,
    "accent_hover": "#00FFCC",
    "blue": ZSCALER_BLUE,
    "danger": GUARDIAN_WARN,
    "warning": GUARDIAN_AMBER,
    "success": GUARDIAN_GREEN,
    "gradient_start": "#0D1117",
    "gradient_end": "#1A1F2E",
    "sidebar_bg": "rgba(13, 17, 23, 0.92)",
    "input_bg": "rgba(22, 27, 34, 0.85)",
    "input_border": "rgba(255, 255, 255, 0.1)",
    "scrollbar_bg": "rgba(255, 255, 255, 0.05)",
    "scrollbar_handle": "rgba(255, 255, 255, 0.15)",
}

LIGHT_THEME = {
    "bg_primary": "#F6F8FA",
    "bg_secondary": "#FFFFFF",
    "bg_card": "rgba(255, 255, 255, 0.8)",
    "bg_glass": "rgba(255, 255, 255, 0.6)",
    "border_glass": "rgba(0, 0, 0, 0.06)",
    "text_primary": "#1F2328",
    "text_secondary": "#656D76",
    "text_muted": "#8B949E",
    "accent": "#009B7D",
    "accent_hover": "#00C49A",
    "blue": ZSCALER_BLUE,
    "danger": "#D1242F",
    "warning": "#BF8700",
    "success": "#1A7F37",
    "gradient_start": "#F6F8FA",
    "gradient_end": "#EFF2F5",
    "sidebar_bg": "rgba(255, 255, 255, 0.95)",
    "input_bg": "rgba(246, 248, 250, 0.9)",
    "input_border": "rgba(0, 0, 0, 0.1)",
    "scrollbar_bg": "rgba(0, 0, 0, 0.03)",
    "scrollbar_handle": "rgba(0, 0, 0, 0.12)",
}


def get_stylesheet(theme: dict) -> str:
    t = theme
    return f"""
    /* Global */
    QMainWindow, QDialog {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {t['gradient_start']}, stop:1 {t['gradient_end']});
        color: {t['text_primary']};
    }}
    QWidget {{
        color: {t['text_primary']};
        font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    }}

    /* Glass card */
    QFrame#glassCard {{
        background: {t['bg_glass']};
        border: 1px solid {t['border_glass']};
        border-radius: 16px;
        padding: 20px;
    }}

    /* Sidebar */
    QFrame#sidebar {{
        background: {t['sidebar_bg']};
        border-right: 1px solid {t['border_glass']};
        border-radius: 0px;
    }}

    /* Buttons */
    QPushButton {{
        background: {t['bg_glass']};
        border: 1px solid {t['border_glass']};
        border-radius: 10px;
        padding: 10px 20px;
        color: {t['text_primary']};
        font-weight: 600;
        font-size: 13px;
    }}
    QPushButton:hover {{
        background: {t['accent']};
        color: #000000;
        border: 1px solid {t['accent']};
    }}
    QPushButton:pressed {{
        background: {t['accent_hover']};
    }}
    QPushButton#primaryButton {{
        background: {t['accent']};
        color: #000000;
        border: none;
        font-weight: 700;
    }}
    QPushButton#primaryButton:hover {{
        background: {t['accent_hover']};
    }}
    QPushButton#dangerButton {{
        background: transparent;
        border: 1px solid {t['danger']};
        color: {t['danger']};
    }}
    QPushButton#dangerButton:hover {{
        background: {t['danger']};
        color: #FFFFFF;
    }}
    QPushButton#sidebarButton {{
        background: transparent;
        border: none;
        border-radius: 8px;
        padding: 12px 16px;
        text-align: left;
        font-size: 13px;
        font-weight: 500;
        color: {t['text_secondary']};
    }}
    QPushButton#sidebarButton:hover {{
        background: {t['bg_glass']};
        color: {t['text_primary']};
    }}
    QPushButton#sidebarButtonActive {{
        background: {t['bg_glass']};
        border: none;
        border-radius: 8px;
        padding: 12px 16px;
        text-align: left;
        font-size: 13px;
        font-weight: 600;
        color: {t['accent']};
    }}

    /* Input fields */
    QLineEdit {{
        background: {t['input_bg']};
        border: 1px solid {t['input_border']};
        border-radius: 10px;
        padding: 10px 14px;
        color: {t['text_primary']};
        font-size: 13px;
        selection-background-color: {t['accent']};
    }}
    QLineEdit:focus {{
        border: 1px solid {t['accent']};
    }}

    /* Labels */
    QLabel {{
        color: {t['text_primary']};
    }}
    QLabel#sectionTitle {{
        font-size: 22px;
        font-weight: 700;
        color: {t['text_primary']};
    }}
    QLabel#cardTitle {{
        font-size: 14px;
        font-weight: 600;
        color: {t['text_primary']};
    }}
    QLabel#cardValue {{
        font-size: 28px;
        font-weight: 700;
        color: {t['accent']};
    }}
    QLabel#subtitle {{
        font-size: 12px;
        color: {t['text_secondary']};
    }}
    QLabel#statusGood {{
        color: {t['success']};
        font-weight: 600;
    }}
    QLabel#statusWarn {{
        color: {t['warning']};
        font-weight: 600;
    }}
    QLabel#statusBad {{
        color: {t['danger']};
        font-weight: 600;
    }}

    /* Scroll areas */
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: {t['scrollbar_bg']};
        width: 8px;
        border-radius: 4px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {t['scrollbar_handle']};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        height: 0px;
    }}

    /* Tab widget */
    QTabWidget::pane {{
        border: 1px solid {t['border_glass']};
        border-radius: 12px;
        background: {t['bg_glass']};
    }}
    QTabBar::tab {{
        background: transparent;
        padding: 8px 16px;
        color: {t['text_secondary']};
        font-weight: 500;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{
        color: {t['accent']};
        border-bottom: 2px solid {t['accent']};
    }}

    /* Progress bar */
    QProgressBar {{
        background: {t['bg_glass']};
        border: 1px solid {t['border_glass']};
        border-radius: 8px;
        text-align: center;
        color: {t['text_primary']};
        font-weight: 600;
        font-size: 11px;
        height: 20px;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {t['accent']}, stop:1 {t['blue']});
        border-radius: 7px;
    }}

    /* Combo box */
    QComboBox {{
        background: {t['input_bg']};
        border: 1px solid {t['input_border']};
        border-radius: 10px;
        padding: 8px 14px;
        color: {t['text_primary']};
        font-size: 13px;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background: {t['bg_secondary']};
        border: 1px solid {t['border_glass']};
        border-radius: 8px;
        color: {t['text_primary']};
        selection-background-color: {t['accent']};
    }}

    /* Tooltips */
    QToolTip {{
        background: {t['bg_secondary']};
        border: 1px solid {t['border_glass']};
        border-radius: 6px;
        color: {t['text_primary']};
        padding: 6px 10px;
        font-size: 12px;
    }}

    /* Text edit (for log viewer) */
    QTextEdit {{
        background: {t['input_bg']};
        border: 1px solid {t['input_border']};
        border-radius: 10px;
        padding: 10px;
        color: {t['text_primary']};
        font-family: "SF Mono", "Menlo", "Monaco", monospace;
        font-size: 12px;
    }}
    """
