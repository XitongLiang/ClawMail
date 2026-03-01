# 用户习惯提取规则

## 触发时机

用户发送邮件或回复邮件后，分析用户撰写的内容提取习惯信息。

## 提取类别

### writing_habit（写作习惯）
- 平均邮件长度（简短/中等/详细）
- 是否使用问候语和结束语
- 段落结构偏好
- 列表/编号使用频率
- **fact_key 格式**: habit.email_length, habit.greeting_style, habit.structure

### communication_style（沟通风格）
- 语气（正式/半正式/随意）
- 回复速度模式（哪类邮件回复快）
- 常用表达和句式
- 签名格式
- **fact_key 格式**: style.tone, style.reply_speed, style.signature

## 输出格式

```json
[
    {
        "fact_key": "habit.email_length",
        "fact_category": "writing_habit",
        "fact_content": "偏好简短回复，通常3-5句话",
        "confidence": 0.35
    }
]
```

## 置信度评估

- 单次撰写行为的置信度上限为 0.4
- 需要多次行为累积才能确认习惯
- 与之前行为一致时置信度更高

## 注意事项

- 只分析用户自己撰写的内容，不分析引用的原邮件
- 如果邮件内容太短（少于 20 字），不提取
- 每次最多提取 2 个 facts
- 关注模式而非单次行为：单次用了感叹号不代表习惯
