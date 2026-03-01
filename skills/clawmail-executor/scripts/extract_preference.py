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

# System prompt: 强制 LLM 只返回 JSON 数组
_SYSTEM_PROMPT = (
    "你是一个 JSON 输出机器。你的唯一任务是根据用户的指令返回一个 JSON 数组。"
    "不要输出任何分析过程、解释、Markdown 标记或其他文字。"
    "只输出一个合法的 JSON 数组，以 [ 开头，以 ] 结尾。"
)

# Executor prompt 模板（与 executor.py 对齐，逐个应用所有技能）
_EXECUTOR_PROMPT = """你是 ClawMail 的个性化记忆管理执行器。

你的任务：分析 AI 预测与用户修正之间的差异，从中提取用户偏好并输出记忆操作。

【当前邮件】
{email_data}

【AI 预测】
{prediction}

【用户修正】
{correction}

【已有用户记忆】
{existing_memories}

【可用技能（全部应用）】
{skills}

【指令】
- 逐个应用上述技能，分析用户修正背后的偏好
- 如果发现新偏好，输出 INSERT 操作
- 如果已有记忆需要更新（同一发件人/同类偏好），输出 UPDATE 操作并指定 memory_id
- 如果已有记忆明显错误，输出 DELETE 操作
- 不要输出没有依据的猜测，只基于实际的修正差异
- 如果修正幅度很小（< 10分）或无法推断偏好，输出空数组

【输出要求】
严格返回 JSON 数组，不要 Markdown 标记：
[
  {{"op": "insert", "memory_type": "类型", "memory_key": "键或null", "content": {{}}, "confidence": 0.7}},
  {{"op": "update", "memory_id": "已有记忆ID", "content": {{}}, "confidence": 0.8}},
  {{"op": "delete", "memory_id": "已有记忆ID", "reason": "原因"}}
]

如果没有值得记录的偏好，返回空数组：[]

重要：直接返回 JSON 数组，不要任何分析过程、Markdown 标记或解释文字。"""


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


def format_skills_from_reference(skills_text: str) -> str:
    """将 memory_types.md 内容转为技能说明段（--- 技能 N: name --- 格式）。"""
    # memory_types.md 已按 ## 技能 N: name 分节，直接使用整体内容
    return skills_text.strip()


