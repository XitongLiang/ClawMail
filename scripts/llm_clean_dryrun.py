#!/usr/bin/env python3
"""LLM-based memory cleaning dry-run: read DB, call LLM, print proposed operations."""
import sqlite3
import json
import re
import sys
import urllib.request

LLM_API = "http://127.0.0.1:18789/v1/chat/completions"
MODEL = "kimi-k2.5"
DB_PATH = r"C:\Users\a\clawmail_data\clawmail.db"
ACCOUNT_ID = "566fe429-81bc-4af5-8cab-0029897ed06d"


def _load_gateway_token() -> str:
    from pathlib import Path
    config_path = Path.home() / ".openclaw" / "openclaw.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        return config.get("gateway", {}).get("auth", {}).get("token", "")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return ""


LLM_TOKEN = _load_gateway_token()


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, memory_type, memory_key, memory_content, confidence_score, "
        "evidence_count, last_updated FROM user_preference_memory "
        "WHERE user_account_id=? ORDER BY memory_type, memory_key",
        (ACCOUNT_ID,),
    )
    rows = cur.fetchall()
    conn.close()

    print(f"共 {len(rows)} 条记忆，正在发送给 LLM 分析...\n")

    # Format memories for LLM
    mem_lines = []
    for r in rows:
        mid, mtype, mkey, mcontent, conf, ev, updated = r
        content = json.loads(mcontent) if mcontent else {}
        mem_lines.append(
            f"[id={mid}] type={mtype}, key={mkey}, evidence={ev}, "
            f"confidence={conf:.2f}, "
            f"content={json.dumps(content, ensure_ascii=False)}, "
            f"updated={updated}"
        )
    memories_text = "\n".join(mem_lines)

    system_prompt = (
        "你是一个 JSON 输出机器。你的唯一任务是根据用户的指令返回一个 JSON 数组。"
        "不要输出任何分析过程、解释、Markdown 标记或其他文字。"
        "只输出一个合法的 JSON 数组，以 [ 开头，以 ] 结尾。"
    )

    user_prompt = (
        "你是 ClawMail 的记忆清洗引擎。\n\n"
        "以下是用户的全部 AI 偏好记忆。请分析这些记忆，执行清洗操作：\n\n"
        "【全部记忆】\n"
        f"{memories_text}\n\n"
        "【清洗规则】\n"
        "1. **合并重复**：语义完全相同或高度相似的记忆才合并\n"
        "   - 注意：即使 memory_key 相同（如都是 None），只要 content 描述的是"
        "不同规则/不同信号/不同场景，就不是重复，不应合并\n"
        "   - 合并后 evidence_count = 各条之和\n"
        "   - confidence = 取较高值\n"
        "   - content 合并关键信息\n\n"
        "2. **解决矛盾**：同一 key 但 content 含义矛盾的记忆\n"
        "   - 保留 evidence_count 更高 / 更新鲜的那条\n"
        "   - 删除另一条\n\n"
        "3. **标注 skill_defect**：content 中 _source=\"skill_defect\" 的记忆\n"
        "   - 提取缺陷描述，方便后续优化 prompt\n\n"
        "【输出要求】\n"
        "返回 JSON 数组，每个元素是一个操作：\n"
        "[\n"
        '  {"op": "merge", "keep_id": "保留的记忆ID", "delete_ids": ["被合并删除的ID"], '
        '"merged_content": {}, "merged_evidence": 5, "merged_confidence": 0.8, '
        '"reason": "合并原因"},\n'
        '  {"op": "delete", "memory_id": "要删除的ID", "reason": "矛盾/过时/无意义"},\n'
        '  {"op": "flag_defect", "memory_id": "ID", "defect_type": "importance/summary/reply", '
        '"description": "缺陷描述"}\n'
        "]\n\n"
        "如果不需要任何清洗操作，返回空数组：[]\n"
        "直接返回 JSON 数组，不要 Markdown 标记或解释文字。"
    )

    # Call LLM
    payload = json.dumps({
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
    req = urllib.request.Request(
        LLM_API,
        data=payload,
        headers=headers,
        method="POST",
    )
    print("调用 LLM 中...")
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    raw = result["choices"][0]["message"]["content"]
    print(f"LLM 原始返回 ({len(raw)} 字符):\n")

    # Parse JSON
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        operations = json.loads(text)
        if not isinstance(operations, list):
            operations = []
    except (json.JSONDecodeError, ValueError):
        match = re.search(r"\[.*\]", text, flags=re.DOTALL)
        operations = json.loads(match.group()) if match else []

    print(f"LLM 返回 {len(operations)} 条清洗操作:\n")
    for i, op in enumerate(operations):
        print(f"{i+1}. {json.dumps(op, ensure_ascii=False, indent=2)}")
        print()

    # Summary comparison
    merge_count = sum(1 for o in operations if o.get("op") == "merge")
    delete_count = sum(1 for o in operations if o.get("op") == "delete")
    defect_count = sum(1 for o in operations if o.get("op") == "flag_defect")
    total_removed = sum(len(o.get("delete_ids", [])) for o in operations if o.get("op") == "merge")
    total_removed += delete_count

    print("=" * 50)
    print(f"汇总: merge={merge_count}, delete={delete_count}, flag_defect={defect_count}")
    print(f"预计清洗后: {len(rows)} → {len(rows) - total_removed} 条")
    print()
    print("对比规则化清洗:")
    print(f"  规则化: 35 → 23 条 (删除12条, 但误删5条urgency_signal)")
    print(f"  LLM:    {len(rows)} → {len(rows) - total_removed} 条")


if __name__ == "__main__":
    main()
