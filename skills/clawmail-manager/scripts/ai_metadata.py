#!/usr/bin/env python3
"""
Get AI metadata for a specific email.
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


def get_ai_metadata(email_id):
    """Get AI metadata for an email."""
    conn = get_db_connection()
    
    row = conn.execute(
        "SELECT * FROM email_ai_metadata WHERE email_id = ?",
        (email_id,)
    ).fetchone()
    
    conn.close()
    
    if not row:
        return None
    
    metadata = {
        "email_id": row["email_id"],
        "keywords": json.loads(row["keywords"]) if row["keywords"] else None,
        "summary_one_line": row["summary_one_line"],
        "summary_brief": row["summary_brief"],

        "outline": json.loads(row["outline"]) if row["outline"] else None,
        "categories": json.loads(row["categories"]) if row["categories"] else None,
        "sentiment": row["sentiment"],
        "suggested_reply": row["suggested_reply"],
        "is_spam": row["is_spam"],
        "ai_status": row["ai_status"],
        "processing_progress": row["processing_progress"],
        "processing_stage": row["processing_stage"],
        "processed_at": row["processed_at"],
        "processing_error": row["processing_error"],
    }
    
    return metadata


def format_metadata(metadata):
    """Format AI metadata for display."""
    lines = []
    lines.append("=" * 60)
    lines.append("🤖 AI Metadata for Email")
    lines.append("=" * 60)
    lines.append(f"Email ID: {metadata['email_id']}")
    lines.append(f"AI Status: {metadata['ai_status']}")
    lines.append(f"Processing: {metadata['processing_progress']}%")
    lines.append("")
    
    if metadata["sentiment"]:
        lines.append(f"Sentiment: {metadata['sentiment']}")
    
    if metadata["is_spam"] is not None:
        lines.append(f"Spam: {'Yes' if metadata['is_spam'] else 'No'}")
    
    if metadata["categories"]:
        lines.append(f"Categories: {', '.join(metadata['categories'])}")
    
    if metadata["keywords"]:
        lines.append(f"Keywords: {', '.join(metadata['keywords'])}")
    
    if metadata["summary_one_line"]:
        lines.append("")
        lines.append("-" * 60)
        lines.append("One-line Summary:")
        lines.append("-" * 60)
        lines.append(metadata["summary_one_line"])
    
    if metadata["summary_brief"]:
        lines.append("")
        lines.append("-" * 60)
        lines.append("Brief Summary:")
        lines.append("-" * 60)
        lines.append(metadata["summary_brief"])
    
    if metadata["suggested_reply"]:
        lines.append("")
        lines.append("-" * 60)
        lines.append("Suggested Reply:")
        lines.append("-" * 60)
        lines.append(metadata["suggested_reply"])
    
    if metadata["processing_error"]:
        lines.append("")
        lines.append("-" * 60)
        lines.append("Processing Error:")
        lines.append("-" * 60)
        lines.append(metadata["processing_error"])
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Get AI metadata for an email")
    parser.add_argument("email_id", help="Email ID")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        return 1
    
    metadata = get_ai_metadata(args.email_id)
    
    if not metadata:
        print(f"No AI metadata found for email {args.email_id}")
        return 1
    
    if args.json:
        print(json.dumps(metadata, indent=2, default=str))
    else:
        print(format_metadata(metadata))
    
    return 0


if __name__ == "__main__":
    exit(main())
