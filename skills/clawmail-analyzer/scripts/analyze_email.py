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
import urllib.parse

# ─── 配置 ───

CLAWMAIL_API = "http://127.0.0.1:9999"
LLM_API = "http://127.0.0.1:18789/v1/chat/completions"
MODEL = "kimi-k2.5"
LLM_TOKEN = ""

SKILL_DIR = Path(__file__).parent.parent
REFERENCES_DIR = SKILL_DIR / "references"

logging.basicConfig(
    level=logging.INFO,
    format="[Analyzer] %(asctime)s %(levelname)s: %(message)s",
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


class ContentFilterError(Exception):
    """LLM 内容安全过滤拒绝了请求。"""
    pass


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
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if LLM_TOKEN:
        headers["Authorization"] = f"Bearer {LLM_TOKEN}"
    req = urllib.request.Request(LLM_API, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        if e.code == 400 and "high risk" in body.lower():
            logger.warning("LLM 内容安全过滤 (400): %s", body[:200])
            raise ContentFilterError(body[:200]) from e
        raise
    content = result["choices"][0]["message"]["content"]
    # 某些 API 在 200 响应体内返回拒绝消息
    if content and "rejected" in content.lower() and "high risk" in content.lower():
        logger.warning("LLM 内容安全过滤 (响应体): %s", content[:200])
        raise ContentFilterError(content[:200])
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


# 按 memory_type 分类的过期天数（超过则不注入 prompt）
# None 表示永不过期
_MEMORY_TTL_DAYS = {
    "contact":              None,   # 关系记忆，基本不过期
    "sender_importance":    180,    # 用户偏好，半年
    "urgency_signal":       180,
    "automated_content":    180,
    "summary_preference":   180,
    "response_pattern":     180,
    "project_state":        90,     # 项目信息，衰减快
}
_DEFAULT_TTL_DAYS = 120  # 未列出的类型默认 4 个月


def _memory_age_days(m: dict) -> int:
    """计算记忆距今天数。无法解析时返回 0（视为新鲜）。"""
    ts = m.get("last_updated") or m.get("created_at")
    if not ts:
        return 0
    try:
        # API 返回 ISO 格式，兼容带 T 和不带 T
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return max(0, (datetime.now(dt.tzinfo) - dt).days)
    except (ValueError, TypeError):
        return 0


def format_memories(memories: dict, only_types: set = None) -> str:
    """将 memories API 返回值格式化为 prompt 段落。

    - contact.* 排除（已在发件人画像段落单独展示）
    - 其他类型按 _MEMORY_TTL_DAYS 策略过滤过期记忆
    - 输出中附带年龄标签，帮助 LLM 判断时效性
    - only_types: 若指定，则只返回这些 memory_type 的记忆
    """
    items = memories.get("memories", [])
    # contact.* 有专属 format_sender_profile 处理
    items = [m for m in items if not (m.get("memory_key") or "").startswith("contact.")]

    if only_types:
        items = [m for m in items if m.get("memory_type", "") in only_types]

    filtered = []
    for m in items:
        mtype = m.get("memory_type", "")
        ttl = _MEMORY_TTL_DAYS.get(mtype, _DEFAULT_TTL_DAYS)
        age = _memory_age_days(m)
        if ttl is not None and age > ttl:
            continue
        # 证据门槛：单次操作产生的记忆不注入，至少需要 2 次确认
        evidence = m.get("evidence_count", 1)
        if evidence < 2:
            continue
        filtered.append((m, age))

    if not filtered:
        return ""

    lines = []
    for m, age in filtered:
        content = m.get("memory_content", {})
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        key = m.get("memory_key") or "全局"
        confidence = m.get("confidence_score", 0.5)
        evidence = m.get("evidence_count", 1)
        # 年龄标签 + 置信度，让 LLM 感知时效和可靠性
        if age <= 1:
            age_tag = "今天"
        elif age <= 7:
            age_tag = f"{age}天前"
        elif age <= 30:
            age_tag = f"{age // 7}周前"
        else:
            age_tag = f"{age // 30}个月前"
        lines.append(
            f"- {key}: {content} ({age_tag}, 置信度{confidence:.0%}, 证据{evidence}次)"
        )
    return "\n".join(lines)


def format_sender_profile(memories: dict, sender_email: str) -> str:
    """从 memories 中提取指定发件人的画像记忆，格式化为 prompt 段落。

    筛选 memory_key 以 contact.{sender_email} 开头的条目，
    包含关系、职位、信息流向、沟通模式等历史记录。
    """
    if not sender_email:
        return ""
    items = memories.get("memories", [])
    prefix = f"contact.{sender_email.lower()}"
    sender_items = [
        m for m in items
        if (m.get("memory_key") or "").lower().startswith(prefix)
    ]
    if not sender_items:
        return ""
    lines = []
    for m in sender_items:
        content = m.get("memory_content", {})
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        key = m.get("memory_key") or ""
        lines.append(f"- {key}: {content}")
    return "\n".join(lines)


def _strip_code_fences(text: str) -> str:
    """去掉 markdown code fence（```json ... ```），支持任意位置。"""
    import re
    # 匹配 ```json ... ``` 或 ``` ... ```
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 仅开头有 ``` 但无闭合（截断情况）
    if text.startswith("```"):
        lines = text.split("\n")
        return "\n".join(lines[1:])
    return text


def _repair_json_quotes(text: str) -> str:
    """修复 LLM 输出中 JSON 字符串值内未转义的双引号。

    策略：
    1. 先把中文弯引号 \u201c\u201d 统一替换为 ASCII "
    2. 逐字符扫描，区分 JSON 结构引号和值内嵌套引号
    3. 值内嵌套引号替换为「」
    """
    # Step 1: 统一引号为 ASCII
    text = text.replace("\u201c", '"').replace("\u201d", '"')

    # Step 2: 逐字符状态机，识别 JSON 字符串值内的嵌套引号
    result = []
    i = 0
    in_string = False
    while i < len(text):
        ch = text[i]
        if ch == '\\' and in_string:
            # 转义字符，原样保留
            result.append(text[i:i+2])
            i += 2
            continue
        if ch == '"':
            if not in_string:
                # 进入字符串
                in_string = True
                result.append(ch)
            else:
                # 当前在字符串内，判断这个 " 是结束引号还是嵌套引号
                # 看后面第一个非空白字符是否为 JSON 结构符: , ] } :
                rest = text[i+1:].lstrip()
                if not rest or rest[0] in ',:]}':
                    # 是 JSON 结构引号 → 结束字符串
                    in_string = False
                    result.append(ch)
                else:
                    # 是值内嵌套引号 → 替换为「
                    # 找配对的闭合嵌套引号
                    close = text.find('"', i + 1)
                    if close != -1:
                        inner = text[i+1:close]
                        # 检查闭合引号后面是否也是非结构符（确认是嵌套对）
                        rest2 = text[close+1:].lstrip()
                        if inner and len(inner) <= 30 and (not rest2 or rest2[0] not in ',:]}'):
                            # 嵌套引号对
                            result.append('「')
                            result.append(inner)
                            result.append('」')
                            i = close + 1
                            continue
                    # 无法配对，转义处理
                    result.append('\\"')
        else:
            result.append(ch)
        i += 1
    return ''.join(result)


def parse_json_from_llm(raw: str, expect_type: str = "object"):
    """从 LLM 输出中解析 JSON。

    Args:
        raw: LLM 原始输出
        expect_type: "object" 或 "array"
    """
    text = _strip_code_fences(raw.strip())

    try:
        result = json.loads(text)
        return result
    except json.JSONDecodeError:
        pass

    # 尝试提取 JSON 对象/数组
    if expect_type == "array":
        start = text.find("[")
        end = text.rfind("]") + 1
    else:
        start = text.find("{")
        end = text.rfind("}") + 1
    if start >= 0 and end > start:
        fragment = text[start:end]
        try:
            return json.loads(fragment)
        except json.JSONDecodeError:
            # 尝试修复引号问题
            repaired = _repair_json_quotes(fragment)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                pass
    raise json.JSONDecodeError("无法解析 LLM 返回的 JSON", text, 0)


# ─── 邮件正文预处理 ───


def strip_quoted_content(body: str) -> str:
    """移除引用的回复历史和转发头，使 4000 字符预算全部用于新增内容。"""
    if not body:
        return body
    lines = body.splitlines()
    cleaned = []

    for i, line in enumerate(lines):
        # "On {date}, {name} wrote:" — 可能跨两行（Gmail/Outlook 自动换行）
        if re.match(r"^On\s+", line, re.IGNORECASE):
            candidate = line.rstrip()
            if i + 1 < len(lines):
                candidate = candidate + " " + lines[i + 1].strip()
            if re.search(r"wrote:\s*$", candidate, re.IGNORECASE):
                break
        # "在 ... 写道：" — 同样支持跨两行
        if re.match(r"^在\s+", line):
            candidate = line.rstrip()
            if i + 1 < len(lines):
                candidate = candidate + " " + lines[i + 1].strip()
            if re.search(r"写道[：:]\s*$", candidate):
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
    r"^谢谢",
    r"^感谢",
    r"^多谢",
    r"^Sent from my (iPhone|iPad|Galaxy|Android)",
    r"^发自我的",
    r"^Get Outlook for",
]
_SIG_DELIM_RE = re.compile("|".join(_SIG_DELIMITERS), re.MULTILINE)
_SIG_PHRASE_RE = re.compile("|".join(_SIG_PHRASES), re.IGNORECASE | re.MULTILINE)


def strip_signature(body: str) -> str:
    """移除邮件签名块。在正文后 30% 或末尾 15 行（取较大范围）搜索，避免误判。"""
    if not body:
        return body
    lines = body.splitlines()
    total = len(lines)
    if total < 3:
        return body

    # 取 30% 和 末尾15行 中更靠前的起点，确保短邮件也能搜到签名
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
    """在 limit 字符以内，找最近的段落或句子边界截断，避免切到词/句中间。"""
    if len(text) <= limit:
        return text
    chunk = text[:limit]
    # 优先：双换行（段落边界）
    pos = chunk.rfind("\n\n")
    if pos > limit // 2:
        return chunk[:pos]
    # 其次：中英文句尾标点
    for sep in ("。", "！", "？", ".\n", "!\n", "?\n", ". ", "! ", "? "):
        pos = chunk.rfind(sep)
        if pos > limit // 2:
            return chunk[:pos + len(sep)]
    # 最后：普通换行
    pos = chunk.rfind("\n")
    if pos > limit // 2:
        return chunk[:pos]
    return chunk


# ─── importance 计算（Python 负责算术，LLM 只负责判断） ───


def compute_importance_score(raw_scores: dict) -> tuple:
    """从 LLM 输出的四维原始分（0-100）计算加权总分和完整 breakdown。"""
    s = max(0, min(100, int(raw_scores.get("sender_score",     0))))
    u = max(0, min(100, int(raw_scores.get("urgency_score",    0))))
    d = max(0, min(100, int(raw_scores.get("deadline_score",   0))))
    c = max(0, min(100, int(raw_scores.get("complexity_score", 0))))
    total = s * 0.25 + u * 0.35 + d * 0.25 + c * 0.15
    breakdown = {
        "sender_weight":     25, "sender_score":     s, "sender_contrib":     round(s * 0.25, 2),
        "urgency_weight":    35, "urgency_score":    u, "urgency_contrib":    round(u * 0.35, 2),
        "deadline_weight":   25, "deadline_score":   d, "deadline_contrib":   round(d * 0.25, 2),
        "complexity_weight": 15, "complexity_score": c, "complexity_contrib": round(c * 0.15, 2),
        "total": round(total, 2),
    }
    return round(total), breakdown


# ─── 默认值补全 ───

_VALID_SENTIMENTS = {"positive", "negative", "neutral"}
_VALID_LANGUAGES  = {"zh", "en", "ja"}


def _apply_defaults(result: dict) -> dict:
    """为 LLM 输出补全缺失字段，防止下游访问时 KeyError / TypeError。"""
    # summary
    summary = result.setdefault("summary", {})
    summary.setdefault("keywords", [])
    summary.setdefault("one_line", "")
    summary.setdefault("brief",    "")

    # action_items
    if not isinstance(result.get("action_items"), list):
        result["action_items"] = []

    # metadata
    meta = result.setdefault("metadata", {})
    meta.setdefault("category", [])
    if meta.get("sentiment") not in _VALID_SENTIMENTS:
        meta["sentiment"] = "neutral"
    if meta.get("language") not in _VALID_LANGUAGES:
        meta["language"] = "zh"
    conf = meta.get("confidence")
    meta["confidence"] = (
        max(0.0, min(1.0, float(conf))) if isinstance(conf, (int, float)) else 0.0
    )
    meta.setdefault("is_spam",           False)
    meta.setdefault("importance_scores", {})
    meta.setdefault("suggested_reply",   None)
    meta.setdefault("reply_stances",     [])

    # pending_facts
    if not isinstance(result.get("pending_facts"), list):
        result["pending_facts"] = []

    return result


# ─── 列表长度限制 ───

_LIST_LIMITS = {
    "keywords": 8,
    "action_items": 10,
    "reply_stances": 4,
    "category": 4,
}


def _enforce_list_limits(analysis: dict) -> dict:
    """截断 LLM 返回的超长列表字段。"""
    summary = analysis.get("summary", {})
    metadata = analysis.get("metadata", {})

    lst = summary.get("keywords")
    if isinstance(lst, list) and len(lst) > _LIST_LIMITS["keywords"]:
        logger.info("截断 summary.keywords: %d → %d", len(lst), _LIST_LIMITS["keywords"])
        summary["keywords"] = lst[: _LIST_LIMITS["keywords"]]

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


def analyze_email(email_id: str, account_id: str, is_sent: bool = False) -> dict:
    """
    完整邮件分析流程（脚本控制，LLM 只回答问题）。

    Step 0: 从 ClawMail REST API 获取数据
    Step 1: 单次 LLM 调用（分析 + 事实提取合并）
    Step 2: 后处理（默认值补全 → 列表截断 → Python 计算 importance → 提取 facts）
    Step 3: 写回结果
    """
    logger.info("开始分析邮件 email_id=%s account_id=%s", email_id, account_id)

    # ── Step 0: 获取数据 ──
    email = api_get(f"/emails/{email_id}")

    # 确定关键联系人（收件邮件=发件人，已发送=收件人）
    if is_sent:
        to_addrs = email.get("to_addresses") or []
        first = to_addrs[0] if to_addrs else {}
        sender_email = first.get("email", "") if isinstance(first, dict) else str(first)
    else:
        sender_email = (email.get("from_address") or {}).get("email", "")

    # 按发件人过滤记忆（全局偏好 + 发件人 + 域名），不拉全量
    memories = api_get(
        f"/memories/{account_id}/for-email?sender_email="
        + urllib.parse.quote(sender_email, safe="")
    )
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

    # ── 统计可用记忆 ──
    all_mem = memories.get("memories", [])
    _count = lambda txt: len(txt.splitlines()) if txt else 0
    n_imp = _count(format_memories(memories, only_types={"sender_importance", "urgency_signal", "automated_content"}))
    n_sum = _count(format_memories(memories, only_types={"summary_preference"}))
    n_profile = len([m for m in all_mem if (m.get("memory_key") or "").startswith(f"contact.{sender_email.lower()}")])
    n_total = n_imp + n_sum + n_profile
    if n_total:
        print(f"[Analyzer] 邮件分析中：应用 {n_total} 条记忆"
              f"（重要性 {n_imp}, 摘要 {n_sum}, 联系人 {n_profile}）",
              file=sys.stderr)
    else:
        print(f"[Analyzer] 邮件分析中：无可用记忆（共 {len(all_mem)} 条未达注入门槛）",
              file=sys.stderr)

    # ── Step 1: 单次 LLM 调用（分析 + 事实提取合并） ──
    system_prompt = _build_analysis_system_prompt(
        user_profile, memories, thread_context, pending_facts, sender_email,
        is_sent=is_sent,
    )
    user_prompt = _build_email_user_prompt(email, is_sent=is_sent)
    try:
        raw = call_llm(system_prompt, user_prompt)
    except ContentFilterError:
        # LLM 安全过滤拒绝，返回最小有效结果
        subject = email.get("subject", "")
        result = _apply_defaults({
            "summary": {
                "keywords": [],
                "one_line": f"（内容无法分析）{subject[:20]}",
                "brief": "邮件内容触发安全过滤，无法生成摘要。",
            },
            "action_items": [],
            "metadata": {"category": [], "confidence": 0.0},
            "pending_facts": [],
        })
        result = _enforce_list_limits(result)
        return result
    try:
        result = parse_json_from_llm(raw, "object")
    except (json.JSONDecodeError, ValueError):
        logger.warning("JSON 解析失败，重试一次。原始返回: %s", raw[:500])
        # 重试：用更强的 JSON 约束提示
        retry_prompt = (
            "你上次的回复不是有效 JSON。请严格只输出 JSON 对象，"
            "不要输出任何其他文字、markdown 格式或解释。\n\n"
            + user_prompt
        )
        raw = call_llm(system_prompt, retry_prompt)
        try:
            result = parse_json_from_llm(raw, "object")
        except (json.JSONDecodeError, ValueError):
            logger.error("重试后仍然解析失败。原始返回: %s", raw[:500])
            raise
    result = _apply_defaults(result)
    result = _enforce_list_limits(result)

    # ── Step 2: 后处理（Python 计算 importance，提取 facts） ──
    metadata = result.setdefault("metadata", {})

    if is_sent:
        # 已发送邮件：LLM 只输出 summary + pending_facts，手动补全其余字段默认值
        result.setdefault("action_items", [])
        metadata["is_spam"] = False
        metadata.pop("importance_scores", None)
        metadata["importance_score"] = 0
        metadata["importance_breakdown"] = {}
        metadata.setdefault("category", [])
        metadata.setdefault("sentiment", "neutral")
        metadata.setdefault("confidence", 0.8)
        metadata.setdefault("suggested_reply", None)
        metadata.setdefault("reply_stances", [])
        logger.info("已发送邮件，跳过 spam/importance，补全默认值")
    else:
        is_spam = metadata.get("is_spam", False)
        if is_spam:
            logger.info("检测为垃圾邮件，importance_score 强制为 0")
            metadata["importance_score"] = 0
            metadata["importance_breakdown"] = {}
        else:
            raw_scores = metadata.pop("importance_scores", {})
            score, breakdown = compute_importance_score(raw_scores)
            metadata["importance_score"] = score
            metadata["importance_breakdown"] = breakdown
            logger.info("邮件分析完成: importance_score=%d", score)

    # 从合并结果中取出 pending_facts（不写入 ai-metadata）
    facts = result.pop("pending_facts", [])
    if not isinstance(facts, list):
        facts = []
    logger.info("事实提取完成: %d 个 facts", len(facts))

    # 按 fact_key 分流：
    #   contact.*   → 直接写 MemoryBank（关系记忆，立即生效）
    #   project.*   → 直接写 MemoryBank（项目信息有时效性，需要可更新/清理）
    #   其他（career/org）→ pending 池，积累后 promote 到 USER.md

    def _is_direct_fact(f: dict) -> bool:
        key = f.get("fact_key") or ""
        return key.startswith("contact.") or key.startswith("project.")

    direct_facts  = [f for f in facts if _is_direct_fact(f)]
    profile_facts = [f for f in facts if not _is_direct_fact(f)]

    # ── Step 3: 写回结果 ──
    api_post(f"/emails/{email_id}/ai-metadata", result)
    logger.info("AI metadata 已写入")

    if direct_facts:
        today = datetime.today().date().isoformat()
        for f in direct_facts:
            content = f.get("fact_content", "")
            # project_state 类型自动注入提取日期，方便未来清理判断
            if f.get("fact_category") == "project_state":
                if isinstance(content, str):
                    try:
                        content = json.loads(content)
                    except (json.JSONDecodeError, ValueError):
                        content = {"raw": content}
                if isinstance(content, dict):
                    content.setdefault("extracted_date", today)
            api_post(f"/memories/{account_id}", {
                "memory_type":      f.get("fact_category", "contact"),
                "memory_key":       f.get("fact_key", ""),
                "memory_content":   content,
                "confidence_score": float(f.get("confidence", 0.5)),
                "evidence_count":   1,
            })
        logger.info("direct facts 直接写入 MemoryBank: %d 条", len(direct_facts))

    if profile_facts:
        for f in profile_facts:
            f["source_email_id"] = email_id
        api_post(f"/pending-facts/{account_id}", {"facts": profile_facts})
        api_post(f"/pending-facts/{account_id}/promote", {})
        logger.info("profile facts 写入 pending 池并触发提升检查: %d 条", len(profile_facts))

    return {
        "status": "success",
        "email_id": email_id,
        "importance_score": result.get("metadata", {}).get("importance_score"),
        "facts_count": len(facts),
    }


# ─── Prompt 构建 ───


def _build_analysis_system_prompt(
    user_profile: str, memories: dict, thread_context: list = None,
    pending_facts: dict = None, sender_email: str = "",
    is_sent: bool = False,
) -> str:
    """构建 system prompt。is_sent=True 时走轻量路径（仅摘要 + 事实）。"""
    extraction_rules = load_reference("prompts/profile_extraction.md")
    existing_facts   = json.dumps(
        (pending_facts or {}).get("facts", []), ensure_ascii=False
    )

    # 按用途拆分记忆，避免不同领域的记忆互相干扰
    _IMPORTANCE_TYPES = {"sender_importance", "urgency_signal", "automated_content"}
    _SUMMARY_TYPES = {"summary_preference"}

    summary_memories    = format_memories(memories, only_types=_SUMMARY_TYPES)
    importance_memories = format_memories(memories, only_types=_IMPORTANCE_TYPES)

    # 联系人画像（收件邮件=发件人画像，已发送=收件人画像）
    profile_text = format_sender_profile(memories, sender_email)
    if is_sent:
        profile_section = (
            f"\n## 收件人画像（历史记忆）\n{profile_text}\n"
            if profile_text else ""
        )
    else:
        profile_section = (
            f"\n## 发件人画像（历史记忆）\n{profile_text}\n"
            if profile_text else ""
        )

    # ── 已发送邮件：轻量 prompt ──
    if is_sent:
        sent_guide = load_reference("prompts/sent_email_guide.md")
        summary_pref_section = (
            f"\n### 用户摘要偏好\n{summary_memories}\n"
            if summary_memories else ""
        )
        return f"""你是一个邮件分析助手。请分析用户发出的邮件，完成摘要和事实提取。

## 用户侧写
{user_profile}
{profile_section}
## 已发送邮件分析指南
{sent_guide}
{summary_pref_section}
## 用户事实提取规则
{extraction_rules}

## 已有 pending facts（避免重复提取）
{existing_facts}

## 输出格式
严格输出以下 JSON，不要输出任何其他内容：

{{
  "summary": {{
    "keywords": ["最多5个关键词"],
    "one_line": "30字以内概括用户做了什么/说了什么",
    "brief": "1-3行摘要"
  }},
  "pending_facts": [
    {{"fact_key": "contact.recipient@example.com.relationship", "fact_category": "contact", "fact_content": "...", "confidence": 0.0}}
  ]
}}

**重要规则**：
- 这是用户自己发出的邮件，contact.* 的 key 必须以收件人 email 为前缀
- one_line 概括"用户做了什么"，不是"收到了什么"
- 每封邮件最多提取 3 个 facts
- brief 必须基于原文，不得推断"""

    # ── 收件邮件：完整 prompt ──
    summary_guide    = load_reference("prompts/summary_guide.md")
    importance_algo  = load_reference("prompts/importance_algorithm.md")
    category_rules   = load_reference("prompts/category_rules.md")

    # 将记忆注入对应规则段，而非统一堆在顶部
    summary_pref_section = (
        f"\n### 用户摘要偏好（历史反馈学习）\n{summary_memories}\n"
        if summary_memories else ""
    )
    importance_pref_section = (
        f"\n### 用户重要性偏好（历史反馈学习）\n{importance_memories}\n"
        if importance_memories else ""
    )

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

    return f"""你是一个邮件分析助手。请一次性完成邮件分析和用户事实提取两项任务。

## 用户侧写
{user_profile}
{profile_section}{thread_section}
## 摘要规则
{summary_guide}
{summary_pref_section}
## 重要性评分规则
{importance_algo}
{importance_pref_section}
## 分类规则
{category_rules}

## 用户事实提取规则
{extraction_rules}

## 已有 pending facts（避免重复提取）
{existing_facts}

## 输出格式
严格输出以下 JSON，不要输出任何其他内容：

{{
  "summary": {{
    "keywords": ["最多8个关键词"],
    "one_line": "30字以内核心概括，如有具体数字/日期/金额请包含",
    "brief": "2-3行纯内容摘要（硬限100字），只写邮件说了什么，不要评论邮件类型或是否需要回复"
  }},
  "action_items": [
    {{
      "text": "行动描述（动词开头，50字以内）",
      "deadline": "YYYY-MM-DD或null",
      "deadline_source": "explicit|inferred|null",
      "priority": "high|medium|low",
      "category": "工作|学习|生活|个人",
      "assignee": "me|sender|other",
      "quote": "原文引用（50字以内）"
    }}
  ],
  "metadata": {{
    "category": ["最多4个分类标签"],
    "sentiment": "positive|negative|neutral",
    "language": "zh|en|ja",
    "confidence": 0.0,
    "is_spam": false,
    "importance_scores": {{
      "sender_score": 0,
      "urgency_score": 0,
      "deadline_score": 0,
      "complexity_score": 0
    }},
    "suggested_reply": "建议回复或null",
    "reply_stances": ["最多4个立场选项"]
  }},
  "pending_facts": [
    {{"fact_key": "career.position", "fact_category": "career", "fact_content": "...", "confidence": 0.0}}
  ]
}}

importance_scores 说明：所有评分均从**收件人（我）的视角**判断——这封邮件对我有多重要/紧急？
四个维度各自独立打分（0-100），不需要计算总分，Python 会完成加权计算。
- sender_score：发件人对我的重要性（如有发件人画像记忆，优先依据记忆中的关系打分）
- urgency_score：邮件对我的紧急程度（发件人自身的紧急事务≠对我紧急）
- deadline_score：需要我响应的截止时间紧迫性（发件人自述的 deadline 不算）
- complexity_score：需要我处理的任务复杂度

**防幻觉规则（严格遵守）**：
- brief 只写邮件**说了什么**（事实内容），禁止写"这是一封XX类邮件"、"属于XX性质"、"无需回复"等元评论——这些信息已在 category/action_items 中体现
- brief 和 action_items 必须有邮件原文对应依据，不得凭空推断
- action_items 仅提取**明确要求收件人（我）执行的行动**。发件人自述的困境、计划或第三方的待办不算我的 action_items
- 如邮件无明确需要我执行的待办，action_items 返回空数组 []
- 如邮件无截止日期，deadline 返回 null，deadline_source 返回 null
- 知识分享、论坛转帖、个人随笔等非事务性邮件：urgency_score 和 deadline_score 应为 0

is_spam 为 true 时，pending_facts 返回空数组 []。"""


def _build_email_user_prompt(email: dict, is_sent: bool = False) -> str:
    """构建邮件的 user prompt。is_sent=True 时省略发件人（就是用户自己）。"""
    body = email.get("body_text") or ""
    body = strip_quoted_content(body)
    body = strip_signature(body)
    body = _truncate_at_boundary(body, 4000)
    if is_sent:
        return f"""请分析以下用户发出的邮件：

主题: {email.get('subject', '')}
收件人: {json.dumps(email.get('to_addresses', []), ensure_ascii=False)}
抄送: {json.dumps(email.get('cc_addresses', []), ensure_ascii=False)}
时间: {email.get('received_at', '')}
正文:
{body}"""
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
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

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
    parser.add_argument("--is-sent", action="store_true", default=False, help="是否为已发送邮件")
    args = parser.parse_args()

    # 更新全局配置
    global CLAWMAIL_API, LLM_API, MODEL, LLM_TOKEN
    CLAWMAIL_API = args.clawmail_api
    LLM_API = args.llm_api
    MODEL = args.model
    LLM_TOKEN = args.llm_token

    try:
        result = analyze_email(args.email_id, args.account_id, is_sent=args.is_sent)
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
