# 偏好提取规则

## 目标

分析用户对 AI 预测的修正行为，推断用户的真实偏好，生成记忆条目。

## 分析框架

### importance_score 修正
- 对比 original_score 和 user_score
- 考虑邮件的发件人、主题、类型
- 推断：用户觉得该类邮件应该更重要/不重要
- 记忆粒度：sender 级别 > domain 级别 > 全局

### summary_rating 差评
- 分析用户评价（太长/太短/遗漏重点/语气不对）
- 推断：用户偏好的摘要风格
- 记忆粒度：全局（摘要偏好通常是全局的）

### reply_edit 编辑
- 对比 AI 草稿和用户编辑版本
- 分析差异：语气变化、长度变化、内容增删
- 推断：用户的回复风格偏好
- 记忆粒度：sender 级别（对不同人可能不同）> 全局

### category_change 修改
- 对比原始分类和用户修改后的分类
- 推断：用户的分类偏好
- 记忆粒度：sender/domain 级别 > 全局

## 输出格式

```json
{
    "memory_type": "email_analysis",
    "memory_key": "sender@example.com",
    "memory_content": {
        "preference": "该发件人邮件的重要性应评为70+，因为是直属上司",
        "source_type": "importance_correction",
        "original_value": 45,
        "corrected_value": 80
    },
    "confidence_score": 0.85,
    "evidence_count": 1
}
```

## 注意事项

- 单次修正的 confidence 上限为 0.85（不是绝对确定）
- 如果已有同 key 的记忆，evidence_count 应 +1，confidence 应提升
- 避免过度泛化：用户修改一封邮件的评分，不代表所有邮件都要改
- 如果修正幅度很小（如评分差 5 分以内），可以 skip
