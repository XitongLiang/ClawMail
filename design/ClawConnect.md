**任务**: 为 ClawMail 添加本地 HTTP REST API 服务，让外部 AI 助手能远程控制邮件操作。

**项目路径**: `C:\Users\a\Desktop\projectA\clawmail`

**需求**:

1. **创建 API 模块** `clawmail/api/server.py`:
- 使用 **FastAPI** 或 **Flask** 创建 HTTP 服务
- 监听 `127.0.0.1:9999`（仅本地，安全）
- 支持 CORS（方便调试）

2. **实现以下接口**:

```python
# POST /compose - 打开写邮件窗口
{
"to": "client@example.com", # 可选
"cc": ["cc@example.com"], # 可选
"subject": "邮件主题", # 可选
"body": "邮件正文", # 可选
"draft": false # 是否只保存草稿，默认 false
}
# 返回: {"success": true, "window_id": "xxx"}

# POST /search - 搜索邮件
{
"query": "关键词",
"folder": "INBOX", # 可选
"limit": 50 # 可选
}
# 返回: {"emails": [...]}

# GET /stats - 获取邮箱统计
# 返回: {"total": 100, "unread": 10, ...}

# POST /mark - 标记邮件
{
"email_id": "xxx",
"read": true, # 可选
"flag": true, # 可选
"pin": true # 可选
}
```

3. **集成到主应用**:
- 在 `main.py` 中启动 API 服务（后台线程或异步）
- 确保 Qt 界面和 API 能通信（用信号/槽或队列）
- API 能调用 `ComposeDialog` 打开写邮件窗口

4. **安全考虑**:
- 只监听 `127.0.0.1`，拒绝外部连接
- 可选：加简单 token 验证（从 `config.json` 读取）

5. **依赖**:
- 添加到 `requirements.txt`: `fastapi`, `uvicorn`

**参考代码**:
- 写邮件窗口: `clawmail/ui/components/compose_dialog.py`
- 数据库操作: `clawmail/infrastructure/database/storage_manager.py`
- 主入口: `main.py`

**输出**:
- 创建 `clawmail/api/server.py`
- 修改 `main.py` 启动 API
- 更新 `requirements.txt`
- 提供测试命令（用 curl 或 Python 测试）





**任务**: 为 ClawMail API 添加待办任务（Tasks）管理接口

**项目路径**: `C:\Users\a\Desktop\projectA\clawmail`

**前提**: API 服务已实现（`clawmail/api/server.py`），运行在 `127.0.0.1:9999`

**需求**:

在现有 API 基础上，添加以下任务管理接口：

```python
# GET /tasks - 获取任务列表
# 支持查询参数: ?status=pending&priority=high&limit=50
# 返回: {"tasks": [{"id": "xxx", "title": "...", "status": "...", "priority": "...", "due_date": "...", ...}]}

# GET /tasks/{id} - 获取单个任务详情
# 返回: {"id": "xxx", "title": "...", ...}

# POST /tasks - 创建新任务
{
"title": "任务标题", # 必填
"description": "详细描述", # 可选
"priority": "high", # 可选: high/medium/low/none, 默认 medium
"due_date": "2026-03-01", # 可选: ISO 格式日期
"source_email_id": "xxx", # 可选: 关联的邮件ID
"status": "pending" # 可选: pending/in_progress/snoozed/completed/cancelled/rejected/archived, 默认 pending
}
# 返回: {"success": true, "task_id": "xxx"}

# PUT /tasks/{id} - 更新任务
{
"title": "新标题", # 可选
"status": "completed", # 可选
"priority": "low", # 可选
"due_date": "2026-04-01", # 可选
"description": "更新描述" # 可选
}
# 返回: {"success": true}

# DELETE /tasks/{id} - 删除任务
# 返回: {"success": true}

# POST /tasks/{id}/complete - 标记任务完成（快捷接口）
# 返回: {"success": true}

# POST /tasks/{id}/snooze - 推迟任务（快捷接口）
{
"until": "2026-03-15" # 推迟到日期
}
# 返回: {"success": true}
```

**要求**:

