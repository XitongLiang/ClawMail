#!/usr/bin/env python3
"""
AI摘要反馈报告 - 生成ClawMail AI处理的综合报告
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime

# 数据库路径
DB_PATH = Path.home() / "clawmail_data" / "clawmail.db"


def get_db_connection():
    """获取带行工厂的 SQLite 连接。"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_ai_summary_report():
    """获取AI摘要处理的综合报告."""
    conn = get_db_connection()

    report = {
        "generated_at": datetime.now().isoformat(),
        "database_path": str(DB_PATH)
    }

    # 1. 基本统计
    cursor = conn.execute("SELECT COUNT(*) as count FROM email_ai_metadata")
    report["total_processed"] = cursor.fetchone()["count"]

    cursor = conn.execute("SELECT COUNT(*) as count FROM emails")
    report["total_emails"] = cursor.fetchone()["count"]
    report["processing_coverage"] = f"{(report['total_processed'] / report['total_emails'] * 100):.1f}%" if report['total_emails'] > 0 else "0%"

    # 2. 按AI状态统计
    cursor = conn.execute("""
        SELECT ai_status, COUNT(*) as count
        FROM email_ai_metadata
        GROUP BY ai_status
    """)
    report["status_breakdown"] = {row["ai_status"]: row["count"] for row in cursor}

    # 3. 处理阶段统计
    cursor = conn.execute("""
        SELECT processing_stage, COUNT(*) as count
        FROM email_ai_metadata
        WHERE processing_stage IS NOT NULL
        GROUP BY processing_stage
    """)
    report["stage_breakdown"] = {row["processing_stage"]: row["count"] for row in cursor}

    # 4. 分类统计
    cursor = conn.execute("SELECT categories FROM email_ai_metadata WHERE categories IS NOT NULL")
    category_counts = {}
    for row in cursor:
        try:
            categories = json.loads(row["categories"])
            if isinstance(categories, list):
                for cat in categories:
                    category_counts[cat] = category_counts.get(cat, 0) + 1
        except:
            pass
    report["categories"] = dict(sorted(category_counts.items(), key=lambda x: x[1], reverse=True))

    # 5. 情感分析统计
    cursor = conn.execute("""
        SELECT sentiment, COUNT(*) as count
        FROM email_ai_metadata
        WHERE sentiment IS NOT NULL
        GROUP BY sentiment
    """)
    report["sentiment_analysis"] = {row["sentiment"]: row["count"] for row in cursor}

    # 6. 紧急程度统计
    cursor = conn.execute("""
        SELECT urgency, COUNT(*) as count
        FROM email_ai_metadata
        WHERE urgency IS NOT NULL
        GROUP BY urgency
    """)
    report["urgency_distribution"] = {row["urgency"]: row["count"] for row in cursor}

    # 7. 垃圾邮件检测
    cursor = conn.execute("""
        SELECT is_spam, COUNT(*) as count
        FROM email_ai_metadata
        WHERE is_spam IS NOT NULL
        GROUP BY is_spam
    """)
    spam_stats = {}
    for row in cursor:
        key = "垃圾邮件" if row["is_spam"] else "正常邮件"
        spam_stats[key] = row["count"]
    report["spam_detection"] = spam_stats

    # 8. 处理错误统计
    cursor = conn.execute("""
        SELECT processing_error, COUNT(*) as count
        FROM email_ai_metadata
        WHERE processing_error IS NOT NULL
        GROUP BY processing_error
    """)
    report["processing_errors"] = {row["processing_error"]: row["count"] for row in cursor}

    # 9. 最近处理的邮件（最近10封）
    cursor = conn.execute("""
        SELECT e.id, e.subject, e.from_address, e.folder, e.received_at,
               m.ai_status, m.summary_one_line, m.processed_at
        FROM emails e
        JOIN email_ai_metadata m ON e.id = m.email_id
        ORDER BY m.processed_at DESC
        LIMIT 10
    """)
    report["recent_processed"] = [
        {
            "id": row["id"],
            "subject": row["subject"],
            "sender": row["from_address"],
            "folder": row["folder"],
            "received_at": row["received_at"],
            "ai_status": row["ai_status"],
            "summary": row["summary_one_line"],
            "processed_at": row["processed_at"]
        }
        for row in cursor
    ]

    # 10. 有建议回复的邮件数量
    cursor = conn.execute("""
        SELECT COUNT(*) as count
        FROM email_ai_metadata
        WHERE suggested_reply IS NOT NULL AND suggested_reply != ''
    """)
    report["suggested_replies_count"] = cursor.fetchone()["count"]

    # 11. 有待办事项的邮件
    cursor = conn.execute("""
        SELECT COUNT(*) as count
        FROM email_ai_metadata
        WHERE action_items IS NOT NULL AND action_items != '[]'
    """)
    report["action_items_count"] = cursor.fetchone()["count"]

    conn.close()
    return report


