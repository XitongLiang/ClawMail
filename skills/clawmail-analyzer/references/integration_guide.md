# ClawMail 集成指南

本文档说明 ClawMail 如何调用和使用 clawmail-analyzer Skill。

---

## 集成架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   ClawMail  │────▶│    Skill    │────▶│   ai_processor │
│   后端       │     │  (analyze)  │     │   / LLM       │
└─────────────┘     └─────────────┘     └─────────────┘
       │                                         │
       │                                         │
       └────────────◄────────────────────────────┘
                    JSON 响应
```

---

## 调用方式

### 方式1: 直接脚本调用（推荐后端使用）

```python
import subprocess
import json

def analyze_email(email_data: dict, account_id: str) -> dict:
    '''调用 Skill 分析邮件'''
    
    # 构建输入
    input_data = {
        "email": email_data,
        "context": {
            "account_id": account_id,
            "memory_enabled": True
        },
        "options": {
            "output_format": "standard"
        }
    }
    
    # 调用脚本
    result = subprocess.run(
        ["python", "skills/clawmail-analyzer/scripts/analyze_email.py"],
        input=json.dumps(input_data),
        capture_output=True,
        text=True,
        timeout=120
    )
    
    # 解析结果
    response = json.loads(result.stdout)
    
    if response["status"] == "error":
        # 使用 fallback 数据
        return response["fallback"]
    
    return response["data"]
```

### 方式2: Python 模块导入

```python
import sys
sys.path.insert(0, "skills/clawmail-analyzer/scripts")

from analyze_email import analyze_email, create_success_response

result = analyze_email(email_data, context, options)
```

### 方式3: 用户命令触发（前端/聊天）

用户在 OpenClaw 聊天中发送：

```
(ClawMail)分析邮件 email_123
```

OpenClaw 自动触发 Skill，调用相应脚本。

---

## 数据流转

### 输入数据准备

ClawMail 需要准备以下数据：

```python
email_data = {
    "id": email.id,
    "subject": email.subject,
    "from_address": {
        "name": email.from_name,
        "email": email.from_email
    },
    "to_addresses": email.to_list,
    "cc_addresses": email.cc_list,
    "received_at": email.received_at.isoformat(),
    "body_text": email.body_text[:4000],  # 截断过长正文
    "body_html": email.body_html,  # 可选
    "attachments": [
        {"filename": att.filename, "size": att.size}
        for att in email.attachments
    ]
}

context = {
    "account_id": user.account_id,
    "user_preferences": {
        "timezone": user.timezone,
        "language": user.language
    },
    "memory_enabled": user.ai_settings.get("memory_enabled", True)
}
```

### 输出数据处理

```python
response = analyze_email(email_data, context)

# 存储到 EmailAIMetadata
email.ai_metadata = EmailAIMetadata(
    email_id=email.id,
    summary=response["summary"],
    categories=response["metadata"]["category"],
    sentiment=response["metadata"]["sentiment"],
    suggested_reply=response["metadata"].get("suggested_reply"),
    is_spam=response["metadata"]["is_spam"],
    action_items=response["action_items"],
    reply_stances=response["metadata"].get("reply_stances"),
    importance_score=response["metadata"].get("importance_score"),
    ai_status="processed",
    processing_progress=100,
    processing_stage="completed",
    processed_at=datetime.utcnow()
)
```

---

## 错误处理

### 降级策略

当 Skill 返回错误时，ClawMail 应使用 fallback 数据：

```python
if response["status"] == "error":
    logger.warning(f"邮件分析失败: {response['message']}")
    
    # 使用 fallback 数据
    fallback = response.get("fallback", {})
    
    # 标记为需要人工审核
    email.ai_metadata = EmailAIMetadata(
        email_id=email.id,
        summary=fallback.get("summary", {}),
        categories=["error"],
        sentiment="neutral",
        is_spam=False,
        action_items=[],
        ai_status="failed",
        processing_progress=0,
        processing_stage="failed",
        error_message=response["message"]
    )
