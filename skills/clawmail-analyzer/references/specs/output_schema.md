# 邮件分析输出格式规范

> **注意**：本文档描述的是**最终写入 ai-metadata 的格式**。
> LLM 输出的 `importance_scores`（四个原始分）会被 Python 后处理为 `importance_score` + `importance_breakdown`。

## JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["summary", "action_items", "metadata"],
  "properties": {
    "summary": {
      "type": "object",
      "required": ["keywords", "one_line", "brief"],
      "properties": {
        "keywords": {
          "type": "array",
          "items": {"type": "string"},
          "minItems": 0,
          "maxItems": 8
        },
        "one_line": {"type": "string", "maxLength": 30},
        "brief": {"type": "string", "maxLength": 150}
      }
    },
    "action_items": {
      "type": "array",
      "maxItems": 10,
      "items": {
        "type": "object",
        "required": ["text", "deadline", "deadline_source", "priority", "category", "assignee", "quote"],
        "properties": {
          "text": {"type": "string", "maxLength": 50},
          "deadline": {"type": ["string", "null"], "format": "date"},
          "deadline_source": {"enum": ["explicit", "inferred", null]},
          "priority": {"enum": ["high", "medium", "low"]},
          "category": {"enum": ["工作", "学习", "生活", "个人"]},
          "assignee": {"enum": ["me", "sender", "other"]},
          "quote": {"type": "string", "maxLength": 50}
        }
      }
    },
    "metadata": {
      "type": "object",
      "required": ["category", "sentiment", "language", "confidence", "is_spam", "importance_score", "importance_breakdown", "suggested_reply", "reply_stances"],
      "properties": {
        "category": {
          "type": "array",
          "items": {"type": "string"},
          "maxItems": 4
        },
        "sentiment": {"enum": ["positive", "negative", "neutral"]},
        "language": {"enum": ["zh", "en", "ja"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "is_spam": {"type": "boolean"},
        "importance_score": {
          "type": "integer", "minimum": 0, "maximum": 100,
          "description": "Python 从 LLM 输出的 importance_scores 加权计算得出"
        },
        "importance_breakdown": {
          "type": "object",
          "description": "Python 计算得出，包含四维度权重、原始分和加权贡献",
          "properties": {
            "sender_weight": {"type": "integer"},
            "sender_score": {"type": "integer"},
            "sender_contrib": {"type": "number"},
            "urgency_weight": {"type": "integer"},
            "urgency_score": {"type": "integer"},
            "urgency_contrib": {"type": "number"},
            "deadline_weight": {"type": "integer"},
            "deadline_score": {"type": "integer"},
            "deadline_contrib": {"type": "number"},
            "complexity_weight": {"type": "integer"},
            "complexity_score": {"type": "integer"},
            "complexity_contrib": {"type": "number"},
            "total": {"type": "number"}
          }
        },
        "suggested_reply": {"type": ["string", "null"]},
        "reply_stances": {
          "type": "array",
          "items": {"type": "string", "maxLength": 15},
          "maxItems": 4
        }
      }
    }
  }
}
```

## LLM 原始输出 vs 最终存储

| 字段 | LLM 输出 | Python 后处理 | 最终存储 |
|------|---------|--------------|---------|
| importance_scores | `{sender_score, urgency_score, deadline_score, complexity_score}` | 加权计算 | 删除 |
| importance_score | - | 从 importance_scores 计算 | 0-100 整数 |
| importance_breakdown | - | 从 importance_scores 生成 | 完整拆解对象 |
| pending_facts | LLM 输出 | 分流写入 MemoryBank / pending 池 | 从 ai-metadata 中移除 |

## 完整示例（最终存储格式）

```json
{
  "summary": {
    "keywords": ["Q4报告", "张总", "周五截止", "财务数据"],
    "one_line": "张总要求周五前提交Q4财务报告",
    "brief": "张总邮件要求各部门在本周五（3月1日）前提交Q4季度财务报告。\n报告需包含收入、支出、利润三大板块数据。\n请确保数据准确，并抄送财务部审核。"
  },
  "action_items": [
    {
      "text": "整理Q4财务数据并撰写报告",
      "deadline": "2026-03-01",
      "deadline_source": "explicit",
      "priority": "high",
      "category": "工作",
      "assignee": "me",
      "quote": "请在本周五（3月1日）前提交Q4季度财务报告"
    },
    {
      "text": "抄送财务部审核报告",
      "deadline": "2026-03-01",
      "deadline_source": "inferred",
      "priority": "medium",
      "category": "工作",
      "assignee": "me",
      "quote": "完成后请抄送财务部进行审核"
    }
  ],
  "metadata": {
    "category": ["urgent", "pending_reply", "项目:Q4财务"],
    "sentiment": "neutral",
    "language": "zh",
    "confidence": 0.95,
    "is_spam": false,
    "importance_score": 85,
    "importance_breakdown": {
      "sender_weight": 30,
      "sender_score": 95,
      "sender_contrib": 28.5,
      "urgency_weight": 25,
      "urgency_score": 90,
      "urgency_contrib": 22.5,
      "deadline_weight": 25,
      "deadline_score": 85,
      "deadline_contrib": 21.25,
      "complexity_weight": 20,
      "complexity_score": 65,
      "complexity_contrib": 13.0,
      "total": 85.25
    },
    "suggested_reply": "收到，我会按时完成Q4报告并提交审核。",
    "reply_stances": ["确认按时完成", "需要延期", "请求更多数据"]
  }
}
```

## 字段详解

### summary
| 字段 | 类型 | 限制 | 说明 |
|------|------|------|------|
| keywords | array | 3-8个 | 最具代表性的关键词 |
| one_line | string | 30字以内 | 一句话核心概括 |
| brief | string | 3-5行，≤150字 | 结构化摘要 |

### action_items
| 字段 | 类型 | 说明 |
|------|------|------|
| text | string | 行动描述，动词开头，最多50字 |
| deadline | string/null | YYYY-MM-DD 格式或 null |
| deadline_source | enum | explicit(明确)/inferred(推断)/null |
| priority | enum | high/medium/low |
| category | enum | 工作/学习/生活/个人 |
| assignee | enum | me(我)/sender(发件人)/other(其他) |
| quote | string | 原文引用，最多50字 |

> **数量限制**: 最多 10 个行动事项。超出时仅保留优先级最高的前 10 个。

### metadata
| 字段 | 类型 | 来源 | 说明 |
|------|------|------|------|
| category | array | LLM | 分类标签，最多4个 |
| sentiment | enum | LLM | positive/negative/neutral |
| language | enum | LLM | zh/en/ja |
| confidence | number | LLM | 0.0-1.0 置信度 |
| is_spam | boolean | LLM | 是否为垃圾邮件 |
| importance_score | integer | Python 计算 | 0-100 重要性评分 |
| importance_breakdown | object | Python 计算 | 评分四维度拆解 |
| suggested_reply | string/null | LLM | 建议回复草稿 |
| reply_stances | array | LLM | 回复立场选项，最多4个 |