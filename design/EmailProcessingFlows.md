# ClawMail 核心处理流程

---

## 一、新邮件收到后的处理流程

```
IMAP/Graph 服务器
    │
    │  新邮件到达
    ▼
SyncService (sync_service.py)
    │  IMAP: fetch_new_emails() / Graph: fetch_folder_delta()
    │  存入 SQLite（emails 表，INSERT OR IGNORE 按 hash 去重）
    │  发射 email_synced(email_id) 信号
    ▼
AIService (ai_service.py)
    │  收到 email_synced → enqueue(email_id)
    │  异步队列（maxsize=500），指数退避重试（5s / 15s / 60s，最多 3 次）
    │  跳过: 草稿箱、已删除
    ▼
ai_processor.process_email()
    │  subprocess 调用（timeout=120s）
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
AIService 后处理
    ├─ 双向垃圾邮件检测：
    │   is_spam=true  且在 INBOX    → 自动移到 垃圾邮件
    │   is_spam=false 且在 垃圾邮件 → 自动移回 INBOX
    ├─ 主动行动检测（仅收件邮件）：
    │   detect_proactive_actions(meta) → 发射 proactive_actions_detected 信号
    └─ 发射 email_processed(email_id, "processed") → UI 刷新
    │
    ▼
ClawMail UI 刷新
    显示: 摘要 / 重要性评分 / 分类标签 / 行动项 / 回复立场建议
    INBOX 按重要性排序（未读优先，按 importance_score 降序）
    其他文件夹按时间排序
```

---

## 一b、已发送邮件的处理流程

```
IMAP/Graph 同步已发送文件夹
    │
    │  email_synced signal
    │  注意：已发送邮件入库时 read_status 强制设为 "read"
    ▼
AIService._process_with_retry()
    │  email.folder == "已发送" → is_sent = True
    │  已发送邮件不触发主动行动检测
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

注意：已发送邮件不触发 Learner（importance=0 是设计预期，非 skill 缺陷）
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
    │  subprocess 调用（timeout=120s）
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
【LLM 调用 ×1】回复生成
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
    │ YES（相似度 < 阈值）
    ▼
clawmail-learner / extract_preference.py
    分析"AI 草稿 vs 用户最终版"的差异
    → 提取回复风格偏好 → 写入 MemoryBank
    （下次生成回复时自动注入）
```

---

## 二b、新邮件撰写流程

```
用户操作
    │  点击"撰写"按钮
    │  输入主题（subject）+ 大纲/要点（outline）
    ▼
ClawMail UI (compose_dialog.py)
    │  调用 ai_processor.generate_email()
    ▼
ai_processor.py
    │  subprocess 调用（timeout=120s）
    ▼
clawmail-reply / generate_email.py
    │
    ├─── 取数据 ──────────────────────────────────────────────────────┐
    │    GET /memories/{account_id}/for-email      ← 仅全局偏好       │
    │    读 USER.md                                ← 用户侧写         │
    │    读 references/prompts/                    ← 回复规则/语气    │
    └─────────────────────────────────────────────────────────────────┘
    │
    ▼
【LLM 调用 ×1】邮件生成
    输入: 主题 + 大纲 + 用户侧写 + 偏好记忆 + 写作规则
    输出: 纯文本（print to stdout）
    │
    ▼
UI 显示草稿 → 用户编辑 → 发送
```

---

## 二c、邮件润色流程

```
用户操作
    │  在编辑器中写好正文 → 点击"润色"按钮
    ▼
ClawMail UI (compose_dialog.py)
    │  调用 ai_processor.polish_email()
    ▼
ai_processor.py
    │  subprocess 调用（timeout=120s）
    ▼
clawmail-reply / polish_email.py
    │
    ├─── 取数据 ──────────────────────────────────────────────────────┐
    │    GET /memories/{account_id}/for-email      ← 仅全局偏好       │
    │    读 USER.md                                ← 用户侧写         │
    │    读 references/prompts/polish_guide.md     ← 润色规则         │
    └─────────────────────────────────────────────────────────────────┘
    │
    ▼
【LLM 调用 ×1】润色
    输入: 原文 body[:4000] + 用户侧写 + 偏好记忆 + 润色规则
    输出: 纯文本（print to stdout）
    │
    ▼
UI 替换编辑器内容 → 用户可继续编辑 → 发送
```

