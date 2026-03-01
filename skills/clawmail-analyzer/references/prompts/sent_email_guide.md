# 已发送邮件分析指南

## 与收件邮件分析的区别

这是用户**自己发出**的邮件，分析目标不同：

**需要**：
- one_line 摘要（用于线程上下文，让后续收到回复时 AI 理解对话脉络）
- 收件人联系人记忆（contact.{收件人email}.* — relationship, role, comm_style）
- 用户侧写事实（career, org, project 等从自身邮件内容中推断）

**不需要**：
- 重要性评分（importance_scores）
- 垃圾邮件检测（is_spam）
- 分类标签（category）
- 行动项（action_items）
- 回复立场建议（reply_stances）

## one_line 摘要规则

- 概括"用户做了什么 / 说了什么"，而非"收到了什么"
- 包含具体数字、日期、金额（如有）
- 30 字以内

好的例子：
- "向张总汇报了 Q1 销售额达 500 万的情况"
- "请求技术部在周五前完成 API 接口联调"
- "确认参加 3 月 15 日的产品发布会"
- "拒绝了供应商的报价并提出还价方案"

差的例子：
- "发了一封邮件"（太笼统）
- "回复了张三"（没有实质内容）
- "关于项目的讨论"（缺乏具体信息）

## 联系人记忆提取规则

- fact_key 必须以 `contact.{收件人email}` 为前缀
- 从邮件内容推断用户与收件人的关系和互动模式
- 用户是发件人，收件人才是 contact 对象

可提取的类型：
- `contact.{email}.relationship`: 上下级、同事、客户、供应商、朋友
- `contact.{email}.role`: 收件人的职位/角色
- `contact.{email}.comm_style`: 与该收件人的沟通风格（正式/轻松）
- `contact.{email}.topic`: 常讨论的话题领域

## 用户侧写事实

从用户发出的邮件中，可以推断用户自身信息（同 profile_extraction.md 规则）：
- career.*: 职位、部门、工作领域
- org.*: 团队结构、汇报关系
- project.*: 参与的项目及角色
