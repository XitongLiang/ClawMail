"""
Email / EmailAIMetadata 域模型
字段定义以 design/userDataStorageDesign.md emails / email_ai_metadata 表为准。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Email:
    id: str                                    # UUID
    account_id: str

    # 信封信息
    imap_uid: Optional[str] = None
    message_id: Optional[str] = None
    subject: Optional[str] = None
    from_address: Optional[Dict] = None        # {"name": "", "email": ""}
    to_addresses: Optional[List[Dict]] = None  # JSON 数组
    cc_addresses: Optional[List[Dict]] = None
    bcc_addresses: Optional[List[Dict]] = None

    # 内容
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    content_type: Optional[str] = None
    charset: str = "utf-8"

    # 时间
    sent_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    internal_date: Optional[datetime] = None

    # 原始数据
    raw_headers: Optional[Dict] = None
    size_bytes: Optional[int] = None
    hash: Optional[str] = None                # 内容哈希，用于去重

    # 同步状态（规范值见 enums.EmailSyncStatus）
    sync_status: str = "pending"
    is_downloaded: bool = False

    # 用户操作状态（规范值见 enums.EmailReadStatus/FlagStatus/ReplyStatus）
    read_status: str = "unread"
    flag_status: str = "none"
    reply_status: str = "no_need"
    folder: str = "INBOX"
    imap_folder: Optional[str] = None        # 原始 IMAP 文件夹，软删除后不变
    pinned: bool = False

    # 关联
    thread_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    references: Optional[List[str]] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class EmailAIMetadata:
    email_id: str                              # 关联 emails.id

    # 统一提取结果（来自 Prompt #1）
    summary: Optional[Dict] = None            # {"keywords":[], "one_line":"", "brief":""}
    categories: Optional[List[str]] = None    # 规范值见 tech_spec.md 第 3 节
    sentiment: Optional[str] = None           # positive/negative/neutral
    suggested_reply: Optional[str] = None     # AI 生成的建议回复草稿
    is_spam: Optional[bool] = None            # AI 判断是否为垃圾邮件
    action_items: Optional[List[Dict]] = None  # AI 提取的行动项（来自 Prompt #1）
    reply_stances: Optional[List[str]] = None  # AI 预生成的 2-4 个回复立场选项
    importance_score: Optional[int] = None       # 0-100，AI 评估的邮件重要性

    # 处理状态（规范值见 enums.EmailAIStatus）
    ai_status: str = "unprocessed"
    processing_progress: int = 0              # 0-100
    processing_stage: Optional[str] = None
    processed_at: Optional[datetime] = None
    processing_error: Optional[str] = None

    # 向量嵌入（Phase 5，ChromaDB）
    embedding_vector: Optional[bytes] = None

    updated_at: Optional[datetime] = None

    # ── 向后兼容属性（旧字段已合并到 summary dict） ──
    @property
    def keywords(self) -> List[str]:
        return (self.summary or {}).get("keywords", [])

    @property
    def summary_one_line(self) -> str:
        return (self.summary or {}).get("one_line", "")

    @property
    def summary_brief(self) -> str:
        return (self.summary or {}).get("brief", "")


