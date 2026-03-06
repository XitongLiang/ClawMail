#!/usr/bin/env python3
"""
从 ClawMail 数据库获取邮件统计信息。
"""

import argparse
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

# 数据库路径
DB_PATH = Path.home() / "clawmail_data" / "clawmail.db"


def get_db_connection():
    """获取带行工厂的 SQLite 连接。"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_statistics(account_id=None):
    """获取综合邮件统计信息。"""
    conn = get_db_connection()

    stats = {}

    # 基础 WHERE 子句
    where_clause = "WHERE account_id = ?" if account_id else ""
    params = [account_id] if account_id else []

    # 邮件总数
    query = f"SELECT COUNT(*) as count FROM emails {where_clause}"
    stats["total_emails"] = conn.execute(query, params).fetchone()["count"]

    # 按文件夹统计
    query = f"""
        SELECT folder, COUNT(*) as count FROM emails
        {where_clause}
        GROUP BY folder
        ORDER BY count DESC
    """
    stats["by_folder"] = {row["folder"]: row["count"] for row in conn.execute(query, params)}

    # 阅读状态统计
    query = f"""
        SELECT read_status, COUNT(*) as count FROM emails
        {where_clause}
        GROUP BY read_status
    """
    stats["by_read_status"] = {row["read_status"]: row["count"] for row in conn.execute(query, params)}

    # 标记状态统计
    query = f"""
        SELECT flag_status, COUNT(*) as count FROM emails
        {where_clause}
        GROUP BY flag_status
    """
    stats["by_flag_status"] = {row["flag_status"]: row["count"] for row in conn.execute(query, params)}

    # 置顶数量
    query = f"""
        SELECT COUNT(*) as count FROM emails
        {where_clause}
        {"AND" if where_clause else "WHERE"} pinned = 1
    """
    stats["pinned_count"] = conn.execute(query, params if where_clause else []).fetchone()["count"]

    # 未读数量
    query = f"""
        SELECT COUNT(*) as count FROM emails
        {where_clause}
        {"AND" if where_clause else "WHERE"} read_status = 'unread'
    """
    stats["unread_count"] = conn.execute(query, params if where_clause else []).fetchone()["count"]

    # 已标记数量
    query = f"""
        SELECT COUNT(*) as count FROM emails
        {where_clause}
        {"AND" if where_clause else "WHERE"} flag_status = 'flagged'
    """
    stats["flagged_count"] = conn.execute(query, params if where_clause else []).fetchone()["count"]

    # 今日收到的邮件
    today = datetime.now().strftime("%Y-%m-%d")
    query = f"""
        SELECT COUNT(*) as count FROM emails
        {where_clause}
        {"AND" if where_clause else "WHERE"} date(received_at) = date('now')
    """
    stats["received_today"] = conn.execute(query, params if where_clause else []).fetchone()["count"]

    # 本周收到的邮件
    query = f"""
        SELECT COUNT(*) as count FROM emails
        {where_clause}
        {"AND" if where_clause else "WHERE"} date(received_at) >= date('now', '-7 days')
    """
    stats["received_this_week"] = conn.execute(query, params if where_clause else []).fetchone()["count"]

    # 存储总大小
    query = f"""
        SELECT COALESCE(SUM(size_bytes), 0) as total_size FROM emails
        {where_clause}
    """
    stats["total_size_bytes"] = conn.execute(query, params).fetchone()["total_size"]

    # AI 处理统计
    query = """
        SELECT ai_status, COUNT(*) as count FROM email_ai_metadata
        GROUP BY ai_status
    """
    stats["ai_processing"] = {row["ai_status"]: row["count"] for row in conn.execute(query)}

    # 账户列表（无账户筛选时显示）
    if not account_id:
        query = """
            SELECT a.id, a.email_address, COUNT(e.id) as email_count
            FROM accounts a
            LEFT JOIN emails e ON a.id = e.account_id
            WHERE a.is_enabled = 1
            GROUP BY a.id
        """
        stats["accounts"] = [
            {
                "id": row["id"],
                "email": row["email_address"],
                "email_count": row["email_count"]
            }
            for row in conn.execute(query)
        ]

    conn.close()
    return stats


def format_size(size_bytes):
    """将字节数格式化为人类可读的大小。"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"


def main():
    parser = argparse.ArgumentParser(description="获取邮件统计信息")
    parser.add_argument("--account", help="获取指定账户 ID 的统计信息")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"错误: 数据库不存在于 {DB_PATH}")
        return 1

    stats = get_statistics(account_id=args.account)

    if args.json:
        print(json.dumps(stats, indent=2, default=str))
    else:
        print("=" * 50)
        print("ClawMail 邮件统计")
        print("=" * 50)

        print(f"\n📧 邮件总数: {stats['total_emails']:,}")
        print(f"📥 今日收到: {stats['received_today']:,}")
        print(f"📥 本周收到: {stats['received_this_week']:,}")
        print(f"📌 已置顶: {stats['pinned_count']:,}")
        print(f"🚩 已标记: {stats['flagged_count']:,}")
        print(f"🔴 未读: {stats['unread_count']:,}")
        print(f"💾 存储占用: {format_size(stats['total_size_bytes'])}")

        print("\n📁 按文件夹:")
        for folder, count in stats['by_folder'].items():
            print(f"  {folder}: {count:,}")

        print("\n👁️  按阅读状态:")
        for status, count in stats['by_read_status'].items():
            print(f"  {status}: {count:,}")

        print("\n🤖 AI 处理状态:")
        for status, count in stats.get('ai_processing', {}).items():
            print(f"  {status}: {count:,}")

        if 'accounts' in stats:
            print("\n👤 账户:")
            for account in stats['accounts']:
                print(f"  {account['email']}: {account['email_count']:,} 封邮件")

        print("=" * 50)

    return 0


if __name__ == "__main__":
    exit(main())
