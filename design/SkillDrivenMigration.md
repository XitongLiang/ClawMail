# Skill-Driven Migration Plan

将 ClawMail 的 AI 智能功能全部迁移到 OpenClaw Skill 层。

## 目标

ClawMail 不再自己编排 AI（不再拼 prompt、不再直接调 LLM），而是作为 OpenClaw 的一个 skill runtime：
- **ClawMail** = 数据层 (IMAP sync + SQLite) + UI 层 (PyQt)
- **OpenClaw Skills** = 所有 AI 智能逻辑

---

## 核心流程

### 新邮件到达

```
1. IMAP 同步 → ClawMail 存入新邮件
2. ClawMail 通知 analyzer skill（发送邮件数据 + 用户记忆 + 用户侧写）
3. Analyzer skill 处理：
   a. 融合：分析基准线(references/) + 用户侧写(USER.md) + 用户记忆(MemoryBank)
   b. 调 LLM → 输出结构化结果（summary + score + categories + action_items + ...）
   c. 提取事实性信息 → 写入 pending facts（不直接写 USER.md）
   d. 检查 pending facts 池 → 同一事实多次出现且置信度足够 → 提升到 USER.md
4. 结果返回 ClawMail → 存入 EmailAIMetadata
5. UI 更新显示
```

### 用户撰写/回复邮件

```
1. 用户起草新邮件 / 编辑回复草稿 / 发送邮件
2. ClawMail 通知 reply skill（用户撰写的内容 + 上下文）
3. Reply skill (extract_habits.py) 提取用户习惯信息：
   a. 写作风格（正式/随意、长短、语气）
   b. 常用表达和签名习惯
   c. 回复速度偏好（哪类邮件回复快、哪类慢）
   d. 提取结果 → 写入 pending facts
4. Pending facts 累积后提升到 USER.md
```

### 用户修正（个性化学习）

```
1. 用户修改重要性评分 / 给摘要差评 / 编辑回复草稿
2. ClawMail 通知 executor skill（原始预测 + 用户修正 + 邮件数据）
3. Executor skill 处理：
   a. 对比差异，分析用户修正背后的偏好
   b. 调 LLM → 输出记忆操作（insert/update/delete）
   c. 更新 MemoryBank（偏好信息）
4. 后续邮件分析时，记忆被注入到 analyzer skill 中
```

### 两种信息的分工

| | 事实性信息 (USER.md) | 偏好信息 (MemoryBank) |
|---|---|---|
| **提取时机** | 新邮件到达时（analyzer） + 用户撰写/回复时（reply） | 用户修正 AI 预测时（被动） |
| **提取者** | analyzer skill（收到邮件）+ reply skill（用户撰写） | executor skill |
| **内容** | 联系人关系、项目上下文、组织结构、职业信息（analyzer）；写作习惯、沟通风格（reply） | 重要性偏好、摘要风格、回复风格 |
| **置信度** | 渐进式：pending → 累积验证 → 提升到 USER.md | 较高（有用户明确意图） |
| **存储位置** | pending: ClawMail SQLite / 确认后: `~/.openclaw/workspace/USER.md` | ClawMail SQLite (user_preference_memory 表) |
| **注入方式** | OpenClaw 自动注入到所有 skill | 通过 REST API 取出后注入到 prompt |

---

## 需要迁移的功能

| 功能 | 现在在哪里 | 迁移到哪个 Skill |
|------|-----------|-----------------|
| 邮件摘要 (summary) | ai_processor.py `process_email()` | clawmail-analyzer |
| 重要性评分 (importance score) | ai_processor.py `process_email()` | clawmail-analyzer |
| 分类/标签 (category) | ai_processor.py `process_email()` | clawmail-analyzer |
| 垃圾邮件检测 (is_spam) | ai_processor.py `process_email()` | clawmail-analyzer |
| 行动项提取 (action_items) | ai_processor.py `process_email()` | clawmail-analyzer |
| 回复立场建议 (reply_stances) | ai_processor.py `process_email()` | clawmail-analyzer |
| 事实性信息提取 (profile update) | 无（新增） | clawmail-analyzer |
| 用户习惯提取 (user habits) | 无（新增） | clawmail-analyzer |
| 回复草稿生成 (reply draft) | ai_processor.py `generate_reply_draft()` | clawmail-reply (新) |
| 新邮件生成 (generate email) | ai_processor.py `generate_email()` | clawmail-reply (新) |
| 邮件润色 (polish) | ai_processor.py `polish_email()` | clawmail-reply (新) |
| 用户偏好提取 (executor) | executor.py | clawmail-executor (新) |
| 技能演化 (designer) | designer.py | clawmail-personalization (已有，扩展) |