1. **使用现有的数据库操作**
- 参考: `clawmail/infrastructure/database/storage_manager.py`
- 已有方法: `create_task()`, `get_tasks()`, `update_task_status()`, `_row_to_task()`

2. **数据结构**:
- 参考 `clawmail/domain/models/task.py` 的 `Task` 模型
- 字段: id, title, description, status, priority, due_date, source_email_id, source_type, is_flagged, ...

3. **安全考虑**:
- 保持只监听 `127.0.0.1`
- 输入验证（防止 SQL 注入、非法状态值等）

4. **错误处理**:
- 任务不存在返回 404
- 参数错误返回 400
- 成功返回 200/201

**输出**:
- 修改 `clawmail/api/server.py` 添加新接口
- 提供测试命令（curl 或 Python 示例）

**测试示例**:
```bash
# 获取任务列表
curl http://127.0.0.1:9999/tasks

# 创建任务
curl -X POST http://127.0.0.1:9999/tasks \
-H "Content-Type: application/json" \
-d '{"title": "测试任务", "priority": "high"}'

# 标记完成
curl -X POST http://127.0.0.1:9999/tasks/xxx/complete
```






## Prompt for Claude Code

**任务**: 为 ClawMail 添加 UI 控制接口，让外部 AI 助手能触发界面操作

**项目路径**: `C:\Users\a\Desktop\projectA\clawmail`

**前提**: API 服务已运行（`clawmail/api/server.py`），地址 `127.0.0.1:9999`

**需求**:

添加以下 UI 控制接口：

```python
# POST /ui/refresh-tasks
# 触发待办列表刷新
# 返回: {"success": true}

# POST /ui/refresh-emails
# 触发邮件列表刷新
# 返回: {"success": true}

# POST /ui/focus-compose
# 聚焦到写邮件窗口（如果已打开）
# 返回: {"success": true}

# POST /ui/click-button
{
"button_id": "refresh_tasks", # 按钮标识
"window": "main" # 可选: main/compose/task_dialog
}
# 返回: {"success": true}
```

**实现要求**:

1. **使用 Qt 信号/槽机制**:
- 在 `ClawMailApp` 中定义信号如 `refresh_tasks_requested`
- API 接收到请求后发射信号
- UI 组件连接信号执行实际刷新操作

2. **参考代码**:
- 主窗口: `clawmail/ui/app.py` - `ClawMailApp` 类
- 任务列表: 找 `tasks_list` 或类似组件的 `refresh()` 方法
- 信号定义示例:
```python
from PyQt6.QtCore import pyqtSignal

class ClawMailApp:
refresh_tasks_requested = pyqtSignal()
refresh_emails_requested = pyqtSignal()
```

3. **安全考虑**:
- 只接受 `127.0.0.1` 请求
- 只暴露安全的 UI 操作（刷新、聚焦等）
- 不暴露危险操作（删除、关闭等）

4. **实现步骤**:
- 在 `ClawMailApp.__init__` 中定义信号
- 连接信号到实际刷新方法
- 在 `api/server.py` 中添加路由
- 通过某种方式让 API 能访问到 `ClawMailApp` 实例（如全局变量、信号总线等）

**输出**:
- 修改 `clawmail/ui/app.py` 添加信号和连接
- 修改 `clawmail/api/server.py` 添加 UI 控制路由
- 提供测试命令

**测试示例**:
```bash
# 刷新待办列表
curl -X POST http://127.0.0.1:9999/ui/refresh-tasks

# 刷新邮件列表
curl -X POST http://127.0.0.1:9999/ui/refresh-emails
```

---

**提示**: 如果 API 和 UI 在不同线程，记得用信号槽线程安全通信，不要直接操作 UI。






**任务**: 修复 API 任务创建接口，确保 `category` 字段能正确保存到数据库

**项目路径**: `C:\Users\a\Desktop\projectA\clawmail`

**问题描述**:
- 调用 `POST /tasks` 传入 `category` 字段
- API 返回成功，但数据库中 `category` 为 `null`
- 需要让 category 字段正确保存

**检查点**:

