#!/usr/bin/env python3
"""
analyze_email.py - 邮件分析主脚本

分析收到的邮件：生成摘要、评分、分类、行动项、回复建议，并提取事实性信息。

用法: python analyze_email.py --email-id <id> --account-id <id>

由 ClawMail 通过 subprocess 直接调用，不经过 LLM 路由。
脚本控制执行流程，LLM 只负责在给定 prompt 下产出结构化结果。
"""

import argparse
import json
import re
import sys
import logging
from datetime import datetime
from pathlib import Path

import urllib.request
import urllib.error

# ─── 配置 ───

CLAWMAIL_API = "http://127.0.0.1:9999"
LLM_API = "http://127.0.0.1:18789/v1/chat/completions"
MODEL = "kimi-k2.5"
LLM_TOKEN = ""

SKILL_DIR = Path(__file__).parent.parent
REFERENCES_DIR = SKILL_DIR / "references"

logging.basicConfig(
    level=logging.INFO,
    format="[analyzer] %(asctime)s %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ─── 工具函数 ───


def load_reference(subpath: str) -> str:
    """加载 reference 文档内容。"""
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
    """调用 LLM，返回文本响应。"""
    logger.info("调用 LLM (model=%s)...", MODEL)
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
    content = result["choices"][0]["message"]["content"]
    logger.info("LLM 返回 %d 字符", len(content))
    return content


def api_get(path: str) -> dict:
    """GET 请求 ClawMail REST API。"""
    return _http_get(f"{CLAWMAIL_API}{path}")


def api_post(path: str, data: dict) -> dict:
    """POST 请求 ClawMail REST API。"""
    return _http_post_json(f"{CLAWMAIL_API}{path}", data)


def read_user_profile() -> str:
    """读取 USER.md 用户侧写。"""
    user_md_path = Path.home() / ".openclaw" / "workspace" / "USER.md"
    if user_md_path.exists():
        return user_md_path.read_text(encoding="utf-8")
    return ""


def format_memories(memories: dict) -> str:
    """将 memories API 返回值格式化为 prompt 段落。"""
    items = memories.get("memories", [])
    if not items:
        return "（无历史记忆）"
    lines = []
    for m in items:
        content = m.get("memory_content", {})
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        key = m.get("memory_key", "全局")
        lines.append(f"- [{m.get('memory_type', '?')}] {key}: {content}")
    return "\n".join(lines)


def parse_json_from_llm(raw: str, expect_type: str = "object"):
    """从 LLM 输出中解析 JSON。

    Args:
        raw: LLM 原始输出
        expect_type: "object" 或 "array"
    """
    text = raw.strip()
    # 去掉 markdown code fence
    if text.startswith("```"):
        lines = text.split("\n")
        # 去掉首行 ```json 和末行 ```
        start = 1
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end])

    try:
        result = json.loads(text)
        return result
    except json.JSONDecodeError:
        # 尝试找到 JSON 对象/数组
        if expect_type == "array":
            start = text.find("[")
            end = text.rfind("]") + 1
        else:
            start = text.find("{")
            end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise


# ─── 邮件正文预处理 ───


def strip_quoted_content(body: str) -> str:
    """移除引用的回复历史和转发头，使 4000 字符预算全部用于新增内容。"""
    if not body:
        return body
    lines = body.splitlines()
    cleaned = []

    for i, line in enumerate(lines):
        # "On {date}, {name} wrote:" (English)
        if re.match(r"^On .+ wrote:\s*$", line, re.IGNORECASE):
            break
        # "在 ... 写道：" (Chinese)
        if re.match(r"^在\s+.+写道[：:]\s*$", line):
            break
        # "---------- Forwarded message ----------"
        if re.match(
            r"^-{5,}\s*(Forwarded message|转发的邮件)\s*-{5,}",
            line,
            re.IGNORECASE,
        ):
            break
        # Forwarded "From:" header block (preceded by blank line, followed by Subject:/To:/Date:)
        if re.match(r"^From:\s+", line) and i > 0 and lines[i - 1].strip() == "":
            lookahead = "\n".join(lines[i : i + 5])
            if re.search(r"^(Subject|To|Date|Sent):", lookahead, re.MULTILINE):
                break
        # ">" quoted lines — skip individually
        if line.startswith(">"):
            continue
        cleaned.append(line)

    result = "\n".join(cleaned).rstrip()
    # Safety: if cleaning removed too much, return original
    if len(result.strip()) < 20 and len(body.strip()) > 20:
        return body
    return result