---

## 二d、用户撰写习惯提取

```
用户通过 compose_dialog 发送邮件/回复
    │
    │  发送成功后自动触发（两个入口）：
    │  ① compose_dialog.py → _trigger_habit_extraction()
    │  ② server.py → POST /send-reply 成功后触发
    ▼
clawmail-reply / extract_habits.py
    │  subprocess 后台执行（不阻塞 UI）
    │
    ├─── 取数据 ──────────────────────────────────────────────────────┐
    │    GET /pending-facts/{account_id}           ← 已有 pending     │
    │    读 USER.md                                ← 用户侧写         │
    │    读 references/prompts/profile_extraction.md                   │
    └─────────────────────────────────────────────────────────────────┘
    │
    ▼
【LLM 调用 ×1】习惯提取
    输入: 用户撰写的邮件内容（subject, to, body, is_reply）
          + 用户侧写 + 提取规则 + 已有 pending facts
    输出（JSON）: { pending_facts: [...] }
    │
    ▼
    ├─ POST /pending-facts/{account_id}            → 写入 pending 池
    └─ POST /pending-facts/{account_id}/promote    → 检查提升阈值 → USER.md
```

---

## 三、用户修正后的个性化学习流程

```
用户行为（5种触发点）
    │
    │  ── 显式反馈 ──
    ├── 修改重要性评分（importance_score 变化 ≥ 10）
    ├── 给摘要差评（rating = "bad"）
    ├── 编辑并发送回复草稿（相似度 < 阈值）
    │
    │  ── 隐式行为信号 ──
    ├── 点击未读邮件（implicit_open → 正向信号：用户认为这封邮件重要）
    └── 删除未读邮件（implicit_delete_unread → 负向信号：用户认为不重要）
    │
    │  注意：已发送文件夹的邮件不触发以上任何学习
    │
    ▼
ClawMail app.py
    _launch_learner(feedback_type, feedback_data, email_id)
    │  asyncio.ensure_future（不阻塞 UI）
    ▼
clawmail-learner / extract_preference.py
    │
    ├─── 取数据 ──────────────────────────────────────────┐
    │    GET /emails/{id}           ← 触发修正的邮件数据   │
    │    GET /memories/{account_id} ← 现有偏好记忆（全量） │
    │    读 memory_types.md         ← 记忆类型定义         │
    │    读 memory_extraction_guide.md ← 偏好提取规则      │
    └─────────────────────────────────────────────────────┘
    │
    ▼
构建 Prompt
    原始预测（AI 的判断）vs 用户修正/行为（用户的反馈）
    + 邮件上下文 + 现有记忆 + 记忆类型指引
    │
    ▼
【LLM 调用 ×1】偏好分析
    输出分类：
    ├─ user_preference → 正常偏好记忆
    └─ skill_defect    → AI 客观错误（如误分类），记入 _source=skill_defect
    │
    输出: [{ operation: INSERT/UPDATE/DELETE, memory_type, key, content }]
    │
    │  POST /memories/{account_id}  → 写入/更新/删除记忆条目
    ▼
MemoryBank 更新完成
    写入来源有两处：
    ① analyze_email.py 分析时 contact.*/project.* facts 直接写入（无需用户触发）
    ② extract_preference.py 用户反馈后写入/更新/删除（显式修正 + 隐式行为）
    下次分析同类邮件时，记忆自动注入到 analyzer / reply 的 prompt
    │
    ▼
累计写入计数
    每次 learner 成功写入后，_memory_writes_since_clean += count
    累计 ≥ 10 条 → 自动触发 optimizer 记忆清洗（见流程四）
```

---

## 四、Optimizer 元 Skill（自动优化 + 记忆清洗）

