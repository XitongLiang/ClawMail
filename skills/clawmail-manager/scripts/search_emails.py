#!/usr/bin/env python3
"""
使用 FTS5 或 LIKE 查询按关键词搜索邮件主题和正文。
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


def search_emails(keywords, folder=None, account_id=None, limit=50):
    """按关键词搜索邮件。"""
    conn = get_db_connection()

    # 优先尝试 FTS5，失败则回退到 LIKE
    try:
        # FTS5 全文搜索
        fts_query = keywords.replace("'", "''")
        query = """
            SELECT e.* FROM emails e
            JOIN emails_fts fts ON e.rowid = fts.rowid
            WHERE emails_fts MATCH ?
        """
        params = [fts_query]

        if folder:
            query += " AND e.folder = ?"
            params.append(folder)

        if account_id:
            query += " AND e.account_id = ?"
            params.append(account_id)

        query += " ORDER BY e.received_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

    except sqlite3.OperationalError:
        # 回退到 LIKE 搜索
        search_pattern = f"%{keywords}%"
        query = """
            SELECT * FROM emails
            WHERE (subject LIKE ? OR body_text LIKE ? OR from_address LIKE ?)
        """
        params = [search_pattern, search_pattern, search_pattern]

        if folder:
            query += " AND folder = ?"
            params.append(folder)

        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)

        query += " ORDER BY received_at DESC LIMIT ?"
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
            "body_preview": (row["body_text"] or "")[:200] if row["body_text"] else None,
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
    parser = argparse.ArgumentParser(description="按关键词搜索邮件")
    parser.add_argument("keywords", help="搜索关键词")
    parser.add_argument("--folder", help="按文件夹筛选")
    parser.add_argument("--account", help="按账户 ID 筛选")
    parser.add_argument("--limit", type=int, default=50, help="限制结果数量（默认: 50）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"错误: 数据库不存在于 {DB_PATH}")
        return 1

    emails = search_emails(
        keywords=args.keywords,
        folder=args.folder,
        account_id=args.account,
        limit=args.limit
    )

    if args.json:
        print(json.dumps(emails, indent=2, default=str))
    else:
        if not emails:
            print(f"未找到匹配 '{args.keywords}' 的邮件。")
            return 0

        print(f"找到 {len(emails)} 封匹配 '{args.keywords}' 的邮件:")
        print("-" * 110)
        print(f"{'置顶':3} {'标记':4} {'已读':4} {'ID':10} {'发件人':30} {'主题':50}")
        print("-" * 110)

        for email in emails:
            print(format_email_line(email))
            if email["body_preview"]:
                preview = email["body_preview"].replace("\n", " ")
                if len(preview) > 80:
                    preview = preview[:77] + "..."
                print(f"      预览: {preview}")

    return 0


if __name__ == "__main__":
    exit(main())
