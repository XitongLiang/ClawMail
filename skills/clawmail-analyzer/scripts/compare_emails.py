#!/usr/bin/env python3
"""
compare_emails.py - 邮件对比分析脚本

输入: 多个邮件ID
输出: 对比分析报告

用法:
    python compare_emails.py --email-ids id1,id2,id3 --account-id user_123
"""

import argparse
import json
import sys
from datetime import datetime

def compare_emails(email_ids: list, account_id: str = None) -> dict:
    """
    对比多封邮件的优先级
    
    TODO: 实际应从数据库读取邮件并调用 ai_processor
    """
    # 示例数据
    emails = [
        {
            "id": email_ids[0] if len(email_ids) > 0 else "email_1",
            "subject": "Q4报告提交",
            "importance_score": 85,
            "breakdown": {
                "sender_contrib": 28.5,
                "urgency_contrib": 20.0,
                "deadline_contrib": 23.75,
                "complexity_contrib": 12.0
            }
        },
        {
            "id": email_ids[1] if len(email_ids) > 1 else "email_2",
            "subject": "周会通知",
            "importance_score": 60,
            "breakdown": {
                "sender_contrib": 15.0,
                "urgency_contrib": 15.0,
                "deadline_contrib": 15.0,
                "complexity_contrib": 15.0
            }
        }
    ]
    
    # 排序
    emails.sort(key=lambda x: x["importance_score"], reverse=True)
    
    return {
        "status": "success",
        "compared_at": datetime.now().isoformat(),
        "email_count": len(email_ids),
        "ranking": [
            {
                "rank": i + 1,
                "email_id": e["id"],
                "subject": e["subject"],
                "importance_score": e["importance_score"],
                "breakdown": e["breakdown"]
            }
            for i, e in enumerate(emails)
        ],
        "recommendation": {
            "order": [e["id"] for e in emails],
            "reason": "基于重要性评分的四维度综合评估",
            "urgent_count": sum(1 for e in emails if e["importance_score"] >= 80)
        }
    }

def main():
    parser = argparse.ArgumentParser(description="邮件对比分析")
    parser.add_argument("--email-ids", required=True, 
                       help="邮件ID列表，逗号分隔")
    parser.add_argument("--account-id", help="用户账户ID")
    parser.add_argument("--output", "-o", help="输出文件路径")
    
    args = parser.parse_args()
    
    email_ids = [id.strip() for id in args.email_ids.split(",")]
    
    if len(email_ids) < 2:
        result = {
            "status": "error",
            "error_code": "INVALID_INPUT",
            "message": "对比分析需要至少2封邮件"
        }
    else:
        result = compare_emails(email_ids, args.account_id)
    
    output = json.dumps(result, ensure_ascii=False, indent=2)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
    else:
        print(output)

if __name__ == "__main__":
    main()
