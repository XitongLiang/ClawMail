"""
Account 域模型
字段定义以 design/userDataStorageDesign.md accounts 表为准。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Account:
    id: str                                    # UUID
    email_address: str                         # 完整邮箱地址
    display_name: Optional[str] = None
    provider_type: str = "imap"               # imap/gmail/exchange
    is_enabled: bool = True

    # IMAP/SMTP 配置
    imap_server: Optional[str] = None
    imap_port: int = 993
    smtp_server: Optional[str] = None
    smtp_port: int = 465
    credentials_encrypted: Optional[bytes] = None  # Fernet 加密，主密钥存 OS Keychain

    # 同步设置
    sync_interval_minutes: int = 2
    last_sync_at: Optional[datetime] = None
    sync_cursor: Optional[str] = None          # IMAP 同步游标

    # 状态（规范值见 enums.AccountStatus）
    status: str = "active"                     # active/error/paused
    error_message: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
