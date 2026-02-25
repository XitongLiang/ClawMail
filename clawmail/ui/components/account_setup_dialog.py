"""
AccountSetupDialog — 账号设置对话框
支持手动 IMAP 配置和 Microsoft OAuth 2.0 设备码流程。
OAuth 流程使用 QThread 在后台线程中执行 HTTP 轮询，通过 Qt 信号更新 UI，
避免 qasync 嵌套事件循环带来的异步调度问题。
"""

import base64
import json
import time
import uuid
from datetime import datetime, timezone, timedelta

import httpx
from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
)

from clawmail.domain.models.account import Account
from clawmail.infrastructure.database.storage_manager import ClawDB
from clawmail.infrastructure.security.credential_manager import CredentialManager

# ── OAuth constants (duplicated here to avoid import-time async issues) ──────
_MS_CLIENT_ID = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
_MS_SCOPES = (
    "https://outlook.office.com/IMAP.AccessAsUser.All "
    "https://outlook.office.com/SMTP.Send "
    "offline_access openid profile email"
)
_MS_DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
_MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"


class _OAuthWorker(QThread):
    """
    在独立线程中执行 Microsoft 设备码 OAuth 流程。
    通过 Qt 信号将结果传回主线程。
    """
    code_ready = pyqtSignal(str, str)   # user_code, verification_uri
    success = pyqtSignal(dict)          # token dict
    error = pyqtSignal(str)             # error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            # 1. 获取设备码
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    _MS_DEVICE_CODE_URL,
                    data={"client_id": _MS_CLIENT_ID, "scope": _MS_SCOPES},
                )
                resp.raise_for_status()
                flow = resp.json()

            if self._cancelled:
                return

            device_code = flow["device_code"]
            user_code = flow.get("user_code", "")
            verification_uri = flow.get("verification_uri", "https://microsoft.com/devicelogin")
            interval = flow.get("interval", 5)
            expires_in = flow.get("expires_in", 900)

            self.code_ready.emit(user_code, verification_uri)

            # 2. 轮询令牌端点
            deadline = time.monotonic() + expires_in
            poll_interval = interval

            while time.monotonic() < deadline:
                if self._cancelled:
                    return
                time.sleep(poll_interval)
                if self._cancelled:
                    return

                with httpx.Client(timeout=30) as client:
                    resp = client.post(
                        _MS_TOKEN_URL,
                        data={
                            "client_id": _MS_CLIENT_ID,
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                            "device_code": device_code,
                        },
                    )
                    data = resp.json()

                if "access_token" in data:
                    self.success.emit(data)
                    return

                err = data.get("error", "")
                if err == "authorization_pending":
                    continue
                elif err == "slow_down":
                    poll_interval += 5
                    continue
                elif err == "expired_token":
                    self.error.emit("设备码已过期，请重新开始")
                    return
                else:
                    desc = data.get("error_description", "")
                    self.error.emit(f"OAuth 错误 {err}: {desc}")
                    return

            self.error.emit("设备码流程超时，请重新开始")

        except Exception as e:
            if not self._cancelled:
                self.error.emit(str(e))


