"""分析邮件回复/撰写的编辑反馈，提取用户偏好模式。

反馈数据结构（来自 feedback_email_generation.jsonl）:
{
    "email_id": "...",
    "source": "reply_draft" | "generate_email",
    "subject": "...",
    "ai_draft": "AI 生成的草稿全文",
    "user_final": "用户编辑后的最终版本",
    "similarity_ratio": 0.85,
    "stance": "agree",     # reply_draft 专有
    "tone": "formal",
    "keywords": [...],     # reply_draft 专有
    "one_line": "...",     # reply_draft 专有
    "outline": "...",      # generate_email 专有
}
"""

import difflib
import re
from collections import Counter


def analyze_feedback(records: list[dict]) -> list[str]:
    """分析邮件生成反馈记录，返回用户偏好模式列表（自然语言描述）。"""
    if not records:
        return []

    patterns: list[str] = []

    # 收集统计数据
    length_deltas = []       # 正 = 用户加长，负 = 用户缩短
    greeting_adds = Counter()  # 用户添加的称呼
    greeting_removes = Counter()  # 用户删除的称呼
    closing_adds = Counter()   # 用户添加的结尾
    closing_removes = Counter()  # 用户删除的结尾
    phrase_removes = Counter()   # 用户反复删除的短语
    phrase_adds = Counter()      # 用户反复添加的短语
    tone_shifts = []           # 语气偏移方向

    for rec in records:
        ai_draft = rec.get("ai_draft", "")
        user_final = rec.get("user_final", "")
        if not ai_draft or not user_final:
            continue

        # 1. 长度偏好
        ai_len = len(ai_draft)
        user_len = len(user_final)
        if ai_len > 0:
            delta_pct = (user_len - ai_len) / ai_len * 100
            length_deltas.append(delta_pct)

        # 2. 称呼分析（首行）
        ai_first = ai_draft.strip().split("\n")[0] if ai_draft.strip() else ""
        user_first = user_final.strip().split("\n")[0] if user_final.strip() else ""
        if ai_first != user_first:
            _analyze_greeting(ai_first, user_first, greeting_adds, greeting_removes)

        # 3. 结尾分析（末尾两行）
        ai_last = "\n".join(ai_draft.strip().split("\n")[-2:])
        user_last = "\n".join(user_final.strip().split("\n")[-2:])
        if ai_last != user_last:
            _analyze_closing(ai_last, user_last, closing_adds, closing_removes)

        # 4. 逐行 diff 分析：识别被删/被加的短语
        _analyze_line_changes(ai_draft, user_final, phrase_removes, phrase_adds)

        # 5. 语气偏移
        shift = _detect_tone_shift(ai_draft, user_final)
        if shift:
            tone_shifts.append(shift)

    # ── 汇总模式 ──

    # 长度偏好
    if length_deltas:
        avg_delta = sum(length_deltas) / len(length_deltas)
        consistent = all(d < -10 for d in length_deltas) or all(d > 10 for d in length_deltas)
        if consistent and abs(avg_delta) > 15:
            if avg_delta < 0:
                patterns.append(
                    f"用户倾向于缩短回复（平均缩短 {abs(avg_delta):.0f}%），"
                    f"生成更简洁的内容 <!-- evidence: {len(length_deltas)} -->"
                )
            else:
                patterns.append(
                    f"用户倾向于加长回复（平均增加 {avg_delta:.0f}%），"
                    f"生成更详尽的内容 <!-- evidence: {len(length_deltas)} -->"
                )

    # 称呼偏好
    min_evidence = 2
    for greeting, cnt in greeting_adds.most_common(3):
        if cnt >= min_evidence:
            patterns.append(
                f"用户偏好使用称呼「{greeting}」 <!-- evidence: {cnt} -->"
            )
    for greeting, cnt in greeting_removes.most_common(3):
        if cnt >= min_evidence:
            patterns.append(
                f"用户不喜欢称呼「{greeting}」，避免使用 <!-- evidence: {cnt} -->"
            )

    # 结尾偏好
    for closing, cnt in closing_adds.most_common(3):
        if cnt >= min_evidence:
            patterns.append(
                f"用户偏好使用结尾「{closing}」 <!-- evidence: {cnt} -->"
            )
    for closing, cnt in closing_removes.most_common(3):
        if cnt >= min_evidence:
            patterns.append(
                f"用户不喜欢结尾「{closing}」，避免使用 <!-- evidence: {cnt} -->"
            )

    # 被删的套话
    for phrase, cnt in phrase_removes.most_common(5):
        if cnt >= min_evidence:
            patterns.append(
                f"用户反复删除表达「{phrase}」，避免使用此类措辞 <!-- evidence: {cnt} -->"
            )

    # 被加的表达
    for phrase, cnt in phrase_adds.most_common(5):
        if cnt >= min_evidence:
            patterns.append(
                f"用户反复添加表达「{phrase}」，适时采用此类措辞 <!-- evidence: {cnt} -->"
            )

    # 语气偏移
    if tone_shifts:
        shift_counter = Counter(tone_shifts)
        dominant_shift, shift_count = shift_counter.most_common(1)[0]
        if shift_count >= min_evidence:
            patterns.append(
                f"用户偏好{dominant_shift}的语气 <!-- evidence: {shift_count} -->"
            )

    return patterns


