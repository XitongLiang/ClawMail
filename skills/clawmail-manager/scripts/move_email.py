#!/usr/bin/env python3
"""
将邮件移动到指定文件夹。
"""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

# 数据库路径
DB_PATH = Path.home() / "clawmail_data" / "clawmail.db"


def get_db_connection():
    """获取 SQLite 连接。"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn


def move_email(email_id, folder):
    """将邮件移动到指定文件夹。"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE emails SET folder = ?, updated_at = ? WHERE id = ?",
        (folder, datetime.utcnow().isoformat(), email_id)
    )

    if cursor.rowcount == 0:
        print(f"未找到邮件 {email_id}。")
        conn.close()
        return False

    conn.commit()
    conn.close()
    return True


def get_email_info(email_id):
    """获取当前邮件信息。"""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT subject, folder FROM emails WHERE id = ?",
        (email_id,)
    ).fetchone()
    conn.close()
    return row


def main():
    parser = argparse.ArgumentParser(description="将邮件移动到指定文件夹")
    parser.add_argument("email_id", help="要移动的邮件 ID")
    parser.add_argument("--folder", required=True, help="目标文件夹（INBOX、Archive、Trash 等）")

    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"错误: 数据库不存在于 {DB_PATH}")
        return 1

    before = get_email_info(args.email_id)
    if not before:
        print(f"未找到邮件 {args.email_id}。")
        return 1

    if move_email(args.email_id, args.folder):
        subject = before["subject"] or "(无主题)"
        print(f"已移动: {subject}")
        print(f"  文件夹: {before['folder']} → {args.folder}")

    return 0


if __name__ == "__main__":
    exit(main())
