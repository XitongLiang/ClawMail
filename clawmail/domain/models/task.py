"""
Task 域模型
字段定义以 design/ToDoListDesign.md 为权威来源，
design/userDataStorageDesign.md tasks 表为简化概览。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Task:
    id: str                                    # UUID
    title: str

    # 来源
    source_email_id: Optional[str] = None     # 关联邮件（可为空）
    source_task_index: Optional[int] = None   # 邮件中的第几个任务
    source_type: str = "manual"               # extracted/manual/template/recurring（规范值见 enums.TaskSourceType）

    # 内容
    description: Optional[str] = None

    # 状态（规范值见 enums.TaskStatus）
    status: str = "pending"
    priority: str = "medium"                  # high/medium/low（规范值见 enums.TaskPriority）
    is_flagged: bool = False

    # 时间
    due_date: Optional[datetime] = None
    due_date_source: Optional[str] = None     # ai_extracted/user_set/inferred
    snoozed_until: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # 分类
    category: Optional[str] = None
    tags: Optional[List[str]] = None

    # 扩展数据（JSON：子任务、提醒等）
    metadata: Optional[Dict] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
