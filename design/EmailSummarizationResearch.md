# 邮件摘要设计研究

> 调研整理：好的邮件 AI 摘要应该怎么做，分解为哪些步骤，业界实践与评估标准。

---

## 1. 好的邮件摘要应该包含什么

一个优秀的邮件 AI 摘要不是简单的"缩短正文"，而是一次**结构化信息提取**，目标是让用户**不读原文也能做出决策**。

### 1.1 核心输出维度

| 维度 | 说明 | 示例 |
|------|------|------|
| **一句话摘要** (one_line) | 15-30 字，回答"这封邮件说了什么" | "张三汇报 Q4 项目进度，完成率 85%，预算超支 10%" |
| **关键要点** (key_points) | 3-5 条结构化要点，覆盖核心事实 | ["完成率 85%", "预算超支 10%", "需要额外人力支持"] |
| **关键词** (keywords) | 3-8 个标签，用于检索和分类 | ["Q4", "项目进度", "预算", "人力"] |
| **行动事项** (action_items) | 需要用户采取的具体行动 | [{text: "回复确认", deadline: "明天", priority: "high"}] |
| **情感倾向** (sentiment) | 邮件的情绪基调 | urgent / positive / negative / neutral |
| **重要性评分** (importance) | 0-100 的量化优先级 | 72（综合发件人权重、紧急度、截止日等） |
| **建议回复立场** (reply_stances) | 2-3 种可选的回复策略 | ["确认收到并查看", "询问具体细节", "转发相关同事"] |
| **分类标签** (categories) | 邮件类型分类 | ["pending_reply", "项目:Q4"] |
| **垃圾邮件检测** (is_spam) | 是否为垃圾/营销邮件 | true / false |

### 1.2 好摘要的质量标准

根据学术界和业界共识，高质量摘要需满足：

- **准确性 (Faithfulness)**：摘要中的事实必须可追溯到原文，不能"幻觉"
- **完整性 (Coverage)**：覆盖所有关键信息点，不遗漏重要决策或行动
- **简洁性 (Conciseness)**：去除冗余，同样的信息不重复表述
- **连贯性 (Coherence)**：要点之间逻辑通顺，不是孤立的碎片
- **可操作性 (Actionability)**：读完摘要后用户知道下一步该做什么

---

## 2. 处理流程（Pipeline）

### 2.1 单封邮件摘要流程

```
┌─────────────────────────────────────────────────────────┐
│  Step 1: 预处理 (Preprocessing)                          │
│  ├─ 清理 HTML → 纯文本                                   │
│  ├─ 去除签名块、免责声明、引用历史                          │
│  ├─ 正文截断（超长邮件取前 N 字符）                         │
│  └─ 提取元数据（发件人、时间、主题、收件人）                 │
├─────────────────────────────────────────────────────────┤
│  Step 2: 上下文构建 (Context Assembly)                    │
│  ├─ 注入发件人历史画像（MemoryBank 中的偏好记忆）           │
│  ├─ 注入用户个人信息（USER.md 中的身份/职业/关系）          │
│  └─ 注入线程上下文（同一 thread 的历史摘要）                │
├─────────────────────────────────────────────────────────┤
│  Step 3: LLM 统一提取 (Unified Extraction)                │
│  ├─ 单次 LLM 调用，结构化 JSON 输出                       │
│  ├─ 同时提取：摘要 + 关键词 + 行动事项 + 情感 + 分类       │
│  └─ 通过 JSON Schema 约束输出格式                         │
├─────────────────────────────────────────────────────────┤
│  Step 4: 后处理 (Post-processing)                         │
│  ├─ JSON 校验 + 字段补全（缺失字段用默认值）                │
│  ├─ 情感值范围校验（必须在合法枚举内）                      │
│  ├─ 重要性评分加权计算                                    │
│  └─ 垃圾邮件标记二次确认                                  │
├─────────────────────────────────────────────────────────┤
│  Step 5: 持久化 (Persistence)                             │
│  ├─ 写入 DB（ai_metadata 表）                             │
│  └─ 触发下游：偏好提取、pending_facts 更新                 │
└─────────────────────────────────────────────────────────┘
```

### 2.2 各步骤详解

#### Step 1: 预处理

**目的**：将原始邮件转化为 LLM 可高效处理的干净输入。

