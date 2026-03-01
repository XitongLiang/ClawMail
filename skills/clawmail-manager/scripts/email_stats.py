#!/usr/bin/env python3
"""
Get email statistics from the ClawMail database.
"""

import argparse
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

# Database path
DB_PATH = Path.home() / "clawmail_data" / "clawmail.db"


def get_db_connection():
    """Get SQLite connection with row factory."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_statistics(account_id=None):
    """Get comprehensive email statistics."""
    conn = get_db_connection()
    
    stats = {}
    
    # Base WHERE clause
    where_clause = "WHERE account_id = ?" if account_id else ""
    params = [account_id] if account_id else []
    
    # Total emails
    query = f"SELECT COUNT(*) as count FROM emails {where_clause}"
    stats["total_emails"] = conn.execute(query, params).fetchone()["count"]
    
    # Emails by folder
    query = f"""
        SELECT folder, COUNT(*) as count FROM emails
        {where_clause}
        GROUP BY folder
        ORDER BY count DESC
    """
    stats["by_folder"] = {row["folder"]: row["count"] for row in conn.execute(query, params)}
    
    # Read status breakdown
    query = f"""
        SELECT read_status, COUNT(*) as count FROM emails
        {where_clause}
        GROUP BY read_status
    """
    stats["by_read_status"] = {row["read_status"]: row["count"] for row in conn.execute(query, params)}
    
    # Flag status breakdown
    query = f"""
        SELECT flag_status, COUNT(*) as count FROM emails
        {where_clause}
        GROUP BY flag_status
    """
    stats["by_flag_status"] = {row["flag_status"]: row["count"] for row in conn.execute(query, params)}
    
    # Pinned count
    query = f"""
        SELECT COUNT(*) as count FROM emails
        {where_clause}
        {"AND" if where_clause else "WHERE"} pinned = 1
    """
    stats["pinned_count"] = conn.execute(query, params if where_clause else []).fetchone()["count"]
    
    # Unread count
    query = f"""
        SELECT COUNT(*) as count FROM emails
        {where_clause}
        {"AND" if where_clause else "WHERE"} read_status = 'unread'
    """
    stats["unread_count"] = conn.execute(query, params if where_clause else []).fetchone()["count"]
    
    # Flagged count
    query = f"""
        SELECT COUNT(*) as count FROM emails
        {where_clause}
        {"AND" if where_clause else "WHERE"} flag_status = 'flagged'
    """
    stats["flagged_count"] = conn.execute(query, params if where_clause else []).fetchone()["count"]
    
    # Emails received today
    today = datetime.now().strftime("%Y-%m-%d")
    query = f"""
        SELECT COUNT(*) as count FROM emails
        {where_clause}
        {"AND" if where_clause else "WHERE"} date(received_at) = date('now')
    """
    stats["received_today"] = conn.execute(query, params if where_clause else []).fetchone()["count"]
    
    # Emails received this week
    query = f"""
        SELECT COUNT(*) as count FROM emails
        {where_clause}
        {"AND" if where_clause else "WHERE"} date(received_at) >= date('now', '-7 days')
    """
    stats["received_this_week"] = conn.execute(query, params if where_clause else []).fetchone()["count"]
    
    # Total storage size
    query = f"""
        SELECT COALESCE(SUM(size_bytes), 0) as total_size FROM emails
        {where_clause}
    """
    stats["total_size_bytes"] = conn.execute(query, params).fetchone()["total_size"]
    
    # AI processing stats
    query = """
        SELECT ai_status, COUNT(*) as count FROM email_ai_metadata
        GROUP BY ai_status
    """
    stats["ai_processing"] = {row["ai_status"]: row["count"] for row in conn.execute(query)}
    
    # Account list (if no account filter)
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
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"


def main():
    parser = argparse.ArgumentParser(description="Get email statistics")
    parser.add_argument("--account", help="Get stats for specific account ID")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        return 1
    
    stats = get_statistics(account_id=args.account)
    
    if args.json:
        print(json.dumps(stats, indent=2, default=str))
    else:
        print("=" * 50)
        print("ClawMail Email Statistics")
        print("=" * 50)
        
        print(f"\n📧 Total Emails: {stats['total_emails']:,}")
        print(f"📥 Received Today: {stats['received_today']:,}")
        print(f"📥 Received This Week: {stats['received_this_week']:,}")
        print(f"📌 Pinned: {stats['pinned_count']:,}")
        print(f"🚩 Flagged: {stats['flagged_count']:,}")
        print(f"🔴 Unread: {stats['unread_count']:,}")
        print(f"💾 Storage: {format_size(stats['total_size_bytes'])}")
        
        print("\n📁 By Folder:")
        for folder, count in stats['by_folder'].items():
            print(f"  {folder}: {count:,}")
        
        print("\n👁️  By Read Status:")
        for status, count in stats['by_read_status'].items():
            print(f"  {status}: {count:,}")
        
        print("\n🤖 AI Processing Status:")
        for status, count in stats.get('ai_processing', {}).items():
            print(f"  {status}: {count:,}")
        
        if 'accounts' in stats:
            print("\n👤 Accounts:")
            for account in stats['accounts']:
                print(f"  {account['email']}: {account['email_count']:,} emails")
        
        print("=" * 50)
    
    return 0


if __name__ == "__main__":
    exit(main())