# Signature delimiter / phrase patterns
_SIG_DELIMITERS = [
    r"^-- $",       # RFC 3676 (trailing space)
    r"^—$",         # Em-dash
    r"^_{3,}$",     # Underscores
    r"^-{3,}$",     # Hyphens (alone on line)
]
_SIG_PHRASES = [
    r"^Best\s+regards",
    r"^Kind\s+regards",
    r"^Regards",
    r"^Sincerely",
    r"^Thanks",
    r"^Thank\s+you",
    r"^Cheers",
    r"^此致",
    r"^顺颂商祺",
    r"^祝好",
    r"^致敬",
    r"^Sent from my (iPhone|iPad|Galaxy|Android)",
    r"^发自我的",
    r"^Get Outlook for",
]
_SIG_DELIM_RE = re.compile("|".join(_SIG_DELIMITERS), re.MULTILINE)
_SIG_PHRASE_RE = re.compile("|".join(_SIG_PHRASES), re.IGNORECASE | re.MULTILINE)


def strip_signature(body: str) -> str:
    """移除邮件签名块。仅在正文后 30% 区域搜索，避免误判。"""
    if not body:
        return body
    lines = body.splitlines()
    total = len(lines)
    if total < 3:
        return body

    search_start = max(0, int(total * 0.7))
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


# ─── 列表长度限制 ───

_LIST_LIMITS = {
    "keywords": 8,
    "key_points": 5,
    "action_items": 10,
    "reply_stances": 4,
    "category": 4,
}


def _enforce_list_limits(analysis: dict) -> dict:
    """截断 LLM 返回的超长列表字段。"""
    summary = analysis.get("summary", {})
    metadata = analysis.get("metadata", {})

    for field in ("keywords", "key_points"):
        lst = summary.get(field)
        if isinstance(lst, list) and len(lst) > _LIST_LIMITS[field]:
            logger.info("截断 summary.%s: %d → %d", field, len(lst), _LIST_LIMITS[field])
            summary[field] = lst[: _LIST_LIMITS[field]]

    items = analysis.get("action_items")
    if isinstance(items, list) and len(items) > _LIST_LIMITS["action_items"]:
        logger.info("截断 action_items: %d → %d", len(items), _LIST_LIMITS["action_items"])
        analysis["action_items"] = items[: _LIST_LIMITS["action_items"]]

    for field in ("reply_stances", "category"):
        lst = metadata.get(field)
        if isinstance(lst, list) and len(lst) > _LIST_LIMITS[field]:
            logger.info("截断 metadata.%s: %d → %d", field, len(lst), _LIST_LIMITS[field])
            metadata[field] = lst[: _LIST_LIMITS[field]]

    return analysis


# ─── 入口1：分析新邮件 ───