```
触发方式（两种）：
    ├── 自动触发：learner 累计写入 ≥ 10 条新记忆
    └── 手动触发：记忆面板点击「清洗」按钮

    ┌──────────────────────────────────────────────────┐
    │  模式一：记忆清洗 (--mode clean)                  │
    └──────────────────────────────────────────────────┘
    │
    ▼
clawmail-optimizer / optimize.py --mode clean --account-id <id>
    │
    ├─── 取数据 ──────────────────────────────────────────┐
    │    GET /memories/{account_id}    ← 全量记忆          │
    └─────────────────────────────────────────────────────┘
    │
    ▼
【LLM 调用 ×1】记忆清洗分析
    规则：
    ├─ 合并重复：同 type + 同/相似 key → 合并为一条，evidence_count 累加
    ├─ 解决矛盾：同 key 但 content 冲突 → 保留高证据/更新鲜的
    └─ 标注缺陷：_source=skill_defect 的记忆 → 提取缺陷描述
    │
    ├─ POST /memories/{account_id} → 更新/删除/合并记忆
    ├─ 清洗发现 skill_defect → 自动触发对应 --mode optimize
    └─ 刷新记忆面板
    │
    ▼
    ┌──────────────────────────────────────────────────┐
    │  模式二：Prompt 优化 (--mode optimize)            │
    └──────────────────────────────────────────────────┘
    │
    ├─── 取数据 ──────────────────────────────────────────┐
    │    GET /personalization/feedback/{prompt_type}       │
    │    GET /memories/{account_id}                        │
    │    读取目标 prompt 文件                               │
    └─────────────────────────────────────────────────────┘
    │
    ▼
前置检查
    ├─ 反馈数 < 3 → 跳过（MIN_FEEDBACK_COUNT）
    └─ 同 prompt-type 24h 内已优化 → 跳过（速率限制）
    │
    ▼
【LLM 调用 ×1】Prompt 重写
    输入: 当前 prompt + 用户反馈模式 + 缺陷描述
    输出: 优化后的 prompt 文本
    │
    ▼
安全写入
    ├─ 自动备份到 .backups/（最多保留 10 个版本）
    ├─ 结构校验：LLM 输出必须保留原有 section headers
    └─ 写入新 prompt 文件

prompt-type 映射：
    ├─ email_generation  → reply_guide.md, tone_styles.md
    ├─ polish_email      → polish_guide.md
    ├─ importance_score   → importance_algorithm.md
    └─ summary           → summary_guide.md

回滚：python rollback.py --prompt-type <type> --target <file> --version latest
```

---

## 五、待办任务自动处理流程（Task Handler）

```
触发方式：
    ├── 用户说"处理我的待办"/"帮我回复那封关于XX的邮件"
    └── ClawMail 发送任务处理请求（带 task_id）
    │
    ▼
clawmail-task-handler / task_handler.py（由 OpenClaw LLM Agent 驱动）
    │
    ▼
┌──────────────────────────────────────────────────────┐
│ 第一步：获取待办任务列表                               │
│   GET /tasks?status=pending&limit=20                  │
│   按优先级排序（high → medium → low），逐个处理        │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────┐
│ 第二步：深度分析每个任务                               │
│   GET /tasks/{task_id}           ← 任务详情            │
│   GET /tasks/{task_id}/email     ← 关联原邮件          │
│   GET /emails/{id}/ai-metadata   ← action_items 等     │
│                                                        │
│   从 action_items 提取：                                │
│   ├─ 需要做什么（回复/提供文件/确认时间/提交数据）      │
│   ├─ 需要哪些信息（报价单/简历/项目进度/合同条款）      │
│   └─ 截止时间（是否紧急）                               │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────┐
│ 第三步：主动搜集所需资料（按顺序直到足够）             │
│                                                        │
│   1. 搜索 OpenClaw 记忆                                │
│      openclaw memory search "<关键词>"                  │
│      → 用户偏好、历史决策、联系人、项目背景             │
│                                                        │
│   2. 搜索本地文件                                       │
│      find ~ / grep -r → 报价单、简历、合同等           │
│                                                        │
│   3. 搜索历史邮件                                       │
│      clawmail-manager/search_emails.py "<关键词>"       │
│      → 同发件人往来、同主题讨论                         │
│                                                        │
│   策略：找不到时不写占位符，                            │
│         邮件中明确说明"该信息暂时无法确认，稍后补充"    │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────┐
│ 第四步：调用 clawmail-reply 撰写邮件（不自己写）       │
│                                                        │
│   clawmail-reply / generate_reply.py                   │
│     --email-id {id}                                    │
│     --account-id {id}                                  │
│     --stance "{从 action_item 提炼的回复立场}"          │
│     --user-notes "{第三步搜集到的所有资料}"              │
│                                                        │
│   user-notes 示例：                                     │
│     【记忆】项目报价历史：¥80,000–¥120,000              │
│     【文件】~/Documents/报价单.xlsx 第3行：¥85,000      │
│     【历史邮件】张三提到预算上限 ¥100,000               │
│     【附件文件】~/Documents/报价单.xlsx（可随邮件发送） │
│                                                        │
│   输出: 纯文本邮件正文（stdout）                        │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────┐
│ 第五步：显示确认弹窗（必须）                           │
│                                                        │
│   POST /ui/confirm-dialog                              │
│   选项：                                                │
│     ├── ✅ 确认发送                                     │
│     ├── ✏️ 打开撰写窗口编辑后发送                       │
│     └── ⏭️ 跳过此任务                                   │
│   超时：60 秒                                           │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────┐
│ 第六步：根据用户选择执行                               │
│                                                        │
│   确认发送 → POST /send-reply → POST /tasks/{id}/complete │
│   编辑发送 → POST /compose（预填内容+附件路径）         │
│   跳过     → 继续下一个任务，不标记完成                 │
└──────────────────────────────────────────────────────┘
    │
    ▼
循环处理下一个 pending 任务，直到全部处理完毕
```

