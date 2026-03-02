"""
proactive_detector — 检测可由 OpenClaw 代理执行的邮件行动项

纯 Python 规则引擎，不调用 LLM。
输入 EmailAIMetadata，输出可代理行动列表。
"""

from typing import Dict, List

from clawmail.domain.models.email import EmailAIMetadata

# 硬性排除：含以下关键词的行动项永远不自动处理
_DENY_KEYWORDS = ["付款", "转账", "签约", "辞职", "投诉", "报价", "解雇", "赔偿"]

# send_document 触发词
_SEND_VERBS = ["发送", "提供", "附上", "发一下", "传一下", "分享", "给我", "send", "share", "provide", "attach"]
_DOC_NOUNS = ["文档", "文件", "资料", "报告", "简历", "合同", "PPT", "PDF", "方案", "表格",
              "document", "file", "report", "slide", "presentation"]

# confirm_reply 触发词
_CONFIRM_KEYWORDS = ["确认", "确认参加", "确认收到", "回复确认", "confirm", "acknowledge", "RSVP"]


def detect_proactive_actions(meta: EmailAIMetadata) -> List[Dict]:
    """检测哪些 action_items 可由 OpenClaw 代理执行。

    返回列表，每项 = 原始 action_item dict + 额外字段:
        action_type: "confirm_reply" | "info_reply" | "send_document"
        action_label: 面向用户的中文描述
    空列表表示没有可代理的行动。
    """
    if not meta.action_items:
        return []

    proactive = []
    for idx, item in enumerate(meta.action_items):
        if not isinstance(item, dict):
            continue
        if item.get("assignee") != "me":
            continue
        if item.get("priority") not in ("high", "medium"):
            continue

        text = (item.get("text") or "").lower()

        # 硬性排除
        if any(kw in text for kw in _DENY_KEYWORDS):
            continue

        action_type = _classify(text, meta)
        if action_type:
            label = _make_label(action_type, item)
            proactive.append({
                **item,
                "action_type": action_type,
                "action_label": label,
                "action_idx": idx,
            })

    return proactive


def _classify(text: str, meta: EmailAIMetadata) -> str | None:
    """判断行动项类型，返回 action_type 或 None。"""
    # Type 1: 文件/文档发送请求
    if any(v in text for v in _SEND_VERBS) and any(n in text for n in _DOC_NOUNS):
        return "send_document"

    # Type 2: 简单确认回复
    if any(kw in text for kw in _CONFIRM_KEYWORDS):
        return "confirm_reply"

    # Type 3: 信息回复（需要 pending_reply 分类 + suggested_reply）
    categories = set(meta.categories or [])
    if "pending_reply" in categories and meta.suggested_reply:
        return "info_reply"

    return None


def _make_label(action_type: str, item: dict) -> str:
    """生成面向用户的行动描述。"""
    text = item.get("text") or ""
    if action_type == "send_document":
        return f"查找并发送文件：{text}"
    elif action_type == "confirm_reply":
        return f"自动回复确认：{text}"
    elif action_type == "info_reply":
        return f"查找信息并回复：{text}"
    return text