1. **API 路由** (`clawmail/api/server.py`):
- 检查 `POST /tasks` 路由是否从请求中读取了 `category`
- 检查是否将 `category` 传递给 `create_task()`

2. **数据库方法** (`clawmail/infrastructure/database/storage_manager.py`):
- 检查 `create_task()` 方法是否接受 `category` 参数
- 检查 SQL 插入语句是否包含 `category` 字段
- 检查 `_row_to_task()` 是否正确读取 `category`

3. **数据模型** (`clawmail/domain/models/task.py`):
- 检查 `Task` dataclass 是否有 `category` 字段

**修复要求**:

- 确保请求中的 `category` 值能完整传递到数据库
- 支持分类: `工作`, `生活`, `学习`, `个人`, `其他`
- 如果请求没传 category，默认为 `null` 或 `其他`

**测试验证**:

创建任务后，通过 `GET /tasks` 验证 category 是否正确返回：

```bash
curl -X POST http://127.0.0.1:9999/tasks \
-H "Content-Type: application/json" \
-d '{"title": "测试", "category": "个人"}'

curl http://127.0.0.1:9999/tasks
# 应该能看到 category: "个人"
```

**输出**:
- 修改涉及的文件
- 说明修复了什么问题
- 提供测试命令

---





17:08

子代理还在找文件路径。这是给 **Claude Code** 的完整 prompt，你可以直接复制使用：

---

## Prompt for Claude Code

**任务**: 为 ClawMail API 添加回复邮件功能，支持查看原邮件和 AI 辅助

**项目路径**: `C:\Users\a\Desktop\projectA\clawmail`

**现有功能**: API 已运行 (`clawmail/api/server.py`)，有 `POST /compose` 接口

**新增需求**:

### 1. 新增接口 `POST /reply`

```python
# POST /reply - 回复指定邮件
{
"email_id": "xxx", # 原邮件ID（必填）
"reply_all": false, # 是否回复所有人，默认 false
"initial_body": "..." # 预填充的回复内容（可选）
}
# 返回: {"success": true, "window_id": "reply"}
```

### 2. 实现要求

**使用 ComposeDialog 的回复模式**:
- 文件: `clawmail/ui/components/compose_dialog.py`
- 关键参数:
- `source_email` - 原邮件对象（用于引用原文）
- `ai_metadata` - AI 元数据（用于显示建议回复）
- `ai_processor` - AI 处理器实例
- `initial_html_quote` - 引用原文的 HTML

**实现步骤**:

1. API 路由接收 `email_id`
2. 从数据库获取：
- 原邮件 (`db.get_email(email_id)`)
- AI 元数据 (`db.get_email_ai_metadata(email_id)`)
3. 构造引用原文的 HTML
4. 打开 ComposeDialog 的回复模式（参考 `app.py` 中如何调用）
5. 如果提供了 `initial_body`，预填充到正文

### 3. 与现有 /compose 的区别

| 功能 | /compose | /reply |
|------|----------|--------|
| 用途 | 新建邮件 | 回复邮件 |
| source_email | None | 原邮件对象 |
| 收件人 | 空白 | 自动填原邮件发件人 |
| 主题 | 空白 | 自动加 "Re: " |
| 引用原文 | 无 | 自动引用 |
| AI 辅助 | 无 | 显示建议回复面板 |

### 4. 需要修改的文件

- `clawmail/api/server.py` - 添加 `/reply` 路由
- 可能需要修改 `clawmail/ui/app.py` - 确保 API 能调用 ComposeDialog

### 5. 测试命令

```bash
# 回复指定邮件（从邮件列表里找一个 ID 测试）
curl -X POST http://127.0.0.1:9999/reply \
-H "Content-Type: application/json" \
-d '{"email_id": "43d08724-bba0-4151-879b-b0f268a31318", "initial_body": "我会准时参加"}'
```

**期望效果**:
- 打开回复窗口
- 能看到原邮件内容（底部引用）
- 能看到 AI 辅助面板（建议回复、邮件摘要等）
- 正文已预填充 "我会准时参加"






