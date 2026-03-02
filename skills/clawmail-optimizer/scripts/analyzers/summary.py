"""分析摘要差评反馈，提取摘要偏好模式。

summary 类型的反馈同样主要通过 learner 写入 MemoryBank（summary_preference.*），
但如果有 feedback_summary.jsonl 也可读取。

records 来自 GET /personalization/feedback/summary，每条预期结构:
{
    "email_id": "...",
    "rating": "bad",
    "reasons": ["太笼统", "遗漏关键信息", ...],
    "comment": "可选的用户补充",
    "summary": {
        "one_line": "...",
        "brief": "...",
        "keywords": [...]
    },
    "subject": "...",
}
"""

from collections import Counter


def analyze_feedback(records: list[dict]) -> list[str]:
    """分析摘要评价反馈，返回偏好模式列表。"""
    if not records:
        return []

    patterns: list[str] = []
    reason_counts = Counter()
    comments = []
    total_bad = 0

    for rec in records:
        rating = rec.get("rating", "bad")
        if rating != "bad":
            continue
        total_bad += 1
        reasons = rec.get("reasons", [])
        for r in reasons:
            reason_counts[r] += 1
        comment = rec.get("comment")
        if comment:
            comments.append(comment)

    if total_bad < 2:
        return patterns

    # 按原因频率生成模式
    min_evidence = 2

    for reason, cnt in reason_counts.most_common():
        if cnt < min_evidence:
            continue

        if reason == "太笼统":
            patterns.append(
                f"用户认为摘要太笼统，应包含更具体的数字、人名、日期等关键信息"
                f" <!-- evidence: {cnt} -->"
            )
        elif reason == "遗漏关键信息":
            patterns.append(
                f"用户认为摘要遗漏关键信息，应提取邮件中最核心的行动要求或决策点"
                f" <!-- evidence: {cnt} -->"
            )
        elif reason == "重点偏移":
            patterns.append(
                f"用户认为摘要重点偏移，应优先概括邮件的主要意图而非次要细节"
                f" <!-- evidence: {cnt} -->"
            )
        elif reason == "太长":
            patterns.append(
                f"用户认为摘要太长，one_line 应控制在更短的范围"
                f" <!-- evidence: {cnt} -->"
            )
        elif reason == "太短":
            patterns.append(
                f"用户认为摘要太短，应包含更多上下文信息"
                f" <!-- evidence: {cnt} -->"
            )
        elif reason == "关键词不准确":
            patterns.append(
                f"用户认为关键词提取不准确，应更贴合邮件实际主题"
                f" <!-- evidence: {cnt} -->"
            )
        else:
            patterns.append(
                f"用户反馈摘要问题「{reason}」"
                f" <!-- evidence: {cnt} -->"
            )

    # 如果有多条用户评论，汇总提取共性
    if len(comments) >= 2:
        patterns.append(
            f"用户多次补充评论（共 {len(comments)} 条），"
            f"以下为原始评论供参考：{'；'.join(comments[:5])}"
            f" <!-- evidence: {len(comments)} -->"
        )

    return patterns