# ── 内部分析函数 ──────────────────────────────────────────────────

# 中文常见称呼模式
_GREETING_PATTERNS = [
    r"^(尊敬的.+?[：:])",
    r"^(亲爱的.+?[：:])",
    r"^(.+?(?:老师|总|经理|领导|主任|教授|博士|先生|女士|同学)[，,：:])",
    r"^(Hi\s+.+?[,，])",
    r"^(Dear\s+.+?[,，])",
    r"^(.+?你好[，,！!]?)",
]

# 中文常见结尾模式
_CLOSING_PATTERNS = [
    r"(此致\s*敬礼)",
    r"(顺祝\s*商祺)",
    r"(祝好[！!]?)",
    r"(Best\s+[Rr]egards)",
    r"(谢谢[！!]?)",
    r"(感谢[！!]?)",
    r"(期待.+回复)",
    r"(如有.+请.+联系)",
]

# AI 套话关键词
_AI_CLICHE_PHRASES = [
    "非常感谢您的来信",
    "感谢您的邮件",
    "收到您的邮件",
    "我已经收到",
    "衷心感谢",
    "在此回复",
    "特此回复",
    "希望以上回复对您有所帮助",
    "如有任何疑问",
    "请随时与我联系",
    "不胜感激",
    "深表感谢",
]

# 正式/非正式标记词
_FORMAL_MARKERS = ["您", "贵", "敬请", "特此", "诚挚", "烦请", "恳请"]
_INFORMAL_MARKERS = ["你", "咱", "啊", "呢", "嘛", "哈", "~", "lol", "ok"]


def _analyze_greeting(
    ai_first: str, user_first: str,
    adds: Counter, removes: Counter,
) -> None:
    """分析称呼变化。"""
    ai_greeting = _extract_greeting(ai_first)
    user_greeting = _extract_greeting(user_first)
    if ai_greeting and not user_greeting:
        removes[ai_greeting] += 1
    elif user_greeting and not ai_greeting:
        adds[user_greeting] += 1
    elif ai_greeting and user_greeting and ai_greeting != user_greeting:
        removes[ai_greeting] += 1
        adds[user_greeting] += 1


def _extract_greeting(line: str) -> str:
    """从行中提取称呼部分。"""
    for pat in _GREETING_PATTERNS:
        m = re.match(pat, line.strip())
        if m:
            return m.group(1).strip()
    return ""


def _analyze_closing(
    ai_last: str, user_last: str,
    adds: Counter, removes: Counter,
) -> None:
    """分析结尾变化。"""
    ai_closing = _extract_closing(ai_last)
    user_closing = _extract_closing(user_last)
    if ai_closing and not user_closing:
        removes[ai_closing] += 1
    elif user_closing and not ai_closing:
        adds[user_closing] += 1
    elif ai_closing and user_closing and ai_closing != user_closing:
        removes[ai_closing] += 1
        adds[user_closing] += 1


def _extract_closing(text: str) -> str:
    """从末尾文本中提取结尾用语。"""
    for pat in _CLOSING_PATTERNS:
        m = re.search(pat, text.strip())
        if m:
            return m.group(1).strip()
    return ""


def _analyze_line_changes(
    ai_draft: str, user_final: str,
    removes: Counter, adds: Counter,
) -> None:
    """通过 diff 分析被删除和添加的短语。"""
    ai_lines = ai_draft.splitlines()
    user_lines = user_final.splitlines()
    sm = difflib.SequenceMatcher(None, ai_lines, user_lines)

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "delete" or tag == "replace":
            # AI 的内容被删除/替换
            for line in ai_lines[i1:i2]:
                line = line.strip()
                if not line:
                    continue
                for cliche in _AI_CLICHE_PHRASES:
                    if cliche in line:
                        removes[cliche] += 1
        if tag == "insert" or tag == "replace":
            # 用户新增的内容
            for line in user_lines[j1:j2]:
                line = line.strip()
                if not line or len(line) < 4:
                    continue
                # 只记录短的、可能是固定表达的内容
                if len(line) <= 30:
                    adds[line] += 1


def _detect_tone_shift(ai_draft: str, user_final: str) -> str | None:
    """检测语气偏移方向。返回 '更正式' / '更轻松' / None。"""
    ai_formal = sum(1 for m in _FORMAL_MARKERS if m in ai_draft)
    ai_informal = sum(1 for m in _INFORMAL_MARKERS if m in ai_draft)
    user_formal = sum(1 for m in _FORMAL_MARKERS if m in user_final)
    user_informal = sum(1 for m in _INFORMAL_MARKERS if m in user_final)

    formal_delta = user_formal - ai_formal
    informal_delta = user_informal - ai_informal

    if formal_delta > 0 and informal_delta <= 0:
        return "更正式"
    elif informal_delta > 0 and formal_delta <= 0:
        return "更轻松"
    return None
