"""
MemoryBank — MemSkill 用户偏好记忆管理
负责记忆的检索、格式化（用于注入 AI prompt）和写入操作。
"""

from typing import Dict, List, Optional

from clawmail.domain.models.memory import UserMemory


# 记忆类型与中文显示名映射
_MEMORY_TYPE_LABELS = {
    "sender_importance": "发件人偏好",
    "urgency_signal": "紧急信号偏好",
    "automated_content": "自动邮件识别",
    "summary_preference": "摘要偏好",
    "response_pattern": "回复风格偏好",
}


# 邮件分析（importance + summary）使用的记忆类型
_EMAIL_ANALYSIS_TYPES = [
    "sender_importance", "urgency_signal", "automated_content", "summary_preference",
]


class MemoryBank:
    """用户偏好记忆的检索与管理。"""

    def __init__(self, db):
        """db: ClawDB 实例。"""
        self._db = db

    # --------------------------------------------------------
    # 检索
    # --------------------------------------------------------

    def retrieve_for_email(
        self,
        account_id: str,
        sender_email: Optional[str] = None,
        sender_domain: Optional[str] = None,
    ) -> List[UserMemory]:
        """检索与当前邮件相关的偏好记忆（仅 importance + summary 相关类型）。"""
        if not sender_email and not sender_domain:
            return self._db.get_all_memories(account_id, memory_types=_EMAIL_ANALYSIS_TYPES)
        return self._db.get_memories_for_email(
            account_id,
            sender_email or "",
            sender_domain or "",
            memory_types=_EMAIL_ANALYSIS_TYPES,
        )

    def retrieve_for_reply(
        self,
        account_id: str,
        recipient_email: Optional[str] = None,
    ) -> List[UserMemory]:
        """检索与回复相关的偏好记忆（response_pattern + summary_preference）。"""
        memories = []
        # 通用回复偏好
        for m in self._db.get_memories_by_type(account_id, "response_pattern"):
            if m.memory_key is None or m.memory_key == recipient_email:
                memories.append(m)
        # 摘要偏好（回复中也会参考用户对摘要风格的偏好）
        memories.extend(
            self._db.get_memories_by_type(account_id, "summary_preference")
        )
        return memories

    # --------------------------------------------------------
    # 格式化（用于注入 AI prompt）
    # --------------------------------------------------------

    def format_memories_for_prompt(
        self,
        memories: List[UserMemory],
        task_type: str = "email_analysis",
    ) -> str:
        """将记忆列表格式化为可注入 AI prompt 的中文文本段。

        task_type:
            - "email_analysis": 邮件分析（importance + summary）
            - "reply_draft": 回复草稿
        """
        if not memories:
            return ""

        # 按类型分组
        grouped: Dict[str, List[UserMemory]] = {}
        for m in memories:
            grouped.setdefault(m.memory_type, []).append(m)

        parts = []

        if task_type == "email_analysis":
            parts.append("【用户偏好记忆】\n以下是根据用户历史反馈学习到的个性化偏好，请在分析时参考：\n")
            # importance 相关
            for mtype in ("sender_importance", "urgency_signal", "automated_content"):
                items = grouped.get(mtype, [])
                if items:
                    label = _MEMORY_TYPE_LABELS.get(mtype, mtype)
                    parts.append(f"{label}：")
                    for m in items:
                        content = m.memory_content or {}
                        pattern = content.get("pattern", "")
                        if pattern:
                            parts.append(f"- {pattern}")
                        else:
                            # 回退到直接展示 content 关键字段
                            parts.append(f"- {_format_content_fallback(content)}")
                    parts.append("")
            # summary 相关
            items = grouped.get("summary_preference", [])
            if items:
                parts.append(f"{_MEMORY_TYPE_LABELS['summary_preference']}：")
                for m in items:
                    content = m.memory_content or {}
                    pattern = content.get("pattern", content.get("desired", ""))
                    if pattern:
                        parts.append(f"- {pattern}")
                parts.append("")

        elif task_type == "reply_draft":
            parts.append("【用户回复风格偏好】\n以下是根据用户历史反馈学习到的回复偏好，请在起草时参考：\n")
            items = grouped.get("response_pattern", [])
            if items:
                for m in items:
                    content = m.memory_content or {}
                    pattern = content.get("pattern", content.get("preference", ""))
                    if pattern:
                        parts.append(f"- {pattern}")
                parts.append("")
            # 摘要偏好也参考
            items = grouped.get("summary_preference", [])
            if items:
                parts.append("摘要偏好（参考）：")
                for m in items:
                    content = m.memory_content or {}
                    pattern = content.get("pattern", "")
                    if pattern:
                        parts.append(f"- {pattern}")
                parts.append("")

        text = "\n".join(parts).strip()
        return text

    # --------------------------------------------------------
    # 写入操作（由 Executor 调用）
    # --------------------------------------------------------

    def apply_memory_operations(
        self,
        account_id: str,
        operations: List[Dict],
    ) -> int:
        """应用 Executor 输出的记忆操作（insert / update / delete），返回执行数量。"""
        import uuid

        count = 0
        print(f"[MemSkill] 开始应用 {len(operations)} 条记忆操作 (account={account_id[:8]}...)")
        for op in operations:
            try:
                action = op.get("op", "").lower()
                if action == "insert":
                    memory = UserMemory(
                        id=str(uuid.uuid4()),
                        user_account_id=account_id,
                        memory_type=op["memory_type"],
                        memory_key=op.get("memory_key"),
                        memory_content=op.get("content", {}),
                        confidence_score=float(op.get("confidence", 0.5)),
                        evidence_count=1,
                    )
                    self._db.upsert_memory(memory)
                    count += 1
                    print(f"[MemSkill] INSERT: type={memory.memory_type}, key={memory.memory_key}, confidence={memory.confidence_score}")

                elif action == "update":
                    memory_id = op.get("memory_id")
                    if not memory_id:
                        print(f"[MemSkill] UPDATE 跳过: memory_id 为空")
                        continue
                    # 通过 memory_id 直接查找
                    found = False
                    for m in self._db.get_all_memories(account_id):
                        if m.id == memory_id:
                            m.memory_content = op.get("content", m.memory_content)
                            m.confidence_score = float(
                                op.get("confidence", m.confidence_score)
                            )
                            m.evidence_count += 1
                            self._db.upsert_memory(m)
                            count += 1
                            found = True
                            print(f"[MemSkill] UPDATE: id={memory_id[:8]}..., type={m.memory_type}, evidence={m.evidence_count}")
                            break
                    if not found:
                        print(f"[MemSkill] UPDATE 失败: 找不到 memory_id={memory_id}")

                elif action == "delete":
                    memory_id = op.get("memory_id")
                    if memory_id:
                        self._db.delete_memory(memory_id)
                        count += 1
                        print(f"[MemSkill] DELETE: id={memory_id}")
            except Exception as e:
                print(f"[MemSkill] 记忆操作失败: {action} - {e}")
                continue
        print(f"[MemSkill] 记忆操作完成: {count}/{len(operations)} 条成功")
        return count


def _format_content_fallback(content: dict) -> str:
    """当 memory_content 没有 pattern 字段时，格式化关键字段为可读文本。"""
    parts = []
    for key in ("sender_email", "sender_name", "signal", "source",
                 "preference_type", "context", "preference"):
        val = content.get(key)
        if val:
            parts.append(f"{key}={val}")
    score = content.get("typical_score")
    if score is not None:
        parts.append(f"typical_score={score}")
    return ", ".join(parts) if parts else str(content)[:100]