---

## 设计原则

### ClawMail 直接调用 Skill 脚本，不经过 LLM 路由

ClawMail 通过 `subprocess` 直接调用 skill 脚本（如 `analyze_email.py`），不通过 `bridge.user_chat()` 让 LLM 判断该不该调 skill。这确保每个事件触发哪个脚本是代码写死的，LLM 不能跳过或替代。

```
ClawMail ai_processor.py
    → subprocess.run(["python", "analyze_email.py", "--email-id", id])
        → 脚本调 LLM API → 获取结果 → 写回 REST API
```

### Skill 脚本控制流程，LLM 只回答问题

Skill 脚本定义**确定性的执行步骤**：每一步调 LLM 问什么、传什么 prompt、期望什么输出格式，都由脚本控制。LLM 不决定流程，只负责在给定 prompt 下产出结构化结果。

```python
# analyzer skill 的执行流程（脚本控制）
def analyze(email, memories, user_profile):
    # Step 1: 摘要 + 分类 + 评分（一次 LLM 调用，合并相关任务）
    analysis = llm(
        prompt = build_prompt(email, summary_guide, importance_algo, category_rules),
        context = [user_profile, memories],
        output_schema = "summary + score + categories + action_items JSON"
    )

    # Step 2: 事实提取 → 写入 pending facts（不直接改 USER.md）
    pending_facts = llm(
        prompt = build_prompt(email, profile_extraction_rules),
        context = [current_user_md, existing_pending_facts],
        output_schema = "[{fact, category, confidence, source_email_id}]"
    )
    api.post(f"/pending-facts/{account_id}", pending_facts)

    # Step 3: 检查是否有 pending fact 达到提升阈值
    api.post(f"/pending-facts/{account_id}/promote")

    return analysis

# 用户撰写/回复邮件时也会触发（提取习惯信息）
def analyze_user_compose(compose_data, user_profile):
    habits = llm(
        prompt = build_prompt(compose_data, habit_extraction_rules),
        context = [current_user_md, existing_pending_facts],
        output_schema = "[{fact, category, confidence, source}]"
    )
    api.post(f"/pending-facts/{account_id}", habits)
    api.post(f"/pending-facts/{account_id}/promote")
```

**关键**：
- 每个 LLM 调用的 prompt 由 references/ 中的基准线文档 + 运行时上下文（记忆、侧写）拼接而成
- 脚本决定调几次、每次问什么；LLM 不自由发挥
- 输出格式在 prompt 中明确要求 JSON，脚本负责解析和验证

### References 文件分两类

```
references/
├── prompts/                  ← 可被 personalization skill 演化修改
│   ├── importance_algorithm.md   — 评分权重和规则
│   ├── summary_guide.md          — 摘要风格和长度
│   ├── category_rules.md         — 分类标准
│   ├── profile_extraction.md     — 事实提取规则
│   └── habit_extraction.md       — 用户习惯提取规则
└── specs/                    ← 接口契约，不可修改
    ├── output_schema.md          — 输出 JSON 结构
    ├── field_definitions.md      — 字段类型定义
    └── error_codes.md            — 错误码
```

`prompts/` 是 LLM 的行为指令，personalization skill 可以根据用户反馈演化这些文件。
`specs/` 是接口规范，改了会导致 ClawMail 解析出错，不允许修改。

---

## Skill 规划

### 1. clawmail-analyzer (已有，需补全)

**位置**: `~/.openclaw/workspace/skills/clawmail-analyzer/`

**现状**: SKILL.md + references/ 已有完整规格，`analyze_email.py` 是 stub

