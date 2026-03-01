# 记忆类型定义

## memory_type 取值

| memory_type | 说明 | 典型 memory_key |
|-------------|------|----------------|
| email_analysis | 邮件分析偏好 | sender_email / domain / null(全局) |
| reply_draft | 回复生成偏好 | sender_email / null(全局) |
| importance | 重要性判断偏好 | sender_email / domain / category |
| summary_style | 摘要风格偏好 | null(全局) |
| category_preference | 分类偏好 | null(全局) |

## memory_content 结构

灵活 JSON，但必须包含：
- `preference`: 文本描述，LLM 可直接理解的偏好说明
- `source_type`: 来源类型（importance_correction / summary_rating / reply_edit / category_change）

可选字段：
- `original_value`: 原始预测值
- `corrected_value`: 用户修正值
- `context`: 额外上下文信息

## memory_key 规则

- 发件人级别：使用完整邮箱地址，如 `zhangsan@company.com`
- 域名级别：使用域名，如 `company.com`
- 全局：使用 `null` 或 `global`
- 分类级别：使用分类名，如 `subscription`