class AccountSetupDialog(QDialog):
    """
    首次使用时弹出的账号配置窗口。
    exec() 返回 Accepted 后，通过 self.account 获取创建好的 Account 对象。
    """

    def __init__(
        self,
        db: ClawDB,
        cred_manager: CredentialManager,
        parent=None,
    ):
        super().__init__(parent)
        self._db = db
        self._cred = cred_manager
        self.account: Account = None
        self._worker: _OAuthWorker = None

        self.setWindowTitle("添加邮箱账号")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Microsoft 登录按钮
        self._ms_button = QPushButton("  使用 Microsoft 账号登录（Outlook/Hotmail）")
        self._ms_button.setStyleSheet(
            "QPushButton {"
            "  background-color: #0078D4;"
            "  color: white;"
            "  font-size: 13px;"
            "  font-weight: bold;"
            "  padding: 10px 16px;"
            "  border-radius: 4px;"
            "  border: none;"
            "}"
            "QPushButton:hover { background-color: #106EBE; }"
            "QPushButton:pressed { background-color: #005A9E; }"
        )
        self._ms_button.clicked.connect(self._on_microsoft_signin)
        layout.addWidget(self._ms_button)

        # 分隔线
        sep_layout = QHBoxLayout()
        line1 = QFrame()
        line1.setFrameShape(QFrame.Shape.HLine)
        line1.setFrameShadow(QFrame.Shadow.Sunken)
        sep_label = QLabel("  或手动添加  ")
        sep_label.setStyleSheet("color: #888; font-size: 11px;")
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        sep_layout.addWidget(line1)
        sep_layout.addWidget(sep_label)
        sep_layout.addWidget(line2)
        layout.addLayout(sep_layout)

        # 堆叠区域：手动表单（page 0）vs OAuth 设备码面板（page 1）
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        self._stack.addWidget(self._build_form_page())
        self._stack.addWidget(self._build_oauth_page())

        # 按钮栏
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

    def _build_form_page(self):
        page = QFrame()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)

        title = QLabel("请填写 IMAP 邮箱信息")
        title.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 4px;")
        v.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("example@163.com")
        form.addRow("邮箱地址：", self._email_input)

        self._auth_input = QLineEdit()
        self._auth_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._auth_input.setPlaceholderText("IMAP 授权码（非登录密码）")
        form.addRow("授权码：", self._auth_input)

        self._imap_server_input = QLineEdit()
        self._imap_server_input.setText("imap.163.com")
        form.addRow("IMAP 服务器：", self._imap_server_input)

        self._imap_port_input = QSpinBox()
        self._imap_port_input.setRange(1, 65535)
        self._imap_port_input.setValue(993)
        form.addRow("IMAP 端口：", self._imap_port_input)

        v.addLayout(form)

        hint = QLabel("注：163 邮箱需在「设置→POP3/SMTP/IMAP」中开启 IMAP 并获取授权码")
        hint.setStyleSheet("color: #888; font-size: 11px; margin-top: 6px;")
        hint.setWordWrap(True)
        v.addWidget(hint)

        return page

    def _build_oauth_page(self):
        page = QFrame()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 4, 0, 4)
        v.setSpacing(10)

        title = QLabel("Microsoft 账号登录")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        v.addWidget(title)

        url_layout = QHBoxLayout()
        url_label_prefix = QLabel("请访问：")
        url_label_prefix.setStyleSheet("font-size: 12px;")
        self._oauth_url_label = QLabel("https://microsoft.com/devicelogin")
        self._oauth_url_label.setStyleSheet(
            "font-size: 12px; color: #0078D4; text-decoration: underline;"
        )
        self._oauth_url_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._open_browser_btn = QPushButton("打开浏览器")
        self._open_browser_btn.setFixedWidth(90)
        self._open_browser_btn.clicked.connect(self._on_open_browser)
        url_layout.addWidget(url_label_prefix)
        url_layout.addWidget(self._oauth_url_label, 1)
        url_layout.addWidget(self._open_browser_btn)
        v.addLayout(url_layout)

        code_layout = QHBoxLayout()
        code_label_prefix = QLabel("输入验证码：")
        code_label_prefix.setStyleSheet("font-size: 12px;")
        self._oauth_code_label = QLabel("获取中…")
        self._oauth_code_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; letter-spacing: 4px; color: #222;"
        )
        self._oauth_code_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._copy_code_btn = QPushButton("复制")
        self._copy_code_btn.setFixedWidth(60)
        self._copy_code_btn.clicked.connect(self._on_copy_code)
        code_layout.addWidget(code_label_prefix)
        code_layout.addWidget(self._oauth_code_label, 1)
        code_layout.addWidget(self._copy_code_btn)
        v.addLayout(code_layout)

        self._oauth_status_label = QLabel("正在连接 Microsoft 服务，请稍候…")
        self._oauth_status_label.setStyleSheet("color: #555; font-size: 11px;")
        self._oauth_status_label.setWordWrap(True)
        v.addWidget(self._oauth_status_label)

        cancel_oauth_btn = QPushButton("取消，返回手动配置")
        cancel_oauth_btn.setStyleSheet("color: #555; border: none; font-size: 11px;")
        cancel_oauth_btn.clicked.connect(self._on_cancel_oauth)
        v.addWidget(cancel_oauth_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        return page

    # ----------------------------------------------------------------
    # Microsoft OAuth 流程（QThread 驱动）
    # ----------------------------------------------------------------

    def _on_microsoft_signin(self):
        self._oauth_code_label.setText("获取中…")
        self._oauth_status_label.setText("正在连接 Microsoft 服务，请稍候…")
        self._oauth_status_label.setStyleSheet("color: #555; font-size: 11px;")
        self._oauth_url_label.setText("https://microsoft.com/devicelogin")
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setVisible(False)
        self._stack.setCurrentIndex(1)

        self._worker = _OAuthWorker(parent=self)
        self._worker.code_ready.connect(self._on_code_ready)
        self._worker.success.connect(self._finish_microsoft_oauth)
        self._worker.error.connect(self._show_oauth_error)
        self._worker.start()

    def _on_code_ready(self, user_code: str, verification_uri: str):
        """后台线程获取到设备码后，在主线程中更新 UI 并打开浏览器。"""
        self._oauth_code_label.setText(user_code)
        self._oauth_url_label.setText(verification_uri)
        self._oauth_status_label.setText(
            "请在浏览器中输入上方验证码，然后用 Microsoft 账号登录。"
            "登录成功后此对话框将自动关闭。"
        )
        QDesktopServices.openUrl(QUrl(verification_uri))

    def _on_cancel_oauth(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        self._worker = None
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setVisible(True)
        self._stack.setCurrentIndex(0)

    def _on_open_browser(self):
        QDesktopServices.openUrl(QUrl(self._oauth_url_label.text().strip()))

    def _on_copy_code(self):
        code = self._oauth_code_label.text().strip()
        if code and code not in ("获取中…",):
            QApplication.clipboard().setText(code)

    def _finish_microsoft_oauth(self, tokens: dict) -> None:
        """从令牌中提取邮箱，创建并保存 Microsoft 账号，然后关闭对话框。"""
        # Debug: dump token keys and id_token claims to a temp file
        try:
            import os
            debug_path = os.path.expanduser("~/clawmail_data/oauth_debug.json")
            debug_info = {"token_keys": list(tokens.keys())}
            id_token_raw = tokens.get("id_token", "")
            if id_token_raw:
                try:
                    parts = id_token_raw.split(".")
                    if len(parts) >= 2:
                        payload = parts[1]
                        payload += "=" * (4 - len(payload) % 4)
                        debug_info["id_token_claims"] = json.loads(
                            base64.urlsafe_b64decode(payload)
                        )
                except Exception as ex:
                    debug_info["id_token_decode_error"] = str(ex)
            else:
                debug_info["id_token_present"] = False
            with open(debug_path, "w") as f:
                json.dump(debug_info, f, indent=2)
        except Exception:
            pass

        email = None
        id_token = tokens.get("id_token", "")
        if id_token:
            try:
                parts = id_token.split(".")
                if len(parts) >= 2:
                    payload = parts[1]
                    payload += "=" * (4 - len(payload) % 4)
                    claims = json.loads(base64.urlsafe_b64decode(payload))
                    email = claims.get("email") or claims.get("preferred_username")
            except Exception:
                pass

        if not email:
            self._show_oauth_error("无法从令牌中获取邮箱地址，请重试。")
            return

        token_json = json.dumps({
            "type": "oauth2",
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(seconds=tokens["expires_in"])
            ).isoformat(),
        })

        try:
            encrypted = self._cred.encrypt_credentials(token_json)
        except Exception as e:
            self._show_oauth_error(f"凭据加密失败：{e}")
            return

        account = Account(
            id=str(uuid.uuid4()),
            email_address=email,
            display_name=email.split("@")[0],
            provider_type="microsoft",
            imap_server="outlook.office365.com",
            imap_port=993,
            smtp_server="smtp.office365.com",
            smtp_port=587,
            credentials_encrypted=encrypted,
            status="active",
        )

        try:
            self._db.create_account(account)
        except Exception as e:
            self._show_oauth_error(f"账号保存失败：{e}")
            return

        self.account = account
        self.accept()

    def _show_oauth_error(self, message: str) -> None:
        self._oauth_status_label.setText(f"错误：{message}")
        self._oauth_status_label.setStyleSheet("color: #d00; font-size: 11px;")

    # ----------------------------------------------------------------
    # 对话框关闭时确保后台线程停止
    # ----------------------------------------------------------------

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        super().closeEvent(event)

    def reject(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        super().reject()

    # ----------------------------------------------------------------
    # 手动表单提交
    # ----------------------------------------------------------------

    def _on_accept(self):
        email = self._email_input.text().strip()
        auth_code = self._auth_input.text().strip()
        imap_server = self._imap_server_input.text().strip()
        imap_port = self._imap_port_input.value()

        if not email or "@" not in email:
            QMessageBox.warning(self, "输入错误", "请填写有效的邮箱地址。")
            return
        if not auth_code:
            QMessageBox.warning(self, "输入错误", "请填写授权码。")
            return
        if not imap_server:
            QMessageBox.warning(self, "输入错误", "请填写 IMAP 服务器地址。")
            return

        try:
            encrypted = self._cred.encrypt_credentials(auth_code)
        except Exception as e:
            QMessageBox.critical(self, "加密失败", f"凭据加密失败：{e}")
            return

        account = Account(
            id=str(uuid.uuid4()),
            email_address=email,
            display_name=email.split("@")[0],
            imap_server=imap_server,
            imap_port=imap_port,
            smtp_server=imap_server.replace("imap.", "smtp."),
            smtp_port=465,
            credentials_encrypted=encrypted,
            status="active",
        )

        try:
            self._db.create_account(account)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"账号保存失败：{e}")
            return

        self.account = account
        self.accept()
