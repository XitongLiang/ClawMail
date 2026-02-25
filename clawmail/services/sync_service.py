"""
SyncService — 邮件同步协调器
负责周期性 IMAP 同步、重试、IDLE 监听，通过 Qt Signal 通知 UI。
设计规范：design/tech_spec.md 异步模型节 + 错误处理节
"""

import asyncio
import json
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from clawmail.domain.models.account import Account
from clawmail.infrastructure.database.storage_manager import ClawDB
from clawmail.infrastructure.email_clients.imap_client import (
    ClawIMAPClient,
    IMAPAuthError,
    IMAPConnectionError,
)
from clawmail.infrastructure.security.credential_manager import CredentialManager

# 需要同步的文件夹
SYNC_FOLDERS = ["INBOX", "垃圾邮件", "已发送"]

# 重试配置
MAX_RETRIES = 3
RETRY_BACKOFF = [2, 4, 8]  # 秒


class SyncService(QObject):
    email_synced = pyqtSignal(str)   # 新邮件 email_id 已存库
    sync_done = pyqtSignal(int)      # 本轮同步完成，参数为新邮件数
    sync_error = pyqtSignal(str)     # 同步出错，参数为错误信息
    sync_started = pyqtSignal()      # 开始新一轮同步

    def __init__(self, db: ClawDB, cred_manager: CredentialManager):
        super().__init__()
        self._db = db
        self._cred = cred_manager
        self._running = False
        self._periodic_task: Optional[asyncio.Task] = None
        self._imap: Optional[ClawIMAPClient] = None
        self._account: Optional[Account] = None

    # ----------------------------------------------------------------
    # 公开接口
    # ----------------------------------------------------------------

    async def start(self, account: Account) -> None:
        """首次立即同步，然后启动周期任务。"""
        self._running = True
        self._account = account
        await self.run_once(account)
        self._periodic_task = asyncio.create_task(
            self._periodic_loop(account)
        )

    async def run_once(self, account: Account) -> int:
        """执行一次完整同步，返回新邮件总数。出错时返回 0 并发射 sync_error。"""
        self.sync_started.emit()

        for attempt in range(MAX_RETRIES):
            try:
                total = await self._do_sync(account)
                self.sync_done.emit(total)
                self._db.update_account_status(account.id, "active")
                return total

            except IMAPAuthError as e:
                # 认证错误不重试
                self._db.update_account_status(account.id, "error", str(e))
                self.sync_error.emit(f"认证失败：{e}")
                return 0

            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF[attempt])
                else:
                    self._db.update_account_status(account.id, "error", str(e))
                    self.sync_error.emit(f"同步失败：{e}")
                    return 0
        return 0

    def stop(self) -> None:
        """停止周期任务。"""
        self._running = False
        if self._periodic_task and not self._periodic_task.done():
            self._periodic_task.cancel()

    async def move_email(
        self, email_id: str, imap_uid: str, from_folder: str, to_folder: str
    ) -> bool:
        """在 IMAP 服务器上移动邮件并更新本地数据库。"""
        if not self._account:
            return False
        password = self._cred.decrypt_credentials(self._account.credentials_encrypted)
        imap = ClawIMAPClient(data_dir=self._db.data_dir)
        try:
            await imap.connect(self._account, password)
            moved = await imap.move_email(imap_uid, from_folder, to_folder)
        finally:
            await imap.disconnect()
        if moved:
            self._db.update_email_folder(email_id, to_folder)
        return moved

    # ----------------------------------------------------------------
    # 内部实现
    # ----------------------------------------------------------------

    async def _do_sync(self, account: Account) -> int:
        """建立 IMAP 连接，同步所有文件夹，返回新邮件总数。"""
        password = self._cred.decrypt_credentials(account.credentials_encrypted)

        imap = ClawIMAPClient(data_dir=self._db.data_dir)
        try:
            await imap.connect(account, password)
            total = 0
            for folder in SYNC_FOLDERS:
                count = await self._sync_folder(account, imap, folder)
                total += count
            return total
        finally:
            await imap.disconnect()

    async def _sync_folder(
        self, account: Account, imap: ClawIMAPClient, folder: str
    ) -> int:
        """同步单个文件夹，返回新邮件数。"""
        # 读取上次同步游标
        cursor = self._get_cursor(account)
        since_uid = cursor.get(folder)

        new_emails = await imap.fetch_new_emails(folder, since_uid)
        if not new_emails:
            return 0

        new_count = 0
        max_uid = since_uid

        for email, attachments in new_emails:
            self._db.save_email(email)
            for att in attachments:
                self._db.save_attachment(
                    email_id=email.id,
                    filename=att["filename"],
                    content_type=att["content_type"],
                    size_bytes=att["size_bytes"],
                    storage_path=att["storage_path"],
                )
            self.email_synced.emit(email.id)
            new_count += 1
            # 追踪最大 UID
            if email.imap_uid:
                if max_uid is None or int(email.imap_uid) > int(max_uid):
                    max_uid = email.imap_uid

        # 更新游标
        if max_uid != since_uid:
            cursor[folder] = max_uid
            self._db.update_account_sync_cursor(account.id, json.dumps(cursor))

        return new_count

    def _get_cursor(self, account: Account) -> dict:
        """从数据库读取并解析 sync_cursor JSON。"""
        acc = self._db.get_account(account.id)
        if acc and acc.sync_cursor:
            try:
                return json.loads(acc.sync_cursor)
            except (json.JSONDecodeError, TypeError):
                pass
        return {}

    async def _periodic_loop(self, account: Account) -> None:
        """周期同步循环：等待 interval 分钟后再同步。"""
        acc = self._db.get_account(account.id)
        interval = (acc.sync_interval_minutes if acc else 2) * 60
        while self._running:
            await asyncio.sleep(interval)
            if not self._running:
                break
            await self.run_once(account)