def analyze_email(email_id: str, account_id: str) -> dict:
    """
    完整邮件分析流程（脚本控制，LLM 只回答问题）。

    Step 0: 从 ClawMail REST API 获取数据
    Step 1: LLM Call 1 — 邮件分析（summary + categories + importance + actions + stances）
    Step 2: LLM Call 2 — 事实提取（pending facts）
    Step 3: 写回结果
    """
    logger.info("开始分析邮件 email_id=%s account_id=%s", email_id, account_id)

    # ── Step 0: 获取数据 ──
    email = api_get(f"/emails/{email_id}")
    memories = api_get(f"/memories/{account_id}")
    pending_facts = api_get(f"/pending-facts/{account_id}")
    user_profile = read_user_profile()

    # ── Step 0b: 获取线程上下文（仅回复邮件） ──
    thread_context = []
    thread_id = email.get("thread_id")
    in_reply_to = email.get("in_reply_to")
    if thread_id and in_reply_to:
        try:
            thread_data = api_get(f"/emails/thread/{thread_id}")
            for te in thread_data.get("emails", []):
                if te["id"] == email_id:
                    break  # 只取当前邮件之前的
                if te.get("ai_summary_one_line"):
                    thread_context.append(te)
            if thread_context:
                logger.info("线程上下文: %d 封历史邮件", len(thread_context))
        except Exception as e:
            logger.warning("获取线程上下文失败: %s", e)

    logger.info("数据获取完成: email subject=%s", email.get("subject", ""))

    # ── Step 1: LLM Call 1 — 邮件分析 ──
    analysis_system = _build_analysis_system_prompt(user_profile, memories, thread_context)
    analysis_user = _build_email_user_prompt(email)
    analysis_raw = call_llm(analysis_system, analysis_user)
    analysis = parse_json_from_llm(analysis_raw, "object")
    analysis = _enforce_list_limits(analysis)

    logger.info("邮件分析完成: importance=%s", analysis.get("metadata", {}).get("importance_score"))

    # ── Step 2: LLM Call 2 — 事实提取 ──
    extraction_system = _build_extraction_system_prompt(user_profile, pending_facts)
    extraction_user = _build_email_user_prompt(email)
    facts_raw = call_llm(extraction_system, extraction_user)
    facts = parse_json_from_llm(facts_raw, "array")
    if not isinstance(facts, list):
        facts = []

    logger.info("事实提取完成: %d 个 facts", len(facts))

    # ── Step 3: 写回结果 ──
    api_post(f"/emails/{email_id}/ai-metadata", analysis)
    logger.info("AI metadata 已写入")

    if facts:
        source_email_id = email_id
        facts_with_source = []
        for f in facts:
            f["source_email_id"] = source_email_id
            facts_with_source.append(f)
        api_post(f"/pending-facts/{account_id}", {"facts": facts_with_source})
        api_post(f"/pending-facts/{account_id}/promote")
        logger.info("Pending facts 已写入并触发提升检查")

    return {
        "status": "success",
        "email_id": email_id,
        "importance_score": analysis.get("metadata", {}).get("importance_score"),
        "facts_count": len(facts),
    }


# ─── Prompt 构建 ───


def _build_analysis_system_prompt(
    user_profile: str, memories: dict, thread_context: list = None,
) -> str:
    """构建邮件分析的 system prompt。"""
    summary_guide = load_reference("prompts/summary_guide.md")
    importance_algo = load_reference("prompts/importance_algorithm.md")
    category_rules = load_reference("prompts/category_rules.md")
    field_defs = load_reference("specs/field_definitions.md")
    output_schema = load_reference("specs/output_schema.md")
    memory_section = format_memories(memories)

    # 线程上下文段落（仅回复邮件才有）
    thread_section = ""
    if thread_context:
        thread_guide = load_reference("prompts/thread_context_guide.md")
        lines = []
        for te in thread_context:
            from_info = te.get("from_address", {})
            name = from_info.get("name") or from_info.get("email", "?")
            date = te.get("received_at", "?")
            one_line = te.get("ai_summary_one_line", "")
            lines.append(f"- [{date}] {name}: {one_line}")
        thread_section = (
            "\n## 线程上下文（当前邮件是回复，以下为此前的对话历史）\n"
            + "\n".join(lines)
            + "\n\n"
            + thread_guide
        )

    return f"""你是一个邮件分析助手。请严格按照以下规则分析邮件。

## 用户侧写
{user_profile}

## 用户偏好记忆
{memory_section}
{thread_section}
## 摘要规则
{summary_guide}

## 重要性评分算法
{importance_algo}

## 分类规则
{category_rules}

## 输出字段定义
{field_defs}

## 输出格式
请严格输出 JSON，格式如下：
{output_schema}

不要输出任何 JSON 之外的内容。"""


