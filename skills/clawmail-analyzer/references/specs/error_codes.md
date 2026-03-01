# 错误码定义

本文档定义 ClawMail 邮件分析 Skill 的标准错误码。

---

## 错误响应格式

```json
{
  "status": "error",
  "error_code": "ERROR_CODE",
  "message": "人类可读的错误描述",
  "email_id": "原始邮件ID（如果有）",
  "details": {
    "field": "出错的字段",
    "reason": "具体原因"
  },
  "fallback": {
    "summary": {
      "one_line": "处理失败，请重试",
      "brief": "由于技术原因，无法完成邮件分析。请稍后重试或联系支持。"
    },
    "metadata": {
      "category": ["error"],
      "confidence": 0,
      "is_spam": false
    }
  }
}
```

---

## 错误码列表

### 输入错误 (4xx)

#### INVALID_INPUT (400)
输入数据格式错误或缺少必需字段。

**场景**:
- JSON 解析失败
- 缺少必需字段 (email.id, email.subject, email.body_text)
- 字段类型不匹配
- email_id 格式无效

**示例**:
```json
{
  "error_code": "INVALID_INPUT",
  "message": "缺少必需字段: email.body_text",
  "details": {
    "missing_fields": ["email.body_text"],
    "received_fields": ["email.id", "email.subject"]
  }
}
```

#### INVALID_EMAIL_ID (400)
邮件ID不存在或无法访问。

**场景**:
- 邮件ID在数据库中不存在
- 邮件已被删除
- 无权访问该邮件

---

### 处理错误 (5xx)

#### PROCESSING_FAILED (500)
AI 处理过程中发生错误。

**场景**:
- LLM API 调用失败
- 返回结果解析失败
- 输出验证失败

**示例**:
```json
{
  "error_code": "PROCESSING_FAILED",
  "message": "AI 分析失败: 返回结果格式无效",
  "details": {
    "raw_response": "...",
    "parse_error": "Missing required field: summary.one_line"
  }
}
```

#### MEMORY_ERROR (500)
记忆检索或注入失败。

**场景**:
- Memory Bank 连接失败
- 记忆检索超时
- 记忆格式错误

**行为**:
- 记忆失败不应阻断主流程
- 降级为无记忆模式继续处理
- 在响应中标记 memory.injected = false

#### TIMEOUT (504)
处理超时。

**场景**:
- LLM API 响应超时 (>60s)
- 邮件正文过长导致处理缓慢
- 网络延迟

**建议**:
- 邮件正文超过 8000 字符时自动截断
- 设置超时重试机制

---

### 服务错误 (5xx)

#### SERVICE_UNAVAILABLE (503)
Skill 服务暂时不可用。

**场景**:
- ai_processor 服务未启动
- 数据库连接失败
- 依赖服务故障

#### RATE_LIMITED (429)
请求频率超限。

**场景**:
- LLM API 达到调用限制
- 批量分析请求过多

---

## 降级策略

当发生错误时，Skill 应返回降级结果，确保 ClawMail 可以正常继续。

### 降级数据

```json
{
  "fallback": {
    "summary": {
      "keywords": [],
      "one_line": "处理失败，请重试",
      "brief": "由于技术原因，无法完成邮件分析。请稍后重试或联系支持。",
      "key_points": ["系统暂时无法处理此邮件"]
    },
    "action_items": [],
    "metadata": {
      "category": ["error"],
      "sentiment": "neutral",
      "language": "zh",
      "confidence": 0,
      "is_spam": false,
      "suggested_reply": null,
      "reply_stances": []
    }
  }
}
```

---

## 错误处理流程

```
接收输入
    │
    ▼
验证输入 ──错误──▶ 返回 INVALID_INPUT
    │
    ▼
尝试记忆检索 ──错误──▶ 降级为无记忆模式，记录警告
    │
    ▼
调用 LLM ──超时──▶ 重试1次 ──仍超时──▶ 返回 TIMEOUT
    │
    ▼
解析结果 ──错误──▶ 返回 PROCESSING_FAILED
    │
    ▼
验证输出 ──错误──▶ 补充默认值，记录警告
    │
    ▼
返回成功响应
```

---

## 日志记录

所有错误应记录到日志，包含：
- 时间戳
- 错误码
- email_id（如果有）
- account_id（如果有）
- 错误详情
- 堆栈跟踪（开发环境）

**日志级别**:
- ERROR: PROCESSING_FAILED, SERVICE_UNAVAILABLE
- WARN: MEMORY_ERROR（已降级）
- INFO: INVALID_INPUT（客户端错误）
