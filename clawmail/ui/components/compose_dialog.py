"""
ComposeDialog — 撰写邮件对话框
支持收件人、抄送、主题、纯文本正文，异步 SMTP 发送。
回复/转发时传入 initial_html_quote，发送 multipart/alternative（HTML + 纯文本降级）。
草稿支持：保存草稿按钮、关闭时询问、60 秒定时自动保存。
AI 辅助拟稿：回复时传入 source_email / ai_metadata / ai_processor，显示分步引导面板。
"""

import asyncio
import os
import uuid as _uuid
from datetime import datetime

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtWidgets import (
    QButtonGroup, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from clawmail.infrastructure.email_clients.smtp_client import ClawSMTPClient, SMTPSendError
from clawmail.ui.theme import get_theme


class ComposeDialog(QDialog):
    """
    撰写并发送邮件的模态对话框。
    :param db:           ClawDB 实例，用于读取账号信息及保存草稿
    :param cred_manager: CredentialManager，用于解密授权码
    :param account:      当前发件账号（Account 对象）
    :param draft_id:     编辑已有草稿时传入草稿 email.id，新建时传 None
    :param source_email: 被回复的原邮件（Email 对象），用于 AI 辅助拟稿
    :param ai_metadata:  原邮件的 AI 元数据（EmailAIMetadata），含 reply_stances
    :param ai_processor: AIProcessor 实例，用于生成草稿
    """

    def __init__(self, db, cred_manager, account,
                 initial_to=None, initial_cc=None,
                 initial_subject=None, initial_body=None,
                 initial_html_quote=None,
                 initial_reply_html=None,
                 draft_id=None,
                 source_email=None,
                 ai_metadata=None,
                 ai_processor=None,
                 initial_attachments=None,
                 parent=None):
        super().__init__(parent)
        self._db = db
        self._cred = cred_manager
        self._account = account
        self._initial_to         = initial_to or ""
        self._initial_cc         = initial_cc or ""
        self._initial_subject    = initial_subject or ""
        self._initial_body       = initial_body or ""
        self._initial_html_quote = initial_html_quote or ""
        self._initial_reply_html = initial_reply_html or ""
        self._smtp = ClawSMTPClient()
        self._draft_id = draft_id

        # AI 辅助拟稿
        self._source_email    = source_email
        self._ai_metadata     = ai_metadata
        self._ai_processor    = ai_processor
        self._selected_stance = None
        self._selected_tone   = None

        # 隐式反馈追踪：邮件生成（reply_draft + generate_email）
        self._ai_draft_text: str | None = None       # AI 生成的原始正文
        self._ai_draft_source: str | None = None     # "reply_draft" 或 "generate_email"
        self._ai_draft_context: dict = {}             # stance, tone, outline 等上下文
        # 隐式反馈追踪：润色
        self._pre_polish_text: str | None = None      # 润色前的正文
        self._polished_text: str | None = None         # AI 润色后的正文
        self._polish_tone: str | None = None           # 润色时选择的风格

        # 附件：文件绝对路径列表（可由 API 预填）
        self._attachments: list = list(initial_attachments or [])

        self.setWindowTitle("撰写邮件")
        self.setMinimumSize(640, 540 if (initial_html_quote or initial_reply_html) else 440)
        self._build_ui()
        if self._attachments:
            self._refresh_attach_ui()

        # 60 秒自动保存定时器
        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setInterval(60_000)
        self._auto_save_timer.timeout.connect(self._on_auto_save)
        self._auto_save_timer.start()

    # ----------------------------------------------------------------
    # UI 构建
    # ----------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(14, 14, 14, 14)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(6)

        _field_style = (
            "border:1px solid palette(mid);border-radius:3px;"
            "padding:3px 6px;background:palette(base);color:palette(text);"
        )
        _std_btn_style = (
            "QPushButton{border:1px solid palette(mid);border-radius:3px;"
            "background:palette(button);color:palette(button-text);padding:4px 14px;}"
            "QPushButton:hover{background:palette(midlight);}"
            "QPushButton:default{border-color:palette(highlight);}"
        )
        self._to_edit = QLineEdit()
        self._to_edit.setPlaceholderText("多个地址用逗号分隔")
        self._to_edit.setStyleSheet(_field_style)
        form.addRow("收件人：", self._to_edit)

        self._cc_edit = QLineEdit()
        self._cc_edit.setPlaceholderText("可留空，多个地址用逗号分隔")
        self._cc_edit.setStyleSheet(_field_style)
        form.addRow("抄送：", self._cc_edit)

        self._subject_edit = QLineEdit()
        self._subject_edit.setStyleSheet(_field_style)
        form.addRow("主题：", self._subject_edit)

        layout.addLayout(form)

        # 附件栏
        self._build_attach_bar(layout)

        if self._initial_html_quote or self._initial_reply_html:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings

            self._compose_view = QWebEngineView()
            self._compose_view.settings().setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptEnabled, True
            )
            self._compose_view.settings().setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            self._compose_view.setHtml(self._build_compose_html(), QUrl("file:///"))
            layout.addWidget(self._compose_view, stretch=1)
        else:
            self._body_edit = QTextEdit()
            self._body_edit.setPlaceholderText("在此输入正文…")
            self._body_edit.setStyleSheet(
                "border:1px solid palette(mid);border-radius:3px;"
                "background:palette(base);color:palette(text);"
            )
            if self._initial_body:
                self._body_edit.setPlainText(self._initial_body)
            layout.addWidget(self._body_edit, stretch=1)

        # AI 润色栏（有 ai_processor 时始终显示）
        if self._ai_processor:
            self._build_polish_bar(layout)

        # AI 辅助拟稿面板（仅回复且有 reply_stances 时显示）
        if (self._source_email and self._ai_metadata
                and self._ai_metadata.reply_stances):
            self._build_ai_draft_panel(layout)

        # 状态提示
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("font-size:11px;")
        layout.addWidget(self._status_label)

        # 按钮行
        self._send_btn = QPushButton("发送")
        self._send_btn.setDefault(True)
        self._send_btn.setStyleSheet(_std_btn_style)
        self._draft_btn = QPushButton("保存草稿")
        self._draft_btn.setStyleSheet(_std_btn_style)
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(_std_btn_style)
        cancel_btn.clicked.connect(self.reject)
        self._send_btn.clicked.connect(self._on_send)
        self._draft_btn.clicked.connect(self._on_save_draft)

        btn_box = QDialogButtonBox()
        btn_box.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)
        btn_box.addButton(self._draft_btn, QDialogButtonBox.ButtonRole.ActionRole)
        btn_box.addButton(self._send_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        layout.addWidget(btn_box)

        if self._initial_to:
            self._to_edit.setText(self._initial_to)
        if self._initial_cc:
            self._cc_edit.setText(self._initial_cc)
        if self._initial_subject:
            self._subject_edit.setText(self._initial_subject)

    # ----------------------------------------------------------------
    # 附件
    # ----------------------------------------------------------------

    def _build_attach_bar(self, layout):
        """附件区：添加按钮 + 文件名标签行（动态显示）。"""
        _attach_style = (
            "QPushButton{border:1px solid palette(mid);border-radius:3px;"
            "background:palette(button);padding:1px 8px;font-size:11px;color:palette(button-text);}"
            "QPushButton:hover{background:palette(midlight);}"
        )
        # 行1：添加附件按钮 + 附件数量提示
        row = QHBoxLayout()
        row.setSpacing(6)
        _add_btn = QPushButton("📎 添加附件")
        _add_btn.setFixedHeight(24)
        _add_btn.setStyleSheet(_attach_style)
        _add_btn.clicked.connect(self._on_add_attachment)
        row.addWidget(_add_btn)
        self._attach_count_label = QLabel("")
        self._attach_count_label.setStyleSheet("font-size:11px;")
        row.addWidget(self._attach_count_label)
        row.addStretch()
        layout.addLayout(row)

        # 行2：文件名 chip 面板（无附件时隐藏）
        self._chips_panel = QWidget()
        self._chips_panel.setVisible(False)
        self._chips_layout = QHBoxLayout(self._chips_panel)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(6)
        layout.addWidget(self._chips_panel)

    def _on_add_attachment(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择附件", "", "所有文件 (*.*)"
        )
        for p in paths:
            if p and p not in self._attachments:
                self._attachments.append(p)
        if paths:
            self._refresh_attach_ui()

    def _remove_attachment(self, path: str):
        if path in self._attachments:
            self._attachments.remove(path)
        self._refresh_attach_ui()

    def _refresh_attach_ui(self):
        """重新渲染附件 chip 列表。"""
        # 清除旧 chip
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._attachments:
            self._chips_panel.setVisible(False)
            self._attach_count_label.setText("")
            return

        for path in self._attachments:
            name = os.path.basename(path)
            display = name if len(name) <= 28 else name[:25] + "…"

            chip = QWidget()
            chip.setStyleSheet(
                "background:palette(button); border:1px solid palette(mid);"
                "border-radius:10px;"
            )
            ch = QHBoxLayout(chip)
            ch.setContentsMargins(7, 2, 5, 2)
            ch.setSpacing(4)

            lbl = QLabel(f"📄 {display}")
            lbl.setStyleSheet(
                "font-size:11px; background:transparent; border:none;"
            )
            lbl.setToolTip(path)

            rm = QPushButton("✕")
            rm.setFixedSize(14, 14)
            rm.setStyleSheet(
                "QPushButton{border:none;background:transparent;"
                "color:#888;font-size:9px;padding:0;}"
                "QPushButton:hover{color:#c00;}"
            )
            rm.clicked.connect(lambda _checked, p=path: self._remove_attachment(p))

            ch.addWidget(lbl)
            ch.addWidget(rm)
            self._chips_layout.addWidget(chip)

        self._chips_layout.addStretch()
        self._chips_panel.setVisible(True)
        n = len(self._attachments)
        self._attach_count_label.setText(f"{n} 个附件")

    # ----------------------------------------------------------------
    # AI 润色栏
    # ----------------------------------------------------------------

    def _build_polish_bar(self, parent_layout):
        bar = QWidget()
        bar.setStyleSheet(
            "background:palette(window);border:1px solid palette(mid);border-radius:5px;"
        )
        vbox = QVBoxLayout(bar)
        vbox.setContentsMargins(10, 6, 10, 6)
        vbox.setSpacing(6)

        # ── 行1：风格选择 + 润色正文 ─────────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(6)

        row1.addWidget(QLabel("✨ AI 工具："))

        self._polish_tone_group = QButtonGroup(self)
        self._polish_tone_group.setExclusive(True)
        self._polish_selected_tone = "礼貌"   # 默认风格
        for t in ["正式", "礼貌", "轻松", "简短"]:
            btn = QPushButton(t)
            btn.setCheckable(True)
            btn.setChecked(t == "礼貌")
            btn.setStyleSheet(self._toggle_btn_style())
            btn.setFixedHeight(26)
            self._polish_tone_group.addButton(btn)
            row1.addWidget(btn)
            btn.clicked.connect(
                lambda checked, tone=t: setattr(self, "_polish_selected_tone", tone)
            )

        row1.addStretch()

        self._polish_btn = QPushButton("✨ 润色正文")
        _ai_btn_disabled = "#3a3a5a" if get_theme().is_dark() else "#aab4d8"
        self._polish_btn.setStyleSheet(
            "QPushButton{background:#4a6cf7;color:#fff;border:none;"
            "border-radius:4px;padding:3px 14px;font-weight:bold;}"
            "QPushButton:hover{background:#3a5ce7;}"
            f"QPushButton:disabled{{background:{_ai_btn_disabled};}}"
        )
        self._polish_btn.setFixedHeight(26)
        self._polish_btn.clicked.connect(self._on_polish)
        row1.addWidget(self._polish_btn)

        vbox.addLayout(row1)

        # ── 行2：大纲输入 + 一键生成 ─────────────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(6)

        self._outline_input = QLineEdit()
        self._outline_input.setPlaceholderText(
            "输入几句话大纲，AI 帮你生成完整邮件…"
        )
        self._outline_input.setStyleSheet(
            "border:1px solid palette(mid);border-radius:3px;"
            "padding:1px 6px;background:palette(base);color:palette(text);"
        )
        self._outline_input.setFixedHeight(26)
        row2.addWidget(self._outline_input)

        self._gen_email_btn = QPushButton("📝 一键生成")
        self._gen_email_btn.setStyleSheet(
            "QPushButton{background:#22a85a;color:#fff;border:none;"
            "border-radius:4px;padding:3px 14px;font-weight:bold;}"
            "QPushButton:hover{background:#1a9050;}"
            f"QPushButton:disabled{{background:{_ai_btn_disabled};}}"
        )
        self._gen_email_btn.setFixedHeight(26)
        self._gen_email_btn.clicked.connect(self._on_generate_email)
        row2.addWidget(self._gen_email_btn)

        vbox.addLayout(row2)

        parent_layout.addWidget(bar)

    def _on_polish(self):
        # 读取当前正文
        if hasattr(self, "_compose_view"):
            self._compose_view.page().runJavaScript(
                "document.getElementById('reply-area').innerText",
                self._on_polish_got_text,
            )
        else:
            self._on_polish_got_text(self._body_edit.toPlainText())

    def _on_polish_got_text(self, text: str):
        if not text or not text.strip():
            QMessageBox.information(self, "提示", "请先输入正文内容再润色。")
            return
        self._polish_btn.setText("润色中…")
        self._polish_btn.setEnabled(False)
        asyncio.ensure_future(self._polish_async(text.strip()))

    async def _polish_async(self, body: str):
        loop = asyncio.get_event_loop()
        try:
            polished = await loop.run_in_executor(
                None,
                self._ai_processor.polish_email,
                body,
                self._polish_selected_tone,
            )
            # 保存润色前后文本用于隐式反馈
            self._pre_polish_text = body
            self._polished_text = polished
            self._polish_tone = self._polish_selected_tone
            self._fill_draft(polished)
        except Exception as e:
            QMessageBox.warning(self, "润色失败", str(e))
        finally:
            self._polish_btn.setText("✨ 润色正文")
            self._polish_btn.setEnabled(True)

    def _on_generate_email(self):
        outline = self._outline_input.text().strip()
        if not outline:
            QMessageBox.information(self, "提示", "请先输入大纲或几句描述，再生成邮件。")
            return
        subject = self._subject_edit.text().strip()
        self._gen_email_btn.setText("生成中…")
        self._gen_email_btn.setEnabled(False)
        asyncio.ensure_future(self._generate_email_async(subject, outline))

    async def _generate_email_async(self, subject: str, outline: str):
        loop = asyncio.get_event_loop()
        try:
            generated = await loop.run_in_executor(
                None,
                self._ai_processor.generate_email,
                subject,
                outline,
                self._polish_selected_tone,
            )
            # 保存 AI 生成正文用于隐式反馈
            self._ai_draft_text = generated
            self._ai_draft_source = "generate_email"
            self._ai_draft_context = {
                "outline": outline,
                "tone": self._polish_selected_tone,
            }
            self._fill_draft(generated)
        except Exception as e:
            QMessageBox.warning(self, "生成失败", str(e))
        finally:
            self._gen_email_btn.setText("📝 一键生成")
            self._gen_email_btn.setEnabled(True)

    # ----------------------------------------------------------------
    # AI 辅助拟稿面板
    # ----------------------------------------------------------------

    @staticmethod
    def _toggle_btn_style() -> str:
        _t = get_theme()
        checked_bg = "#1e3870" if _t.is_dark() else "#4a6cf7"
        return (
            "QPushButton{border:1px solid palette(mid);border-radius:4px;"
            "padding:3px 10px;background:palette(button);color:palette(button-text);}"
            f"QPushButton:checked{{background:{checked_bg};color:#e8f0ff;"
            f"border-color:{checked_bg};}}"
            "QPushButton:hover:!checked{background:palette(midlight);}"
        )

    def _build_ai_draft_panel(self, parent_layout):
        box = QGroupBox("✨ AI 辅助拟稿")
        box.setStyleSheet(
            "QGroupBox{font-weight:bold;border:1px solid palette(mid);"
            "border-radius:6px;margin-top:6px;padding:8px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:10px;"
            "padding:0 4px;}"
        )
        vbox = QVBoxLayout(box)
        vbox.setSpacing(6)

        # ── 步骤1：立场选择 ──────────────────────────────────────
        vbox.addWidget(QLabel("步骤 1   选择回复立场："))
        stance_row = QHBoxLayout()
        stance_row.setSpacing(6)
        self._stance_group = QButtonGroup(self)
        self._stance_group.setExclusive(True)
        for s in self._ai_metadata.reply_stances:
            btn = QPushButton(s)
            btn.setCheckable(True)
            btn.setStyleSheet(self._toggle_btn_style())
            self._stance_group.addButton(btn)
            stance_row.addWidget(btn)
            btn.clicked.connect(
                lambda checked, stance=s: self._on_stance_selected(stance)
            )
        stance_row.addStretch()
        vbox.addLayout(stance_row)

        # ── 步骤2：风格选择（初始隐藏）──────────────────────────
        self._tone_label = QLabel("步骤 2   选择回复风格：")
        self._tone_label.hide()
        vbox.addWidget(self._tone_label)

        tone_container = QWidget()
        tone_container.hide()
        tone_row = QHBoxLayout(tone_container)
        tone_row.setContentsMargins(0, 0, 0, 0)
        tone_row.setSpacing(6)
        self._tone_group = QButtonGroup(self)
        self._tone_group.setExclusive(True)
        for t in ["正式", "礼貌", "轻松", "简短"]:
            btn = QPushButton(t)
            btn.setCheckable(True)
            btn.setStyleSheet(self._toggle_btn_style())
            self._tone_group.addButton(btn)
            tone_row.addWidget(btn)
            btn.clicked.connect(
                lambda checked, tone=t: self._on_tone_selected(tone)
            )
        tone_row.addStretch()
        self._tone_container = tone_container
        vbox.addWidget(tone_container)

        # ── 补充说明 + 生成按钮（初始隐藏）─────────────────────
        self._notes_label = QLabel("补充说明（可选）：")
        self._notes_label.hide()
        self._notes_input = QLineEdit()
        self._notes_input.setPlaceholderText(
            "例：强调时间紧迫，需对方尽快确认"
        )
        self._notes_input.setStyleSheet(
            "border:1px solid palette(mid);border-radius:3px;"
            "padding:2px 6px;background:palette(base);color:palette(text);"
        )
        self._notes_input.hide()

        gen_row = QHBoxLayout()
        gen_row.addStretch()
        self._gen_btn = QPushButton("✨ 生成草稿")
        _dis = "#3a3a5a" if get_theme().is_dark() else "#aab4d8"
        self._gen_btn.setStyleSheet(
            "QPushButton{background:#4a6cf7;color:#fff;border:none;"
            "border-radius:4px;padding:4px 14px;font-weight:bold;}"
            "QPushButton:hover{background:#3a5ce7;}"
            f"QPushButton:disabled{{background:{_dis};}}"
        )
        self._gen_btn.hide()
        self._gen_btn.clicked.connect(self._on_generate_draft)
        gen_row.addWidget(self._gen_btn)

        vbox.addWidget(self._notes_label)
        vbox.addWidget(self._notes_input)
        vbox.addLayout(gen_row)

        parent_layout.addWidget(box)

    def _on_stance_selected(self, stance: str):
        self._selected_stance = stance
        self._tone_label.show()
        self._tone_container.show()

    def _on_tone_selected(self, tone: str):
        self._selected_tone = tone
        self._notes_label.show()
        self._notes_input.show()
        self._gen_btn.show()

    def _on_generate_draft(self):
        if not self._ai_processor or not self._source_email:
            return
        if not self._selected_stance or not self._selected_tone:
            QMessageBox.information(self, "提示", "请先选择回复立场和风格。")
            return
        self._gen_btn.setText("生成中…")
        self._gen_btn.setEnabled(False)
        asyncio.ensure_future(self._generate_draft_async())

    async def _generate_draft_async(self):
        loop = asyncio.get_event_loop()
        try:
            draft = await loop.run_in_executor(
                None,
                self._ai_processor.generate_reply_draft,
                self._source_email,
                self._selected_stance,
                self._selected_tone,
                self._notes_input.text().strip(),
            )
            # 保存 AI 草稿用于隐式反馈
            self._ai_draft_text = draft
            self._ai_draft_source = "reply_draft"
            self._ai_draft_context = {
                "stance": self._selected_stance,
                "tone": self._selected_tone,
            }
            self._fill_draft(draft)
        except Exception as e:
            QMessageBox.warning(self, "生成失败", str(e))
        finally:
            self._gen_btn.setText("✨ 生成草稿")
            self._gen_btn.setEnabled(True)

    def _fill_draft(self, draft: str):
        """将草稿填入撰写区（纯文本或 WebEngine 模式）。"""
        if hasattr(self, "_compose_view"):
            escaped = (
                draft
                .replace("\\", "\\\\")
                .replace("`", "\\`")
                .replace("\n", "\\n")
            )
            js = f"document.getElementById('reply-area').innerText = `{escaped}`;"
            self._compose_view.page().runJavaScript(js)
        else:
            self._body_edit.setPlainText(draft)

    # ----------------------------------------------------------------
    # 回复/转发 HTML 模板
    # ----------------------------------------------------------------

    def _build_compose_html(self) -> str:
        import html as _h
        reply_content = self._initial_reply_html if self._initial_reply_html else "<br><br><br>"
        # 引用区：优先使用 HTML，降级为纯文本
        if self._initial_html_quote:
            quote_content = self._initial_html_quote
        elif self._initial_body:
            quote_content = (
                "<pre style='white-space:pre-wrap;font-family:sans-serif;"
                "font-size:13px;margin:0'>"
                + _h.escape(self._initial_body)
                + "</pre>"
            )
        else:
            quote_content = ""
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<style>"
            "body{margin:0;padding:0;font-family:sans-serif;font-size:13px;}"
            "#reply-area{"
            "min-height:120px;"
            "padding:14px 16px 10px;outline:none;"
            "white-space:pre-wrap;word-break:break-word;"
            "}"
            "#reply-area:empty::before{"
            "content:attr(data-placeholder);color:#999;"
            "pointer-events:none;display:block"
            "}"
            "#quote-divider{"
            "margin:0 16px;"
            "border:none;border-top:1px solid #888;"
            "}"
            "#quote-area{"
            "padding:10px 16px 16px;"
            "font-family:sans-serif;font-size:13px;opacity:0.75;"
            "}"
            "img{max-width:100%!important;height:auto!important}"
            "@media(prefers-color-scheme:dark){"
            "body{background:#1e1e1e;color:#ddd;}"
            "#reply-area{background:#1e1e1e;}"
            "}"
            "</style></head><body>"
            "<div id='reply-area' contenteditable='true' "
            "data-placeholder='在此输入回复内容…'>"
            + reply_content +
            "</div>"
            + (
                "<hr id='quote-divider'>"
                f"<div id='quote-area'>{quote_content}</div>"
                if quote_content else ""
            )
            + "</body></html>"
        )

    # ----------------------------------------------------------------
    # 草稿逻辑
    # ----------------------------------------------------------------

    def _has_content(self) -> bool:
        if self._to_edit.text().strip() or self._subject_edit.text().strip():
            return True
        if hasattr(self, "_body_edit"):
            return bool(self._body_edit.toPlainText().strip())
        return True

    def _on_auto_save(self):
        if not self._has_content():
            return
        self._on_save_draft(silent=True)

    def _on_save_draft(self, silent: bool = False):
        to_raw  = self._to_edit.text().strip()
        cc_raw  = self._cc_edit.text().strip()
        subject = self._subject_edit.text().strip()

        to_list = [{"name": a.strip(), "email": a.strip()}
                   for a in to_raw.split(",") if a.strip()] or None
        cc_list = [{"name": a.strip(), "email": a.strip()}
                   for a in cc_raw.split(",") if a.strip()] or None

        if hasattr(self, "_compose_view"):
            def _got_reply_html(reply_html):
                self._compose_view.page().runJavaScript(
                    "document.getElementById('quote-area').innerHTML",
                    lambda quote_html: self._finish_save_draft(
                        to_list, cc_list, subject,
                        body_text=quote_html or "",
                        body_html=reply_html or "",
                        silent=silent,
                    ),
                )
            self._compose_view.page().runJavaScript(
                "document.getElementById('reply-area').innerHTML",
                _got_reply_html,
            )
        else:
            body = self._body_edit.toPlainText()
            self._finish_save_draft(to_list, cc_list, subject,
                                    body_text=body, body_html=None,
                                    silent=silent)

    def _finish_save_draft(self, to_list, cc_list, subject,
                           body_text, body_html, silent=False):
        from clawmail.domain.models.email import Email

        if not self._db:
            return

        if self._draft_id:
            self._db.update_draft(
                self._draft_id, to_list, cc_list, subject, body_text, body_html
            )
        else:
            email = Email(
                id=str(_uuid.uuid4()),
                account_id=self._account.id,
                subject=subject or "(无主题)",
                from_address={
                    "name": self._account.display_name or "",
                    "email": self._account.email_address,
                },
                to_addresses=to_list,
                cc_addresses=cc_list,
                body_text=body_text,
                body_html=body_html,
                folder="草稿箱",
                imap_folder="草稿箱",
                sync_status="completed",
                is_downloaded=True,
                received_at=datetime.utcnow(),
                in_reply_to=self._source_email.id if self._source_email else None,
            )
            self._db.save_email(email)
            self._draft_id = email.id

        if not silent:
            self._status_label.setText("草稿已保存")

    # ----------------------------------------------------------------
    # 关闭拦截
    # ----------------------------------------------------------------

    def reject(self):
        self._auto_save_timer.stop()
        if self._has_content() and not self._draft_id:
            reply = QMessageBox.question(
                self, "保存草稿",
                "是否将邮件保存到草稿箱？",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                self._auto_save_timer.start()
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._on_save_draft()
        super().reject()

    # ----------------------------------------------------------------
    # 发送逻辑
    # ----------------------------------------------------------------

    def _on_send(self):
        to_raw = self._to_edit.text().strip()
        subject = self._subject_edit.text().strip()

        if not to_raw:
            QMessageBox.warning(self, "提示", "请填写收件人。")
            return
        if not subject:
            QMessageBox.warning(self, "提示", "请填写主题。")
            return

        to_addresses = [a.strip() for a in to_raw.split(",") if a.strip()]
        cc_raw = self._cc_edit.text().strip()
        cc_addresses = [a.strip() for a in cc_raw.split(",") if a.strip()] or None

        self._send_btn.setEnabled(False)
        self._status_label.setText("发送中…")

        if hasattr(self, "_compose_view"):
            self._compose_view.page().runJavaScript(
                "document.getElementById('reply-area').innerText",
                lambda text: self._on_js_plain(
                    text, to_addresses, cc_addresses, subject
                ),
            )
        else:
            body = self._body_edit.toPlainText()
            asyncio.ensure_future(
                self._send_async(to_addresses, cc_addresses, subject, body, None,
                                 self._attachments or None)
            )

    def _on_js_plain(self, plain_text, to_addresses, cc_addresses, subject):
        self._compose_view.page().runJavaScript(
            "document.getElementById('reply-area').innerHTML",
            lambda inner_html: self._on_js_html(
                plain_text or "", inner_html or "",
                to_addresses, cc_addresses, subject,
            ),
        )

    def _on_js_html(self, plain_text, inner_html, to_addresses, cc_addresses, subject):
        html_body = (
            f"<div style='font-family:sans-serif;font-size:13px'>{inner_html}</div>"
            f"{self._initial_html_quote}"
        )
        asyncio.ensure_future(
            self._send_async(to_addresses, cc_addresses, subject, plain_text, html_body,
                             self._attachments or None)
        )

    async def _send_async(self, to_addresses, cc_addresses, subject, body,
                          html_body=None, attachments=None):
        try:
            if self._account.provider_type == "microsoft":
                await self._send_via_graph(
                    to_addresses, cc_addresses, subject, body, html_body, attachments
                )
            else:
                password = self._cred.decrypt_credentials(
                    self._account.credentials_encrypted
                )
                await self._smtp.send_email(
                    account=self._account,
                    password=password,
                    to_addresses=to_addresses,
                    subject=subject,
                    body=body,
                    cc_addresses=cc_addresses,
                    html_body=html_body,
                    attachments=attachments,
                )
            self._auto_save_timer.stop()
            if self._draft_id and self._db:
                self._db.delete_email(self._draft_id)
                self._draft_id = None
            # 更新原邮件：reply_status + 移除 pending_reply 分类
            if self._source_email and self._db:
                src_id = self._source_email.id
                with self._db.get_conn() as conn:
                    conn.execute(
                        "UPDATE emails SET reply_status='replied', updated_at=? WHERE id=?",
                        (datetime.utcnow().isoformat(), src_id),
                    )
                    row = conn.execute(
                        "SELECT categories FROM email_ai_metadata WHERE email_id=?",
                        (src_id,),
                    ).fetchone()
                    if row and row[0]:
                        import json as _json
                        try:
                            cats = _json.loads(row[0])
                            if "pending_reply" in cats:
                                cats.remove("pending_reply")
                                conn.execute(
                                    "UPDATE email_ai_metadata SET categories=? WHERE email_id=?",
                                    (_json.dumps(cats, ensure_ascii=False), src_id),
                                )
                        except Exception:
                            pass
                    conn.commit()
            # ── 隐式反馈：比对 AI 生成 / 润色 与最终版本 ──
            self._record_implicit_feedback(body)

            parent = self.parent()
            if parent and hasattr(parent, "_status_bar"):
                parent._status_bar.showMessage("✅ 发送成功，正在同步已发送…", 4000)
            self.accept()
            if parent and hasattr(parent, "_sync_service") and parent._sync_service:
                accs = parent._db.get_all_accounts() if parent._db else []
                if accs:
                    asyncio.ensure_future(parent._sync_service.run_once(accs[0]))
        except SMTPSendError as e:
            self._status_label.setText("")
            self._send_btn.setEnabled(True)
            QMessageBox.critical(self, "发送失败", f"SMTP 错误：{e}")
        except Exception as e:
            self._status_label.setText("")
            self._send_btn.setEnabled(True)
            QMessageBox.critical(self, "发送失败", str(e))

    def _record_implicit_feedback(self, final_body: str) -> None:
        """发送成功后，比对 AI 生成 / 润色版本与用户最终版本，记录隐式反馈。"""
        from difflib import SequenceMatcher

        if not self._db:
            return

        subject = self._subject_edit.text().strip()

        # ── 邮件生成反馈（reply_draft / generate_email）──
        if self._ai_draft_text is not None and final_body:
            ratio = SequenceMatcher(
                None, self._ai_draft_text, final_body
            ).ratio()
            if ratio < 0.95:
                source = self._ai_draft_source or "reply_draft"
                # 确定 email_id
                if source == "reply_draft" and self._source_email:
                    email_id = self._source_email.id
                else:
                    email_id = self._draft_id or str(_uuid.uuid4())
                # 从 AI 元数据中提取摘要上下文
                kw = self._ai_metadata.keywords if self._ai_metadata else None
                ol = (self._ai_metadata.summary_one_line
                      if self._ai_metadata else None)
                self._db.record_email_generation_feedback(
                    email_id=email_id,
                    source=source,
                    subject=subject,
                    ai_draft=self._ai_draft_text,
                    user_final=final_body,
                    similarity_ratio=ratio,
                    stance=self._ai_draft_context.get("stance"),
                    tone=self._ai_draft_context.get("tone"),
                    outline=self._ai_draft_context.get("outline"),
                    keywords=kw,
                    one_line=ol,
                )
                # 检查是否触发个性化
                parent = self.parent()
                count = self._db.get_feedback_count("email_generation")
                if (count >= 5 and parent
                        and hasattr(parent, "_trigger_personalization")
                        and getattr(parent, "_ai_bridge", None)):
                    parent._trigger_personalization("email_generation")

        # ── 润色反馈 ──
        if self._polished_text is not None and final_body:
            ratio = SequenceMatcher(
                None, self._polished_text, final_body
            ).ratio()
            if ratio < 0.95:
                if self._source_email:
                    email_id = self._source_email.id
                else:
                    email_id = self._draft_id or str(_uuid.uuid4())
                self._db.record_polish_email_feedback(
                    email_id=email_id,
                    subject=subject,
                    tone=self._polish_tone or "",
                    original_body=self._pre_polish_text or "",
                    polished_body=self._polished_text,
                    user_final=final_body,
                    similarity_ratio=ratio,
                )
                parent = self.parent()
                count = self._db.get_feedback_count("polish_email")
                if (count >= 5 and parent
                        and hasattr(parent, "_trigger_personalization")
                        and getattr(parent, "_ai_bridge", None)):
                    parent._trigger_personalization("polish_email")

    async def _send_via_graph(self, to_addresses, cc_addresses, subject, body,
                              html_body, attachments):
        """通过 Microsoft Graph API 发送邮件（替代 SMTP）。"""
        import json
        from datetime import datetime, timezone, timedelta
        from clawmail.infrastructure.email_clients.graph_client import GraphSyncClient

        # 解密 OAuth JSON
        raw = self._cred.decrypt_credentials(self._account.credentials_encrypted)
        data = json.loads(raw)

        # 必要时刷新令牌
        expires_at = datetime.fromisoformat(data["expires_at"])
        if datetime.now(timezone.utc) >= expires_at - timedelta(minutes=5):
            from clawmail.infrastructure.auth.microsoft_graph_oauth import refresh_access_token
            loop = asyncio.get_event_loop()
            new = await refresh_access_token(data["refresh_token"])
            data["access_token"] = new["access_token"]
            data["refresh_token"] = new.get("refresh_token", data["refresh_token"])
            data["expires_at"] = (
                datetime.now(timezone.utc) + timedelta(seconds=new["expires_in"])
            ).isoformat()
            if self._db:
                new_enc = self._cred.encrypt_credentials(json.dumps(data))
                self._db.update_account_credentials(self._account.id, new_enc)

        access_token = data["access_token"]
        graph = GraphSyncClient()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            graph.send_message,
            access_token,
            self._account.email_address,
            to_addresses,
            subject,
            body,
            cc_addresses,
            html_body,
            attachments,
        )
