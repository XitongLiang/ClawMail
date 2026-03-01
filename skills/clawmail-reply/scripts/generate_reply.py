#!/usr/bin/env python3
"""
generate_reply.py - 回复草稿生成

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
    format="[reply] %(asctime)s %(levelname)s: %(message)s",
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
        "temperature": 0.5,
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


def generate_reply(
    email_id: str, stance: str, tone: str, user_notes: str, account_id: str
) -> str:
    """生成回复草稿，返回纯文本。"""
    logger.info("生成回复: email_id=%s stance=%s tone=%s", email_id, stance, tone)

    # 获取数据
    email = _http_get(f"{CLAWMAIL_API}/emails/{email_id}")
    ai_meta = _http_get(f"{CLAWMAIL_API}/emails/{email_id}/ai-metadata")
    memories = _http_get(f"{CLAWMAIL_API}/memories/{account_id}")
    user_profile = read_user_profile()

    # 加载 references
    reply_guide = load_reference("prompts/reply_guide.md")
    tone_styles = load_reference("prompts/tone_styles.md")
    memory_text = format_memories(memories)

    # 构建 prompt
    system_prompt = f"""你是一个邮件回复助手。请根据以下规则生成回复草稿。

## 用户侧写
{user_profile}

## 用户偏好记忆
{memory_text}

## 回复规则
{reply_guide}

## 语气风格
{tone_styles}

请直接输出回复内容（纯文本），不要输出 JSON，不要添加标题或标签。"""

    body = email.get("body_text", "")[:4000]
    user_prompt = f"""原始邮件：
主题: {email.get('subject', '')}
发件人: {json.dumps(email.get('from_address', {}), ensure_ascii=False)}
正文:
{body}

---
用户选择的回复立场: {stance}
目标语气: {tone}"""
    if user_notes:
        user_prompt += f"\n用户补充说明: {user_notes}"

    return call_llm(system_prompt, user_prompt)


def main():
    parser = argparse.ArgumentParser(description="生成邮件回复草稿")
    parser.add_argument("--email-id", required=True)
    parser.add_argument("--stance", required=True)
    parser.add_argument("--tone", required=True)
    parser.add_argument("--user-notes", default="")
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
        result = generate_reply(
            args.email_id, args.stance, args.tone, args.user_notes, args.account_id
        )
        print(result)
    except Exception as e:
        logger.error("生成回复失败: %s", e, exc_info=True)
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
