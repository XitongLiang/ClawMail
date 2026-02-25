# ClawMail API /reply 接口测试指南

## 新增接口

### POST /reply

回复指定邮件，自动填充收件人、主题（Re:）、引用原文，并显示 AI 辅助拟稿面板（如果有 AI 元数据）。

**请求参数：**

```json
{
  "email_id": "xxx",        // 原邮件ID（必填）
  "reply_all": false,       // 是否回复所有人，默认 false
  "initial_body": "..."     // 预填充的回复内容（可选）
}
```

**返回：**

```json
{
  "success": true,
  "window_id": "reply"
}
```

---

## 测试命令

### 1. 基础回复测试

回复指定邮件（只回复发件人）：

```bash
curl -X POST http://127.0.0.1:9999/reply \
  -H "Content-Type: application/json" \
  -d '{"email_id": "your-email-id-here"}'
```

### 2. 回复所有人测试

```bash
curl -X POST http://127.0.0.1:9999/reply \
  -H "Content-Type: application/json" \
  -d '{
    "email_id": "your-email-id-here",
    "reply_all": true
  }'
```

### 3. 预填充回复内容测试

```bash
curl -X POST http://127.0.0.1:9999/reply \
  -H "Content-Type: application/json" \
  -d '{
    "email_id": "your-email-id-here",
    "initial_body": "我会准时参加，谢谢邀请！"
  }'
```

### 4. 完整参数测试

```bash
curl -X POST http://127.0.0.1:9999/reply \
  -H "Content-Type: application/json" \
  -d '{
    "email_id": "your-email-id-here",
    "reply_all": true,
    "initial_body": "收到，我会尽快处理。"
  }'
```

---

## 错误场景测试

### 邮件不存在

```bash
curl -X POST http://127.0.0.1:9999/reply \
  -H "Content-Type: application/json" \
  -d '{"email_id": "non-existent-id"}'
```

**预期返回：** `404 Not Found`

```json
{"detail": "Email not found"}
```

---

## 获取 email_id

使用以下命令获取邮件列表：

```bash
# 搜索邮件
curl -X POST http://127.0.0.1:9999/search \
  -H "Content-Type: application/json" \
  -d '{"query": "", "limit": 10}'

# 或使用 stats 接口查看统计
curl http://127.0.0.1:9999/stats
```

---

## 实现说明

### 与 /compose 的区别

| 特性 | /compose | /reply |
|------|----------|--------|
| 用途 | 新建邮件 | 回复邮件 |
| source_email | None | 原邮件对象 |
| ai_metadata | 无 | 原邮件的 AI 元数据 |
| 收件人 | 手动指定 | 自动提取原邮件发件人 |
| 主题 | 手动指定 | 自动添加 Re: 前缀 |
| 引用原文 | 无 | 自动生成引用块 |
| AI 辅助面板 | 无 | 如有 reply_stances 则显示 |

### ComposeDialog 回复模式参数

```python
ComposeDialog(
    db, cred_manager, account,
    source_email=email_obj,        # 原邮件对象
    ai_metadata=ai_meta,           # AI 元数据（含 reply_stances）
    ai_processor=ai_processor,     # AI 处理器
    initial_html_quote=quote,      # 引用 HTML
    initial_reply_html=reply_html, # 预填充回复内容
    ...
)
```

### AI 辅助功能

- 读取原邮件的 `email_ai_metadata` 表
- 获取 `suggested_reply` 或 `reply_stances`
- 传递给 ComposeDialog 显示 AI 辅助拟稿面板
- 支持选择回复立场和风格，一键生成草稿

---

## 修改的文件

- `clawmail/api/server.py`：添加 `/reply` 路由和相关辅助函数
