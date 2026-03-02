# ClawMail 个性化测试方案

## 目标

展示 ClawMail 在 **摘要（Briefing）**、**排序（Sorting）**、**回复草稿（Reply-drafting）** 三个维度的个性化效果。

两种展示角度：
- **方案 A（双用户对比）**：两个用户收到相同邮件，产出不同
- **方案 B（单用户旅程）**：一个用户通过操作让系统逐步学会个性化

---

# 方案 A：双用户对比

> 同样 5 封邮件，两个用户看到完全不同的排序、摘要和回复。

## A.1 双用户画像

| | User A（技术主管） | User B（销售经理） |
|---|---|---|
| 职位 | 带 5 人研发团队的 Tech Lead | 华东区大客户销售经理 |
| 日常关注 | 代码构建、技术方案、团队进度 | 客户关系、报价、合同 |
| 沟通风格 | 和 boss 简短直接，不喜欢套话 | 对外正式、对内礼貌 |
| 摘要偏好 | 具体技术细节、模块名、错误信息 | 商业价值、行动项、客户名 |

---

## A.2 共用测试邮件（5 封）

### 邮件 1：Boss 邮件

```
From: boss@company.com (李经理)
Subject: 请提交本周工作进展

你好，

本周工作进展报告请在周五下午3点前发给我。
重点说明：
1. 当前项目的里程碑完成情况
2. 遇到的问题和风险
3. 下周计划

谢谢

李经理
```

### 邮件 2：客户邮件

```
From: client@bigcorp.com (王总)
Subject: Re: 产品报价咨询

您好，

我们 BigCorp 正在评估Q2的采购计划，对贵公司的企业版产品很感兴趣。

能否提供以下信息：
1. 企业版 50 人授权的年度报价
2. 是否支持私有化部署
3. 技术支持的响应时间 SLA

我们计划在本月底前完成供应商评估，希望尽快收到回复。

王总
BigCorp 采购部
```

### 邮件 3：GitHub CI 通知

```
From: noreply@github.com (GitHub)
Subject: [clawmail/main] Build #1234 failed

Run #1234 on branch main triggered by push (commit abc1234)

  backend-tests: FAILED
    - test_email_sync: AssertionError: expected 200 got 500
    - test_ai_processor: TimeoutError after 30s

  frontend-build: PASSED
  lint: PASSED

View details: https://github.com/clawmail/actions/runs/1234
```

### 邮件 4：同事请求

```
From: colleague@company.com (张三)
Subject: API 文档能发我一份吗

Hi，

上周五会议上你提到的API文档能否发我一份？

我们这边开发需要参考接口定义，目前进度有点卡住了。

如果方便的话今天能给到最好，谢谢！

张三
```

### 邮件 5：Newsletter

```
From: newsletter@techweekly.com (TechWeekly)
Subject: 本周技术动态 #128

【本周头条】
1. Rust 2026 Edition 发布，新增 async trait 稳定支持
2. OpenAI 发布 GPT-5 API，推理速度提升 3 倍
3. Kubernetes 1.32 正式 GA，改进 Pod 调度性能

【深度文章】
- 如何用 eBPF 实现零成本可观测性
- 大模型微调实战：从数据标注到部署上线

---
取消订阅 | 更新偏好
```

---

## A.3 预装记忆（个性化的来源）

### User A（技术主管）的记忆

| 类型 | key | 内容 | 置信度 |
|------|-----|------|:---:|
| `sender_importance` | `boss@company.com` | sender_name: 李经理, typical_score: 72, pattern: "直接上级，重视但非必须立即响应" | 0.85 |
| `sender_importance` | `noreply@github.com` | sender_name: GitHub, typical_score: 65, pattern: "用户关注构建状态，失败需及时处理" | 0.80 |
| `automated_content` | `github.com` | source: GitHub CI, content_type: notification, typical_score: 60, pattern: "用户是技术主管，CI 失败对其重要" | 0.82 |
| `response_pattern` | `boss@company.com` | context: 与上级沟通, preference: 简短直接不客套, tone: 简短, pattern: "用户和boss沟通偏好极简风格" | 0.90 |
| `summary_preference` | *(global)* | preference_type: brief, issue: 摘要缺少具体技术细节, desired: 包含模块名/错误信息/技术指标, pattern: "用户重视摘要中的具体技术信息" | 0.85 |

### User B（销售经理）的记忆

| 类型 | key | 内容 | 置信度 |
|------|-----|------|:---:|
| `sender_importance` | `client@bigcorp.com` | sender_name: 王总, typical_score: 90, pattern: "大客户，邮件需优先处理" | 0.92 |
| `sender_importance` | `boss@company.com` | sender_name: 李经理, typical_score: 85, pattern: "直接上级，非常重视" | 0.88 |
| `automated_content` | `github.com` | source: GitHub, content_type: notification, typical_score: 10, pattern: "用户对技术通知完全不关心" | 0.90 |
| `response_pattern` | *(global)* | context: 对外沟通, preference: 正式完整有礼貌, tone: 正式, pattern: "用户对外部联系人保持高正式度" | 0.88 |
| `summary_preference` | *(global)* | preference_type: brief, issue: 摘要太技术化看不懂, desired: 突出商业价值和需要采取的行动, pattern: "用户偏好行动导向的摘要" | 0.85 |

