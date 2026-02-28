"""
AIProcessor — 邮件 AI 分析处理器
调用统一提取 Prompt #1（design/prompt.md），解析 JSON 结果，失败时降级。
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from clawmail.domain.models.email import Email, EmailAIMetadata


# 长邮件正文截断上限（字符数）
BODY_MAX_CHARS = 4000

# AI 返回非法 JSON 或字段缺失时的默认值
DEFAULT_AI_RESULT = {
    "summary": {"keywords": [], "one_line": "", "brief": "", "key_points": []},
    "action_items": [],
    "metadata": {
        "category": [],
        "sentiment": "neutral",
        "language": "zh",
        "confidence": 0.0,
        "suggested_reply": None,
        "is_spam": False,
        "reply_stances": [],
    },
}

# 各说明段落默认内容（拆分到 ~/clawmail_data/prompts/*.txt，可由用户编辑）
DEFAULT_PROMPT_SECTIONS = {
    "summary": """【summary说明】
生成多层次的邮件摘要并提取关键词。

1. keywords（关键词，3-5个）
   从邮件中提取3-5个最具代表性的关键词或短语。

   提取维度及优先级：
   - 核心主题词（最高优先级）：邮件讨论的核心话题或事件名称
   - 关键实体（高优先级）：人名、项目名、产品名、组织名等专有名词
   - 行动/状态词（中优先级）：邮件要求的核心行动或当前状态
   - 时间/场景标记（低优先级）：重要的时间节点或场景信息

   选取规则：
   - 总数3-5个，优先选取高优先级维度的词
   - 每个关键词2-8个字，简洁有力
   - 避免过于笼统的词（如"工作"、"邮件"、"通知"、"信息"）
   - 避免重复或高度相似的词（如同时出现"报告"和"季度报告"，只保留后者）
   - 中英文按邮件原文语言输出

2. one_line（一句话概括，20字以内）
   - 用一句话回答"这封邮件说了什么"
   - 必须包含核心动作或结论
   - 格式：[主语] + [动作/状态] + [关键信息]
   - 好的例子："张总要求周五前提交Q4报告"
   - 差的例子："关于报告的邮件"（太笼统，缺少具体信息）

3. brief（标准摘要，3-5行）
   - 完整概述邮件内容，保留关键细节
   - 第一句点明核心主题
   - 中间补充重要背景和具体要求
   - 最后说明需要采取的行动或下一步
   - 保持客观，不添加原文未提及的推断

4. key_points（关键要点，2-5条）
   - 每条要点是一个完整的陈述句
   - 优先提取：决策结论、具体要求、重要数据、截止时间、负责人
   - 按重要性排序，最重要的放在第一条
   - 每条15-30字，信息密度高
   - 避免与 one_line 内容重复""",

    "category": """【分类说明】
从以下固定标签中选择 0-3 个（不强制必须选）：
- urgent（需24小时内处理）
- pending_reply（等待我方回复）
- notification（纯信息，无需行动）
- subscription（newsletters/推广）
- meeting（包含会议安排或日程）
- approval（需要决策或签字）
如邮件明确与某项目相关，额外输出一个"项目:XX"动态标签。总标签不超过4个。""",

    "is_spam": """【is_spam说明】
- true：此邮件是垃圾邮件/推广/广告/钓鱼邮件，应归入垃圾邮件文件夹
- false：此邮件是正常邮件，不应归入垃圾邮件文件夹""",

    "action_category": """【action_items.category说明】
- 工作：职场任务、商务沟通、项目相关
- 学习：学习资料、课程、知识获取
- 生活：日常事务、购物、个人生活
- 个人：个人事项、健康、家庭""",

    "reply_stances": """【reply_stances说明】
- 根据邮件内容，生成2-4个我方可能的回复立场选项（动词开头，15字以内）
- 选项应覆盖不同态度（如同意、拒绝、需要信息等）
- 若邮件无需回复（通知类/垃圾邮件/推广），输出空数组 []""",

    "importance_score": """【importance_score说明】
综合评估邮件的重要性，给出0-100的分数。

评判维度及权重：

1. 发件人身份（权重30%）
   - 90-100：家人/CEO/总经理/董事会成员
   - 70-89：部门经理/总监
   - 50-69：项目经理
   - 30-49：普通同事
   - 0-29：系统邮件/自动通知

