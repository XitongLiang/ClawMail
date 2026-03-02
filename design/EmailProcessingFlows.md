# ClawMail 核心处理流程

---

## 一、新邮件收到后的处理流程

```
IMAP 服务器
    │
    │  新邮件到达
    ▼
ClawMail IMAP Sync
    │  存入 SQLite（emails 表）
    │  触发 AI 分析
    ▼
ai_processor.process_email()
    │  subprocess 调用
    ▼
clawmail-analyzer / analyze_email.py
    │
    ├─── 取数据 ──────────────────────────────────────────────────────┐
    │    GET /emails/{id}                         ← 完整邮件正文      │
    │    确定发件人 sender_email（已发送取收件人）                     │
    │    GET /memories/{account_id}/for-email      ← 按发件人过滤记忆 │
    │      ?sender_email={sender_email}                               │
    │      返回: 全局偏好 + 该发件人 + 该域名的记忆                   │
    │    GET /pending-facts/{account_id}           ← 已有 pending     │
    │    读 USER.md                                ← 用户侧写         │
    │    读 references/prompts/                    ← 评分/摘要规则    │
    └─────────────────────────────────────────────────────────────────┘
    │
    ▼
【LLM 调用 ×1】邮件分析 + 事实提取（合并为单次调用）
    输入: 邮件 + 记忆 + 用户侧写 + 线程历史(如有) + 分析规则 + 已有pending facts
    输出（单个 JSON）: {
        summary: { one_line, brief, keywords }
        action_items: [...]
        metadata: {
            importance_scores: { sender/urgency/deadline/complexity 四维原始分 }
            categories, sentiment, is_spam, reply_stances, ...
        }
        pending_facts: [{ fact_key, category, content, confidence }]
    }
    │
    ▼
Python 后处理（不调 LLM）
    ├─ importance 加权计算: score = s×0.30 + u×0.25 + d×0.25 + c×0.20
    └─ 拆出 pending_facts（不写入 ai-metadata）
    │
    ├─ POST /emails/{id}/ai-metadata  → 写回分析结果
    │
    │  pending_facts 按 fact_key 前缀分流：
    ├─ contact.*  → POST /memories/{account_id} → 直接写入 MemoryBank（关系记忆，立即生效）
    ├─ project.*  → POST /memories/{account_id} → 直接写入 MemoryBank（项目有时效性，可更新/清理）
    └─ career/org → POST /pending-facts/{account_id} → pending 池（稳定属性，需积累验证）
                                │
                                └─ POST /pending-facts/{account_id}/promote → 检查提升阈值
    │
    ▼
达到阈值的 pending fact（career/org）→ 追加到 USER.md
    │
    ▼
ClawMail UI 刷新
    显示: 摘要 / 重要性评分 / 分类标签 / 行动项 / 回复立场建议
```

---

## 一b、已发送邮件的处理流程

```
IMAP/Graph 同步已发送文件夹
    │
    │  email_synced signal
    ▼
AIService._process_with_retry()
    │  email.folder == "已发送" → is_sent = True
    ▼
ai_processor.process_email(is_sent=True)
    │  subprocess: analyze_email.py --is-sent
    ▼
clawmail-analyzer / analyze_email.py（轻量路径）
    │
    ├─── 取数据 ──────────────────────────────────────────────────────┐
    │    GET /emails/{id}                         ← 完整邮件正文      │
    │    确定收件人 sender_email（已发送取第一个收件人）               │
    │    GET /memories/{account_id}/for-email      ← 按收件人过滤记忆 │
    │      ?sender_email={recipient_email}                            │
    │    GET /pending-facts/{account_id}                              │
    │    读 USER.md                                ← 用户侧写         │
    │    读 sent_email_guide.md                    ← 已发送分析指南   │
    │    读 profile_extraction.md                  ← 事实提取规则     │
    └─────────────────────────────────────────────────────────────────┘
    │
    ▼
【LLM 调用 ×1】轻量分析（无 importance / spam / categories）
    输入: 邮件正文 + 收件人画像 + 记忆 + 用户侧写 + 提取规则
    输出（JSON）: {
        summary: { one_line, brief, keywords }
        pending_facts: [{ fact_key, category, content, confidence }]
    }
    │
    ▼
Python 后处理
    ├─ 补全默认值（action_items=[], is_spam=false, importance=0 等）
    ├─ POST /emails/{id}/ai-metadata  → 写回摘要（其余字段为默认值）
    │
    │  pending_facts 按 fact_key 前缀分流（与收件邮件相同）：
    ├─ contact.{收件人}.* → POST /memories/{account_id} → 直接写入 MemoryBank
    ├─ project.*          → POST /memories/{account_id} → 直接写入 MemoryBank
    └─ career/org         → POST /pending-facts/{account_id} → pending 池 → promote
    │
    ▼
效果：
    后续收到回复时，generate_reply.py 可从线程上下文中
    获取已发送邮件的 one_line 摘要（而非 body_text[:200] 截断）
```

---

## 二、回复草稿生成流程

