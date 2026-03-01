# 反馈系统设计与实现

## 概述

反馈系统允许用户对生成的邮件摘要进行评分和评论，系统根据反馈历史自动调整生成策略，实现持续改进。

## 架构

```
用户反馈
    ↓
feedback_system.py 收集反馈
    ↓
存储到 memory/feedback/summary_feedback.jsonl
    ↓
更新 memory/feedback/summary_stats.json
    ↓
analyze_email.py 读取偏好
    ↓
调整生成参数
    ↓
输出改进后的摘要
```

## 数据存储

### 1. 原始反馈记录 (JSONL)

路径：`~/.openclaw/workspace/memory/feedback/summary_feedback.jsonl`

格式：
```json
{
  "timestamp": "2026-02-26T10:30:00",
  "email_subject": "关于Q4项目的会议邀请",
  "generated_summary": {...},
  "user_rating": 4,
  "user_comment": "摘要很好，但遗漏了截止时间",
  "improvement_areas": ["missing_deadline"],
  "summary_hash": 1234
}
```

### 2. 统计数据 (JSON)

路径：`~/.openclaw/workspace/memory/feedback/summary_stats.json`

格式：
```json
{
  "total_feedbacks": 25,
  "average_rating": 4.2,
  "rating_distribution": {
    "1": 0,
    "2": 2,
    "3": 3,
    "4": 10,
    "5": 10
  },
  "improvement_areas": {
    "too_long": 3,
    "missing_deadline": 5,
    "missing_action_items": 2
  },
  "learned_preferences": {
    "detail_level": "normal",
    "focus_areas": ["deadline"]
  }
}
```

## 偏好推断算法

### 触发阈值

当某个改进领域出现 **≥2次** 反馈时，触发偏好调整。

### 调整规则

| 反馈类型 | 出现次数 | 调整策略 |
|---------|---------|---------|
| too_long | ≥2 | detail_level → brief, max_brief_lines = 3 |
| too_short | ≥2 | detail_level → detailed, min_key_points = 5 |
| missing_deadline | ≥2 | focus_areas 添加 "deadline" |
| missing_action_items | ≥2 | focus_areas 添加 "action_items" |
| wrong_tone | ≥2 | avoid_patterns 添加 "too_formal" |

### 冲突处理

如果同时出现 `too_long` 和 `too_short` 反馈：
1. 以多数为准
2. 如果数量相同，保持 normal
3. 记录冲突到日志

## 使用场景

### 场景1：用户偏好简洁摘要

**反馈历史**：
- 第1次：评分3，评论"有点啰嗦"
- 第2次：评分3，评论"可以更简洁"
- 第3次：评分4，评论"这次好多了"

**系统调整**：
```json
{
  "detail_level": "brief",
  "style_adjustments": {
    "max_brief_lines": 3,
    "max_key_points": 2
  }
}
```

**效果**：后续生成的摘要自动减少行数和要点数量。

### 场景2：用户关注截止时间

**反馈历史**：
- 第1次：评分2，评论"没提取到截止日期"
- 第2次：评分3，评论"还是漏了时间"
- 第3次：评分5，评论"完美，时间提取到了"

**系统调整**：
```json
{
  "focus_areas": ["deadline"],
  "priority_rules": {
    "extract_deadline_first": true
  }
}
```

**效果**：
- 优先提取时间信息
- 在 key_points 中优先放置截止时间
- 增强日期模式匹配敏感度

## API 参考

### collect_feedback()

```python
collect_feedback(
    email_subject="邮件主题",
    generated_summary={...},
    user_rating=4,
    user_comment="评论",
    improvement_areas=["missing_deadline"]
)
```

### get_user_preferences()

```python
prefs = get_user_preferences()
# 返回：
{
    "detail_level": "brief|normal|detailed",
    "focus_areas": ["deadline", "action_items"],
    "avoid_patterns": [],
    "style_adjustments": {...}
}
```

### analyze_feedback_trends()

```python
trends = analyze_feedback_trends()
# 返回：
{
    "total_feedbacks": 25,
    "satisfaction_rate": "84.0%",
    "average_rating": "4.2/5.0",
    "top_issues": ["missing_deadline (5次)"],
    "recommendations": ["用户关注截止时间，建议加强日期提取"]
}
```

## 最佳实践

### 1. 定期查看报告

建议每周运行一次：
```bash
python scripts/feedback_system.py --report
```

### 2. 及时响应负面反馈

当出现评分 ≤2 时：
1. 查看具体评论
2. 分析生成结果
3. 调整算法或规则
4. 验证改进效果

### 3. 保持反馈多样性

不要只收集负面反馈，也要记录：
- 高质量摘要（5分）的特征
- 用户特别满意的点
- 不同场景下的表现差异

### 4. A/B 测试

重大调整前，可以先：
1. 保存当前偏好
2. 小范围测试新策略
3. 对比反馈评分
4. 决定是否全量应用

## 扩展性

未来可扩展的功能：

1. **多用户支持**：为不同用户维护独立的偏好文件
2. **场景感知**：根据邮件类型（会议/审批/通知）使用不同策略
3. **时间衰减**：旧反馈权重降低，新反馈权重更高
4. **聚类分析**：识别不同类型用户的偏好模式