**任务**: 为 ClawMail 添加待办追溯功能，实现双击待办打开源邮件，以及邮件页面 AI 待办一键添加

**项目路径**: `C:\Users\a\Desktop\projectA\clawmail`

### 功能 1: 待办列表双击追溯

**修改文件**: `clawmail/ui/app.py` 或待办列表组件

**需求**:
- 待办列表（Tasks 面板）支持**双击**事件
- 双击时，如果该待办有 `source_email_id`，打开对应的邮件详情
- 如果没有 `source_email_id`，显示提示"无关联邮件"

**实现参考**:
```python
# 在任务列表组件中
def on_task_double_clicked(self, task_id):
task = db.get_task(task_id)
if task.source_email_id:
# 打开邮件详情视图，定位到该邮件
self.show_email_detail(task.source_email_id)
else:
QMessageBox.information(self, "提示", "该待办无关联邮件")
```

---

### 功能 2: 邮件页面 AI 待办一键添加

**修改文件**: `clawmail/ui/app.py` (邮件详情面板)

**需求**:
- 在邮件详情页（阅读邮件时），如果 AI 检测到该邮件包含待办事项
- 在 AI 面板中显示提取出的待办列表
- 每个待办后面有**"加入待办"**按钮
- 点击后直接创建任务，并关联该邮件 ID

**UI 布局参考**:
```
┌─ AI 智能分析 ──────────────┐
│ 摘要: xxx │
│ 分类: 工作 │
│ 检测到的待办: │
│ • "周五前提交报告" [加入待办] │
│ • "回复客户确认" [加入待办] │
└───────────────────────────┘
```

**实现参考**:
```python
# 在邮件详情面板中添加
class EmailDetailPanel(QWidget):
def show_ai_action_items(self, email_id, action_items):
# action_items 来自 AI 分析结果
for item in action_items:
row = QHBoxLayout()
label = QLabel(item['text'])
btn = QPushButton("加入待办")
btn.clicked.connect(lambda: self.add_task_from_email(email_id, item))
row.addWidget(label)
row.addWidget(btn)
self.ai_panel.addLayout(row)

def add_task_from_email(self, email_id, item):
# 调用 API 创建待办
task_data = {
'title': item['text'],
'source_email_id': email_id,
'priority': item.get('priority', 'medium'),
'due_date': item.get('deadline'),
'category': self.infer_category(item)
}
# POST /tasks
```

---

### 功能 3: API 增强（可选）

**修改文件**: `clawmail/api/server.py`

**新增接口**:
```python
# GET /tasks/{id}/email
# 返回该待办关联的邮件详情
# 用于前端快速获取源邮件

@app.get("/tasks/{task_id}/email")
def get_task_source_email(task_id: str):
task = db.get_task(task_id)
if not task or not task.source_email_id:
return {"error": "No source email"}, 404
email = db.get_email(task.source_email_id)
return {"email": email_to_dict(email)}
```

---

### 测试验证

1. **双击追溯**:
- 在待办列表创建一个带 `source_email_id` 的任务
- 双击该任务，应打开对应邮件详情

2. **AI 待办按钮**:
- 打开一封包含行动项的邮件（如 "周五前提交报告"）
- 在 AI 面板应看到待办列表和"加入待办"按钮
- 点击后任务列表增加该待办，且双击可跳回邮件

---

### 输出

- 修改涉及的文件列表
- 新增/修改的代码说明
- 测试步骤

---








**任务**: 为 ClawMail API 添加打开邮件详情视图的接口

**项目路径**: `C:\Users\a\Desktop\projectA\clawmail`

**新增接口**:

```python
# POST /ui/open-email - 打开指定邮件的详情视图
{
"email_id": "xxx" # 邮件ID（必填）
}
# 返回: {"success": true, "window": "email_detail"}
```

**实现要求**:

1. **在主窗口中打开邮件详情**:
- 文件: `clawmail/ui/app.py` - `ClawMailApp` 类
- 调用现有的邮件详情展示方法（如 `show_email_detail()` 或类似）
- 如果邮件列表中有该邮件，自动选中并显示详情
- 如果邮件在别的文件夹，自动切换文件夹并定位

