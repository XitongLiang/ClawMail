#!/usr/bin/env python3
"""
generate_reply.py - 回复草稿生成

由 ClawMail 通过 subprocess 直接调用。
输出纯文本到 stdout，不输出 JSON。
"""

import argparse
import json
import re
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
    """格式化全局偏好记忆（排除 contact.* 条目，由 format_sender_profile 单独处理）。"""
    items = memories.get("memories", [])
    global_items = [m for m in items if not m.get("memory_key", "").startswith("contact.")]
    if not global_items:
        return "（无历史记忆）"
    lines = []
    for m in global_items:
        content = m.get("memory_content", {})
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        lines.append(
            f"- [{m.get('memory_type')}] {m.get('memory_key', '全局')}: {content}"
        )
    return "\n".join(lines)


def format_sender_profile(memories: dict, sender_email: str) -> str:
    """从 MemoryBank 提取指定发件人的画像记忆（contact.{email}.* 条目）。"""
    if not sender_email:
        return ""
    items = memories.get("memories", [])
    prefix = f"contact.{sender_email.lower()}"
    sender_items = [
        m for m in items
        if m.get("memory_key", "").lower().startswith(prefix)
    ]
    if not sender_items:
        return ""
    lines = []
    for m in sender_items:
        content = m.get("memory_content", {})
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        lines.append(f"- {m.get('memory_key', '')}: {content}")
    return "\n".join(lines)


# ── 正文预处理（与 analyze_email.py 保持一致）──

def strip_quoted_content(body: str) -> str:
    """移除引用的回复历史和转发头。"""
    if not body:
        return body
    lines = body.splitlines()
    cleaned = []
    for i, line in enumerate(lines):
        if re.match(r"^On\s+", line, re.IGNORECASE):
            candidate = line.rstrip()
            if i + 1 < len(lines):
                candidate = candidate + " " + lines[i + 1].strip()
            if re.search(r"wrote:\s*$", candidate, re.IGNORECASE):
                break
        if re.match(r"^在\s+", line):
            candidate = line.rstrip()
            if i + 1 < len(lines):
                candidate = candidate + " " + lines[i + 1].strip()
            if re.search(r"写道[：:]\s*$", candidate):
                break
        if re.match(r"^-{5,}\s*(Forwarded message|转发的邮件)\s*-{5,}", line, re.IGNORECASE):
            break
        if re.match(r"^From:\s+", line) and i > 0 and lines[i - 1].strip() == "":
            lookahead = "\n".join(lines[i: i + 5])
            if re.search(r"^(Subject|To|Date|Sent):", lookahead, re.MULTILINE):
                break
        if line.startswith(">"):
            continue
        cleaned.append(line)
    result = "\n".join(cleaned).rstrip()
    if len(result.strip()) < 20 and len(body.strip()) > 20:
        return body
    return result


_SIG_DELIMITERS = [r"^-- $", r"^—$", r"^_{3,}$", r"^-{3,}$"]
_SIG_PHRASES = [
    r"^Best\s+regards", r"^Kind\s+regards", r"^Regards", r"^Sincerely",
    r"^Thanks", r"^Thank\s+you", r"^Cheers",
    r"^此致", r"^顺颂商祺", r"^祝好", r"^致敬", r"^谢谢", r"^感谢", r"^多谢",
    r"^Sent from my (iPhone|iPad|Galaxy|Android)", r"^发自我的", r"^Get Outlook for",
]
_SIG_DELIM_RE = re.compile("|".join(_SIG_DELIMITERS), re.MULTILINE)
_SIG_PHRASE_RE = re.compile("|".join(_SIG_PHRASES), re.IGNORECASE | re.MULTILINE)


def strip_signature(body: str) -> str:
    """移除邮件签名块。"""
    if not body:
        return body
    lines = body.splitlines()
    total = len(lines)
    if total < 3:
        return body
    search_start = max(0, min(int(total * 0.7), total - 15))
    cut_at = None
    for i in range(search_start, total):
        line = lines[i]
        if _SIG_DELIM_RE.match(line.rstrip()):
            cut_at = i
            break
        if _SIG_PHRASE_RE.match(line.strip()):
            cut_at = i
            break
    if cut_at is not None:
        result = "\n".join(lines[:cut_at]).rstrip()
        if len(result.strip()) < 20:
            return body
        return result
    return body


