#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 ClawMail 数据库获取邮件
"""

import sqlite3
import json
import os
import sys
from pathlib import Path

# 数据库路径
DB_PATH = os.path.expanduser("~/clawmail_data/clawmail.db")


def get_email_by_id(email_id: str) -> dict:
    """根据ID获取邮件详情"""
    if not os.path.exists(DB_PATH):
        return {"error": f"数据库不存在: {DB_PATH}"}
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM emails WHERE id = ?
        """, (email_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        else:
            return {"error": "邮件不存在"}
            
    except Exception as e:
        return {"error": str(e)}


def get_latest_unread(limit: int = 1) -> list:
    """获取最新未读邮件"""
    if not os.path.exists(DB_PATH):
        return [{"error": f"数据库不存在: {DB_PATH}"}]
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM emails 
            WHERE is_read = 0 
            ORDER BY date DESC 
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
        
    except Exception as e:
        return [{"error": str(e)}]


def get_email_by_subject(subject_keyword: str) -> list:
    """根据主题关键词搜索邮件"""
    if not os.path.exists(DB_PATH):
        return [{"error": f"数据库不存在: {DB_PATH}"}]
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM emails 
            WHERE subject LIKE ?
            ORDER BY date DESC 
            LIMIT 10
        """, (f"%{subject_keyword}%",))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
        
    except Exception as e:
        return [{"error": str(e)}]


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='获取 ClawMail 邮件')
    parser.add_argument('--id', help='邮件ID')
    parser.add_argument('--latest', action='store_true', help='获取最新未读邮件')
    parser.add_argument('--search', help='按主题搜索')
    
    args = parser.parse_args()
    
    if args.id:
        result = get_email_by_id(args.id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.latest:
        results = get_latest_unread()
        print(json.dumps(results, ensure_ascii=False, indent=2))
    elif args.search:
        results = get_email_by_subject(args.search)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("请提供参数: --id, --latest, 或 --search")
        sys.exit(1)