def parse_json_array_from_llm(raw: str) -> list:
    """从 LLM 输出中解析 JSON 数组。"""
    import re
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except (json.JSONDecodeError, ValueError):
        match = re.search(r'\[.*\]', text, flags=re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                if isinstance(result, list):
                    return result
            except (json.JSONDecodeError, ValueError):
                pass
    logger.warning("JSON 数组解析失败: %s", text[:200])
    return []


def validate_operations(operations: list) -> list:
    """验证每个操作的基本格式，过滤无效条目。"""
    valid = []
    for op in operations:
        if not isinstance(op, dict):
            continue
        action = op.get("op", "").lower()
        if action == "insert" and "memory_type" in op:
            valid.append(op)
        elif action == "update" and "memory_id" in op:
            valid.append(op)
        elif action == "delete" and "memory_id" in op:
            valid.append(op)
    return valid


def apply_operations(account_id: str, operations: list) -> int:
    """通过 REST API 将记忆操作写入 MemoryBank，返回成功数量。"""
    count = 0
    for op in operations:
        action = op.get("op", "").lower()
        try:
            if action == "insert":
                payload = {
                    "memory_type": op["memory_type"],
                    "memory_key": op.get("memory_key"),
                    "memory_content": op.get("content", {}),
                    "confidence_score": float(op.get("confidence", 0.5)),
                    "evidence_count": 1,
                }
                _http_post_json(f"{CLAWMAIL_API}/memories/{account_id}", payload)
                count += 1
                logger.info("INSERT: type=%s key=%s", op["memory_type"], op.get("memory_key"))

            elif action == "update":
                payload = {
                    "op": "update",
                    "memory_id": op["memory_id"],
                    "content": op.get("content", {}),
                    "confidence": float(op.get("confidence", 0.7)),
                }
                _http_post_json(f"{CLAWMAIL_API}/memories/{account_id}", payload)
                count += 1
                logger.info("UPDATE: memory_id=%s", op["memory_id"])

            elif action == "delete":
                payload = {"op": "delete", "memory_id": op["memory_id"]}
                _http_post_json(f"{CLAWMAIL_API}/memories/{account_id}", payload)
                count += 1
                logger.info("DELETE: memory_id=%s", op["memory_id"])

        except Exception as e:
            logger.warning("操作失败 %s: %s", action, e)

    return count


def extract_preference(
    feedback_type: str, feedback_data: dict, email_id: str, account_id: str
) -> dict:
    """
    分析用户修正，提取偏好，写入 MemoryBank。

    Step 0: 获取邮件上下文和已有记忆
    Step 1: LLM Call — 逐个应用所有技能分析用户修正
    Step 2: 解析操作 → 写入 MemoryBank
    """
    logger.info(
        "提取偏好: type=%s email_id=%s account_id=%s",
        feedback_type, email_id, account_id,
    )

    # ── Step 0: 获取数据 ──
    email = _http_get(f"{CLAWMAIL_API}/emails/{email_id}")
    memories_resp = _http_get(f"{CLAWMAIL_API}/memories/{account_id}")
    existing_memories = memories_resp.get("memories", [])

    # ── 构建 prompt 各段 ──
    email_text = json.dumps(email, ensure_ascii=False, indent=2)

    if existing_memories:
        mem_lines = []
        for m in existing_memories[:10]:
            mem_lines.append(
                f"- [id={m.get('id', '?')}] type={m.get('memory_type')}, "
                f"key={m.get('memory_key')}, "
                f"confidence={m.get('confidence_score', 0):.2f}, "
                f"content={json.dumps(m.get('memory_content', {}), ensure_ascii=False)}"
            )
        existing_text = "\n".join(mem_lines)
    else:
        existing_text = "（暂无已有记忆）"

    # 构建预测/修正描述
    sender_email = email.get("from_address", {}).get("email", "unknown")
    if feedback_type == "importance_score":
        original = feedback_data.get("original_score", "?")
        user_val = feedback_data.get("user_score", "?")
        prediction = f"重要性评分: {original}/100"
        correction = f"用户修正为: {user_val}/100（差异: {abs(int(user_val) - int(original)) if str(original).isdigit() and str(user_val).isdigit() else '?'}）"
    elif feedback_type == "summary_rating":
        summary = feedback_data.get("summary", {})
        reasons = feedback_data.get("reasons", [])
        comment = feedback_data.get("comment", "")
        prediction = (
            f"AI 摘要:\n"
            f"- one_line: {summary.get('one_line', '')}\n"
            f"- brief: {summary.get('brief', '')}\n"
            f"- keywords: {summary.get('keywords', [])}"
        )
        parts = ["用户反馈: 差评"]
        if reasons:
            parts.append(f"问题原因: {', '.join(reasons)}")
        if comment:
            parts.append(f"用户补充说明: {comment}")
        correction = "\n".join(parts)
    elif feedback_type == "reply_edit":
        ai_draft = feedback_data.get("ai_draft", "")
        user_edited = feedback_data.get("user_edited", "")
        similarity = feedback_data.get("similarity", 1.0)
        prediction = f"AI 回复草稿:\n{ai_draft[:500]}"
        correction = f"用户最终版本（相似度: {similarity:.2%}）:\n{user_edited[:500]}"
    elif feedback_type == "category_change":
        prediction = f"原始分类: {feedback_data.get('original_categories', [])}"
        correction = f"用户修改为: {feedback_data.get('user_categories', [])}"
    else:
        prediction = f"AI 预测: {json.dumps(feedback_data.get('original', {}), ensure_ascii=False)}"
        correction = f"用户修正: {json.dumps(feedback_data.get('corrected', {}), ensure_ascii=False)}"

    # 加载技能库（memory_types.md 包含 5 个提取技能）
    skills_text = format_skills_from_reference(load_reference("prompts/memory_types.md"))

    # ── Step 1: LLM Call ──
    user_prompt = _EXECUTOR_PROMPT.format(
        email_data=email_text,
        prediction=prediction,
        correction=correction,
        existing_memories=existing_text,
        skills=skills_text,
    )

    logger.info("调用 LLM (executor)...")
    raw = call_llm(_SYSTEM_PROMPT, user_prompt)
    operations = validate_operations(parse_json_array_from_llm(raw))

    if not operations:
        logger.info("LLM 返回无操作（空数组）")
        return {"status": "skipped", "reason": "no_operations", "feedback_type": feedback_type}

    # ── Step 2: 写入 MemoryBank ──
    logger.info("LLM 返回 %d 条操作: %s", len(operations), [op.get("op") for op in operations])
    count = apply_operations(account_id, operations)

    logger.info("记忆操作完成: %d/%d 条成功", count, len(operations))
    return {
        "status": "success",
        "operations_total": len(operations),
        "operations_applied": count,
        "feedback_type": feedback_type,
    }


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
