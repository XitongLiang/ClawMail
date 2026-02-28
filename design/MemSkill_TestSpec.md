# MemSkill 个性化系统 — 测试规格 (Test Spec)

> 本文档定义 MemSkill 各环节的输入/输出规格与验收标准。
> 覆盖三个目标任务：**重要性评分**、**摘要生成**、**回复起草**。

---

## 1. 系统输出规格

### 1.1 重要性评分 (Importance Scoring)

| 项目 | 规格 |
|------|------|
| 输出格式 | 整数 0-100 |
| 来源 | `process_email()` → `metadata.importance_score` |
| 无记忆时 | 纯靠 prompt 规则评分 |
| 有记忆时 | prompt 注入 `【用户偏好记忆】` 段，LLM 参考后评分 |

**评分参考基线（无记忆时）：**

| 场景 | 期望分数范围 | 判定依据 |
|------|-------------|---------|
| 上级紧急任务 (boss@, 【紧急】) | 80-100 | 发件人权重 + 紧急关键词 |
| 同事会议确认 | 50-70 | 需行动但非紧急 |
| 客户咨询 | 60-80 | 外部关系 + 待回复 |
| Newsletter / 自动通知 | 10-30 | 自动发送 + 无需行动 |
| 感谢/确认 (无行动) | 20-40 | 无需回复 |

**有记忆时的期望偏移：**

| 记忆内容 | 期望效果 |
|----------|---------|
| `sender_importance`: boss@company.com 评为 90 | 同一发件人新邮件分数上升 (>= 80) |
| `urgency_signal`: 用户不认为"请查收"紧急 | 包含"请查收"的邮件分数不应因此上升 |
| `automated_content`: noreply@xxx 一律低分 | 该发件人邮件 <= 20 |

### 1.2 摘要生成 (Summary)

| 项目 | 规格 |
|------|------|
| 输出格式 | JSON: `{keywords, one_line, brief, key_points}` |
| `keywords` | 3-5 个关键词，array of string |
| `one_line` | <= 20 字核心概括 |
| `brief` | 3-5 行标准摘要 |
| `key_points` | 2-5 条要点，每条一句话 |

**质量标准：**

| 维度 | 合格标准 | 不合格示例 |
|------|---------|-----------|
| 准确性 | 关键词覆盖邮件核心话题 | 关键词与邮件内容无关 |
| 完整性 | key_points 覆盖所有行动项 | 遗漏截止时间或负责人 |
| 简洁性 | one_line 能独立概括邮件意图 | one_line 是正文前 20 字截断 |
| 风格一致性（有记忆时） | 符合 `summary_preference` 要求 | 用户要求简短但输出冗长 |

### 1.3 回复起草 (Reply Draft)

| 项目 | 规格 |
|------|------|
| 输入 | `(email, stance, tone, user_notes, account_id)` |
| 输出格式 | 纯文本正文，不含主题行/JSON/Markdown |
| 立场 (`stance`) | 来自 `reply_stances`，2-4 个选项，每个 <= 30 字 |
| 语气 (`tone`) | 四选一：正式 / 礼貌 / 轻松 / 简短 |

**语气规格：**

| 语气 | 用词风格 | 目标长度 |
|------|---------|---------|
| 正式 | 规范书面语，不使用口语 | 150-250 字 |
| 礼貌 | 温和友好，适当感谢/歉意 | 100-200 字 |
| 轻松 | 口语化，简洁直接 | 50-100 字 |
| 简短 | 极简，只说核心 | 30-80 字 |

**质量标准：**

| 维度 | 合格标准 | 不合格示例 |
|------|---------|-----------|
| 立场一致 | 回复内容与选择的 stance 一致 | 选"拒绝"但回复同意了 |
| 语气匹配 | 长度和用词符合 tone 规格 | 选"简短"但输出 200 字 |
| 内容相关 | 回复针对原邮件的具体内容 | 泛泛而谈未提原邮件话题 |
| 格式规范 | 无"尊敬的XXX"开头，直接切入 | 输出了 JSON 或 Markdown |
| 风格一致性（有记忆时） | 符合 `response_pattern` 偏好 | 用户偏好直接给结论但先铺垫 |

---