def _build_extraction_system_prompt(user_profile: str, pending_facts: dict) -> str:
    """构建事实提取的 system prompt。"""
    extraction_rules = load_reference("prompts/profile_extraction.md")
    existing_facts = json.dumps(
        pending_facts.get("facts", []), ensure_ascii=False, indent=2
    )

    return f"""你是一个用户信息提取助手。从邮件中提取关于收件人（用户）的事实性信息。

## 提取规则
{extraction_rules}

## 用户当前侧写
{user_profile}

## 已有的 pending facts（避免重复）
{existing_facts}

请输出 JSON 数组，格式为：
[{{"fact_key": "...", "fact_category": "...", "fact_content": "...", "confidence": 0.0}}]

如果没有可提取的信息，输出空数组 []。
不要输出任何 JSON 之外的内容。"""


def _build_email_user_prompt(email: dict) -> str:
    """构建邮件的 user prompt（分析和提取共用）。"""
    body = email.get("body_text", "")
    body = strip_quoted_content(body)
    body = strip_signature(body)
    body = body[:4000]
    return f"""请分析以下邮件：

主题: {email.get('subject', '')}
发件人: {json.dumps(email.get('from_address', {}), ensure_ascii=False)}
收件人: {json.dumps(email.get('to_addresses', []), ensure_ascii=False)}
抄送: {json.dumps(email.get('cc_addresses', []), ensure_ascii=False)}
时间: {email.get('received_at', '')}
正文:
{body}"""


# ─── 错误处理 ───


def create_error_result(error_code: str, message: str, email_id: str = None) -> dict:
    """创建错误结果。"""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
        "email_id": email_id,
    }


# ─── CLI ───


def main():
    parser = argparse.ArgumentParser(description="ClawMail Analyzer Skill")
    parser.add_argument("--email-id", required=True, help="邮件ID")
    parser.add_argument("--account-id", required=True, help="账户ID")
    parser.add_argument(
        "--clawmail-api", default="http://127.0.0.1:9999",
        help="ClawMail REST API 地址"
    )
    parser.add_argument(
        "--llm-api", default="http://127.0.0.1:18789/v1/chat/completions",
        help="LLM API 地址"
    )
    parser.add_argument("--model", default="kimi-k2.5", help="LLM 模型名称")
    parser.add_argument("--llm-token", default="", help="LLM Gateway auth token")
    args = parser.parse_args()

    # 更新全局配置
    global CLAWMAIL_API, LLM_API, MODEL, LLM_TOKEN
    CLAWMAIL_API = args.clawmail_api
    LLM_API = args.llm_api
    MODEL = args.model
    LLM_TOKEN = args.llm_token

    try:
        result = analyze_email(args.email_id, args.account_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    except urllib.error.URLError as e:
        logger.error("连接失败: %s", e)
        print(json.dumps(create_error_result(
            "SERVICE_UNAVAILABLE", f"服务连接失败: {e}"
        ), ensure_ascii=False, indent=2))
        sys.exit(1)

    except TimeoutError as e:
        logger.error("请求超时: %s", e)
        print(json.dumps(create_error_result(
            "TIMEOUT", f"请求超时: {e}"
        ), ensure_ascii=False, indent=2))
        sys.exit(1)

    except json.JSONDecodeError as e:
        logger.error("JSON 解析失败: %s", e)
        print(json.dumps(create_error_result(
            "PROCESSING_FAILED", f"LLM 输出解析失败: {e}"
        ), ensure_ascii=False, indent=2))
        sys.exit(1)

    except Exception as e:
        logger.error("未知错误: %s", e, exc_info=True)
        print(json.dumps(create_error_result(
            "PROCESSING_FAILED", f"分析过程出错: {e}"
        ), ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
