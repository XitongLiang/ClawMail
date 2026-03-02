---
name: clawmail-learner
description: 用户偏好提取。分析用户对 AI 预测的修正行为，提取偏好记忆并写入 ClawMail MemoryBank。由 ClawMail 通过 subprocess 直接调用。
---

# ClawMail Learner Skill

分析用户对 AI 预测的修正，提取偏好记忆并写入 ClawMail MemoryBank。

## 触发方式

**ClawMail 直接调用脚本，不经过 LLM 路由。**
每次用户修正立即触发，不做批量。

```bash
python scripts/extract_preference.py \
  --feedback-type importance_score \
  --feedback-data '{"original_score": 45, "user_score": 15}' \
  --email-id <id> \
  --account-id <account_id>
```

## 支持的修正类型

| feedback_type | 说明 | 输入数据 |
|--------------|------|---------|
| importance_score | 用户修改重要性评分 | original_score, user_score |
| summary_rating | 用户给摘要评分(差评) | summary, rating, comment |
| reply_edit | 用户编辑 AI 回复草稿 | ai_draft, user_edited, similarity |
| category_change | 用户修改分类 | original_categories, user_categories |

## 执行流程

1. 从 ClawMail REST API 获取邮件上下文和已有记忆
2. LLM Call：分析用户修正行为，推断偏好
3. 通过 REST API 写入 MemoryBank

## REST API 依赖

| 端点 | 方法 | 用途 |
|------|------|------|
| `/emails/{id}` | GET | 获取邮件上下文 |
| `/memories/{account_id}` | GET | 获取已有记忆（避免重复） |
| `/memories/{account_id}` | POST | 写入新记忆 |

## LLM 调用

每次调用 1 次 LLM。输出为单个 JSON 对象（记忆条目或 skip）。

## 输出

通过 POST /memories/{account_id} 写入 MemoryBank。
stdout 输出执行状态 JSON（供 ClawMail 日志记录）。

## 目录结构

```
clawmail-learner/
├── SKILL.md
├── references/
│   ├── prompts/
│   │   ├── memory_extraction_guide.md  — 偏好提取规则
│   │   └── memory_types.md             — 记忆类型定义
│   └── specs/
│       └── memory_schema.md            — 记忆输出格式
└── scripts/
    ├── __init__.py
    └── extract_preference.py           — 偏好提取入口
```