```

### 重试机制

对于超时错误，可以重试：

```python
for attempt in range(3):
    try:
        response = analyze_email(email_data, context)
        if response["status"] == "success":
            break
    except subprocess.TimeoutExpired:
        if attempt < 2:
            continue
        raise
```

---

## 批量处理

### 批量分析多封邮件

```python
def batch_analyze(emails: list, account_id: str) -> list:
    '''批量分析邮件'''
    results = []
    
    for email in emails:
        email_data = prepare_email_data(email)
        context = {"account_id": account_id, "memory_enabled": True}
        
        result = analyze_email(email_data, context)
        results.append({
            "email_id": email.id,
            "result": result
        })
    
    return results
```

### 对比分析

```python
# 对比两封邮件优先级
result = subprocess.run(
    ["python", "skills/clawmail-analyzer/scripts/compare_emails.py",
     "--email-ids", f"{email1.id},{email2.id}",
     "--account-id", user.account_id],
    capture_output=True,
    text=True
)

comparison = json.loads(result.stdout)
# 返回优先级排序建议
```

---

## 用户命令处理

### 处理用户命令

在 OpenClaw bridge 中添加命令处理：

```python
# openclawbridge.py

COMMAND_PATTERNS = {
    "analyze_email": r"\(ClawMail\)分析邮件\s+(\w+)",
    "compare_emails": r"\(ClawMail\)对比邮件\s+(\w+)\s+(\w+)",
    "feedback_report": r"\(ClawMail\)查看AI摘要反馈报告",
}

def handle_command(text: str, account_id: str) -> str:
    '''处理用户命令'''
    
    # 分析单封邮件
    if match := re.search(COMMAND_PATTERNS["analyze_email"], text):
        email_id = match.group(1)
        return analyze_single_email(email_id, account_id)
    
    # 对比邮件
    if match := re.search(COMMAND_PATTERNS["compare_emails"], text):
        id1, id2 = match.group(1), match.group(2)
        return compare_emails(id1, id2, account_id)
    
    # 反馈报告
    if re.search(COMMAND_PATTERNS["feedback_report"], text):
        return generate_feedback_report(account_id)
    
    return None
```

---

## 配置

### Skill 配置项

在 ClawMail 配置中添加：

```yaml
# config.yaml
ai:
  skill_path: "skills/clawmail-analyzer"
  memory_enabled: true
  timeout_seconds: 60
  max_retries: 3
  fallback_enabled: true
```

### 环境变量

```bash
# .env
CLAWMAIL_SKILL_PATH=skills/clawmail-analyzer
CLAWMAIL_AI_TIMEOUT=60
CLAWMAIL_AI_MAX_RETRIES=3
```

---

## 调试

### 日志记录

```python
import logging

logger = logging.getLogger("clawmail.skill")

def analyze_with_logging(email_data, context):
    logger.info(f"开始分析邮件: {email_data['id']}")
    
    start_time = time.time()
    result = analyze_email(email_data, context)
    duration = time.time() - start_time
    
    logger.info(f"邮件分析完成: {email_data['id']}, 耗时: {duration:.2f}s")
    
    if result["status"] == "error":
        logger.error(f"分析失败: {result['message']}")
    
    return result
```

### 测试脚本

```bash
# 测试单封邮件分析
python skills/clawmail-analyzer/scripts/analyze_email.py \
  --input test_email.json \
  --output result.json

# 测试对比分析
python skills/clawmail-analyzer/scripts/compare_emails.py \
  --email-ids email_1,email_2 \
  --account-id test_user

# 测试反馈报告
python skills/clawmail-analyzer/scripts/feedback_report.py \
  --account-id test_user \
  --format text
```

---

## 注意事项

1. **超时处理**: 设置合理的超时时间（建议60秒），避免阻塞
2. **内存管理**: 长邮件正文应截断，避免超出 LLM 上下文限制
3. **错误降级**: 始终使用 fallback 数据，确保用户体验
4. **记忆隔离**: 不同 account_id 的记忆应严格隔离
5. **版本兼容**: Skill 输出版本应与 ClawMail 期望版本匹配
