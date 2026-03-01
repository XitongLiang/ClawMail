"""分析邮件润色的编辑反馈，提取用户偏好模式。

反馈数据结构（来自 feedback_polish_email.jsonl）:
{
    "email_id": "...",
    "subject": "...",
    "tone": "formal",
    "original_body": "用户原始邮件正文",
    "polished_body": "AI 润色后的版本",
    "user_final": "用户编辑后的最终版本",
    "similarity_ratio": 0.90,
}
"""

import difflib
import re
from collections import Counter


def analyze_feedback(records: list[dict]) -> list[str]:
    """分析润色反馈记录，返回用户偏好模式列表。"""
    if not records:
        return []

    patterns: list[str] = []

    polish_level_deltas = []  # AI 润色 vs 用户期望的润色程度
    restore_counts = 0        # 用户恢复原文片段的次数
    total = 0
    over_polish = 0           # AI 过度润色（用户改回接近原文）
    under_polish = 0          # AI 润色不够（用户进一步修改远离原文）
    tone_mismatches = Counter()  # 语气不匹配计数

    for rec in records:
        original = rec.get("original_body", "")
        polished = rec.get("polished_body", "")
        user_final = rec.get("user_final", "")
        tone = rec.get("tone", "")
        if not polished or not user_final:
            continue
        total += 1

        # 计算用户最终版与原文、AI版的相似度
        sim_to_original = difflib.SequenceMatcher(None, original, user_final).ratio()
        sim_to_polished = difflib.SequenceMatcher(None, polished, user_final).ratio()

        if sim_to_original > sim_to_polished:
            # 用户更接近原文 → AI 过度润色
            over_polish += 1
        elif sim_to_polished < 0.85:
            # 用户对 AI 版改动较大 → 可能润色不够或方向不对
            under_polish += 1

        # 检测恢复原文片段
        if original:
            _check_restore(original, polished, user_final)
            orig_lines = set(original.strip().splitlines())
            polish_lines = set(polished.strip().splitlines())
            user_lines = set(user_final.strip().splitlines())
            # 原文有、AI删了、但用户加回来的
            restored = (orig_lines - polish_lines) & user_lines
            if restored:
                restore_counts += 1

        # 语气偏好：记录用户选择的语气 vs 实际接受程度
        if tone and sim_to_polished < 0.80:
            tone_mismatches[tone] += 1

    # ── 汇总模式 ──

    if total >= 2:
        if over_polish >= total * 0.6:
            patterns.append(
                f"用户倾向于保留原文风格，AI 润色程度应降低（"
                f"减少大幅改写，保留用户原有表达）"
                f" <!-- evidence: {over_polish} -->"
            )
        if under_polish >= total * 0.6:
            patterns.append(
                f"用户对 AI 润色结果修改较多，润色力度可能不够"
                f"（或方向不符合预期）"
                f" <!-- evidence: {under_polish} -->"
            )
        if restore_counts >= 2:
            patterns.append(
                f"用户多次恢复被 AI 改掉的原文片段，"
                f"润色时应更保守，保留用户原有的关键表达"
                f" <!-- evidence: {restore_counts} -->"
            )

    for tone, cnt in tone_mismatches.most_common(3):
        if cnt >= 2:
            patterns.append(
                f"用户选择「{tone}」语气时对 AI 结果修改较多，"
                f"该语气的润色效果需改进"
                f" <!-- evidence: {cnt} -->"
            )

    return patterns


def _check_restore(original: str, polished: str, user_final: str) -> int:
    """检测用户从原文恢复了多少内容（行级别）。"""
    orig_lines = set(original.strip().splitlines())
    polish_lines = set(polished.strip().splitlines())
    user_lines = set(user_final.strip().splitlines())
    restored = (orig_lines - polish_lines) & user_lines
    return len(restored)
