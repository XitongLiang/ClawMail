"""
UserMemory / Skill 域模型
MemSkill 个性化系统的核心数据结构。
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


@dataclass
class Skill:
    """记忆提取技能定义。"""
    id: str                          # UUID
    skill_name: str                  # 唯一名称，如 extract_sender_importance
    skill_type: str                  # insert | update | delete
    description: str                 # 简短描述
    instruction_template: str        # 执行器使用的指令模板
    version: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