---

## 组件依赖总览

```
ClawMail (PyQt6 UI + FastAPI Server + SQLite)
    │
    │  subprocess 调用
    ├─────────────────────────────────────────────────────────────┐
    │                    │                    │                    │
    ▼                    ▼                    ▼                    ▼
clawmail-analyzer   clawmail-reply      clawmail-learner    clawmail-optimizer
  analyze_email.py    generate_reply.py   extract_preference.py  optimize.py
  get_email.py        generate_email.py                          rollback.py
  get_latest_unread   polish_email.py
                      extract_habits.py

                      ▼
              clawmail-manager            clawmail-task-handler
                list_emails.py              task_handler.py
                search_emails.py            (调用 clawmail-reply
                mark_email.py                生成回复草稿)
                move_email.py
                email_stats.py
                ...

所有 skill 脚本共同依赖:
  ├── ClawMail REST API (http://127.0.0.1:9999)
  │     /emails/{id}  /emails/{id}/ai-metadata  /emails/thread/{thread_id}
  │     /memories/{account_id}  /memories/{account_id}/for-email
  │     /pending-facts/{account_id}  /pending-facts/{account_id}/promote
  │     /personalization/feedback/{type}
  │     /tasks  /tasks/{id}  /tasks/{id}/complete
  │     /send-reply  /compose  /ui/confirm-dialog
  ├── OpenClaw LLM Gateway (http://127.0.0.1:18789/v1/chat/completions)
  │     模型: kimi-k2.5
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
     contact.*              关系记忆（张三是你同事）               │
     contact_direction.*    信息流向                               │
     contact_comm_pattern.* 沟通模式                               │
     project.*              项目状态（alpha项目开发中）            │
  ② learner 用户修正时提取:                                        │
     sender_importance      发件人重要性偏好                       │
     urgency_signal         紧急信号偏好                           │
     automated_content      自动化邮件偏好                         │
     summary_preference     摘要风格偏好                           │
     response_pattern       回复风格偏好                           │
  ③ learner 发现 skill 缺陷:                                      │
     任意 type + _source=skill_defect  AI 客观错误记录            │
  ④ optimizer 清洗:                                                │
     合并重复 / 解决矛盾 / 提取缺陷                               │
                    │                                             │
读取 ←──────────────┤                                             │
  analyzer / reply / polish 分析下一封邮件时注入 prompt           │
                    └─────────────────────────────────────────────┘

                    ┌─────────────────────────────────────────────┐
                    │              USER.md                         │
                    │     (~/.openclaw/workspace/USER.md)          │
写入 ←──────────────┤                                             │
  pending_facts 表积累 career/org 事实                             │
  confidence 达阈值 → promote → 追加到 USER.md                    │
  extract_habits.py 提取用户撰写习惯 → pending → promote         │
                    │                                             │
读取 ←──────────────┤                                             │
  所有 skill 的 system prompt 通过 read_user_profile() 注入       │
                    └─────────────────────────────────────────────┘
```

