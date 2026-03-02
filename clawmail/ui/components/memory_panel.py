"""
MemoryPanel — AI 记忆面板（独立窗口，紧贴主窗口右侧）。

树形折叠分组 + 右侧详情面板。
"""

import json
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QSplitter, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from clawmail.ui.theme import get_theme

# ── 常量 ──────────────────────────────────────────────────────────

MEMORY_TYPE_LABELS = {
    "sender_importance": "发件人重要性",
    "urgency_signal": "紧急信号",
    "automated_content": "自动化内容",
    "summary_preference": "摘要偏好",
    "response_pattern": "回复风格",
    "contact": "联系人关系",
    "contact_direction": "信息流向",
    "contact_comm_pattern": "沟通模式",
    "project_state": "项目状态",
}

MEMORY_GROUPS = [
    ("📊 重要性评分", {"sender_importance", "urgency_signal", "automated_content"}),
    ("👤 联系人画像", {"contact", "contact_direction", "contact_comm_pattern"}),
    ("✍ 回复风格", {"response_pattern"}),
    ("📝 摘要偏好", {"summary_preference"}),
    ("📁 项目状态", {"project_state"}),
]

# memory_content 中要隐藏的元字段
_META_KEYS = {"_source", "extracted_date", "last_updated"}


def _format_content(content) -> str:
    """将 memory_content 格式化为可读文本，跳过元字段。"""
    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return str(content) if content else ""
    lines = []
    for k, v in content.items():
        if k in _META_KEYS:
            continue
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        lines.append(f"{k}: {v}")
    return "\n".join(lines)


def _short_summary(content) -> str:
    """提取 content 的一行简短摘要（用于树节点显示）。"""
    if isinstance(content, str):
        return content[:50]
    if not isinstance(content, dict):
        return str(content)[:50] if content else ""
    # 优先取有意义的字段
    for key in ("defect", "pattern", "preference", "issue", "signal",
                "sender_name", "relationship", "description"):
        v = content.get(key)
        if v and isinstance(v, str):
            return v[:50]
    # fallback: 第一个非元字段的字符串值
    for k, v in content.items():
        if k in _META_KEYS:
            continue
        if isinstance(v, str) and v.strip():
            return v[:50]
    return ""


