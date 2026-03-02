#!/usr/bin/env python3
"""
extract_habits.py - 用户撰写习惯提取

用户发送邮件/回复后，分析用户撰写的内容提取写作习惯和沟通风格，
写入 pending facts。

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
    format="[Habits] %(asctime)s %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def load_reference(subpath: str) -> str:
    path = REFERENCES_DIR / subpath
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("Reference 文件不存在: %s", path)
    return ""


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


def api_get(path: str) -> dict:
    return _http_get(f"{CLAWMAIL_API}{path}")


def api_post(path: str, data: dict) -> dict:
    return _http_post_json(f"{CLAWMAIL_API}{path}", data)


def read_user_profile() -> str:
    user_md_path = Path.home() / ".openclaw" / "workspace" / "USER.md"
    if user_md_path.exists():
        return user_md_path.read_text(encoding="utf-8")
    return ""


def parse_json_array(raw: str) -> list:
    """从 LLM 输出中解析 JSON 数组。"""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        start = 1
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])
    try:
        result = json.loads(text)
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        s = text.find("[")
        e = text.rfind("]") + 1
        if s >= 0 and e > s:
            return json.loads(text[s:e])
        return []


def extract_habits(compose_data: dict, account_id: str) -> dict:
    """
    用户撰写/回复邮件后，提取习惯信息。

    Step 0: 获取上下文
    Step 1: LLM Call — 习惯提取
    Step 2: 写回 pending facts
    """
    logger.info("开始提取用户习惯 account_id=%s", account_id)

    # ── Step 0: 获取上下文 ──
    pending_facts = api_get(f"/pending-facts/{account_id}")
    user_profile = read_user_profile()

    # ── Step 1: LLM Call — 习惯提取 ──
    habit_rules = load_reference("prompts/habit_extraction.md")
    existing_facts = json.dumps(
        pending_facts.get("facts", []), ensure_ascii=False, indent=2
    )

    system_prompt = f"""你是一个用户习惯分析助手。分析用户撰写的邮件内容，提取写作习惯和沟通风格。

## 提取规则
{habit_rules}

## 用户当前侧写
{user_profile}

## 已有的 pending facts
{existing_facts}

请输出 JSON 数组，格式为：
[{{"fact_key": "...", "fact_category": "...", "fact_content": "...", "confidence": 0.0}}]

如果没有可提取的信息，输出空数组 []。
不要输出任何 JSON 之外的内容。"""

    user_prompt = f"""用户撰写了以下邮件：

主题: {compose_data.get('subject', '')}
收件人: {compose_data.get('to', '')}
正文:
{compose_data.get('body', '')[:4000]}

类型: {'回复' if compose_data.get('is_reply') else '新邮件'}"""

    facts_raw = call_llm(system_prompt, user_prompt)
    facts = parse_json_array(facts_raw)

    logger.info("习惯提取完成: %d 个 facts", len(facts))

    # ── Step 2: 写回 pending facts ──
    if facts:
        for f in facts:
            f["source_email_id"] = compose_data.get("email_id", "compose")
        api_post(f"/pending-facts/{account_id}", {"facts": facts})
        api_post(f"/pending-facts/{account_id}/promote", {})
        logger.info("Pending facts 已写入并触发提升检查")

    return {"status": "success", "facts_count": len(facts)}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="用户撰写习惯提取")
    parser.add_argument("--compose-data", required=True, help="用户撰写数据 JSON")
    parser.add_argument("--account-id", required=True, help="账户ID")
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
        data = json.loads(args.compose_data)
        result = extract_habits(data, args.account_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        logger.error("习惯提取失败: %s", e, exc_info=True)
        print(json.dumps(
            {"status": "error", "message": str(e)}, ensure_ascii=False, indent=2
        ))
        sys.exit(1)


if __name__ == "__main__":
    main()
