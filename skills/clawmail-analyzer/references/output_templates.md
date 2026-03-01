# 输出格式模板

本文档定义不同场景下的输出格式模板。

---

## 模板类型

### 1. quick（快速预览）

**适用场景**: 快速扫一眼，判断是否需要立即处理

**输出格式**:
```
📧 {one_line}
🏷️ {category} | 🔥 {importance_score}分 | ⏰ {行动提示}
```

**示例**:
```
📧 张总要求周五前提交Q4报告
🏷️ urgent,工作 | 🔥 85分 | ⏰ 今日有2个待办
```

---

### 2. standard（标准摘要）

**适用场景**: 默认输出，信息完整

**输出格式**:
```
📧 {subject}
👤 {from_name} <{from_email}>
📅 {received_at}
🏷️ 分类: {category}
🔥 重要性: {importance_score}/100 | 情感: {sentiment}

📝 摘要:
{brief}

🔑 关键词: {keywords}

💡 要点:
{key_points}

⚡ 待办事项 ({action_items_count}):
{action_items}

💬 建议回复:
{suggested_reply}
```

**示例**:
```
📧 关于Q4财务报告提交的紧急通知
👤 张伟 <zhang@company.com>
📅 2026-02-28 10:30
🏷️ 分类: urgent, 工作, 项目:Q4财务
🔥 重要性: 85/100 | 情感: urgent

📝 摘要:
张总邮件要求各部门在本周五（3月1日）前提交Q4季度财务报告。
报告需包含收入、支出、利润三大板块数据。
请确保数据准确，并抄送财务部审核。

🔑 关键词: Q4报告, 张总, 周五截止, 财务数据

💡 要点:
1. 周五（3月1日）为报告提交截止日期
2. 报告需包含收入、支出、利润三大板块
3. 完成后需抄送财务部审核

⚡ 待办事项 (2):
1. 【高】整理Q4财务数据并撰写报告 (截止: 2026-03-01)
   引用: "请在本周五（3月1日）前提交Q4季度财务报告"
2. 【中】抄送财务部审核报告 (截止: 2026-03-01)
   引用: "完成后请抄送财务部进行审核"

💬 建议回复:
收到，我会按时完成Q4报告并提交审核。
```

---

### 3. detail（详细分析）

**适用场景**: 需要理解判断依据，或回答"为什么"

**输出格式**:
```
📧 {subject}
👤 {from_name} <{from_email}>
📅 {received_at}

📊 重要性评分详情: {importance_score}/100
├─ 发件人身份 (权重{sender_weight}%): {sender_score}分 × {sender_weight}% = {sender_contrib}分
│   └─ {sender_explanation}
├─ 紧急关键词 (权重{urgency_weight}%): {urgency_score}分 × {urgency_weight}% = {urgency_contrib}分
│   └─ 检测到关键词: {detected_keywords}
├─ 截止时间 (权重{deadline_weight}%): {deadline_score}分 × {deadline_weight}% = {deadline_contrib}分
│   └─ 距离截止还有 {days_left} 天
└─ 任务复杂度 (权重{complexity_weight}%): {complexity_score}分 × {complexity_weight}% = {complexity_contrib}分
    └─ {complexity_explanation}

总分: {total}

📝 完整摘要:
{brief}

📌 关键要点（含引用）:
{key_points_with_quotes}

⚡ 待办事项（含原文引用）:
{action_items_with_quotes}

💭 情感分析:
{sentiment_explanation}

🎯 建议行动:
{recommended_actions}
```

---

### 4. action_focus（待办导向）

**适用场景**: 任务管理，快速提取行动项

**输出格式**:
```
📋 待办清单
来自: {subject}
发件人: {from_name}

高优先级:
{high_priority_actions}

中优先级:
{medium_priority_actions}

低优先级:
{low_priority_actions}

⏰ 即将截止:
{upcoming_deadlines}

💬 建议回复立场:
{reply_stances}

🚀 快速操作:
- 标记完成
- 设置提醒
- 起草回复
```

---

### 5. compare（对比分析）

**适用场景**: 多封邮件比较优先级

**输出格式**:
```
📊 邮件优先级对比分析

| 排名 | 邮件主题 | 总分 | 发件人 | 紧急度 | 截止 | 复杂度 |
|-----|---------|------|-------|-------|------|-------|
| 1 | {subject_1} | {score_1} | {s1} | {u1} | {d1} | {c1} |
| 2 | {subject_2} | {score_2} | {s2} | {u2} | {d2} | {c2} |
| ... | ... | ... | ... | ... | ... | ... |

🔝 建议处理顺序:
1. {email_1_subject} - 原因: {reason}
2. {email_2_subject} - 原因: {reason}
...

📈 详细对比:
{detailed_comparison}

💡 时间管理建议:
{time_management_tips}
```

---

## JSON 输出格式

所有模板都对应一个标准 JSON 结构：

```json
{
  "status": "success",
  "format": "quick|standard|detail|action_focus|compare",
  "email_id": "...",
  "rendered": "人类可读格式化文本",
  "data": {
    "summary": {...},
    "action_items": [...],
    "metadata": {...}
  }
}
```

ClawMail 可以根据 `format` 选择渲染方式：
- `quick`: 显示在邮件列表预览
- `standard`: 默认详情页
- `detail`: 展开分析视图
- `action_focus`: 任务管理集成
- `compare`: 对比视图
