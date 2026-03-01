#!/usr/bin/env python3
"""
List tasks from ClawMail database with various filters.
"""

import argparse
import json
import sqlite3
from pathlib import Path
from datetime import datetime

# Database path
DB_PATH = Path.home() / "clawmail_data" / "clawmail.db"


def get_db_connection():
    """Get SQLite connection with row factory."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def list_tasks(status=None, priority=None, email_id=None, limit=100):
    """List tasks with optional filters."""
    conn = get_db_connection()
    
    query = "SELECT * FROM tasks WHERE 1=1"
    params = []
    
    if status:
        query += " AND status = ?"
        params.append(status)
    
    if priority:
        query += " AND priority = ?"
        params.append(priority)
    
    if email_id:
        query += " AND source_email_id = ?"
        params.append(email_id)
    
    query += " ORDER BY due_date ASC, created_at DESC LIMIT ?"
    params.append(limit)
    
    rows = conn.execute(query, params).fetchall()
    conn.close()
    
    tasks = []
    for row in rows:
        task = {
            "id": row["id"],
            "source_email_id": row["source_email_id"],
            "source_type": row["source_type"],
            "title": row["title"],
            "description": row["description"],
            "status": row["status"],
            "priority": row["priority"],
            "is_flagged": bool(row["is_flagged"]),
            "due_date": row["due_date"],
            "due_date_source": row["due_date_source"],
            "snoozed_until": row["snoozed_until"],
            "completed_at": row["completed_at"],
            "category": row["category"],
            "tags": row["tags"],
            "created_at": row["created_at"],
        }
        tasks.append(task)
    
    return tasks


def format_task_line(task):
    """Format task as a single line summary."""
    flag_icon = "F" if task["is_flagged"] else " "
    
    priority_icon = {
        "high": "H",
        "medium": "M",
        "low": "L",
        "none": "-"
    }.get(task["priority"], "-")
    
    status_icon = {
        "pending": "PENDING",
        "in_progress": "DOING",
        "snoozed": "SNOOZED",
        "completed": "DONE",
        "cancelled": "CANCELLED",
        "rejected": "REJECTED",
        "archived": "ARCHIVED"
    }.get(task["status"], "UNKNOWN")
    
    title = task["title"] or "(no title)"
    if len(title) > 50:
        title = title[:47] + "..."
    
    due = task["due_date"] or "No due date"
    
    return f"{flag_icon} {priority_icon} {status_icon} {task['id'][:8]}... | {title:50} | Due: {due}"


def main():
    parser = argparse.ArgumentParser(description="List tasks from ClawMail database")
    parser.add_argument("--status", choices=["pending", "in_progress", "snoozed", "completed", "cancelled", "rejected", "archived"],
                        help="Filter by status")
    parser.add_argument("--priority", choices=["high", "medium", "low", "none"],
                        help="Filter by priority")
    parser.add_argument("--email", help="Filter by source email ID")
    parser.add_argument("--limit", type=int, default=100, help="Limit results (default: 100)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        return 1
    
    tasks = list_tasks(
        status=args.status,
        priority=args.priority,
        email_id=args.email,
        limit=args.limit
    )
    
    if args.json:
        print(json.dumps(tasks, indent=2, default=str))
    else:
        if not tasks:
            print("No tasks found matching the criteria.")
            return 0
        
        print(f"Found {len(tasks)} task(s):")
        print("-" * 100)
        print(f"{'Flag':4} {'Pri':3} {'Status':3} {'ID':10} {'Title':50} {'Due Date'}")
        print("-" * 100)
        
        for task in tasks:
            print(format_task_line(task))
            if task["description"]:
                desc = task["description"].replace("\n", " ")
                if len(desc) > 80:
                    desc = desc[:77] + "..."
                print(f"      Description: {desc}")
    
    return 0


if __name__ == "__main__":
    exit(main())
