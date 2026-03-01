# 记忆输出格式

## 成功输出

LLM 应返回一个 JSON 对象：

```json
{
    "memory_type": "importance",
    "memory_key": "newsletter@techblog.com",
    "memory_content": {
        "preference": "来自 techblog.com 的订阅邮件重要性应低于20",
        "source_type": "importance_correction",
        "original_value": 45,
        "corrected_value": 15
    },
    "confidence_score": 0.85,
    "evidence_count": 1
}
```

## 跳过输出

如果修正不包含有意义的偏好信号：

```json
{
    "skip": true,
    "reason": "评分差异过小，不构成明确偏好"
}
```

## 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| memory_type | string | 是 | 见 memory_types.md |
| memory_key | string/null | 是 | 记忆粒度标识 |
| memory_content | object | 是 | 必须包含 preference 和 source_type |
| confidence_score | float | 是 | 0.0-1.0，单次修正上限 0.85 |
| evidence_count | int | 是 | 固定为 1（新记忆） |
