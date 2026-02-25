"""
AIProcessor — 邮件 AI 分析处理器
调用统一提取 Prompt #1（design/prompt.md），解析 JSON 结果，失败时降级。
"""

import json
import re
from datetime import datetime
from typing import Optional

from clawmail.domain.models.email import Email, EmailAIMetadata


# 长邮件正文截断上限（字符数）
BODY_MAX_CHARS = 4000

# AI 返回非法 JSON 或字段缺失时的默认值
DEFAULT_AI_RESULT = {
    "keywords": [],
    "summary": {"one_line": "", "brief": "", "key_points": []},
    "outline": [],
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

# 统一提取 Prompt 模板（来自 design/prompt.md #1）
_PROMPT_TEMPLATE = """你是ClawMail智能助手Claw。请分析以下邮件，一次性提取关键信息、生成摘要并识别待办事项。

【输入邮件】
{mail_json}

【分类说明】
从以下固定标签中选择 0-3 个（不强制必须选）：
- urgent（需24小时内处理）
- pending_reply（等待我方回复）
- notification（纯信息，无需行动）
- subscription（newsletters/推广）
- meeting（包含会议安排或日程）
- approval（需要决策或签字）
如邮件明确与某项目相关，额外输出一个"项目:XX"动态标签。总标签不超过4个。

【输出要求】
严格返回JSON，不要Markdown标记，所有字段必须存在：

{
  "keywords": ["关键词1", "关键词2", "关键词3-5个"],
  "summary": {
    "one_line": "一句话核心概括（20字内）",
    "brief": "3-5行标准摘要",
    "key_points": ["要点1", "要点2", "要点3"]
  },
  "outline": [
    {
      "index": 1,
      "title": "段落主题",
      "content": "核心内容",
      "type": "背景|核心信息|行动要求|问题|其他"
    }
  ],
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
    "urgency": "high|medium|low",
    "suggested_reply": "简短的建议回复草稿（如无需回复则为null）",
    "reply_stances": ["同意并确认时间", "需要更多信息", "暂时无法满足"]
  }
}

【urgency说明】
- high：今天内需处理，有明确截止日期或紧迫措辞
- medium：近期需处理（约1周内），措辞平和
- low：无明确时限，可按需处理或仅供参考

【is_spam说明】
- true：此邮件是垃圾邮件/推广/广告/钓鱼邮件，应归入垃圾邮件文件夹
- false：此邮件是正常邮件，不应归入垃圾邮件文件夹

【action_items.category说明】
- 工作：职场任务、商务沟通、项目相关
- 学习：学习资料、课程、知识获取
- 生活：日常事务、购物、个人生活
- 个人：个人事项、健康、家庭

【reply_stances说明】
- 根据邮件内容，生成2-4个我方可能的回复立场选项（动词开头，15字以内）
- 选项应覆盖不同态度（如同意、拒绝、需要信息等）
- 若邮件无需回复（通知类/垃圾邮件/推广），输出空数组 []"""

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

    process_email() 成功时返回 ai_status='processed' 的 EmailAIMetadata，
    失败时抛出 AIProcessingError，由调用方决定是否重试。
    """

    def __init__(self, bridge):
        """bridge: OpenClawBridge 实例"""
        self._bridge = bridge

    def process_email(self, email: Email) -> EmailAIMetadata:
        """
        对单封邮件执行 AI 统一提取分析。
        成功：返回 ai_status='processed' 的 EmailAIMetadata。
        失败：抛出 AIProcessingError。
        """
        mail_input = self._build_mail_json(email)
        prompt = _PROMPT_TEMPLATE.replace("{mail_json}", mail_input)

        try:
            raw = self._bridge.process_email(prompt, "mailAgent001")
        except Exception as e:
            raise AIProcessingError(f"AI 调用失败: {e}") from e

        result = self._parse_response(raw)
        return self._build_metadata(email.id, result, ai_status="processed")

    def generate_reply_draft(
        self, email: Email, stance: str, tone: str, user_notes: str = ""
    ) -> str:
        """
        根据选定立场和风格生成回复草稿，返回正文字符串。
        失败时抛出 AIProcessingError。
        """
        tone_desc, length_hint = _TONE_DESCRIPTIONS.get(tone, ("礼貌友好", "100-200字"))
        mail_input = self._build_mail_json(email)
        prompt = (
            _DRAFT_PROMPT_TEMPLATE
            .replace("{mail_json}", mail_input)
            .replace("{stance}", stance)
            .replace("{tone_desc}", tone_desc)
            .replace("{user_notes}", user_notes or "（无）")
            .replace("{length_hint}", length_hint)
        )
        try:
            raw = self._bridge.process_email(prompt, "draftAgent001")
        except Exception as e:
            raise AIProcessingError(f"草稿生成失败: {e}") from e
        return raw.strip()

    def generate_email(self, subject: str, outline: str, tone: str) -> str:
        """
        根据主题和大纲生成完整邮件正文，返回正文字符串。
        失败时抛出 AIProcessingError。
        """
        tone_desc, length_hint = _TONE_DESCRIPTIONS.get(tone, ("礼貌友好，语气温和", "100-200字"))
        prompt = (
            _GENERATE_PROMPT_TEMPLATE
            .replace("{subject}", subject or "（无主题）")
            .replace("{outline}", outline)
            .replace("{tone_desc}", tone_desc)
            .replace("{length_hint}", length_hint)
        )
        try:
            raw = self._bridge.process_email(prompt, "generateAgent001")
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
        prompt = (
            _POLISH_PROMPT_TEMPLATE
            .replace("{body}", body_trimmed)
            .replace("{tone_desc}", tone_desc)
        )
        try:
            raw = self._bridge.process_email(prompt, "polishAgent001")
        except Exception as e:
            raise AIProcessingError(f"润色失败: {e}") from e
        return raw.strip()

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

        urgency_raw = metadata.get("urgency")
        urgency = urgency_raw if urgency_raw in ("high", "medium", "low") else None

        raw_stances = metadata.get("reply_stances") or []
        if not isinstance(raw_stances, list):
            raw_stances = []
        reply_stances = [s for s in raw_stances if isinstance(s, str) and len(s) <= 30]

        return EmailAIMetadata(
            email_id=email_id,
            keywords=result.get("keywords") or [],
            summary_one_line=summary.get("one_line", ""),
            summary_brief=summary.get("brief", ""),
            summary_key_points=summary.get("key_points") or [],
            outline=result.get("outline") or [],
            categories=metadata.get("category") or [],
            sentiment=sentiment,
            suggested_reply=suggested_reply,
            is_spam=is_spam,
            urgency=urgency,
            action_items=result.get("action_items") or [],
            reply_stances=reply_stances or None,
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