**需要做**:
- [ ] 补全 `analyze_email.py`，让它真正调用 LLM 分析
- [ ] 新增事实性信息提取逻辑（联系人、项目、组织关系 → pending facts）
- [ ] 新增用户习惯提取逻辑（用户撰写/回复时触发 → pending facts）
- [ ] 实现 pending facts → USER.md 提升机制
- [ ] 确保输出格式能映射回 EmailAIMetadata

**覆盖功能**: summary, importance_score, category, is_spam, action_items, reply_stances, profile_update, user_habits

---

### 2. clawmail-reply (新建)

**位置**: `~/.openclaw/workspace/skills/clawmail-reply/`

**需要创建**:
- [ ] SKILL.md — 接口定义
- [ ] references/reply_guide.md — 回复生成规格
- [ ] references/tone_styles.md — 语气风格定义 (正式/礼貌/轻松/简短)
- [ ] references/polish_guide.md — 润色规格
- [ ] scripts/generate_reply.py — 回复生成入口
- [ ] scripts/generate_email.py — 新邮件生成入口
- [ ] scripts/polish_email.py — 润色入口

**覆盖功能**: reply_draft, generate_email, polish_email

---

### 3. clawmail-executor (新建)

**位置**: `~/.openclaw/workspace/skills/clawmail-executor/`

**职责**: 用户修正 AI 预测后，分析差异并提取偏好记忆

**现在在**: `clawmail/infrastructure/personalization/executor.py`（ClawMail 内部）

**需要创建**:
- [ ] SKILL.md — 接口定义（输入：原始预测 + 用户修正 + 邮件数据 + 已有记忆）
- [ ] references/memory_extraction_guide.md — 偏好提取规则
- [ ] references/memory_types.md — 5 种记忆类型定义
- [ ] scripts/extract_preference.py — 偏好提取入口

**覆盖功能**: importance 修正 → 记忆, summary 差评 → 记忆, reply 编辑 → 记忆

---

### 4. clawmail-personalization (已有，扩展)

**位置**: `~/.openclaw/workspace/skills/clawmail-personalization/`

