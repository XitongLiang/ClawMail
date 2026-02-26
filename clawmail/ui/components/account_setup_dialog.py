"""
AccountSetupDialog — Modern gradient login page.
Full-window QDialog with deep-blue gradient background.
Centered white card with four pages:
  0 — Service chooser
  1 — Microsoft device-code OAuth
  2 — 163 Mail IMAP form
  3 — Generic IMAP form
"""

import base64
import json
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from PyQt6.QtCore import Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QColor, QDesktopServices, QFont, QLinearGradient, QPainter,
    QPainterPath, QBrush, QPen,
)
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from clawmail.domain.models.account import Account
from clawmail.infrastructure.database.storage_manager import ClawDB
from clawmail.infrastructure.security.credential_manager import CredentialManager
from clawmail.ui.theme import get_theme

# ── OAuth constants ──────────────────────────────────────────────────────────
_MS_CLIENT_ID = "9e5f94bc-e8a4-4e73-b8be-63364c29d753"
_MS_SCOPES = (
    "https://graph.microsoft.com/Mail.Read "
    "https://graph.microsoft.com/Mail.Send "
    "https://graph.microsoft.com/User.Read "
    "offline_access openid profile email"
)
_MS_DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
_MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"

_LOGO_PATH = Path(__file__).parent.parent / "assets" / "logo.svg"

# Card dimensions
_CARD_W = 400
_CARD_H = 560
_CARD_RADIUS = 12


class _OAuthWorker(QThread):
    """Runs Microsoft device-code OAuth flow in a background thread."""
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


def _make_logo_label(size: int = 72) -> QLabel:
    """Render logo.svg to a QLabel pixmap."""
    label = QLabel()
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setFixedSize(size, size)
    if _LOGO_PATH.exists():
        renderer = QSvgRenderer(str(_LOGO_PATH))
        from PyQt6.QtGui import QPixmap
        px = QPixmap(size, size)
        px.fill(Qt.GlobalColor.transparent)
        p = QPainter(px)
        renderer.render(p)
        p.end()
        label.setPixmap(px)
    else:
        label.setText("🦞")
        label.setStyleSheet(f"font-size:{size // 2}px;")
    return label


def _service_button(text: str, bg: str, hover: str, disabled: bool = False) -> QPushButton:
    btn = QPushButton(text)
    btn.setFixedHeight(44)
    btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    if disabled:
        btn.setEnabled(False)
        btn.setStyleSheet(
            "QPushButton{"
            "  background:#e0e0e0; color:#aaa;"
            "  font-size:13px; font-weight:600;"
            "  border-radius:6px; border:none; text-align:left; padding-left:16px;"
            "}"
        )
    else:
        btn.setStyleSheet(
            f"QPushButton{{"
            f"  background:{bg}; color:#fff;"
            f"  font-size:13px; font-weight:600;"
            f"  border-radius:6px; border:none; text-align:left; padding-left:16px;"
            f"}}"
            f"QPushButton:hover{{background:{hover};}}"
            f"QPushButton:pressed{{background:{hover}; opacity:0.85;}}"
        )
    return btn


def _separator_line() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    f.setStyleSheet("color:#e0e0e0;")
    return f


def _back_button() -> QPushButton:
    btn = QPushButton("← Back")
    btn.setFixedHeight(28)
    btn.setStyleSheet(
        "QPushButton{border:none;background:transparent;color:#666;"
        "font-size:12px;text-align:left;padding:0;}"
        "QPushButton:hover{color:#333;}"
    )
    return btn


def _imap_input(placeholder: str = "", password: bool = False) -> QLineEdit:
    le = QLineEdit()
    le.setPlaceholderText(placeholder)
    if password:
        le.setEchoMode(QLineEdit.EchoMode.Password)
    le.setFixedHeight(36)
    le.setStyleSheet(
        "border:1px solid #ddd; border-radius:6px; padding:4px 10px;"
        "font-size:13px; background:#fafafa; color:#333;"
        "selection-background-color:#0078D4;"
    )
    return le


def _imap_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size:12px; color:#555; margin-bottom:2px;")
    return lbl


