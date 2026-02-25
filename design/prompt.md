只用过ClawChat.py和openClaw进行合作与聊天。先运行class ClawChat通过OpenAI库进行连接，连接到openClaw的服务器。

---

## ClawMail AI功能Prompt设计

### 通用约定

**输入格式**：所有Prompt统一使用结构化JSON作为邮件输入，便于解析和扩展。

**输出格式**：要求AI返回标准JSON，便于程序化处理。

**角色设定**：AI扮演专业邮件助手"Claw"，具备商务沟通、项目管理、信息提取能力。

---

## 1. 邮件统一分析（核心Prompt，覆盖信息补全+分类+任务提取）

**触发时机**：新邮件下载完成，首次AI处理（一次调用完成所有分析）

> **分类标签规范**：所有 category 值以 `tech_spec.md` 第3节为准。
> 系统固定标签：`urgent` / `pending_reply` / `notification` / `subscription` / `meeting` / `approval`
> 动态项目标签：格式 `"项目:{项目名称}"`，如 `"项目:Q4发布"`

**Prompt**：
```
你是ClawMail智能助手Claw。请分析以下邮件，一次性提取关键信息、生成摘要并识别待办事项。

【输入邮件】
{mail_json}

【分类说明】
从以下固定标签中选择 0-3 个（不强制必须选）：
- urgent（需24小时内处理）
- pending_reply（等待我方回复）
- notification（纯信息，无需行动）
- subscription（newsletters/推广）
- meeting（包含会议安排或日程）
- approval（需要决策或签字）
如邮件明确与某项目相关，额外输出一个"项目:XX"动态标签。总标签不超过4个。

【输出要求】
严格返回JSON，不要Markdown标记，所有字段必须存在：

{
  "keywords": [
    "关键词1",
    "关键词2",
    "关键词3-5个"
  ],

  "summary": {
    "one_line": "一句话核心概括（20字内）",
    "brief": "3-5行标准摘要",
    "key_points": ["要点1", "要点2", "要点3"]
  },

  "outline": [
    {
      "index": 1,
      "title": "段落主题",
      "content": "核心内容",
      "type": "背景|核心信息|行动要求|问题|其他"
    }
  ],

  "action_items": [
    {
      "text": "具体行动描述（动词开头）",
      "deadline": "YYYY-MM-DD或null",
      "deadline_source": "explicit|inferred|null",
      "priority": "high|medium|low",
      "assignee": "me|sender|other",
      "quote": "原文引用"
    }
  ],

  "metadata": {
    "category": ["urgent", "项目:Q4发布"],
    "sentiment": "urgent|positive|negative|neutral",
    "language": "zh|en|ja",
    "confidence": 0.95,
    "suggested_reply": "简短的建议回复草稿（如无需回复则为null）"
  }
}
```

**AI输出校验与降级规则**：

当 AI 返回非法 JSON 或字段缺失时，使用以下默认值并设置 `ai_status='failed'`，放入重试队列：
```python
DEFAULT_AI_RESULT = {
    "keywords": [],
    "summary": {"one_line": "", "brief": "", "key_points": []},
    "outline": [],
    "action_items": [],
    "metadata": {
        "category": [],
        "sentiment": "neutral",
        "language": "zh",
        "confidence": 0.0,
        "suggested_reply": None
    }
}
```

---

## 2. 邮件摘要生成（独立功能）

**触发时机**：用户点击"摘要"按钮，或长邮件自动触发

**Prompt**：
```
请为以下邮件生成简洁摘要。

【邮件内容】
主题：{subject}
发件人：{from}
正文：{body_text}

【摘要要求】
- 长度：3-5句话，不超过100字
- 结构：背景 → 核心信息 → 所需行动
- 语言：与邮件相同

【输出】
直接返回摘要文本，无需JSON格式。
```

---

## 3. 智能分类（独立功能，用于重新分类或批量整理）

**触发时机**：用户点击"重新分类"按钮，或批量整理已有邮件

> **注意**：新邮件首次处理时分类已包含在 Prompt #1 中，无需单独调用本 Prompt。

**Prompt**：
```
分析以下邮件，给出最准确的分类标签。

【邮件】
{mail_json}

【固定标签选项】
urgent / pending_reply / notification / subscription / meeting / approval
（动态项目标签格式：项目:{项目名称}）

【输出格式】
{
  "category": ["urgent", "项目:Q4发布"],
  "reasoning": "分类理由（一句话）",
  "suggested_new_label": "如现有标签都不匹配，建议新动态标签名，否则null"
}
```

---

## 4. 任务提取（ToDo生成）

**触发时机**：邮件处理流程中自动执行，或用户点击"提取任务"

**Prompt**：
```
从以下邮件中提取所有待办事项。

【邮件】
{mail_json}

【提取规则】
1. 明确任务：包含"请"、"需要"、"务必"等词的行动要求
2. 隐含任务：根据上下文推断的期望行动（如"周五前给我"→需在周五前回复）
3. 截止时间：识别具体日期或相对时间（明天/下周/月底）
4. 优先级：根据用词判断（紧急>重要>一般）

【输出格式】
{
  "action_items": [
    {
      "id": "task_001",
      "text": "任务描述（动词开头）",
      "deadline": "YYYY-MM-DD或null",
      "deadline_source": "explicit|inferred|null",
      "priority": "high|medium|low",
      "quote": "原文引用",
      "assignee": "me|sender|other"
    }
  ],
  "has_explicit_deadline": true,
  "suggested_reminder": "建议提醒时间"
}
// assignee 映射到存储层（ToDoListDesign.md assignee_type）：
// me→me，sender→waiting（等待发件人行动），other→delegate（委派给他人）
```

