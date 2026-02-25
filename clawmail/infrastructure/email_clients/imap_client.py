"""
ClawIMAPClient — 异步 IMAP 收件客户端
使用 aioimaplib 1.1.0（原生 async），替代旧的同步 imapclient。
"""

import asyncio
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import aioimaplib

from clawmail.domain.models.account import Account
from clawmail.domain.models.email import Email


class IMAPAuthError(Exception):
    pass


class IMAPConnectionError(Exception):
    pass


class ClawIMAPClient:
    """
    异步 IMAP 客户端。
    一个实例对应一个账号的单个连接，不可复用于多账号。
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self._imap: Optional[aioimaplib.IMAP4_SSL] = None
        self._account_id: Optional[str] = None
        self._idle_task: Optional[asyncio.Task] = None
        self._data_dir: Optional[Path] = data_dir

    # ----------------------------------------------------------------
    # 连接管理
    # ----------------------------------------------------------------

    async def connect(self, account: Account, password: str) -> None:
        """建立 SSL IMAP 连接并登录。"""
        try:
            self._imap = aioimaplib.IMAP4_SSL(
                host=account.imap_server or "imap.163.com",
                port=account.imap_port or 993,
            )
            await self._imap.wait_hello_from_server()
        except Exception as e:
            raise IMAPConnectionError(f"连接 IMAP 服务器失败: {e}") from e

        status, data = await self._imap.login(account.email_address, password)
        if status != "OK":
            msg = data[0].decode() if data else "未知错误"
            raise IMAPAuthError(f"登录失败: {msg}")

        # 163.com 要求登录后发送 IMAP ID 命令，否则 search/fetch 被拒绝
        # 注意：aioimaplib 的 id(**kwargs) 会在括号内加空格，163.com 拒绝该格式，
        # 必须直接构造 Command 以确保格式为 ("name" "ClawMail" "version" "1.0")
        try:
            from aioimaplib.aioimaplib import Command
            tag = self._imap.protocol.new_tag()
            await self._imap.protocol.execute(
                Command('ID', tag, '("name" "ClawMail" "version" "1.0")',
                        loop=self._imap.protocol.loop)
            )
        except Exception:
            pass  # 部分服务器不支持 ID，忽略

        self._account_id = account.id

    async def disconnect(self) -> None:
        """登出并关闭连接。"""
        await self.stop_idle()
        if self._imap:
            try:
                await self._imap.logout()
            except Exception:
                pass
            self._imap = None

    # ----------------------------------------------------------------
    # 邮件同步
    # ----------------------------------------------------------------

    async def fetch_new_emails(
        self, folder: str, since_uid: Optional[str]
    ) -> List[Email]:
        """
        拉取指定文件夹中的新邮件。
        since_uid: 上次同步最大 UID（含），None 表示首次全量同步。
        返回解析后的 Email 列表，最新邮件在前。
        """
        status, data = await self._imap.select(folder)
        if status != "OK":
            raise IMAPConnectionError(f"无法选择文件夹 {folder}: {data}")

        # 构造 UID 搜索条件（aioimaplib 使用 uid_search，不支持通用 uid("search",...)）
        if since_uid:
            next_uid = int(since_uid) + 1
            status, data = await self._imap.uid_search('UID', f'{next_uid}:*')
        else:
            status, data = await self._imap.uid_search('ALL')
        if status != "OK":
            return []

        uid_str = data[0].decode().strip() if data and data[0] else ""
        if not uid_str:
            return []

        uid_list = [u for u in uid_str.split() if u.strip()]
        if not uid_list:
            return []

        # 如果是增量同步，过滤掉等于 since_uid 的 UID（search UID N:* 包含 N）
        if since_uid:
            uid_list = [u for u in uid_list if u != since_uid]
        if not uid_list:
            return []

        # 批量 fetch（每批最多 50 封，避免响应过大）
        results: List[tuple] = []  # List[(Email, List[dict])]
        batch_size = 50
        loop = asyncio.get_event_loop()

        for i in range(0, len(uid_list), batch_size):
            batch = uid_list[i : i + batch_size]
            uid_range = ",".join(batch)

            status, fetch_data = await self._imap.uid(
                "fetch", uid_range, "(FLAGS INTERNALDATE RFC822)"
            )
            if status != "OK":
                continue

            # aioimaplib 的 fetch 响应格式：交错的 header/literal 行
            parsed = self._extract_messages_from_fetch(fetch_data)
            for uid, raw_bytes in parsed.items():
                try:
                    result = await loop.run_in_executor(
                        None,
                        self._parse_raw_email,
                        uid,
                        raw_bytes,
                        self._account_id,
                        folder,
                    )
                    if result:
                        results.append(result)
                except Exception:
                    pass  # 解析单封邮件失败不影响其他邮件

        return results

    # ----------------------------------------------------------------
    # IDLE 推送监听
    # ----------------------------------------------------------------

    async def start_idle(
        self, folder: str, on_new_mail: Callable, timeout_seconds: int = 1200
    ) -> None:
        """
        在后台协程中监听 INBOX IDLE 推送。
        有新邮件到达时调用 on_new_mail()。
        timeout_seconds: IDLE 保持时长（默认 20 分钟），超时后重新发起。
        """
        await self.stop_idle()
        self._idle_task = asyncio.create_task(
            self._idle_loop(folder, on_new_mail, timeout_seconds)
        )

    async def delete_email_by_message_id(self, message_id: str) -> bool:
        """在 IMAP 服务器的所有文件夹中按 Message-ID 搜索并删除邮件。
        返回 True 表示至少在一个文件夹中删除成功。
        """
        try:
            # 列出服务器所有文件夹
            status, folder_list = await self._imap.list('""', "*")
            if status != "OK":
                return False

            # Message-ID 去掉两端 <> 后搜索更兼容
            mid = message_id.strip("<>").strip()
            deleted = False

            for line in folder_list:
                if not isinstance(line, bytes):
                    continue
                # 格式：(\Flags) "delimiter" "FolderName" 或 FolderName（无引号）
                decoded = line.decode(errors="replace")
                # 取最后一段作为文件夹名
                parts = decoded.rsplit('"', 1)
                folder = parts[-1].strip().strip('"') if len(parts) > 1 else decoded.split()[-1]
                if not folder or folder in (".", ".."):
                    continue

                sel_status, _ = await self._imap.select(folder)
                if sel_status != "OK":
                    continue

                search_status, data = await self._imap.uid_search(
                    "HEADER", "Message-ID", mid
                )
                if search_status != "OK":
                    continue

                uid_str = data[0].decode().strip() if data and data[0] else ""
                if not uid_str:
                    continue

                for uid in uid_str.split():
                    await self._imap.uid("store", uid, "+FLAGS", r"(\Deleted)")

                await self._imap.expunge()
                deleted = True

            return deleted
        except Exception:
            return False

    async def move_email(self, uid: str, from_folder: str, to_folder: str) -> bool:
        """将邮件从 from_folder 移动到 to_folder（UID COPY + 标记删除 + EXPUNGE）。"""
        try:
            await self._imap.select(from_folder)
            await self._imap.uid("copy", uid, to_folder)
            await self._imap.uid("store", uid, "+FLAGS", "\\Deleted")
            await self._imap.expunge()
            return True
        except Exception as e:
            print(f"[IMAPClient] 移动邮件失败 uid={uid}: {e}")
            return False

    async def stop_idle(self) -> None:
        """取消 IDLE 后台任务。"""
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
            try:
                await self._idle_task
            except asyncio.CancelledError:
                pass
        self._idle_task = None

    async def _idle_loop(
        self, folder: str, on_new_mail: Callable, timeout_seconds: int
    ) -> None:
        while True:
            try:
                status, _ = await self._imap.select(folder)
                if status != "OK":
                    await asyncio.sleep(30)
                    continue

                idle_task = await self._imap.idle_start(timeout=timeout_seconds)
                try:
                    msg = await asyncio.wait_for(
                        self._imap.wait_server_push(), timeout=timeout_seconds
                    )
                    if msg and any(b"EXISTS" in line for line in msg if isinstance(line, bytes)):
                        on_new_mail()
                except asyncio.TimeoutError:
                    pass
                finally:
                    await self._imap.idle_done()

            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(10)

    # ----------------------------------------------------------------
    # 内部解析工具
    # ----------------------------------------------------------------

    def _extract_messages_from_fetch(self, fetch_data: list) -> dict:
        """
        从 aioimaplib uid fetch 响应中提取 {uid: raw_bytes} 字典。

        aioimaplib 响应格式示例：
          [b'1 (UID 123 FLAGS (\\Seen) RFC822 {12345}',
           b'<12345 bytes of raw email>',
           b')',
           b'2 (UID 124 FLAGS () RFC822 {6789}',
           b'<6789 bytes>',
           b')', ...]
        """
        messages = {}
        current_uid = None

        for item in fetch_data:
            if not isinstance(item, (bytes, bytearray)):
                continue

            line = item.decode(errors="replace")

            # 识别含 RFC822 的 metadata 行（含 UID 和消息大小）
            if "RFC822" in line and "{" in line:
                uid_match = re.search(r"UID\s+(\d+)", line)
                if uid_match:
                    current_uid = uid_match.group(1)
                continue

            # metadata 行之后的第一个大字节块即为邮件内容
            if current_uid and len(item) > 100:
                messages[current_uid] = bytes(item)
                current_uid = None

        return messages

    def _parse_raw_email(
        self, uid: str, raw: bytes, account_id: str, folder: str
    ) -> Optional[Tuple["Email", List[dict]]]:
        """将 RFC822 原始字节解析为 (Email, attachments) 元组（在线程池中执行）。
        attachments: [{"filename", "content_type", "size_bytes", "storage_path"}]
        """
        msg = message_from_bytes(raw)

        # 主题
        subject = self._decode_header_value(msg.get("Subject", ""))

        # 发件人
        from_raw = self._decode_header_value(msg.get("From", ""))
        from_name, from_email = parseaddr(from_raw)
        from_address = {"name": from_name or from_email, "email": from_email}

        # 收件人
        to_addresses = self._parse_address_list(msg.get("To", ""))
        cc_addresses = self._parse_address_list(msg.get("Cc", ""))

        # Message-ID
        message_id = (msg.get("Message-ID") or "").strip()

        # 日期
        sent_at = None
        date_str = msg.get("Date")
        if date_str:
            try:
                sent_at = parsedate_to_datetime(date_str)
                if sent_at.tzinfo is not None:
                    sent_at = sent_at.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                sent_at = None

        # 正文 + 内联图片 + 附件
        email_id = str(uuid.uuid4())
        body_text, body_html, inline_images, raw_attachments = self._extract_body(msg)
        if inline_images and body_html and self._data_dir:
            body_html = self._save_inline_images(email_id, body_html, inline_images)

        saved_attachments: List[dict] = []
        if raw_attachments and self._data_dir:
            att_dir = self._data_dir / "attachments" / email_id
            att_dir.mkdir(parents=True, exist_ok=True)
            for att in raw_attachments:
                safe_name = re.sub(r"[^\w\-.]", "_", att["filename"])
                filepath = att_dir / safe_name
                filepath.write_bytes(att["data"])
                saved_attachments.append({
                    "filename": att["filename"],
                    "content_type": att["content_type"],
                    "size_bytes": len(att["data"]),
                    "storage_path": str(filepath),
                })

        # Thread ID（用 In-Reply-To 或 Message-ID 构造）
        in_reply_to = msg.get("In-Reply-To", "").strip()
        thread_id = in_reply_to or message_id or str(uuid.uuid4())

        # Hash（去重）
        hash_src = (message_id + subject + (body_text or "")[:200]).encode()
        email_hash = hashlib.sha256(hash_src).hexdigest()

        email = Email(
            id=email_id,
            account_id=account_id,
            imap_uid=uid,
            message_id=message_id or None,
            subject=subject or "(无主题)",
            from_address=from_address,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses if cc_addresses else None,
            body_text=body_text,
            body_html=body_html,
            content_type=msg.get_content_type(),
            charset=msg.get_content_charset() or "utf-8",
            sent_at=sent_at,
            received_at=datetime.utcnow(),
            size_bytes=len(raw),
            hash=email_hash,
            sync_status="completed",
            is_downloaded=True,
            folder=folder,
            thread_id=thread_id,
            in_reply_to=in_reply_to or None,
        )
        return email, saved_attachments

    def _decode_header_value(self, value: str) -> str:
        """解码 RFC2047 编码的邮件头（Base64/QP 中文）。"""
        if not value:
            return ""
        try:
            return str(make_header(decode_header(value)))
        except Exception:
            return value

    def _parse_address_list(self, value: str) -> Optional[List[dict]]:
        """将地址列表字符串解析为 [{"name": ..., "email": ...}, ...] 格式。"""
        if not value:
            return None
        result = []
        for part in value.split(","):
            part = part.strip()
            if not part:
                continue
            name, addr = parseaddr(self._decode_header_value(part))
            result.append({"name": name or addr, "email": addr})
        return result if result else None

    def _extract_body(
        self, msg
    ) -> Tuple[Optional[str], Optional[str], Dict[str, Tuple[bytes, str]], List[dict]]:
        """从 MIME 消息中提取纯文本、HTML 正文、内联图片和附件。
        返回 (body_text, body_html, inline_images, attachments)
        inline_images: {content_id: (bytes, content_type)}
        attachments: [{"filename", "content_type", "data"}]
        """
        body_text = None
        body_html = None
        inline_images: Dict[str, Tuple[bytes, str]] = {}
        attachments: List[dict] = []

        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                cd = str(part.get("Content-Disposition") or "")

                # 收集内联图片（有 Content-ID 的图片部件）
                cid_raw = part.get("Content-ID", "").strip().strip("<>")
                if cid_raw and part.get_content_maintype() == "image":
                    payload = part.get_payload(decode=True)
                    if payload:
                        inline_images[cid_raw] = (payload, ct)
                    continue

                # 收集附件
                if "attachment" in cd:
                    payload = part.get_payload(decode=True)
                    if payload:
                        filename = part.get_filename() or f"attachment_{len(attachments) + 1}"
                        try:
                            filename = str(make_header(decode_header(filename)))
                        except Exception:
                            pass
                        attachments.append({
                            "filename": filename,
                            "content_type": ct,
                            "data": payload,
                        })
                    continue

                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                try:
                    text = payload.decode(charset, errors="replace")
                except (LookupError, Exception):
                    text = payload.decode("utf-8", errors="replace")

                if ct == "text/plain" and body_text is None:
                    body_text = text
                elif ct == "text/html" and body_html is None:
                    body_html = text
        else:
            charset = msg.get_content_charset() or "utf-8"
            payload = msg.get_payload(decode=True)
            if payload:
                try:
                    text = payload.decode(charset, errors="replace")
                except (LookupError, Exception):
                    text = payload.decode("utf-8", errors="replace")
                ct = msg.get_content_type()
                if ct == "text/html":
                    body_html = text
                else:
                    body_text = text

        return body_text, body_html, inline_images, attachments

    def _save_inline_images(
        self, email_id: str, body_html: str,
        inline_images: Dict[str, Tuple[bytes, str]]
    ) -> str:
        """将内联图片保存到磁盘，并将 body_html 中的 cid: 替换为 file:// 路径。"""
        _EXT_MAP = {
            "image/jpeg": "jpg", "image/jpg": "jpg",
            "image/png": "png", "image/gif": "gif",
            "image/webp": "webp", "image/bmp": "bmp",
        }
        img_dir = self._data_dir / "attachments" / email_id
        img_dir.mkdir(parents=True, exist_ok=True)

        for cid, (img_bytes, content_type) in inline_images.items():
            ext = _EXT_MAP.get(content_type.lower(), "bin")
            safe_name = re.sub(r"[^\w\-.]", "_", cid) + f".{ext}"
            filepath = img_dir / safe_name
            filepath.write_bytes(img_bytes)
            # 替换 src="cid:xxx" 和 src='cid:xxx'（Content-ID 可能含 @ 等符号）
            escaped = re.escape(cid)
            body_html = re.sub(
                rf"cid:{escaped}",
                filepath.as_uri(),
                body_html,
            )

        return body_html