**现状**: 已能根据反馈优化 prompts/*.txt

**扩展**:
- [ ] 吸收 designer.py 的技能演化功能
- [ ] 从优化 prompts/*.txt 改为优化 skill references/ 文档
- [ ] 分析 executor 的失败案例，改进提取策略

---

## ClawMail 侧改动 ✅ 已实现

### REST API 端点（已全部实现）

| 端点 | 方法 | 用途 | 状态 |
|------|------|------|------|
| `GET /emails/{id}` | GET | Skill 获取邮件完整数据 | ✅ |
| `GET /emails/{id}/ai-metadata` | GET | Skill 获取已有分析结果 | ✅ |
| `POST /emails/{id}/ai-metadata` | POST | Skill 写入分析结果 | ✅ |
| `GET /emails/unprocessed` | GET | Skill 获取待分析邮件列表 | ✅ |
| `GET /memories/{account_id}` | GET | Skill 获取用户偏好记忆 | ✅ |
| `POST /memories/{account_id}` | POST | Executor skill 写入偏好记忆 | ✅ |
| `GET /pending-facts/{account_id}` | GET | Skill 获取当前 pending facts | ✅ |
| `POST /pending-facts/{account_id}` | POST | Analyzer skill 写入新 pending fact | ✅ |
| `POST /pending-facts/{account_id}/promote` | POST | 将达标的 pending fact 提升到 USER.md | ✅ |

### ai_processor.py 改动（已实现）

`process_email()` / `generate_reply_draft()` / `generate_email()` / `polish_email()` 已改为 thin wrapper：
1. 优先通过 `subprocess` 触发对应的 OpenClaw skill 脚本
2. Skill 脚本通过 REST API 读写数据
3. Skill 失败时自动 fallback 到旧的 prompt-based LLM 调用路径

---

## 迁移顺序

### Phase 1: ClawMail 数据层 + REST API ✅ 已完成
- ✅ 新增 pending_facts 表 + CRUD 方法
- ✅ 新增 9 个 REST API 端点
- ✅ ClawMail 的 process_email() 改为调用 skill（保留 fallback）

### Phase 2: ClawMail AI 层迁移 ✅ 已完成
- ✅ ai_processor.py 所有方法改为 try skill → fallback legacy
- ✅ 用户撰写时触发习惯提取 hook
- ✅ ClawMail 的 reply/generate/polish 改为调用 skill

### Phase 3: Skill 侧补全（待实施）
- 补全 clawmail-analyzer analyze_email.py
- 创建 clawmail-reply SKILL.md + references/ + scripts/
- 创建 clawmail-executor SKILL.md + references/ + scripts/

### Phase 4: 清理（待 Phase 3 完成后）
- 移除 ai_processor.py 中的 prompt 模板
- 移除 ~/clawmail_data/prompts/*.txt 依赖
- 更新 clawmail-personalization skill 改为修改 skill references

---

## 已决定的设计问题

### 1. 基准线 (Baseline) 定义

基准线 = skill 的 `references/prompts/` 目录中的文档。这是最基本的 prompt，没有融合用户记忆、没有个性化。运行时由脚本将基准线 + 用户侧写(USER.md) + 用户记忆(MemoryBank) 拼接成完整 prompt。

personalization skill 的演化目标就是修改这些基准线文件，让它们逐步适应用户偏好。

### 2. 同步调用

初期采用同步方式。ClawMail 调用 skill 后同步等待结果返回，不引入异步回调机制。理由：
- 实现简单，不需要通知/轮询机制
- 现有的 `bridge.user_chat()` 已经是同步等待模式
- 邮件分析不需要实时响应，等几秒可以接受

### 3. 不保留离线 fallback

OpenClaw gateway 没启动时，AI 功能不可用。理由：
- 维护两套 AI 路径（本地 + skill）成本太高
- 迁移完成后 ai_processor.py 的 prompt 逻辑会被清理
- 用户可以正常浏览邮件，只是没有 AI 分析

### 4. 记忆存储留在 ClawMail SQLite

MemoryBank（偏好记忆）继续存在 ClawMail 的 SQLite `user_preference_memory` 表中。Skills 通过 REST API 读写：
- `GET /memories/{account_id}` — analyzer/reply skill 读取记忆注入 prompt
- `POST /memories/{account_id}` — executor skill 分析用户修正后写入新记忆

完整流程：
```
用户修正 → ClawMail 通知 executor skill
         → executor skill 调 LLM 分析差异
         → executor skill 调 POST /memories/{account_id} 写入记忆
         → 后续 analyzer skill 调 GET /memories/{account_id} 读取记忆
```

### 5. 事实提取：Pending Memory 机制

不直接写入 USER.md，而是通过 pending facts 池渐进式验证：

```
邮件/用户撰写 → analyzer skill 提取事实
                     ↓
              写入 pending facts 池（带置信度 + 来源邮件ID）
                     ↓
              同一事实被多封邮件佐证 → 置信度累加
                     ↓
              置信度超过阈值 → 提升到 USER.md
```

**举例**：
- 职业信息：第1封邮件推断出"可能是科技行业" (0.4) → 第3封邮件确认"软件工程师" (0.7) → 第5封邮件有明确签名"Senior Engineer @ XYZ" (0.95) → 写入 USER.md
- 联系人关系：多封邮件中 Alice 出现在 CC 且讨论同一项目 → 逐步确认"Alice 是项目组成员"
- 写作习惯：用户连续3次回复邮件都用简短风格 → 确认"偏好简短回复"

**信息来源**（两个触发点）：
1. **收到邮件时**（被动接收）：提取发件人关系、项目上下文、组织结构、行业/职位线索
2. **用户撰写/回复时**（主动行为）：提取写作风格、常用表达、回复习惯、语气偏好

**存储**：pending facts 存在 ClawMail SQLite 中，通过 REST API 供 skill 读写

---

## 已解决的开放问题

### 6. Skill 执行环境（已解决）

**结论**：Skill 脚本自己拼 prompt 调 LLM API，不依赖 gateway 的 LLM 路由。

Gateway 只作为 LLM 的 HTTP 代理（OpenAI 兼容 API on port 18789），skill 脚本读取 `references/` 文档自行构建 prompt、调 LLM、解析结构化 JSON 输出。ClawMail 通过 `subprocess` 直接调用脚本，脚本完全控制执行流程。

### 7. Reply skill 的规格（已解决）

**结论**：已在 `SkillDesign.md` 中完整设计。

clawmail-reply 包含 3 个脚本（generate_reply.py, generate_email.py, polish_email.py），4 个 reference 文档（reply_guide.md, tone_styles.md, polish_guide.md, generate_email_guide.md）。Reply skill 通过 stdout 直接返回文本结果（不通过 REST API 写入 DB），因为回复内容是临时的，由 ClawMail 的 ai_processor 从 `result.stdout.strip()` 读取。

### 8. Pending facts 存储设计（已解决）

**结论**：已在 `ClawMailChanges.md` 中完整设计。

`pending_facts` 表包含 id, user_account_id, fact_key, fact_category, fact_content, confidence, evidence_count, source_emails (JSON), status, promoted_at, created_at, updated_at。有唯一索引 `(user_account_id, fact_key)` 用于 upsert。置信度累加规则：`new_confidence = min(1.0, existing.confidence + new_confidence * 0.3)`。

### 9. 提升阈值（已解决）

**结论**：按 category 设不同阈值，已在 `ClawMailChanges.md` 中定义。

career(0.75), contact(0.60), organization(0.70), project(0.55), writing_habit(0.65), communication_style(0.65)。

### 10. Analyzer LLM 调用次数（已解决）

**结论**：保持 2 次独立 LLM 调用，不合并。

Call 1: 邮件分析（summary + categories + importance + action_items + reply_stances）。Call 2: 事实提取（pending facts）。两个任务的思维方向不同，合并会降低质量。

### 11. Executor 触发时机（已解决）

**结论**：每次用户修正立即触发 executor skill，不做批量。

理由：用户修正是高价值信号（明确的用户意图），及时提取偏好记忆更有意义。personalization skill 的技能演化则是周期性的，需要积累足够反馈数据。

---

## 当前状态

所有开放问题已解决。设计文档已拆分为两份详细实现文档：
- `SkillDesign.md` — OpenClaw Skill 侧实现细节
- `ClawMailChanges.md` — ClawMail 侧实现细节

### ClawMail 侧实现进度

**✅ Phase 1: 数据层准备 — 已完成**
- [x] 新增 `pending_facts` 表（DDL + 索引 + 旧数据库兼容）
- [x] 新增 `upsert_pending_fact()`, `get_pending_facts()`, `get_pending_fact()`, `promote_pending_facts()`, `dismiss_pending_fact()` 方法
- [x] 新增 `get_email_full()`, `get_unprocessed_emails()` 方法
- [x] 新增 9 个 REST API 端点（邮件数据 4 个 + Memory 2 个 + Pending Facts 3 个）
- [x] `_append_facts_to_user_md()` 辅助函数
- [x] 路由顺序：`/emails/unprocessed` 在 `/emails/{email_id}` 之前

**✅ Phase 2: AI 层迁移 — 已完成**
- [x] `ai_processor.py` 添加 6 个 skill 脚本路径常量
- [x] `process_email()` 重构为 try skill → fallback legacy
- [x] `generate_reply_draft()` 重构为 try skill → fallback legacy
- [x] `generate_email()` 重构为 try skill → fallback legacy
- [x] `polish_email()` 重构为 try skill → fallback legacy
- [x] `compose_dialog.py` 添加发送后习惯提取 hook
- [x] `server.py /send-reply` 端点添加习惯提取触发

**✅ Phase 3: Legacy 清理 — 已完成**
- [x] 移除 ai_processor.py 中的旧 prompt 模板代码（~450 行删除）
- [x] 移除 `~/clawmail_data/prompts/*.txt` 依赖（storage_manager.py 初始化清理）
- [x] 移除 legacy fallback 路径（所有方法改为纯 skill 调用）
- [x] 移除 server.py 的 `GET /personalization/prompt/{type}` 和 `POST /personalization/update-prompt` 端点
- [x] 简化 AIProcessor 构造函数为 `AIProcessor(data_dir)` （6 处调用已适配）

### OpenClaw Skill 侧实现进度

- [x] clawmail-analyzer: 补全 `analyze_email.py`
- [x] clawmail-reply: 新建 SKILL.md + references/ + scripts/
- [x] clawmail-executor: 新建 SKILL.md + references/ + scripts/
- [ ] clawmail-personalization: 扩展为修改 skill references

