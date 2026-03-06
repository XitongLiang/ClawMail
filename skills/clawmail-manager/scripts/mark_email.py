#!/usr/bin/env python3
"""
将邮件标记为已读/未读、标记/取消标记或置顶/取消置顶。
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


def mark_email(email_id, read=None, flag=None, pin=None):
    """更新邮件状态。"""
    conn = get_db_connection()
    cursor = conn.cursor()

    updates = []
    params = []

    if read is not None:
        updates.append("read_status = ?")
        params.append("read" if read else "unread")

    if flag is not None:
        updates.append("flag_status = ?")
        params.append("flagged" if flag else "none")

    if pin is not None:
        updates.append("pinned = ?")
        params.append(1 if pin else 0)

    if not updates:
        print("未指定任何更改。请使用 --read、--flag 或 --pin。")
        return False

    updates.append("updated_at = ?")
    params.append(datetime.utcnow().isoformat())
    params.append(email_id)

    query = f"UPDATE emails SET {', '.join(updates)} WHERE id = ?"
    cursor.execute(query, params)

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
        "SELECT subject, read_status, flag_status, pinned FROM emails WHERE id = ?",
        (email_id,)
    ).fetchone()
    conn.close()
    return row


def main():
    parser = argparse.ArgumentParser(description="为邮件设置各种状态标记")
    parser.add_argument("email_id", help="要更新的邮件 ID")
    parser.add_argument("--read", action="store_true", help="标记为已读")
    parser.add_argument("--unread", action="store_true", help="标记为未读")
    parser.add_argument("--flag", action="store_true", help="标记邮件")
    parser.add_argument("--unflag", action="store_true", help="取消标记邮件")
    parser.add_argument("--pin", action="store_true", help="置顶邮件")
    parser.add_argument("--unpin", action="store_true", help="取消置顶邮件")

    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"错误: 数据库不存在于 {DB_PATH}")
        return 1

    # 确定操作
    read = None
    if args.read:
        read = True
    elif args.unread:
        read = False

    flag = None
    if args.flag:
        flag = True
    elif args.unflag:
        flag = False

    pin = None
    if args.pin:
        pin = True
    elif args.unpin:
        pin = False

    # 更新前获取当前信息
    before = get_email_info(args.email_id)
    if not before:
        print(f"未找到邮件 {args.email_id}。")
        return 1

    if mark_email(args.email_id, read=read, flag=flag, pin=pin):
        after = get_email_info(args.email_id)
        subject = after["subject"] or "(无主题)"
        print(f"已更新: {subject}")
        print(f"  已读: {before['read_status']} → {after['read_status']}")
        print(f"  标记: {before['flag_status']} → {after['flag_status']}")
        print(f"  置顶: {bool(before['pinned'])} → {bool(after['pinned'])}")

    return 0


if __name__ == "__main__":
    exit(main())
