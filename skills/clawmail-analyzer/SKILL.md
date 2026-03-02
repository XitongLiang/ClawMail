---
name: clawmail-analyzer
description: 收到邮件分析与事实提取。分析收到的邮件生成结构化摘要、重要性评分、待办识别、回复建议；从收到的邮件中提取事实性信息写入 pending facts。由 ClawMail 通过 subprocess 直接调用。
---

# ClawMail 邮件分析 Skill

## 触发方式

**ClawMail 直接调用脚本，不经过 LLM 路由。**

```bash
python scripts/analyze_email.py \
  --email-id <email_id> \
  --account-id <account_id>
```

执行流程：
1. 从 ClawMail REST API 获取邮件数据、按发件人过滤的用户记忆、pending facts
2. 读取 USER.md 用户侧写
3. 单次 LLM 调用：邮件分析 + 事实提取合并
4. Python 后处理：默认值补全、importance 加权计算、事实分流
5. 通过 REST API 写回分析结果、MemoryBank 记忆、pending facts

## REST API 依赖

| 端点 | 方法 | 用途 |
|------|------|------|
| `/emails/{id}` | GET | 获取邮件完整数据 |
| `/emails/thread/{thread_id}` | GET | 获取线程上下文（回复邮件） |
| `/memories/{account_id}/for-email?sender_email=` | GET | 获取与当前邮件相关的偏好记忆（全局 + 发件人 + 域名） |
| `/pending-facts/{account_id}` | GET | 获取已有 pending facts（避免重复提取） |
| `/emails/{id}/ai-metadata` | POST | 写入分析结果 |
| `/memories/{account_id}` | POST | 直接写入 MemoryBank（contact/project 事实） |
| `/pending-facts/{account_id}` | POST | 写入 pending facts（career/org 事实） |
| `/pending-facts/{account_id}/promote` | POST | 触发 pending fact 提升到 USER.md |

## LLM 调用

通过 OpenClaw Gateway（`http://127.0.0.1:18789/v1/chat/completions`），OpenAI 兼容 API。

每次邮件分析包含 **1 次 LLM 调用**，同时完成分析和事实提取。
LLM 输出的 `importance_scores`（四维度）由 Python 加权计算最终 `importance_score`。

## 记忆注入

记忆按发件人过滤后注入 prompt，避免无关记忆浪费 token：
- 全局偏好（memory_key IS NULL）：urgency_signal、summary_preference 等
- 发件人级别：sender_importance、response_pattern 等
- 域名级别：automated_content 等

注入时按 memory_type 做 TTL 过滤：contact 永不过期，project 90天，偏好类 180天。
每条记忆附带年龄标签（如"2天前""3个月前"），帮助 LLM 判断时效性。

## 事实分流

LLM 提取的 `pending_facts` 按 fact_key 分流到不同存储：

| fact_key 前缀 | 目标 | 理由 |
|---------------|------|------|
| `contact.*` | MemoryBank（直接写入） | 关系记忆，立即生效，可更新 |
| `project.*` | MemoryBank（直接写入，带 extracted_date） | 项目信息有时效性，需要可更新/清理 |
| `career.*` / `org.*` | pending facts → 积累 → USER.md | 稳定个人属性，需多封邮件交叉验证 |

## 输出格式

### 邮件分析输出（写入 POST /emails/{id}/ai-metadata）

```json
{
  "summary": {
    "keywords": ["关键词1", "关键词2"],
    "one_line": "一句话概括（20字内）",
    "brief": "3-5行标准摘要"
  },
  "action_items": [
    {
      "text": "行动描述",
      "deadline": "2026-03-01",
      "deadline_source": "explicit",
      "priority": "high",
      "category": "工作",
      "assignee": "me",
      "quote": "原文引用"
    }
  ],
  "metadata": {
    "category": ["urgent", "pending_reply"],
    "sentiment": "neutral",
    "language": "zh",
    "confidence": 0.9,
    "is_spam": false,
    "importance_score": 72,
    "importance_breakdown": {
      "sender_weight": 30, "sender_score": 70, "sender_contrib": 21.0,
      "urgency_weight": 25, "urgency_score": 60, "urgency_contrib": 15.0,
      "deadline_weight": 25, "deadline_score": 80, "deadline_contrib": 20.0,
      "complexity_weight": 20, "complexity_score": 80, "complexity_contrib": 16.0,
      "total": 72.0
    },
    "suggested_reply": "收到，我会查看并回复。",
    "reply_stances": ["确认收到", "询问细节", "转发相关人"]
  }
}
```

### 事实提取输出（写入 POST /pending-facts/{account_id}）

```json
{
  "facts": [
    {
      "fact_key": "career.position",
      "fact_category": "career",
      "fact_content": "软件工程师",
      "confidence": 0.7,
      "source_email_id": "email_123"
    }
  ]
}
```

## 目录结构

```
clawmail-analyzer/
├── SKILL.md                          ← 本文件
├── references/
│   ├── prompts/                      ← 可被 personalization skill 演化
│   │   ├── importance_algorithm.md   — 重要性评分权重和规则
│   │   ├── summary_guide.md          — 摘要生成规则
│   │   ├── category_rules.md         — 分类标准
│   │   └── profile_extraction.md     — 事实信息提取规则
│   ├── specs/                        ← 接口契约，不可修改
│   │   ├── output_schema.md          — 输出 JSON 结构
│   │   ├── field_definitions.md      — 字段类型定义
│   │   ├── error_codes.md            — 错误码
│   │   └── memory_injection.md       — 记忆注入规范
│   └── (根目录保留的参考文档)
│       ├── integration_guide.md
│       ├── output_templates.md
│       ├── priority_criteria.md
│       ├── task_detection.md
│       └── feedback_system.md
└── scripts/
    ├── __init__.py
    └── analyze_email.py              ← 主脚本
```

## 参考文档

- [字段定义规范](references/specs/field_definitions.md)
- [输出格式](references/specs/output_schema.md)
- [重要性评分算法](references/prompts/importance_algorithm.md)
- [摘要生成规则](references/prompts/summary_guide.md)
- [分类规则](references/prompts/category_rules.md)
- [事实提取规则](references/prompts/profile_extraction.md)
- [错误码定义](references/specs/error_codes.md)
- [记忆注入规范](references/specs/memory_injection.md)
