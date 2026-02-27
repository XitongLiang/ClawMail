"""
Theme management for ClawMail.

Uses Qt's Fusion style so that ALL widgets (including native-looking ones on macOS)
fully respect the QPalette.  QPalette tokens in stylesheets are then reliable and
consistent across light and dark themes.

A ThemeManager singleton tracks the current theme, applies the palette + Fusion style
on demand, and exposes semantic color accessors for places that cannot use palette()
tokens (WebEngine HTML, QPainter drawing code).
"""

import sys
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QStyleFactory


# ---------------------------------------------------------------------------
# Palette definitions
# ---------------------------------------------------------------------------

def _make_dark_palette() -> QPalette:
    p = QPalette()

    def c(role, hex_color, disabled_factor=140):
        col = QColor(hex_color)
        dis = col.darker(disabled_factor)
        p.setColor(role, col)
        p.setColor(QPalette.ColorGroup.Inactive, role, col)
        p.setColor(QPalette.ColorGroup.Disabled, role, dis)

    R = QPalette.ColorRole
    c(R.Window,          "#252526")
    c(R.WindowText,      "#d4d4d4")
    c(R.Base,            "#1e1e1e")
    c(R.AlternateBase,   "#2d2d2d")
    c(R.Text,            "#d4d4d4")
    c(R.BrightText,      "#ffffff")
    c(R.Button,          "#3c3c3c")
    c(R.ButtonText,      "#d4d4d4")
    c(R.Highlight,       "#264f78")
    c(R.HighlightedText, "#ffffff")
    c(R.ToolTipBase,     "#3c3c3c")
    c(R.ToolTipText,     "#d4d4d4")
    c(R.Link,            "#569cd6")
    c(R.LinkVisited,     "#c586c0")
    c(R.Mid,             "#555555")
    c(R.Midlight,        "#484848")
    c(R.Dark,            "#1a1a1a")
    c(R.Shadow,          "#101010")
    c(R.PlaceholderText, "#6b6b6b")
    return p


def _make_light_palette() -> QPalette:
    p = QPalette()

    def c(role, hex_color, disabled_factor=140):
        col = QColor(hex_color)
        dis = col.darker(disabled_factor)
        p.setColor(role, col)
        p.setColor(QPalette.ColorGroup.Inactive, role, col)
        p.setColor(QPalette.ColorGroup.Disabled, role, dis)

    R = QPalette.ColorRole
    c(R.Window,          "#f3f3f3")
    c(R.WindowText,      "#1a1a1a")
    c(R.Base,            "#ffffff")
    c(R.AlternateBase,   "#f0f0f0")
    c(R.Text,            "#1a1a1a")
    c(R.BrightText,      "#000000")
    c(R.Button,          "#e8e8e8")
    c(R.ButtonText,      "#1a1a1a")
    c(R.Highlight,       "#0078d7")
    c(R.HighlightedText, "#ffffff")
    c(R.ToolTipBase,     "#ffffc0")
    c(R.ToolTipText,     "#1a1a1a")
    c(R.Link,            "#0064c8")
    c(R.LinkVisited,     "#8000c8")
    c(R.Mid,             "#c0c0c0")
    c(R.Midlight,        "#d8d8d8")
    c(R.Dark,            "#b0b0b0")
    c(R.Shadow,          "#808080")
    c(R.PlaceholderText, "#909090")
    return p


# ---------------------------------------------------------------------------
# ThemeManager
# ---------------------------------------------------------------------------

