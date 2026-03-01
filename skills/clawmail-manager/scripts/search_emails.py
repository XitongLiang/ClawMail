#!/usr/bin/env python3
"""
Search emails by keywords in subject and body using FTS5 or LIKE queries.
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


def search_emails(keywords, folder=None, account_id=None, limit=50):
    """Search emails by keywords."""
    conn = get_db_connection()
    
    # Try FTS5 first, fall back to LIKE if FTS5 fails
    try:
        # FTS5 search
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
        # Fallback to LIKE search
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
    parser = argparse.ArgumentParser(description="Search emails by keywords")
    parser.add_argument("keywords", help="Search keywords")
    parser.add_argument("--folder", help="Filter by folder")
    parser.add_argument("--account", help="Filter by account ID")
    parser.add_argument("--limit", type=int, default=50, help="Limit results (default: 50)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
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
            print(f"No emails found matching '{args.keywords}'.")
            return 0
        
        print(f"Found {len(emails)} email(s) matching '{args.keywords}':")
        print("-" * 110)
        print(f"{'Pin':3} {'Flag':4} {'Read':4} {'ID':10} {'From':30} {'Subject':50}")
        print("-" * 110)
        
        for email in emails:
            print(format_email_line(email))
            if email["body_preview"]:
                preview = email["body_preview"].replace("\n", " ")
                if len(preview) > 80:
                    preview = preview[:77] + "..."
                print(f"      Preview: {preview}")
    
    return 0


if __name__ == "__main__":
    exit(main())