| 子步骤 | 技术手段 | 说明 |
|--------|---------|------|
| HTML → 纯文本 | `html2text` / BeautifulSoup | 保留段落结构，去除样式标签 |
| 去除签名块 | 正则 + 启发式规则 | 匹配 `--`、`Best regards` 等常见签名分隔符 |
| 去除引用历史 | 匹配 `>` 前缀行、`On ... wrote:` | 线程摘要单独处理，不混入当前邮件 |
| 正文截断 | 前 4000 字符 | 避免超出 LLM 上下文窗口，保留开头（关键信息集中区） |
| 元数据提取 | 从 Email 对象直接读取 | 发件人、时间、主题、收件人列表 |

> **研究发现**：邮件的**第一段**包含核心信息的概率高达 75%。截断时优先保留开头内容。

#### Step 2: 上下文构建

**目的**：为 LLM 提供个性化判断依据，使摘要不只是通用总结，而是"对这个用户有意义的"总结。

- **发件人画像**：从 MemoryBank 读取该发件人的历史特征（如"直属上司"、"经常发紧急任务"）
- **用户身份**：从 USER.md 读取用户的职业、部门、关注领域，帮助判断重要性
- **线程上下文**：如果邮件属于某个 thread，注入前序邮件的摘要，避免孤立理解

> **个性化是关键**：同一封邮件，对技术负责人和市场部员工的"重要性"完全不同。上下文注入让 LLM 从用户视角评估。

#### Step 3: LLM 统一提取

**目的**：一次调用完成所有维度的提取，避免多次 API 调用的成本和延迟。

**设计原则**：
- **单次调用**：将所有提取任务（摘要、关键词、行动事项、情感、分类、重要性、回复建议）合并到一个 prompt 中
- **结构化输出**：要求 LLM 返回严格的 JSON 格式，每个字段有明确的类型和约束
- **Abstractive 为主**：使用生成式摘要（用新的语句概括），而非抽取式（直接摘抄原文句子）

**为什么选择 Abstractive（生成式）而非 Extractive（抽取式）**：

| 维度 | Extractive (抽取式) | Abstractive (生成式) |
|------|-------------------|---------------------|
| 方法 | 从原文选取关键句子拼接 | 生成新的概括性句子 |
| 准确性 | 高（原文原句） | 可能有幻觉风险 |
| 可读性 | 差（句子间缺乏衔接） | 好（类似人类摘要） |
| 信息密度 | 低（句子中有冗余） | 高（精练表达） |
| 适用场景 | 法律文档等需原文引用 | 邮件摘要等日常场景 |

> 邮件摘要场景更适合 Abstractive，因为用户需要的是**快速理解**而非**精确引用**。通过 JSON Schema 约束 + 后处理校验来控制幻觉风险。

#### Step 4: 后处理

**目的**：确保 LLM 输出的健壮性，处理边界情况。

```python
# 后处理逻辑示例
def post_process(raw_json: dict) -> dict:
    # 1. 字段补全：缺失字段用默认值填充
    result = deep_merge(raw_json, DEFAULT_AI_RESULT)

    # 2. 枚举校验：sentiment 必须在合法范围内
    if result["metadata"]["sentiment"] not in VALID_SENTIMENTS:
        result["metadata"]["sentiment"] = "neutral"

    # 3. 数值范围：importance_score 必须在 0-100
    score = result["metadata"].get("importance_score")
    if score is not None:
        result["metadata"]["importance_score"] = max(0, min(100, int(score)))

    # 4. 列表长度：关键词不超过 8 个，行动事项不超过 10 个
    result["summary"]["keywords"] = result["summary"]["keywords"][:8]
    result["action_items"] = result["action_items"][:10]

    return result
```

#### Step 5: 持久化 & 下游触发

- 将结构化结果写入 `email_ai_metadata` 表
- 异步触发偏好提取（executor skill）：从邮件内容中提取用户习惯和事实
- 更新 `pending_facts` 表：累积置信度，达标后提升到 USER.md

---

## 3. 重要性评分（Importance Scoring）

### 3.1 加权模型

重要性评分不是一个简单数字，而是多维度加权的结果：

```
importance_score = Σ (weight_i × score_i)

维度          权重    评分依据
─────────────────────────────────────────
sender_weight   30%   发件人与用户的关系（上司=90, 同事=60, 陌生人=20）
urgency_weight  25%   邮件中的紧急程度信号（deadline、ASAP、催促语气）
deadline_weight 25%   是否有明确截止日期及距今天数
complexity_weight 20% 需要的回复/处理复杂度
```

### 3.2 评分信号

| 信号类型 | 高分指标 | 低分指标 |
|---------|---------|---------|
| 发件人 | 直属上司、重要客户、高频联系人 | 营销邮件、系统通知、陌生人 |
| 紧急度 | "ASAP"、"紧急"、"deadline tomorrow" | 无时间限制、FYI 性质 |
| 截止日 | 明确日期且 < 3 天 | 无截止日或 > 2 周 |
| 复杂度 | 需要决策、多个行动事项 | 纯信息通知、确认收到即可 |

