# 记忆注入规范

本文档定义 ClawMail 邮件分析中的用户记忆注入机制。

---

## 记忆系统架构

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Memory    │────▶│   Skill     │────▶│    LLM      │
│   Bank      │     │  (analyze)  │     │  (prompt)   │
└─────────────┘     └─────────────┘     └─────────────┘
```

---

## 记忆类型

### 1. 发件人偏好记忆 (sender_preference)

记录与特定发件人的历史交互模式。

**存储内容**:
- 该发件人邮件的通常优先级
- 历史回复风格偏好
- 常用沟通方式
- 特殊注意事项

**示例**:
```json
{
  "memory_type": "sender_preference",
  "sender_email": "zhang@company.com",
  "content": "张总通常使用微信跟进邮件事项，邮件需简洁直接，回复时间最好在2小时内",
  "created_at": "2026-01-15"
}
```

### 2. 域名级别记忆 (domain_pattern)

记录某类域名邮件的通用特征。

**存储内容**:
- 该域名的邮件类型特征
- 默认处理方式
- 常见主题模式

**示例**:
```json
{
  "memory_type": "domain_pattern",
  "domain": "github.com",
  "content": "GitHub通知通常是技术相关，PR审查请求优先级中等，CI失败通知需要立即查看",
  "created_at": "2026-02-01"
}
```

### 3. 项目关联记忆 (project_context)

记录项目相关的上下文信息。

**存储内容**:
- 项目当前状态
- 最近的里程碑
- 相关邮件主题关键词

**示例**:
```json
{
  "memory_type": "project_context",
  "project": "Q4发布",
  "content": "Q4发布项目当前处于测试阶段，截止日期为3月15日，相关邮件涉及Bug修复和测试反馈",
  "created_at": "2026-02-20"
}
```

### 4. 用户通用偏好 (user_preference)

记录用户的一般性偏好设置。

**存储内容**:
- 摘要长度偏好
- 关注的邮件类型
- 工作时间习惯

**示例**:
```json
{
  "memory_type": "user_preference",
  "content": "用户偏好简短摘要，重点关注deadline和action items，非工作时间（晚10点后）收到的邮件自动标记为次日处理",
  "created_at": "2026-01-10"
}
```

---

## 检索策略

### 邮件分析任务 (email_analysis)

**检索维度**:
1. 发件人邮箱精确匹配
2. 发件人域名匹配
3. 主题关键词匹配（项目）
4. 用户通用偏好

**优先级**:
1. 发件人偏好（最高）
2. 项目关联（高）
3. 域名级别（中）
4. 通用偏好（低）

### 回复草稿任务 (reply_draft)

**检索维度**:
1. 发件人历史回复风格
2. 该发件人的常用表达
3. 用户通用写作偏好

**注入内容**:
- 历史回复示例
- 建议的语气风格
- 避免的表达方式

---

## Prompt 注入格式

### 邮件分析注入

```
【用户偏好记忆】

发件人相关：
- 张总（zhang@company.com）的邮件通常需要2小时内回复，偏好简洁直接的沟通方式

域名相关：
- company.com 域名下的邮件多为内部工作沟通，优先级普遍较高

项目相关：
- 当前涉及项目"Q4发布"，截止日期3月15日，相关邮件需特别关注

通用偏好：
- 用户偏好简短摘要，重点关注deadline和action items
```

### 回复草稿注入

```
【历史回复偏好】

对张总的历史回复风格：
- 语气：正式但友好
- 长度：50-100字
- 常用结尾："期待您的反馈"、"如有问题请随时联系"
- 避免：过于简短的回复、使用表情符号

建议：保持与以往一致的正式程度，在2小时内回复
```

---

## 输入数据中的记忆字段

```json
{
  "context": {
    "account_id": "user_123",
    "memory_enabled": true,
    "memory_options": {
      "max_memories": 5,
      "include_types": ["sender_preference", "domain_pattern", "project_context"],
      "time_range_days": 90
    }
  }
}
```

---

## 输出数据中的记忆字段

```json
{
  "memory": {
    "injected": true,
    "memory_count": 3,
    "memory_types": ["sender_preference", "domain_pattern", "project_context"],
    "memories": [
      {
        "type": "sender_preference",
        "source": "zhang@company.com",
        "relevance": 0.95
      }
    ]
  }
}
```

---

## 记忆更新机制

### 自动学习

Skill 可以基于用户行为自动更新记忆：

1. **优先级校正**: 用户手动调整邮件优先级 → 更新发件人偏好
2. **回复风格**: 用户编辑AI生成的回复 → 学习用户偏好
3. **分类习惯**: 用户修改分类标签 → 更新分类规则

### 显式反馈

用户可以直接告诉 Skill：
- "张总的邮件以后都标记为高优先级"
- "GitHub的PR通知可以批量处理"
- "项目Q4相关的邮件都要提醒我"

---

## 隐私与安全

- 记忆数据与用户 account_id 绑定
- 不跨用户共享记忆
- 敏感信息（如具体邮件内容）不存入长期记忆
- 记忆可导出、可删除
