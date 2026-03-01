#!/usr/bin/env python3
"""
List all AI categories from ClawMail database.
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


def get_categories(account_id=None):
    """Get all AI categories."""
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
    parser = argparse.ArgumentParser(description="List all AI categories")
    parser.add_argument("--account", help="Filter by account ID")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        return 1
    
    categories = get_categories(account_id=args.account)
    
    if args.json:
        print(json.dumps(categories, indent=2))
    else:
        if not categories:
            print("No AI categories found.")
            return 0
        
        print(f"Found {len(categories)} AI categor{'y' if len(categories) == 1 else 'ies'}:")
        print("-" * 50)
        
        for cat in categories:
            print(f"  • {cat}")
    
    return 0


if __name__ == "__main__":
    exit(main())
