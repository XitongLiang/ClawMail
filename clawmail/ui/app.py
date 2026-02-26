"""
ClawMailApp — 主窗口（Phase 1）
四栏布局：文件夹列表 | 邮件列表 | 邮件内容 | AI 助手
接入 SyncService，显示真实邮件数据。
"""

import asyncio
import html as _html_mod
import json
import re
import shutil
from datetime import datetime, timedelta
from typing import Optional

_CST = timedelta(hours=8)

def _to_cst(dt: datetime) -> datetime:
    """UTC datetime → 北京时间（UTC+8）。"""
    return dt + _CST

from PyQt6.QtCore import QEvent, Qt, QDate, QSize, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QDesktopServices, QFont
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPushButton,
    QSplitter, QStatusBar, QStyle, QStyledItemDelegate, QTextBrowser, QTextEdit,
    QVBoxLayout, QWidget,
)


# 注入到所有邮件 HTML 的响应式 CSS：图片宽度自适应，防止横向溢出，支持深色模式
_RESPONSIVE_CSS = (
    "<style>"
    "img{max-width:100%!important;height:auto!important;}"
    "body{overflow-x:hidden!important;}"
    "@media(prefers-color-scheme:dark){"
    "body{background:#1e1e1e!important;color:#ddd!important;}"
    "a{color:#7aafff!important;}"
    "}"
    "</style>"
)


class EmailListDelegate(QStyledItemDelegate):
    """
    四行邮件列表项：
      行1 = 发件人（左）+ 时间（右，小字）
      行2 = 主题
      行3 = AI one_line 摘要（灰色斜体；无摘要时隐藏，行高压缩）
      行4 = AI 分类标签（彩色小字；无分类时隐藏）
    """
    _ROW_H = 20       # 基础行高
    _TAG_H = 16       # 分类标签行高
    _PAD   = 6        # 上下 padding

    _STRIPE_W     = 3
    _UNREAD_BG    = QColor("#EEF5FF")
    _STRIPE_COLOR = QColor("#2196F3")

    # 分类标签颜色映射
    _TAG_COLORS = {
        "urgent":        "#E53935",
        "pending_reply": "#FB8C00",
        "meeting":       "#1E88E5",
        "approval":      "#8E24AA",
        "notification":  "#43A047",
        "subscription":  "#757575",
    }
    _TAG_LABELS = {
        "urgent":        "紧急",
        "pending_reply": "待回复",
        "meeting":       "会议",
        "approval":      "待审批",
        "notification":  "通知",
        "subscription":  "订阅",
    }

    def sizeHint(self, option, index):
        ai_one_line = index.data(Qt.ItemDataRole.UserRole + 8) or ""
        categories  = index.data(Qt.ItemDataRole.UserRole + 9) or []
        has_summary  = bool(ai_one_line)
        has_tags     = bool(categories)
        h = self._PAD * 2 + self._ROW_H * 2  # 发件人 + 主题（固定）
        if has_summary:
            h += self._ROW_H
        if has_tags:
            h += self._TAG_H + 2
        return QSize(option.rect.width(), h)

    def paint(self, painter, option, index):
        painter.save()

        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_unread   = index.data(Qt.ItemDataRole.UserRole + 4) or False

        # 背景填充
        if is_selected:
            painter.fillRect(option.rect, option.palette.highlight())
            fg  = option.palette.highlightedText().color()
            dim = fg
        elif is_unread:
            painter.fillRect(option.rect, self._UNREAD_BG)
            fg  = option.palette.text().color()
            dim = QColor("#999999")
        else:
            painter.fillRect(option.rect, option.palette.base())
            fg  = option.palette.text().color()
            dim = QColor("#999999")

        # 未读蓝色左侧竖条
        if is_unread and not is_selected:
            painter.fillRect(
                option.rect.x(), option.rect.y(),
                self._STRIPE_W, option.rect.height(),
                self._STRIPE_COLOR,
            )

        is_pinned    = index.data(Qt.ItemDataRole.UserRole + 5) or False
        is_flagged   = index.data(Qt.ItemDataRole.UserRole + 6) or False
        is_draft     = index.data(Qt.ItemDataRole.UserRole + 7) or False
        ai_one_line  = index.data(Qt.ItemDataRole.UserRole + 8) or ""
        categories   = index.data(Qt.ItemDataRole.UserRole + 9) or []
        ai_failed    = index.data(Qt.ItemDataRole.UserRole + 10) or False

        _prefix = "📌 " if is_pinned else ("🚩 " if is_flagged else "")
        if ai_failed:
            _prefix = "⚠️ " + _prefix
        sender   = _prefix + (index.data(Qt.ItemDataRole.UserRole + 1) or "")
        subject  = index.data(Qt.ItemDataRole.UserRole + 2) or ""
        time_str = index.data(Qt.ItemDataRole.UserRole + 3) or ""

        if is_draft and not is_selected:
            fg  = QColor("#888888")
            dim = QColor("#aaaaaa")

        x = option.rect.x() + self._PAD
        y = option.rect.y() + self._PAD
        w = option.rect.width() - self._PAD * 2

        base = QFont(option.font)
        if is_draft:
            base.setItalic(True)

        # --- 行1：发件人（左）+ 时间（右，小字）---
        f1 = QFont(base)
        f1.setBold(is_unread and not is_draft)
        painter.setFont(f1)
        painter.setPen(fg)

        # 先量出时间宽度，再画发件人（截断避免重叠）
        f_time = QFont(base)
        f_time.setBold(False)
        pt = base.pointSize()
        if pt > 0:
            f_time.setPointSize(max(pt - 1, 8))
        from PyQt6.QtGui import QFontMetrics
        fm_time = QFontMetrics(f_time)
        time_w = fm_time.horizontalAdvance(time_str) + 4

        painter.setFont(f1)
        painter.setPen(fg)
        painter.drawText(x, y, w - time_w, self._ROW_H,
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         sender)

        painter.setFont(f_time)
        painter.setPen(dim)
        painter.drawText(x, y, w, self._ROW_H,
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                         time_str)

        # --- 行2：主题 ---
        f2 = QFont(base)
        f2.setBold(is_unread and not is_draft)
        painter.setFont(f2)
        painter.setPen(fg)
        painter.drawText(x, y + self._ROW_H, w, self._ROW_H,
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         subject)

        cur_y = y + self._ROW_H * 2

        # --- 行3：AI one_line 摘要（有内容时才画）---
        if ai_one_line:
            f3 = QFont(base)
            f3.setItalic(True)
            f3.setBold(False)
            if pt > 0:
                f3.setPointSize(max(pt - 1, 8))
            painter.setFont(f3)
            painter.setPen(dim if not is_selected else fg)
            painter.drawText(x, cur_y, w, self._ROW_H,
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             ai_one_line)
            cur_y += self._ROW_H

        # --- 行4：AI 分类标签（彩色小圆角方块）---
        if categories:
            from PyQt6.QtGui import QFontMetrics, QPainterPath
            from PyQt6.QtCore import QRectF
            f4 = QFont(base)
            f4.setBold(False)
            if pt > 0:
                f4.setPointSize(max(pt - 2, 7))
            painter.setFont(f4)
            fm4 = QFontMetrics(f4)
            tag_x = x
            tag_y = cur_y + 1
            for cat in categories[:4]:   # 最多显示 4 个标签
                label = self._TAG_LABELS.get(cat, cat)
                color_str = self._TAG_COLORS.get(cat, "#607D8B")
                tag_w = fm4.horizontalAdvance(label) + 8
                if tag_x + tag_w > option.rect.right() - self._PAD:
                    break
                tag_rect = QRectF(tag_x, tag_y, tag_w, self._TAG_H - 2)
                tag_color = QColor(color_str)
                if is_selected:
                    painter.setPen(Qt.PenStyle.NoPen)
                    fill = QColor(tag_color)
                    fill.setAlpha(180)
                    painter.setBrush(fill)
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                    fill = QColor(tag_color)
                    fill.setAlpha(30)
                    painter.setBrush(fill)
                path = QPainterPath()
                path.addRoundedRect(tag_rect, 3, 3)
                painter.drawPath(path)
                painter.setPen(tag_color if not is_selected else QColor("#ffffff"))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawText(
                    int(tag_x + 4), int(tag_y),
                    int(tag_w - 8), int(self._TAG_H - 2),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    label,
                )
                tag_x += tag_w + 4

        painter.restore()


class _EmailWebPage(QWebEnginePage):
    """拦截邮件中的链接点击，改为在系统浏览器中打开，防止在视图内部跳转。
    clawmail-todo:// 协议链接不打开浏览器，改为发射 todo_link_clicked 信号。"""

    todo_link_clicked   = pyqtSignal(str)  # 发射 clawmail-todo:// 完整 URL
    action_link_clicked = pyqtSignal(str)  # 发射 clawmail-action:// host（reply/reply-all/forward）

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            if url.scheme() == "clawmail-todo":
                self.todo_link_clicked.emit(url.toString())
                return False
            if url.scheme() == "clawmail-action":
                self.action_link_clicked.emit(url.host())
                return False
            QDesktopServices.openUrl(url)
            return False  # 阻止在 WebView 内部跳转
        return True


