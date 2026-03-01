---
name: clawmail-manager
description: Manage ClawMail email system - query emails, tasks, and AI metadata from SQLite database. Use when working with ClawMail data including searching emails by folder/category/keywords, marking read/unread, flagging, pinning, listing tasks, and getting email statistics.
---

# ClawMail Manager

Manage and query ClawMail email data from the SQLite database.

## Data Directory Structure

ClawMail 数据存储在以下位置：

```
~/clawmail_data/
├── clawmail.db          # SQLite 数据库文件
├── emails/              # 邮件原始内容存储
│   ├── <account_id>/    # 按账户分类
│   │   ├── <folder>/    # 按文件夹分类
│   │   │   └── <email_id>.eml
│   └── ...
├── attachments/         # 附件存储
│   └── <attachment_id>.<ext>
└── logs/                # 操作日志
    └── clawmail.log
```

## Database Location

The SQLite database is located at: `~/clawmail_data/clawmail.db`

## Available Scripts

All scripts are in the `scripts/` folder and can be run directly:

### Email Operations

| Script | Purpose | Example |
|--------|---------|---------|
| `list_emails.py` | List emails with filters | `python scripts/list_emails.py --folder INBOX --limit 20` |
| `search_emails.py` | Search by keywords | `python scripts/search_emails.py "project deadline"` |
| `mark_email.py` | Mark read/unread, flag, pin | `python scripts/mark_email.py <email_id> --read --flag` |
| `move_email.py` | Move email to folder | `python scripts/move_email.py <email_id> --folder Archive` |
| `email_stats.py` | Get email statistics | `python scripts/email_stats.py` |

### Task Operations

| Script | Purpose | Example |
|--------|---------|---------|
| `list_tasks.py` | List tasks with filters | `python scripts/list_tasks.py --status pending` |
| `task_categories.py` | List all AI categories | `python scripts/task_categories.py` |

### AI Metadata Operations

| Script | Purpose | Example |
|--------|---------|---------|
| `ai_metadata.py` | Get AI metadata for email | `python scripts/ai_metadata.py <email_id>` |
| `emails_by_category.py` | Get emails by AI category | `python scripts/emails_by_category.py "urgent"` |
| `ai_summary_report.py` | AI摘要反馈报告 | `python scripts/ai_summary_report.py` |

## Common Workflows

### Search and Mark Emails

```bash
# Search for emails about "invoice"
python scripts/search_emails.py "invoice"

# Mark a specific email as read and flagged
python scripts/mark_email.py <email_id> --read --flag
```

### Get Unread Emails from INBOX

```bash
python scripts/list_emails.py --folder INBOX --status unread --limit 50
```

### List Pending Tasks

```bash
python scripts/list_tasks.py --status pending
```

### Get Email Statistics

```bash
python scripts/email_stats.py
```

### Generate AI Summary Report

```bash
# 生成AI摘要反馈报告
python scripts/ai_summary_report.py

# 以JSON格式输出
python scripts/ai_summary_report.py --json
```

## Script Parameters

### list_emails.py
- `--folder FOLDER` - Filter by folder (INBOX, Sent, Drafts, etc.)
- `--account ACCOUNT_ID` - Filter by account ID
- `--status {read,unread,skimmed}` - Filter by read status
- `--flagged` - Show only flagged emails
- `--pinned` - Show only pinned emails
- `--limit N` - Limit results (default: 50)
- `--json` - Output as JSON

### search_emails.py
- `--folder FOLDER` - Filter by folder
- `--account ACCOUNT_ID` - Filter by account
- `--limit N` - Limit results (default: 50)
- `--json` - Output as JSON

### mark_email.py
- `--read` / `--unread` - Set read status
- `--flag` / `--unflag` - Set flag status
- `--pin` / `--unpin` - Set pinned status

### list_tasks.py
- `--status {pending,in_progress,snoozed,completed,cancelled,rejected,archived}` - Filter by status
- `--priority {high,medium,low,none}` - Filter by priority
- `--email EMAIL_ID` - Filter by source email
- `--limit N` - Limit results (default: 100)
- `--json` - Output as JSON

### email_stats.py
- `--account ACCOUNT_ID` - Stats for specific account
- `--json` - Output as JSON

### ai_summary_report.py
- `--json` - Output as JSON

## Database Schema Overview

### 主要表结构

**emails** - 邮件主表
- `id` - 邮件唯一ID
- `account_id` - 所属账户
- `folder` - 所在文件夹
- `subject` - 主题
- `sender` - 发件人
- `recipient` - 收件人
- `date` - 日期
- `body_text` - 纯文本内容
- `body_html` - HTML内容
- `is_read` - 是否已读
- `is_flagged` - 是否标记
- `is_pinned` - 是否置顶

**tasks** - 任务表
- `id` - 任务ID
- `email_id` - 关联邮件ID
- `title` - 任务标题
- `status` - 状态
- `priority` - 优先级
- `due_date` - 截止日期
- `ai_category` - AI分类

**ai_metadata** - AI分析元数据
- `email_id` - 关联邮件ID
- `summary` - AI摘要
- `category` - AI分类
- `priority_score` - 优先级评分
- `action_items` - 行动项
- `sentiment` - 情感分析

## 高级用法

### 批量处理邮件

```bash
# 获取所有未读邮件并标记为已读
python scripts/list_emails.py --status unread --json | jq -r '.[].id' | xargs -I {} python scripts/mark_email.py {} --read
```

### 按优先级筛选任务

```bash
# 获取高优先级待办任务
python scripts/list_tasks.py --status pending --priority high
```

### 导出邮件数据

```bash
# 导出特定文件夹的所有邮件为JSON
python scripts/list_emails.py --folder INBOX --json > inbox_emails.json
```

## 故障排除

### 数据库连接问题
确保数据库文件存在：
```bash
ls ~/clawmail_data/clawmail.db
```

### 权限问题
确保对 `clawmail_data` 目录有读写权限。

### 数据备份建议
定期备份数据库文件：
```bash
cp ~/clawmail_data/clawmail.db ~/clawmail_data/clawmail.db.backup
```
