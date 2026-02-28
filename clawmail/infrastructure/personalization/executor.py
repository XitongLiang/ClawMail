"""
Executor — MemSkill 记忆提取执行器
当用户修正 AI 预测时，Executor 分析差异并提取/更新用户偏好记忆。
使用 OpenClawBridge 调用 LLM 完成分析。
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from clawmail.infrastructure.personalization.memory_bank import MemoryBank
from clawmail.infrastructure.personalization.skill_bank import SkillBank


# Executor prompt 模板
_EXECUTOR_PROMPT = """你是 ClawMail 的个性化记忆管理执行器。

你的任务：分析 AI 预测与用户修正之间的差异，从中提取用户偏好并输出记忆操作。

【当前邮件】
{email_data}

【AI 预测】
{prediction}

【用户修正】
{correction}

【已有用户记忆】
{existing_memories}

【可用技能（全部应用）】
{skills}

【指令】
- 逐个应用上述技能，分析用户修正背后的偏好
- 如果发现新偏好，输出 INSERT 操作
- 如果已有记忆需要更新（同一发件人/同类偏好），输出 UPDATE 操作并指定 memory_id
- 如果已有记忆明显错误，输出 DELETE 操作
- 不要输出没有依据的猜测，只基于实际的修正差异
- 如果修正幅度很小（< 10分）或无法推断偏好，输出空数组

【输出要求】
严格返回 JSON 数组，不要 Markdown 标记：
[
  {{"op": "insert", "memory_type": "类型", "memory_key": "键或null", "content": {{}}, "confidence": 0.7}},
  {{"op": "update", "memory_id": "已有记忆ID", "content": {{}}, "confidence": 0.8}},
  {{"op": "delete", "memory_id": "已有记忆ID", "reason": "原因"}}
]

如果没有值得记录的偏好，返回空数组：[]