2. **实现步骤**:
- API 路由接收 `email_id`
- 从数据库获取邮件信息（确认存在）
- 通过信号/槽机制通知主窗口打开该邮件
- 主窗口切换到邮件详情视图，显示邮件内容、AI 分析等

3. **参考代码**:
```python
# 在 app.py 中已有的类似功能
def show_email_detail(self, email_id):
# 定位邮件
# 切换到详情视图
# 显示邮件内容、AI 元数据等
```

4. **与现有功能的整合**:
- 复用现有的邮件详情展示逻辑
- 确保 AI 面板也能正常显示（摘要、分类、建议回复等）
- 支持所有邮件操作（回复、转发、标记等）

**测试命令**:
```bash
curl -X POST http://127.0.0.1:9999/ui/open-email \
-H "Content-Type: application/json" \
-d '{"email_id": "98b22e1c-2e8a-488f-bf45-d85c04f7f034"}'
```

**期望效果**:
- ClawMail 窗口自动切换到该邮件的详情视图
- 显示邮件正文、发件人、时间等
- 显示 AI 分析面板（摘要、分类、建议回复）
- 可以进行回复、转发等操作

**输出**:
- 修改的文件列表
- 测试步骤

---








**Claude Code Prompt:**

```markdown
# 任务：为 ClawMail 添加直接发送邮件的 API 端点

## 背景
ClawMail 目前有一个 `/reply` API 可以打开回复窗口，但需要用户手动点击发送。
现在需要添加一个新的 API 端点 `/send-reply`，可以直接发送回复邮件而不打开 UI。

## 项目位置
C:\Users\a\Desktop\projectA\clawmail

## 数据库位置
C:\Users\a\clawmail_data\clawmail.db

## 现有代码参考
- API 服务器：clawmail/api/server.py
- SMTP 客户端：clawmail/infrastructure/email_clients/smtp_client.py

## 需要实现的功能

### 1. 新增 API 端点：POST /send-reply

请求体：
```json
{
"email_id": "string", // 原邮件ID（必填）
"reply_body": "string", // 回复内容（必填）
"reply_all": false, // 是否回复所有人，默认 false
"subject_override": "string" // 可选，自定义主题（默认自动添加 Re:）
}
```

响应：
```json
{
"success": true,
"message_id": "string", // 发送后的 Message-ID
"sent_at": "2026-02-25T..."
}
```

### 2. 实现细节

- 从数据库获取原邮件信息（收件人、主题等）
- 自动构建回复主题（添加 Re: 前缀）
- 构建引用原文的邮件正文
- 获取账户的 SMTP 凭证（需要实现从安全存储获取密码）
- 使用现有的 ClawSMTPClient 发送邮件
- 发送成功后，更新原邮件的 reply_status

### 3. SMTP 凭证获取

查看 _window._cred 或类似机制来获取账户密码。如果需要在 API 层独立运行，可能需要：
- 添加 credentials manager 的引用
- 或者临时允许传入密码（不推荐长期使用）

### 4. 安全考虑

- 需要验证 email_id 存在
- 需要确保账户已配置 SMTP
- 添加适当的错误处理和日志

## 测试方式

发送测试请求：
```bash
curl -X POST http://127.0.0.1:9999/send-reply \
-H "Content-Type: application/json" \
-d '{
"email_id": "a2abb51d-d52e-47de-86fc-1c9ea0101e25",
"reply_body": "测试回复内容",
"reply_all": false
}'
```

## 其他要求

1. 参考现有的 `/reply` 端点实现，复用其逻辑
2. 保持代码风格一致
3. 添加适当的错误处理和 HTTP 状态码
4. 更新 test_reply_api.md 文档，添加新接口说明

请实现这个功能，并确保可以正常发送邮件。
```









## 任务目标
为 ClawMail 添加两个新的 API 端点，支持 AI 助手自动处理待办任务并发送邮件。

## 项目路径
`C:\Users\a\Desktop\projectA\clawmail`

