#!/usr/bin/env python3
"""
polish_email.py - 邮件润色

由 ClawMail 通过 subprocess 直接调用。
输出纯文本到 stdout，不输出 JSON。
"""

import argparse
import json
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
    format="[polish] %(asctime)s %(levelname)s: %(message)s",
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


def format_memories(memories: dict) -> str:
    items = memories.get("memories", [])
    if not items:
        return "（无历史记忆）"
    lines = []
    for m in items:
        content = m.get("memory_content", {})
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        lines.append(
            f"- [{m.get('memory_type')}] {m.get('memory_key', '全局')}: {content}"
        )
    return "\n".join(lines)


def polish_email(body: str, tone: str, account_id: str) -> str:
    """润色邮件，返回润色后的纯文本。"""
    logger.info("润色邮件: tone=%s body_len=%d", tone, len(body))

    # 获取用户记忆
    memories = _http_get(f"{CLAWMAIL_API}/memories/{account_id}")
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

目标语气: {tone}

原始邮件内容:
{body[:4000]}"""

    return call_llm(system_prompt, user_prompt)


def main():
    parser = argparse.ArgumentParser(description="润色邮件")
    parser.add_argument("--body", required=True)
    parser.add_argument("--tone", required=True)
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
        result = polish_email(args.body, args.tone, args.account_id)
        print(result)
    except Exception as e:
        logger.error("润色失败: %s", e, exc_info=True)
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
