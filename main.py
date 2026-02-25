"""
ClawMail 入口（Phase 1）
qasync 将 asyncio 集成到 Qt 事件循环，启动 IMAP 同步服务。
"""

import asyncio
import os
import sys
from pathlib import Path

# macOS conda 环境下 QtWebEngine 沙箱进程找不到路径，需禁用沙箱
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
# macOS 15 + Qt 6.7 WebEngine GPU 进程崩溃，禁用 GPU 硬件加速
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

import qasync
from PyQt6.QtWidgets import QApplication

from clawmail.infrastructure.ai.openclawbridge import OpenClawBridge
from clawmail.infrastructure.ai.ai_processor import AIProcessor
from clawmail.infrastructure.database.storage_manager import ClawDB
from clawmail.infrastructure.security.credential_manager import CredentialManager
from clawmail.services.sync_service import SyncService
from clawmail.services.ai_service import AIService
from clawmail.ui.app import ClawMailApp
from clawmail.ui.components.account_setup_dialog import AccountSetupDialog
from clawmail.api import server as api_server


_DEFAULT_TOKEN = "6b777db2700cfcedbaf8d11f5b02580025dd8d90cfce792a"


def _load_openclaw_token(data_dir: Path) -> str:
    config_path = data_dir / "config.json"
    if config_path.exists():
        try:
            import json
            cfg = json.loads(config_path.read_text())
            return cfg.get("openclaw_token") or _DEFAULT_TOKEN
        except Exception:
            pass
    return _DEFAULT_TOKEN


async def _startup(window: ClawMailApp, db: ClawDB, cred_manager: CredentialManager,
                   ai_bridge: OpenClawBridge) -> None:
    """
    账号检查、对话框、同步服务启动。
    在 loop.run_forever() 之后以协程运行，确保 asyncio 事件循环已就绪，
    从而支持对话框内的 ensure_future（Microsoft OAuth 设备码流程）。
    """
    accounts = db.get_all_accounts()
    if not accounts:
        dialog = AccountSetupDialog(db, cred_manager, parent=window)
        dialog.exec()   # 进入嵌套 Qt 事件循环；qasync 仍会处理 asyncio 回调
        if dialog.account:
            accounts = [dialog.account]

    if not accounts:
        return

    account = accounts[0]
    window.set_current_account(account.id)

    sync_svc = SyncService(db, cred_manager)
    window.set_sync_service(sync_svc, account_id=account.id)

    ai_processor = AIProcessor(ai_bridge)
    ai_svc = AIService(db, ai_processor, move_callback=sync_svc.move_email)
    window.set_ai_service(ai_svc)

    # 新邮件同步完成后自动入队 AI 处理
    sync_svc.email_synced.connect(ai_svc.enqueue)

    asyncio.ensure_future(sync_svc.start(account))
    asyncio.ensure_future(ai_svc.start(account_id=account.id))


def main():
    data_dir = Path.home() / "clawmail_data"
    db = ClawDB(data_dir)
    db.initialize()
    cred_manager = CredentialManager()

    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    ai_bridge = OpenClawBridge(token=_load_openclaw_token(data_dir))

    window = ClawMailApp(db, cred_manager)
    window.set_ai_bridge(ai_bridge)
    window.show()

    # 注入 API 服务引用
    api_server.init(window, db)
    asyncio.ensure_future(api_server.start_api_server())

    # 账号检查与启动（在事件循环运行后执行，确保 OAuth 流程可用）
    asyncio.ensure_future(_startup(window, db, cred_manager, ai_bridge))

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
