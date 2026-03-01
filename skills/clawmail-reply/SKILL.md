---
name: clawmail-reply
description: 邮件回复、撰写、润色、习惯提取。生成回复草稿、撰写新邮件、润色已有邮件、提取用户撰写习惯。由 ClawMail 通过 subprocess 直接调用。
---

# ClawMail Reply Skill

## 触发方式

**ClawMail 直接调用脚本，不经过 LLM 路由。**

### 1. 回复草稿生成

```bash
python scripts/generate_reply.py \
  --email-id <id> \
  --stance "确认收到并查看" \
  --tone "礼貌" \
  --account-id <account_id> \
  --user-notes "提一下周五前会回复详细意见"
```

### 2. 新邮件生成

```bash
python scripts/generate_email.py \
  --subject "Q4进度汇报" \
  --outline "汇报本季度工作进展，包括完成的任务和遇到的问题" \
  --tone "正式" \
  --account-id <account_id>
```

### 3. 邮件润色

```bash
python scripts/polish_email.py \
  --body "原始邮件内容..." \
  --tone "礼貌" \
  --account-id <account_id>
```

### 4. 用户撰写习惯提取

用户发送邮件/回复后触发，提取写作习惯和沟通风格到 pending facts。

```bash
python scripts/extract_habits.py \
  --compose-data '{"subject": "...", "to": "...", "body": "...", "is_reply": true}' \
  --account-id <account_id>
```

## 输出

- **回复/生成/润色**（1-3）：纯文本邮件内容，直接 print 到 stdout。ClawMail 从 `result.stdout.strip()` 读取。
- **习惯提取**（4）：JSON 状态输出到 stdout，实际数据通过 REST API 写入 pending facts。

## REST API 依赖

| 端点 | 方法 | 用途 | 被谁调用 |
|------|------|------|---------|
| `/emails/{id}` | GET | 获取原始邮件 | generate_reply |
| `/emails/{id}/ai-metadata` | GET | 获取分析结果 | generate_reply |
| `/memories/{account_id}` | GET | 获取用户偏好记忆 | 全部 |
| `/pending-facts/{account_id}` | GET | 获取已有 pending facts | extract_habits |
| `/pending-facts/{account_id}` | POST | 写入新 pending facts | extract_habits |
| `/pending-facts/{account_id}/promote` | POST | 触发提升检查 | extract_habits |

## LLM 调用

通过 OpenClaw Gateway（`http://127.0.0.1:18789/v1/chat/completions`），每个脚本调用 1 次 LLM。

## 目录结构

```
clawmail-reply/
├── SKILL.md
├── references/
│   ├── prompts/                      ← 可被 personalization skill 演化
│   │   ├── reply_guide.md            — 回复生成规则
│   │   ├── generate_email_guide.md   — 新邮件生成规则
│   │   ├── polish_guide.md           — 润色规则
│   │   ├── tone_styles.md            — 语气风格定义
│   │   └── habit_extraction.md       — 用户习惯提取规则
│   └── specs/
│       └── output_format.md          — 输出格式规范
└── scripts/
    ├── __init__.py
    ├── generate_reply.py             — 回复生成入口
    ├── generate_email.py             — 新邮件生成入口
    ├── polish_email.py               — 润色入口
    └── extract_habits.py             — 用户撰写习惯提取
```