## 2. 记忆系统规格

### 2.1 记忆类型与归属

| memory_type | 归属组 | 用于 | memory_key 含义 |
|------------|--------|------|----------------|
| `sender_importance` | 邮件分析 | 重要性评分 | 发件人邮箱 |
| `urgency_signal` | 邮件分析 | 重要性评分 | null（全局） |
| `automated_content` | 邮件分析 | 重要性评分 | 发件人邮箱或域名 |
| `summary_preference` | 邮件分析 + 回复起草 | 摘要 + 回复参考 | null（全局） |
| `response_pattern` | 回复起草 | 回复风格 | 收件人邮箱或 null |

### 2.2 记忆检索分组规格

| 检索方法 | 返回类型 | 不应返回 |
|----------|---------|---------|
| `retrieve_for_email()` | sender_importance, urgency_signal, automated_content, summary_preference | response_pattern |
| `retrieve_for_reply()` | response_pattern, summary_preference | sender_importance, urgency_signal, automated_content |

### 2.3 Executor 触发条件

| 触发点 | 条件 | 调用方法 |
|--------|------|---------|
| 重要性修正 | `abs(old - new) >= 10` | `execute_importance_feedback()` |
| 摘要差评 | 用户点 👎 | `execute_summary_feedback()` |
| 回复修改 | `SequenceMatcher ratio < 0.95` | `execute_reply_feedback()` |

### 2.4 Executor 输出规格

| 项目 | 规格 |
|------|------|
| 格式 | JSON 数组，以 `[` 开头 `]` 结尾 |
| op 类型 | `insert` / `update` / `delete` |
| 无偏好时 | 返回空数组 `[]` |
| 不允许 | 自然语言分析、Markdown 标记、代码块 |

**单条操作格式：**
```json
{"op": "insert", "memory_type": "sender_importance", "memory_key": "boss@company.com", "content": {"pattern": "..."}, "confidence": 0.7}
{"op": "update", "memory_id": "uuid", "content": {"pattern": "..."}, "confidence": 0.8}
{"op": "delete", "memory_id": "uuid", "reason": "已过时"}
```

---

## 3. 测试用例

### TC-01: 记忆分组过滤

**前置**：DB 中插入 5 条记忆，每种 memory_type 各 1 条，同一 account_id。

| 步骤 | 操作 | 期望结果 |
|------|------|---------|
| 1 | 调用 `retrieve_for_email(account_id, "test@example.com", "example.com")` | 返回 4 条：sender_importance, urgency_signal, automated_content, summary_preference |
| 2 | 验证返回列表中不存在 response_pattern | 无 response_pattern |
| 3 | 调用 `retrieve_for_reply(account_id, "test@example.com")` | 返回 2 条：response_pattern, summary_preference |
| 4 | 验证返回列表中不存在 sender_importance, urgency_signal, automated_content | 无邮件分析专用类型 |

### TC-02: 无 sender 信息的 fallback

**前置**：同 TC-01。

| 步骤 | 操作 | 期望结果 |
|------|------|---------|
| 1 | 调用 `retrieve_for_email(account_id)` （不传 sender） | 返回 4 条，仅邮件分析类型 |
| 2 | 确认不含 response_pattern | 无 response_pattern |

### TC-03: 重要性学习闭环

**前置**：空记忆库 + 已注入测试邮件（newsletter@techcompany.com, 主题: 周刊）。

| 步骤 | 操作 | 期望结果 |
|------|------|---------|
| 1 | 处理邮件，观察初始 importance_score | 分数在 10-30 范围（newsletter 类） |
| 2 | 手动改分为 5 | 触发 Executor，日志: `[MemSkill] 重要性反馈 → N 条记忆更新` |
| 3 | 查 DB: `SELECT * FROM user_preference_memory WHERE memory_type='sender_importance'` | 至少 1 条 INSERT，memory_key 为 newsletter@techcompany.com |
| 4 | 注入并处理 newsletter@techcompany.com 的新邮件 | prompt 日志中出现 `【用户偏好记忆】`，包含对应 pattern |
| 5 | 新邮件 importance_score 对比步骤 1 | 分数应更低（趋向用户修正的 5） |

### TC-04: 摘要学习闭环