> **个性化加权**：MemoryBank 中存储的发件人画像可以动态调整 sender_weight。如果用户过去总是优先回复某人，该发件人的权重自动提升。

---

## 4. 线程摘要（Thread Summarization）

### 4.1 挑战

邮件线程摘要面临独特的挑战：

- **非线性回复链**：转发、CC 增减、多人参与导致对话分叉
- **主题漂移**：一个线程中可能穿插多个话题
- **时间跨度**：跨天甚至跨周的线程，上下文随时间变化
- **重复引用**：每封回复都包含历史引用，大量冗余

### 4.2 处理策略

```
方案 A: 增量摘要（Incremental）— 推荐
───────────────────────────────
每封新邮件到达时：
  1. 读取该线程的"当前摘要"（已持久化）
  2. 将 [当前摘要 + 新邮件正文] 送入 LLM
  3. 生成更新后的线程摘要
  4. 覆盖存储

优点：低延迟，每次只处理增量
缺点：可能累积误差（摘要的摘要）

方案 B: 全量重摘要（MapReduce）
───────────────────────────────
定期或触发时：
  1. 收集线程中所有邮件
  2. 按时间排序，每封邮件分别摘要（Map）
  3. 将所有单封摘要合并，生成线程总摘要（Reduce）

优点：准确度高
缺点：成本高，延迟大
```

> Gmail Gemini 采用的是类似 MapReduce 的方式，能将 47 封邮件的线程在 10 秒内压缩为 3 条行动事项。但这依赖于 1M token 上下文窗口。对于本地 LLM 调用，推荐使用增量摘要。

---

## 5. Prompt 工程最佳实践

### 5.1 结构化 Prompt 模板

```
你是一个邮件分析助手。请分析以下邮件并以 JSON 格式返回结果。

## 用户背景
{user_context}

## 发件人画像
{sender_profile}

## 邮件内容
发件人: {from}
收件人: {to}
时间: {date}
主题: {subject}

{body}

## 输出要求
请返回以下 JSON 结构（严格遵守字段名和类型）：
{
  "summary": {
    "one_line": "15-30字的一句话摘要",
    "key_points": ["要点1", "要点2", "要点3"],
    "keywords": ["关键词1", "关键词2"]
  },
  "action_items": [
    {
      "text": "行动描述",
      "deadline": "截止日期或null",
      "priority": "high|medium|low",
      "assignee": "me|发件人名|其他人名"
    }
  ],
  "metadata": {
    "category": ["分类标签"],
    "sentiment": "urgent|positive|negative|neutral",
    "is_spam": false,
    "importance_score": 0-100,
    "importance_breakdown": {
      "sender_weight": 30, "sender_score": 0-100,
      "urgency_weight": 25, "urgency_score": 0-100,
      "deadline_weight": 25, "deadline_score": 0-100,
      "complexity_weight": 20, "complexity_score": 0-100
    },
    "reply_stances": ["建议回复立场1", "建议回复立场2"],
    "suggested_reply": "建议的简短回复"
  }
}
```

### 5.2 关键 Prompt 技巧

| 技巧 | 说明 |
|------|------|
| **输出格式先行** | 在 prompt 末尾放 JSON Schema，LLM 更倾向遵守 |
| **枚举约束** | sentiment 用 `"urgent\|positive\|negative\|neutral"` 明确列出合法值 |
| **数值范围** | importance_score 用 `"0-100"` 标注范围 |
| **示例驱动** | 对复杂字段（如 action_items）给一个完整示例 |
| **负面指令** | "不要编造邮件中未提及的事实"、"如果没有行动事项则返回空数组" |
| **角色设定** | "你是用户的邮件助手" 比 "你是 AI" 产出更贴合用户视角的摘要 |

---

## 6. 评估标准

### 6.1 自动化指标

| 指标 | 衡量什么 | 局限性 |
|------|---------|--------|
| **ROUGE-1** | 单词级重叠率 | 无法衡量语义相似度 |
| **ROUGE-2** | 双词组重叠率 | 惩罚合理的改写 |
| **ROUGE-L** | 最长公共子序列 | 对语序敏感 |
| **BERTScore** | 语义嵌入相似度 | 计算成本高 |

> ROUGE 适合基线对比，但**不适合**作为邮件摘要的唯一评估标准。邮件摘要更关注"可操作性"和"信息完整度"，这些需要人工评估。

### 6.2 人工评估维度

