#!/usr/bin/env python3
"""
从 ClawMail 数据库列出邮件，支持多种筛选条件。
"""

import argparse
import json
import sqlite3
import os
from datetime import datetime
from pathlib import Path

# 数据库路径 — 将 ~ 解析为用户主目录
DB_PATH = Path.home() / "clawmail_data" / "clawmail.db"


def get_db_connection():
    """获取带行工厂的 SQLite 连接。"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def list_emails(folder=None, account_id=None, status=None, flagged=False, pinned=False, limit=50):
    """列出邮件，支持可选筛选条件。"""
    conn = get_db_connection()

    query = "SELECT * FROM emails WHERE 1=1"
    params = []

    if folder:
        query += " AND folder = ?"
        params.append(folder)

    if account_id:
        query += " AND account_id = ?"
        params.append(account_id)

    if status:
        query += " AND read_status = ?"
        params.append(status)

    if flagged:
        query += " AND flag_status = 'flagged'"

    if pinned:
        query += " AND pinned = 1"

    query += " ORDER BY pinned DESC, received_at DESC LIMIT ?"
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
            "to_addresses": row["to_addresses"],
            "folder": row["folder"],
            "read_status": row["read_status"],
            "flag_status": row["flag_status"],
            "pinned": bool(row["pinned"]),
            "sent_at": row["sent_at"],
            "received_at": row["received_at"],
            "size_bytes": row["size_bytes"],
            "created_at": row["created_at"],
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

    received = email["received_at"] or "N/A"

    return f"{pin_icon} {flag_icon} [{read_icon}] {email['id'][:8]}... | {from_addr:30} | {subject:50} | {received}"


def main():
    parser = argparse.ArgumentParser(description="从 ClawMail 数据库列出邮件")
    parser.add_argument("--folder", help="按文件夹筛选（INBOX、Sent、Drafts 等）")
    parser.add_argument("--account", help="按账户 ID 筛选")
    parser.add_argument("--status", choices=["read", "unread", "skimmed"], help="按阅读状态筛选")
    parser.add_argument("--flagged", action="store_true", help="仅显示已标记邮件")
    parser.add_argument("--pinned", action="store_true", help="仅显示已置顶邮件")
    parser.add_argument("--limit", type=int, default=50, help="限制结果数量（默认: 50）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"错误: 数据库不存在于 {DB_PATH}")
        return 1

    emails = list_emails(
        folder=args.folder,
        account_id=args.account,
        status=args.status,
        flagged=args.flagged,
        pinned=args.pinned,
        limit=args.limit
    )

    if args.json:
        print(json.dumps(emails, indent=2, default=str))
    else:
        if not emails:
            print("未找到符合条件的邮件。")
            return 0

        print(f"找到 {len(emails)} 封邮件:")
        print("-" * 120)
        print(f"{'置顶':3} {'标记':4} {'已读':4} {'ID':10} {'发件人':30} {'主题':50} {'收件时间'}")
        print("-" * 120)

        for email in emails:
            print(format_email_line(email))

    return 0


if __name__ == "__main__":
    exit(main())
