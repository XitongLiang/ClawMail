#!/usr/bin/env python3
"""
extract_preference.py - 用户偏好提取

分析用户对 AI 预测的修正行为，提取偏好记忆并写入 ClawMail MemoryBank。
由 ClawMail 通过 subprocess 直接调用。
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
    format="[executor] %(asctime)s %(levelname)s: %(message)s",
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
        "temperature": 0.3,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if LLM_TOKEN:
        headers["Authorization"] = f"Bearer {LLM_TOKEN}"
    req = urllib.request.Request(LLM_API, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"]


def parse_json_from_llm(raw: str) -> dict:
    """从 LLM 输出中解析 JSON 对象。"""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise


def extract_preference(
    feedback_type: str, feedback_data: dict, email_id: str, account_id: str
) -> dict:
    """
    分析用户修正，提取偏好，写入 MemoryBank。

    Step 0: 获取邮件上下文和已有记忆
    Step 1: LLM Call — 偏好分析
    Step 2: 写入 MemoryBank（如果有结果）
    """
    logger.info(
        "提取偏好: type=%s email_id=%s account_id=%s",
        feedback_type, email_id, account_id,
    )

    # ── Step 0: 获取数据 ──
    email = _http_get(f"{CLAWMAIL_API}/emails/{email_id}")
    memories = _http_get(f"{CLAWMAIL_API}/memories/{account_id}")

    # ── Step 1: LLM Call — 偏好分析 ──
    extraction_guide = load_reference("prompts/memory_extraction_guide.md")
    memory_types = load_reference("prompts/memory_types.md")

    system_prompt = f"""你是一个用户偏好分析助手。分析用户对 AI 预测的修正行为，提取偏好记忆。

## 提取规则
{extraction_guide}

## 记忆类型定义
{memory_types}

## 已有记忆（参考，避免重复）
{json.dumps(memories.get('memories', [])[:10], ensure_ascii=False, indent=2)}

请输出一个 JSON 对象，格式为：
{{"memory_type": "...", "memory_key": "...", "memory_content": {{...}}, "confidence_score": 0.0, "evidence_count": 1}}

如果这次修正没有明确的偏好信号，输出 {{"skip": true, "reason": "..."}}。
不要输出任何 JSON 之外的内容。"""

    sender_email = email.get("from_address", {}).get("email", "unknown")
    user_prompt = f"""用户修正类型: {feedback_type}

邮件信息:
- 主题: {email.get('subject', '')}
- 发件人: {sender_email}
- 分类: {email.get('categories', [])}

修正数据:
{json.dumps(feedback_data, ensure_ascii=False, indent=2)}"""

    raw = call_llm(system_prompt, user_prompt)
    result = parse_json_from_llm(raw)

    # ── Step 2: 写入 MemoryBank ──
    if result.get("skip"):
        logger.info("偏好提取跳过: %s", result.get("reason"))
        return {"status": "skipped", "reason": result["reason"]}

    _http_post_json(f"{CLAWMAIL_API}/memories/{account_id}", result)

    logger.info(
        "记忆已写入: type=%s key=%s",
        result.get("memory_type"), result.get("memory_key"),
    )
    return {"status": "success", "memory": result}


def main():
    parser = argparse.ArgumentParser(description="用户偏好提取")
    parser.add_argument("--feedback-type", required=True,
                        choices=["importance_score", "summary_rating", "reply_edit", "category_change"])
    parser.add_argument("--feedback-data", required=True, help="JSON string")
    parser.add_argument("--email-id", required=True)
    parser.add_argument("--account-id", required=True)
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
        data = json.loads(args.feedback_data)
        result = extract_preference(
            args.feedback_type, data, args.email_id, args.account_id
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error("偏好提取失败: %s", e, exc_info=True)
        print(json.dumps(
            {"status": "error", "message": str(e)}, ensure_ascii=False, indent=2
        ))
        sys.exit(1)


if __name__ == "__main__":
    main()