### 记忆过滤（读取时）

每次分析邮件或生成回复时，记忆不是全量注入，而是经过多层过滤：

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
| learner 用户修正 | `/memories/{account_id}`（全量） | 全部（需要判断 UPDATE/INSERT） |

**第二层：按类型 TTL 过滤（format_memories 层）**

过滤掉过期的记忆，不同类型衰减速度不同：

| memory_type | TTL | 理由 |
|-------------|-----|------|
| contact | **永不过期** | 人际关系不会因为几个月没联系就失效 |
| contact_direction | **永不过期** | 同上 |
| contact_comm_pattern | **永不过期** | 同上 |
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

## AI 记忆面板

独立圆角浮窗，紧贴主窗口右侧，树形分组 + 右侧详情面板。

```
主窗口工具栏 → 点击「🧠 记忆」按钮
    │
    ▼
记忆面板（MemoryPanel，QDialog，FramelessWindowHint + 圆角）
    │
    ├── 标题栏：「🧠 AI 记忆 (N)」 + [清洗] + [✕]
    │
    ├── 左侧树形列表（按影响域分组）
    │   ├── 📊 重要性评分（3 条）
    │   │     [发件人重要性] hr@company.com: HR邮件评低分
    │   │     [紧急信号] 全局: 用户认为"验收"不算紧急
    │   │     [自动化内容] noreply@github.com: CI通知较重要
    │   ├── 👤 联系人画像（2 条）
    │   │     [联系人关系] alice@co.com: 同事，项目经理
    │   │     [沟通模式] bob@co.com: 周报型沟通
    │   ├── ✍ 回复风格（1 条）
    │   │     [回复风格] boss@co.com: 回复老板用正式语气
    │   ├── 📝 摘要偏好（1 条）
    │   │     [摘要偏好] 全局: 关键词应包含具体项目名
    │   ├── 📁 项目状态（1 条）
    │   │     [项目状态] alpha: 开发中，预计下月交付
    │   └── 🐛 Skill 缺陷（橙色高亮，独立分组）
    │         [缺陷] AI 将客户邮件误分类为广告
    │
    ├── 右侧详情面板
    │   ├── 类型 + 分组标签
    │   ├── 键（发件人/全局）
    │   ├── 置信度进度条 + 百分比
    │   ├── 元信息（证据次数 · 创建日期）
    │   └── 完整内容
    │
    └── 底部操作栏
        └── [🗑 删除选中] → 确认对话框 → 删除单条记忆
```

---

## 同步机制

```
SyncService (sync_service.py)
    │
    ├── 支持两种协议：
    │   ├── IMAP（非 Microsoft 账号）— ClawIMAPClient
    │   └── Microsoft Graph API — GraphSyncClient
    │
    ├── 同步文件夹：
    │   ├── IMAP:  ["INBOX", "垃圾邮件", "已发送"]
    │   └── Graph: [("inbox", "INBOX"), ("junkemail", "Junk Email"), ("sentitems", "Sent Items")]
    │
    ├── 增量同步：
    │   ├── IMAP: 基于 UID 游标（sync_cursor JSON 存 DB）
    │   └── Graph: 基于 deltaLink（按文件夹独立追踪）
    │
    ├── 已发送邮件特殊处理：
    │   └── read_status 强制设为 "read"（发出的邮件不应标为未读）
    │
    ├── 重试：最多 3 次，退避 [2, 4, 8] 秒
    │   认证错误（IMAPAuthError / GraphAuthError）不重试
    │
    └── 信号：
        ├── email_synced(email_id) → AIService 入队
        ├── sync_done(count)       → UI 刷新
        ├── sync_error(msg)        → 状态栏提示
        └── sync_started()         → 进度指示
```
