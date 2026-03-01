"""
ClawMail 枚举定义 — 单一来源
所有枚举值与 design/tech_spec.md 第 2 节保持一致。
"""

from enum import Enum


class EmailSyncStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


class EmailAIStatus(str, Enum):
    UNPROCESSED = "unprocessed"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"        # AI 出错，可重试
    SKIPPED = "skipped"      # 有意跳过，不重试


class EmailReadStatus(str, Enum):
    UNREAD = "unread"
    READ = "read"
    SKIMMED = "skimmed"


class EmailFlagStatus(str, Enum):
    NONE = "none"
    FLAGGED = "flagged"
    COMPLETED = "completed"


class EmailReplyStatus(str, Enum):
    NO_NEED = "no_need"
    PENDING = "pending"
    REPLIED = "replied"
    FORWARDED = "forwarded"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SNOOZED = "snoozed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"    # 仅 AI 提取的任务
    ARCHIVED = "archived"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    ERROR = "error"
    PAUSED = "paused"


class TaskSourceType(str, Enum):
    EXTRACTED = "extracted"  # 从邮件 AI 提取
    MANUAL = "manual"
    TEMPLATE = "template"
    RECURRING = "recurring"


class TaskPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class AISentiment(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
