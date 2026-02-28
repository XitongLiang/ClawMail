"""
Designer — MemSkill 技能演化器
定期分析 Executor 的失败案例，自动改进或新增记忆提取技能。
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from clawmail.domain.models.memory import Skill
from clawmail.infrastructure.personalization.skill_bank import SkillBank


# Designer 触发阈值：累计多少次 Executor 日志后触发
_TRIGGER_THRESHOLD = 25

# 传给 LLM 的最大硬案例数
_MAX_HARD_CASES = 20

# --------------------------------------------------------
# LLM Prompt 模板
# --------------------------------------------------------

_ANALYSIS_SYSTEM_PROMPT = (
    "你是一个 JSON 输出机器。只输出合法 JSON 对象，不要 Markdown 标记或解释文字。"
)

_ANALYSIS_PROMPT = """你是 ClawMail 个性化系统的技能设计师。

Executor 的任务是从用户对 AI 的修正中提取偏好记忆，但在以下案例中 Executor 返回了空结果或格式错误。

【失败案例（共 {case_count} 个）】
{formatted_cases}

【当前技能库】
{skills}

请分析：
1. 失败模式：这些案例有什么共同特征？
2. 根因：是哪个技能的指令不够明确，还是缺少某类技能？
3. 建议操作：refine_skill（改进已有技能） / add_skill（新增技能） / no_change

输出 JSON：
{{"failure_pattern": "描述", "root_cause": "描述", "recommendation": "refine_skill|add_skill|no_change", "target_skill": "技能名或null", "reasoning": "推理过程"}}"""

_REFINE_PROMPT = """请改进以下技能的 instruction_template，使其能更好地处理这类失败案例。

【当前技能】
名称: {skill_name}
当前指令:
{instruction_template}

【失败模式】
{failure_pattern}

【根因分析】
{root_cause}

【要求】
- 保持技能的核心目的不变
- 改进指令的清晰度和覆盖面
- 只输出新的 instruction_template 纯文本内容，不要 JSON 包裹、不要 Markdown 代码块"""

_ADD_SKILL_PROMPT = """请设计一个新的记忆提取技能来填补以下空白。

【失败模式】
{failure_pattern}

【根因分析】
{root_cause}

【已有技能】
{skill_names}