class ThemeManager(QObject):
    """Singleton that owns the application theme (light / dark / system)."""

    theme_changed = pyqtSignal(str)   # emits "light" or "dark"

    def __init__(self):
        super().__init__()
        self._mode = "system"          # "system" | "light" | "dark"
        self._system_dark = False      # cached OS detection result

    # ------------------------------------------------------------------
    # Initialisation — call once, after QApplication is created
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Detect system dark/light, then switch to Fusion + matching palette."""
        app = QApplication.instance()
        if not app:
            return
        # IMPORTANT: read the OS palette BEFORE touching anything.  Calling
        # app.setStyle("Fusion") resets the application palette to Fusion's own
        # light defaults, so if we read AFTER that call we always get "light".
        bg = app.palette().color(QPalette.ColorRole.Window)
        self._system_dark = bg.lightness() < 128
        # Set Fusion style ONCE — re-creating a new style instance on every
        # palette swap causes a one-frame rendering artefact (the style change
        # triggers a repaint with the old palette, giving an inverted flash).
        app.setStyle(QStyleFactory.create("Fusion"))
        # Apply the correct palette immediately.
        self._apply_palette()

    # ------------------------------------------------------------------
    # Mode management
    # ------------------------------------------------------------------

    def set_mode(self, mode: str) -> None:
        """mode: 'system', 'light', or 'dark'."""
        self._mode = mode
        self._apply_palette()
        self.theme_changed.emit(self.current())

    def _apply_palette(self) -> None:
        """Apply the correct palette and force a full stylesheet re-evaluation.

        Order matters:
        1. setPalette() first — the new palette is in effect BEFORE StyleChange fires.
        2. setStyle(Fusion) — sends QEvent::StyleChange to every widget, which makes
           Qt's stylesheet engine re-evaluate all palette(...) tokens against the
           already-updated palette.  This is the only reliable way to make
           palette(...) tokens refresh across the whole widget tree on macOS.
        """
        app = QApplication.instance()
        if not app:
            return
        app.setPalette(_make_dark_palette() if self.is_dark() else _make_light_palette())
        app.setStyle(QStyleFactory.create("Fusion"))

    # Keep old name as an alias so call-sites that pre-date the rename still work.
    def _apply_style_and_palette(self) -> None:
        self._apply_palette()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def is_dark(self) -> bool:
        if self._mode == "dark":
            return True
        if self._mode == "light":
            return False
        return self._system_dark

    def current(self) -> str:
        return "dark" if self.is_dark() else "light"

    def mode(self) -> str:
        return self._mode

    # ------------------------------------------------------------------
    # Semantic color accessors
    # Used for: QPainter-painted items, WebEngine HTML, hard-coded stylesheets
    # ------------------------------------------------------------------

    # Email list delegate
    def unread_bg(self) -> QColor:
        return QColor("#1a2d45") if self.is_dark() else QColor("#eef5ff")

    def dim_color(self) -> QColor:
        return QColor("#808080") if self.is_dark() else QColor("#999999")

    def draft_fg(self) -> QColor:
        return QColor("#6a6a6a") if self.is_dark() else QColor("#888888")

    def draft_dim(self) -> QColor:
        return QColor("#505050") if self.is_dark() else QColor("#aaaaaa")

    # AI chat bubbles (for HTML inside QTextBrowser)
    def chat_user_bg(self) -> str:
        return "#1e5799" if self.is_dark() else "#4a90d9"

    def chat_user_fg(self) -> str:
        return "#e8f0ff" if self.is_dark() else "#ffffff"

    def chat_ai_bg(self) -> str:
        return "#2d2d2d" if self.is_dark() else "#e8e8e8"

    def chat_ai_fg(self) -> str:
        return "#dddddd" if self.is_dark() else "#222222"

    def chat_timestamp_color(self) -> str:
        return "#606060" if self.is_dark() else "#aaaaaa"

    # Filter toggle checked state
    def filter_checked_bg(self) -> str:
        return "#1e3870" if self.is_dark() else "#c5d0f5"

    def filter_checked_border(self) -> str:
        return "#3a5aaa" if self.is_dark() else "#8899dd"

    # Primary action button
    def primary_btn_bg(self) -> str:
        return "#2a5aa8" if self.is_dark() else "#5c7cfa"

    def primary_btn_hover(self) -> str:
        return "#1e4a98" if self.is_dark() else "#4a67e0"

    # Settings section separators / labels
    def settings_section_color(self) -> str:
        return "#a0a0a0" if self.is_dark() else "#555555"

    def settings_section_border(self) -> str:
        return "#444444" if self.is_dark() else "#dddddd"

    # WebEngine HTML content (AI summary, email headers, quoted text)
    def html_text(self) -> str:
        """Normal body text inside WebEngine panels."""
        return "#d4d4d4" if self.is_dark() else "#222222"

    def html_dim(self) -> str:
        """Dimmed/secondary text inside WebEngine panels."""
        return "#808080" if self.is_dark() else "#888888"

    def html_panel_bg(self) -> str:
        return "#1e2030" if self.is_dark() else "#f5f7ff"

    def html_panel_border(self) -> str:
        return "#3d4a8a" if self.is_dark() else "#c5cae9"

    def html_section_label(self) -> str:
        return "#7ea8d8" if self.is_dark() else "#7986cb"

    def html_header_border(self) -> str:
        return "#444444" if self.is_dark() else "#dddddd"

    def html_link_color(self) -> str:
        return "#569cd6" if self.is_dark() else "#0064c8"

    def html_warning_bg(self) -> str:
        return "#2a2000" if self.is_dark() else "#fff8e1"

    def html_warning_border(self) -> str:
        return "#665500" if self.is_dark() else "#ffe082"

    def html_warning_text(self) -> str:
        return "#ccaa44" if self.is_dark() else "#795548"

    def html_quote_border(self) -> str:
        return "#555555" if self.is_dark() else "#cccccc"

    # OAuth code display
    def oauth_code_color(self) -> str:
        return "#d4d4d4" if self.is_dark() else "#222222"

    def oauth_status_color(self) -> str:
        return "#909090" if self.is_dark() else "#555555"

    # Agent dialog buttons (server.py)
    def dialog_btn_bg(self) -> str:
        return "#3c3c3c" if self.is_dark() else "#eef1f8"

    def dialog_btn_border(self) -> str:
        return "#555555" if self.is_dark() else "#b0b8d0"

    def dialog_btn_hover(self) -> str:
        return "#484848" if self.is_dark() else "#d8e0f4"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_theme_manager = ThemeManager()


def get_theme() -> ThemeManager:
    return _theme_manager
