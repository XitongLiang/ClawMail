"""
AIService — AI 邮件处理流水线
监听 SyncService.email_synced 信号，将新邮件加入异步队列，
在线程池中调用 AIProcessor，通过 Qt Signal 通知 UI 更新。
支持指数退避重试（最多 3 次），最终失败写 ai_status='failed'。
"""

import asyncio
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from clawmail.domain.models.email import EmailAIMetadata
from clawmail.infrastructure.ai.ai_processor import AIProcessor, AIProcessingError
from clawmail.infrastructure.database.storage_manager import ClawDB

# 重试配置
MAX_RETRIES = 3
RETRY_BACKOFF = [5, 15, 60]  # 秒，指数退避


class AIService(QObject):
    """
    AI 处理流水线服务。

    信号：
    - email_processed(email_id, ai_status): 每封邮件处理完成后发射
      ai_status = 'processed' | 'failed'
    """

    email_processed    = pyqtSignal(str, str)  # (email_id, ai_status)
    processing_started = pyqtSignal(str, int)   # (email_id, queue_remaining) — 开始处理单封邮件

    def __init__(self, db: ClawDB, ai_processor: AIProcessor, move_callback=None):
        super().__init__()
        self._db = db
        self._processor = ai_processor
        self._move_callback = move_callback  # async callable(email_id, imap_uid, from_folder, to_folder)
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._running = False
        self._task: Optional[asyncio.Task] = None

    # ----------------------------------------------------------------
    # 公开接口
    # ----------------------------------------------------------------

    def enqueue(self, email_id: str) -> None:
        """将 email_id 加入待处理队列（由 SyncService.email_synced 信号触发）。"""
        try:
            self._queue.put_nowait(email_id)
        except asyncio.QueueFull:
            pass  # 队列已满时静默丢弃，下次启动时会重新处理

    async def start(self, account_id: Optional[str] = None) -> None:
        """
        启动处理循环。
        若提供 account_id，先将所有历史未处理邮件入队，再进入常驻循环。
        """
        self._running = True

        # 历史未处理邮件入队
        if account_id:
            unprocessed = self._db.get_unprocessed_email_ids(account_id, limit=200)
            for eid in unprocessed:
                try:
                    self._queue.put_nowait(eid)
                except asyncio.QueueFull:
                    break

        await self._run_loop()

    def stop(self) -> None:
        """停止处理循环。"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    # ----------------------------------------------------------------
    # 内部循环
    # ----------------------------------------------------------------

    async def _run_loop(self) -> None:
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                email_id = await asyncio.wait_for(self._queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            await self._process_with_retry(email_id, loop)
            self._queue.task_done()

    async def _process_with_retry(self, email_id: str, loop) -> None:
        """带指数退避重试的单封邮件 AI 处理。"""
        email = self._db.get_email(email_id)
        if not email:
            return

        # 跳过草稿、回收站（垃圾邮件需 AI 判断真假；已发送提取摘要和联系人记忆）
        if email.folder in ("草稿箱", "已删除"):
            return

        is_sent = email.folder == "已发送"
        self.processing_started.emit(email_id, self._queue.qsize())
        last_error = ""
        for attempt in range(MAX_RETRIES):
            try:
                meta = await loop.run_in_executor(
                    None, self._processor.process_email, email, email.account_id, is_sent
                )
                self._db.update_email_ai_metadata(meta)
                # 双向垃圾邮件检测：根据 is_spam 结果自动移动邮件
                if self._move_callback and meta.is_spam is not None and email.imap_uid:
                    if email.folder == "垃圾邮件" and meta.is_spam is False:
                        await self._move_callback(email_id, email.imap_uid, "垃圾邮件", "INBOX")
                    elif email.folder == "INBOX" and meta.is_spam is True:
                        await self._move_callback(email_id, email.imap_uid, "INBOX", "垃圾邮件")
                # 行动项存入 email_ai_metadata，由用户在邮件详情页手动选择加入待办
                self.email_processed.emit(email_id, meta.ai_status)
                return

            except AIProcessingError as e:
                last_error = str(e)
                print(f"[AIService] 处理邮件 {email_id[:8]} 第{attempt+1}次失败: {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF[attempt])

            except Exception as e:
                last_error = str(e)
                print(f"[AIService] 处理邮件 {email_id[:8]} 意外错误: {e}")
                break  # 非预期错误直接写 failed

        # 写入 failed 状态
        failed_meta = EmailAIMetadata(
            email_id=email_id,
            ai_status="failed",
            processing_error=last_error or f"重试 {MAX_RETRIES} 次后仍失败",
            processed_at=datetime.utcnow(),
        )
        self._db.update_email_ai_metadata(failed_meta)
        self.email_processed.emit(email_id, "failed")
