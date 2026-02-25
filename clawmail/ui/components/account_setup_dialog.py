"""
AccountSetupDialog — 账号设置对话框
用户首次运行时输入 IMAP 账号和授权码，保存加密凭据到数据库。
"""

import uuid

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QLineEdit, QMessageBox, QVBoxLayout, QSpinBox,
)
from PyQt6.QtCore import Qt

from clawmail.domain.models.account import Account
from clawmail.infrastructure.database.storage_manager import ClawDB
from clawmail.infrastructure.security.credential_manager import CredentialManager


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
        self.account: Account = None  # 创建成功后的 Account 对象

        self.setWindowTitle("添加邮箱账号")
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("请填写 IMAP 邮箱信息")
        title.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 8px;")
        layout.addWidget(title)

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

        layout.addLayout(form)

        hint = QLabel("注：163 邮箱需在「设置→POP3/SMTP/IMAP」中开启 IMAP 并获取授权码")
        hint.setStyleSheet("color: #888; font-size: 11px; margin-top: 6px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
