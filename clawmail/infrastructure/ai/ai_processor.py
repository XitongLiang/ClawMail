"""
AIProcessor — Skill-Driven 邮件 AI 分析处理器
通过 subprocess 直接调用外部 OpenClaw skill 脚本，不再自行拼 prompt 调 LLM。
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from clawmail.domain.models.email import Email, EmailAIMetadata

# Skill-Driven: 脚本路径配置
SKILL_BASE = Path.home() / ".openclaw" / "workspace" / "skills"
ANALYZER_SCRIPT = SKILL_BASE / "clawmail-analyzer" / "scripts" / "analyze_email.py"
REPLY_SCRIPT = SKILL_BASE / "clawmail-reply" / "scripts" / "generate_reply.py"
GENERATE_SCRIPT = SKILL_BASE / "clawmail-reply" / "scripts" / "generate_email.py"
POLISH_SCRIPT = SKILL_BASE / "clawmail-reply" / "scripts" / "polish_email.py"
HABITS_SCRIPT = SKILL_BASE / "clawmail-reply" / "scripts" / "extract_habits.py"
LEARNER_SCRIPT = SKILL_BASE / "clawmail-learner" / "scripts" / "extract_preference.py"
OPTIMIZER_SCRIPT = SKILL_BASE / "clawmail-optimizer" / "scripts" / "optimize.py"


def _load_gateway_token() -> str:
    """从 openclaw.json 读取 gateway auth token。"""
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        return config.get("gateway", {}).get("auth", {}).get("token", "")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return ""


GATEWAY_TOKEN = _load_gateway_token()


# 长邮件正文截断上限（字符数）
BODY_MAX_CHARS = 4000

# AI 返回非法 JSON 或字段缺失时的默认值
DEFAULT_AI_RESULT = {
    "summary": {"keywords": [], "one_line": "", "brief": ""},
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

_VALID_SENTIMENTS = {"positive", "negative", "neutral"}


class AIProcessingError(Exception):
    """AI 处理失败（skill 脚本错误、超时等）。"""


class AIProcessor:
    """
    Skill-Driven AI 处理器。
    所有 AI 功能通过 subprocess 调用外部 skill 脚本实现。
    """

    def __init__(self, data_dir: Path = None):
        """data_dir: 用户数据目录（用于从 DB 读取 skill 写入的结果）"""
        self._data_dir = data_dir

    @staticmethod
    def _token_args() -> list:
        """返回 --llm-token 参数列表（token 为空则返回空列表）。"""
        return ["--llm-token", GATEWAY_TOKEN] if GATEWAY_TOKEN else []

    def process_email(
        self, email: Email, account_id: str = None, is_sent: bool = False
    ) -> EmailAIMetadata:
        """
        对单封邮件执行 AI 统一提取分析。
        调用 analyzer skill 脚本，成功返回 ai_status='processed' 的 EmailAIMetadata。
        失败时抛出 AIProcessingError。
        """
        cmd = [
            sys.executable, str(ANALYZER_SCRIPT),
            "--email-id", str(email.id),
        ] + self._token_args()
        if account_id:
            cmd.extend(["--account-id", account_id])
        if is_sent:
            cmd.append("--is-sent")

        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=None,
            encoding="utf-8", timeout=120,
        )

        if result.returncode != 0:
            raise AIProcessingError(f"Analyzer skill 失败 (exit={result.returncode})")

        # Skill 脚本执行时已通过 REST API 写入 DB
        # 尝试从 DB 读取最新结果
        if self._data_dir:
            from clawmail.infrastructure.database.storage_manager import ClawDB
            db = ClawDB(self._data_dir)
            metadata = db.get_email_ai_metadata(email.id)
            if metadata and metadata.ai_status == "processed":
                return metadata

        # Fallback: 从 stdout 解析结果
        if result.stdout.strip():
            parsed = self._parse_response(result.stdout)
            return self._build_metadata(email.id, parsed, ai_status="processed")

        raise AIProcessingError("Skill 脚本未返回结果且 DB 中无数据")

    def generate_reply_draft(
        self, email: Email, stance: str,
        user_notes: str = "", account_id: str = None,
    ) -> str:
        """
        根据选定立场生成回复草稿，返回正文字符串。
        语气风格由 LLM 根据用户记忆自动判断。
        调用 reply skill 脚本，失败时抛出 AIProcessingError。
        """
        cmd = [
            sys.executable, str(REPLY_SCRIPT),
            "--email-id", str(email.id),
            "--stance", stance,
        ] + self._token_args()
        if account_id:
            cmd.extend(["--account-id", account_id])
        if user_notes:
            cmd.extend(["--user-notes", user_notes])

        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=None,
            encoding="utf-8", timeout=120,
        )
        if result.returncode != 0:
            detail = result.stdout.strip()[:200] if result.stdout else ""
            raise AIProcessingError(
                f"Reply skill 失败 (rc={result.returncode}): {detail}"
            )
        if not result.stdout.strip():
            raise AIProcessingError("Reply skill 未返回结果")
        return result.stdout.strip()

    def generate_email(self, subject: str, outline: str) -> str:
        """
        根据主题和大纲生成完整邮件正文，返回正文字符串。
        语气风格由 LLM 根据用户记忆自动判断。
        调用 generate skill 脚本，失败时抛出 AIProcessingError。
        """
        cmd = [
            sys.executable, str(GENERATE_SCRIPT),
            "--subject", subject or "",
            "--outline", outline,
        ] + self._token_args()
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=None,
            encoding="utf-8", timeout=120,
        )
        if result.returncode != 0:
            detail = result.stdout.strip()[:200] if result.stdout else ""
            raise AIProcessingError(f"Generate skill 失败 (rc={result.returncode}): {detail}")
        if not result.stdout.strip():
            raise AIProcessingError("Generate skill 未返回结果")
        return result.stdout.strip()

    def polish_email(self, body: str) -> str:
        """
        对邮件正文进行 AI 润色，返回润色后的正文字符串。
        语气风格由 LLM 根据用户记忆自动判断。
        调用 polish skill 脚本，失败时抛出 AIProcessingError。
        """
        cmd = [
            sys.executable, str(POLISH_SCRIPT),
            "--body", body[:BODY_MAX_CHARS],
        ] + self._token_args()
        result = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=None,
            encoding="utf-8", timeout=120,
        )
        if result.returncode != 0:
            detail = result.stdout.strip()[:200] if result.stdout else ""
            raise AIProcessingError(f"Polish skill 失败 (rc={result.returncode}): {detail}")
        if not result.stdout.strip():
            raise AIProcessingError("Polish skill 未返回结果")
        return result.stdout.strip()

    # ----------------------------------------------------------------
    # 内部工具
    # ----------------------------------------------------------------

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
        reply_stances = [s for s in raw_stances if isinstance(s, str) and len(s) <= 30][:4]

        return EmailAIMetadata(
            email_id=email_id,
            summary={
                "keywords": (summary.get("keywords") or [])[:8],
                "one_line": summary.get("one_line", ""),
                "brief": summary.get("brief", ""),
            },
            categories=(metadata.get("category") or [])[:4],
            sentiment=sentiment,
            suggested_reply=suggested_reply,
            is_spam=is_spam,
            action_items=(result.get("action_items") or [])[:10],
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