2. 紧急关键词（权重25%）
   - 90-100：包含"紧急"/"立即"/"马上"
   - 70-89：包含"今天"/"尽快"
   - 50-69：包含"本周"
   - 30-49：包含"请"/"需要"
   - 0-29：无时间要求

3. 截止时间（权重25%）
   - 90-100：今日截止
   - 70-89：明日截止
   - 50-69：本周内
   - 30-49：下周
   - 0-29：无明确时间

4. 任务复杂度（权重20%）
   - 90-100：3个及以上高优先级待办
   - 70-89：2个高优先级待办
   - 50-69：1个中优先级待办
   - 30-49：1-2个低优先级待办
   - 0-29：无明确待办

最终分数 = 各维度分数 × 权重 之和，取整为0-100的整数。""",
}

# 说明段落加载顺序
_SECTION_ORDER = ("summary", "category", "is_spam",
                  "action_category", "reply_stances", "importance_score")

# 统一提取 Prompt 模板（说明段落在运行时从文件加载并注入 {prompt_sections}）
_PROMPT_TEMPLATE = """你是ClawMail智能助手Claw。请分析以下邮件，一次性提取关键信息、生成摘要并识别待办事项。

【输入邮件】
{mail_json}

{prompt_sections}

【输出要求】
严格返回JSON，不要Markdown标记，所有字段必须存在：

{
  "summary": {
    "keywords": ["关键词1", "关键词2", "关键词3-5个"],
    "one_line": "一句话核心概括（20字内）",
    "brief": "3-5行标准摘要",
    "key_points": ["要点1", "要点2", "要点3"]
  },
  "action_items": [
    {
      "text": "具体行动描述（动词开头）",
      "deadline": "YYYY-MM-DD或null",
      "deadline_source": "explicit|inferred|null",
      "priority": "high|medium|low",
      "category": "工作|学习|生活|个人",
      "assignee": "me|sender|other",
      "quote": "原文引用"
    }
  ],
  "metadata": {
    "category": ["urgent", "项目:Q4发布"],
    "sentiment": "urgent|positive|negative|neutral",
    "language": "zh|en|ja",
    "confidence": 0.95,
    "is_spam": false,
    "suggested_reply": "简短的建议回复草稿（如无需回复则为null）",
    "reply_stances": ["同意并确认时间", "需要更多信息", "暂时无法满足"],
    "importance_score": "0-100的整数，越大越重要"
  }
}"""

# 邮件正文润色 Prompt 模板
_POLISH_PROMPT_TEMPLATE = """你是ClawMail智能助手Claw，请帮我润色以下邮件正文。

【待润色正文】
{body}

【润色风格】
{tone_desc}

【输出要求】
- 直接输出润色后的正文，不含主题行
- 保持原有意思和内容结构，只改进语言表达和流畅度
- 长度与原文相近，不要大幅扩写或缩减
- 语言：与原文相同
- 仅输出正文文本，不要任何 JSON 或 Markdown"""

# 一键生成邮件 Prompt 模板
_GENERATE_PROMPT_TEMPLATE = """你是ClawMail智能助手Claw，请根据以下信息撰写一封完整的邮件正文。

【邮件主题】
{subject}

【内容大纲/草稿】
{outline}

【写作风格】
{tone_desc}

【输出要求】
- 直接输出邮件正文，不含主题行
- 根据大纲扩展成完整、流畅的邮件内容，补充适当的礼貌用语和过渡句
- 长度：{length_hint}
- 语言：根据大纲语言自动判断，默认中文
- 仅输出正文文本，不要任何 JSON 或 Markdown"""

# 回复草稿生成 Prompt 模板
_DRAFT_PROMPT_TEMPLATE = """你是ClawMail智能助手Claw，请根据以下信息撰写一封回复邮件草稿。

【原邮件】
{mail_json}

【回复立场】
{stance}

【回复风格】
{tone_desc}

【用户补充说明】
{user_notes}