def _submit_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setFixedHeight(40)
    btn.setStyleSheet(
        "QPushButton{background:#0078D4;color:#fff;font-size:13px;"
        "font-weight:600;border-radius:6px;border:none;}"
        "QPushButton:hover{background:#106EBE;}"
        "QPushButton:pressed{background:#005A9E;}"
    )
    return btn


class _CardWidget(QWidget):
    """White rounded card drawn directly on a transparent widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Drop shadow layers
        for i in range(8, 0, -1):
            shadow = QPainterPath()
            shadow.addRoundedRect(
                i * 0.5, i * 0.8, self.width() - i, self.height() - i * 0.8,
                _CARD_RADIUS, _CARD_RADIUS,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 8))
            painter.drawPath(shadow)

        # White card body
        card = QPainterPath()
        card.addRoundedRect(0, 0, self.width(), self.height(), _CARD_RADIUS, _CARD_RADIUS)
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(card)


class AccountSetupDialog(QDialog):
    """
    Full-window gradient login dialog.
    After exec() returns Accepted, read self.account for the created Account.
    """

    def __init__(self, db: ClawDB, cred_manager: CredentialManager, parent=None):
        super().__init__(parent)
        self._db = db
        self._cred = cred_manager
        self.account: Account = None
        self._worker: _OAuthWorker = None

        self.setWindowTitle("ClawMail — Add Account")
        self.setMinimumSize(640, 560)
        self.resize(780, 620)
        # Remove normal window frame decorations, keep close button
        self._build_ui()

    # ----------------------------------------------------------------
    # Background painting
    # ----------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor("#1A237E"))
        grad.setColorAt(1.0, QColor("#0D47A1"))
        painter.fillRect(self.rect(), QBrush(grad))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._center_card()

    def _center_card(self):
        x = (self.width() - _CARD_W) // 2
        y = (self.height() - _CARD_H) // 2
        self._card.setGeometry(x, y, _CARD_W, _CARD_H)

    # ----------------------------------------------------------------
    # UI construction
    # ----------------------------------------------------------------

    def _build_ui(self):
        # Card is a child widget that floats on the gradient background
        self._card = _CardWidget(self)
        self._card.setFixedSize(_CARD_W, _CARD_H)

        card_vbox = QVBoxLayout(self._card)
        card_vbox.setContentsMargins(32, 28, 32, 28)
        card_vbox.setSpacing(0)

        # Logo + branding
        logo_label = _make_logo_label(72)
        logo_label.setFixedSize(_CARD_W - 64, 72)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_vbox.addWidget(logo_label)

        card_vbox.addSpacing(8)
        app_name = QLabel("ClawMail")
        app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        app_name.setStyleSheet("font-size:26px; font-weight:700; color:#1A237E; letter-spacing:-0.5px;")
        card_vbox.addWidget(app_name)

        self._subtitle = QLabel("Add your email account")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setStyleSheet("font-size:13px; color:#666; margin-bottom:4px;")
        card_vbox.addWidget(self._subtitle)

        card_vbox.addSpacing(16)

        # Stacked content area
        self._stack = QStackedWidget()
        card_vbox.addWidget(self._stack, stretch=1)

        self._stack.addWidget(self._build_chooser_page())   # 0
        self._stack.addWidget(self._build_ms_oauth_page())  # 1
        self._stack.addWidget(self._build_163_page())       # 2
        self._stack.addWidget(self._build_imap_page())      # 3

        self._stack.setCurrentIndex(0)

    # ----------------------------------------------------------------
    # Page 0: Service chooser
    # ----------------------------------------------------------------

    def _build_chooser_page(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(10)

        ms_btn = _service_button("⊞   Sign in with Microsoft", "#0078D4", "#106EBE")
        ms_btn.clicked.connect(self._on_microsoft_signin)
        vbox.addWidget(ms_btn)

        mail163_btn = _service_button("163   Sign in with 163 Mail", "#D8000C", "#B30009")
        mail163_btn.clicked.connect(self._on_163_signin)
        vbox.addWidget(mail163_btn)

        google_btn = _service_button("G   Sign in with Google  (coming soon)", "#757575", "#757575", disabled=True)
        google_btn.setToolTip("Google OAuth support coming soon")
        vbox.addWidget(google_btn)

        # Separator "or"
        sep_row = QHBoxLayout()
        sep_row.setSpacing(8)
        sep_row.addWidget(_separator_line())
        or_lbl = QLabel("or")
        or_lbl.setStyleSheet("color:#aaa; font-size:12px;")
        sep_row.addWidget(or_lbl)
        sep_row.addWidget(_separator_line())
        vbox.addLayout(sep_row)

        imap_btn = QPushButton("📧   Add other IMAP account")
        imap_btn.setFixedHeight(44)
        imap_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        imap_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#333;"
            "font-size:13px;font-weight:600;border-radius:6px;"
            "border:1.5px solid #ccc;text-align:left;padding-left:16px;}"
            "QPushButton:hover{background:#f5f5f5;border-color:#999;}"
        )
        imap_btn.clicked.connect(self._on_imap_signin)
        vbox.addWidget(imap_btn)

        vbox.addStretch()
        return page

    # ----------------------------------------------------------------
    # Page 1: Microsoft device-code OAuth
    # ----------------------------------------------------------------

    def _build_ms_oauth_page(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(10)

        back_row = QHBoxLayout()
        back_btn = _back_button()
        back_btn.clicked.connect(self._on_cancel_oauth)
        back_row.addWidget(back_btn)
        back_row.addStretch()
        vbox.addLayout(back_row)

        title = QLabel("Sign in with Microsoft")
        title.setStyleSheet("font-size:15px; font-weight:700; color:#1A237E;")
        vbox.addWidget(title)

        vbox.addSpacing(6)

        url_row = QHBoxLayout()
        url_row.setSpacing(6)
        url_lbl = QLabel("Visit:")
        url_lbl.setStyleSheet("font-size:12px; color:#555;")
        url_row.addWidget(url_lbl)
        self._oauth_url_label = QLabel("https://microsoft.com/devicelogin")
        self._oauth_url_label.setStyleSheet(
            "font-size:12px; color:#0078D4; text-decoration:underline;"
        )
        self._oauth_url_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        url_row.addWidget(self._oauth_url_label, stretch=1)
        open_btn = QPushButton("Open Browser")
        open_btn.setFixedHeight(26)
        open_btn.setStyleSheet(
            "QPushButton{font-size:11px;padding:2px 10px;border:1px solid #0078D4;"
            "border-radius:4px;color:#0078D4;background:transparent;}"
            "QPushButton:hover{background:#e8f0fe;}"
        )
        open_btn.clicked.connect(self._on_open_browser)
        url_row.addWidget(open_btn)
        vbox.addLayout(url_row)

        code_row = QHBoxLayout()
        code_row.setSpacing(6)
        code_lbl = QLabel("Code:")
        code_lbl.setStyleSheet("font-size:12px; color:#555;")
        code_row.addWidget(code_lbl)
        self._oauth_code_label = QLabel("Fetching…")
        self._oauth_code_label.setStyleSheet(
            f"font-size:22px; font-weight:700; letter-spacing:4px;"
            f" color:{get_theme().oauth_code_color()};"
        )
        self._oauth_code_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        code_row.addWidget(self._oauth_code_label, stretch=1)
        copy_btn = QPushButton("Copy")
        copy_btn.setFixedHeight(26)
        copy_btn.setStyleSheet(
            "QPushButton{font-size:11px;padding:2px 10px;border:1px solid #ccc;"
            "border-radius:4px;color:#555;background:transparent;}"
            "QPushButton:hover{background:#f5f5f5;}"
        )
        copy_btn.clicked.connect(self._on_copy_code)
        code_row.addWidget(copy_btn)
        vbox.addLayout(code_row)

        self._oauth_status_label = QLabel("⏳ Waiting for sign-in…")
        self._oauth_status_label.setStyleSheet(
            f"color:{get_theme().oauth_status_color()}; font-size:12px;"
        )
        self._oauth_status_label.setWordWrap(True)
        vbox.addWidget(self._oauth_status_label)

        vbox.addStretch()
        return page

    # ----------------------------------------------------------------
    # Page 2: 163 Mail form
    # ----------------------------------------------------------------

    def _build_163_page(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(8)

        back_row = QHBoxLayout()
        back_btn = _back_button()
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        back_row.addWidget(back_btn)
        back_row.addStretch()
        vbox.addLayout(back_row)

        title = QLabel("Sign in with 163 Mail")
        title.setStyleSheet("font-size:15px; font-weight:700; color:#D8000C;")
        vbox.addWidget(title)

        vbox.addSpacing(4)

        vbox.addWidget(_imap_label("Email address"))
        self._163_email_input = _imap_input("username@163.com")
        vbox.addWidget(self._163_email_input)

        vbox.addWidget(_imap_label("Auth code (授权码, not login password)"))
        self._163_auth_input = _imap_input("Your 163 Mail auth code", password=True)
        vbox.addWidget(self._163_auth_input)

        server_row = QHBoxLayout()
        server_row.setSpacing(8)
        server_lbl = QLabel("Server: imap.163.com   Port: 993")
        server_lbl.setStyleSheet("font-size:11px; color:#999; border:1px solid #eee;"
                                 "border-radius:4px; padding:4px 8px; background:#f9f9f9;")
        server_row.addWidget(server_lbl)
        server_row.addStretch()
        vbox.addLayout(server_row)

        submit = _submit_button("Add Account")
        submit.clicked.connect(self._on_163_submit)
        vbox.addWidget(submit)

        hint = QLabel("Enable IMAP in 163 Mail settings → POP3/SMTP/IMAP to get your auth code.")
        hint.setStyleSheet("font-size:11px; color:#999;")
        hint.setWordWrap(True)
        vbox.addWidget(hint)

        vbox.addStretch()
        return page

    # ----------------------------------------------------------------
    # Page 3: Generic IMAP form
    # ----------------------------------------------------------------

    def _build_imap_page(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(8)

        back_row = QHBoxLayout()
        back_btn = _back_button()
        back_btn.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        back_row.addWidget(back_btn)
        back_row.addStretch()
        vbox.addLayout(back_row)

        title = QLabel("Add IMAP Account")
        title.setStyleSheet("font-size:15px; font-weight:700; color:#1A237E;")
        vbox.addWidget(title)

        vbox.addSpacing(4)

        vbox.addWidget(_imap_label("Email address"))
        self._imap_email_input = _imap_input("you@example.com")
        vbox.addWidget(self._imap_email_input)

        vbox.addWidget(_imap_label("Password or app password"))
        self._imap_auth_input = _imap_input("Password / auth code", password=True)
        vbox.addWidget(self._imap_auth_input)

        server_port_row = QHBoxLayout()
        server_port_row.setSpacing(8)
        self._imap_server_input = _imap_input("imap.example.com")
        server_port_row.addWidget(self._imap_server_input, stretch=3)
        self._imap_port_input = QSpinBox()
        self._imap_port_input.setRange(1, 65535)
        self._imap_port_input.setValue(993)
        self._imap_port_input.setFixedHeight(36)
        self._imap_port_input.setStyleSheet(
            "border:1px solid #ddd; border-radius:6px; padding:4px 6px; font-size:13px;"
        )
        server_port_row.addWidget(self._imap_port_input, stretch=1)
        vbox.addLayout(server_port_row)

        submit = _submit_button("Add Account")
        submit.clicked.connect(self._on_imap_submit)
        vbox.addWidget(submit)

        vbox.addStretch()
        return page

    # ----------------------------------------------------------------
    # Navigation
    # ----------------------------------------------------------------

    def _on_microsoft_signin(self):
        self._oauth_code_label.setText("Fetching…")
        self._oauth_status_label.setText("⏳ Connecting to Microsoft…")
        self._oauth_status_label.setStyleSheet(
            f"color:{get_theme().oauth_status_color()}; font-size:12px;"
        )
        self._oauth_url_label.setText("https://microsoft.com/devicelogin")
        self._subtitle.setText("Sign in with your Microsoft account")
        self._stack.setCurrentIndex(1)

        self._worker = _OAuthWorker(parent=self)
        self._worker.code_ready.connect(self._on_code_ready)
        self._worker.success.connect(self._finish_microsoft_oauth)
        self._worker.error.connect(self._show_oauth_error)
        self._worker.start()

    def _on_163_signin(self):
        self._subtitle.setText("163 Mail — IMAP")
        self._stack.setCurrentIndex(2)

    def _on_imap_signin(self):
        self._subtitle.setText("IMAP account")
        self._stack.setCurrentIndex(3)

    def _on_cancel_oauth(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        self._worker = None
        self._subtitle.setText("Add your email account")
        self._stack.setCurrentIndex(0)

    # ----------------------------------------------------------------
    # Microsoft OAuth callbacks
    # ----------------------------------------------------------------

    def _on_code_ready(self, user_code: str, verification_uri: str):
        self._oauth_code_label.setText(user_code)
        self._oauth_url_label.setText(verification_uri)
        self._oauth_status_label.setText(
            "Enter the code above in your browser, then sign in with your Microsoft account. "
            "This dialog will close automatically when done."
        )
        QDesktopServices.openUrl(QUrl(verification_uri))

    def _on_open_browser(self):
        QDesktopServices.openUrl(QUrl(self._oauth_url_label.text().strip()))

    def _on_copy_code(self):
        code = self._oauth_code_label.text().strip()
        if code and code not in ("Fetching…",):
            QApplication.clipboard().setText(code)

    def _finish_microsoft_oauth(self, tokens: dict) -> None:
        # Debug dump
        try:
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
            self._show_oauth_error("Could not extract email from token. Please retry.")
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
            self._show_oauth_error(f"Credential encryption failed: {e}")
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
            self._show_oauth_error(f"Account save failed: {e}")
            return

        self.account = account
        self.accept()

    def _show_oauth_error(self, message: str) -> None:
        self._oauth_status_label.setText(f"❌ {message}")
        self._oauth_status_label.setStyleSheet("color:#D32F2F; font-size:12px;")

    # ----------------------------------------------------------------
    # 163 Mail form submit
    # ----------------------------------------------------------------

    def _on_163_submit(self):
        email = self._163_email_input.text().strip()
        auth_code = self._163_auth_input.text().strip()

        if not email or "@" not in email:
            QMessageBox.warning(self, "Input Error", "Please enter a valid email address.")
            return
        if not auth_code:
            QMessageBox.warning(self, "Input Error", "Please enter your auth code (授权码).")
            return

        try:
            encrypted = self._cred.encrypt_credentials(auth_code)
        except Exception as e:
            QMessageBox.critical(self, "Encryption Error", f"Credential encryption failed: {e}")
            return

        account = Account(
            id=str(uuid.uuid4()),
            email_address=email,
            display_name=email.split("@")[0],
            provider_type="imap",
            imap_server="imap.163.com",
            imap_port=993,
            smtp_server="smtp.163.com",
            smtp_port=465,
            credentials_encrypted=encrypted,
            status="active",
        )

        try:
            self._db.create_account(account)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Account save failed: {e}")
            return

        self.account = account
        self.accept()

    # ----------------------------------------------------------------
    # Generic IMAP form submit
    # ----------------------------------------------------------------

    def _on_imap_submit(self):
        email = self._imap_email_input.text().strip()
        auth_code = self._imap_auth_input.text().strip()
        imap_server = self._imap_server_input.text().strip()
        imap_port = self._imap_port_input.value()

        if not email or "@" not in email:
            QMessageBox.warning(self, "Input Error", "Please enter a valid email address.")
            return
        if not auth_code:
            QMessageBox.warning(self, "Input Error", "Please enter your password or auth code.")
            return
        if not imap_server:
            QMessageBox.warning(self, "Input Error", "Please enter the IMAP server address.")
            return

        try:
            encrypted = self._cred.encrypt_credentials(auth_code)
        except Exception as e:
            QMessageBox.critical(self, "Encryption Error", f"Credential encryption failed: {e}")
            return

        account = Account(
            id=str(uuid.uuid4()),
            email_address=email,
            display_name=email.split("@")[0],
            provider_type="imap",
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
            QMessageBox.critical(self, "Save Error", f"Account save failed: {e}")
            return

        self.account = account
        self.accept()

    # ----------------------------------------------------------------
    # Cleanup
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
