#!/usr/bin/env python3
"""
feedback_report.py - AI摘要反馈报告生成脚本

用法:
    python feedback_report.py --account-id user_123
    python feedback_report.py --report-type summary|detailed
"""

import argparse
import json
from datetime import datetime, timedelta

def generate_feedback_report(account_id: str, report_type: str = "summary") -> dict:
    """
    生成AI摘要反馈报告
    
    TODO: 实际应从数据库读取反馈数据
    """
    
    # 示例报告数据
    report = {
        "status": "success",
        "generated_at": datetime.now().isoformat(),
        "account_id": account_id,
        "report_period": {
            "start": (datetime.now() - timedelta(days=30)).isoformat(),
            "end": datetime.now().isoformat()
        },
        "summary": {
            "total_analyzed": 156,
            "total_feedback": 42,
            "feedback_rate": 0.269,
            "average_rating": 4.2,
            "satisfaction_rate": 0.88
        },
        "rating_distribution": {
            "5_star": 25,
            "4_star": 12,
            "3_star": 3,
            "2_star": 1,
            "1_star": 1
        },
        "common_issues": [
            {
                "issue": "关键词提取不准确",
                "count": 5,
                "percentage": 0.12
            },
            {
                "issue": "截止日期识别错误",
                "count": 3,
                "percentage": 0.07
            }
        ],
        "learned_preferences": [
            "用户更偏好简短摘要",
            "对张总的邮件自动标记为高优先级",
            "GitHub通知可批量处理"
        ]
    }
    
    if report_type == "detailed":
        report["detailed_stats"] = {
            "accuracy_by_field": {
                "keywords": 0.85,
                "one_line": 0.90,
                "brief": 0.88,
                "action_items": 0.82,
                "importance_score": 0.75
            },
            "improvement_trends": [
                {"week": "W1", "rating": 4.0},
                {"week": "W2", "rating": 4.1},
                {"week": "W3", "rating": 4.2},
                {"week": "W4", "rating": 4.3}
            ]
        }
    
    return report

def format_report_for_display(report: dict) -> str:
    """格式化报告为人类可读文本"""
    
    s = report["summary"]
    
    lines = [
        "📊 ClawMail AI摘要反馈报告",
        "",
        f"统计周期: {report['report_period']['start'][:10]} 至 {report['report_period']['end'][:10]}",
        "",
        "📈 总体统计:",
        f"  - 分析邮件总数: {s['total_analyzed']} 封",
        f"  - 收到反馈数: {s['total_feedback']} 条",
        f"  - 反馈率: {s['feedback_rate']:.1%}",
        f"  - 平均评分: {s['average_rating']}/5.0",
        f"  - 满意度: {s['satisfaction_rate']:.1%}",
        "",
        "⭐ 评分分布:",
        f"  ⭐⭐⭐⭐⭐: {report['rating_distribution']['5_star']} 条",
        f"  ⭐⭐⭐⭐: {report['rating_distribution']['4_star']} 条",
        f"  ⭐⭐⭐: {report['rating_distribution']['3_star']} 条",
        f"  ⭐⭐: {report['rating_distribution']['2_star']} 条",
        f"  ⭐: {report['rating_distribution']['1_star']} 条",
        "",
        "🔧 常见问题:",
    ]
    
    for issue in report["common_issues"]:
        lines.append(f"  - {issue['issue']}: {issue['count']}次 ({issue['percentage']:.0%})")
    
    lines.extend([
        "",
        "🧠 已学习的偏好:",
    ])
    
    for pref in report["learned_preferences"]:
        lines.append(f"  - {pref}")
    
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="生成AI摘要反馈报告")
    parser.add_argument("--account-id", help="用户账户ID")
    parser.add_argument("--report-type", default="summary",
                       choices=["summary", "detailed"],
                       help="报告类型")
    parser.add_argument("--output", "-o", help="输出JSON文件路径")
    parser.add_argument("--format", default="json",
                       choices=["json", "text"],
                       help="输出格式")
    
    args = parser.parse_args()
    
    report = generate_feedback_report(
        args.account_id or "anonymous",
        args.report_type
    )
    
    if args.format == "text":
        output = format_report_for_display(report)
    else:
        output = json.dumps(report, ensure_ascii=False, indent=2)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
    else:
        print(output)

if __name__ == "__main__":
    main()
