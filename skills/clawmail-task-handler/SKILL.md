---
name: clawmail-task-handler
description: 自动处理 ClawMail 待办任务。当用户说"处理我的待办"、"帮我回复邮件任务"，或收到 ClawMail 任务触发时激活。核心能力：分析任务真正需要什么信息，主动从 OpenClaw 记忆、本地文件、历史邮件中搜集资料，组成完整的真实邮件，经用户确认后发送。
---

# ClawMail Task Handler

自动处理 ClawMail 中的待办任务——不是显示模板选项，而是**真正完成任务**。

## 核心原则

- **理解 > 匹配**：读懂 action_item 需要什么，而不是关键词匹配
- **搜集 > 猜测**：从记忆、文件、邮件历史中找真实信息，不写占位符
- **完整 > 草稿**：发出去的邮件必须是能直接使用的完整内容
- **确认 > 自动**：发送前必须经用户确认

## 触发方式

- 用户说"处理我的待办"/"帮我看看待办任务"/"批量处理任务"
- 用户说"帮我回复那封关于 XX 的邮件"
- ClawMail 发送任务处理请求（带 task_id）

---

## 工作流程

### 第一步：获取待办任务列表

```bash
curl http://127.0.0.1:9999/tasks?status=pending&limit=20
```

或使用 manager 脚本：
```bash
python ~/.openclaw/workspace/skills/clawmail-manager/scripts/list_tasks.py --status pending --json
```

按优先级排序（high → medium → low），逐个处理。

---

### 第二步：深度分析每个任务

对每个任务，依次获取：

```bash
# 任务详情
curl http://127.0.0.1:9999/tasks/{task_id}

# 关联原邮件（含发件人、正文、附件列表）
curl http://127.0.0.1:9999/tasks/{task_id}/email

# AI 分析结果（含 action_items、summary、reply_stances）
curl http://127.0.0.1:9999/emails/{email_id}/ai-metadata
```

从 `action_items` 中提取：
- **需要做什么**：回复/提供文件/确认时间/提交数据/转发资料
- **需要哪些信息**：报价单/简历/项目进度/合同条款/个人背景/数据等
- **截止时间**：是否紧急

---

### 第三步：主动搜集所需资料

根据任务需要的信息，按以下顺序搜集，**直到收集到足够内容**：

#### 1. 搜索 OpenClaw 记忆
```bash
openclaw memory search "<关键词>"
```
用于找：用户偏好、历史决策、联系人信息、项目背景、过去的承诺、写作习惯。

#### 2. 搜索本地文件

```bash
# 按文件名搜索
find ~ -name "*关键词*" -type f 2>/dev/null | head -20

# 按内容搜索
grep -r "关键词" ~/Documents ~/Desktop ~/Downloads 2>/dev/null -l | head -10
```

找到相关文件后，读取其内容提取所需信息。

#### 3. 搜索历史邮件
```bash
python ~/.openclaw/workspace/skills/clawmail-manager/scripts/search_emails.py "关键词" --json
```
找同一发件人的历史往来、同主题的过往讨论。

#### 搜集策略

- 从 action_item 的描述中拆解关键词（项目名、资料类型、人名等）
- 每个关键词依次在记忆 → 本地文件 → 邮件历史搜索
- 如果真的找不到某项信息，**不要写占位符**，在邮件中明确说明"该信息暂时无法确认，稍后补充"

---

### 第四步：调用 clawmail-reply 撰写邮件

**不要自己写邮件**，调用 `clawmail-reply` 的 `generate_reply.py`，它使用经过用户反馈调优的个性化 prompt。

从 action_item 和原邮件中确定：
- **stance**：回复立场，用一句话描述（如 `"提供项目报价，含金额和工期"` / `"发送个人简历"` / `"确认下周三下午3点会议"`）
- **tone**：语气（`professional` / `casual` / `concise`，参考原邮件风格）

将第三步搜集到的所有资料整理为纯文本，作为 `--user-notes` 传入：

```bash
python ~/.openclaw/workspace/skills/clawmail-reply/scripts/generate_reply.py \
  --email-id   {email_id} \
  --account-id {account_id} \
  --stance     "{从 action_item 提炼的回复立场}" \
  --tone       "{professional|casual|concise}" \
  --user-notes "{第三步搜集到的所有资料，拼成纯文本}"
```

`--user-notes` 示例（搜集到报价资料时）：
```
【记忆】项目报价历史：中型项目区间 ¥80,000–¥120,000，工期 3 个月
【文件】~/Documents/报价单2025.xlsx 第3行：XX项目基础版 ¥85,000
【历史邮件】2025-11-20 张三来信提到预算上限 ¥100,000
【附件文件】~/Documents/报价单2025.xlsx（可随邮件发送）
```

脚本输出纯文本邮件正文到 stdout，直接用于下一步发送。

**如果搜集到了附件文件路径**，记录下来，在第六步走 `/compose` 接口而非 `/send-reply`。

---