| 维度 | 评分标准 (1-5) |
|------|---------------|
| **准确性** | 摘要中的所有事实是否都能在原邮件中找到对应？ |
| **完整性** | 是否遗漏了重要信息或行动事项？ |
| **简洁性** | 是否有冗余信息？能否进一步精简？ |
| **可操作性** | 读完摘要后是否知道下一步该做什么？ |
| **个性化** | 重要性评分是否反映了该用户的实际优先级？ |

---

## 7. 业界参考

### 7.1 Gmail Gemini

- **触发条件**：邮件足够长或复杂时自动显示摘要卡片
- **输出格式**：1-2 句关键摘要 + 行动事项
- **上下文窗口**：1M token，可处理超长线程
- **特色**：自动识别截止日期、升级事件、行动事项

### 7.2 Microsoft Copilot (Outlook)

- **功能**：线程摘要 + 回复草稿 + 语气教练
- **上下文**：通过 Microsoft Graph 跨应用关联（邮件+文档+会议）
- **特色**：基于全局上下文的个性化摘要，不仅看邮件内容还看相关文档

### 7.3 共同趋势

1. **单次调用多维提取**：不再分多步调用，而是一次性提取所有维度
2. **个性化优先**：结合用户画像和历史行为定制摘要
3. **可操作性导向**：摘要的核心价值是"帮用户决定下一步"，而非"缩短原文"
4. **结构化输出**：JSON 格式输出，便于 UI 分区展示和下游处理

---

## 8. 对 ClawMail Analyzer Skill 的建议

基于以上调研，当前 `clawmail-analyzer` 的设计已覆盖大部分最佳实践：

### 已覆盖

- [x] 结构化 JSON 输出（summary, action_items, metadata）
- [x] 多维度统一提取（单次 LLM 调用）
- [x] 重要性加权评分（4 维度模型）
- [x] 情感分析 + 垃圾邮件检测
- [x] 回复立场建议
- [x] 个性化上下文注入（MemoryBank + USER.md）
- [x] 后处理校验 + 默认值补全

### 可优化方向

- [x] **预处理增强**：✅ 已实现签名块去除（`strip_signature`）和引用历史清理（`strip_quoted_content`），预处理在截断之前执行
- [x] **线程摘要**：✅ 已实现增量线程上下文注入，回复邮件自动获取历史摘要并注入 LLM prompt
- [x] **列表长度限制**：✅ 已在 skill 侧（`_enforce_list_limits`）和 ClawMail 侧（`_build_metadata`）双重截断
- [ ] **幻觉检测**：对 key_points 做原文回溯校验，确保可追溯
- [ ] **用户反馈闭环**：用户修改/忽略摘要时，记录为隐式反馈，优化后续提取（Executor 已部分实现）
- [ ] **分层摘要**：超长邮件使用 MapReduce 策略，先分段再合并

---

## 参考资料

- [Gmail AI Summaries That Actually Work](https://ucstrategies.com/news/gmail-just-solved-email-overload-with-ai-summaries-that-actually-work/)
- [Building an AI Email Assistant with LLMs](https://dev.to/malok/building-an-ai-email-assistant-that-prioritizes-sorts-and-summarizes-with-llms-34m8)
- [AI-Powered Email Summarization & Follow-up System](https://medium.com/@connectwidamit/how-i-built-an-ai-powered-email-summarization-follow-up-system-to-solve-business-efficiency-4f898654e3b7)
- [LLM Summarization Strategies](https://galileo.ai/blog/llm-summarization-strategies)
- [Microsoft ISE: GPT Summary Prompt Engineering](https://devblogs.microsoft.com/ise/gpt-summary-prompt-engineering/)
- [EmailSum: Abstractive Email Thread Summarization (ACL 2021)](https://aclanthology.org/2021.acl-long.537/)
- [Prompt Engineering for Email Summarization](https://ai47labs.com/prompts-engineering/prompt-email-summarization/)
- [Extractive vs. Abstractive Summarization](https://www.prodigaltech.com/blog/extractive-vs-abstractive-summarization-how-does-it-work)
- [How to Evaluate Abstractive Summarization (OpenAI Cookbook)](https://developers.openai.com/cookbook/examples/evaluation/how_to_eval_abstractive_summarization/)
- [ROUGE Metric for AI Summarization Quality](https://galileo.ai/blog/rouge-metric)
- [AI Email Summaries: Keep Email Clear](https://4thoughtmarketing.com/articles/ai-email-summaries-keep-email-clear/)
- [Designing Emails for Humans and AI](https://www.attentive.com/blog/email-marketing-strategy-google-gemini-2025)
