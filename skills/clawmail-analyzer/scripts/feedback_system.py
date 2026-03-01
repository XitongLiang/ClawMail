#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
摘要反馈收集与学习系统
记录用户对摘要的满意度，用于调整生成策略
"""

import json
import os
import sys
from datetime import datetime
from typing import Dict, List

# Fix Windows encoding
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 反馈存储路径
FEEDBACK_DIR = os.path.expanduser("~/.openclaw/workspace/memory/feedback")
FEEDBACK_FILE = os.path.join(FEEDBACK_DIR, "summary_feedback.jsonl")

# 反馈统计文件
STATS_FILE = os.path.join(FEEDBACK_DIR, "summary_stats.json")


def ensure_feedback_dir():
    """确保反馈目录存在"""
    if not os.path.exists(FEEDBACK_DIR):
        os.makedirs(FEEDBACK_DIR)


def collect_feedback(
    email_subject: str,
    generated_summary: Dict,
    user_rating: int,  # 1-5 分
    user_comment: str = "",
    improvement_areas: List[str] = None
) -> Dict:
    """
    收集用户对摘要的反馈
    
    Args:
        email_subject: 邮件主题（用于关联）
        generated_summary: 生成的摘要内容
        user_rating: 用户评分 1-5（5最满意）
        user_comment: 用户文字反馈
        improvement_areas: 需要改进的方面列表
    """
    ensure_feedback_dir()
    
    feedback_entry = {
        "timestamp": datetime.now().isoformat(),
        "email_subject": email_subject[:50],  # 只记录前50字用于关联
        "generated_summary": generated_summary,
        "user_rating": user_rating,
        "user_comment": user_comment,
        "improvement_areas": improvement_areas or [],
        "summary_hash": hash(str(generated_summary)) % 10000  # 简单哈希用于去重
    }
    
    # 追加写入 JSONL 文件
    with open(FEEDBACK_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(feedback_entry, ensure_ascii=False) + '\n')
    
    # 更新统计
    update_stats(feedback_entry)
    
    return {
        "success": True,
        "message": f"反馈已记录，当前平均评分: {get_average_rating():.2f}/5.0"
    }


def update_stats(feedback_entry: Dict):
    """更新反馈统计"""
    stats = load_stats()
    
    rating = feedback_entry["user_rating"]
    
    # 更新计数
    stats["total_feedbacks"] = stats.get("total_feedbacks", 0) + 1
    stats["rating_distribution"] = stats.get("rating_distribution", {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0})
    stats["rating_distribution"][str(rating)] = stats["rating_distribution"].get(str(rating), 0) + 1
    
    # 计算平均分
    total = stats["total_feedbacks"]
    current_avg = stats.get("average_rating", 0)
    stats["average_rating"] = (current_avg * (total - 1) + rating) / total if total > 0 else rating
    
    # 记录改进领域
    for area in feedback_entry.get("improvement_areas", []):
        stats["improvement_areas"] = stats.get("improvement_areas", {})
        stats["improvement_areas"][area] = stats["improvement_areas"].get(area, 0) + 1
    
    # 保存统计
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def load_stats() -> Dict:
    """加载反馈统计"""
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "total_feedbacks": 0,
        "average_rating": 0,
        "rating_distribution": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
        "improvement_areas": {},
        "learned_preferences": {}
    }


def get_average_rating() -> float:
    """获取平均评分"""
    stats = load_stats()
    return stats.get("average_rating", 0)


def get_user_preferences() -> Dict:
    """
    根据反馈历史，推断用户偏好
    返回用于调整摘要生成的参数
    """
    stats = load_stats()
    
    preferences = {
        "detail_level": "normal",  # brief/normal/detailed
        "focus_areas": [],  # 用户更关注的内容类型
        "avoid_patterns": [],  # 用户不喜欢的模式
        "style_adjustments": {}
    }
    
    # 分析改进领域，推断偏好
    improvement_areas = stats.get("improvement_areas", {})
    
    if improvement_areas.get("too_long", 0) > 2:
        preferences["detail_level"] = "brief"
        preferences["style_adjustments"]["max_brief_lines"] = 3
    
    if improvement_areas.get("too_short", 0) > 2:
        preferences["detail_level"] = "detailed"
        preferences["style_adjustments"]["min_key_points"] = 5
    
    if improvement_areas.get("missing_deadline", 0) > 2:
        preferences["focus_areas"].append("deadline")
    
    if improvement_areas.get("missing_action_items", 0) > 2:
        preferences["focus_areas"].append("action_items")
    
    if improvement_areas.get("wrong_tone", 0) > 2:
        preferences["avoid_patterns"].append("too_formal")
    
    return preferences


def generate_feedback_prompt() -> str:
    """生成反馈收集提示"""
    return """
