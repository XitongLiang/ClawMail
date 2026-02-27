## ClawMail 邮件内容定义

### 基础信息层（原始数据）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | 系统唯一标识 |
| `imap_uid` | String | 服务器端UID，用于同步 |
| `subject` | String | 邮件主题（原始） |
| `from` | EmailAddress | 发件人（姓名+邮箱） |
| `to` | List[EmailAddress] | 收件人列表 |
| `cc` | List[EmailAddress] | 抄送列表 |
| `bcc` | List[EmailAddress] | 密送列表（仅自己发送的邮件有） |
| `date` | Datetime | 发送时间（服务器时间） |
| `received_at` | Datetime | 本地接收时间 |
| `size` | Int | 邮件大小（字节） |
| `thread_id` | String | 会话线程ID，关联往来邮件 |

---

### 内容层（正文与附件）

| 字段 | 类型 | 说明 |
|------|------|------|
| `body_text` | String | 纯文本正文（提取或转换） |
| `body_html` | String | 原始HTML正文 |
| `content_type` | Enum | text/plain / text/html / multipart |
| `attachments` | List[Attachment] | 附件列表 |
| `embedded_images` | List[Image] | 内嵌图片（HTML邮件） |
| `encoding` | String | 原始编码格式 |

**Attachment 结构**：
```
- filename: 文件名
- content_type: MIME类型
- size: 大小
- content_id: 内嵌引用ID
- local_path: 本地存储路径（下载后填充）
- is_downloaded: 是否已下载到本地
```

---

### AI处理层（智能生成）

| 字段 | 类型 | 生成方式 |
|------|------|---------|
| `summary` | Object | AI生成摘要：含 one_line / brief / key_points 三层结构 |
| `keywords` | List[String] | AI提取的5-10个关键词 |
| `outline` | List[OutlineItem] | 邮件结构大纲（要点分解） |
| `category` | List[String] | 智能分类标签（**规范值见 tech_spec.md 第3节**） |
| `sentiment` | Enum | AI情感/紧急度：`urgent` / `positive` / `negative` / `neutral` |
| `urgency` | Enum | 紧急度：`high` / `medium` / `low` |
| `is_spam` | Boolean | 是否为垃圾邮件 |
| `action_items` | List[ActionItem] | 待办事项提取 |
| `reply_stances` | List[String] | AI 建议的回复立场 |
| `suggested_reply` | String | AI建议的回复草稿（可为 null） |
| `importance_score` | Int (0-100) | AI 评估的邮件重要性（详见 PersonalizationPlan.md） |
| `language` | String | 检测语言（zh/en/ja等） |

> **category 规范标签**（来自 `tech_spec.md` 3.1节）：
> - 固定标签：`urgent`、`pending_reply`、`notification`、`subscription`、`meeting`、`approval`
> - 动态项目标签：格式 `"项目:{项目名称}"`，如 `"项目:Q4发布"`
> - 存储格式：JSON 数组，空时为 `[]`，不为 `null`

**OutlineItem 结构**：
```
- index: 序号
- title: 要点标题
- content: 详细内容
- type: 段落/列表/行动项/问题
```

**ActionItem 结构**：
```
- text: 任务描述
- deadline: 推测截止日期（YYYY-MM-DD 或 null）
- deadline_source: 截止来源（explicit|inferred|null）
- priority: 优先级（high|medium|low）
- assignee: 指派人（me|sender|other）
- quote: 原文引用
- added_to_todo: 是否已加入待办清单
```
> 字段名与 prompt.md Prompt #1 的 action_items 输出格式完全一致。
> assignee 值映射到 Task 存储层：me→me，sender→waiting，other→delegate。

---

### 状态层（处理进度）

| 字段 | 类型 | 说明 |
|------|------|------|
| `sync_status` | Enum | 同步状态：`pending` / `downloading` / `completed` / `failed`（见 tech_spec.md 2.1节） |
| `ai_status` | Enum | AI处理状态：`unprocessed` / `processing` / `processed` / `failed` / `skipped`（见 tech_spec.md 2.2节） |
| `processing_progress` | Int | 处理进度百分比（0-100） |
| `processing_stage` | String | 当前阶段：关键词/分类/摘要/任务提取 |
| `read_status` | Enum | 阅读状态：unread / read / skimmed（快速浏览） |
| `flag_status` | Enum | 标记状态：none / flagged / completed |
| `reply_status` | Enum | 回复状态：no_need / pending / replied / forwarded |