---

## A.4 预期个性化效果

### 排序（Sorting）

| 邮件 | User A 预估分 | User B 预估分 | 差异原因 |
|------|:---:|:---:|---|
| Boss: 工作进展 | ~65 | ~75 | B 的 boss sender_importance 更高 (85 vs 72) |
| Client: 产品报价 | ~35 | ~82 | B 有 client 记忆 (90)，A 无记忆 |
| GitHub: Build failed | ~58 | ~12 | A 有 automated_content=60，B=10 |
| Colleague: API文档 | ~48 | ~38 | A 更重视技术协作 |
| Newsletter: 技术动态 | ~15 | ~8 | 两者都低，订阅邮件 sender_score 上限 30 |

**User A 排序：** Boss → GitHub CI → 同事 → 客户 → Newsletter

**User B 排序：** 客户 → Boss → 同事 → Newsletter → GitHub CI

### 摘要（Briefing）

#### Boss 邮件摘要对比

| | User A（技术主管） | User B（销售经理） |
|---|---|---|
| keywords | ["周报", "里程碑", "风险", "周五截止"] | ["工作进展", "周五3点", "李经理"] |
| one_line | "李经理要求周五3点前提交进展，重点汇报里程碑和风险" | "李经理要求周五3点前提交本周工作进展报告" |
| brief | 侧重：具体需要汇报哪些技术指标 | 侧重：需要采取什么行动 |

#### GitHub CI 摘要对比

| | User A（技术主管） | User B（销售经理） |
|---|---|---|
| keywords | ["CI失败", "main分支", "test_email_sync", "500错误", "超时"] | ["构建失败", "GitHub通知"] |
| one_line | "main 分支 CI 失败：email_sync 返回 500，ai_processor 超时" | "GitHub 项目构建失败通知" |
| brief | 详细列出失败的测试名和错误类型 | 一句话概括"有构建失败" |

#### Client 邮件摘要对比

| | User A（技术主管） | User B（销售经理） |
|---|---|---|
| keywords | ["报价", "BigCorp", "企业版", "私有化部署"] | ["BigCorp", "Q2采购", "50人授权", "月底评估", "王总"] |
| one_line | "BigCorp 询问企业版报价和私有化部署方案" | "BigCorp王总询问企业版50人年度报价，月底前完成评估" |
| brief | 侧重技术需求（私有化部署、SLA） | 侧重商业信息（采购规模、时间线、决策流程） |

### 回复草稿（Reply-drafting）

#### Boss 邮件回复（stance=agree）

**User A（简短风格）：**
```
好的李经理，周五3点前发您。有问题提前沟通。
```

**User B（正式风格）：**
```
李经理您好，

本周工作进展报告将在周五下午3点前提交。我会按照要求涵盖里程碑完成情况、
当前问题与风险、以及下周计划三个部分。

如需补充其他内容，请提前告知。
```

#### Client 邮件回复（stance=provide_info）

**User A（无特定客户记忆，默认风格）：**
```
王总好，

企业版 50 人年度授权报价、私有化部署方案和 SLA 信息我这边整理后发您。
预计明天可以给到。
```

**User B（正式 + 重视客户）：**
```
王总您好，

感谢 BigCorp 对我们企业版产品的关注。

针对您提出的三个问题，我将在明日（周X）前提供完整的报价方案，包括：
1. 50 人授权年度报价及阶梯优惠
2. 私有化部署技术方案与实施周期
3. 技术支持 SLA 详细条款

考虑到贵方月底前完成评估的时间节点，如需安排产品演示或技术对接，
我们可以在本周内协调。
```

---

---

# 方案 B：单用户旅程 —— 回复风格的发件人级个性化

> 核心演示点：用户编辑了给 Boss 的回复后，系统只改变给 Boss 的回复风格，给客户的回复不受影响。
> 证明个性化是**按发件人粒度**学习的，不是一刀切。

## B.1 设定

- 用户：一名技术主管，刚开始使用 ClawMail（零记忆）
- 两个发件人：**Boss（李经理）** 和 **客户（王总）**
- 两人邮件内容结构类似（都是请求类），方便对比回复

## B.2 测试邮件

### 第一轮（零记忆阶段）

**邮件 1：Boss 来信**
```
From: boss@company.com (李经理)
Subject: 请提交本周工作进展

你好，

本周工作进展报告请在周五下午3点前发给我。
重点说明：
1. 当前项目的里程碑完成情况
2. 遇到的问题和风险
3. 下周计划

谢谢

李经理
```

**邮件 2：客户来信**
```
From: client@bigcorp.com (王总)
Subject: Re: 产品报价咨询

您好，

我们 BigCorp 正在评估 Q2 的采购计划，对贵公司的企业版产品很感兴趣。

能否提供以下信息：
1. 企业版 50 人授权的年度报价
2. 是否支持私有化部署
3. 技术支持的响应时间 SLA

我们计划在本月底前完成供应商评估，希望尽快收到回复。

王总
BigCorp 采购部
```

