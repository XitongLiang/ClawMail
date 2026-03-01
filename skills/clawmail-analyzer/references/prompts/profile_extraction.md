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

### contact_direction（信息流向）
描述该发件人与用户之间的指令/信息传播方向，帮助判断该联系人对用户的"权力关系"。
- `inbound_command`：发件人向用户发出指令、任务、要求（如上司布置工作、客户下订单）
- `outbound_report`：用户向发件人汇报、请示、提交材料（如下属汇报、学生提交作业）
- `bidirectional`：双向讨论、协商、互相请求（如平级合作）
- `inbound_info`：发件人向用户传递信息，无需行动（如订阅通知、系统推送）
- **fact_key 格式**: contact.{email}.direction
- **提取信号**: 邮件中是否有命令语气？用户是执行方还是决策方？是否有待办项指向用户？

### contact_comm_pattern（沟通模式）
描述该联系人与用户之间的典型沟通风格，帮助 AI 生成更贴合预期的回复。
- 沟通风格：正式/非正式、简洁/详细
- 典型话题类型：技术讨论/行政事务/项目协调/闲聊
- 回复预期：需要即时回复 / 无需回复（仅供参考）/ 讨论式（期望意见反馈）
- **fact_key 格式**: contact.{email}.comm_style, contact.{email}.reply_expect
- **提取信号**: 邮件的措辞风格、是否有明确的回复要求、历史邮件是否体现固定模式

### organization（组织结构）
- 用户所在团队/部门的结构
- 汇报关系
- 跨部门协作关系
- **fact_key 格式**: org.team, org.report_to, org.collaborate_with

### project（项目静态信息）
仅提取用户在项目中的稳定角色信息，走 pending 池积累确认后写入 USER.md。
- 当前参与的项目名称
- 项目角色（负责人、参与者、审批人）
- **fact_key 格式**: project.{name}.role
- **不提取**：项目阶段、截止日期、进度等动态状态（由 project_state 类别处理）

### project_state（项目动态状态）
提取项目的当前阶段和截止时间，直接写入 MemoryBank（支持 UPDATE/DELETE，无需积累）。

**必须同时满足以下条件才提取，缺一不可：**
1. 邮件中出现**可识别的具体项目名称**（如"XX系统"、"Q4发布"、"App改版"，不接受"这个项目"、"我们的项目"等模糊指代）
2. 邮件中出现以下**阶段或截止信号**之一：
   - 阶段词：冲刺、上线、交付、验收、发布、灰度、封版、launch、sprint、milestone、go-live
   - 明确截止日期：如"本周五前"、"3月底"、"下周一交付"（须可提取为具体日期或相对时间）

**不满足条件时禁止提取**（宁可漏，不可错）：
- 仅提到项目名但无阶段/截止信号
- 有阶段词但无法识别具体项目名称
- 泛泛的"项目很忙"、"最近工作量大"

**fact_key 格式**: project.{name}.phase, project.{name}.deadline
**fact_content 格式**: 必须包含阶段描述和截止时间（如有），例如：
`{"phase": "冲刺", "deadline": "2026-03-31", "note": "本周五前完成联调"}`

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

- 只提取关于**用户**（收件人）的信息；contact_direction 和 contact_comm_pattern 是关于用户与发件人之间关系的信息，属于合法的用户侧写范围
- 如果无法提取任何有价值的信息，返回空数组 `[]`
- 不要重复提取已在 USER.md 中存在的信息
- 每封邮件最多提取 5 个 facts（优先提取置信度高的），其中 contact_direction / contact_comm_pattern 各算 1 个