【要求】
输出 JSON（不要 Markdown 代码块）：
{{"skill_name": "snake_case_名称", "skill_type": "insert", "description": "简短描述", "instruction_template": "完整指令模板"}}"""


class Designer:
    """MemSkill 技能演化器。分析 Executor 失败案例，自动改进技能库。"""

    def __init__(self, bridge, skill_bank: SkillBank, log_dir: Path):
        """
        bridge: OpenClawBridge 实例
        skill_bank: SkillBank 实例
        log_dir: feedback 日志目录（含 executor_log.jsonl）
        """
        self._bridge = bridge
        self._skill_bank = skill_bank
        self._log_dir = log_dir
        self._state_file = log_dir / "designer_state.json"
        self._log_file = log_dir / "executor_log.jsonl"
        self._snapshot_dir = log_dir / "skill_snapshots"
        self._evolution_log = log_dir / "designer_evolution.jsonl"

    # --------------------------------------------------------
    # 触发判断
    # --------------------------------------------------------

    def should_run(self) -> bool:
        """检查是否达到触发阈值。"""
        if not self._log_file.exists():
            return False
        current_count = self._count_log_lines()
        last_count = self._load_state().get("last_log_count", 0)
        return (current_count - last_count) >= _TRIGGER_THRESHOLD

    # --------------------------------------------------------
    # 主流程
    # --------------------------------------------------------

    def run(self) -> Dict:
        """完整演化流程：收集 → 分析 → 提议 → 应用。返回结果摘要。"""
        print("[Designer] 开始技能演化分析...")

        # 1. 收集硬案例
        hard_cases = self._collect_hard_cases()
        if not hard_cases:
            print("[Designer] 无硬案例，跳过")
            self._update_state()
            return {"changes": [], "reason": "no_hard_cases"}

        print(f"[Designer] 收集到 {len(hard_cases)} 个硬案例")

        # 2. LLM 分析失败模式
        analysis = self._analyze_failures(hard_cases)
        if not analysis or analysis.get("recommendation") == "no_change":
            print(f"[Designer] 分析结论: 无需改动")
            self._update_state()
            return {"changes": [], "reason": "no_change", "analysis": analysis}

        print(f"[Designer] 分析结论: {analysis.get('recommendation')} → {analysis.get('target_skill', 'new')}")

        # 3. 提议具体修改
        changes = self._propose_changes(analysis)
        if not changes:
            print("[Designer] 未能生成有效的技能修改提议")
            self._update_state()
            return {"changes": [], "reason": "proposal_failed", "analysis": analysis}

        # 4. 备份 + 应用
        self._backup_skills()
        result = self._apply_changes(changes)

        # 5. 记录演化日志 + 更新状态
        self._log_evolution(analysis, changes, result)
        self._update_state()

        print(f"[Designer] 技能演化完成: {result}")
        return result

    # --------------------------------------------------------
    # 硬案例收集
    # --------------------------------------------------------

    def _collect_hard_cases(self) -> List[Dict]:
        """从 executor_log.jsonl 筛选失败/低效案例。"""
        if not self._log_file.exists():
            return []

        state = self._load_state()
        last_count = state.get("last_log_count", 0)
        cases = []

        try:
            with open(self._log_file, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i < last_count:
                        continue
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    # 硬案例条件：成功但空操作，或失败
                    if (entry.get("success") and entry.get("operation_count", 0) == 0) or \
                       not entry.get("success"):
                        cases.append(entry)
        except Exception:
            return []

        # 最多取最近 _MAX_HARD_CASES 条
        return cases[-_MAX_HARD_CASES:]

    # --------------------------------------------------------
    # LLM 分析
    # --------------------------------------------------------

    def _analyze_failures(self, hard_cases: List[Dict]) -> Optional[Dict]:
        """调用 LLM 分析失败模式。"""
        # 格式化案例
        formatted = []
        for i, case in enumerate(hard_cases, 1):
            formatted.append(
                f"案例 {i} (类型={case.get('feedback_type', '?')}):\n"
                f"  邮件: {json.dumps(case.get('email_data', {}), ensure_ascii=False)[:200]}\n"
                f"  AI预测: {case.get('prediction', '')[:150]}\n"
                f"  用户修正: {case.get('correction', '')[:150]}\n"
                f"  结果: success={case.get('success')}, operations={case.get('operation_count', 0)}\n"
                f"  LLM原始输出: {case.get('llm_raw', '')[:100]}"
            )
        formatted_text = "\n\n".join(formatted)

        skills_text = self._skill_bank.format_skills_for_prompt()

        prompt = _ANALYSIS_PROMPT.format(
            case_count=len(hard_cases),
            formatted_cases=formatted_text,
            skills=skills_text,
        )

        try:
            raw = self._bridge.user_chat(
                prompt, "personalizationAgent001",
                system_prompt=_ANALYSIS_SYSTEM_PROMPT,
            )
            return self._parse_json_object(raw)
        except Exception as e:
            print(f"[Designer] 分析 LLM 调用失败: {e}")
            return None

    def _propose_changes(self, analysis: Dict) -> List[Dict]:
        """根据分析结果，调用 LLM 生成具体的技能修改。"""
        recommendation = analysis.get("recommendation", "")
        failure_pattern = analysis.get("failure_pattern", "")
        root_cause = analysis.get("root_cause", "")

        if recommendation == "refine_skill":
            target = analysis.get("target_skill")
            if not target:
                return []
            skill = self._skill_bank.get_skill(target)
            if not skill:
                print(f"[Designer] 目标技能不存在: {target}")
                return []

            prompt = _REFINE_PROMPT.format(
                skill_name=skill.skill_name,
                instruction_template=skill.instruction_template,
                failure_pattern=failure_pattern,
                root_cause=root_cause,
            )
            try:
                new_template = self._bridge.user_chat(
                    prompt, "personalizationAgent001",
                )
                # 清理可能的 Markdown 包裹
                new_template = new_template.strip()
                if new_template.startswith("```"):
                    lines = new_template.split("\n")
                    lines = [l for l in lines if not l.strip().startswith("```")]
                    new_template = "\n".join(lines).strip()
                return [{
                    "action": "refine",
                    "skill_name": target,
                    "new_template": new_template,
                }]
            except Exception as e:
                print(f"[Designer] 技能改进 LLM 调用失败: {e}")
                return []

        elif recommendation == "add_skill":
            skill_names = [s.skill_name for s in self._skill_bank.get_all_skills()]
            prompt = _ADD_SKILL_PROMPT.format(
                failure_pattern=failure_pattern,
                root_cause=root_cause,
                skill_names=", ".join(skill_names),
            )
            try:
                raw = self._bridge.user_chat(
                    prompt, "personalizationAgent001",
                    system_prompt=_ANALYSIS_SYSTEM_PROMPT,
                )
                skill_def = self._parse_json_object(raw)
                if skill_def and "skill_name" in skill_def and "instruction_template" in skill_def:
                    return [{"action": "add", "skill": skill_def}]
            except Exception as e:
                print(f"[Designer] 新增技能 LLM 调用失败: {e}")
            return []

        return []

    # --------------------------------------------------------
    # 应用修改
    # --------------------------------------------------------

    def _apply_changes(self, changes: List[Dict]) -> Dict:
        """应用技能修改到 skill_bank DB。"""
        applied = []
        for change in changes:
            action = change.get("action")
            try:
                if action == "refine":
                    skill = self._skill_bank.get_skill(change["skill_name"])
                    if skill:
                        skill.instruction_template = change["new_template"]
                        skill.version += 1
                        self._skill_bank._db.save_skill(skill)
                        applied.append({"action": "refine", "skill": skill.skill_name, "version": skill.version})
                        print(f"[Designer] 改进技能: {skill.skill_name} → v{skill.version}")

                elif action == "add":
                    skill_def = change["skill"]
                    new_skill = Skill(
                        id=str(uuid.uuid4()),
                        skill_name=skill_def["skill_name"],
                        skill_type=skill_def.get("skill_type", "insert"),
                        description=skill_def.get("description", ""),
                        instruction_template=skill_def["instruction_template"],
                    )
                    self._skill_bank._db.save_skill(new_skill)
                    applied.append({"action": "add", "skill": new_skill.skill_name})
                    print(f"[Designer] 新增技能: {new_skill.skill_name}")
            except Exception as e:
                print(f"[Designer] 应用变更失败: {action} - {e}")

        return {"changes": applied}

    # --------------------------------------------------------
    # 备份 / 日志 / 状态
    # --------------------------------------------------------

    def _backup_skills(self) -> None:
        """备份当前技能库到 skill_snapshots/。"""
        try:
            self._snapshot_dir.mkdir(parents=True, exist_ok=True)
            skills = self._skill_bank.get_all_skills()
            snapshot = [{
                "skill_name": s.skill_name,
                "skill_type": s.skill_type,
                "description": s.description,
                "instruction_template": s.instruction_template,
                "version": s.version,
            } for s in skills]
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            path = self._snapshot_dir / f"{ts}.json"
            path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[Designer] 技能快照已保存: {path.name}")
        except Exception as e:
            print(f"[Designer] 备份失败: {e}")

    def _log_evolution(self, analysis: Dict, changes: List[Dict], result: Dict) -> None:
        """记录演化日志。"""
        try:
            record = {
                "timestamp": datetime.utcnow().isoformat(),
                "analysis": analysis,
                "proposed_changes": changes,
                "applied": result.get("changes", []),
            }
            with open(self._evolution_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _load_state(self) -> Dict:
        """读取 designer_state.json。"""
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _update_state(self) -> None:
        """更新 designer_state.json 中的 last_log_count。"""
        try:
            state = self._load_state()
            state["last_log_count"] = self._count_log_lines()
            state["last_run"] = datetime.utcnow().isoformat()
            self._state_file.write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def _count_log_lines(self) -> int:
        """统计 executor_log.jsonl 行数。"""
        if not self._log_file.exists():
            return 0
        try:
            with open(self._log_file, "r", encoding="utf-8") as f:
                return sum(1 for line in f if line.strip())
        except Exception:
            return 0

    # --------------------------------------------------------
    # JSON 解析工具
    # --------------------------------------------------------

    @staticmethod
    def _parse_json_object(raw: str) -> Optional[Dict]:
        """从 LLM 返回中解析 JSON 对象。"""
        import re
        text = raw.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            match = re.search(r'\{.*\}', text, flags=re.DOTALL)
            if match:
                try:
                    result = json.loads(match.group())
                    if isinstance(result, dict):
                        return result
                except (json.JSONDecodeError, ValueError):
                    pass
        print(f"[Designer] JSON 对象解析失败: {text[:200]}")
        return None
