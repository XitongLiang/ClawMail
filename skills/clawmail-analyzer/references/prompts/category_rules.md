# 邮件分类规则

## 固定分类标签

| 标签 | 触发条件 |
|------|---------|
| urgent | 包含紧急关键词或有今日截止的待办 |
| pending_reply | 邮件明确要求回复或确认 |
| notification | 系统通知、自动生成的邮件 |
| subscription | 订阅邮件、newsletter |
| meeting | 会议邀请、日程相关 |
| approval | 审批请求 |

## 动态分类

- `项目:XXX` — 当邮件与已知项目相关时添加
- 最多 4 个标签（含动态标签）

## 分类优先级

urgent > pending_reply > approval > meeting > 其他

## 判断规则

### urgent
- 主题或正文包含：紧急、立即、马上、ASAP、urgent、emergency
- 截止日期为今日或已过期
- 发件人为 VIP 且明确要求立即处理

### pending_reply
- 正文包含疑问句或明确要求回复
- 包含：请回复、请确认、请反馈、could you reply、please confirm
- 邮件以问题结尾

### notification
- 发件人为 noreply、notification、system、alert
- 邮件结构为固定模板（无个人化内容）
- 来自已知系统（GitHub、Jira、Slack 等）

### subscription
- 包含退订链接或 unsubscribe
- 来自 newsletter 域名
- 批量发送特征（无个人称呼）

### meeting
- 包含会议时间、地点、议程
- 来自日历系统（calendar invite）
- 主题包含：会议、meeting、sync、standup

### approval
- 包含：审批、approve、sign off、请签字
- 邮件结构为审批流模板
