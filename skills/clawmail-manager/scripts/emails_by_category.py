#!/usr/bin/env python3
"""
从 ClawMail 数据库按 AI 分类获取邮件。
"""

import argparse
import json
import sqlite3
from pathlib import Path

# 数据库路径
DB_PATH = Path.home() / "clawmail_data" / "clawmail.db"


def get_db_connection():
    """获取带行工厂的 SQLite 连接。"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_emails_by_category(category, account_id=None, limit=100):
    """按 AI 分类获取邮件。"""
    conn = get_db_connection()

    # JSON 数组 LIKE 匹配
    pattern = f'%"{category}"%'

    query = """
        SELECT e.* FROM emails e
        JOIN email_ai_metadata m ON e.id = m.email_id
        WHERE m.categories LIKE ?
    """
    params = [pattern]

    if account_id:
        query += " AND e.account_id = ?"
        params.append(account_id)

    query += " ORDER BY e.pinned DESC, e.received_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    emails = []
    for row in rows:
        email = {
            "id": row["id"],
            "account_id": row["account_id"],
            "subject": row["subject"],
            "from_address": row["from_address"],
            "folder": row["folder"],
            "read_status": row["read_status"],
            "flag_status": row["flag_status"],
            "pinned": bool(row["pinned"]),
            "received_at": row["received_at"],
        }
        emails.append(email)

    return emails


def format_email_line(email):
    """将邮件格式化为单行摘要。"""
    pin_icon = "P" if email["pinned"] else " "
    flag_icon = "F" if email["flag_status"] == "flagged" else " "
    read_icon = "R" if email["read_status"] == "read" else "U"

    subject = email["subject"] or "(无主题)"
    if len(subject) > 50:
        subject = subject[:47] + "..."

    from_addr = email["from_address"] or "未知"
    if len(from_addr) > 30:
        from_addr = from_addr[:27] + "..."

    return f"{pin_icon} {flag_icon} [{read_icon}] {email['id'][:8]}... | {from_addr:30} | {subject:50}"


def main():
    parser = argparse.ArgumentParser(description="按 AI 分类获取邮件")
    parser.add_argument("category", help="用于筛选的 AI 分类")
    parser.add_argument("--account", help="按账户 ID 筛选")
    parser.add_argument("--limit", type=int, default=100, help="限制结果数量（默认: 100）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"错误: 数据库不存在于 {DB_PATH}")
        return 1

    emails = get_emails_by_category(
        category=args.category,
        account_id=args.account,
        limit=args.limit
    )

    if args.json:
        print(json.dumps(emails, indent=2, default=str))
    else:
        if not emails:
            print(f"在分类 '{args.category}' 中未找到邮件。")
            return 0

        print(f"在分类 '{args.category}' 中找到 {len(emails)} 封邮件:")
        print("-" * 110)
        print(f"{'置顶':3} {'标记':4} {'已读':4} {'ID':10} {'发件人':30} {'主题':50}")
        print("-" * 110)

        for email in emails:
            print(format_email_line(email))

    return 0


if __name__ == "__main__":
    exit(main())