━━━━━━━━━━━━━━━━━━━━━
📊 摘要质量反馈

请为刚才的摘要质量评分：
⭐⭐⭐⭐⭐ (5) - 非常满意，完全准确
⭐⭐⭐⭐   (4) - 满意，基本准确
⭐⭐⭐     (3) - 一般，有改进空间
⭐⭐       (2) - 不满意，有较大问题
⭐         (1) - 完全不符合要求

回复格式：
- 满意：回复 "满意" 或 "5"
- 不满意：回复 "不满意" 并说明原因

常见改进方向：
- 太长 / 太短
- 遗漏关键信息（截止时间/行动项）
- 语气不对
- 关键点提取不准
━━━━━━━━━━━━━━━━━━━━━
"""


def analyze_feedback_trends() -> Dict:
    """分析反馈趋势，生成改进建议"""
    stats = load_stats()
    total = stats.get("total_feedbacks", 0)
    
    distribution = stats.get("rating_distribution", {})
    
    # 计算满意度
    satisfied = sum(distribution.get(str(i), 0) for i in [4, 5])
    satisfaction_rate = satisfied / total * 100
    
    # 分析主要问题
    improvement_areas = stats.get("improvement_areas", {})
    top_issues = sorted(improvement_areas.items(), key=lambda x: x[1], reverse=True)[:3]
    
    return {
        "total_feedbacks": total,
        "satisfaction_rate": f"{satisfaction_rate:.1f}%",
        "average_rating": f"{stats.get('average_rating', 0):.2f}/5.0",
        "top_issues": [f"{issue} ({count}次)" for issue, count in top_issues],
        "recommendations": generate_recommendations(top_issues)
    }


def generate_recommendations(top_issues: List) -> List[str]:
    """根据问题生成改进建议"""
    recommendations = []
    
    issue_names = [issue for issue, _ in top_issues]
    
    if "too_long" in issue_names:
        recommendations.append("用户偏好更简洁的摘要，建议减少摘要行数和字数")
    
    if "too_short" in issue_names:
        recommendations.append("用户希望更详细的摘要，建议增加关键信息提取")
    
    if "missing_deadline" in issue_names:
        recommendations.append("用户关注截止时间，建议加强日期提取算法")
    
    if "missing_action_items" in issue_names:
        recommendations.append("用户需要明确的待办事项，建议提高action_item识别率")
    
    if "wrong_tone" in issue_names:
        recommendations.append("摘要语气需要调整，建议根据邮件类型适配语气")
    
    if not recommendations:
        recommendations.append("继续收集反馈以优化摘要质量")
    
    return recommendations


def export_feedback_report() -> str:
    """导出反馈报告"""
    trends = analyze_feedback_trends()
    prefs = get_user_preferences()
    
    report = f"""
📈 摘要反馈报告
━━━━━━━━━━━━━━━━━━━━━

【统计概览】
总反馈数: {trends.get('total_feedbacks', 0)}
平均评分: {trends.get('average_rating', 'N/A')}
满意度: {trends.get('satisfaction_rate', 'N/A')}

【主要问题】
{chr(10).join(['• ' + issue for issue in trends.get('top_issues', [])])}

【改进建议】
{chr(10).join(['• ' + rec for rec in trends.get('recommendations', [])])}

【用户偏好推断】
详细程度: {prefs.get('detail_level', 'normal')}
关注重点: {', '.join(prefs.get('focus_areas', ['无']))}

━━━━━━━━━━━━━━━━━━━━━
"""
    return report


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='摘要反馈系统')
    parser.add_argument('--collect', action='store_true', help='收集反馈（交互模式）')
    parser.add_argument('--rating', type=int, help='评分 1-5')
    parser.add_argument('--comment', help='文字反馈')
    parser.add_argument('--stats', action='store_true', help='查看统计')
    parser.add_argument('--report', action='store_true', help='生成报告')
    
    args = parser.parse_args()
    
    if args.stats:
        stats = load_stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    
    elif args.report:
        print(export_feedback_report())
    
    elif args.rating:
        result = collect_feedback(
            email_subject="测试邮件",
            generated_summary={"test": "summary"},
            user_rating=args.rating,
            user_comment=args.comment or ""
        )
        print(json.dumps(result, ensure_ascii=False))
    
    else:
        print(generate_feedback_prompt())