### 第二轮（学习后阶段）

**邮件 3：Boss 又来信**（不同内容，同一发件人）
```
From: boss@company.com (李经理)
Subject: Q2 预算方案什么时候能交

快了吗？下周一开会要用。

李经理
```

**邮件 4：客户又来信**（不同内容，同一发件人）
```
From: client@bigcorp.com (王总)
Subject: Re: Re: 产品报价咨询

您好，

报价方案已收到，有几个后续问题：
1. 如果采购量增加到 100 人，是否有额外折扣？
2. 实施周期大约多久？
3. 能否安排一次线上产品演示？

希望本周内能确认，我们下周要向董事会汇报。

王总
```

---

## B.3 演示流程

### Step 1：展示"Before" —— 系统默认回复

对 Boss 和客户的邮件分别生成回复草稿（stance=agree），展示两者**风格一致**：

**Boss 回复（默认）：**
```
李经理好，

周五3点前的工作进展报告我会按时提交，内容将涵盖项目里程碑进度、
当前问题与风险、以及下周工作计划。

如需补充其他内容，请提前告知。
```
> ~60字，礼貌、完整、有结尾客套

**客户回复（默认）：**
```
王总好，

感谢对我们企业版产品的关注。针对您提到的三个问题，
我将整理详细的报价方案和技术信息，预计明日发送给您。

考虑到月底评估的时间节点，如需进一步沟通请随时联系。
```
> ~65字，礼貌、完整、有结尾客套

**观众看到**：两个回复结构和语气几乎一样 —— 称呼 + 正文 + 客套结尾。

---

### Step 2：用户操作 —— 编辑 Boss 回复

用户把 Boss 回复从上面的 60 字改成：

```
好的李经理，周五3点前发您。
```

> 12 字，极简。

**系统反应**：`executor` 检测到 similarity < 0.95，提取出记忆：

```
memory_type: response_pattern
memory_key: boss@company.com        ← 绑定到 Boss 这个发件人
content: {
  context: "与上级沟通",
  preference: "极简直接，不需要客套和结尾语",
  tone: "简短",
  pattern: "用户和 boss@company.com 沟通时偏好简短风格"
}
confidence: 0.75
```

注意：**这条记忆的 memory_key 是 `boss@company.com`**，不是全局的。

用户**不编辑**客户回复（直接采用 AI 生成的默认版本）。

---

### Step 3：展示"After" —— 新邮件到了

Boss 和客户各来了一封新邮件（邮件 3 和邮件 4），系统再次生成回复草稿：

**Boss 回复（个性化后）：**
```
李经理，周末前给您，来得及。
```
> 12 字，极简，和用户上次的编辑风格一致。

**客户回复（未受影响）：**
```
王总好，

关于后续问题：
1. 100 人授权有阶梯折扣，我会在报价方案中注明
2. 标准实施周期约 2-4 周，私有化部署可能需要额外时间
3. 线上演示本周可以安排，我来协调时间

考虑到下周董事会汇报的节点，我争取本周三前把完整方案发给您。
```
> ~90字，正式、详尽、有结构 —— 和之前一样。

---

## B.4 对比总结

| | Boss 回复 Before | Boss 回复 After | 客户回复 Before | 客户回复 After |
|---|---|---|---|---|
| 字数 | ~60 | **~12** | ~65 | ~90 |
| 风格 | 礼貌完整 | **极简直接** | 礼貌完整 | 礼貌完整 |
| 称呼 | "李经理好" | "李经理" | "王总好" | "王总好" |
| 结尾 | "如需补充...请提前告知" | 无 | "请随时联系" | "争取本周三前..." |
| 变化 | | **大幅简化** | | **基本不变** |

**一句话总结**：用户只改了给 Boss 的回复，系统就学会了"和 Boss 沟通要简短"，但给客户的回复依然保持正式详尽 —— **个性化精确到每一个联系人**。

---

## B.5 演示脚本流程

```
Step 1  注入邮件 1（Boss）和邮件 2（客户）
Step 2  运行 analyzer
Step 3  生成两封邮件的回复草稿（stance=agree）
        ── 展示 "Before"：两个回复风格一致 ──

Step 4  模拟用户编辑 Boss 回复（60字→12字）
Step 5  触发 executor → 写入 response_pattern 记忆（key=boss@company.com）
        ── 验证记忆已写入 ──

Step 6  注入邮件 3（Boss 新邮件）和邮件 4（客户新邮件）
Step 7  运行 analyzer
Step 8  生成两封新邮件的回复草稿（stance=agree）
        ── 展示 "After"：Boss 回复变简短，客户回复不变 ──
```

---

# 测试执行

## 前置条件

1. ClawMail REST API server 运行中 (`http://127.0.0.1:9999`)
2. OpenClaw gateway 运行中 (`http://127.0.0.1:18789`)

## 自动化脚本

`tests/test_personalization.py`：

```bash
# 方案 A：双用户对比
python tests/test_personalization.py --mode dual-user

# 方案 B：单用户回复个性化旅程
python tests/test_personalization.py --mode journey
```