**状态流转**：
```
下载完成 → unprocessed
    ↓
开始AI处理 → processing (显示进度条)
    ↓
[关键词 ✓] → [分类 ✓] → [摘要 ✓] → [任务提取 ✓]
    ↓
processed（正式显示在列表中）
```

---

### 关联层（关系与历史）

| 字段 | 类型 | 说明 |
|------|------|------|
| `in_reply_to` | String | 回复目标的Message-ID |
| `references` | List[String] | 整个线程的Message-ID链 |
| `related_emails` | List[UUID] | 关联邮件ID（同线程） |
| `conversation_history` | List[ChatMessage] | 与该邮件相关的AI对话记录 |
| `user_notes` | String | 用户手动添加的备注 |

---

### 完整数据示例（JSON视角）

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "imap_uid": "12345",
  "subject": "Q4项目进度汇报及延期申请",
  "from": {"name": "张三", "email": "zhangsan@company.com"},
  "to": [{"name": "我", "email": "me@163.com"}],
  "date": "2024-01-15T10:30:00+08:00",
  
  "body_text": "李工，\n\nQ4项目因外部供应商延迟，预计需要延期两周...",
  "body_html": "<html>...</html>",
  "attachments": [
    {
      "filename": "Q4_schedule.xlsx",
      "size": 25600,
      "is_downloaded": true,
      "local_path": "/data/attachments/550e8400/..."
    }
  ],
  
  "ai_metadata": {
    "summary": {
      "one_line": "张三申请Q4项目延期两周",
      "brief": "Q4项目因外部供应商交付延迟，申请延期两周至2月15日，附最新排期表。",
      "key_points": ["供应商延迟是根因", "预计延期至2月15日", "需尽快确认是否同意"]
    },
    "keywords": ["Q4项目", "延期申请", "供应商", "进度汇报", "排期"],
    "outline": [
      {"index": 1, "title": "项目现状", "content": "已完成80%，测试阶段", "type": "段落"},
      {"index": 2, "title": "延期原因", "content": "第三方API接口延迟交付", "type": "列表"},
      {"index": 3, "title": "新时间表", "content": "预计延期至2月15日", "type": "行动项"}
    ],
    "category": ["urgent", "项目:项目A", "pending_reply"],
    "sentiment": "urgent",
    "urgency": "high",
    "is_spam": false,
    "importance_score": 92,
    "reply_stances": ["同意延期", "要求更详细排期"],
    "action_items": [
      {
        "text": "确认是否同意延期申请",
        "deadline": "2024-01-17",
        "priority": "high",
        "added_to_todo": true
      }
    ],
    "suggested_reply": "收到，我会评估延期影响并尽快回复..."
  },
  
  "status": {
    "sync_status": "completed",
    "ai_status": "processed",
    "processing_progress": 100,
    "read_status": "unread",
    "flag_status": "flagged",
    "reply_status": "pending"
  }
}
```

---

## UI展示映射

| UI区域 | 使用字段 |
|--------|---------|
| 邮件列表（左二） | subject, from.name, summary, date, category, read_status, flag_status |
| 状态进度条（右二上） | ai_status, processing_progress, processing_stage |
| 邮件内容（右二中） | body_html/body_text, attachments, outline |
| AI处理区（右二下） | suggested_reply, action_items |
| 智能分类（左一下） | category |
| ToDo清单（右一上） | action_items (filtered by added_to_todo=true) |
| AI对话框（右一下） | 全字段可读，对话上下文关联 |

---

## 关键设计决策

1. **AI元数据独立存储**：`ai_metadata`作为JSON字段或单独表，便于扩展新AI功能而不改表结构

2. **状态分离**：`sync_status`（下载）与`ai_status`（处理）独立，支持断点续传和重试

3. **大纲结构化**：不只是文本，而是结构化数组，支持UI折叠展开、点击跳转

4. **待办双向绑定**：邮件中的`action_items`与ToDo清单系统共享ID，状态同步

5. **渐进式加载**：正文和附件按需下载，AI处理异步进行，优先展示列表
