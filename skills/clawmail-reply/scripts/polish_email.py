#!/usr/bin/env python3
"""
polish_email.py - 邮件润色

由 ClawMail 通过 subprocess 直接调用。
输出纯文本到 stdout，不输出 JSON。
"""

import argparse
import json
from datetime import datetime
import sys
import logging
from pathlib import Path

import urllib.request
import urllib.error

CLAWMAIL_API = "http://127.0.0.1:9999"
LLM_API = "http://127.0.0.1:18789/v1/chat/completions"
MODEL = "kimi-k2.5"
LLM_TOKEN = ""
REFERENCES_DIR = Path(__file__).parent.parent / "references"

logging.basicConfig(
    level=logging.INFO,
    format="[Polish] %(asctime)s %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def load_reference(subpath: str) -> str:
    path = REFERENCES_DIR / subpath
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _http_get(url: str, timeout: int = 30) -> dict:
    """GET 请求，返回 JSON。"""
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post_json(url: str, data: dict, timeout: int = 30) -> dict:
    """POST JSON 请求，返回 JSON。"""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_llm(system_prompt: str, user_prompt: str) -> str:
    data = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if LLM_TOKEN:
        headers["Authorization"] = f"Bearer {LLM_TOKEN}"
    req = urllib.request.Request(LLM_API, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"]


def read_user_profile() -> str:
    user_md_path = Path.home() / ".openclaw" / "workspace" / "USER.md"
    if user_md_path.exists():
        return user_md_path.read_text(encoding="utf-8")
    return ""


_MEMORY_TTL_DAYS = {
    "contact": None, "sender_importance": 180, "urgency_signal": 180,
    "automated_content": 180, "summary_preference": 180,
    "response_pattern": 180, "project_state": 90,
}
_DEFAULT_TTL_DAYS = 120


def _memory_age_days(m: dict) -> int:
    ts = m.get("last_updated") or m.get("created_at")
    if not ts:
        return 0
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return max(0, (datetime.now(dt.tzinfo) - dt).days)
    except (ValueError, TypeError):
        return 0


def format_memories(memories: dict) -> str:
    """格式化偏好记忆，按类型 TTL 过滤，附带年龄标签。"""
    items = memories.get("memories", [])
    filtered = []
    for m in items:
        mtype = m.get("memory_type", "")
        ttl = _MEMORY_TTL_DAYS.get(mtype, _DEFAULT_TTL_DAYS)
        age = _memory_age_days(m)
        if ttl is not None and age > ttl:
            continue
        filtered.append((m, age))
    if not filtered:
        return "（无历史记忆）"
    lines = []
    for m, age in filtered:
        content = m.get("memory_content", {})
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        key = m.get("memory_key") or "全局"
        if age <= 1:
            age_tag = "今天"
        elif age <= 7:
            age_tag = f"{age}天前"
        elif age <= 30:
            age_tag = f"{age // 7}周前"
        else:
            age_tag = f"{age // 30}个月前"
        lines.append(f"- [{m.get('memory_type', '?')}] {key}: {content} ({age_tag})")
    return "\n".join(lines)


def polish_email(body: str, account_id: str) -> str:
    """润色邮件，返回润色后的纯文本。语气风格由 LLM 根据记忆自动判断。"""
    logger.info("润色邮件: body_len=%d", len(body))

    # 获取用户记忆
    # 润色无收件人上下文，只拉全局偏好
    memories = _http_get(f"{CLAWMAIL_API}/memories/{account_id}/for-email") if account_id else {}
    user_profile = read_user_profile()

    # 加载 references
    polish_guide = load_reference("prompts/polish_guide.md")
    tone_styles = load_reference("prompts/tone_styles.md")
    memory_text = format_memories(memories)

    system_prompt = f"""你是一个邮件润色助手。请根据以下规则润色邮件。

## 用户侧写
{user_profile}

## 用户偏好记忆
{memory_text}

## 润色规则
{polish_guide}

## 语气风格
{tone_styles}

请直接输出润色后的邮件内容（纯文本），不要输出 JSON，不要添加标题或标签。"""

    user_prompt = f"""请润色以下邮件：

语气风格: 根据用户偏好记忆（response_pattern）自动判断。如无相关记忆，默认使用礼貌风格。

原始邮件内容:
{body[:4000]}"""

    return call_llm(system_prompt, user_prompt)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="润色邮件")
    parser.add_argument("--body", required=True)
    parser.add_argument("--account-id", default="")
    parser.add_argument("--clawmail-api", default="http://127.0.0.1:9999")
    parser.add_argument(
        "--llm-api", default="http://127.0.0.1:18789/v1/chat/completions"
    )
    parser.add_argument("--model", default="kimi-k2.5")
    parser.add_argument("--llm-token", default="")
    args = parser.parse_args()

    global CLAWMAIL_API, LLM_API, MODEL, LLM_TOKEN
    CLAWMAIL_API = args.clawmail_api
    LLM_API = args.llm_api
    MODEL = args.model
    LLM_TOKEN = args.llm_token

    try:
        result = polish_email(args.body, args.account_id)
        print(result)
    except Exception as e:
        logger.error("润色失败: %s", e, exc_info=True)
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