**前置**：空记忆库 + 已处理邮件有摘要。

| 步骤 | 操作 | 期望结果 |
|------|------|---------|
| 1 | 对摘要点 👎，选择原因 "关键词不够具体"，补充 "希望包含截止日期" | 触发 Executor |
| 2 | 查 DB: `SELECT * FROM user_preference_memory WHERE memory_type='summary_preference'` | 至少 1 条 INSERT，content 含 "截止日期" 相关信息 |
| 3 | 处理新邮件 | prompt 注入 `摘要偏好` 段，包含步骤 2 的 pattern |

### TC-05: 回复学习闭环

**前置**：空记忆库 + 已处理邮件有 reply_stances。

| 步骤 | 操作 | 期望结果 |
|------|------|---------|
| 1 | 选择立场/语气，生成 AI 草稿 | 记录 `_ai_draft_text` |
| 2 | 大幅修改草稿（使其 similarity < 0.95），发送 | 触发 Executor，日志: `[MemSkill] 回复反馈` |
| 3 | 查 DB: `SELECT * FROM user_preference_memory WHERE memory_type='response_pattern'` | 至少 1 条 INSERT |
| 4 | 对同一发件人再次起草回复 | prompt 注入 `【用户回复风格偏好】` 段 |

### TC-06: Executor JSON 格式

**前置**：触发任意 Executor 调用。

| 步骤 | 操作 | 期望结果 |
|------|------|---------|
| 1 | 观察 Executor 原始返回 | 必须以 `[` 开头，以 `]` 结尾 |
| 2 | 确认不含自然语言分析 | 无 "分析"、"我来"、"##" 等文字 |
| 3 | `json.loads(raw)` 成功 | 返回 list |
| 4 | 每个 op 的 `memory_type` 在 5 种合法值内 | 无未知类型 |

### TC-07: 记忆注入不跨组

**前置**：DB 中有 response_pattern 记忆（key=boss@company.com）。

| 步骤 | 操作 | 期望结果 |
|------|------|---------|
| 1 | 处理 boss@company.com 的邮件（importance + summary） | prompt 中**不出现** `【用户回复风格偏好】` 或 response_pattern 内容 |
| 2 | 对 boss@company.com 起草回复 | prompt 中**出现** `【用户回复风格偏好】` |

### TC-08: 回复草稿格式规范

**前置**：处理一封邮件，获取 reply_stances。

| 步骤 | 操作 | 期望结果 |
|------|------|---------|
| 1 | tone="简短"，生成草稿 | 输出 <= 80 字 |
| 2 | tone="正式"，同一封邮件重新生成 | 输出 150-250 字，无口语 |
| 3 | 两次草稿内容 | 不含 JSON、Markdown、主题行 |
| 4 | 选"同意"stance 的草稿 | 内容表达同意意图 |
| 5 | 选"拒绝"stance 的草稿 | 内容表达婉拒意图 |

---

## 4. 验证方法

### 4.1 日志观察法（手动）

启动 app 后观察 console，关键日志前缀：
- `[MemSkill] 个性化组件初始化完成` — 启动正常
- `[MemSkill] 检索到 N 条记忆` — 记忆注入
- `[MemSkill] 重要性反馈 → N 条记忆更新` — Executor 执行成功
- `[MemSkill] INSERT: type=...` — 具体操作
- `[Executor] JSON 解析失败` — Executor 输出格式异常

### 4.2 DB 直查法

```bash
# 查看所有记忆
sqlite3 ~/clawmail_data/clawmail.db \
  "SELECT memory_type, memory_key, memory_content, confidence_score, evidence_count FROM user_preference_memory ORDER BY memory_type;"

# 按类型统计
sqlite3 ~/clawmail_data/clawmail.db \
  "SELECT memory_type, COUNT(*) FROM user_preference_memory GROUP BY memory_type;"

# 查看最近创建的记忆
sqlite3 ~/clawmail_data/clawmail.db \
  "SELECT * FROM user_preference_memory ORDER BY created_at DESC LIMIT 5;"
```

### 4.3 脚本验证法

使用 `tests/synthetic_email_injector.py` 注入测试邮件，按 TC 步骤操作后用 DB 查询验证结果。
