"""
UserMemory 域模型
用户偏好记忆数据结构，由 clawmail-executor skill 写入，analyzer skill 读取注入 prompt。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional


@dataclass
class UserMemory:
    """用户偏好记忆条目。"""
    id: str                          # UUID
    user_account_id: str             # 所属用户账户

    # 记忆分类
    memory_type: str                 # sender_importance | urgency_signal | automated_content | summary_preference | response_pattern
    memory_key: Optional[str] = None # 查找键（发件人邮箱、域名等），全局偏好为 None

    # 内容
    memory_content: Optional[Dict] = None  # JSON 编码的偏好数据

    # 置信度
    confidence_score: float = 0.5    # 0.0 - 1.0
    evidence_count: int = 1          # 支撑证据数量

    # 时间
    last_updated: Optional[datetime] = None
    created_at: Optional[datetime] = None
