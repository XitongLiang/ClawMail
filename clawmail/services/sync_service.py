"""
SyncService — 邮件同步协调器
负责周期性 IMAP 同步、重试、IDLE 监听，通过 Qt Signal 通知 UI。
设计规范：design/tech_spec.md 异步模型节 + 错误处理节
"""

import asyncio
import json
from pathlib import Path
from typing import Optional


def _dbg(msg: str) -> None:
    """写调试日志到文件（绕过 conda run 的 stdout 捕获问题）。"""
    try:
        log = Path.home() / "clawmail_data" / "sync_debug.log"
        with open(log, "a") as f:
            f.write(msg + "\n")
    except Exception:
        pass

from PyQt6.QtCore import QObject, pyqtSignal

from clawmail.domain.models.account import Account
from clawmail.infrastructure.database.storage_manager import ClawDB
from clawmail.infrastructure.email_clients.imap_client import (
    ClawIMAPClient,
    IMAPAuthError,
    IMAPConnectionError,
)
from clawmail.infrastructure.email_clients.graph_client import (
    GraphSyncClient,
    GraphAuthError,
    GRAPH_FOLDERS,
    GRAPH_FOLDER_ID_MAP,
)
from clawmail.infrastructure.security.credential_manager import CredentialManager

# 需要同步的文件夹（非 Microsoft 账号）
SYNC_FOLDERS_DEFAULT = ["INBOX", "垃圾邮件", "已发送"]

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

        auth_error_types = (IMAPAuthError, GraphAuthError)

        for attempt in range(MAX_RETRIES):
            try:
                total = await self._do_sync(account)
                self.sync_done.emit(total)
                self._db.update_account_status(account.id, "active")
                return total

            except auth_error_types as e:
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
        """移动邮件并更新本地数据库（Microsoft 用 Graph，其他用 IMAP）。"""
        if not self._account:
            return False

        if self._account.provider_type == "microsoft":
            access_token = await self._get_valid_oauth_token(self._account)
            dest_id = GRAPH_FOLDER_ID_MAP.get(to_folder, to_folder)
            loop = asyncio.get_event_loop()
            graph = GraphSyncClient()
            moved = await loop.run_in_executor(
                None, graph.move_message, access_token, imap_uid, dest_id
            )
        else:
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

    async def _get_valid_oauth_token(self, account: Account) -> str:
        """解密 OAuth JSON，必要时刷新令牌，返回有效的 access_token。"""
        import json
        from datetime import datetime, timezone, timedelta
        raw = self._cred.decrypt_credentials(account.credentials_encrypted)
        data = json.loads(raw)
        expires_at = datetime.fromisoformat(data["expires_at"])
        if datetime.now(timezone.utc) >= expires_at - timedelta(minutes=5):
            from clawmail.infrastructure.auth.microsoft_graph_oauth import refresh_access_token
            new = await refresh_access_token(data["refresh_token"])
            data["access_token"] = new["access_token"]
            data["refresh_token"] = new.get("refresh_token", data["refresh_token"])
            data["expires_at"] = (
                datetime.now(timezone.utc) + timedelta(seconds=new["expires_in"])
            ).isoformat()
            new_enc = self._cred.encrypt_credentials(json.dumps(data))
            self._db.update_account_credentials(account.id, new_enc)
        return data["access_token"]

    async def _do_sync(self, account: Account) -> int:
        """同步所有文件夹，Microsoft 走 Graph API，其他走 IMAP。"""
        _dbg(f"_do_sync start provider={account.provider_type}")
        if account.provider_type == "microsoft":
            return await self._do_sync_graph(account)

        password = self._cred.decrypt_credentials(account.credentials_encrypted)
        imap = ClawIMAPClient(data_dir=self._db.data_dir)
        try:
            await imap.connect(account, password)
            _dbg("imap connected OK")
            total = 0
            for folder in SYNC_FOLDERS_DEFAULT:
                try:
                    count = await self._sync_folder(account, imap, folder)
                    total += count
                except (IMAPConnectionError, Exception) as folder_err:
                    _dbg(f"folder '{folder}' error: {type(folder_err).__name__}: {folder_err}")
            return total
        finally:
            await imap.disconnect()

    async def _do_sync_graph(self, account: Account) -> int:
        """通过 Microsoft Graph API 增量同步邮件。"""
        access_token = await self._get_valid_oauth_token(account)
        graph = GraphSyncClient(data_dir=self._db.data_dir)
        cursor = self._get_cursor(account)
        loop = asyncio.get_event_loop()
        total = 0

        for folder_id, folder_display in GRAPH_FOLDERS:
            try:
                delta_link = cursor.get(folder_display)
                _dbg(f"Graph sync folder={folder_display} has_delta={bool(delta_link)}")

                results, new_delta = await loop.run_in_executor(
                    None,
                    graph.fetch_folder_delta,
                    access_token,
                    folder_id,
                    delta_link,
                    account.id,
                    folder_display,
                )

                for email, attachments in results:
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
                    total += 1

                if new_delta:
                    cursor[folder_display] = new_delta
                    self._db.update_account_sync_cursor(account.id, json.dumps(cursor))

                _dbg(f"Graph folder={folder_display} synced {len(results)} emails")

            except GraphAuthError:
                raise
            except Exception as e:
                _dbg(f"Graph folder '{folder_display}' error: {type(e).__name__}: {e}")

        return total

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