【输出要求】
- 直接输出邮件正文，不含主题行
- 不需要"尊敬的XXX"等固定开头，直接切入主题
- 长度：{length_hint}
- 语言：与原邮件相同
- 仅输出正文文本，不要任何 JSON 或 Markdown"""

_TONE_DESCRIPTIONS = {
    "正式": ("正式严肃，用词规范，不使用口语", "150-250字"),
    "礼貌": ("礼貌友好，语气温和，适当表达感谢或歉意", "100-200字"),
    "轻松": ("轻松自然，口语化，简洁直接", "50-100字"),
    "简短": ("极度简短，只说核心内容", "30-80字"),
}

_VALID_SENTIMENTS = {"urgent", "positive", "negative", "neutral"}


class AIProcessingError(Exception):
    """AI 处理失败（网络错误、模型无响应等）。"""


class AIProcessor:
    """
    同步 AI 处理器，在线程池中调用 OpenClawBridge。

    process_email() 成功时返回 ai_status='processed' 的 EmailAIMetadata,
    失败时抛出 AIProcessingError，由调用方决定是否重试。
    """

    def __init__(self, bridge, data_dir: Path = None, memory_bank=None):
        """bridge: OpenClawBridge 实例, data_dir: 用户数据目录（用于加载自定义 prompt）
        memory_bank: MemoryBank 实例（可选，用于注入用户偏好记忆）"""
        self._bridge = bridge
        self._data_dir = data_dir
        self._memory_bank = memory_bank
        self._prompt_cache: dict[str, str] = {}  # name → 上次加载时的完整内容

    def _load_template(self, name: str, default: str) -> str:
        """从 prompts/{name}.txt 加载模板，不存在时回退到 default。
        检测到内容变化时自动归档旧版本。"""
        if not self._data_dir:
            return default
        from datetime import datetime
        f = self._data_dir / "prompts" / f"{name}.txt"
        if not f.exists():
            return default
        content = f.read_text(encoding="utf-8").strip()
        cache_key = f"_tpl_{name}"
        prev = self._prompt_cache.get(cache_key)
        if prev is not None and content != prev:
            try:
                archive_dir = self._data_dir / "prompts" / "archive"
                archive_dir.mkdir(exist_ok=True)
                date_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                (archive_dir / f"{name}_{date_str}.txt").write_text(
                    prev, encoding="utf-8")
                print(f"[AIProcessor] template '{name}' 已变更，旧版本已归档")
            except Exception:
                pass
        self._prompt_cache[cache_key] = content
        return content

    def _load_prompt_sections(self) -> str:
        """从用户数据目录加载说明文件，拼接为 prompt 片段。文件不存在时回退到默认值。
        检测到文件内容变化时，自动将旧版本归档到 prompts/archive/。"""
        from datetime import datetime
        parts = []
        for name in _SECTION_ORDER:
            if self._data_dir:
                f = self._data_dir / "prompts" / f"{name}.txt"
                if f.exists():
                    content = f.read_text(encoding="utf-8").strip()
                    prev_content = self._prompt_cache.get(name)
                    if prev_content is not None and content != prev_content:
                        try:
                            archive_dir = self._data_dir / "prompts" / "archive"
                            archive_dir.mkdir(exist_ok=True)
                            date_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
                            archive_file = archive_dir / f"{name}_{date_str}.txt"
                            archive_file.write_text(prev_content, encoding="utf-8")
                            print(f"[AIProcessor] prompt '{name}' 已变更，旧版本归档为 {archive_file.name}")
                        except Exception:
                            pass
                    self._prompt_cache[name] = content
                    parts.append(content)
                    continue
            parts.append(DEFAULT_PROMPT_SECTIONS[name])
        return "\n\n".join(parts)

    def process_email(
        self, email: Email, account_id: str = None
    ) -> EmailAIMetadata:
        """
        对单封邮件执行 AI 统一提取分析。
        成功：返回 ai_status='processed' 的 EmailAIMetadata。
        失败：抛出 AIProcessingError。
        account_id: 用户账户 ID，用于检索偏好记忆（可选）。
        """
        mail_input = self._build_mail_json(email)
        prompt_sections = self._load_prompt_sections()

        # MemSkill: 注入用户偏好记忆
        memory_section = self._build_memory_section(email, account_id, "email_analysis")
        if memory_section:
            prompt_sections = memory_section + "\n\n" + prompt_sections

        template = self._load_template("mail_analysis", _PROMPT_TEMPLATE)
        prompt = (
            template
            .replace("{prompt_sections}", prompt_sections)
            .replace("{mail_json}", mail_input)
        )

        try:
            raw = self._bridge.user_chat(prompt, "mailAgent001")
        except Exception as e:
            raise AIProcessingError(f"AI 调用失败: {e}") from e

        result = self._parse_response(raw)
        return self._build_metadata(email.id, result, ai_status="processed")

    def generate_reply_draft(
        self, email: Email, stance: str, tone: str,
        user_notes: str = "", account_id: str = None,
    ) -> str:
        """
        根据选定立场和风格生成回复草稿，返回正文字符串。
        失败时抛出 AIProcessingError。
        account_id: 用户账户 ID，用于检索偏好记忆（可选）。
        """
        tone_desc, length_hint = _TONE_DESCRIPTIONS.get(tone, ("礼貌友好", "100-200字"))
        mail_input = self._build_mail_json(email)
        template = self._load_template("reply_draft", _DRAFT_PROMPT_TEMPLATE)

        # MemSkill: 注入用户回复偏好记忆
        memory_section = self._build_memory_section(email, account_id, "reply_draft")
        user_notes_full = user_notes or "（无）"
        if memory_section:
            user_notes_full = user_notes_full + "\n\n" + memory_section

        prompt = (
            template
            .replace("{mail_json}", mail_input)
            .replace("{stance}", stance)
            .replace("{tone_desc}", tone_desc)
            .replace("{user_notes}", user_notes_full)
            .replace("{length_hint}", length_hint)
        )
        try:
            raw = self._bridge.user_chat(prompt, "draftAgent001")
        except Exception as e:
            raise AIProcessingError(f"草稿生成失败: {e}") from e
        return raw.strip()

    def generate_email(self, subject: str, outline: str, tone: str) -> str:
        """
        根据主题和大纲生成完整邮件正文，返回正文字符串。
        失败时抛出 AIProcessingError。
        """
        tone_desc, length_hint = _TONE_DESCRIPTIONS.get(tone, ("礼貌友好，语气温和", "100-200字"))
        template = self._load_template("generate_email", _GENERATE_PROMPT_TEMPLATE)
        prompt = (
            template
            .replace("{subject}", subject or "（无主题）")
            .replace("{outline}", outline)
            .replace("{tone_desc}", tone_desc)
            .replace("{length_hint}", length_hint)
        )
        try:
            raw = self._bridge.user_chat(prompt, "generateAgent001")
        except Exception as e:
            raise AIProcessingError(f"生成失败: {e}") from e
        return raw.strip()

    def polish_email(self, body: str, tone: str) -> str:
        """
        对邮件正文进行 AI 润色，返回润色后的正文字符串。
        失败时抛出 AIProcessingError。
        """
        tone_desc, _ = _TONE_DESCRIPTIONS.get(tone, ("礼貌友好，语气温和", ""))
        body_trimmed = body[:BODY_MAX_CHARS] if len(body) > BODY_MAX_CHARS else body
        template = self._load_template("polish_email", _POLISH_PROMPT_TEMPLATE)
        prompt = (
            template
            .replace("{body}", body_trimmed)
            .replace("{tone_desc}", tone_desc)
        )
        try:
            raw = self._bridge.user_chat(prompt, "polishAgent001")
        except Exception as e:
            raise AIProcessingError(f"润色失败: {e}") from e
        return raw.strip()

    # ----------------------------------------------------------------
    # MemSkill: 记忆注入
    # ----------------------------------------------------------------

    def _build_memory_section(
        self, email: Email, account_id: str = None, task_type: str = "email_analysis"
    ) -> str:
        """根据邮件和 task_type 检索用户记忆并格式化为 prompt 段落。无记忆时返回空字符串。"""
        if not self._memory_bank:
            print(f"[MemSkill] 记忆注入跳过: memory_bank 未初始化")
            return ""
        if not account_id:
            print(f"[MemSkill] 记忆注入跳过: account_id 为空")
            return ""

        from_info = email.from_address or {}
        sender_email = from_info.get("email", "")
        sender_domain = sender_email.split("@")[-1] if "@" in sender_email else ""

        try:
            if task_type == "reply_draft":
                memories = self._memory_bank.retrieve_for_reply(
                    account_id, sender_email
                )
            else:
                memories = self._memory_bank.retrieve_for_email(
                    account_id, sender_email, sender_domain
                )

            if memories:
                types = {}
                for m in memories:
                    types[m.memory_type] = types.get(m.memory_type, 0) + 1
                print(f"[MemSkill] 检索到 {len(memories)} 条记忆 (task={task_type}, sender={sender_email}): {types}")
            else:
                print(f"[MemSkill] 无记忆 (task={task_type}, sender={sender_email}, account={account_id[:8]}...)")

            text = self._memory_bank.format_memories_for_prompt(memories, task_type)
            if text:
                print(f"[MemSkill] 记忆段落已注入 prompt ({len(text)} 字符)")
            return text
        except Exception as e:
            print(f"[MemSkill] 记忆检索失败: {e}")
            return ""

    # ----------------------------------------------------------------
    # 内部工具
    # ----------------------------------------------------------------

    def _build_mail_json(self, email: Email) -> str:
        """将 Email 序列化为 AI 输入 JSON（正文超长时截断）。"""
        from_info = email.from_address or {}
        body_text = email.body_text or ""
        if len(body_text) > BODY_MAX_CHARS:
            body_text = body_text[:BODY_MAX_CHARS] + "\n...[正文过长，已截断]"

        data = {
            "subject": email.subject or "",
            "from": {
                "name": from_info.get("name", ""),
                "email": from_info.get("email", ""),
            },
            "to": [d.get("email", "") for d in (email.to_addresses or [])],
            "date": (
                email.received_at.strftime("%Y-%m-%d %H:%M")
                if email.received_at
                else ""
            ),
            "body_text": body_text,
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _parse_response(self, raw: str) -> dict:
        """解析 AI 返回的 JSON，字段缺失时以 DEFAULT_AI_RESULT 补全。"""
        text = raw.strip()
        # 去掉可能的 Markdown 代码块包裹
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)

        try:
            data = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return _deep_merge({}, DEFAULT_AI_RESULT)

        return _deep_merge(data, DEFAULT_AI_RESULT)

    def _build_metadata(
        self, email_id: str, result: dict, ai_status: str
    ) -> EmailAIMetadata:
        summary = result.get("summary") or {}
        metadata = result.get("metadata") or {}

        sentiment = metadata.get("sentiment", "neutral")
        if sentiment not in _VALID_SENTIMENTS:
            sentiment = "neutral"

        suggested_reply = metadata.get("suggested_reply")
        if suggested_reply == "null" or suggested_reply == "":
            suggested_reply = None

        raw_is_spam = metadata.get("is_spam", False)
        is_spam = bool(raw_is_spam) if raw_is_spam is not None else False

        importance_raw = metadata.get("importance_score")
        importance_score = None
        if importance_raw is not None:
            try:
                val = int(importance_raw)
                if 0 <= val <= 100:
                    importance_score = val
            except (ValueError, TypeError):
                pass

        raw_stances = metadata.get("reply_stances") or []
        if not isinstance(raw_stances, list):
            raw_stances = []
        reply_stances = [s for s in raw_stances if isinstance(s, str) and len(s) <= 30]

        return EmailAIMetadata(
            email_id=email_id,
            summary={
                "keywords": summary.get("keywords") or [],
                "one_line": summary.get("one_line", ""),
                "brief": summary.get("brief", ""),
                "key_points": summary.get("key_points") or [],
            },
            categories=metadata.get("category") or [],
            sentiment=sentiment,
            suggested_reply=suggested_reply,
            is_spam=is_spam,
            action_items=result.get("action_items") or [],
            reply_stances=reply_stances or None,
            importance_score=importance_score,
            ai_status=ai_status,
            processing_progress=100 if ai_status == "processed" else 0,
            processing_stage="completed" if ai_status == "processed" else "failed",
            processed_at=datetime.utcnow() if ai_status == "processed" else None,
        )


def _deep_merge(data: dict, defaults: dict) -> dict:
    """将 defaults 中缺失的键递归补充到 data 中，返回 data。"""
    for k, v in defaults.items():
        if k not in data:
            data[k] = v
        elif isinstance(v, dict) and isinstance(data.get(k), dict):
            _deep_merge(data[k], v)
    return data
