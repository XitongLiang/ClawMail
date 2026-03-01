# 事实性信息提取规则

## 提取目标

从邮件内容中提取关于用户（收件人）的事实性信息，用于构建用户侧写。

## 提取类别

### career（职业信息）
- 行业、公司名称、部门
- 职位、职级
- 工作职责和专业领域
- **fact_key 格式**: career.industry, career.company, career.position, career.department

### contact（联系人关系）
- 发件人与用户的关系（上司、同事、客户、朋友、家人）
- 频繁沟通的联系人
- 联系人的角色和职位
- **fact_key 格式**: contact.{email}.relationship, contact.{email}.role

### organization（组织结构）
- 用户所在团队/部门的结构
- 汇报关系
- 跨部门协作关系
- **fact_key 格式**: org.team, org.report_to, org.collaborate_with

### project（项目上下文）
- 当前参与的项目名称
- 项目角色（负责人、参与者、审批人）
- 项目状态和里程碑
- **fact_key 格式**: project.{name}.role, project.{name}.status

## 输出格式

```json
[
    {
        "fact_key": "career.position",
        "fact_category": "career",
        "fact_content": "软件工程师，专注后端开发",
        "confidence": 0.7
    }
]
```

## 置信度评估

- **0.9-1.0**: 邮件中有明确声明（如签名、自我介绍）
- **0.7-0.8**: 从上下文强烈暗示（如讨论技术架构 + 代码审查）
- **0.5-0.6**: 合理推断（如收到某类邮件较多）
- **0.3-0.4**: 弱信号（如 CC 列表中的位置）
- **<0.3**: 不要提取，信号太弱

## 注意事项

- 只提取关于**用户**（收件人）的信息，不是关于发件人的
- 如果无法提取任何有价值的信息，返回空数组 `[]`
- 不要重复提取已在 USER.md 中存在的信息
- 每封邮件最多提取 3 个 facts，优先提取置信度高的
