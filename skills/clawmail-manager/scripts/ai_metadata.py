#!/usr/bin/env python3
"""
获取指定邮件的 AI 元数据。
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


def get_ai_metadata(email_id):
    """获取指定邮件的 AI 元数据。"""
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
    """格式化 AI 元数据以供显示。"""
    lines = []
    lines.append("=" * 60)
    lines.append("🤖 邮件 AI 元数据")
    lines.append("=" * 60)
    lines.append(f"邮件 ID: {metadata['email_id']}")
    lines.append(f"AI 状态: {metadata['ai_status']}")
    lines.append(f"处理进度: {metadata['processing_progress']}%")
    lines.append("")

    if metadata["sentiment"]:
        lines.append(f"情感: {metadata['sentiment']}")

    if metadata["is_spam"] is not None:
        lines.append(f"垃圾邮件: {'是' if metadata['is_spam'] else '否'}")

    if metadata["categories"]:
        lines.append(f"分类: {', '.join(metadata['categories'])}")

    if metadata["keywords"]:
        lines.append(f"关键词: {', '.join(metadata['keywords'])}")

    if metadata["summary_one_line"]:
        lines.append("")
        lines.append("-" * 60)
        lines.append("一句话摘要:")
        lines.append("-" * 60)
        lines.append(metadata["summary_one_line"])

    if metadata["summary_brief"]:
        lines.append("")
        lines.append("-" * 60)
        lines.append("简要摘要:")
        lines.append("-" * 60)
        lines.append(metadata["summary_brief"])

    if metadata["suggested_reply"]:
        lines.append("")
        lines.append("-" * 60)
        lines.append("建议回复:")
        lines.append("-" * 60)
        lines.append(metadata["suggested_reply"])

    if metadata["processing_error"]:
        lines.append("")
        lines.append("-" * 60)
        lines.append("处理错误:")
        lines.append("-" * 60)
        lines.append(metadata["processing_error"])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="获取邮件的 AI 元数据")
    parser.add_argument("email_id", help="邮件 ID")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"错误: 数据库不存在于 {DB_PATH}")
        return 1

    metadata = get_ai_metadata(args.email_id)

    if not metadata:
        print(f"未找到邮件 {args.email_id} 的 AI 元数据")
        return 1

    if args.json:
        print(json.dumps(metadata, indent=2, default=str))
    else:
        print(format_metadata(metadata))

    return 0


if __name__ == "__main__":
    exit(main())
