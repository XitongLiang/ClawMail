# 重要性评分算法

本文档详细说明 importance_score 的计算逻辑。

---

## 算法公式

```
总得分 = round(
  发件人得分 × 0.30 +
  紧急词得分 × 0.25 +
  截止时间得分 × 0.25 +
  复杂度得分 × 0.20
)
```

结果取整为 0-100 的整数。

---

## 维度1: 发件人身份 (权重30%)

基于组织架构层级判断发件人重要性。

### 评分表

| 身份类型 | 得分范围 | 判断依据 |
|---------|---------|---------|
| 家人/CEO/总经理/董事会成员 | 90-100 | 邮箱匹配VIP列表，或职位关键词匹配 |
| 部门经理/总监 | 70-89 | 组织架构中的直接上级，或部门负责人 |
| 项目经理 | 50-69 | 当前项目相关，或项目管理层 |
| 普通同事 | 30-49 | 无特殊职位标识，内部员工 |
| 系统邮件/自动通知 | 0-29 | noreply / notification / 系统发件人 |
| 外部未知 | 10-40 | 根据域名判断 |

### 判断规则

**优先级：历史记忆 > 职位关键词推测**

1. **记忆优先**：如果 system prompt 中的"发件人画像（历史记忆）"有此发件人的 `contact.{email}.relationship` 或 `contact.{email}.direction` 记录，**优先依据记忆中的关系类型打分**：
   - 上司 / 直接上级 / `inbound_command` 关系 → 70-95（结合过往邮件紧迫性调整）
   - 平级同事 / `bidirectional` 关系 → 40-60
   - 下属 / `outbound_report` 关系 → 30-50
   - 外部客户 / 合作方（非命令关系）→ 50-70
   - 纯信息推送 / `inbound_info` → 10-30

2. **无记忆时，用职位关键词推测**：

```python
def score_sender(from_address, user_context):
    email = from_address.get("email", "")
    name = from_address.get("name", "")

    # VIP列表匹配
    if email in user_context.get("vip_list", []):
        return 95

    # 职位关键词
    title_keywords = {
        ("CEO", "总经理", "董事长", "总裁"): (90, 100),
        ("总监", "经理", "主管"): (70, 89),
        ("项目经理", "PM"): (50, 69),
    }

    # 系统邮件检测
    if any(kw in email for kw in ["noreply", "notification", "system", "alert"]):
        return 20

    # 默认
    return 40
```

---

## 维度2: 紧急关键词 (权重25%)

检测邮件正文中表达的紧急程度。

### 关键词分级

| 级别 | 得分 | 关键词示例 |
|-----|------|-----------|
| 极高 | 90-100 | "紧急"、"立即"、"马上"、"asap"、"urgent" |
| 高 | 70-89 | "今天"、"尽快"、"速回"、"priority" |
| 中 | 50-69 | "本周"、"这几天"、"近期" |
| 低 | 30-49 | "请"、"需要"、"麻烦" |
| 无 | 0-29 | 无时间相关词汇 |

### 检测逻辑

```python
def score_urgency(body_text):
    urgency_patterns = {
        ("紧急", "立即", "马上", "asap", "urgent"): 95,
        ("今天", "今日", "尽快", "速回", "priority"): 80,
        ("本周", "这周", "这几天", "近期"): 60,
        ("请", "需要", "麻烦"): 40,
    }
    
    max_score = 0
    for patterns, score in urgency_patterns.items():
        if any(p in body_text for p in patterns):
            max_score = max(max_score, score)
    
    return max_score
```

---

## 维度3: 截止时间 (权重25%)

基于当前时间计算截止日期的客观紧迫性。

### 日期评分

| 截止时间 | 得分 | 说明 |
|---------|------|------|
| 今天 | 90-100 | 当日截止 |
| 明天 | 70-89 | 次日截止 |
| 本周内 | 50-69 | 本周日前 |
| 下周 | 30-49 | 下周一至周日 |
| 更晚/无 | 0-29 | 无明确时间或超过一周 |

### 计算逻辑

```python
def score_deadline(deadline_str, current_date):
    if not deadline_str:
        return 0
    
    try:
        deadline = parse_date(deadline_str)
        days_diff = (deadline - current_date).days
        
        if days_diff <= 0:
            return 100  # 已过期，最高紧急
        elif days_diff == 1:
            return 85   # 明天
        elif days_diff <= 7 - current_date.weekday():
            return 60   # 本周内
        elif days_diff <= 14:
            return 40   # 两周内
        else:
            return 20   # 更晚
    except:
        return 0
```

---

## 维度4: 任务复杂度 (权重20%)

评估待办事项的数量和优先级分布。

### 复杂度评分

| 待办特征 | 得分 | 说明 |
|---------|------|------|
| ≥3个高优先级待办 | 90-100 | 大量紧急任务 |
| 2个高优先级待办 | 70-89 | 较多紧急任务 |
| 1个中优先级待办 | 50-69 | 中等工作量 |
| 1-2个低优先级待办 | 30-49 | 少量简单任务 |
| 无明确待办 | 0-29 | 纯通知/讨论 |

### 计算逻辑

```python
def score_complexity(action_items):
    if not action_items:
        return 0
    
    high = sum(1 for item in action_items if item["priority"] == "high")
    medium = sum(1 for item in action_items if item["priority"] == "medium")
    low = sum(1 for item in action_items if item["priority"] == "low")
    
    if high >= 3:
        return 95
    elif high == 2:
        return 80
    elif high == 1 or medium >= 2:
        return 60
    elif low >= 1:
        return 40
    else:
        return 20
```

---

## 完整计算示例

### 示例邮件
- 发件人: 张总 (CEO) → sender_score: 95
- 正文包含: "请在今天下班前完成" → urgency_score: 80
- 截止日期: 今天 → deadline_score: 95
- 待办: 2个高优先级 → complexity_score: 80

### 计算过程

```
sender_contrib = 95 × 0.30 = 28.5
urgency_contrib = 80 × 0.25 = 20.0
deadline_contrib = 95 × 0.25 = 23.75
complexity_contrib = 80 × 0.20 = 16.0

total = 28.5 + 20.0 + 23.75 + 16.0 = 88.25

importance_score = round(88.25) = 88
```

---

## 输出格式

```json
{
  "importance_score": 88,
  "importance_breakdown": {
    "sender_weight": 30,
    "sender_score": 95,
    "sender_contrib": 28.5,
    "urgency_weight": 25,
    "urgency_score": 80,
    "urgency_contrib": 20.0,
    "deadline_weight": 25,
    "deadline_score": 95,
    "deadline_contrib": 23.75,
    "complexity_weight": 20,
    "complexity_score": 80,
    "complexity_contrib": 16.0,
    "total": 88.25
  }
}
```

---

## 特殊规则

### 垃圾邮件
- is_spam = true 时，importance_score 强制为 0
- 不计算其他维度

### 订阅邮件
- category 包含 "subscription" 时，sender_score 上限为 30

### 系统通知
- 检测为系统邮件时，复杂度强制为 0（无待办）