class EmailWebView(QWebEngineView):
    """QWebEngineView 子类：禁用 JS，允许加载外链图片，链接在系统浏览器打开。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPage(_EmailWebPage(self))
        s = self.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, False)
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)


class _FbStarBar(QWidget):
    """1-5 星评分条：hover 时左侧星星联动高亮，点击后锁定。"""

    rating_selected = pyqtSignal(int)   # 发射 1-5

    _CLR_OFF  = "#d0d0d0"
    _CLR_HOVER  = "#ffc107"
    _CLR_ON   = "#f5a623"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rating = 0
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._btns: list = []
        for i in range(1, 6):
            btn = QPushButton("★")
            btn.setFixedSize(30, 30)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.installEventFilter(self)
            btn.clicked.connect(lambda _, n=i: self._on_click(n))
            layout.addWidget(btn)
            self._btns.append(btn)
        layout.addStretch()
        self._render(0, 0)

    def eventFilter(self, obj, event):
        if obj in self._btns:
            idx = self._btns.index(obj) + 1
            if event.type() == QEvent.Type.Enter:
                self._render(self._rating, idx)
            elif event.type() == QEvent.Type.Leave:
                self._render(self._rating, 0)
        return super().eventFilter(obj, event)

    def _on_click(self, n: int):
        self._rating = n
        self._render(n, 0)
        self.rating_selected.emit(n)

    def _render(self, filled: int, hover: int):
        active = max(filled, hover)
        for i, btn in enumerate(self._btns, 1):
            if i <= active:
                clr = self._CLR_HOVER if (hover > 0 and i <= hover) else self._CLR_ON
            else:
                clr = self._CLR_OFF
            btn.setStyleSheet(
                f"QPushButton{{border:none;background:transparent;"
                f"font-size:22px;color:{clr};padding:0;}}"
            )

    def get_rating(self) -> int:
        return self._rating

    def reset(self):
        self._rating = 0
        self._render(0, 0)


class ClawMailApp(QMainWindow):
    def __init__(self, db=None, cred_manager=None):
        super().__init__()
        self._db = db
        self._cred = cred_manager
        self._sync_service = None
        self._ai_service = None
        self._ai_bridge = None
        self._ai_processing_count = 0
        self._current_folder = "INBOX"
        self._current_category: Optional[str] = None  # AI 分类筛选
        self._current_urgency: Optional[str] = None   # AI 紧急度筛选
        self._current_account_id: Optional[str] = None
        self._current_account = None
        self._current_email = None
        self._search_input = None
        self._search_clear_btn = None
        self._search_hint = None
        self._search_active = False
        self._email_list_header = None
        self._todo_list = None
        self._todo_add_input = None
        self._todo_add_date = None
        self._todo_add_pri = None
        self._todo_add_cat = None
        self._todo_search_input = None
        self._todo_filter_cat = None
        self._todo_sort_combo = None
        self._typing_label = None
        self._typing_timer = None
        self._typing_frame = 0
        self._pending_ai_task: Optional[asyncio.Task] = None
        self._ai_request_cancelled: bool = False
        self._ai_chat_mode: str = "user_chat"
        self._feedback_email_id: Optional[str] = None
        self._feedback_meta = None
        self._init_ui()
        self._ai_chat_mode = self._load_config().get("ai_chat_mode", "user_chat")

    # ----------------------------------------------------------------
    # UI 初始化
    # ----------------------------------------------------------------

    def _init_ui(self):
        self.setWindowTitle("ClawMail")
        self.resize(1200, 700)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left1：文件夹列表 + AI 分类栏（合并到一个左侧面板）
        self._folder_display_map = {
            "收件箱": "INBOX",
            "垃圾邮件": "垃圾邮件",
            "已发送": "已发送",
            "草稿箱": "草稿箱",
            "回收站": "已删除",
        }
        self._folder_list = QListWidget()
        for display in self._folder_display_map:
            _fi = QListWidgetItem(display)
            _fi.setData(Qt.ItemDataRole.UserRole, display)   # 基础名，不含数字
            self._folder_list.addItem(_fi)
        self._folder_list.setCurrentRow(0)
        self._folder_list.currentTextChanged.connect(self._on_folder_changed)
        self._folder_list.setStyleSheet("background:palette(window); border:none; padding:4px;")

        # AI 分类标签列表
        self._category_list = QListWidget()
        self._category_list.setStyleSheet(
            "background:palette(window); border:none; padding:4px;"
        )
        self._category_list.currentItemChanged.connect(self._on_category_changed)

        # AI 紧急度列表
        self._urgency_list = QListWidget()
        self._urgency_list.setStyleSheet(
            "background:palette(window); border:none; padding:4px;"
        )
        self._urgency_list.currentItemChanged.connect(self._on_urgency_changed)

        left_panel = QWidget()
        left_panel.setStyleSheet("background:palette(window);")
        left_vbox = QVBoxLayout(left_panel)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.setSpacing(0)

        folder_header = QLabel("📁 文件夹")
        folder_header.setStyleSheet(
            "padding:5px 10px; font-weight:bold; font-size:11px; "
            "border-bottom:1px solid palette(mid); background:palette(button);"
        )
        left_vbox.addWidget(folder_header)
        left_vbox.addWidget(self._folder_list)

        category_header = QLabel("🏷️ AI 分类")
        category_header.setStyleSheet(
            "padding:5px 10px; font-weight:bold; font-size:11px; "
            "border-top:1px solid palette(mid); border-bottom:1px solid palette(mid);"
            "background:palette(button);"
        )
        left_vbox.addWidget(category_header)
        left_vbox.addWidget(self._category_list)

        urgency_header = QLabel("⚡ 紧急度")
        urgency_header.setStyleSheet(
            "padding:5px 10px; font-weight:bold; font-size:11px; "
            "border-top:1px solid palette(mid); border-bottom:1px solid palette(mid);"
            "background:palette(button);"
        )
        left_vbox.addWidget(urgency_header)
        left_vbox.addWidget(self._urgency_list)

        splitter.addWidget(left_panel)

        # Left2：邮件列表
        self._email_list = QListWidget()
        self._email_list.setStyleSheet("background:palette(base); border:none;")
        self._email_list.setItemDelegate(EmailListDelegate(self._email_list))
        _email_panel = QWidget()
        _email_panel.setStyleSheet("background:palette(base);")
        _ep_vbox = QVBoxLayout(_email_panel)
        _ep_vbox.setContentsMargins(0, 0, 0, 0)
        _ep_vbox.setSpacing(0)
        self._email_list_header = QLabel("📧 邮件列表")
        self._email_list_header.setStyleSheet(
            "padding:5px 10px; font-weight:bold; font-size:11px; "
            "border-bottom:1px solid palette(mid); background:palette(button);"
        )
        _ep_vbox.addWidget(self._email_list_header)

        # 搜索栏（嵌入邮件列表面板内）
        _srch_row = QWidget()
        _srch_row.setStyleSheet("background:palette(button); border-bottom:1px solid palette(mid);")
        _srch_h = QHBoxLayout(_srch_row)
        _srch_h.setContentsMargins(6, 3, 4, 3)
        _srch_h.setSpacing(3)
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("输入关键词搜索邮件…")
        self._search_input.setFixedHeight(22)
        self._search_input.setStyleSheet(
            "border:1px solid palette(mid); border-radius:3px; padding:1px 6px;"
            "background:palette(base); color:palette(text); font-size:12px;"
        )
        self._search_input.returnPressed.connect(self._on_search_submit)
        _srch_h.addWidget(self._search_input, stretch=1)
        # 确认按钮（空文本，tooltip 提示）
        _srch_ok = QPushButton()
        _srch_ok.setFixedSize(22, 22)
        _srch_ok.setToolTip("搜索  (Enter)")
        _srch_ok.setStyleSheet(
            "border:1px solid palette(mid); border-radius:3px; background:palette(midlight);"
            "font-size:10px; "
        )
        _srch_ok.clicked.connect(self._on_search_submit)
        _srch_h.addWidget(_srch_ok)
        # 回退按钮（空文本，tooltip 提示，搜索激活时才显示）
        self._search_clear_btn = QPushButton()
        self._search_clear_btn.setFixedSize(22, 22)
        self._search_clear_btn.setToolTip("返回邮件列表")
        self._search_clear_btn.setStyleSheet(
            "border:1px solid palette(mid); border-radius:3px; background:palette(midlight);"
            "font-size:10px;"
        )
        self._search_clear_btn.setVisible(False)
        self._search_clear_btn.clicked.connect(self._on_search_clear)
        _srch_h.addWidget(self._search_clear_btn)
        # 高级筛选切换按钮
        self._filter_toggle_btn = QPushButton("⚙")
        self._filter_toggle_btn.setFixedSize(22, 22)
        self._filter_toggle_btn.setToolTip("高级筛选")
        self._filter_toggle_btn.setCheckable(True)
        self._filter_toggle_btn.setStyleSheet(
            "QPushButton{border:1px solid palette(mid);border-radius:3px;background:palette(midlight);font-size:11px;}"
            "QPushButton:checked{background:#c5d0f5;border-color:#8899dd;}"
        )
        self._filter_toggle_btn.clicked.connect(self._on_filter_toggle)
        _srch_h.addWidget(self._filter_toggle_btn)
        _ep_vbox.addWidget(_srch_row)

        # 搜索状态提示行
        self._search_hint = QLabel("⏎ 回车搜索  ·  支持主题、正文、AI 摘要关键词")
        self._search_hint.setStyleSheet(
            "font-size:10px;  padding:1px 8px 2px; background:palette(button);"
        )
        _ep_vbox.addWidget(self._search_hint)

        # 高级筛选面板（初始折叠）
        _fp_input_style = (
            "border:1px solid palette(mid); border-radius:3px; padding:1px 4px; font-size:11px;"
        )
        _fp_combo_style = "border:1px solid palette(mid); border-radius:3px; font-size:11px;"
        self._filter_panel = QWidget()
        self._filter_panel.setStyleSheet("background:palette(window); border-bottom:1px solid palette(mid);")
        self._filter_panel.setVisible(False)
        _fp_vbox = QVBoxLayout(self._filter_panel)
        _fp_vbox.setContentsMargins(6, 4, 6, 4)
        _fp_vbox.setSpacing(4)
        # 第一行：发件人 + 日期范围
        _fp_row1 = QHBoxLayout()
        _fp_row1.setSpacing(4)
        _fp_lbl1 = QLabel("发件人:")
        _fp_lbl1.setStyleSheet("font-size:11px;")
        _fp_row1.addWidget(_fp_lbl1)
        self._filter_sender = QLineEdit()
        self._filter_sender.setPlaceholderText("发件人姓名或地址…")
        self._filter_sender.setFixedHeight(22)
        self._filter_sender.setStyleSheet(_fp_input_style)
        _fp_row1.addWidget(self._filter_sender, stretch=2)
        _fp_lbl2 = QLabel("日期:")
        _fp_lbl2.setStyleSheet("font-size:11px;")
        _fp_row1.addWidget(_fp_lbl2)
        self._filter_date_from = QLineEdit()
        self._filter_date_from.setPlaceholderText("从 YYYY-MM-DD")
        self._filter_date_from.setFixedWidth(100)
        self._filter_date_from.setFixedHeight(22)
        self._filter_date_from.setStyleSheet(_fp_input_style)
        _fp_row1.addWidget(self._filter_date_from)
        _fp_lbl3 = QLabel("~")
        _fp_lbl3.setStyleSheet("font-size:11px;")
        _fp_row1.addWidget(_fp_lbl3)
        self._filter_date_to = QLineEdit()
        self._filter_date_to.setPlaceholderText("到 YYYY-MM-DD")
        self._filter_date_to.setFixedWidth(100)
        self._filter_date_to.setFixedHeight(22)
        self._filter_date_to.setStyleSheet(_fp_input_style)
        _fp_row1.addWidget(self._filter_date_to)
        _fp_vbox.addLayout(_fp_row1)
        # 第二行：状态 + 标记 + 应用/重置
        _fp_row2 = QHBoxLayout()
        _fp_row2.setSpacing(4)
        _fp_lbl4 = QLabel("状态:")
        _fp_lbl4.setStyleSheet("font-size:11px;")
        _fp_row2.addWidget(_fp_lbl4)
        self._filter_read_combo = QComboBox()
        self._filter_read_combo.addItems(["全部", "未读", "已读"])
        self._filter_read_combo.setFixedHeight(22)
        self._filter_read_combo.setStyleSheet(_fp_combo_style)
        _fp_row2.addWidget(self._filter_read_combo)
        _fp_lbl5 = QLabel("标记:")
        _fp_lbl5.setStyleSheet("font-size:11px;")
        _fp_row2.addWidget(_fp_lbl5)
        self._filter_flag_combo = QComboBox()
        self._filter_flag_combo.addItems(["全部", "已标记", "未标记"])
        self._filter_flag_combo.setFixedHeight(22)
        self._filter_flag_combo.setStyleSheet(_fp_combo_style)
        _fp_row2.addWidget(self._filter_flag_combo)
        _fp_row2.addStretch()
        _fp_apply = QPushButton("应用")
        _fp_apply.setFixedSize(44, 22)
        _fp_apply.setStyleSheet(
            "QPushButton{background:#5c7cfa;color:#fff;border:none;border-radius:3px;font-size:11px;}"
            "QPushButton:hover{background:#4a67e0;}"
        )
        _fp_apply.clicked.connect(self._on_search_submit)
        _fp_row2.addWidget(_fp_apply)
        _fp_reset = QPushButton("重置")
        _fp_reset.setFixedSize(44, 22)
        _fp_reset.setStyleSheet(
            "QPushButton{background:palette(button);color:palette(button-text);border:1px solid palette(mid);border-radius:3px;font-size:11px;}"
            "QPushButton:hover{background:palette(midlight);}"
        )
        _fp_reset.clicked.connect(self._on_filter_reset)
        _fp_row2.addWidget(_fp_reset)
        _fp_vbox.addLayout(_fp_row2)
        _ep_vbox.addWidget(self._filter_panel)

        _ep_vbox.addWidget(self._email_list, stretch=1)
        splitter.addWidget(_email_panel)

        # Right2：邮件内容（QWebEngineView — 完整浏览器渲染）
        self._content_view = EmailWebView()
        self._content_view.setHtml(
            "<p>选择一封邮件查看内容</p>", QUrl("file:///")
        )
        self._content_view.page().todo_link_clicked.connect(self._on_todo_link_clicked)

        # 回复工具栏（Qt 按钮，直接调用方法，可靠）
        _content_panel = QWidget()
        _cp_vbox = QVBoxLayout(_content_panel)
        _cp_vbox.setContentsMargins(0, 0, 0, 0)
        _cp_vbox.setSpacing(0)

        _action_bar = QWidget()
        _action_bar.setStyleSheet("background:palette(button); border-bottom:1px solid palette(mid);")
        _action_bar.setFixedHeight(32)
        _ab_hbox = QHBoxLayout(_action_bar)
        _ab_hbox.setContentsMargins(8, 0, 8, 0)
        _ab_hbox.setSpacing(4)

        _reply_btn_style = (
            "QPushButton{border:1px solid palette(mid);border-radius:3px;background:palette(button);"
            "color:palette(button-text);font-size:11px;padding:2px 10px;}"
            "QPushButton:hover{background:palette(midlight);}"
            "QPushButton:disabled{color:palette(mid);border-color:palette(mid);background:palette(window);}"
        )
        self._reply_btn     = QPushButton("↩ 回复")
        self._reply_all_btn = QPushButton("↩ 回复全部")
        self._forward_btn   = QPushButton("→ 转发")
        self._reply_btn.clicked.connect(self._on_reply)
        self._reply_all_btn.clicked.connect(self._on_reply_all)
        self._forward_btn.clicked.connect(self._on_forward)
        _ab_hbox.addStretch()
        for _b in (self._reply_btn, self._reply_all_btn, self._forward_btn):
            _b.setStyleSheet(_reply_btn_style)
            _b.setFixedHeight(24)
            _b.setEnabled(False)
            _ab_hbox.addWidget(_b)

        _cp_vbox.addWidget(_action_bar)
        _cp_vbox.addWidget(self._content_view, stretch=1)

        # ── AI 摘要反馈面板（星评分） ──
        self._feedback_widget = QFrame()
        self._feedback_widget.setStyleSheet(
            "QFrame{background:#f5f7ff;border-top:1px solid #c5cae9;}"
        )
        self._feedback_widget.setVisible(False)
        _fb_vbox = QVBoxLayout(self._feedback_widget)
        _fb_vbox.setContentsMargins(14, 8, 14, 10)
        _fb_vbox.setSpacing(6)

        _fb_title = QLabel("对 AI 摘要评分：")
        _fb_title.setStyleSheet("font-size:12px;color:#3a4a9a;font-weight:bold;")
        _fb_vbox.addWidget(_fb_title)

        _fb_star_row = QHBoxLayout()
        _fb_star_row.setSpacing(4)
        self._fb_star_bar = _FbStarBar()
        _fb_star_row.addWidget(self._fb_star_bar)
        _fb_star_row.addStretch()
        _fb_vbox.addLayout(_fb_star_row)

        self._fb_comment_edit = QTextEdit()
        self._fb_comment_edit.setPlaceholderText("填写反馈意见（可选）…")
        self._fb_comment_edit.setFixedHeight(58)
        self._fb_comment_edit.setStyleSheet(
            "font-size:12px;border:1px solid #c5cae9;border-radius:3px;"
        )
        self._fb_comment_edit.setVisible(False)
        _fb_vbox.addWidget(self._fb_comment_edit)

        _fb_submit_btn = QPushButton("提交")
        _fb_submit_btn.setFixedHeight(26)
        _fb_submit_btn.setEnabled(False)
        _fb_submit_btn.setStyleSheet(
            "QPushButton{border:1px solid #9fa8da;border-radius:3px;"
            "background:#e8ecfa;color:#3a4a9a;font-size:11px;padding:2px 14px;}"
            "QPushButton:hover{background:#d0d8f5;}"
            "QPushButton:disabled{color:#aaa;border-color:#ccc;background:#f5f5f5;}"
        )
        _fb_btn_row = QHBoxLayout()
        _fb_btn_row.addStretch()
        _fb_btn_row.addWidget(_fb_submit_btn)
        _fb_vbox.addLayout(_fb_btn_row)

        _cp_vbox.addWidget(self._feedback_widget)

        # 点星 → 显示评论框，激活提交按钮
        self._fb_star_bar.rating_selected.connect(
            lambda _: (
                self._fb_comment_edit.setVisible(True),
                _fb_submit_btn.setEnabled(True),
            )
        )
        _fb_submit_btn.clicked.connect(self._on_feedback_submit)

        splitter.addWidget(_content_panel)

        # Right1：ToDo 面板（上）+ AI 助手聊天面板（下）
        right1_splitter = QSplitter(Qt.Orientation.Vertical)
        right1_splitter.addWidget(self._build_todo_panel())
        # AI 助手面板：带清除按钮的自定义标题行
        _ai_content = self._build_ai_panel()
        _ai_container = QWidget()
        _ai_container.setStyleSheet("background:palette(window);")
        _ai_vbox = QVBoxLayout(_ai_container)
        _ai_vbox.setContentsMargins(0, 0, 0, 0)
        _ai_vbox.setSpacing(0)
        _ai_hdr = QHBoxLayout()
        _ai_hdr.setContentsMargins(0, 0, 0, 0)
        _ai_hdr.setSpacing(0)
        _ai_title = QLabel("🤖 AI 助手")
        _ai_title.setStyleSheet(
            "padding:5px 10px; font-weight:bold; font-size:11px; "
            "border-bottom:1px solid palette(mid); background:palette(button);"
        )
        _ai_clear_btn = QPushButton("🗑")
        _ai_clear_btn.setToolTip("清除聊天记录")
        _ai_clear_btn.setFixedSize(28, 28)
        _ai_clear_btn.setStyleSheet(
            "QPushButton{border:none; border-bottom:1px solid palette(mid);"
            "background:palette(button); font-size:13px; padding:0;}"
            "QPushButton:hover{background:palette(midlight);}"
        )
        _ai_clear_btn.clicked.connect(self._on_clear_chat)
        self._ai_reconnect_btn = QPushButton("🔄")
        self._ai_reconnect_btn.setToolTip("重新连接 AI")
        self._ai_reconnect_btn.setFixedSize(28, 28)
        self._ai_reconnect_btn.setStyleSheet(
            "border:none; border-bottom:1px solid #bfc9da;"
            "background:#e4eaf6; color:#666; font-size:13px; padding:0;"
            "QPushButton:hover{background:#d0d9ef;}"
        )
        self._ai_reconnect_btn.clicked.connect(self._on_ai_reconnect)
        _ai_hdr.addWidget(_ai_title, stretch=1)
        _ai_hdr.addWidget(self._ai_reconnect_btn)
        _ai_hdr.addWidget(_ai_clear_btn)
        _ai_hdr_widget = QWidget()
        _ai_hdr_widget.setLayout(_ai_hdr)
        _ai_vbox.addWidget(_ai_hdr_widget)
        _ai_vbox.addWidget(_ai_content)
        right1_splitter.addWidget(_ai_container)
        right1_splitter.setSizes([350, 250])
        splitter.addWidget(right1_splitter)

        splitter.setSizes([120, 240, 600, 240])

        # 顶部工具栏（独占一行，覆盖所有栏目上方）
        _top_btn_style = (
            "QPushButton{font-size:11px;padding:3px 12px;"
            "border:1px solid palette(mid);border-radius:3px;"
            "background:palette(window);}"
            "QPushButton:pressed{background:palette(midlight);}"
        )
        toolbar = QWidget()
        toolbar.setStyleSheet("background:palette(button); border-bottom:1px solid palette(mid);")
        toolbar.setFixedHeight(32)
        toolbar_hbox = QHBoxLayout(toolbar)
        toolbar_hbox.setContentsMargins(8, 3, 8, 3)
        toolbar_hbox.setSpacing(6)
        compose_btn = QPushButton("✉ 撰写")
        compose_btn.setStyleSheet(_top_btn_style)
        compose_btn.clicked.connect(self._on_compose)
        settings_btn = QPushButton("⚙ 设置")
        settings_btn.setStyleSheet(_top_btn_style)
        settings_btn.clicked.connect(self._on_settings)
        sync_btn = QPushButton("↻ 同步")
        sync_btn.setStyleSheet(_top_btn_style)
        sync_btn.clicked.connect(self._on_manual_sync)
        toolbar_hbox.addWidget(compose_btn)
        toolbar_hbox.addWidget(settings_btn)
        toolbar_hbox.addWidget(sync_btn)
        toolbar_hbox.addStretch()

        central = QWidget()
        central_vbox = QVBoxLayout(central)
        central_vbox.setContentsMargins(0, 0, 0, 0)
        central_vbox.setSpacing(0)
        central_vbox.addWidget(toolbar)
        central_vbox.addWidget(splitter)
        self.setCentralWidget(central)

        # 邮件列表点击 + 右键菜单 + 双击
        self._email_list.currentItemChanged.connect(self._on_email_selected)
        self._email_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._email_list.customContextMenuRequested.connect(self._on_email_context_menu)
        self._email_list.itemDoubleClicked.connect(self._on_email_double_clicked)

        # 状态栏
        self._status_bar = QStatusBar()
        self._status_bar.showMessage("v0.1 — 就绪")
        self.setStatusBar(self._status_bar)

        # 右下角 AI 处理中指示标签（常驻，默认隐藏）
        self._ai_status_label = QLabel()
        self._ai_status_label.setStyleSheet(
            "font-size:11px;padding:0 8px;"
        )
        self._ai_status_label.setVisible(False)
        self._status_bar.addPermanentWidget(self._ai_status_label)

        self._refresh_todo_list()

        # 每 2 分钟自动刷新待办列表（含唤醒打盹任务）
        from PyQt6.QtCore import QTimer as _QTimerTodo
        self._todo_auto_timer = _QTimerTodo(self)
        self._todo_auto_timer.setInterval(2 * 60 * 1000)  # 2 min
        self._todo_auto_timer.timeout.connect(self._refresh_todo_list)
        self._todo_auto_timer.start()

    def _wrap(self, title: str, widget: QWidget, bg: str) -> QWidget:
        """将内容 widget 包裹在带标题的容器中。"""
        container = QWidget()
        container.setStyleSheet(f"background:{bg};")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QLabel(title)
        header.setStyleSheet(
            "padding:5px 10px; font-weight:bold; font-size:11px; "
            "border-bottom:1px solid palette(mid); background:palette(button);"
        )
        layout.addWidget(header)
        layout.addWidget(widget)
        return container

    # ----------------------------------------------------------------
    # SyncService 接入
    # ----------------------------------------------------------------

    def set_sync_service(self, sync_service, account_id: str = None) -> None:
        """连接 SyncService 信号到 UI。"""
        self._sync_service = sync_service
        self._current_account_id = account_id
        sync_service.sync_started.connect(self._on_sync_started)
        sync_service.sync_done.connect(self._on_sync_done)
        sync_service.sync_error.connect(self._on_sync_error)
        sync_service.email_synced.connect(self._on_email_synced)

    def set_ai_service(self, ai_service) -> None:
        """注入 AIService 并连接 email_processed 信号。"""
        self._ai_service = ai_service
        ai_service.processing_started.connect(self._on_ai_processing_started)
        ai_service.email_processed.connect(self._on_ai_email_processed)

    def set_ai_bridge(self, bridge) -> None:
        """注入 OpenClawBridge 实例。"""
        self._ai_bridge = bridge

    # ----------------------------------------------------------------
    # 信号处理
    # ----------------------------------------------------------------

    @pyqtSlot()
    def _on_sync_started(self):
        self._status_bar.showMessage("⏳ 同步中...")

    @pyqtSlot(int)
    def _on_sync_done(self, count: int):
        if count > 0:
            self._status_bar.showMessage(f"✅ 同步完成，{count} 封新邮件")
        else:
            self._status_bar.showMessage("✅ 无新邮件")
        # 同步完成后刷新当前文件夹和分类栏
        self.refresh_email_list(self._current_folder)
        self._refresh_category_list()
        self._refresh_urgency_list()

    @pyqtSlot(str)
    def _on_sync_error(self, msg: str):
        self._status_bar.showMessage(f"❌ 同步失败：{msg}")

    @pyqtSlot(str)
    def _on_email_synced(self, email_id: str):
        # 增量更新：仅在当前文件夹匹配时添加到列表顶部
        if not self._db:
            return
        email = self._db.get_email(email_id)
        if email and email.folder == self._current_folder:
            self._prepend_email_item(email)

    def _on_folder_changed(self, _text: str):
        current = self._folder_list.currentItem()
        if not current:
            return
        # 用 UserRole 取基础名，避免被数字后缀干扰
        display_name = current.data(Qt.ItemDataRole.UserRole) or _text
        if not display_name:
            return
        folder = self._folder_display_map.get(display_name, display_name)
        self._current_folder = folder
        self._current_category = None
        self._current_urgency = None
        # 清除搜索状态
        self._search_active = False
        if self._search_clear_btn:
            self._search_clear_btn.setVisible(False)
        if self._search_input:
            self._search_input.clear()
        if self._email_list_header:
            self._email_list_header.setText("📧 邮件列表")
        if self._search_hint:
            self._search_hint.setText("⏎ 回车搜索  ·  支持主题、正文、AI 摘要关键词")
            self._search_hint.setStyleSheet(
                "font-size:10px;  padding:1px 8px 2px; background:palette(button);"
            )
        # 取消分类栏选中
        self._category_list.blockSignals(True)
        self._category_list.clearSelection()
        self._category_list.setCurrentRow(-1)
        self._category_list.blockSignals(False)
        # 取消紧急度选中
        self._urgency_list.blockSignals(True)
        self._urgency_list.clearSelection()
        self._urgency_list.setCurrentRow(-1)
        self._urgency_list.blockSignals(False)
        # 收起筛选面板
        if hasattr(self, "_filter_panel") and self._filter_panel:
            self._filter_panel.setVisible(False)
        if hasattr(self, "_filter_toggle_btn") and self._filter_toggle_btn:
            self._filter_toggle_btn.setChecked(False)
        self.refresh_email_list(folder)

    def _on_search_submit(self) -> None:
        if not self._db or not self._current_account_id:
            return
        query = (self._search_input.text() if self._search_input else "").strip()

        # 收集筛选条件
        sender = getattr(self, "_filter_sender", None)
        sender = sender.text().strip() if sender else ""
        date_from_str = getattr(self, "_filter_date_from", None)
        date_from_str = date_from_str.text().strip() if date_from_str else ""
        date_to_str = getattr(self, "_filter_date_to", None)
        date_to_str = date_to_str.text().strip() if date_to_str else ""
        read_combo = getattr(self, "_filter_read_combo", None)
        read_sel = read_combo.currentText() if read_combo else "全部"
        flag_combo = getattr(self, "_filter_flag_combo", None)
        flag_sel = flag_combo.currentText() if flag_combo else "全部"

        has_filter = bool(
            sender or date_from_str or date_to_str
            or read_sel != "全部" or flag_sel != "全部"
        )
        if not query and not has_filter:
            return

        # 解析日期
        from datetime import datetime as _dt
        date_from = None
        date_to = None
        if date_from_str:
            try:
                date_from = _dt.fromisoformat(date_from_str)
            except ValueError:
                self._status_bar.showMessage("日期格式错误，请使用 YYYY-MM-DD", 3000)
                return
        if date_to_str:
            try:
                date_to = _dt.fromisoformat(date_to_str).replace(
                    hour=23, minute=59, second=59
                )
            except ValueError:
                self._status_bar.showMessage("日期格式错误，请使用 YYYY-MM-DD", 3000)
                return

        read_status = {"未读": "unread", "已读": "read"}.get(read_sel)
        is_flagged = True if flag_sel == "已标记" else (
            False if flag_sel == "未标记" else None
        )

        results = self._db.search_emails(
            self._current_account_id, query,
            date_from=date_from, date_to=date_to,
            sender=sender or None,
            read_status=read_status,
            is_flagged=is_flagged,
        )

        self._search_active = True
        self._search_clear_btn.setVisible(True)

        # 构建标题摘要
        parts = []
        if query:
            parts.append(f'"{query}"')
        if sender:
            parts.append(f"发件人:{sender}")
        if date_from_str or date_to_str:
            parts.append(f"{date_from_str or '…'}~{date_to_str or '…'}")
        if read_sel != "全部":
            parts.append(read_sel)
        if flag_sel != "全部":
            parts.append(flag_sel)
        summary = "  ".join(parts) if parts else "筛选"

        self._email_list_header.setText(f"🔍 共 {len(results)} 封  {summary}")
        if self._search_hint:
            self._search_hint.setText(f"← 点击右侧按钮返回邮件列表  ·  共 {len(results)} 封")
            self._search_hint.setStyleSheet(
                "font-size:10px; padding:1px 8px 2px; background:palette(button);"
            )
        self._email_list.clear()
        for email in results:
            self._append_email_item(email)
        self._status_bar.showMessage(f"筛选结果：{len(results)} 封", 3000)

    def _on_search_clear(self) -> None:
        self._search_active = False
        if self._search_clear_btn:
            self._search_clear_btn.setVisible(False)
        if self._search_input:
            self._search_input.clear()
        if self._email_list_header:
            self._email_list_header.setText("📧 邮件列表")
        if self._search_hint:
            self._search_hint.setText("⏎ 回车搜索  ·  支持主题、正文、AI 摘要关键词")
            self._search_hint.setStyleSheet(
                "font-size:10px;  padding:1px 8px 2px; background:palette(button);"
            )
        self._on_filter_reset()
        if hasattr(self, "_filter_panel") and self._filter_panel:
            self._filter_panel.setVisible(False)
        if hasattr(self, "_filter_toggle_btn") and self._filter_toggle_btn:
            self._filter_toggle_btn.setChecked(False)
        self.refresh_email_list(self._current_folder)

    def _on_filter_toggle(self) -> None:
        """展开/折叠高级筛选面板。"""
        if hasattr(self, "_filter_panel") and self._filter_panel:
            self._filter_panel.setVisible(not self._filter_panel.isVisible())

    def _on_filter_reset(self) -> None:
        """清空所有筛选条件输入框。"""
        if hasattr(self, "_filter_sender"):
            self._filter_sender.clear()
        if hasattr(self, "_filter_date_from"):
            self._filter_date_from.clear()
        if hasattr(self, "_filter_date_to"):
            self._filter_date_to.clear()
        if hasattr(self, "_filter_read_combo"):
            self._filter_read_combo.setCurrentIndex(0)
        if hasattr(self, "_filter_flag_combo"):
            self._filter_flag_combo.setCurrentIndex(0)

    def _on_category_changed(self, current: QListWidgetItem, _prev):
        if not current:
            return
        cat_key = current.data(Qt.ItemDataRole.UserRole)
        if not cat_key:
            return
        self._current_category = cat_key
        self._current_urgency = None
        # 取消文件夹列表选中
        self._folder_list.blockSignals(True)
        self._folder_list.clearSelection()
        self._folder_list.setCurrentRow(-1)
        self._folder_list.blockSignals(False)
        # 取消紧急度选中
        self._urgency_list.blockSignals(True)
        self._urgency_list.clearSelection()
        self._urgency_list.setCurrentRow(-1)
        self._urgency_list.blockSignals(False)
        self._refresh_email_list_by_category(cat_key)

    @pyqtSlot(str, str)
    @pyqtSlot(str)
    def _on_ai_processing_started(self, email_id: str):
        self._ai_processing_count += 1
        self._ai_status_label.setText(f"🤖 AI 处理中… ({self._ai_processing_count})")
        self._ai_status_label.setVisible(True)

    def _on_ai_email_processed(self, email_id: str, ai_status: str):
        """AI 处理完成后，更新列表中对应邮件项的 AI 数据并刷新分类栏。"""
        if not self._db:
            return
        # 更新列表项的 AI 角色数据
        for i in range(self._email_list.count()):
            item = self._email_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == email_id:
                meta = self._db.get_email_ai_metadata(email_id)
                if meta:
                    item.setData(Qt.ItemDataRole.UserRole + 8,
                                 meta.summary_one_line or "")
                    item.setData(Qt.ItemDataRole.UserRole + 9,
                                 meta.categories or [])
                item.setData(Qt.ItemDataRole.UserRole + 10,
                             ai_status == "failed")
                self._email_list.viewport().update()
                break
        self._refresh_category_list()
        self._refresh_urgency_list()
        self._refresh_todo_list()
        # 更新右下角 AI 处理中指示
        self._ai_processing_count = max(0, self._ai_processing_count - 1)
        if self._ai_processing_count > 0:
            self._ai_status_label.setText(f"🤖 AI 处理中… ({self._ai_processing_count})")
        else:
            self._ai_status_label.setVisible(False)

    def _on_email_selected(self, current: QListWidgetItem, _prev):
        if not current:
            return
        email_id = current.data(Qt.ItemDataRole.UserRole)
        if not email_id or not self._db:
            return
        email = self._db.get_email(email_id)
        if not email:
            return

        self._current_email = email

        # 启用回复工具栏按钮
        for _b in (self._reply_btn, self._reply_all_btn, self._forward_btn):
            _b.setEnabled(True)

        # 打开邮件即标为已读，并刷新列表项视觉
        if email.read_status == "unread":
            self._db.mark_email_read(email_id)
            current.setData(Qt.ItemDataRole.UserRole + 4, False)
            self._email_list.viewport().update()
        from_info = email.from_address or {}
        from_str = f"{from_info.get('name', '')} <{from_info.get('email', '')}>"
        date_str = _to_cst(email.received_at).strftime("%Y-%m-%d %H:%M") if email.received_at else ""
        def _esc(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        import urllib.parse as _up
        _add_email_params = _up.urlencode({
            "email_id": email_id,
            "subject": email.subject or "",
        })
        _add_todo_btn = (
            f"<a href='clawmail-todo://add-email?{_add_email_params}' "
            f"style='display:inline-block;margin-top:6px;font-size:11px;"
            f"text-decoration:none;"
            f"padding:2px 9px;border:1px solid #888;border-radius:3px;"
            f"'>📝 加入待办</a>"
        )
        header_html = (
            f"<div style='font-family:sans-serif;font-size:13px;"
            f"padding:10px 14px;border-bottom:1px solid #888;'>"
            f"<b>{_esc(email.subject or '')}</b><br>"
            f"发件人：{_esc(from_str)}<br>"
            f"时间：{_esc(date_str)}<br>"
            f"{_add_todo_btn}"
            f"</div>"
        )
        # AI 摘要面板（brief + key_points + 分类标签）
        ai_panel_html = ""
        if self._db:
            meta = self._db.get_email_ai_metadata(email_id)
            if meta and meta.ai_status == "processed":
                ai_panel_html = self._build_ai_summary_html(meta)
                # 只对未打过分的邮件显示反馈面板
                with self._db.get_conn() as _fc:
                    _fr = _fc.execute(
                        "SELECT feedback_rating FROM email_ai_metadata WHERE email_id=?",
                        (email_id,),
                    ).fetchone()
                _already_rated = _fr and _fr[0] is not None
                if _already_rated:
                    self._feedback_widget.setVisible(False)
                else:
                    self._feedback_email_id = email_id
                    self._feedback_meta = meta
                    self._fb_star_bar.reset()
                    self._fb_comment_edit.clear()
                    self._fb_comment_edit.setVisible(False)
                    self._feedback_widget.setEnabled(True)
                    self._feedback_widget.setVisible(True)
            else:
                self._feedback_widget.setVisible(False)
                if meta and meta.ai_status == "failed":
                    err_detail = ""
                    if meta.processing_error:
                        err_detail = (
                            f" <span style='color:#aaa'>({_html_mod.escape(meta.processing_error[:80])})</span>"
                        )
                    ai_panel_html = (
                        "<div style='padding:6px 14px;background:#fff8e1;"
                        "border-bottom:1px solid #ffe082;font-size:12px;color:#795548'>"
                        f"⚠️ AI 分析失败，将在下次启动时重试{err_detail}</div>"
                    )
        else:
            self._feedback_widget.setVisible(False)

        if email.body_html:
            html = header_html + ai_panel_html + email.body_html
        elif email.body_text:
            html = (
                header_html + ai_panel_html
                + f"<pre style='padding:14px;white-space:pre-wrap'>{_esc(email.body_text)}</pre>"
            )
        else:
            html = header_html + ai_panel_html + "<p style='padding:14px;'>[无邮件内容]</p>"

        # 附件列表
        attachments = self._db.get_attachments_by_email(email_id) if self._db else []
        if attachments:
            def _fmt_size(n: int) -> str:
                return f"{n // 1024} KB" if n >= 1024 else f"{n} B"
            items = "".join(
                f"<a href='file://{att['storage_path']}' style='margin-right:12px'>"
                f"📎 {_esc(att['filename'])} ({_fmt_size(att['size_bytes'] or 0)})</a>"
                for att in attachments
            )
            html += (
                f"<div style='padding:10px 14px;background:palette(window);"
                f"border-top:1px solid #888;font-size:12px'>"
                f"<b>附件：</b>{items}</div>"
            )

        self._content_view.setHtml(
"<p style='padding:14px'>加载中…</p>", QUrl("file:///")
        )
        asyncio.ensure_future(self._display_email_async(html))

    async def _display_email_async(self, html: str) -> None:
        """注入响应式 CSS，交由 WebEngine 渲染（自动加载外链图片）。"""
        if re.search(r'</head>', html, re.IGNORECASE):
            html = re.sub(
                r'(</head>)', _RESPONSIVE_CSS + r'\1', html, count=1, flags=re.IGNORECASE
            )
        else:
            html = _RESPONSIVE_CSS + html
        self._content_view.setHtml(html, QUrl("file:///"))

    def _on_manual_sync(self):
        """手动触发同步按钮。"""
        if self._sync_service and self._current_account_id:
            accs = self._db.get_all_accounts() if self._db else []
            if accs:
                asyncio.ensure_future(self._sync_service.run_once(accs[0]))

    def _on_feedback_submit(self) -> None:
        """收集星评分反馈，持久化到 DB，并发送给 OpenClaw。"""
        rating = self._fb_star_bar.get_rating()
        if rating == 0 or not self._feedback_email_id:
            return

        email   = self._db.get_email(self._feedback_email_id) if self._db else None
        meta    = self._feedback_meta
        comment = self._fb_comment_edit.toPlainText().strip()

        subject   = (email.subject or "（无主题）") if email else "（未知）"
        body_text = ((email.body_text or "")[:500]) if email else ""
        summary   = (meta.summary_brief or meta.summary_one_line or "") if meta else ""

        lines = [
            "【AI摘要用户评分反馈】",
            f"邮件主题：{subject}",
            f"邮件内容（前500字）：{body_text}",
            "",
            f"AI生成摘要：{summary}",
            "",
            f"用户评分：{rating}/5 星",
        ]
        if comment:
            lines.append(f"反馈意见：{comment}")
        prompt = "\n".join(lines)

        # 持久化评分到 DB
        if self._db:
            try:
                with self._db.get_conn() as conn:
                    conn.execute(
                        "UPDATE email_ai_metadata SET feedback_rating=? WHERE email_id=?",
                        (rating, self._feedback_email_id),
                    )
                    conn.commit()
            except Exception:
                pass

        # 隐藏面板（已评分）
        self._feedback_widget.setVisible(False)

        # 在聊天框显示用户侧摘要（简洁格式）
        star_str = "★" * rating + "☆" * (5 - rating)
        chat_user_text = (
            f"📧 邮件：{subject}\n"
            f"摘要评分：{star_str} ({rating}/5)\n"
            f"反馈意见：{comment or '（无）'}"
        )
        self._append_user_message(chat_user_text)

        if not self._ai_bridge:
            self._append_ai_message("（AI 未连接，评分已保存）")
            self._status_bar.showMessage("✅ 评分已保存", 3000)
            return

        self._show_typing()
        self._input_line.setEnabled(False)
        self._send_btn.setEnabled(False)
        self._status_bar.showMessage("正在提交反馈…", 2000)

        async def _send():
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self._ai_bridge.user_chat(prompt, "feedbackAgent001"),
                )
                self._append_ai_message(response)
                self._status_bar.showMessage("✅ 反馈已提交，感谢！", 3000)
            except Exception as e:
                self._append_ai_message(f"（反馈发送失败：{e}）")
                self._status_bar.showMessage("✅ 评分已保存（发送失败）", 3000)
            finally:
                self._hide_typing()
                self._input_line.setEnabled(True)
                self._send_btn.setEnabled(True)

        asyncio.ensure_future(_send())

    def _on_settings(self):
        """打开设置对话框。"""
        from clawmail.infrastructure.ai.openclawbridge import OpenClawBridge

        current_token = ""
        if self._ai_bridge:
            # openai.OpenAI 将 api_key 存在 client.api_key
            try:
                current_token = self._ai_bridge.client.api_key or ""
            except AttributeError:
                pass

        dlg = QDialog(self)
        dlg.setWindowTitle("设置")
        dlg.setMinimumWidth(420)
        form = QFormLayout(dlg)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)

        token_edit = QLineEdit(current_token)
        token_edit.setEchoMode(QLineEdit.EchoMode.Password)
        token_edit.setPlaceholderText("OpenClaw API Token")

        show_btn = QPushButton("显示")
        show_btn.setFixedWidth(50)
        show_btn.setCheckable(True)

        def _toggle_echo(checked):
            token_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
            show_btn.setText("隐藏" if checked else "显示")

        show_btn.toggled.connect(_toggle_echo)

        token_row = QHBoxLayout()
        token_row.addWidget(token_edit)
        token_row.addWidget(show_btn)
        form.addRow("OpenClaw Token：", token_row)

        # ---- 账户管理 ----
        acct_section = QLabel("账户管理")
        acct_section.setStyleSheet(
            "color:#555; font-weight:bold; font-size:11px; "
            "padding-top:10px; border-top:1px solid #ddd; margin-top:6px;"
        )
        form.addRow(acct_section)

        current_email = self._current_account.email_address if self._current_account else "未登录"
        acct_info = QLabel(f"📧 {current_email}")
        acct_info.setStyleSheet("font-size:12px; color:#333;")
        form.addRow("当前账户：", acct_info)

        all_accs = self._db.get_all_accounts() if self._db else []
        other_accs = [a for a in all_accs if a.id != (self._current_account_id or "")]

        if other_accs:
            switch_combo = QComboBox()
            for a in other_accs:
                switch_combo.addItem(a.email_address, a.id)
            switch_btn = QPushButton("切换到此账户")

            def _on_switch():
                acc_id = switch_combo.currentData()
                dlg.accept()
                self._switch_account(acc_id)

            switch_btn.clicked.connect(_on_switch)
            switch_row = QHBoxLayout()
            switch_row.addWidget(switch_combo, stretch=1)
            switch_row.addWidget(switch_btn)
            form.addRow("切换账户：", switch_row)

        add_acct_btn = QPushButton("➕ 添加新账户")

        def _on_add_acct():
            from clawmail.ui.components.account_setup_dialog import AccountSetupDialog
            setup_dlg = AccountSetupDialog(self._db, self._cred, parent=dlg)
            if setup_dlg.exec():
                dlg.accept()
                self._switch_account(setup_dlg.account.id)

        add_acct_btn.clicked.connect(_on_add_acct)
        form.addRow(add_acct_btn)

        logout_btn = QPushButton("🚪 登出当前账户")
        logout_btn.setStyleSheet("color:#cc2200;")

        def _on_logout():
            if not self._current_account:
                return
            reply = QMessageBox.question(
                dlg, "确认登出",
                f"确定要登出 {current_email} 吗？\n本地邮件数据会保留，下次登录可继续使用。",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            dlg.accept()
            self._switch_account(None)

        logout_btn.clicked.connect(_on_logout)
        form.addRow(logout_btn)

        # ---- 数据管理 ----
        section_label = QLabel("数据管理")
        section_label.setStyleSheet(
            "font-weight:bold; font-size:11px; "
            "padding-top:10px; border-top:1px solid palette(mid); margin-top:6px;"
        )
        form.addRow(section_label)

        att_dir = (self._db.data_dir / "attachments") if self._db else None

        def _calc_size(path) -> int:
            if path and path.exists():
                return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            return 0

        def _fmt_mb(b: int) -> str:
            return f"{b / (1024 * 1024):.1f} MB" if b >= 1024 * 1024 else f"{b // 1024} KB"

        size_label = QLabel(_fmt_mb(_calc_size(att_dir)))
        size_label.setStyleSheet("font-size:11px;")
        form.addRow("缓存大小：", size_label)

        clear_btn = QPushButton("一键清除本地缓存文件")
        clear_btn.setStyleSheet("color:#cc2200;")

        def _on_clear_cache():
            total = _calc_size(att_dir)
            reply = QMessageBox.question(
                dlg, "确认清除",
                f"将删除本地已下载的附件和图片缓存（约 {_fmt_mb(total)}），确定继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            if att_dir and att_dir.exists():
                shutil.rmtree(att_dir)
                att_dir.mkdir(parents=True, exist_ok=True)
            size_label.setText("0 KB")
            QMessageBox.information(dlg, "清除完成", f"已清除 {_fmt_mb(total)} 缓存文件。")

        clear_btn.clicked.connect(_on_clear_cache)
        form.addRow(clear_btn)

        # 邮件数量标签
        email_count = self._db.count_emails(self._current_account_id) if self._db else 0
        email_count_label = QLabel(f"{email_count} 封")
        email_count_label.setStyleSheet("font-size:11px;")
        form.addRow("本地邮件：", email_count_label)

        clear_emails_btn = QPushButton("一键清除本地邮件")
        clear_emails_btn.setStyleSheet("color:#cc2200;")

        def _on_clear_emails():
            count = self._db.count_emails(self._current_account_id) if self._db else 0
            if count == 0:
                QMessageBox.information(dlg, "提示", "本地暂无邮件。")
                return
            reply = QMessageBox.question(
                dlg, "确认清除",
                f"将删除本地 {count} 封邮件（不影响服务器数据），\n"
                "下次同步后将重新从服务器拉取，确定继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            deleted = self._db.delete_all_emails(self._current_account_id) if self._db else 0
            # 清空 UI 列表与内容视图
            self._email_list.clear()
            self._content_view.setHtml(
                "<p>选择一封邮件查看内容</p>", QUrl("file:///")
            )
            email_count_label.setText("0 封")
            QMessageBox.information(dlg, "清除完成", f"已删除 {deleted} 封本地邮件。\n下次同步后将重新从服务器拉取。")

        clear_emails_btn.clicked.connect(_on_clear_emails)
        form.addRow(clear_emails_btn)

        # 待办任务数量标签 + 清除按钮
        task_count = len(self._db.get_tasks_for_todo()) if self._db else 0
        task_count_label = QLabel(f"{task_count} 条")
        task_count_label.setStyleSheet("font-size:11px;")
        form.addRow("待办任务：", task_count_label)

        clear_tasks_btn = QPushButton("一键清除待办列表")
        clear_tasks_btn.setStyleSheet("color:#cc2200;")

        def _on_clear_tasks():
            count = len(self._db.get_tasks_for_todo()) if self._db else 0
            if count == 0:
                QMessageBox.information(dlg, "提示", "待办列表为空。")
                return
            reply = QMessageBox.question(
                dlg, "确认清除",
                f"将删除全部 {count} 条待办任务，此操作不可撤销，确定继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            deleted = self._db.delete_all_tasks() if self._db else 0
            task_count_label.setText("0 条")
            self._refresh_todo_list()
            QMessageBox.information(dlg, "清除完成", f"已删除 {deleted} 条待办任务。")

        clear_tasks_btn.clicked.connect(_on_clear_tasks)
        form.addRow(clear_tasks_btn)

        # ---- AI 助手 ----
        ai_chat_section = QLabel("AI 助手")
        ai_chat_section.setStyleSheet(
            "color:#555; font-weight:bold; font-size:11px; "
            "padding-top:10px; border-top:1px solid #ddd; margin-top:6px;"
        )
        form.addRow(ai_chat_section)

        mode_combo = QComboBox()
        mode_combo.addItem("用户对话 (user_chat)", "user_chat")
        mode_combo.addItem("邮件助手 (mail_chat)", "mail_chat")
        mode_combo.setCurrentIndex(0 if self._ai_chat_mode == "user_chat" else 1)
        form.addRow("聊天模式：", mode_combo)

        # ---- AI 分析 ----
        ai_section_label = QLabel("AI 分析")
        ai_section_label.setStyleSheet(
            "color:#555; font-weight:bold; font-size:11px; "
            "padding-top:10px; border-top:1px solid #ddd; margin-top:6px;"
        )
        form.addRow(ai_section_label)

        _accs = self._db.get_all_accounts() if self._db else []
        if _accs:
            with self._db.get_conn() as _c:
                _inbox_count = _c.execute(
                    "SELECT COUNT(*) FROM emails WHERE account_id=? AND folder='INBOX'",
                    (_accs[0].id,),
                ).fetchone()[0]
        else:
            _inbox_count = 0

        ai_inbox_btn = QPushButton(f"🤖 一键 AI 分析收件箱（{_inbox_count} 封）")

        def _on_ai_all_inbox():
            if not self._ai_bridge:
                QMessageBox.information(
                    dlg, "AI 未连接",
                    "AI 助手当前未连接，请先检查 OpenClaw 服务。",
                )
                return
            if not _accs or not self._ai_service:
                return
            with self._db.get_conn() as conn:
                rows = conn.execute(
                    "SELECT id FROM emails WHERE account_id=? AND folder='INBOX'"
                    " ORDER BY received_at DESC LIMIT 500",
                    (_accs[0].id,),
                ).fetchall()
            ids = [r[0] for r in rows]
            for eid in ids:
                self._ai_service.enqueue(eid)
            dlg.accept()
            self._status_bar.showMessage(
                f"已将 {len(ids)} 封收件箱邮件加入 AI 分析队列…", 5000
            )

        ai_inbox_btn.clicked.connect(_on_ai_all_inbox)
        form.addRow(ai_inbox_btn)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        form.addRow(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        # 保存聊天模式
        new_mode = mode_combo.currentData()
        mode_changed = new_mode != self._ai_chat_mode
        if mode_changed:
            self._ai_chat_mode = new_mode
            self._save_config({"ai_chat_mode": new_mode})

        new_token = token_edit.text().strip()
        if not new_token:
            if mode_changed:
                self._status_bar.showMessage("✅ 设置已保存", 3000)
            return

        # 更新 bridge
        self._ai_bridge = OpenClawBridge(token=new_token)

        # 持久化到 config.json
        self._save_config({"openclaw_token": new_token})
        self._status_bar.showMessage("✅ 设置已保存", 3000)

    # ----------------------------------------------------------------
    # 邮件列表右键菜单
    # ----------------------------------------------------------------

    def _on_email_context_menu(self, pos):
        item = self._email_list.itemAt(pos)
        if not item:
            return
        email_id   = item.data(Qt.ItemDataRole.UserRole)
        is_unread  = item.data(Qt.ItemDataRole.UserRole + 4) or False
        is_pinned  = item.data(Qt.ItemDataRole.UserRole + 5) or False
        is_flagged = item.data(Qt.ItemDataRole.UserRole + 6) or False

        menu = QMenu(self)
        act_unread = menu.addAction("设为未读") if not is_unread else None
        act_pin    = menu.addAction("取消置顶" if is_pinned else "置顶")
        act_flag   = menu.addAction("🚩 取消旗标" if is_flagged else "🚩 旗标")
        menu.addSeparator()
        in_trash = (self._current_folder == "已删除")
        in_draft = (self._current_folder == "草稿箱")
        in_spam  = (self._current_folder == "垃圾邮件")
        act_spam    = menu.addAction("标记为垃圾邮件") if not in_trash and not in_draft and not in_spam else None
        act_unspam  = menu.addAction("移动到收件箱") if in_spam else None
        act_delete  = menu.addAction("彻底删除" if (in_trash or in_draft) else "删除邮件")
        act_restore = menu.addAction("移回收件箱") if in_trash else None
        menu.addSeparator()
        act_reai = menu.addAction("🤖 重新 AI 分析")

        action = menu.exec(self._email_list.mapToGlobal(pos))
        if action is None:
            return
        if act_unread and action == act_unread:
            self._ctx_mark_unread(email_id, item)
        elif action == act_pin:
            self._ctx_toggle_pin(email_id, is_pinned)
        elif action == act_flag:
            self._ctx_toggle_flag(email_id, is_flagged, item)
        elif act_spam and action == act_spam:
            self._ctx_mark_spam(email_id, item)
        elif act_unspam and action == act_unspam:
            self._ctx_restore_email(email_id, item)
        elif action == act_delete:
            if in_trash:
                self._ctx_perm_delete_email(email_id, item)
            elif in_draft:
                self._ctx_delete_draft(email_id, item)
            else:
                self._ctx_delete_email(email_id, item)
        elif act_restore and action == act_restore:
            self._ctx_restore_email(email_id, item)
        elif action == act_reai:
            self._ctx_rerun_ai(email_id)

    def _ctx_mark_unread(self, email_id: str, item: QListWidgetItem):
        self._db.mark_email_read(email_id, read=False)
        item.setData(Qt.ItemDataRole.UserRole + 4, True)
        self._email_list.viewport().update()

    def _ctx_toggle_flag(self, email_id: str, currently_flagged: bool, item: QListWidgetItem):
        new_flagged = not currently_flagged
        self._db.update_email_flag(email_id, new_flagged)
        item.setData(Qt.ItemDataRole.UserRole + 6, new_flagged)
        self._email_list.viewport().update()

    def _ctx_toggle_pin(self, email_id: str, currently_pinned: bool):
        self._db.update_email_pinned(email_id, not currently_pinned)
        self.refresh_email_list(self._current_folder)

    def _ctx_mark_spam(self, email_id: str, item: QListWidgetItem):
        self._db.update_email_folder(email_id, "垃圾邮件")
        self._email_list.takeItem(self._email_list.row(item))
        self._status_bar.showMessage("已标记为垃圾邮件", 3000)

    def _ctx_delete_email(self, email_id: str, item: QListWidgetItem):
        """移入回收站（可恢复）。"""
        self._db.update_email_folder(email_id, "已删除")
        self._email_list.takeItem(self._email_list.row(item))
        self._status_bar.showMessage("已移入回收站", 3000)

    def _ctx_delete_draft(self, email_id: str, item: QListWidgetItem):
        """直接删除草稿（不经回收站）。"""
        self._db.delete_email(email_id)
        self._email_list.takeItem(self._email_list.row(item))
        self._status_bar.showMessage("草稿已删除", 3000)

    def _ctx_perm_delete_email(self, email_id: str, item: QListWidgetItem):
        """从回收站彻底删除（不可恢复），同时异步从 IMAP 服务器删除。"""
        reply = QMessageBox.question(
            self, "确认彻底删除", "彻底删除这封邮件？此操作不可恢复，同时会从邮件服务器删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        # 先读取 IMAP 元信息，再删除本地记录
        email = self._db.get_email(email_id) if self._db else None
        self._db.delete_email(email_id)
        self._email_list.takeItem(self._email_list.row(item))
        self._status_bar.showMessage("邮件已彻底删除", 3000)
        # 异步在服务器所有文件夹中搜索并删除
        if email and email.message_id and self._cred:
            account = self._db.get_account(email.account_id) if self._db else None
            if account:
                asyncio.ensure_future(
                    self._delete_on_server_async(account, email.message_id)
                )

    async def _delete_on_server_async(self, account, message_id: str) -> None:
        """后台协程：遍历 IMAP 服务器所有文件夹，按 Message-ID 搜索并删除邮件。"""
        from clawmail.infrastructure.email_clients.imap_client import ClawIMAPClient
        imap = ClawIMAPClient()
        try:
            password = self._cred.decrypt_credentials(account.credentials_encrypted)
            await imap.connect(account, password)
            await imap.delete_email_by_message_id(message_id)
        except Exception:
            pass
        finally:
            await imap.disconnect()

    def _ctx_restore_email(self, email_id: str, item: QListWidgetItem):
        """将回收站中的邮件移回收件箱。"""
        self._db.update_email_folder(email_id, "INBOX")
        self._email_list.takeItem(self._email_list.row(item))
        self._status_bar.showMessage("已移回收件箱", 3000)

    def _ctx_rerun_ai(self, email_id: str) -> None:
        """对单封邮件手动触发 AI 重新分析。"""
        if not self._ai_bridge or not self._db:
            QMessageBox.information(self, "提示", "AI 服务未连接，请在设置中配置 API Token。")
            return
        email = self._db.get_email(email_id)
        if not email:
            return
        self._status_bar.showMessage(
            f"🤖 正在重新分析：{(email.subject or '')[:30]}…", 0
        )
        asyncio.ensure_future(self._rerun_ai_async(email))

    async def _rerun_ai_async(self, email) -> None:
        """异步执行 AI 分析并更新数据库。"""
        from clawmail.infrastructure.ai.ai_processor import AIProcessor, AIProcessingError
        loop = asyncio.get_event_loop()
        processor = AIProcessor(self._ai_bridge)
        try:
            meta = await loop.run_in_executor(None, processor.process_email, email)
            self._db.update_email_ai_metadata(meta)
            self._on_ai_email_processed(email.id, "processed")
            # 若当前正在查看这封邮件，刷新详情区域
            if self._current_email and self._current_email.id == email.id:
                self._on_email_selected(self._email_list.currentItem(), None)
            self._status_bar.showMessage(
                f"✅ AI 分析完成：{(email.subject or '')[:30]}", 3000
            )
        except AIProcessingError as e:
            self._status_bar.showMessage(f"❌ AI 分析失败：{e}", 4000)

    def _on_email_double_clicked(self, item: QListWidgetItem):
        """双击草稿箱中的邮件，打开 ComposeDialog 继续编辑。"""
        if self._current_folder != "草稿箱":
            return
        email_id = item.data(Qt.ItemDataRole.UserRole)
        email = self._db.get_email(email_id) if self._db else None
        if not email:
            return
        accs = self._db.get_all_accounts() if self._db else []
        if not accs:
            return
        from clawmail.ui.components.compose_dialog import ComposeDialog
        ai_proc = None
        if self._ai_bridge:
            from clawmail.infrastructure.ai.ai_processor import AIProcessor
            ai_proc = AIProcessor(self._ai_bridge)
        # 通过 in_reply_to 字段（存储的是源邮件 DB id）恢复源邮件
        source_email = None
        source_ai_meta = None
        if email.in_reply_to and self._db:
            source_email = self._db.get_email(email.in_reply_to)
            if source_email:
                source_ai_meta = self._db.get_email_ai_metadata(source_email.id)
        to_str = ", ".join(a.get("email", "") for a in (email.to_addresses or []))
        cc_str = ", ".join(a.get("email", "") for a in (email.cc_addresses or []))
        if email.body_html:
            # WebEngine 草稿（回复/转发）：body_html = 回复区内容，body_text = 引用区内容
            dlg = ComposeDialog(
                self._db, self._cred, accs[0],
                initial_to=to_str,
                initial_cc=cc_str,
                initial_subject=email.subject or "",
                initial_reply_html=email.body_html,
                initial_html_quote=email.body_text or "",
                draft_id=email.id,
                ai_processor=ai_proc,
                source_email=source_email,
                ai_metadata=source_ai_meta,
                parent=self,
            )
        else:
            # QTextEdit 草稿（新撰写）：body_text = 正文内容
            dlg = ComposeDialog(
                self._db, self._cred, accs[0],
                initial_to=to_str,
                initial_cc=cc_str,
                initial_subject=email.subject or "",
                initial_body=email.body_text or "",
                draft_id=email.id,
                ai_processor=ai_proc,
                source_email=source_email,
                ai_metadata=source_ai_meta,
                parent=self,
            )
        dlg.exec()
        self.refresh_email_list(self._current_folder)

    def _on_compose(self):
        """打开撰写邮件对话框。"""
        from clawmail.ui.components.compose_dialog import ComposeDialog

        accs = self._db.get_all_accounts() if self._db else []
        if not accs:
            self._status_bar.showMessage("❌ 请先配置邮箱账号", 3000)
            return

        ai_proc = None
        if self._ai_bridge:
            from clawmail.infrastructure.ai.ai_processor import AIProcessor
            ai_proc = AIProcessor(self._ai_bridge)

        dlg = ComposeDialog(self._db, self._cred, accs[0],
                            ai_processor=ai_proc, parent=self)
        dlg.exec()

    def _on_action_link_clicked(self, action: str) -> None:
        """处理邮件详情头部的 clawmail-action:// 快捷操作链接。"""
        if action == "reply":
            self._on_reply()
        elif action == "reply-all":
            self._on_reply_all()
        elif action == "forward":
            self._on_forward()

    def _on_reply(self):
        """回复：预填发件人，主题加 Re:，正文含引用。"""
        from clawmail.ui.components.compose_dialog import ComposeDialog
        email = self._current_email
        if not email or not self._current_account:
            return

        # 读取 AI 元数据（含 reply_stances）
        ai_meta = None
        if self._db:
            ai_meta = self._db.get_email_ai_metadata(email.id)

        # 构造 AIProcessor（若已有 ai_bridge）
        ai_proc = None
        if self._ai_bridge:
            from clawmail.infrastructure.ai.ai_processor import AIProcessor
            ai_proc = AIProcessor(self._ai_bridge)

        from_info = email.from_address or {}
        to_addr = from_info.get("email", "")
        subject = email.subject or ""
        if not subject.lower().startswith("re:"):
            subject = "Re: " + subject
        dlg = ComposeDialog(
            self._db, self._cred, self._current_account,
            initial_to=to_addr, initial_subject=subject,
            initial_body=self._quoted_body(email),
            initial_html_quote=self._quoted_html(email),
            source_email=email,
            ai_metadata=ai_meta,
            ai_processor=ai_proc,
            parent=self,
        )
        dlg.exec()

    def _on_reply_all(self):
        """回复全部：发件人 + 所有收件人（排除自己），主题加 Re:。"""
        from clawmail.ui.components.compose_dialog import ComposeDialog
        email = self._current_email
        if not email or not self._current_account:
            return
        from_info = email.from_address or {}
        my_addr = self._current_account.email_address.lower()
        to_set = {from_info.get("email", "")}
        for d in (email.to_addresses or []):
            addr = d.get("email", "")
            if addr.lower() != my_addr:
                to_set.add(addr)
        cc_set = set()
        for d in (email.cc_addresses or []):
            addr = d.get("email", "")
            if addr.lower() != my_addr:
                cc_set.add(addr)
        subject = email.subject or ""
        if not subject.lower().startswith("re:"):
            subject = "Re: " + subject
        dlg = ComposeDialog(
            self._db, self._cred, self._current_account,
            initial_to=", ".join(filter(None, to_set)),
            initial_cc=", ".join(filter(None, cc_set)),
            initial_subject=subject,
            initial_body=self._quoted_body(email),
            initial_html_quote=self._quoted_html(email),
            parent=self,
        )
        dlg.exec()

    def _on_forward(self):
        """转发：收件人留空，主题加 Fwd:，正文含原文。"""
        from clawmail.ui.components.compose_dialog import ComposeDialog
        email = self._current_email
        if not email or not self._current_account:
            return
        subject = email.subject or ""
        if not subject.lower().startswith("fwd:"):
            subject = "Fwd: " + subject
        dlg = ComposeDialog(
            self._db, self._cred, self._current_account,
            initial_subject=subject,
            initial_body=self._quoted_body(email, is_forward=True),
            initial_html_quote=self._quoted_html(email, is_forward=True),
            parent=self,
        )
        dlg.exec()

    def _quoted_body(self, email, is_forward: bool = False) -> str:
        """生成引用块（163/QQ邮箱风格）：顶部两行空白供用户输入回复内容，分界线后附完整原始邮件。"""
        from_info = email.from_address or {}
        sender_name  = from_info.get("name", "")
        sender_email = from_info.get("email", "")
        from_str = f"{sender_name} <{sender_email}>".strip() if sender_name else sender_email
        date_str = _to_cst(email.received_at).strftime("%Y-%m-%d %H:%M") if email.received_at else ""
        label = "转发邮件" if is_forward else "原始邮件"
        orig = (email.body_text or "").strip()
        return (
            "\n\n"                                          # 两行空白——光标在此，用户直接输入
            "\n\n"
            f"------------------ {label} ------------------\n"
            f"发件人: {from_str}\n"
            f"发送时间: {date_str}\n"
            f"收件人: {self._current_account.email_address if self._current_account else ''}\n"
            f"主题: {email.subject or ''}\n\n"
            + orig
        )

    def _quoted_html(self, email, is_forward: bool = False) -> str:
        """生成 HTML 引用块（轻量分界头 + 原始 HTML 直出，不加包装样式以保留原邮件外观）。"""
        from_info = email.from_address or {}
        sender_name  = from_info.get("name", "")
        sender_email = from_info.get("email", "")
        from_str_esc = _html_mod.escape(
            f"{sender_name} <{sender_email}>".strip() if sender_name else sender_email
        )
        date_str = _to_cst(email.received_at).strftime("%Y-%m-%d %H:%M") if email.received_at else ""
        label = "转发邮件" if is_forward else "原始邮件"
        to_str = _html_mod.escape(self._current_account.email_address if self._current_account else "")

        header_html = (
            "<div style='font-family:sans-serif;font-size:12px;"
            "border-top:1px solid #ccc;padding-top:6px;margin-top:16px'>"
            f"---------- {label} ----------<br>"
            f"发件人: {from_str_esc}<br>"
            f"发送时间: {_html_mod.escape(date_str)}<br>"
            f"收件人: {to_str}<br>"
            f"主题: {_html_mod.escape(email.subject or '')}"
            "</div>"
        )

        # 原始 HTML 直出（去掉外层 <html>/<head>/<body> 标签避免嵌套冲突）
        if email.body_html:
            import re as _re
            orig = _re.sub(r'(?is)<html[^>]*>|</html>|<head[^>]*>.*?</head>|<body[^>]*>|</body>', '', email.body_html)
        elif email.body_text:
            orig = (
                "<pre style='white-space:pre-wrap;font-family:sans-serif;font-size:13px'>"
                + _html_mod.escape(email.body_text)
                + "</pre>"
            )
        else:
            orig = ""

        return header_html + orig

    # ----------------------------------------------------------------
    # AI 摘要 HTML 构建
    # ----------------------------------------------------------------

    _CAT_LABEL = {
        "urgent":        ("紧急",  "#E53935"),
        "pending_reply": ("待回复","#FB8C00"),
        "meeting":       ("会议",  "#1E88E5"),
        "approval":      ("待审批","#8E24AA"),
        "notification":  ("通知",  "#43A047"),
        "subscription":  ("订阅",  "#757575"),
    }

    def _build_ai_summary_html(self, meta) -> str:
        """生成邮件详情顶部的 AI 摘要面板 HTML。"""
        parts = []
        if meta.summary_brief:
            brief_esc = _html_mod.escape(meta.summary_brief).replace("\n", "<br>")
            parts.append(
                f"<div style='margin-bottom:6px;color:#333;font-size:13px'>"
                f"{brief_esc}</div>"
            )
        if meta.summary_key_points:
            items = "".join(
                f"<li style='margin:2px 0'>{_html_mod.escape(p)}</li>"
                for p in meta.summary_key_points
            )
            parts.append(f"<ul style='margin:0 0 6px 16px;padding:0'>{items}</ul>")
        if meta.categories:
            badges = ""
            for cat in meta.categories:
                label, color = self._CAT_LABEL.get(cat, (cat, "#607D8B"))
                badges += (
                    f"<span style='display:inline-block;margin:2px 4px 2px 0;"
                    f"padding:1px 7px;border-radius:10px;"
                    f"background:{color}22;color:{color};"
                    f"font-size:11px;border:1px solid {color}66'>"
                    f"{_html_mod.escape(label)}</span>"
                )
            parts.append(f"<div style='margin-top:2px'>{badges}</div>")

        # 行动项（用户可点击"加入待办"）
        if meta.action_items:
            _PRI_COLORS = {"high": "#E53935", "medium": "#FB8C00", "low": "#43A047"}
            rows = ""
            for idx, item in enumerate(meta.action_items):
                if not isinstance(item, dict):
                    continue
                text = _html_mod.escape(item.get("text") or "")
                if not text:
                    continue
                pri = item.get("priority", "medium")
                pri_color = _PRI_COLORS.get(pri, "#888")
                deadline = item.get("deadline") or ""
                dl_str = (
                    f" <span style='color:#888;font-size:11px'>{_html_mod.escape(deadline)}</span>"
                    if deadline and deadline != "null" else ""
                )
                import urllib.parse as _up
                params = _up.urlencode({
                    "email_id": meta.email_id,
                    "idx": str(idx),
                    "text": item.get("text") or "",
                    "priority": pri,
                    "deadline": deadline if deadline and deadline != "null" else "",
                    "category": item.get("category") or "",
                })
                add_link = (
                    f"<a href='clawmail-todo://add?{params}' "
                    f"style='font-size:11px;text-decoration:none;"
                    f"padding:1px 6px;border:1px solid #888;border-radius:3px;"
                    f"white-space:nowrap'>＋ 加入待办</a>"
                )
                rows += (
                    f"<tr>"
                    f"<td style='padding:3px 6px 3px 0;color:{pri_color};font-size:12px'>"
                    f"{'🔴' if pri=='high' else '🟡' if pri=='medium' else '🟢'}</td>"
                    f"<td style='padding:3px 8px 3px 0;font-size:12px;color:#333'>"
                    f"{text}{dl_str}</td>"
                    f"<td style='padding:3px 0;white-space:nowrap'>{add_link}</td>"
                    f"</tr>"
                )
            if rows:
                parts.append(
                    "<div style='margin-top:6px;border-top:1px solid #c5cae9;padding-top:6px'>"
                    "<div style='font-size:11px;color:#7986cb;font-weight:bold;margin-bottom:4px'>"
                    "📋 AI 检测到的待办</div>"
                    f"<table style='border-collapse:collapse;width:100%'>{rows}</table>"
                    "</div>"
                )

        if not parts:
            return ""
        body = "".join(parts)
        return (
            "<div style='padding:10px 14px;background:palette(button);"
            "border-bottom:1px solid #c5cae9;font-family:sans-serif'>"
            "<div style='font-size:11px;color:#7986cb;font-weight:bold;"
            "margin-bottom:6px'>🤖 AI 分析</div>"
            f"{body}"
            "</div>"
        )

    def _on_todo_link_clicked(self, url_str: str) -> None:
        """处理邮件视图中"加入待办"链接点击。
        clawmail-todo://add?...       — AI 行动项直接加入
        clawmail-todo://add-email?... — 整封邮件加入待办（弹窗让用户确认标题）
        """
        import urllib.parse as _up
        import uuid as _uuid
        from clawmail.domain.models.task import Task as _Task

        try:
            parsed = _up.urlparse(url_str)
            params = dict(_up.parse_qsl(parsed.query))
        except Exception:
            return

        if not self._db:
            return

        command = parsed.netloc  # "add" 或 "add-email"

        if command == "add-email":
            # 整封邮件作为待办：直接以邮件主题为标题加入
            email_id = params.get("email_id", "") or None
            title = params.get("subject", "").strip() or "（来自邮件）"
            task = _Task(
                id=str(_uuid.uuid4()),
                title=title,
                source_email_id=email_id,
                source_type="extracted",
                priority="medium",
            )

        elif command == "add":
            # AI 行动项直接加入
            text = params.get("text", "").strip()
            if not text:
                return
            email_id = params.get("email_id", "") or None
            priority = params.get("priority", "medium")
            deadline_str = params.get("deadline", "")
            category = params.get("category", "").strip() or None
            due_date = None
            due_date_source = None
            if deadline_str:
                try:
                    due_date = datetime.strptime(deadline_str, "%Y-%m-%d")
                    due_date_source = "ai_extracted"
                except ValueError:
                    pass
            task = _Task(
                id=str(_uuid.uuid4()),
                title=text,
                source_email_id=email_id,
                source_type="extracted",
                priority=priority,
                due_date=due_date,
                due_date_source=due_date_source,
                category=category,
            )

        else:
            return

        try:
            self._db.create_task(task)
        except Exception as e:
            QMessageBox.warning(self, "添加失败", str(e))
            return
        self._refresh_todo_list()
        self._status_bar.showMessage(f"✅ 已加入待办：{task.title[:30]}", 2500)

    # ----------------------------------------------------------------
    # 分类栏刷新
    # ----------------------------------------------------------------

    _FIXED_CATEGORY_ORDER = [
        "urgent", "pending_reply", "meeting", "approval",
        "notification", "subscription",
    ]
    _FIXED_LABELS = {
        "urgent":        "🔴 紧急",
        "pending_reply": "🟠 待回复",
        "meeting":       "🔵 会议",
        "approval":      "🟣 待审批",
        "notification":  "🟢 通知",
        "subscription":  "⚫ 订阅",
    }
    _URGENCY_LABELS = {
        "high":   "🔴 高",
        "medium": "🟡 中",
        "low":    "🟢 低",
    }

    def _refresh_category_list(self) -> None:
        """从数据库读取所有分类标签，刷新左侧分类栏。"""
        if not self._db or not self._current_account_id:
            return
        all_cats = self._db.get_all_categories(self._current_account_id)

        self._category_list.blockSignals(True)
        self._category_list.clear()

        # 固定标签（按序，有数据才显示）
        for cat in self._FIXED_CATEGORY_ORDER:
            if cat in all_cats:
                label = self._FIXED_LABELS.get(cat, cat)
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, cat)  # 存原始 key
                self._category_list.addItem(item)

        # 动态项目标签
        for cat in all_cats:
            if cat.startswith("项目:"):
                item = QListWidgetItem(f"📁 {cat}")
                item.setData(Qt.ItemDataRole.UserRole, cat)
                self._category_list.addItem(item)

        self._category_list.blockSignals(False)

    def _refresh_email_list_by_category(self, cat_key: str) -> None:
        """按 AI 分类标签（原始 key，如 'urgent'）筛选并展示邮件列表。"""
        self._email_list.clear()
        if not self._db or not self._current_account_id:
            return
        emails = self._db.get_emails_by_category(
            self._current_account_id, cat_key, limit=100
        )
        for email in emails:
            self._append_email_item(email)

    def _refresh_urgency_list(self) -> None:
        """从数据库读取各紧急度邮件数，刷新左侧紧急度栏。"""
        if not self._db or not self._current_account_id:
            return
        counts = self._db.get_urgency_counts(self._current_account_id)
        self._urgency_list.blockSignals(True)
        self._urgency_list.clear()
        for key in ("high", "medium", "low"):
            if key in counts:
                item = QListWidgetItem(self._URGENCY_LABELS[key])
                item.setData(Qt.ItemDataRole.UserRole, key)
                self._urgency_list.addItem(item)
        self._urgency_list.blockSignals(False)

    def _on_urgency_changed(self, current: QListWidgetItem, _prev) -> None:
        if not current:
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        if not key:
            return
        self._current_urgency = key
        # 取消文件夹和分类的选中
        self._folder_list.blockSignals(True)
        self._folder_list.clearSelection()
        self._folder_list.setCurrentRow(-1)
        self._folder_list.blockSignals(False)
        self._category_list.blockSignals(True)
        self._category_list.clearSelection()
        self._category_list.setCurrentRow(-1)
        self._category_list.blockSignals(False)
        self._current_category = None
        self._refresh_email_list_by_urgency(key)

    def _refresh_email_list_by_urgency(self, urgency_key: str) -> None:
        """按紧急度筛选并展示邮件列表。"""
        self._email_list.clear()
        if not self._db or not self._current_account_id:
            return
        emails = self._db.get_emails_by_urgency(
            self._current_account_id, urgency_key, limit=100
        )
        for email in emails:
            self._append_email_item(email)

    # ----------------------------------------------------------------
    # 配置文件读写
    # ----------------------------------------------------------------

    def _config_path(self):
        if self._db:
            return self._db.data_dir / "config.json"
        return None

    def _save_config(self, data: dict) -> None:
        path = self._config_path()
        if not path:
            return
        existing = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except Exception:
                pass
        existing.update(data)
        path.write_text(json.dumps(existing, ensure_ascii=False, indent=2))

    def _load_config(self) -> dict:
        path = self._config_path()
        if path and path.exists():
            try:
                return json.loads(path.read_text())
            except Exception:
                pass
        return {}


    # ----------------------------------------------------------------
    # 邮件列表刷新
    # ----------------------------------------------------------------

    def refresh_email_list(self, folder: str) -> None:
        """从数据库重新加载并填充邮件列表。"""
        self._email_list.clear()
        if not self._db or not self._current_account_id:
            return
        emails = self._db.get_emails_by_folder(
            self._current_account_id, folder, limit=100
        )
        for email in emails:
            self._append_email_item(email)
        self._refresh_folder_counts()

    def _refresh_folder_counts(self) -> None:
        """在文件夹名称旁更新数字标注：收件箱显示 (未读/总数)，其余显示 (总数)。"""
        if not self._db or not self._current_account_id:
            return
        try:
            with self._db.get_conn() as conn:
                total_rows = conn.execute(
                    "SELECT folder, COUNT(*) FROM emails"
                    " WHERE account_id=? GROUP BY folder",
                    (self._current_account_id,),
                ).fetchall()
                unread_rows = conn.execute(
                    "SELECT folder, COUNT(*) FROM emails"
                    " WHERE account_id=? AND read_status='unread' GROUP BY folder",
                    (self._current_account_id,),
                ).fetchall()
        except Exception:
            return

        total_map  = {r[0]: r[1] for r in total_rows}
        unread_map = {r[0]: r[1] for r in unread_rows}

        self._folder_list.blockSignals(True)
        for i in range(self._folder_list.count()):
            item = self._folder_list.item(i)
            base = item.data(Qt.ItemDataRole.UserRole)
            if not base:
                continue
            db_folder = self._folder_display_map.get(base, base)
            total  = total_map.get(db_folder, 0)
            unread = unread_map.get(db_folder, 0)
            if db_folder == "INBOX" and unread > 0:
                item.setText(f"{base}  ({unread}/{total})")
            else:
                item.setText(f"{base}  ({total})")
        self._folder_list.blockSignals(False)

    def _prepend_email_item(self, email) -> None:
        """将邮件插入列表顶部（增量更新用）。"""
        item = self._make_email_item(email)
        self._email_list.insertItem(0, item)

    def _append_email_item(self, email) -> None:
        item = self._make_email_item(email)
        self._email_list.addItem(item)

    def _make_email_item(self, email) -> QListWidgetItem:
        is_draft = (self._current_folder == "草稿箱")

        if is_draft and email.to_addresses:
            # 草稿箱：显示"致: 收件人"
            first_to = email.to_addresses[0]
            to_name = (first_to.get("name") or first_to.get("email") or "").strip()
            sender = f"致: {to_name}" if to_name else "致: (未填)"
        else:
            from_info = email.from_address or {}
            name = (from_info.get("name") or "").strip()
            addr = (from_info.get("email") or "").strip()
            if name and addr:
                sender = f"{name} <{addr}>"
            elif addr:
                sender = addr
            else:
                sender = "未知"

        subject = email.subject or "(无主题)"
        time_str = (
            _to_cst(email.received_at).strftime("%Y-%m-%d %H:%M")
            if email.received_at else ""
        )
        is_unread = (email.read_status == "unread")

        # AI 元数据
        ai_one_line = ""
        ai_categories: list = []
        ai_failed = False
        if self._db:
            meta = self._db.get_email_ai_metadata(email.id)
            if meta:
                ai_one_line = meta.summary_one_line or ""
                ai_categories = meta.categories or []
                ai_failed = (meta.ai_status == "failed")

        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole,      email.id)
        item.setData(Qt.ItemDataRole.UserRole + 1,  sender)
        item.setData(Qt.ItemDataRole.UserRole + 2,  subject)
        item.setData(Qt.ItemDataRole.UserRole + 3,  time_str)
        item.setData(Qt.ItemDataRole.UserRole + 4,  is_unread)
        item.setData(Qt.ItemDataRole.UserRole + 5,  getattr(email, "pinned", False))
        item.setData(Qt.ItemDataRole.UserRole + 6,  email.flag_status == "flagged")
        item.setData(Qt.ItemDataRole.UserRole + 7,  is_draft)
        item.setData(Qt.ItemDataRole.UserRole + 8,  ai_one_line)
        item.setData(Qt.ItemDataRole.UserRole + 9,  ai_categories)
        item.setData(Qt.ItemDataRole.UserRole + 10, ai_failed)
        return item

    def set_current_account(self, account_id: str) -> None:
        """设置当前账号并加载邮件列表。"""
        self._current_account_id = account_id
        if self._db:
            accs = self._db.get_all_accounts()
            self._current_account = next((a for a in accs if a.id == account_id), None)
        self.refresh_email_list(self._current_folder)
        self._refresh_category_list()
        self._refresh_urgency_list()
        self._refresh_todo_list()

    def _switch_account(self, account_id: Optional[str]) -> None:
        """停止当前服务，切换到目标账户并重启服务。account_id=None 表示登出。"""
        if self._sync_service:
            self._sync_service.stop()
        if self._ai_service:
            self._ai_service.stop()

        if account_id is None:
            self._current_account_id = None
            self._current_account = None
            self._email_list.clear()
            self._content_view.setHtml(
                "<p style='color:#888'>请在设置中登录账户</p>", QUrl("file:///")
            )
            self._refresh_todo_list()
            self._status_bar.showMessage("已登出", 3000)

            from clawmail.ui.components.account_setup_dialog import AccountSetupDialog
            setup_dlg = AccountSetupDialog(self._db, self._cred, parent=self)
            if setup_dlg.exec():
                self._switch_account(setup_dlg.account.id)
            return

        self.set_current_account(account_id)

        from clawmail.services.sync_service import SyncService
        from clawmail.infrastructure.ai.ai_processor import AIProcessor
        from clawmail.services.ai_service import AIService

        account = self._current_account
        if not account:
            return

        sync_svc = SyncService(self._db, self._cred)
        self.set_sync_service(sync_svc, account_id=account.id)

        ai_processor = AIProcessor(self._ai_bridge) if self._ai_bridge else None
        if ai_processor:
            ai_svc = AIService(self._db, ai_processor, move_callback=sync_svc.move_email)
            self.set_ai_service(ai_svc)
            sync_svc.email_synced.connect(ai_svc.enqueue)
            asyncio.ensure_future(ai_svc.start(account_id=account.id))

        asyncio.ensure_future(sync_svc.start(account))
        self._save_config({"last_account_id": account.id})
        self._status_bar.showMessage(f"已切换到 {account.email_address}", 3000)

    # ----------------------------------------------------------------
    # ToDo 面板
    # ----------------------------------------------------------------

    def _build_todo_panel(self) -> QWidget:
        """构建 ToDo 面板：分组任务列表 + 快速添加输入框。"""
        container = QWidget()
        container.setStyleSheet("background:palette(window);")
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        _todo_hdr_row = QHBoxLayout()
        _todo_hdr_row.setContentsMargins(0, 0, 0, 0)
        _todo_hdr_row.setSpacing(0)
        _todo_hdr_label = QLabel("📝 待办事项")
        _todo_hdr_label.setStyleSheet(
            "padding:5px 10px; font-weight:bold; font-size:11px; "
            "border-bottom:1px solid palette(mid); background:palette(button);"
        )
        _todo_refresh_btn = QPushButton("↻")
        _todo_refresh_btn.setToolTip("刷新待办列表")
        _todo_refresh_btn.setFixedSize(28, 28)
        _todo_refresh_btn.setStyleSheet(
            "QPushButton{border:none; border-bottom:1px solid palette(mid);"
            "background:palette(button); font-size:15px; padding:0;}"
            "QPushButton:hover{background:palette(midlight);}"
        )
        _todo_refresh_btn.clicked.connect(self._refresh_todo_list)
        _todo_hdr_row.addWidget(_todo_hdr_label, stretch=1)
        _todo_hdr_row.addWidget(_todo_refresh_btn)
        _todo_hdr_widget = QWidget()
        _todo_hdr_widget.setLayout(_todo_hdr_row)
        vbox.addWidget(_todo_hdr_widget)

        _input_style = "border:1px solid palette(mid); border-radius:3px; padding:2px 6px;"
        _btn_style = (
            "QPushButton{border:1px solid palette(mid);border-radius:3px;background:palette(base);}"
            "QPushButton:hover{background:palette(midlight);}"
        )

        # ── 搜索 + 筛选 + 排序行 ──
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(6, 4, 6, 2)
        toolbar.setSpacing(4)
        self._todo_search_input = QLineEdit()
        self._todo_search_input.setPlaceholderText("🔍 搜索…")
        self._todo_search_input.setStyleSheet(_input_style)
        self._todo_search_input.textChanged.connect(self._refresh_todo_list)
        toolbar.addWidget(self._todo_search_input, stretch=2)
        self._todo_filter_cat = QComboBox()
        self._todo_filter_cat.addItems(["全部", "工作", "生活", "学习", "个人"])
        self._todo_filter_cat.currentTextChanged.connect(self._refresh_todo_list)
        toolbar.addWidget(self._todo_filter_cat, stretch=1)
        self._todo_sort_combo = QComboBox()
        self._todo_sort_combo.addItems(["分组顺序", "优先级", "截止日期"])
        self._todo_sort_combo.currentTextChanged.connect(self._refresh_todo_list)
        toolbar.addWidget(self._todo_sort_combo, stretch=1)
        vbox.addLayout(toolbar)

        self._todo_list = QListWidget()
        self._todo_list.setStyleSheet("border:none; background:palette(window);")
        self._todo_list.itemChanged.connect(self._on_todo_item_clicked)
        self._todo_list.itemDoubleClicked.connect(self._on_todo_item_double_clicked)
        self._todo_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._todo_list.customContextMenuRequested.connect(self._on_todo_context_menu)
        vbox.addWidget(self._todo_list, stretch=1)

        # 第一行：任务标题
        title_row = QHBoxLayout()
        title_row.setContentsMargins(6, 4, 6, 0)
        title_row.setSpacing(4)
        self._todo_add_input = QLineEdit()
        self._todo_add_input.setPlaceholderText("添加任务…")
        self._todo_add_input.setStyleSheet(_input_style)
        self._todo_add_input.returnPressed.connect(self._on_todo_add)
        title_row.addWidget(self._todo_add_input)
        vbox.addLayout(title_row)

        # 第二行：截止日期 + 优先级 + 分类 + 确认按钮
        date_row = QHBoxLayout()
        date_row.setContentsMargins(6, 2, 6, 4)
        date_row.setSpacing(4)
        _NO_DATE = QDate(2000, 1, 1)
        self._todo_add_date = QDateEdit()
        self._todo_add_date.setCalendarPopup(True)
        self._todo_add_date.setDisplayFormat("yyyy/MM/dd")
        self._todo_add_date.setMinimumDate(_NO_DATE)
        self._todo_add_date.setDate(QDate.currentDate())
        self._todo_add_date.setSpecialValueText("截止日期(可选)")
        self._todo_add_date.setStyleSheet(_input_style)
        date_row.addWidget(self._todo_add_date, stretch=1)
        self._todo_add_pri = QComboBox()
        self._todo_add_pri.addItems(["🔴 高", "🟡 中", "🟢 低"])
        self._todo_add_pri.setCurrentIndex(1)   # 默认"中"
        self._todo_add_pri.setStyleSheet(_input_style)
        date_row.addWidget(self._todo_add_pri)
        self._todo_add_cat = QComboBox()
        self._todo_add_cat.addItems(["工作", "生活", "学习", "个人", "其他"])
        self._todo_add_cat.setStyleSheet(_input_style)
        date_row.addWidget(self._todo_add_cat)
        add_btn = QPushButton("＋ 添加")
        add_btn.setStyleSheet(_btn_style)
        add_btn.clicked.connect(self._on_todo_add)
        date_row.addWidget(add_btn)
        vbox.addLayout(date_row)

        return container

    def _refresh_todo_list(self, *_args) -> None:
        """重新从数据库读取任务并按分组渲染列表。"""
        if self._todo_list is None or self._db is None:
            return
        from datetime import date
        today = date.today()
        try:
            tasks = self._db.get_tasks_for_todo()
        except Exception as e:
            self._todo_list.clear()
            err_item = QListWidgetItem(f"⚠ 加载失败: {e}")
            err_item.setFlags(Qt.ItemFlag.NoItemFlags)
            err_item.setForeground(QColor("#cc0000"))
            self._todo_list.addItem(err_item)
            return

        # 搜索 / 筛选 / 排序条件
        search_text = (
            self._todo_search_input.text().strip().lower()
            if self._todo_search_input else ""
        )
        filter_cat = (
            self._todo_filter_cat.currentText()
            if self._todo_filter_cat else "全部"
        )
        sort_key = (
            self._todo_sort_combo.currentText()
            if self._todo_sort_combo else "分组顺序"
        )

        def _matches(t) -> bool:
            if search_text and search_text not in t.title.lower():
                return False
            if filter_cat != "全部":
                if (t.category or "其他") != filter_cat:
                    return False
            return True

        tasks = [t for t in tasks if _matches(t)]

        _PRI = {"high": 0, "medium": 1, "low": 2}
        if sort_key == "优先级":
            tasks.sort(key=lambda t: _PRI.get(t.priority, 9))
        elif sort_key == "截止日期":
            tasks.sort(key=lambda t: (t.due_date is None, t.due_date or datetime.min))

        # 使用 guard 防止 itemChanged 递归触发
        if getattr(self, "_todo_refreshing", False):
            return
        self._todo_refreshing = True
        try:
            self._todo_list.clear()

            groups = {"今日": [], "未来": [], "已完成": []}
            for t in tasks:
                if t.status == "completed":
                    groups["已完成"].append(t)
                elif t.due_date and t.due_date.date() <= today:
                    groups["今日"].append(t)
                else:
                    groups["未来"].append(t)

            if not any(groups.values()):
                empty_item = QListWidgetItem("（暂无任务）")
                empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
                empty_item.setForeground(QColor("#aaaaaa"))
                self._todo_list.addItem(empty_item)
                return

            for group_name, group_tasks in groups.items():
                if not group_tasks:
                    continue
                header_item = QListWidgetItem(f"── {group_name} ({len(group_tasks)}) ──")
                header_item.setFlags(Qt.ItemFlag.NoItemFlags)
                header_item.setForeground(QColor("#888888"))
                f = header_item.font()
                f.setBold(True)
                header_item.setFont(f)
                self._todo_list.addItem(header_item)
                for task in group_tasks:
                    self._add_todo_item(task, group_name)
        finally:
            self._todo_refreshing = False

    def _add_todo_item(self, task, group_name: str) -> None:
        pri_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(task.priority, "⚪")
        due_str = (
            f" [{task.due_date.strftime('%m/%d')}]" if task.due_date else ""
        )
        cat_badge = f" [{task.category}]" if task.category else ""
        email_icon = " 📧" if task.source_email_id else ""
        title = f"{pri_icon} {task.title}{cat_badge}{email_icon}{due_str}"
        item = QListWidgetItem(title)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsUserCheckable
        )
        item.setData(Qt.ItemDataRole.UserRole, task.id)
        item.setData(Qt.ItemDataRole.UserRole + 1, task.source_email_id)
        item.setData(Qt.ItemDataRole.UserRole + 2, group_name)
        if task.status == "completed":
            item.setForeground(QColor("#aaaaaa"))
            f = item.font()
            f.setStrikeOut(True)
            item.setFont(f)
        item.setCheckState(
            Qt.CheckState.Checked
            if task.status == "completed"
            else Qt.CheckState.Unchecked
        )
        self._todo_list.addItem(item)

    def _on_todo_item_clicked(self, item: QListWidgetItem) -> None:
        task_id = item.data(Qt.ItemDataRole.UserRole)
        if not task_id or not self._db:
            return
        checked = item.checkState() == Qt.CheckState.Checked
        new_status = "completed" if checked else "pending"
        self._db.update_task_status(task_id, new_status)
        self._refresh_todo_list()

    def _on_todo_item_double_clicked(self, item: QListWidgetItem) -> None:
        """双击任务条目 → 若为邮件来源任务，跳转到源邮件。"""
        email_id = item.data(Qt.ItemDataRole.UserRole + 1)
        if not email_id:
            return
        self._jump_to_source_email(email_id)

    def _jump_to_source_email(self, email_id: str) -> None:
        """切换到源邮件所在文件夹并选中该邮件。"""
        if not self._db:
            return
        email = self._db.get_email(email_id)
        if not email:
            QMessageBox.information(self, "提示", "源邮件已被删除或不存在")
            return

        # 切换文件夹并清除分类筛选
        self._current_folder = email.folder
        self._current_category = None

        # 同步左侧文件夹列表选中（避免触发 _on_folder_changed 再次刷新）
        display_rev = {v: k for k, v in self._folder_display_map.items()}
        display_name = display_rev.get(email.folder, email.folder)
        self._folder_list.blockSignals(True)
        for i in range(self._folder_list.count()):
            _it = self._folder_list.item(i)
            _base = _it.data(Qt.ItemDataRole.UserRole) or _it.text()
            if _base == display_name:
                self._folder_list.setCurrentRow(i)
                break
        self._folder_list.blockSignals(False)

        # 重新加载邮件列表，确保目标邮件在其中
        self.refresh_email_list(email.folder)

        # 定位并选中目标邮件
        for i in range(self._email_list.count()):
            it = self._email_list.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole) == email_id:
                self._email_list.setCurrentItem(it)
                self._email_list.scrollToItem(it)
                return

    def _navigate_to_email(self, email_id: str) -> None:
        for i in range(self._email_list.count()):
            it = self._email_list.item(i)
            if it and it.data(Qt.ItemDataRole.UserRole) == email_id:
                self._email_list.setCurrentItem(it)
                return

    def _on_todo_add(self) -> None:
        import uuid as _uuid
        from clawmail.domain.models.task import Task as _Task
        text = self._todo_add_input.text().strip()
        if not text:
            return
        if self._db is None:
            QMessageBox.warning(self, "错误", "数据库未初始化")
            return
        # 读取截止日期（特殊值 2000/01/01 表示"无期限"）
        due_date = None
        due_date_source = None
        if self._todo_add_date is not None:
            qdate = self._todo_add_date.date()
            if qdate != QDate(2000, 1, 1):
                due_date = datetime(qdate.year(), qdate.month(), qdate.day())
                due_date_source = "user_set"

        category = None
        if self._todo_add_cat is not None:
            cat_text = self._todo_add_cat.currentText()
            category = cat_text if cat_text != "其他" else None

        _PRI_MAP = {"🔴 高": "high", "🟡 中": "medium", "🟢 低": "low"}
        priority = "medium"
        if self._todo_add_pri is not None:
            priority = _PRI_MAP.get(self._todo_add_pri.currentText(), "medium")

        task = _Task(
            id=str(_uuid.uuid4()),
            title=text,
            source_type="manual",
            priority=priority,
            due_date=due_date,
            due_date_source=due_date_source,
            category=category,
        )
        try:
            self._db.create_task(task)
        except Exception as e:
            QMessageBox.warning(self, "添加失败", str(e))
            return
        self._todo_add_input.clear()
        if self._todo_add_date is not None:
            self._todo_add_date.setDate(QDate(2000, 1, 1))
        self._refresh_todo_list()

    def _on_todo_context_menu(self, pos) -> None:
        item = self._todo_list.itemAt(pos)
        if not item:
            return
        task_id = item.data(Qt.ItemDataRole.UserRole)
        if not task_id or not self._db:
            return
        menu = QMenu(self)
        edit_act   = menu.addAction("✏ 编辑任务")
        cancel_act = menu.addAction("取消任务")
        menu.addSeparator()
        ai_exec_act = menu.addAction("🤖 由AI助手执行")
        act = menu.exec(self._todo_list.mapToGlobal(pos))
        if act == edit_act:
            self._on_todo_edit(task_id)
        elif act == cancel_act:
            self._db.update_task_status(task_id, "cancelled")
            self._refresh_todo_list()
        elif act == ai_exec_act:
            self._ctx_ai_execute_task(task_id)

    def _ctx_ai_execute_task(self, task_id: str) -> None:
        """将待办任务（含关联邮件）打包发送给 AI 助手执行。"""
        if not self._db:
            return
        task = self._db.get_task(task_id)
        if not task:
            return

        _PRI = {"high": "高", "medium": "中", "low": "低"}
        priority_label = _PRI.get(task.priority or "medium", task.priority or "中")
        due_str = task.due_date.strftime("%Y/%m/%d") if task.due_date else "无"

        lines = [
            "【待办任务执行请求】",
            f"标题：{task.title}",
            f"优先级：{priority_label}",
            f"截止日期：{due_str}",
            f"描述：{task.description or '（无）'}",
            f"分类：{task.category or '（无）'}",
        ]

        if task.source_email_id:
            email = self._db.get_email(task.source_email_id)
            if email:
                from_info = email.from_address or {}
                sender = f"{from_info.get('name', '')} <{from_info.get('email', '')}>".strip(" <>")
                date_str = _to_cst(email.received_at).strftime("%Y/%m/%d %H:%M") if email.received_at else "未知"
                ai_meta = self._db.get_email_ai_metadata(task.source_email_id)
                summary = (ai_meta.summary_one_line or ai_meta.summary_brief or "") if ai_meta else ""
                if not summary:
                    summary = (email.body_text or "")[:300]
                lines += [
                    "",
                    "【关联邮件】",
                    f"发件人：{sender}",
                    f"主题：{email.subject or '（无主题）'}",
                    f"日期：{date_str}",
                    f"摘要：{summary}",
                ]

        lines += ["", "请帮我处理此任务，给出具体操作步骤或直接完成。"]
        prompt = "\n".join(lines)

        if not self._ai_bridge:
            QMessageBox.information(self, "AI 未连接", "AI 助手当前未连接，请先检查 OpenClaw 服务。")
            return

        self._input_line.setText(prompt)
        self._on_send()

    def _on_todo_edit(self, task_id: str) -> None:
        """弹出编辑对话框，允许修改任务的标题、优先级、截止日期、描述、分类。"""
        task = self._db.get_task(task_id)
        if task is None:
            QMessageBox.warning(self, "错误", "任务不存在")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("编辑任务")
        dlg.setMinimumWidth(360)
        form = QFormLayout(dlg)
        form.setSpacing(8)
        form.setContentsMargins(12, 12, 12, 8)

        _input_style = "border:1px solid palette(mid); border-radius:3px; padding:2px 6px;"

        # 标题
        title_edit = QLineEdit(task.title or "")
        title_edit.setStyleSheet(_input_style)
        form.addRow("标题：", title_edit)

        # 优先级
        pri_combo = QComboBox()
        pri_combo.addItems(["🔴 高", "🟡 中", "🟢 低"])
        _PRI_IDX = {"high": 0, "medium": 1, "low": 2}
        pri_combo.setCurrentIndex(_PRI_IDX.get(task.priority or "medium", 1))
        pri_combo.setStyleSheet(_input_style)
        form.addRow("优先级：", pri_combo)

        # 截止日期
        _NO_DATE = QDate(2000, 1, 1)
        due_edit = QDateEdit()
        due_edit.setCalendarPopup(True)
        due_edit.setDisplayFormat("yyyy/MM/dd")
        due_edit.setMinimumDate(_NO_DATE)
        due_edit.setSpecialValueText("无截止日期")
        due_edit.setStyleSheet(_input_style)
        if task.due_date:
            d = task.due_date
            due_edit.setDate(QDate(d.year, d.month, d.day))
        else:
            due_edit.setDate(_NO_DATE)
        form.addRow("截止日期：", due_edit)

        # 描述
        desc_edit = QTextEdit()
        desc_edit.setPlaceholderText("（可选）补充说明…")
        desc_edit.setPlainText(task.description or "")
        desc_edit.setFixedHeight(70)
        desc_edit.setStyleSheet(_input_style)
        form.addRow("描述：", desc_edit)

        # 分类
        cat_combo = QComboBox()
        cats = ["工作", "生活", "学习", "个人", "其他"]
        cat_combo.addItems(cats)
        cur_cat = task.category or "其他"
        idx = cats.index(cur_cat) if cur_cat in cats else len(cats) - 1
        cat_combo.setCurrentIndex(idx)
        cat_combo.setStyleSheet(_input_style)
        form.addRow("分类：", cat_combo)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        form.addRow(btn_box)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        _PRI_MAP = {"🔴 高": "high", "🟡 中": "medium", "🟢 低": "low"}
        new_priority = _PRI_MAP.get(pri_combo.currentText(), "medium")
        new_title    = title_edit.text().strip() or task.title
        qdate        = due_edit.date()
        new_due      = (
            datetime(qdate.year(), qdate.month(), qdate.day())
            if qdate != _NO_DATE else None
        )
        new_desc     = desc_edit.toPlainText().strip() or None
        cat_text     = cat_combo.currentText()
        new_cat      = cat_text if cat_text != "其他" else None

        try:
            self._db.update_task(task_id, new_title, new_priority,
                                 new_due, new_desc, new_cat)
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))
            return
        self._refresh_todo_list()

    # ----------------------------------------------------------------
    # AI 助手聊天面板
    # ----------------------------------------------------------------

    def _build_ai_panel(self) -> QWidget:
        """构建 AI 聊天面板：消息历史 + 输入框 + 发送按钮。"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # 消息历史区
        self._chat_history = QTextBrowser()
        self._chat_history.setOpenExternalLinks(False)
        self._chat_history.setStyleSheet(
            "background:palette(base); border:1px solid palette(mid); border-radius:4px;"
        )
        layout.addWidget(self._chat_history, stretch=1)

        # 打字动画指示器（AI 回复时显示）
        self._typing_label = QLabel()
        self._typing_label.setStyleSheet(
            "font-size:11px; padding:1px 4px; font-style:italic;"
        )
        self._typing_label.setVisible(False)
        layout.addWidget(self._typing_label)

        # 输入行
        input_row = QHBoxLayout()
        input_row.setSpacing(4)
        self._input_line = QLineEdit()
        self._input_line.setPlaceholderText("输入消息，按回车发送…")
        self._input_line.returnPressed.connect(self._on_send)
        self._send_btn = QPushButton("发送")
        self._send_btn.setFixedWidth(52)
        self._send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self._input_line)
        input_row.addWidget(self._send_btn)
        layout.addLayout(input_row)

        return container

    def _on_ai_reconnect(self) -> None:
        """取消当前挂起的 AI 请求，立即恢复输入状态。"""
        task = self._pending_ai_task
        if task and not task.done():
            self._ai_request_cancelled = True
            task.cancel()
            self._pending_ai_task = None
            self._hide_typing()
            self._append_ai_message("⏹ Interrupted.")
            self._send_btn.setEnabled(True)
            self._input_line.setEnabled(True)
            self._input_line.setFocus()
            self._status_bar.showMessage("⏹ 已中断 AI 响应", 2000)

    def _on_clear_chat(self) -> None:
        """清除聊天历史（界面 + AI 桥接侧记忆）。"""
        self._chat_history.clear()
        bridge = getattr(self, "_ai_bridge", None)
        if bridge and hasattr(bridge, "clear_history"):
            try:
                bridge.clear_history()
            except Exception:
                pass

    def _on_send(self) -> None:
        text = self._input_line.text().strip()
        if not text:
            return
        self._input_line.clear()

        self._append_user_message(text)

        if not self._ai_bridge:
            self._append_ai_message("[AI 助手未连接，请检查 OpenClaw 服务。]")
            return

        # 禁用输入，防止重复发送
        self._input_line.setEnabled(False)
        self._send_btn.setEnabled(False)
        self._show_typing()

        self._pending_ai_task = asyncio.ensure_future(self._send_message_async(text))

    async def _send_message_async(self, text: str) -> None:
        self._ai_request_cancelled = False
        loop = asyncio.get_event_loop()
        try:
            if self._ai_chat_mode == "mail_chat":
                response = await loop.run_in_executor(
                    None, self._ai_bridge.process_email, text
                )
            else:
                response = await loop.run_in_executor(
                    None, self._ai_bridge.user_chat, text
                )
            if not self._ai_request_cancelled:
                self._append_ai_message(response)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if not self._ai_request_cancelled:
                self._append_ai_message(f"[请求失败：{e}]")
        finally:
            if not self._ai_request_cancelled:
                self._hide_typing()
                self._send_btn.setEnabled(True)
                self._input_line.setEnabled(True)
                self._input_line.setFocus()

    _TYPING_FRAMES = [
        "🤖  Claw 正在思考 ·",
        "🤖  Claw 正在思考 · ·",
        "🤖  Claw 正在思考 · · ·",
        "🤖  Claw 正在思考 · ·",
    ]

    def _show_typing(self) -> None:
        """显示打字动画指示器。"""
        if not self._typing_label:
            return
        self._typing_frame = 0
        self._typing_label.setText(self._TYPING_FRAMES[0])
        self._typing_label.setVisible(True)
        # 滚动到底部让指示器可见
        sb = self._chat_history.verticalScrollBar()
        sb.setValue(sb.maximum())
        from PyQt6.QtCore import QTimer as _QTimer
        self._typing_timer = _QTimer(self)
        self._typing_timer.setInterval(380)
        self._typing_timer.timeout.connect(self._on_typing_tick)
        self._typing_timer.start()

    def _on_typing_tick(self) -> None:
        self._typing_frame = (self._typing_frame + 1) % len(self._TYPING_FRAMES)
        if self._typing_label:
            self._typing_label.setText(self._TYPING_FRAMES[self._typing_frame])

    def _hide_typing(self) -> None:
        """停止并隐藏打字动画。"""
        if self._typing_timer:
            self._typing_timer.stop()
            self._typing_timer = None
        if self._typing_label:
            self._typing_label.setVisible(False)

    def _append_user_message(self, text: str) -> None:
        safe = _html_mod.escape(text).replace("\n", "<br>")
        time_str = datetime.now().strftime("%H:%M")
        self._chat_history.append(
            "<table width='100%' cellspacing='0' cellpadding='0' style='margin:3px 0'>"
            "<tr>"
            "  <td width='20%'></td>"
            f"  <td align='right'><font size='1' color='#aaaaaa'>{time_str}</font></td>"
            "</tr>"
            "<tr>"
            "  <td width='20%'></td>"
            "  <td bgcolor='#4a90d9' style='padding:6px 10px'>"
            f"    <font color='#ffffff'>{safe}</font>"
            "  </td>"
            "</tr>"
            "</table>"
        )

    def _append_ai_message(self, text: str) -> None:
        safe = _html_mod.escape(text).replace("\n", "<br>")
        time_str = datetime.now().strftime("%H:%M")
        self._chat_history.append(
            "<table width='100%' cellspacing='0' cellpadding='0' style='margin:3px 0'>"
            "<tr>"
            f"  <td align='left'><font size='1' color='#aaaaaa'>{time_str}</font></td>"
            "  <td width='20%'></td>"
            "</tr>"
            "<tr>"
            "  <td bgcolor='#e8e8e8' style='padding:6px 10px'>"
            f"    <font color='#222222'>{safe}</font>"
            "  </td>"
            "  <td width='20%'></td>"
            "</tr>"
            "</table>"
        )