```
用户操作
    │  选择回复立场（stance）+ 语气（tone）
    │  可选：填写补充说明（user_notes）
    ▼
ClawMail UI (compose_dialog.py)
    │  调用 ai_processor.generate_reply_draft()
    ▼
ai_processor.py
    │  subprocess 调用
    ▼
clawmail-reply / generate_reply.py
    │
    ├─── 取数据 ──────────────────────────────────────────────────────┐
    │    GET /emails/{id}                         ← 原始邮件全文      │
    │    GET /emails/{id}/ai-metadata             ← AI 分析结果       │
    │    确定发件人 sender_email                                      │
    │    GET /memories/{account_id}/for-email      ← 按发件人过滤记忆 │
    │      ?sender_email={sender_email}                               │
    │    GET /emails/thread/{thread_id}            ← 线程历史(最近4封)│
    │    读 USER.md                                ← 用户侧写         │
    │    读 references/prompts/                    ← 回复规则/语气    │
    └─────────────────────────────────────────────────────────────────┘
    │
    ▼
构建 Prompt
    system: 用户侧写 + 偏好记忆 + 回复规则 + 语气风格定义
    user:   原始邮件（主题 / 发件人 / 正文[:4000]）
            + 对话历史（如有线程）
            + 意图判断指引（6种意图类型）
            + 发件人语气识别指引
            + 用户选择的立场 + 目标语气
    │
    ▼
【LLM 调用】回复生成
    先判断: 意图类型 + 发件人语气级别
    然后生成: 符合立场、语气、意图结构的回复正文
    输出: 纯文本（无 JSON 包装）
    │
    │  print to stdout
    ▼
ai_processor.py 读取 stdout
    │  返回纯文本正文
    ▼
UI 显示草稿
    用户可编辑后发送
    │
    ▼ （发送后）
用户对草稿有修改？
    │ YES
    ▼
clawmail-executor / extract_preference.py
    分析"AI 草稿 vs 用户最终版"的差异
    → 提取回复风格偏好 → 写入 MemoryBank
    （下次生成回复时自动注入）
```

---

## 三、用户修正后的个性化学习流程

```
用户行为（5种触发点）
    │
    │  ── 显式反馈 ──
    ├── 修改重要性评分（importance_score 变化 ≥ 10）
    ├── 给摘要差评（rating = "bad"）
    ├── 编辑并发送回复草稿
    │
    │  ── 隐式行为信号 ──
    ├── 点击未读邮件（implicit_open → 正向信号：用户认为这封邮件重要）
    └── 删除未读邮件（implicit_delete_unread → 负向信号：用户认为不重要）
    │
    ▼
ClawMail app.py
    _run_executor_skill(feedback_type, feedback_data, email_id)
    │  async subprocess（不阻塞 UI）
    ▼
clawmail-executor / extract_preference.py
    │
    ├─── 取数据 ──────────────────────────────────────────┐
    │    GET /emails/{id}           ← 触发修正的邮件数据   │
    │    GET /memories/{account_id} ← 现有偏好记忆         │
    │    读 memory_types.md         ← 5 种技能定义         │
    └─────────────────────────────────────────────────────┘
    │
    ▼
构建 Prompt
    原始预测（AI 的判断）vs 用户修正/行为（用户的反馈）
    + 邮件上下文 + 现有记忆 + 5种技能指引
    │
    ▼
【LLM 调用】偏好分析
    输出: [{ operation: INSERT/UPDATE/DELETE, memory_type, key, content }]
    │
    │  POST /memories/{account_id}  → 写入/更新/删除记忆条目
    ▼
MemoryBank 更新完成
    写入来源有两处：
    ① analyze_email.py 分析时 contact.* facts 直接写入（无需用户触发）
    ② extract_preference.py 用户反馈后写入/更新/删除（显式修正 + 隐式行为）
    下次分析同类邮件时，记忆自动注入到 analyze_email.py 的 prompt
```

---

## 组件依赖总览

```
ClawMail (PyQt UI + FastAPI Server + SQLite)
    │
    │  subprocess
    ├──────────────────────────────────────────┐
    │                                          │
    ▼                                          ▼
clawmail-analyzer                     clawmail-reply
  analyze_email.py                      generate_reply.py
    (--is-sent 轻量路径)                generate_email.py
  get_email.py                          polish_email.py
  ...
    │                                   extract_habits.py
    │  subprocess
    ▼
clawmail-executor
  extract_preference.py

所有 skill 脚本共同依赖:
  ├── ClawMail REST API (http://127.0.0.1:9999)
  │     /emails/{id}  /memories/  /pending-facts/  /emails/thread/
  ├── OpenClaw LLM Gateway (http://127.0.0.1:18789/v1/chat/completions)
  └── ~/.openclaw/workspace/USER.md
```

---

## 记忆注入机制

### 记忆的全生命周期

