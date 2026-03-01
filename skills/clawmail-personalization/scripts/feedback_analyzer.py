#!/usr/bin/env python3
"""
反馈数据分析器

支持所有 9 种反馈类型的分析。
"""

from typing import List, Dict, Any
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class FeedbackAnalysis:
    """分析结果"""
    summary: str
    insights: List[str]
    patterns: Dict[str, Any]
    statistics: Dict[str, Any]


class FeedbackAnalyzer:
    """反馈数据分析器"""
    
    def __init__(self, feedback_type: str):
        self.feedback_type = feedback_type
    
    def analyze(self, feedback_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        分析反馈数据。
        
        根据 feedback_type 选择对应的分析方法。
        """
        if not feedback_data:
            return {
                "summary": "没有反馈数据",
                "insights": [],
                "patterns": {},
                "statistics": {}
            }
        
        # 根据类型选择分析方法（8种反馈类型）
        analyzers = {
            "importance_score": self._analyze_importance_score,
            "category": self._analyze_category,
            "is_spam": self._analyze_is_spam,
            "action_category": self._analyze_action_category,
            "reply_stances": self._analyze_reply_stances,
            "summary": self._analyze_summary,
            "email_generation": self._analyze_email_generation,  # 合并 reply_draft + generate_email
            "polish_email": self._analyze_polish_email,
        }
        
        analyzer = analyzers.get(self.feedback_type, self._analyze_generic)
        return analyzer(feedback_data)
    
    def _analyze_importance_score(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析重要性评分反馈"""
        total = len(data)
        increases = sum(1 for d in data if d.get("new_score", 0) > d.get("original_score", 0))
        decreases = sum(1 for d in data if d.get("new_score", 0) < d.get("original_score", 0))
        
        changes = [d.get("new_score", 0) - d.get("original_score", 0) for d in data]
        avg_change = sum(changes) / len(changes) if changes else 0
        
        # 关键词分析
        keyword_stats = defaultdict(lambda: {"count": 0, "total_change": 0})
        for d in data:
            change = d.get("new_score", 0) - d.get("original_score", 0)
            for kw in d.get("keywords", []):
                keyword_stats[kw]["count"] += 1
                keyword_stats[kw]["total_change"] += change
        
        preferred = []
        avoided = []
        for kw, stats in keyword_stats.items():
            if stats["count"] >= 2:
                avg = stats["total_change"] / stats["count"]
                if avg > 10:
                    preferred.append({"keyword": kw, "avg_change": round(avg, 1), "count": stats["count"]})
                elif avg < -10:
                    avoided.append({"keyword": kw, "avg_change": round(avg, 1), "count": stats["count"]})
        
        preferred.sort(key=lambda x: x["avg_change"], reverse=True)
        avoided.sort(key=lambda x: x["avg_change"])
        
        insights = []
        if avg_change > 5:
            insights.append(f"用户整体倾向于提高评分（平均提升 {avg_change:.1f} 分）")
        elif avg_change < -5:
            insights.append(f"用户整体倾向于降低评分（平均降低 {abs(avg_change):.1f} 分）")
        else:
            insights.append("用户对重要性的判断与 AI 基本一致")
        
        if preferred:
            insights.append(f"倾向于提高评分的关键词: {', '.join([p['keyword'] for p in preferred[:3]])}")
        if avoided:
            insights.append(f"倾向于降低评分的关键词: {', '.join([a['keyword'] for a in avoided[:3]])}")
        
        return {
            "summary": f"分析了 {total} 条重要性评分反馈，平均变化 {avg_change:+.1f} 分",
            "insights": insights,
            "patterns": {
                "preferred_keywords": preferred[:10],
                "avoided_keywords": avoided[:10],
                "avg_change": round(avg_change, 2),
                "increases": increases,
                "decreases": decreases
            },
            "statistics": {
                "total": total,
                "increases": increases,
                "decreases": decreases,
                "avg_change": round(avg_change, 2)
            }
        }
    
    def _analyze_category(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析分类标签反馈"""
        total = len(data)
        
        # 统计分类修改模式
        category_changes = defaultdict(lambda: {"added": 0, "removed": 0})
        for d in data:
            for cat in d.get("added_categories", []):
                category_changes[cat]["added"] += 1
            for cat in d.get("removed_categories", []):
                category_changes[cat]["removed"] += 1
        
        insights = [f"分析了 {total} 条分类标签反馈"]
        
        # 找出用户经常添加的分类
        frequently_added = sorted(
            [(cat, stats["added"]) for cat, stats in category_changes.items()],
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        if frequently_added:
            insights.append(f"用户经常手动添加的分类: {', '.join([c[0] for c in frequently_added])}")
        
        return {
            "summary": f"分析了 {total} 条分类标签反馈",
            "insights": insights,
            "patterns": dict(category_changes),
            "statistics": {"total": total}
        }
    
    def _analyze_is_spam(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析垃圾邮件检测反馈"""
        total = len(data)
        missed_spam = sum(1 for d in data if d.get("error_type") == "missed_spam")
        false_positive = sum(1 for d in data if d.get("error_type") == "false_positive")
        
        # 发件人分析
        sender_stats = defaultdict(lambda: {"missed": 0, "false_positive": 0})
        for d in data:
            sender = d.get("sender", "unknown")
            if d.get("error_type") == "missed_spam":
                sender_stats[sender]["missed"] += 1
            else:
                sender_stats[sender]["false_positive"] += 1
        
        insights = [
            f"分析了 {total} 条垃圾邮件检测反馈",
            f"漏判（AI 认为是正常邮件）: {missed_spam} 次",
            f"误判（AI 认为是垃圾邮件）: {false_positive} 次"
        ]
        
        return {
            "summary": f"分析了 {total} 条垃圾邮件反馈，漏判 {missed_spam} 次，误判 {false_positive} 次",
            "insights": insights,
            "patterns": {
                "missed_spam": missed_spam,
                "false_positive": false_positive,
                "sender_stats": dict(sender_stats)
            },
            "statistics": {"total": total, "missed_spam": missed_spam, "false_positive": false_positive}
        }
    
    def _analyze_action_category(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析行动项分类反馈"""
        total = len(data)
        
        # 统计分类修改
        category_changes = defaultdict(int)
        for d in data:
            orig = d.get("original_category", "")
            new = d.get("new_category", "")
            if orig and new:
                category_changes[f"{orig} → {new}"] += 1
        
        insights = [f"分析了 {total} 条行动项分类反馈"]
        
        return {
            "summary": f"分析了 {total} 条行动项分类反馈",
            "insights": insights,
            "patterns": dict(category_changes),
            "statistics": {"total": total}
        }
    
    def _analyze_reply_stances(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析回复立场反馈"""
        total = len(data)
        used_ai = sum(1 for d in data if d.get("used_ai_draft", False))
        not_used = total - used_ai
        
        # 统计用户选择的立场
        stance_stats = defaultdict(int)
        for d in data:
            if d.get("used_ai_draft") and d.get("selected_stance"):
                stance_stats[d["selected_stance"]] += 1
        
        insights = [
            f"分析了 {total} 条回复立场反馈",
            f"使用 AI 辅助: {used_ai} 次",
            f"未使用 AI 辅助: {not_used} 次"
        ]
        
        if stance_stats:
            popular_stances = sorted(stance_stats.items(), key=lambda x: x[1], reverse=True)[:3]
            insights.append(f"用户偏好的立场: {', '.join([s[0] for s in popular_stances])}")
        
        return {
            "summary": f"分析了 {total} 条回复立场反馈，使用 AI 率 {used_ai/total*100:.1f}%",
            "insights": insights,
            "patterns": {
                "used_ai_rate": used_ai / total if total else 0,
                "stance_preferences": dict(stance_stats)
            },
            "statistics": {"total": total, "used_ai": used_ai, "not_used": not_used}
        }
    
    def _analyze_email_generation(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析邮件生成反馈（合并 reply_draft + generate_email）"""
        total = len(data)
        
        # 按来源分类统计
        reply_draft_count = sum(1 for d in data if d.get("source") == "reply_draft")
        generate_email_count = sum(1 for d in data if d.get("source") == "generate_email")
        
        # 计算相似度（阈值 0.95）
        similarities = [d.get("similarity_ratio", 0) for d in data if d.get("similarity_ratio") is not None]
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0
        
        high_sim = sum(1 for s in similarities if s >= 0.95)  # 阈值改为 0.95
        low_sim = sum(1 for s in similarities if s < 0.95)
        
        # 统计风格偏好
        tone_stats = defaultdict(int)
        stance_stats = defaultdict(int)
        for d in data:
            if d.get("tone"):
                tone_stats[d["tone"]] += 1
            if d.get("stance"):
                stance_stats[d["stance"]] += 1
        
        insights = [
            f"分析了 {total} 条邮件生成反馈",
            f"  - 回复草稿场景: {reply_draft_count} 次",
            f"  - 写新邮件场景: {generate_email_count} 次",
            f"平均相似度（AI生成 vs 用户最终）: {avg_similarity:.2f}",
            f"高相似度(≥0.95): {high_sim} 次, 低相似度(<0.95): {low_sim} 次"
        ]
        
        if tone_stats:
            popular_tones = sorted(tone_stats.items(), key=lambda x: x[1], reverse=True)[:3]
            insights.append(f"用户偏好的风格: {', '.join([t[0] for t in popular_tones])}")
        
        if stance_stats:
            popular_stances = sorted(stance_stats.items(), key=lambda x: x[1], reverse=True)[:3]
            insights.append(f"用户偏好的回复立场: {', '.join([s[0] for s in popular_stances])}")
        
        return {
            "summary": f"分析了 {total} 条邮件生成反馈（回复草稿 {reply_draft_count} 次，写新邮件 {generate_email_count} 次），平均相似度 {avg_similarity:.2f}",
            "insights": insights,
            "patterns": {
                "avg_similarity": round(avg_similarity, 2),
                "high_similarity": high_sim,
                "low_similarity": low_sim,
                "reply_draft_count": reply_draft_count,
                "generate_email_count": generate_email_count,
                "tone_preferences": dict(tone_stats),
                "stance_preferences": dict(stance_stats)
            },
            "statistics": {
                "total": total,
                "reply_draft_count": reply_draft_count,
                "generate_email_count": generate_email_count,
                "avg_similarity": round(avg_similarity, 2)
            }
        }
    
    def _analyze_summary(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析摘要质量反馈"""
        total = len(data)
        good = sum(1 for d in data if d.get("rating") == "good")
        bad = total - good
        
        # 统计不满意原因
        reason_stats = defaultdict(int)
        for d in data:
            if d.get("rating") == "bad":
                for reason in d.get("reasons", []):
                    reason_stats[reason] += 1
        
        insights = [
            f"分析了 {total} 条摘要质量反馈",
            f"满意: {good} 次 ({good/total*100:.1f}%)",
            f"不满意: {bad} 次 ({bad/total*100:.1f}%)"
        ]
        
        if reason_stats:
            top_reasons = sorted(reason_stats.items(), key=lambda x: x[1], reverse=True)[:3]
            insights.append(f"主要问题: {', '.join([r[0] for r in top_reasons])}")
        
        return {
            "summary": f"分析了 {total} 条摘要反馈，满意率 {good/total*100:.1f}%",
            "insights": insights,
            "patterns": {
                "good_rate": good / total if total else 0,
                "top_issues": dict(sorted(reason_stats.items(), key=lambda x: x[1], reverse=True)[:5])
            },
            "statistics": {"total": total, "good": good, "bad": bad}
        }
    
    def _analyze_polish_email(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析邮件润色反馈"""
        total = len(data)
        
        # 计算相似度（阈值 0.95）
        similarities = [d.get("similarity_ratio", 0) for d in data if d.get("similarity_ratio") is not None]
        avg_similarity = sum(similarities) / len(similarities) if similarities else 0
        
        high_sim = sum(1 for s in similarities if s >= 0.95)  # 阈值改为 0.95
        low_sim = sum(1 for s in similarities if s < 0.95)
        
        # 统计润色风格
        tone_stats = defaultdict(int)
        for d in data:
            if d.get("tone"):
                tone_stats[d["tone"]] += 1
        
        insights = [
            f"分析了 {total} 条润色反馈",
            f"平均相似度: {avg_similarity:.2f}",
            f"高相似度(≥0.95): {high_sim} 次, 低相似度(<0.95): {low_sim} 次"
        ]
        
        if tone_stats:
            popular_tones = sorted(tone_stats.items(), key=lambda x: x[1], reverse=True)[:3]
            insights.append(f"用户偏好的润色风格: {', '.join([t[0] for t in popular_tones])}")
        
        return {
            "summary": f"分析了 {total} 条润色反馈，平均相似度 {avg_similarity:.2f}",
            "insights": insights,
            "patterns": {
                "avg_similarity": round(avg_similarity, 2),
                "high_similarity": high_sim,
                "low_similarity": low_sim,
                "tone_preferences": dict(tone_stats)
            },
            "statistics": {"total": total, "avg_similarity": round(avg_similarity, 2)}
        }
    
    def _analyze_generic(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """通用分析方法"""
        total = len(data)
        return {
            "summary": f"分析了 {total} 条反馈",
            "insights": [f"共 {total} 条反馈记录"],
            "patterns": {},
            "statistics": {"total": total}
        }
