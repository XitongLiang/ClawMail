#!/usr/bin/env python3
"""
Get emails by AI category from ClawMail database.
"""

import argparse
import json
import sqlite3
from pathlib import Path

# Database path
DB_PATH = Path.home() / "clawmail_data" / "clawmail.db"


def get_db_connection():
    """Get SQLite connection with row factory."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_emails_by_category(category, account_id=None, limit=100):
    """Get emails by AI category."""
    conn = get_db_connection()
    
    # JSON array LIKE matching
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
    """Format email as a single line summary."""
    pin_icon = "P" if email["pinned"] else " "
    flag_icon = "F" if email["flag_status"] == "flagged" else " "
    read_icon = "R" if email["read_status"] == "read" else "U"
    
    subject = email["subject"] or "(no subject)"
    if len(subject) > 50:
        subject = subject[:47] + "..."
    
    from_addr = email["from_address"] or "unknown"
    if len(from_addr) > 30:
        from_addr = from_addr[:27] + "..."
    
    return f"{pin_icon} {flag_icon} [{read_icon}] {email['id'][:8]}... | {from_addr:30} | {subject:50}"


def main():
    parser = argparse.ArgumentParser(description="Get emails by AI category")
    parser.add_argument("category", help="AI category to filter by")
    parser.add_argument("--account", help="Filter by account ID")
    parser.add_argument("--limit", type=int, default=100, help="Limit results (default: 100)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
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
            print(f"No emails found in category '{args.category}'.")
            return 0
        
        print(f"Found {len(emails)} email(s) in category '{args.category}':")
        print("-" * 110)
        print(f"{'Pin':3} {'Flag':4} {'Read':4} {'ID':10} {'From':30} {'Subject':50}")
        print("-" * 110)
        
        for email in emails:
            print(format_email_line(email))
    
    return 0


if __name__ == "__main__":
    exit(main())