## 现有代码参考
- API 服务器：`clawmail/api/server.py`
- SMTP 客户端：`clawmail/infrastructure/email_clients/smtp_client.py`
- 凭据管理：`clawmail/infrastructure/security/credential_manager.py`

---

## 需要实现的端点

### 1. POST /send-reply

**功能**：直接发送回复邮件，不打开 UI 撰写窗口。

**请求体模型**：
```python
class SendReplyRequest(BaseModel):
    email_id: str                    # 原邮件ID（必填）
    reply_body: str                  # 回复正文（必填）
    reply_all: bool = False          # 是否回复所有人，默认 false
    subject_override: Optional[str] = None  # 可选，自定义主题
```

**实现逻辑**：
1. 验证 `email_id` 存在，获取原邮件
2. 获取账户信息（第一个账户即可）
3. 使用 `CredentialManager` 解密密码
4. 构建回复主题：
   - 如果原主题不以 "Re:" 开头，添加 "Re: " 前缀
   - 如果提供了 `subject_override`，使用自定义主题
5. 构建收件人列表：
   - 从原邮件 `from_address` 获取发件人邮箱
   - 如果 `reply_all=True`，添加原邮件的 `to_addresses` 和 `cc_addresses`（排除自己）
6. 构建引用原文的 HTML（参考现有的 `_build_reply_quote` 函数）
7. 使用 `ClawSMTPClient.send_email()` 发送邮件
8. 发送成功后更新原邮件的 `reply_status = 'replied'`
9. 返回发送结果

**响应模型**：
```python
{
    "success": true,
    "message_id": "生成的Message-ID",
    "sent_at": "2026-02-25T10:30:00Z"
}

# 或错误时
{
    "success": false,
    "error": "错误信息"
}
```

**错误处理**：
- 404: Email not found
- 400: No account configured / Missing required fields
- 500: SMTP send failed

---

### 2. POST /ui/confirm-dialog

**功能**：显示确认弹窗，让用户选择如何处理 AI 待办任务。

**请求体模型**：
```python
class ConfirmDialogOption(BaseModel):
    id: str          # 选项标识符
    label: str       # 显示文本

class ConfirmDialogRequest(BaseModel):
    title: str                           # 弹窗标题
    message: str                         # 弹窗内容（支持换行）
    options: List[ConfirmDialogOption]   # 选项列表（2-4个选项）
    default_option_id: Optional[str] = None  # 默认选中项
    timeout_seconds: int = 60            # 超时时间，默认60秒
```

**实现逻辑**：
1. 创建一个新的 Qt 对话框窗口（类似 ComposeDialog）
2. 显示标题和内容
3. 根据 `options` 动态生成按钮
4. 等待用户点击或超时
5. 关闭窗口并返回结果

**UI 设计建议**：
```
+------------------------------------------+
|  AI待办处理确认                    [X]  |
+------------------------------------------+
|                                          |
|  发现待办任务：确认会议时间              |
|                                          |
|  关联邮件：Xitong确认明天下午可参会      |
|                                          |
|  建议操作：回复邮件确认 14:00-15:00      |
|                                          |
+------------------------------------------+
|  [回复 14:00-15:00]  [询问对方]  [取消] |
+------------------------------------------+
```

**响应模型**：
```python
# 用户选择时
{
    "success": true,
    "selected_option_id": "reply_14_15",
    "confirmed_at": "2026-02-25T10:30:00Z"
}

# 超时时
{
    "success": false,
    "error": "timeout",
    "selected_option_id": null
}

# 用户关闭窗口时
{
    "success": false,
    "error": "cancelled",
    "selected_option_id": null
}
```

**实现细节**：
- 使用 `QDialog` 或自定义窗口
- 使用 `QTimer` 处理超时
- 使用 `QEventLoop` 或回调等待用户响应
- 确保在等待期间不阻塞其他 API 请求

---

## 文件修改清单

### 1. `clawmail/api/server.py`

添加新的 Pydantic 模型：
```python
class SendReplyRequest(BaseModel):
    ...

class ConfirmDialogOption(BaseModel):
    ...

class ConfirmDialogRequest(BaseModel):
    ...
```

