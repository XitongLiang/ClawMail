"""
GraphSyncClient — Microsoft Graph API 邮件客户端
使用 REST API 替代 IMAP/SMTP，解决 Microsoft IMAP regression（2024~）。
同步方法，通过 run_in_executor 在线程池中执行。
"""

import base64
import hashlib
import json
import mimetypes
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

import httpx

from clawmail.domain.models.email import Email

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# (well-known folder id, display name stored in DB)
GRAPH_FOLDERS: List[Tuple[str, str]] = [
    ("inbox",      "INBOX"),
    ("junkemail",  "Junk Email"),
    ("sentitems",  "Sent Items"),
]

# display name → well-known id (for move operations)
GRAPH_FOLDER_ID_MAP = {
    "INBOX":       "inbox",
    "Junk Email":  "junkemail",
    "Sent Items":  "sentitems",
    "Drafts":      "drafts",
    "Deleted Items": "deleteditems",
}

_SELECT_FIELDS = (
    "id,subject,from,toRecipients,ccRecipients,receivedDateTime,"
    "bodyPreview,body,isRead,conversationId,internetMessageId,hasAttachments"
)


class GraphAuthError(Exception):
    pass


class GraphAPIError(Exception):
    pass


class GraphSyncClient:
    """同步 Graph API 客户端，每个方法可在线程池中独立调用。"""

    def __init__(self, data_dir: Optional[Path] = None):
        self._data_dir = data_dir

    # ----------------------------------------------------------------
    # HTTP helpers
    # ----------------------------------------------------------------

    def _get(self, access_token: str, url: str, params: dict = None) -> dict:
        with httpx.Client(timeout=30, trust_env=False) as client:
            resp = client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params or {},
            )
        if resp.status_code == 401:
            raise GraphAuthError("Token expired or invalid")
        if not resp.is_success:
            raise GraphAPIError(f"{resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def _post_json(self, access_token: str, url: str, body: dict) -> dict:
        with httpx.Client(timeout=60, trust_env=False) as client:
            resp = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        if resp.status_code == 401:
            raise GraphAuthError("Token expired or invalid")
        if not resp.is_success:
            raise GraphAPIError(f"{resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else {}

    # ----------------------------------------------------------------
    # Delta sync
    # ----------------------------------------------------------------

    def fetch_folder_delta(
        self,
        access_token: str,
        folder_id: str,
        delta_link: Optional[str],
        account_id: str,
        folder_display: str,
    ) -> Tuple[List[Tuple[Email, List[dict]]], str]:
        """
        增量拉取文件夹邮件。
        delta_link=None 时首次全量同步；传入 delta_link 时仅返回变更。
        返回 ([(Email, attachments)], new_delta_link)
        """
        if delta_link:
            url = delta_link
            params = None
        else:
            url = f"{GRAPH_BASE}/me/mailFolders/{folder_id}/messages/delta"
            params = {"$select": _SELECT_FIELDS, "$top": "50"}

        results: List[Tuple[Email, List[dict]]] = []
        new_delta_link = ""

        while url:
            data = self._get(access_token, url, params)
            params = None  # only first request uses params

            for msg in data.get("value", []):
                try:
                    email, atts = self._parse_graph_message(msg, account_id, folder_display)
                    results.append((email, atts))
                except Exception:
                    pass

            new_delta_link = data.get("@odata.deltaLink", new_delta_link)
            url = data.get("@odata.nextLink")  # follow pages; None when done

        return results, new_delta_link

    # ----------------------------------------------------------------
    # Send
    # ----------------------------------------------------------------

    def send_message(
        self,
        access_token: str,
        account_email: str,
        to_addresses: list,
        subject: str,
        body: str,
        cc_addresses: list = None,
        html_body: str = None,
        attachments: list = None,  # file paths
    ) -> None:
        """通过 Graph /me/sendMail 发送邮件。"""
        message: dict = {
            "subject": subject,
            "body": {
                "contentType": "HTML" if html_body else "Text",
                "content": html_body if html_body else body,
            },
            "toRecipients": [
                {"emailAddress": {"address": addr}} for addr in to_addresses
            ],
        }
        if cc_addresses:
            message["ccRecipients"] = [
                {"emailAddress": {"address": addr}} for addr in cc_addresses
            ]

        if attachments:
            att_list = []
            for path in attachments:
                try:
                    with open(path, "rb") as f:
                        data = f.read()
                    ctype, _ = mimetypes.guess_type(path)
                    att_list.append({
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": os.path.basename(path),
                        "contentType": ctype or "application/octet-stream",
                        "contentBytes": base64.b64encode(data).decode(),
                    })
                except OSError:
                    pass
            if att_list:
                message["attachments"] = att_list

        self._post_json(access_token, f"{GRAPH_BASE}/me/sendMail", {"message": message})

    # ----------------------------------------------------------------
    # Move
    # ----------------------------------------------------------------

    def move_message(
        self,
        access_token: str,
        message_id: str,
        destination_folder_id: str,
    ) -> bool:
        """将邮件移动到目标文件夹（使用 well-known 名称或文件夹 ID）。"""
        try:
            self._post_json(
                access_token,
                f"{GRAPH_BASE}/me/messages/{message_id}/move",
                {"destinationId": destination_folder_id},
            )
            return True
        except Exception:
            return False

    # ----------------------------------------------------------------
    # Parse
    # ----------------------------------------------------------------

    def _parse_graph_message(
        self, msg: dict, account_id: str, folder: str
    ) -> Tuple[Email, List[dict]]:
        """将 Graph API 消息 JSON 转换为 Email 模型。"""
        email_id = str(uuid.uuid4())

        # 发件人
        from_ep = (msg.get("from") or {}).get("emailAddress", {})
        from_address = {
            "name": from_ep.get("name") or from_ep.get("address", ""),
            "email": from_ep.get("address", ""),
        }

        # 收件人
        def _parse_recips(lst):
            if not lst:
                return None
            return [
                {
                    "name": r["emailAddress"].get("name", ""),
                    "email": r["emailAddress"].get("address", ""),
                }
                for r in lst if r.get("emailAddress")
            ]

        to_addresses = _parse_recips(msg.get("toRecipients"))
        cc_addresses = _parse_recips(msg.get("ccRecipients"))

        # 时间
        sent_at = None
        dt_str = msg.get("receivedDateTime", "")
        if dt_str:
            try:
                sent_at = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                sent_at = sent_at.astimezone(timezone.utc).replace(tzinfo=None)
            except Exception:
                pass

        # 正文
        body_obj = msg.get("body", {})
        ct = body_obj.get("contentType", "text").lower()
        content = body_obj.get("content", "")
        body_html = content if ct == "html" else None
        body_text = msg.get("bodyPreview", "") if ct == "html" else content

        # 标识符
        graph_id = msg.get("id", "")
        message_id = msg.get("internetMessageId", "")
        thread_id = msg.get("conversationId") or message_id or graph_id

        # 去重 hash（与 IMAP 解析保持相同格式）
        subject = msg.get("subject") or "(无主题)"
        hash_src = (message_id + subject + (body_text or "")[:200]).encode()
        email_hash = hashlib.sha256(hash_src).hexdigest()

        email = Email(
            id=email_id,
            account_id=account_id,
            imap_uid=graph_id,          # Graph message ID，用于 move/delete
            message_id=message_id or None,
            subject=subject,
            from_address=from_address,
            to_addresses=to_addresses,
            cc_addresses=cc_addresses,
            body_text=body_text,
            body_html=body_html,
            content_type="text/html" if body_html else "text/plain",
            charset="utf-8",
            sent_at=sent_at,
            received_at=datetime.utcnow(),
            size_bytes=len(content.encode("utf-8", errors="replace")),
            hash=email_hash,
            sync_status="completed",
            is_downloaded=True,
            folder=folder,
            thread_id=thread_id,
            in_reply_to=None,
        )
        return email, []
