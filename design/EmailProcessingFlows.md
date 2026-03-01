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
    ├─── 取数据 ──────────────────────────────────────────┐
    │    GET /emails/{id}          ← 完整邮件正文          │
    │    GET /memories/{account_id} ← 用户偏好记忆         │
    │    读 USER.md                ← 用户侧写（职位/习惯） │
    │    读 references/prompts/    ← 评分规则/摘要规则等   │
    └─────────────────────────────────────────────────────┘
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
    ├─ contact.* facts → POST /memories/{account_id}   → 直接写入 MemoryBank（立即生效）
    └─ 其他 facts      → POST /pending-facts/{account_id} → pending 池
                                │
                                └─ POST /pending-facts/{account_id}/promote → 检查提升阈值
    │
    ▼
达到阈值的 pending fact（career/org/project）→ 追加到 USER.md
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
    ├─── 取数据 ──────────────────────────────────────────┐
    │    GET /emails/{id}          ← 完整邮件正文          │
    │    GET /memories/{account_id} ← 用户偏好记忆         │
    │    GET /pending-facts/{account_id}                   │
    │    读 USER.md                ← 用户侧写              │
    │    读 sent_email_guide.md    ← 已发送邮件分析指南    │
    │    读 profile_extraction.md  ← 事实提取规则          │
    └─────────────────────────────────────────────────────┘
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
    └─ career/org/project → POST /pending-facts/{account_id} → pending 池 → promote
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
    ├─── 取数据 ──────────────────────────────────────────┐
    │    GET /emails/{id}              ← 原始邮件全文      │
    │    GET /emails/{id}/ai-metadata  ← AI 分析结果       │
    │    GET /memories/{account_id}    ← 用户偏好记忆      │
    │    GET /emails/thread/{thread_id}← 线程历史(最近4封) │
    │    读 USER.md                    ← 用户侧写          │
    │    读 references/prompts/        ← 回复规则/语气定义 │
    └─────────────────────────────────────────────────────┘
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
用户修正行为（3种触发点）
    │
    ├── 修改重要性评分（importance_score 变化 ≥ 10）
    ├── 给摘要差评（rating = "bad"）
    └── 编辑并发送回复草稿
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
    原始预测（AI 的判断）vs 用户修正（用户的行为）
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
    ② extract_preference.py 用户修正后写入/更新/删除
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