class MemoryPanel(QDialog):
    """AI 记忆面板，以独立窗口紧贴主窗口右侧。"""

    closed = pyqtSignal()
    clean_requested = pyqtSignal()

    _RADIUS = 10  # 窗口圆角半径

    def __init__(self, parent: QWidget, db, account_id: str = ""):
        super().__init__(
            parent,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._db = db
        self._account_id = account_id
        self.setMinimumSize(480, 400)
        self.resize(500, parent.height() if parent else 600)
        self._setup_ui()

    # ── UI 构建 ──

    def _setup_ui(self) -> None:
        # 不设 QDialog 背景，由 paintEvent 绘制圆角背景
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)  # 1px 为边框留空
        root.setSpacing(0)

        # ── 标题栏 ──
        r = self._RADIUS
        title_bar = QWidget()
        title_bar.setStyleSheet(
            f"QWidget {{ background: palette(button);"
            f"border-bottom: 1px solid palette(mid);"
            f"border-top-left-radius: {r}px;"
            f"border-top-right-radius: {r}px; }}"
        )
        title_bar.setFixedHeight(34)
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(10, 0, 6, 0)
        tb_layout.setSpacing(6)

        self._title_label = QLabel("🧠 AI 记忆 (0)")
        font = self._title_label.font()
        font.setBold(True)
        font.setPointSize(10)
        self._title_label.setFont(font)
        tb_layout.addWidget(self._title_label)
        tb_layout.addStretch()

        clean_btn = QPushButton("清洗")
        clean_btn.setFixedHeight(22)
        clean_btn.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 2px 10px;"
            "border: 1px solid palette(mid); border-radius: 3px;"
            "background: palette(window); }"
            "QPushButton:hover { background: palette(midlight); }"
        )
        clean_btn.setToolTip("调用 AI 分析并清洗重复/矛盾记忆")
        clean_btn.clicked.connect(self.clean_requested.emit)
        self._clean_btn = clean_btn
        tb_layout.addWidget(clean_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            "QPushButton { border: none; font-size: 14px; }"
            "QPushButton:hover { color: #cc2200; }"
        )
        close_btn.clicked.connect(self.close)
        tb_layout.addWidget(close_btn)

        root.addWidget(title_bar)

        # ── 主体：树形列表 | 详情面板 ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background: palette(mid); width: 1px; }")

        # 左侧：树形列表
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(20)
        self._tree.setRootIsDecorated(True)
        self._tree.setStyleSheet(
            "QTreeWidget { font-size: 12px; background: palette(base);"
            "border: none; }"
            "QTreeWidget::item { padding: 3px 0; }"
            "QTreeWidget::item:selected { background: palette(highlight);"
            "color: palette(highlighted-text); }"
        )
        self._tree.currentItemChanged.connect(self._on_item_selected)
        splitter.addWidget(self._tree)

        # 右侧：详情面板
        detail_container = QWidget()
        detail_container.setStyleSheet(
            "QWidget#detailContainer { background: palette(base);"
            "border: 1px solid palette(mid); border-radius: 4px; }"
        )
        detail_container.setObjectName("detailContainer")
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(10, 10, 10, 10)
        detail_layout.setSpacing(6)

        # 类型
        self._detail_type = QLabel("")
        type_font = self._detail_type.font()
        type_font.setBold(True)
        type_font.setPointSize(10)
        self._detail_type.setFont(type_font)
        detail_layout.addWidget(self._detail_type)

        # 键
        self._detail_key = QLabel("")
        self._detail_key.setStyleSheet("font-size: 12px; color: palette(text);")
        self._detail_key.setWordWrap(True)
        detail_layout.addWidget(self._detail_key)

        # 置信度行
        conf_row = QHBoxLayout()
        conf_row.setSpacing(8)
        self._conf_bar = QProgressBar()
        self._conf_bar.setRange(0, 100)
        self._conf_bar.setFixedHeight(10)
        self._conf_bar.setTextVisible(False)
        self._conf_bar.setStyleSheet(
            "QProgressBar { background: palette(mid); border: none; border-radius: 4px; }"
            "QProgressBar::chunk { background: palette(highlight); border-radius: 4px; }"
        )
        conf_row.addWidget(self._conf_bar, stretch=1)
        self._conf_label = QLabel("")
        self._conf_label.setStyleSheet("font-size: 11px; min-width: 36px;")
        conf_row.addWidget(self._conf_label)
        detail_layout.addLayout(conf_row)

        # 元信息
        self._detail_meta = QLabel("")
        self._detail_meta.setStyleSheet("font-size: 11px; color: palette(placeholderText);")
        detail_layout.addWidget(self._detail_meta)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: palette(mid);")
        detail_layout.addWidget(sep)

        # 内容区
        content_label = QLabel("内容")
        content_label.setStyleSheet("font-size: 11px; color: palette(placeholderText);")
        detail_layout.addWidget(content_label)

        self._detail_content = QTextEdit()
        self._detail_content.setReadOnly(True)
        self._detail_content.setStyleSheet(
            "QTextEdit { font-size: 12px; background: transparent;"
            "border: none; }"
        )
        detail_layout.addWidget(self._detail_content, stretch=1)

        # 占位提示（未选中时）
        self._detail_placeholder = QLabel("选择一条记忆查看详情")
        self._detail_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail_placeholder.setStyleSheet(
            "font-size: 12px; color: palette(placeholderText);"
        )

        # 用 stacked 方式切换占位/详情
        self._detail_widgets = [
            self._detail_type, self._detail_key, self._conf_bar,
            self._conf_label, self._detail_meta, sep, content_label,
            self._detail_content,
        ]
        detail_layout.addWidget(self._detail_placeholder)
        self._show_detail(False)

        splitter.addWidget(detail_container)
        splitter.setSizes([200, 280])

        body = QVBoxLayout()
        body.setContentsMargins(6, 6, 6, 6)
        body.setSpacing(6)
        body.addWidget(splitter, stretch=1)

        # ── 底部操作栏 ──
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        del_btn = QPushButton("🗑 删除选中")
        del_btn.setStyleSheet(
            "QPushButton { font-size: 11px; color: #cc2200; padding: 3px 10px;"
            "border: 1px solid palette(mid); border-radius: 3px;"
            "background: palette(window); }"
            "QPushButton:hover { background: palette(midlight); }"
        )
        del_btn.clicked.connect(self._on_delete)
        bottom.addWidget(del_btn)
        bottom.addStretch()
        body.addLayout(bottom)

        root.addLayout(body, stretch=1)

    # ── 显示/隐藏详情 ──

    def _show_detail(self, show: bool) -> None:
        for w in self._detail_widgets:
            w.setVisible(show)
        self._detail_placeholder.setVisible(not show)

    # ── 数据填充 ──

    def set_account_id(self, account_id: str) -> None:
        self._account_id = account_id

    def populate(self) -> None:
        """重新读取数据库并填充树形列表。"""
        self._tree.clear()
        self._show_detail(False)
        self._detail_content.clear()

        if not self._db or not self._account_id:
            self._title_label.setText("🧠 AI 记忆 (0)")
            return

        memories = self._db.get_all_memories(self._account_id)
        self._title_label.setText(f"🧠 AI 记忆 ({len(memories)})")

        # 分离 skill_defect 和普通记忆
        defect_mems = []
        normal_mems = []
        for m in memories:
            content = m.memory_content if isinstance(m.memory_content, dict) else {}
            if content.get("_source") == "skill_defect":
                defect_mems.append(m)
            else:
                normal_mems.append(m)

        # 普通记忆按分组显示
        for grp_label, grp_types in MEMORY_GROUPS:
            grp_mems = [m for m in normal_mems if m.memory_type in grp_types]
            if not grp_mems:
                continue
            self._add_group_node(grp_label, grp_mems)

        # Skill 缺陷单独分组
        if defect_mems:
            self._add_group_node("🐛 Skill 缺陷", defect_mems, is_defect=True)

        if not normal_mems and not defect_mems:
            empty = QTreeWidgetItem(self._tree)
            empty.setText(0, "暂无 AI 记忆。使用邮件并给出反馈后，AI 会逐渐学习你的偏好。")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)

    def _add_group_node(self, label: str, mems: list, is_defect: bool = False) -> None:
        """添加一个分组节点及其子条目。"""
        group_node = QTreeWidgetItem(self._tree)
        group_node.setText(0, f"{label} ({len(mems)})")
        group_font = group_node.font(0)
        group_font.setBold(True)
        group_node.setFont(0, group_font)
        group_node.setFlags(Qt.ItemFlag.ItemIsEnabled)
        group_node.setExpanded(True)
        if is_defect:
            group_node.setForeground(0, QColor("#cc6600"))

        for m in mems:
            child = QTreeWidgetItem(group_node)
            key_display = m.memory_key or "全局"
            summary = _short_summary(m.memory_content)
            if summary:
                text = f"{key_display}: {summary}"
            else:
                text = key_display
            if len(text) > 60:
                text = text[:58] + "…"
            child.setText(0, text)
            child.setToolTip(0, key_display)
            child.setData(0, Qt.ItemDataRole.UserRole, m)
            if is_defect:
                child.setForeground(0, QColor("#cc6600"))

    # ── 选中事件 ──

    def _on_item_selected(self, current: QTreeWidgetItem, _prev) -> None:
        if not current:
            self._show_detail(False)
            return
        mem = current.data(0, Qt.ItemDataRole.UserRole)
        if mem is None:
            # 分组节点，无数据
            self._show_detail(False)
            return
        self._show_detail(True)

        # 类型 + 来源标签
        type_name = MEMORY_TYPE_LABELS.get(mem.memory_type, mem.memory_type)
        content = mem.memory_content if isinstance(mem.memory_content, dict) else {}
        is_defect = content.get("_source") == "skill_defect"
        if is_defect:
            group_name = "Skill 缺陷"
        else:
            group_name = next(
                (g.split(" ", 1)[-1] for g, ts in MEMORY_GROUPS if mem.memory_type in ts),
                "",
            )
        self._detail_type.setText(
            f"{type_name}" + (f"  ·  {group_name}" if group_name else "")
        )
        self._detail_type.setStyleSheet(
            f"color: #cc6600; font-size: 10pt; font-weight: bold;" if is_defect
            else "font-size: 10pt; font-weight: bold;"
        )

        # 键
        self._detail_key.setText(f"键: {mem.memory_key or '全局'}")

        # 置信度
        pct = int(mem.confidence_score * 100)
        self._conf_bar.setValue(pct)
        self._conf_label.setText(f"{pct}%")

        # 元信息
        created = mem.created_at.strftime("%Y-%m-%d") if mem.created_at else "?"
        self._detail_meta.setText(
            f"证据: {mem.evidence_count} 次  ·  创建: {created}"
        )

        # 内容
        self._detail_content.setPlainText(_format_content(mem.memory_content))

    # ── 删除 ──

    def _on_delete(self) -> None:
        item = self._tree.currentItem()
        if not item:
            return
        mem = item.data(0, Qt.ItemDataRole.UserRole)
        if mem is None:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            "确定删除这条记忆？删除后 AI 将不再使用该偏好。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._db.delete_memory(mem.id)
        self.populate()

    # ── 清洗按钮状态 ──

    def set_cleaning(self, is_cleaning: bool) -> None:
        self._clean_btn.setText("清洗中…" if is_cleaning else "清洗")
        self._clean_btn.setEnabled(not is_cleaning)

    # ── 圆角绘制 ──

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self._RADIUS
        path = QPainterPath()
        path.addRoundedRect(0.5, 0.5, self.width() - 1, self.height() - 1, r, r)
        pal = self.palette()
        painter.fillPath(path, pal.color(QPalette.ColorRole.Window))
        painter.setPen(pal.color(QPalette.ColorRole.Mid))
        painter.drawPath(path)

    # ── 关闭事件 ──

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)
