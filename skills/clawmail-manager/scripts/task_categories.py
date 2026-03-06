#!/usr/bin/env python3
"""
列出 ClawMail 数据库中所有 AI 分类。
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


def get_categories(account_id=None):
    """获取所有 AI 分类。"""
    conn = get_db_connection()

    query = """
        SELECT m.categories FROM email_ai_metadata m
        JOIN emails e ON e.id = m.email_id
        WHERE m.categories IS NOT NULL
          AND m.categories != '[]'
          AND m.ai_status = 'processed'
    """
    params = []

    if account_id:
        query += " AND e.account_id = ?"
        params.append(account_id)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    category_set = set()
    for (cats_json,) in rows:
        try:
            cats = json.loads(cats_json)
            if isinstance(cats, list):
                category_set.update(cats)
        except (json.JSONDecodeError, TypeError):
            pass

    return sorted(category_set)


def main():
    parser = argparse.ArgumentParser(description="列出所有 AI 分类")
    parser.add_argument("--account", help="按账户 ID 筛选")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"错误: 数据库不存在于 {DB_PATH}")
        return 1

    categories = get_categories(account_id=args.account)

    if args.json:
        print(json.dumps(categories, indent=2))
    else:
        if not categories:
            print("未找到 AI 分类。")
            return 0

        print(f"找到 {len(categories)} 个 AI 分类:")
        print("-" * 50)

        for cat in categories:
            print(f"  • {cat}")

    return 0


if __name__ == "__main__":
    exit(main())
