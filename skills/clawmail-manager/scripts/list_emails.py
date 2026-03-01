#!/usr/bin/env python3
"""
List emails from ClawMail database with various filters.
"""

import argparse
import json
import sqlite3
import os
from datetime import datetime
from pathlib import Path

# Database path - resolves ~ to user home
DB_PATH = Path.home() / "clawmail_data" / "clawmail.db"


def get_db_connection():
    """Get SQLite connection with row factory."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def list_emails(folder=None, account_id=None, status=None, flagged=False, pinned=False, limit=50):
    """List emails with optional filters."""
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
    
    received = email["received_at"] or "N/A"
    
    return f"{pin_icon} {flag_icon} [{read_icon}] {email['id'][:8]}... | {from_addr:30} | {subject:50} | {received}"


def main():
    parser = argparse.ArgumentParser(description="List emails from ClawMail database")
    parser.add_argument("--folder", help="Filter by folder (INBOX, Sent, Drafts, etc.)")
    parser.add_argument("--account", help="Filter by account ID")
    parser.add_argument("--status", choices=["read", "unread", "skimmed"], help="Filter by read status")
    parser.add_argument("--flagged", action="store_true", help="Show only flagged emails")
    parser.add_argument("--pinned", action="store_true", help="Show only pinned emails")
    parser.add_argument("--limit", type=int, default=50, help="Limit results (default: 50)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
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
            print("No emails found matching the criteria.")
            return 0
        
        print(f"Found {len(emails)} email(s):")
        print("-" * 120)
        print(f"{'Pin':3} {'Flag':4} {'Read':4} {'ID':10} {'From':30} {'Subject':50} {'Received'}")
        print("-" * 120)
        
        for email in emails:
            print(format_email_line(email))
    
    return 0


if __name__ == "__main__":
    exit(main())