---

## 5. 智能撰写（邮件生成）

**触发时机**：用户在AI对话框输入写作需求

**Prompt**：
```
根据以下信息撰写一封专业邮件。

【写作需求】
{user_prompt}  // 用户输入，如"给客户写封延期道歉信，延期一周"

【上下文信息】
- 关联邮件：{related_mail_summary}  // 如有引用历史邮件
- 收件人信息：{recipient_info}  // 姓名、职位、过往往来风格
- 期望语气：{tone}  // 正式/友好/简洁/诚恳

【输出要求】
1. 主题行：简洁明确，包含关键信息
2. 正文：分段清晰，重点前置
3. 结尾：明确的下一步行动或期待回复

【输出格式】
{
  "subject": "邮件主题",
  "body": "完整正文（含称呼和落款）",
  "tone_analysis": "语气分析",
  "alternative_subjects": ["备选主题1", "备选主题2"],
  "suggested_attachments": ["建议附件类型"]
}
```

---

## 6. 邮件润色（辅导功能）

**触发时机**：用户选中文字点击"润色"

**Prompt**：
```
请润色以下邮件内容，保持原意但提升专业度。

【原文】
{selected_text}

【润色方向】
{style}  // 更正式 / 更友好 / 更简洁 / 更委婉

【输出格式】
{
  "polished_text": "润色后文本",
  "changes": [
    {"original": "原句", "modified": "修改后", "reason": "修改理由"}
  ],
  "alternative_versions": {
    "formal": "正式版",
    "friendly": "友好版"
  }
}
```

---

## 7. 智能回复建议

**触发时机**：用户点击"智能回复"

**Prompt**：
```
基于以下邮件，生成3个不同风格的回复建议。

【原邮件】
{mail_json}

【回复场景】
{context}  // 用户可选：同意/拒绝/询问/推迟

【输出格式】
{
  "suggestions": [
    {
      "style": "积极接受",
      "subject": "Re: {原主题}",
      "body": "完整回复内容",
      "key_points": ["表达感谢", "确认行动", "给出时间"]
    },
    {
      "style": "委婉拒绝",
      "subject": "...",
      "body": "...",
      "key_points": ["表达理解", "说明困难", "提供替代方案"]
    },
    {
      "style": "请求澄清",
      "subject": "...",
      "body": "...",
      "key_points": ["确认理解", "提出问题", "期待回复"]
    }
  ],
  "recommended": 0  // 推荐第几个（0-based）
}
```

---

## 8. AI助手对话（聊天框）

**触发时机**：用户在右侧面板输入问题

**Prompt**：
```
你是ClawMail助手Claw，正在与用户对话。用户可能询问当前邮件、历史邮件或一般问题。

【当前上下文】
- 选中邮件：{current_mail_json}
- 最近邮件（5封）：{recent_mails_summary}
- 对话历史：{chat_history}

【用户问题】
{user_question}

【回答要求】
1. 如问题涉及当前邮件，基于邮件内容回答
2. 如问题涉及历史邮件，基于提供的recent_mails回答
3. 如需要执行操作（如"提取任务"），返回action标记
4. 保持简洁，商务风格

【输出格式】
{
  "response": "回答文本（支持Markdown）",
  "action_triggered": "extract_tasks|summarize|compose|null",
  "action_params": {},
  "suggested_followups": ["建议后续问题1", "建议后续问题2"]
}
```

---

## Prompt管理架构

```
prompts/
├── __init__.py
├── manager.py              # Prompt加载和渲染
├── templates/              # 文本模板文件
│   ├── mail_analysis.txt   # 功能1：信息补全
│   ├── summarize.txt       # 功能2：摘要
│   ├── classify.txt        # 功能3：分类
│   ├── extract_tasks.txt   # 功能4：任务提取
│   ├── compose.txt         # 功能5：撰写
│   ├── polish.txt          # 功能6：润色
│   ├── reply_suggest.txt   # 功能7：回复建议
│   └── chat_assistant.txt  # 功能8：AI对话
└── variables/              # 动态变量定义
    ├── mail_schema.py      # 邮件JSON结构
    └── user_context.py     # 用户上下文
```

**使用示例**：
```python
from prompts.manager import PromptManager

pm = PromptManager()
prompt = pm.render('mail_analysis', mail_json=mail.to_json())
response = await openclaw.chat_completion(prompt)
result = json.loads(response)
mail.update_ai_metadata(result)
```

---

## 关键设计要点

1. **单一职责**：每个Prompt只做一个任务，避免指令冲突
2. **输入标准化**：统一使用JSON序列化的邮件对象，减少格式解析错误
3. **输出可验证**：要求结构化JSON，失败时可重试或降级
4. **上下文控制**：长邮件自动截断或分段，避免token超限
5. **可扩展**：新功能只需新增模板文件，无需修改核心代码

