#!/usr/bin/env python3
"""
Move email to a different folder.
"""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

# Database path
DB_PATH = Path.home() / "clawmail_data" / "clawmail.db"


def get_db_connection():
    """Get SQLite connection."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn


def move_email(email_id, folder):
    """Move email to specified folder."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE emails SET folder = ?, updated_at = ? WHERE id = ?",
        (folder, datetime.utcnow().isoformat(), email_id)
    )
    
    if cursor.rowcount == 0:
        print(f"Email {email_id} not found.")
        conn.close()
        return False
    
    conn.commit()
    conn.close()
    return True


def get_email_info(email_id):
    """Get current email info."""
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT subject, folder FROM emails WHERE id = ?",
        (email_id,)
    ).fetchone()
    conn.close()
    return row


def main():
    parser = argparse.ArgumentParser(description="Move email to a folder")
    parser.add_argument("email_id", help="Email ID to move")
    parser.add_argument("--folder", required=True, help="Target folder (INBOX, Archive, Trash, etc.)")
    
    args = parser.parse_args()
    
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        return 1
    
    before = get_email_info(args.email_id)
    if not before:
        print(f"Email {args.email_id} not found.")
        return 1
    
    if move_email(args.email_id, args.folder):
        subject = before["subject"] or "(no subject)"
        print(f"Moved: {subject}")
        print(f"  Folder: {before['folder']} → {args.folder}")
    
    return 0


if __name__ == "__main__":
    exit(main())
