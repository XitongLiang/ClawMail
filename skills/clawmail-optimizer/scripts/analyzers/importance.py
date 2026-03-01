"""分析重要性评分修正反馈，提取评分偏好模式。

importance_score 类型没有 JSONL 文件，反馈通过 executor 已写入 MemoryBank。
此 analyzer 从 MemoryBank 读取 sender_importance.* / urgency_signal.* 记忆，
综合分析用户的评分修正趋势。

注意：records 参数来自 GET /personalization/feedback/importance_score，
      可能为空（因为反馈走 executor 而非 JSONL）。
      但 optimizer 调用时也会传入 memories，此 analyzer 需要在 analyze_feedback
      签名中兼容（目前只用 records）。
"""


def analyze_feedback(records: list[dict]) -> list[str]:
    """分析重要性评分反馈。

    records 可能来自两个来源:
    1. JSONL feedback_importance_score.jsonl（如果未来添加）
    2. 传入的 MemoryBank entries（executor 已处理的评分修正记忆）

    当前实现：从 records 中分析评分修正模式。
    每条 record 预期结构:
    {
        "email_id": "...",
        "original_score": 65,
        "user_score": 80,
        "subject": "...",
        "sender": "...",
        "category": ["work"],
    }
    """
    if not records:
        return []

    patterns: list[str] = []

    # 统计修正方向
    up_count = 0
    down_count = 0
    up_deltas = []
    down_deltas = []
    category_ups = {}    # category → 调高次数
    category_downs = {}  # category → 调低次数
    sender_ups = {}      # sender → 调高次数

    for rec in records:
        original = rec.get("original_score")
        user = rec.get("user_score")
        if original is None or user is None:
            continue
        delta = user - original
        if delta == 0:
            continue

        category_list = rec.get("category", [])
        sender = rec.get("sender", "")

        if delta > 0:
            up_count += 1
            up_deltas.append(delta)
            for cat in category_list:
                category_ups[cat] = category_ups.get(cat, 0) + 1
            if sender:
                sender_ups[sender] = sender_ups.get(sender, 0) + 1
        else:
            down_count += 1
            down_deltas.append(abs(delta))
            for cat in category_list:
                category_downs[cat] = category_downs.get(cat, 0) + 1

    total = up_count + down_count
    if total < 2:
        return patterns

    # 整体偏向
    if up_count >= total * 0.7:
        avg_up = sum(up_deltas) / len(up_deltas)
        patterns.append(
            f"用户倾向于调高重要性评分（平均调高 {avg_up:.0f} 分），"
            f"当前评分标准可能偏保守"
            f" <!-- evidence: {up_count} -->"
        )
    elif down_count >= total * 0.7:
        avg_down = sum(down_deltas) / len(down_deltas)
        patterns.append(
            f"用户倾向于调低重要性评分（平均调低 {avg_down:.0f} 分），"
            f"当前评分标准可能偏高"
            f" <!-- evidence: {down_count} -->"
        )

    # 按类别分析
    min_evidence = 2
    for cat, cnt in sorted(category_ups.items(), key=lambda x: -x[1]):
        if cnt >= min_evidence:
            patterns.append(
                f"用户认为「{cat}」类邮件的重要性被低估，"
                f"应适当提高该类别的权重"
                f" <!-- evidence: {cnt} -->"
            )
    for cat, cnt in sorted(category_downs.items(), key=lambda x: -x[1]):
        if cnt >= min_evidence:
            patterns.append(
                f"用户认为「{cat}」类邮件的重要性被高估，"
                f"应适当降低该类别的权重"
                f" <!-- evidence: {cnt} -->"
            )

    return patterns