重要：直接返回 JSON 数组，不要任何分析过程、Markdown 标记或解释文字。"""


# System prompt: 强制 LLM 只返回 JSON
_EXECUTOR_SYSTEM_PROMPT = (
    "你是一个 JSON 输出机器。你的唯一任务是根据用户的指令返回一个 JSON 数组。"
    "不要输出任何分析过程、解释、Markdown 标记或其他文字。"
    "只输出一个合法的 JSON 数组，以 [ 开头，以 ] 结尾。"
)


class Executor:
    """MemSkill 记忆提取执行器。异步调用 LLM 分析用户修正并更新记忆。"""

    def __init__(
        self, bridge, memory_bank: MemoryBank, skill_bank: SkillBank,
        log_dir: Optional[Path] = None,
    ):
        """
        bridge: OpenClawBridge 实例
        memory_bank: MemoryBank 实例
        skill_bank: SkillBank 实例
        log_dir: 日志目录（用于写入 executor_log.jsonl，供 Designer 分析）
        """
        self._bridge = bridge
        self._memory_bank = memory_bank
        self._skill_bank = skill_bank
        self._log_dir = log_dir

    def execute_importance_feedback(
        self,
        account_id: str,
        email_data: Dict,
        original_score: int,
        new_score: int,
        sender_email: Optional[str] = None,
        sender_domain: Optional[str] = None,
    ) -> int:
        """处理重要性评分修正，提取/更新记忆。返回记忆操作数量。
        此方法为同步调用，应通过 run_in_executor 在线程池中执行。"""
        diff = abs(original_score - new_score)
        if diff < 10:
            print(f"[MemSkill Executor] 重要性修正幅度过小 ({diff})，跳过")
            return 0

        print(f"[MemSkill Executor] 处理重要性修正: {original_score} → {new_score} (差异={diff}, sender={sender_email})")
        existing = self._memory_bank.retrieve_for_email(
            account_id, sender_email, sender_domain
        )
        prediction = f"重要性评分: {original_score}/100"
        correction = f"用户修正为: {new_score}/100（差异: {diff}）"

        return self._run(account_id, email_data, prediction, correction, existing, "importance")

    def execute_summary_feedback(
        self,
        account_id: str,
        email_data: Dict,
        original_summary: Dict,
        reasons: List[str],
        user_comment: Optional[str] = None,
        sender_email: Optional[str] = None,
        sender_domain: Optional[str] = None,
    ) -> int:
        """处理摘要差评反馈，提取/更新记忆。返回记忆操作数量。"""
        print(f"[MemSkill Executor] 处理摘要差评: reasons={reasons}, comment={user_comment}")
        existing = self._memory_bank.retrieve_for_email(
            account_id, sender_email, sender_domain
        )
        prediction = (
            f"AI 摘要:\n"
            f"- one_line: {original_summary.get('one_line', '')}\n"
            f"- brief: {original_summary.get('brief', '')}\n"
            f"- key_points: {original_summary.get('key_points', [])}\n"
            f"- keywords: {original_summary.get('keywords', [])}"
        )
        correction_parts = [f"用户反馈: 差评"]
        if reasons:
            correction_parts.append(f"问题原因: {', '.join(reasons)}")
        if user_comment:
            correction_parts.append(f"用户补充说明: {user_comment}")
        correction = "\n".join(correction_parts)

        return self._run(account_id, email_data, prediction, correction, existing, "summary")

    def execute_reply_feedback(
        self,
        account_id: str,
        email_data: Dict,
        ai_draft: str,
        user_final: str,
        similarity_ratio: float,
        stance: Optional[str] = None,
        tone: Optional[str] = None,
        recipient_email: Optional[str] = None,
    ) -> int:
        """处理回复草稿隐式反馈（用户修改了 AI 草稿），提取/更新记忆。"""
        if similarity_ratio >= 0.95:
            print(f"[MemSkill Executor] 回复草稿相似度过高 ({similarity_ratio:.2%})，跳过")
            return 0

        print(f"[MemSkill Executor] 处理回复修正: similarity={similarity_ratio:.2%}, recipient={recipient_email}")
        existing = self._memory_bank.retrieve_for_reply(
            account_id, recipient_email
        )
        prediction = (
            f"AI 回复草稿（立场: {stance or '未知'}, 语气: {tone or '未知'}）:\n"
            f"{ai_draft[:500]}"
        )
        correction = (
            f"用户最终版本（相似度: {similarity_ratio:.2%}）:\n"
            f"{user_final[:500]}"
        )

        return self._run(account_id, email_data, prediction, correction, existing, "reply")

    # --------------------------------------------------------
    # 内部实现
    # --------------------------------------------------------

    def _run(
        self,
        account_id: str,
        email_data: Dict,
        prediction: str,
        correction: str,
        existing_memories: List,
        feedback_type: str = "unknown",
    ) -> int:
        """构建 prompt → 调用 LLM → 解析结果 → 写入记忆 → 记录日志。"""
        # 格式化已有记忆
        if existing_memories:
            mem_lines = []
            for m in existing_memories:
                mem_lines.append(
                    f"- [id={m.id}] type={m.memory_type}, key={m.memory_key}, "
                    f"confidence={m.confidence_score:.2f}, "
                    f"content={json.dumps(m.memory_content, ensure_ascii=False)}"
                )
            existing_text = "\n".join(mem_lines)
        else:
            existing_text = "（暂无已有记忆）"

        # 格式化邮件数据
        email_text = json.dumps(email_data, ensure_ascii=False, indent=2)

        # 格式化技能
        skills_text = self._skill_bank.format_skills_for_prompt()

        # 构建 prompt
        prompt = _EXECUTOR_PROMPT.format(
            email_data=email_text,
            prediction=prediction,
            correction=correction,
            existing_memories=existing_text,
            skills=skills_text,
        )

        # 调用 LLM
        print(f"[MemSkill Executor] 调用 LLM (personalizationAgent001)...")
        raw = ""
        success = False
        operations: List[Dict] = []
        try:
            raw = self._bridge.user_chat(
                prompt,
                "personalizationAgent001",
                system_prompt=_EXECUTOR_SYSTEM_PROMPT,
            )
            operations = self._parse_response(raw)
            success = True
        except Exception as e:
            print(f"[MemSkill Executor] LLM 调用失败: {e}")

        # 记录日志（无论成功与否）
        self._save_log(
            account_id, feedback_type, email_data,
            prediction, correction, len(existing_memories),
            raw, operations, success,
        )

        if not success:
            return 0
        if not operations:
            print(f"[MemSkill Executor] LLM 返回无操作（空数组或解析失败）")
            return 0

        print(f"[MemSkill Executor] LLM 返回 {len(operations)} 条操作: {[op.get('op') for op in operations]}")
        return self._memory_bank.apply_memory_operations(account_id, operations)

    def _save_log(
        self, account_id: str, feedback_type: str, email_data: Dict,
        prediction: str, correction: str, existing_memory_count: int,
        llm_raw: str, operations: List[Dict], success: bool,
    ) -> None:
        """追加写入 executor_log.jsonl，供 Designer 分析。"""
        if not self._log_dir:
            return
        try:
            log_file = self._log_dir / "executor_log.jsonl"
            record = {
                "timestamp": datetime.utcnow().isoformat(),
                "account_id": account_id,
                "feedback_type": feedback_type,
                "email_data": email_data,
                "prediction": prediction[:300],
                "correction": correction[:300],
                "existing_memory_count": existing_memory_count,
                "llm_raw": llm_raw[:500],
                "operations": operations,
                "operation_count": len(operations),
                "success": success,
            }
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass  # 日志写入失败不影响主流程

    def _parse_response(self, raw: str) -> List[Dict]:
        """解析 LLM 返回的 JSON 数组。"""
        text = raw.strip()
        # 去掉可能的 Markdown 代码块包裹
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)

        try:
            result = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            # 尝试从文本中提取 JSON 数组
            match = re.search(r'\[.*\]', text, flags=re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group())
                except (json.JSONDecodeError, ValueError):
                    print(f"[Executor] JSON 解析失败: {text[:200]}")
                    return []
            else:
                print(f"[Executor] 未找到 JSON 数组: {text[:200]}")
                return []

        if not isinstance(result, list):
            return []

        # 验证每个操作的基本格式
        valid = []
        for op in result:
            if not isinstance(op, dict):
                continue
            action = op.get("op", "").lower()
            if action == "insert" and "memory_type" in op:
                valid.append(op)
            elif action == "update" and "memory_id" in op:
                valid.append(op)
            elif action == "delete" and "memory_id" in op:
                valid.append(op)
        return valid
