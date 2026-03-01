# ai_processor.py 输出格式规范

## JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["keywords", "summary", "outline", "action_items", "metadata"],
  "properties": {
    "keywords": {
      "type": "array",
      "items": {"type": "string"},
      "minItems": 0,
      "maxItems": 5
    },
    "summary": {
      "type": "object",
      "required": ["one_line", "brief"],
      "properties": {
        "one_line": {"type": "string", "maxLength": 20},
        "brief": {"type": "string"}
      }
    },
    "outline": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["index", "title", "content", "type"],
        "properties": {
          "index": {"type": "integer", "minimum": 1},
          "title": {"type": "string", "maxLength": 50},
          "content": {"type": "string", "maxLength": 200},
          "type": {"enum": ["背景", "核心信息", "行动要求", "问题", "其他"]}
        }
      }
    },
    "action_items": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["text", "deadline", "deadline_source", "priority", "category", "assignee", "quote"],
        "properties": {
          "text": {"type": "string", "maxLength": 50},
          "deadline": {"type": ["string", "null"], "format": "date"},
          "deadline_source": {"enum": ["explicit", "inferred", "null"]},
          "priority": {"enum": ["high", "medium", "low"]},
          "category": {"enum": ["工作", "学习", "生活", "个人"]},
          "assignee": {"enum": ["me", "sender", "other"]},
          "quote": {"type": "string", "maxLength": 50}
        }
      }
    },
    "metadata": {
      "type": "object",
      "required": ["category", "sentiment", "language", "confidence", "is_spam", "urgency", "suggested_reply", "reply_stances"],
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
        "urgency": {"enum": ["high", "medium", "low"]},
        "suggested_reply": {"type": ["string", "null"]},
        "reply_stances": {
          "type": "array",
          "items": {"type": "string", "maxLength": 15}
        }
      }
    }
  }
}
```

## 完整示例

### 输入邮件

```json
{
  "subject": "关于Q4项目进度汇报的会议邀请",
  "from": {"name": "张三", "email": "zhangsan@company.com"},
  "to": ["me@company.com"],
  "date": "2026-02-26 09:00",
  "body_text": "你好，\n\n想邀请你参加本周五下午2点的项目进度汇报会议。\n\n会议议程：\n1. Q4项目整体进度回顾\n2. 当前遇到的问题和挑战\n3. 下阶段计划和资源需求\n\n请确认是否可以参加，如果有时间冲突请提前告知。\n另外，麻烦准备一下你们团队的进度报告PPT。\n\n谢谢！\n张三"
}
```

### 输出结果

```json
{
  "keywords": ["会议", "项目", "进度", "汇报", "Q4"],
  "summary": {
    "one_line": "邀请参加周五Q4项目进度汇报会议",
    "brief": "张三邀请参加本周五下午2点的项目进度汇报会议。\n会议将回顾Q4项目进展、讨论当前问题并规划下阶段工作。\n需要确认参会并准备团队进度报告PPT。",
  },
  "outline": [
    {
      "index": 1,
      "title": "会议邀请",
      "content": "想邀请你参加本周五下午2点的项目进度汇报会议...",
      "type": "核心信息"
    },
    {
      "index": 2,
      "title": "会议议程",
      "content": "1. Q4项目整体进度回顾 2. 当前遇到的问题和挑战 3. 下阶段计划和资源需求",
      "type": "背景"
    },
    {
      "index": 3,
      "title": "参会确认",
      "content": "请确认是否可以参加，如果有时间冲突请提前告知...",
      "type": "行动要求"
    },
    {
      "index": 4,
      "title": "准备材料",
      "content": "另外，麻烦准备一下你们团队的进度报告PPT...",
      "type": "行动要求"
    }
  ],
  "action_items": [
    {
      "text": "请确认是否可以参加会议",
      "deadline": null,
      "deadline_source": "null",
      "priority": "medium",
      "category": "工作",
      "assignee": "me",
      "quote": "确认是否可以参加"
    },
    {
      "text": "麻烦准备团队进度报告PPT",
      "deadline": null,
      "deadline_source": "null",
      "priority": "high",
      "category": "工作",
      "assignee": "me",
      "quote": "准备一下你们团队的进度报告PPT"
    }
  ],
  "metadata": {
    "category": ["meeting", "pending_reply"],
    "sentiment": "neutral",
    "language": "zh",
    "confidence": 0.9,
    "is_spam": false,
    "urgency": "medium",
    "suggested_reply": "确认参加，准时出席。",
    "reply_stances": ["确认参加", "时间冲突需调整", "需要更多信息"]
  }
}
```

## 字段详解

### keywords
- 类型：字符串数组
- 数量：0-5个
- 作用：快速识别邮件主题

### summary
| 字段 | 类型 | 限制 | 说明 |
|------|------|------|------|
| one_line | string | 20字以内 | 一句话核心概括 |
| brief | string | 无限制 | 3-5行标准摘要 |

### outline
| 字段 | 类型 | 说明 |
|------|------|------|
| index | integer | 序号从1开始 |
| title | string | 段落主题，最多50字 |
| content | string | 内容摘要，最多200字 |
| type | enum | 背景/核心信息/行动要求/问题/其他 |

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

### metadata
| 字段 | 类型 | 说明 |
|------|------|------|
| category | array | 分类标签，最多4个 |
| sentiment | enum | positive/negative/neutral |
| language | enum | zh/en/ja |
| confidence | number | 0.0-1.0 置信度 |
| is_spam | boolean | 是否为垃圾邮件 |
| urgency | enum | high/medium/low 紧急程度 |
| suggested_reply | string/null | 建议回复草稿 |
| reply_stances | array | 回复立场选项，最多4个 |
