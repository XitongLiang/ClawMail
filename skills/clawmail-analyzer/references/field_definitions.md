# 邮件分析字段定义规范

本文档定义 ClawMail 邮件分析的标准字段，与 ai_processor.py 保持严格一致。

---

## Summary 对象（摘要）

### keywords（关键词列表）
- **类型**: string[]
- **数量**: 3-5个
- **描述**: 从邮件中提取的最具代表性关键词

**提取维度及优先级**:
1. **核心主题词**（最高优先级）: 邮件讨论的核心话题或事件名称
2. **关键实体**（高优先级）: 人名、项目名、产品名、组织名等专有名词
3. **行动/状态词**（中优先级）: 邮件要求的核心行动或当前状态
4. **时间/场景标记**（低优先级）: 重要的时间节点或场景信息

**选取规则**:
- 总数3-5个，优先选取高优先级维度的词
- 每个关键词2-8个字，简洁有力
- 避免过于笼统的词: "工作"、"邮件"、"通知"、"信息"
- 避免重复或高度相似的词: 同时出现"报告"和"季度报告"，只保留后者
- 中英文按邮件原文语言输出

---

### one_line（一句话概括）
- **类型**: string
- **长度**: 20字以内
- **描述**: 用一句话回答"这封邮件说了什么"

**格式**: [主语] + [动作/状态] + [关键信息]

**好的例子**:
- "张总要求周五前提交Q4报告"
- "产品团队确认3月15日上线新功能"

**差的例子**:
- "关于报告的邮件"（太笼统，缺少具体信息）
- "讨论了项目进展"（缺少具体结论）

---

### brief（标准摘要）
- **类型**: string
- **长度**: 3-5行
- **描述**: 完整概述邮件内容，保留关键细节

**结构**:
1. 第一句: 点明核心主题
2. 中间: 补充重要背景和具体要求
3. 最后: 说明需要采取的行动或下一步

**原则**: 保持客观，不添加原文未提及的推断

---

## Action Items（待办事项）

### 单条待办结构

| 字段 | 类型 | 必填 | 说明 |
|-----|------|------|------|
| text | string | 是 | 具体行动描述（动词开头） |
| deadline | string\|null | 是 | 截止日期 (YYYY-MM-DD) |
| deadline_source | enum | 是 | explicit(明确写出) / inferred(推断) / null |
| priority | enum | 是 | high / medium / low |
| category | enum | 是 | 工作 / 学习 / 生活 /个人 |
| assignee | enum | 是 | me(我) / sender(发件人) / other(其他人) |
| quote | string | 是 | 提取 deadline/action 的原文片段 |

### Priority 定义

- **high**: 24小时内需要处理，或有明确今日/明日截止
- **medium**: 本周内需要完成
- **low**: 无明确时间要求，或可以延后

### Category 定义

- **工作**: 职场任务、商务沟通、项目相关
- **学习**: 学习资料、课程、知识获取
- **生活**: 日常事务、购物、个人生活
- **个人**: 个人事项、健康、家庭

### Assignee 定义

- **me**: 需要我执行的行动
- **sender**: 发件人承诺要做的事
- **other**: 第三方负责的事项

---

## Metadata（元数据）

### category（分类标签）
- **类型**: string[]
- **数量**: 0-4个

**固定标签**（可选0-3个）:
- `urgent`: 需24小时内处理
- `pending_reply`: 等待我方回复
- `notification`: 纯信息，无需行动
- `subscription`: newsletters/推广
- `meeting`: 包含会议安排或日程
- `approval`: 需要决策或签字

**动态标签**（可选0-1个）:
- `项目:XX`: 如邮件明确与某项目相关，如"项目:Q4发布"

**总标签数**: 不超过4个

---

### sentiment（情感倾向）
- **类型**: enum
- **可选值**:
  - `urgent`: 紧急
  - `positive`: 积极
  - `negative`: 消极
  - `neutral`: 中性

---

### language（语言）
- **类型**: enum
- **可选值**: `zh` | `en` | `ja` | 其他ISO语言码

---

### confidence（置信度）
- **类型**: number (0.0-1.0)
- **描述**: AI对分析结果的置信程度

**参考标准**:
- 0.9-1.0: 非常确定
- 0.7-0.89: 比较确定
- 0.5-0.69: 一般确定
- <0.5: 不确定，可能需要人工复核

---

### is_spam（垃圾邮件判断）
- **类型**: boolean
- **true**: 垃圾邮件/推广/广告/钓鱼邮件，应归入垃圾邮件文件夹
- **false**: 正常邮件

---

### importance_score（重要性评分）
- **类型**: integer
- **范围**: 0-100
- **描述**: 综合评估邮件的重要性

**评判维度及权重**:

| 维度 | 权重 | 说明 |
|-----|------|------|
| 发件人身份 | 30% | 基于组织架构的层级判断 |
| 紧急关键词 | 25% | 邮件表达的紧急程度 |
| 截止时间 | 25% | 基于当前时间的客观紧迫性 |
| 任务复杂度 | 20% | 待办数量和工作量 |

详见 [importance_algorithm.md](importance_algorithm.md)

---

### importance_breakdown（评分拆解）
- **类型**: object
- **描述**: 重要性评分的详细拆解，用于解释评分依据

```json
{
  "sender_weight": 30,
  "sender_score": 90,
  "sender_contrib": 27,
  "urgency_weight": 25,
  "urgency_score": 80,
  "urgency_contrib": 20,
  "deadline_weight": 25,
  "deadline_score": 70,
  "deadline_contrib": 17.5,
  "complexity_weight": 20,
  "complexity_score": 60,
  "complexity_contrib": 12,
  "total": 76.5
}
```

---

### suggested_reply（建议回复）
- **类型**: string|null
- **描述**: 简短的建议回复草稿
- **无需回复时**: null

---

### reply_stances（回复立场选项）
- **类型**: string[]
- **数量**: 0-4个（无需回复时为[]）
- **描述**: 我方可能的回复立场选项

**要求**:
- 动词开头，15字以内
- 选项应覆盖不同态度（如同意、拒绝、需要信息等）
- 若邮件无需回复（通知类/垃圾邮件/推广），输出空数组 []

**示例**:
- ["同意并确认时间", "需要更多信息", "暂时无法满足", "建议推迟到下周"]

---

## 完整输出示例

```json
{
  "summary": {
    "keywords": ["Q4报告", "张总", "周五截止", "财务数据"],
    "one_line": "张总要求周五前提交Q4财务报告",
    "brief": "张总邮件要求各部门在本周五（3月1日）前提交Q4季度财务报告。\n报告需包含收入、支出、利润三大板块数据。\n请确保数据准确，并抄送财务部审核。",
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
    "category": ["urgent", "工作", "项目:Q4财务"],
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
      "complexity_contrib": 13,
      "total": 85.25
    },
    "suggested_reply": "收到，我会按时完成Q4报告并提交审核。",
    "reply_stances": ["确认按时完成", "需要延期", "请求更多数据"]
  }
}
```