def _truncate_at_boundary(text: str, limit: int) -> str:
    """在 limit 字符以内找最近段落或句子边界截断。"""
    if len(text) <= limit:
        return text
    chunk = text[:limit]
    pos = chunk.rfind("\n\n")
    if pos > limit // 2:
        return chunk[:pos]
    for sep in ("。", "！", "？", ".\n", "!\n", "?\n", ". ", "! ", "? "):
        pos = chunk.rfind(sep)
        if pos > limit // 2:
            return chunk[:pos + len(sep)]
    pos = chunk.rfind("\n")
    if pos > limit // 2:
        return chunk[:pos]
    return chunk


def format_ai_context(ai_meta: dict) -> str:
    """将 AI 分析结果格式化为简洁上下文，仅取 one_line 摘要。"""
    if not ai_meta:
        return ""
    one_line = (ai_meta.get("summary") or {}).get("one_line", "")
    return f"邮件核心: {one_line}" if one_line else ""


def generate_reply(
    email_id: str, stance: str, tone: str, user_notes: str, account_id: str
) -> str:
    """生成回复草稿，返回纯文本。"""
    logger.info("生成回复: email_id=%s stance=%s tone=%s", email_id, stance, tone)

    # 获取数据
    email = _http_get(f"{CLAWMAIL_API}/emails/{email_id}")
    ai_meta = _http_get(f"{CLAWMAIL_API}/emails/{email_id}/ai-metadata")
    memories = _http_get(f"{CLAWMAIL_API}/memories/{account_id}") if account_id else {}
    user_profile = read_user_profile()

    # 获取线程历史（最近 4 封，排除当前邮件）
    thread_context = ""
    thread_id = email.get("thread_id")
    if thread_id:
        try:
            thread_data = _http_get(f"{CLAWMAIL_API}/emails/thread/{thread_id}?limit=5")
            thread_emails = [
                e for e in thread_data.get("emails", [])
                if e.get("id") != email_id
            ][-4:]
            if thread_emails:
                lines = []
                for e in thread_emails:
                    fa = e.get("from_address") or {}
                    sender_name = fa.get("name") or fa.get("email", "未知") if isinstance(fa, dict) else str(fa)
                    date_str = (e.get("received_at") or e.get("date", ""))[:10]
                    ai = e.get("ai_metadata") or {}
                    summary = (ai.get("summary") or {}).get("one_line") if isinstance(ai, dict) else ""
                    summary = summary or (e.get("body_text") or "")[:200]
                    lines.append(f"- [{date_str}] {sender_name}: {summary}")
                thread_context = "\n".join(lines)
        except Exception as e:
            logger.warning("获取线程历史失败: %s", e)

    # 发件人信息
    from_addr = email.get("from_address", {})
    if isinstance(from_addr, dict):
        sender_email = from_addr.get("email", "")
        sender = f"{from_addr.get('name', '')} <{sender_email}>".strip(" <>")
    else:
        sender_email = ""
        sender = str(from_addr)

    # 发件人画像（从 MemoryBank 的 contact.* 记忆中提取）
    sender_profile = format_sender_profile(memories, sender_email)

    # 加载 references
    reply_guide = load_reference("prompts/reply_guide.md")
    tone_styles = load_reference("prompts/tone_styles.md")
    memory_text = format_memories(memories)

    # 构建 system prompt
    sender_section = f"\n## 发件人画像\n{sender_profile}\n" if sender_profile else ""
    system_prompt = f"""你是一个邮件回复助手。请根据以下规则生成回复草稿。

## 用户侧写
{user_profile}

## 用户偏好记忆
{memory_text}
{sender_section}
## 回复规则
{reply_guide}

## 语气风格
{tone_styles}

请直接输出回复内容（纯文本），不要输出 JSON，不要添加标题或标签。"""

    # 正文预处理：去除引用历史和签名，再按边界截断
    body = email.get("body_text", "")
    body = strip_quoted_content(body)
    body = strip_signature(body)
    body = _truncate_at_boundary(body, 4000)

    # AI 分析摘要（避免 LLM 重复理解）
    ai_context = format_ai_context(ai_meta)

    # 构建 user prompt
    user_prompt = f"""原始邮件：
主题: {email.get('subject', '')}
发件人: {sender}
正文:
{body}
"""
    if ai_context:
        user_prompt += f"""
## AI 已分析摘要（供参考）
{ai_context}
"""
    if thread_context:
        user_prompt += f"""
## 对话历史（最近几封）
{thread_context}
"""
    user_prompt += f"""
---
请先判断：
1. 原邮件的意图类型（确认请求/信息请求/行动请求/问题投诉/通知FYI/跟进催促）
2. 发件人语气级别（正式/礼貌/轻松）

然后生成回复：
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