```
                    ┌─────────────────────────────────────────────┐
                    │              MemoryBank                      │
                    │         (user_preference_memory 表)          │
写入 ←──────────────┤                                             │
  ① analyzer 分析邮件时提取:                                       │
     contact.*   关系记忆（张三是你同事）                           │
     project.*   项目状态（alpha项目开发中）                        │
  ② executor 用户修正时提取:                                       │
     sender_importance  发件人重要性偏好                            │
     urgency_signal     紧急信号偏好                               │
     automated_content  自动化邮件偏好                              │
     summary_preference 摘要风格偏好                                │
     response_pattern   回复风格偏好                                │
                    │                                             │
读取 ←──────────────┤                                             │
  analyzer / reply 分析下一封邮件时注入 prompt                     │
                    └─────────────────────────────────────────────┘

                    ┌─────────────────────────────────────────────┐
                    │              USER.md                         │
                    │     (~/.openclaw/workspace/USER.md)          │
写入 ←──────────────┤                                             │
  pending_facts 表积累 career/org 事实                             │
  confidence 达阈值 → promote → 追加到 USER.md                    │
                    │                                             │
读取 ←──────────────┤                                             │
  所有 skill 的 system prompt 通过 read_user_profile() 注入       │
                    └─────────────────────────────────────────────┘
```

### 记忆过滤（读取时）

每次分析邮件或生成回复时，记忆不是全量注入，而是经过两层过滤：

**第一层：按发件人过滤（REST API 层）**

```
GET /memories/{account_id}/for-email?sender_email=alice@company.com

SQL: WHERE memory_key IS NULL           ← 全局偏好（对所有邮件生效）
       OR memory_key = 'alice@company.com'  ← 该发件人的记忆
       OR memory_key = 'company.com'        ← 该域名的记忆
```

| 场景 | 端点 | 返回 |
|------|------|------|
| 分析收件邮件 | `for-email?sender_email=发件人` | 全局 + 发件人 + 域名 |
| 分析已发送邮件 | `for-email?sender_email=收件人` | 全局 + 收件人 + 域名 |
| 生成回复 | `for-email?sender_email=回复对象` | 全局 + 回复对象 + 域名 |
| 撰写新邮件 | `for-email`（无参数） | 仅全局偏好 |
| 润色邮件 | `for-email`（无参数） | 仅全局偏好 |
| executor 用户修正 | `/memories/{account_id}`（全量） | 全部（需要判断 UPDATE/INSERT） |

**第二层：按类型 TTL 过滤（format_memories 层）**

过滤掉过期的记忆，不同类型衰减速度不同：

| memory_type | TTL | 理由 |
|-------------|-----|------|
| contact | **永不过期** | 人际关系不会因为几个月没联系就失效 |
| project_state | **90 天** | 项目有时效性，过期信息干扰判断 |
| sender_importance | **180 天** | 用户偏好变化慢 |
| urgency_signal | **180 天** | 同上 |
| automated_content | **180 天** | 同上 |
| summary_preference | **180 天** | 同上 |
| response_pattern | **180 天** | 同上 |

**第三层：按用途分段注入（format_memories only_types 过滤）**

记忆不再作为一个扁平列表注入，而是按影响域拆分后注入到 prompt 的对应规则区域，
避免 LLM 混淆不同用途的偏好：

```
analyzer prompt（收件邮件）:

    ## 摘要规则
    {summary_guide.md}
    ### 用户摘要偏好（历史反馈学习）       ← 仅 summary_preference 类型
    - 全局: {"preference_type": "keywords", "desired": "包含项目名"} (2周前)

    ## 重要性评分规则
    {importance_algorithm.md}
    ### 用户重要性偏好（历史反馈学习）       ← 仅 sender_importance / urgency_signal / automated_content
    - hr@company.com: {"typical_score": 30, "pattern": "HR邮件用户通常评低分"} (2周前)
    - noreply@github.com: {"content_type": "notification", "typical_score": 70} (3天前)

reply prompt:
    ## 用户回复偏好                          ← 仅 response_pattern
    - 全局: {"preference": "简短回复", "tone": "轻松"} (1个月前)
```

**第四层：年龄标签（LLM 自主判断）**

每条记忆注入 prompt 时附带年龄标签，LLM 可自行判断权重：
- `(2天前)` → 近期信号，权重高
- `(3个月前)` → 较旧，权重低
- 超过 TTL 的记忆直接过滤不注入

---

## AI 记忆查看器

用户可在 设置 → AI 记忆 面板中查看和管理已学习的偏好：

```
设置对话框
    │
    ├── 已学习记忆：N 条
    ├── [查看 AI 记忆]  → 打开记忆查看器子对话框
    └── [清除全部 AI 记忆]
    │
    ▼
记忆查看器（按影响域合并分组）
    │
    ── 重要性评分（3 条）──
      [发件人重要性] hr@company.com: HR邮件评低分  (70%)
      [紧急信号] 全局: 用户认为"验收"不算紧急  (65%)
      [自动化内容] noreply@github.com: CI通知较重要  (60%)
    ── 摘要生成（1 条）──
      [摘要偏好] 全局: 关键词应包含具体项目名  (75%)
    ── 回复生成（1 条）──
      [回复风格] boss@co.com: 回复老板用正式语气  (80%)
    │
    ├── 点击选中 → 底部显示详情（类型、键、置信度、证据数、创建时间、完整内容）
    └── [删除选中记忆] → 删除单条错误记忆
```