### 第五步：显示确认弹窗（必须）

**发送前必须显示弹窗**，让用户预览邮件内容：

```bash
curl -X POST http://127.0.0.1:9999/ui/confirm-dialog \
  -H "Content-Type: application/json" \
  -d '{
    "title": "待办处理确认",
    "message": "任务：{task_title}\n发件人：{sender}\n\n邮件预览：\n{email_body_first_300_chars}...",
    "options": [
      {"id": "send",   "label": "✅ 确认发送"},
      {"id": "edit",   "label": "✏️ 打开撰写窗口编辑后发送"},
      {"id": "skip",   "label": "⏭️ 跳过此任务"}
    ],
    "default_option_id": "send",
    "timeout_seconds": 60
  }'
```

弹窗返回 `{"success": true, "selected_option_id": "send"}` 后才能继续。

---

### 第六步：根据用户选择执行

| 用户选择 | 执行操作 |
|---------|---------|
| `send` 确认发送 | POST `/send-reply` 发送 → POST `/tasks/{id}/complete` 标记完成 |
| `edit` 编辑后发送 | POST `/compose` 打开撰写窗口（预填收件人、主题、正文、附件） |
| `skip` 跳过 | 继续处理下一个任务，不标记完成 |

#### 发送回复
```bash
curl -X POST http://127.0.0.1:9999/send-reply \
  -H "Content-Type: application/json" \
  -d '{
    "email_id": "{original_email_id}",
    "reply_body": "{完整邮件正文}",
    "reply_all": false
  }'
```

#### 打开撰写窗口（带附件）
```bash
curl -X POST http://127.0.0.1:9999/compose \
  -H "Content-Type: application/json" \
  -d '{
    "to": "{sender_email}",
    "subject": "Re: {original_subject}",
    "body": "{完整邮件正文}",
    "attachments": ["/path/to/file1.pdf", "/path/to/file2.xlsx"]
  }'
```

#### 标记任务完成
```bash
curl -X POST http://127.0.0.1:9999/tasks/{task_id}/complete
```

---

## 完整示例场景

### 场景 A：对方请求提供项目报价

**任务**：`action_item: 回复报价，提供 XX 项目的开发费用和交付时间`

**搜集过程：**
1. `openclaw memory search "报价 XX项目"` → 找到历史报价区间记录
2. `find ~ -name "*报价*"` → 找到 `~/Documents/报价单2025.xlsx`
3. 读取文件，提取具体金额和工期
4. `openclaw memory search "XX公司 联系人"` → 找到对接人姓名

**发出邮件包含：** 具体金额范围、交付周期、付款方式、联系方式——全来自真实资料

---

### 场景 B：对方询问简历/个人背景

**任务**：`action_item: 发送个人简历给 HR`

**搜集过程：**
1. `openclaw memory search "简历 工作经历 技能"` → 找到职业背景摘要
2. `find ~ -name "*.pdf" | grep -i "简历\|resume\|CV"` → 找到 `~/Documents/简历_2025.pdf`

**发出邮件包含：** 一段个人介绍 + "已附上最新简历（PDF）"，通过 `/compose` 接口携带附件路径

---

### 场景 C：会议时间确认

**任务**：`action_item: 确认下周三下午的会议时间`

**搜集过程：**
1. `openclaw memory search "日程 下周三"` → 确认用户当天是否有冲突
2. 读取原邮件中提到的时间段选项

**发出邮件包含：** 明确的时间确认（或提出替代时间），而非"14:00/15:00/16:00 三选一"模板

---

### 场景 D：需要提供数据或进度

**任务**：`action_item: 向项目组汇报本周进度`

**搜集过程：**
1. `openclaw memory search "项目进度 本周"` → 找到最近记录的进度
2. `grep -r "项目名" ~/Documents/进度报告` → 找到最新进度文档
3. 读取文档内容提取关键数字

**发出邮件包含：** 具体进度百分比、完成的里程碑、下周计划——不是"进度良好"这种空话

---

## API 速查

```
GET  /tasks?status=pending&limit=20      获取待办任务列表
GET  /tasks/{id}                         获取单个任务详情
GET  /tasks/{id}/email                   获取关联原邮件
GET  /emails/{id}/ai-metadata           获取 AI 分析（action_items 在这里）
POST /ui/confirm-dialog                  显示确认弹窗（必须在发送前调用）
POST /send-reply                         发送回复
POST /compose                            打开撰写窗口（支持附件）
POST /tasks/{id}/complete               标记任务完成
```

## 辅助脚本

`scripts/api_utils.py` 提供封装好的 API 调用函数，可直接使用：

```python
from scripts.api_utils import ClawMailAPI
api = ClawMailAPI()

tasks      = api.get_pending_tasks()
task       = api.get_task(task_id)
email      = api.get_task_email(task_id)
metadata   = api.get_ai_metadata(email_id)
result     = api.show_confirm_dialog(title, message, options)
sent       = api.send_reply(email_id, body)
            api.complete_task(task_id)
```
