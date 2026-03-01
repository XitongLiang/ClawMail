---
name: clawmail-task-handler
description: 自动处理 ClawMail 待办任务，支持会议确认、邮件回复、任务跟进等场景。当检测到【待办任务执行请求】标记的任务时，分析任务内容、显示确认弹窗、执行用户选择的操作，并自动标记任务完成。适用于需要 AI 协助处理邮件相关待办的工作流。
---

# ClawMail Task Handler

自动处理 ClawMail 中需要 AI 协助的待办任务。

## 工作流程

```
1. 检测任务
   └── 查询 status=pending 且标记为 AI 处理的任务
   
2. 分析任务
   └── 读取任务详情 + 关联邮件
   └── 识别任务类型（会议确认/邮件回复/跟进事项等）
   
3. 生成选项
   └── 根据任务类型生成处理选项
   └── 准备回复内容/执行计划
   
4. 【必须】显示确认弹窗  ← 关键步骤
   └── 调用 /ui/confirm-dialog 显示弹窗
   └── 等待用户选择（超时默认第一个选项）
   └── 用户确认后才能继续执行！
   
5. 执行操作
   └── 发送邮件 /send-reply
   └── 或创建新任务 POST /tasks
   └── 或更新现有任务 PUT /tasks/{id}
   
6. 标记完成
   └── 调用 /tasks/{id}/complete
   └── 报告处理结果
```

⚠️ **重要：执行任何操作前，必须先调用 `/ui/confirm-dialog` 弹窗让用户确认！**

## 任务类型识别

### 会议时间确认
**特征：** 标题含"会议"、"时间"、"确认"等关键词
**处理：**
- 提取关联邮件中提到的可用时间
- 生成时间段选项（14:00-15:00 / 15:00-16:00 / 16:00-17:00）
- 用户选择后发送确认邮件

### 邮件回复
**特征：** 标题含"回复"、"RE:"、"跟进"
**处理：**
- 分析邮件内容生成回复草稿
- 提供"发送/编辑/跳过"选项

### 待办跟进
**特征：** 标题含"跟进"、"检查"、"提醒"
**处理：**
- 查询相关状态
- 生成跟进计划

## API 端点使用

### 必需端点

```python
# 1. 获取任务列表
GET /tasks?status=pending&limit=50

# 2. 获取任务详情
GET /tasks/{task_id}

# 3. 获取关联邮件
GET /tasks/{task_id}/email

# 4. 【关键步骤】显示确认弹窗
POST /ui/confirm-dialog
{
  "title": "AI待办处理确认",
  "message": "任务：确认会议时间\n\n建议操作：回复邮件确认 14:00-15:00",
  "options": [
    {"id": "reply_14_15", "label": "回复 14:00-15:00"},
    {"id": "reply_15_16", "label": "回复 15:00-16:00"},
    {"id": "skip", "label": "暂不处理"}
  ],
  "default_option_id": "reply_14_15",
  "timeout_seconds": 60
}
# 返回: {"success": true, "selected_option_id": "reply_14_15"}

# 5. 发送回复邮件
POST /send-reply
{
  "email_id": "原邮件ID",
  "reply_body": "回复内容",
  "reply_all": false
}

# 6. 标记任务完成
POST /tasks/{task_id}/complete

# 7. 【新增】发送带附件的邮件
POST /compose
{
  "to": "recipient@example.com",
  "subject": "带附件的邮件",
  "body": "请查收附件",
  "attachments": [
    "C:\\Users\\a\\Desktop\\skills.zip",
    "C:\\Users\\a\\Documents\\file.pdf"
  ]
}
# 返回: {"success": true, "window_id": "compose"}
# 撰写窗口会自动加载附件
```

### 弹窗调用示例

```python
import requests

# 必须先显示弹窗，等待用户确认
dialog_result = requests.post(
    "http://127.0.0.1:9999/ui/confirm-dialog",
    json={
        "title": "AI待办处理确认",
        "message": f"任务：{task_title}\n\n请选择处理方式：",
        "options": [
            {"id": "option1", "label": "选项1描述"},
            {"id": "option2", "label": "选项2描述"},
            {"id": "skip", "label": "跳过"}
        ],
        "timeout_seconds": 60
    }
).json()

# 检查用户选择
if not dialog_result.get('success'):
    print("用户取消或超时")
    return

selected = dialog_result['selected_option_id']
print(f"用户选择: {selected}")

# 根据选择执行操作...
```

### 发送带附件的邮件

```python
import requests

# 发送带附件的新邮件
resp = requests.post(
    "http://127.0.0.1:9999/compose",
    json={
        "to": "cayley.demo4@outlook.com",
        "subject": "ClawMail Task Handler Skill 分享",
        "body": "附件是我们开发的自动化待办处理工具...",
        "attachments": [
            "C:\\Users\\a\\Desktop\\skills.zip"
        ]
    }
)

result = resp.json()
print(f"撰写窗口已打开，附件已加载: {result}")
```

## 脚本使用

### 处理单个任务

```python
from scripts import task_handler

# 处理指定任务
result = task_handler.process_task(task_id="xxx")
# 返回: {"success": True, "action": "sent_email", "message": "..."}
```

### 批量处理

```python
from scripts import task_handler

# 处理所有待处理的 AI 任务
results = task_handler.process_pending_tasks()
# 返回: [{"task_id": "...", "success": True, "action": "..."}, ...]
```

### 命令行使用

```bash
# 处理指定任务
python scripts/task_handler.py --task-id <task_id>

# 处理所有待处理任务
python scripts/task_handler.py --all-pending

# 测试模式（不实际发送）
python scripts/task_handler.py --task-id <task_id> --dry-run
```

## 错误处理

| 错误场景 | 处理方式 |
|---------|---------|
| 任务无关联邮件 | 显示"无法获取关联邮件"，提供手动输入选项 |
| 弹窗超时 | 默认选择第一个选项，记录日志 |
| 邮件发送失败 | 标记任务为"in_progress"，不标记完成，报告错误 |
| API 不可用 | 重试3次后报错，保留任务状态 |

## 配置参考

参见 [references/task_types.md](references/task_types.md) 了解完整的任务类型定义和处理策略。