添加新的端点：
```python
@app.post("/send-reply")
async def send_reply(req: SendReplyRequest):
    ...

@app.post("/ui/confirm-dialog")
async def confirm_dialog(req: ConfirmDialogRequest):
    ...
```

### 2. 可能需要的新文件

如果确认对话框逻辑复杂，可以创建：
`clawmail/ui/components/confirm_dialog.py`

参考现有的 `compose_dialog.py` 实现。

---

## 测试命令

### 测试 /send-reply
```bash
curl -X POST http://127.0.0.1:9999/send-reply \
  -H "Content-Type: application/json" \
  -d '{
    "email_id": "a2abb51d-d52e-47de-86fc-1c9ea0101e25",
    "reply_body": "Xitong，\n\n好的，那我们定在明天下午14:00-15:00开会。\n\n会议室我会提前预订，到时候见！\n\n谢谢，\nTony",
    "reply_all": false
  }'
```

### 测试 /ui/confirm-dialog
```bash
curl -X POST http://127.0.0.1:9999/ui/confirm-dialog \
  -H "Content-Type: application/json" \
  -d '{
    "title": "AI待办处理确认",
    "message": "发现待办任务：确认会议时间\n关联邮件：Xitong确认明天下午可参会\n\n建议操作：回复邮件确认 14:00-15:00",
    "options": [
      {"id": "reply_14_15", "label": "回复 14:00-15:00"},
      {"id": "ask_time", "label": "询问对方具体时间"},
      {"id": "cancel", "label": "暂不处理"}
    ],
    "default_option_id": "reply_14_15",
    "timeout_seconds": 60
  }'
```

---

## 使用场景示例

当 AI 检测到带有【待办任务执行请求】的任务时：

```python
# 1. 分析任务和关联邮件
# 2. 调用确认弹窗让用户选择
response = requests.post("http://127.0.0.1:9999/ui/confirm-dialog", json={
    "title": "AI待办处理确认",
    "message": "任务：确认明天下午会议时间\n\n检测到关联邮件：Xitong确认可参会\n\n建议：回复确认 14:00-15:00",
    "options": [
        {"id": "send", "label": "发送确认 14:00-15:00"},
        {"id": "custom", "label": "自定义时间"},
        {"id": "skip", "label": "跳过"}
    ]
})

# 3. 根据用户选择执行
if response.json()["selected_option_id"] == "send":
    requests.post("http://127.0.0.1:9999/send-reply", json={
        "email_id": "xxx",
        "reply_body": "..."
    })
    requests.post(f"http://127.0.0.1:9999/tasks/{task_id}/complete")
```

---

## 文档更新

更新 `test_reply_api.md`，添加新接口的说明和测试用例。

---

请实现以上两个 API 端点，确保：
1. 代码风格与现有代码一致
2. 有适当的错误处理和日志
3. 测试命令可以正常工作
4. 更新相关文档












## Prompt 包含的内容

### 需要修改的文件

| 文件 | 修改内容 |
|------|---------|
| `server.py` | `ComposeRequest` 添加 `attachments` 字段 |
| `server.py` | `/compose` 端点传递附件列表 |
| `compose_dialog.py` | 添加 `initial_attachments` 参数 |
| `compose_dialog.py` | 自动加载附件到 UI |
| `test_reply_api.md` | 添加附件上传示例 |

### 核心代码示例

**API 调用：**
```bash
curl -X POST http://127.0.0.1:9999/compose \
-H "Content-Type: application/json" \
-d '{
"to": "cayley.demo4@outlook.com",
"subject": "带附件的邮件",
"body": "请查收附件",
"attachments": [
"C:\\Users\\a\\Desktop\\skills.zip"
]
}'
```

### 可选增强
- ✅ 文件大小检查（25MB 限制）
- ✅ 文件存在验证
- ✅ 附件数量限制

---

**使用方法：**

1. 在 VS Code 中打开 ClawMail 项目
2. 启动 Claude Code
3. 把 prompt 文件内容复制粘贴给 Claude Code
4. 它会帮你实现附件上传功能