def format_report(report):
    """格式化报告为可读文本."""
    lines = []
    lines.append("=" * 70)
    lines.append("ClawMail AI摘要反馈报告")
    lines.append("=" * 70)
    lines.append(f"生成时间: {report['generated_at']}")
    lines.append(f"数据库路径: {report['database_path']}")
    lines.append("")

    # 处理覆盖情况
    lines.append("-" * 70)
    lines.append("[处理覆盖情况]")
    lines.append("-" * 70)
    lines.append(f"  总邮件数: {report['total_emails']}")
    lines.append(f"  AI已处理: {report['total_processed']}")
    lines.append(f"  覆盖率: {report['processing_coverage']}")
    lines.append("")

    # 状态分布
    lines.append("-" * 70)
    lines.append("[AI处理状态分布]")
    lines.append("-" * 70)
    for status, count in report['status_breakdown'].items():
        lines.append(f"  {status}: {count}")
    lines.append("")

    # 处理阶段
    if report['stage_breakdown']:
        lines.append("-" * 70)
        lines.append("[处理阶段分布]")
        lines.append("-" * 70)
        for stage, count in report['stage_breakdown'].items():
            lines.append(f"  {stage}: {count}")
        lines.append("")

    # 分类统计
    if report['categories']:
        lines.append("-" * 70)
        lines.append("[邮件分类统计]")
        lines.append("-" * 70)
        for category, count in list(report['categories'].items())[:15]:  # 最多显示15个
            lines.append(f"  {category}: {count}")
        lines.append("")

    # 情感分析
    if report['sentiment_analysis']:
        lines.append("-" * 70)
        lines.append("[情感分析统计]")
        lines.append("-" * 70)
        for sentiment, count in report['sentiment_analysis'].items():
            lines.append(f"  {sentiment}: {count}")
        lines.append("")

    # 紧急程度
    if report['urgency_distribution']:
        lines.append("-" * 70)
        lines.append("[紧急程度分布]")
        lines.append("-" * 70)
        for urgency, count in report['urgency_distribution'].items():
            lines.append(f"  {urgency}: {count}")
        lines.append("")

    # 垃圾邮件检测
    if report['spam_detection']:
        lines.append("-" * 70)
        lines.append("[垃圾邮件检测]")
        lines.append("-" * 70)
        for spam_type, count in report['spam_detection'].items():
            lines.append(f"  {spam_type}: {count}")
        lines.append("")

    # 处理错误
    if report['processing_errors']:
        lines.append("-" * 70)
        lines.append("[处理错误统计]")
        lines.append("-" * 70)
        for error, count in report['processing_errors'].items():
            lines.append(f"  {error}: {count}")
        lines.append("")

    # AI功能统计
    lines.append("-" * 70)
    lines.append("[AI功能使用情况]")
    lines.append("-" * 70)
    lines.append(f"  建议回复数量: {report['suggested_replies_count']}")
    lines.append(f"  待办事项数量: {report['action_items_count']}")
    lines.append("")

    # 最近处理的邮件
    lines.append("-" * 70)
    lines.append("[最近处理的10封邮件]")
    lines.append("-" * 70)
    for email in report['recent_processed']:
        lines.append(f"\n  邮件ID: {email['id']}")
        lines.append(f"  主题: {email['subject'] or '(无主题)'}")
        lines.append(f"  发件人: {email['sender']}")
        lines.append(f"  文件夹: {email['folder']}")
        lines.append(f"  状态: {email['ai_status']}")
        if email['summary']:
            lines.append(f"  摘要: {email['summary']}")
        lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="生成ClawMail AI摘要反馈报告")
    parser.add_argument("--json", action="store_true", help="以JSON格式输出")
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"错误: 数据库不存在于 {DB_PATH}")
        return 1

    report = get_ai_summary_report()

    if args.json:
        print(json.dumps(report, indent=2, default=str, ensure_ascii=False))
    else:
        print(format_report(report))

    return 0


if __name__ == "__main__":
    exit(main())
