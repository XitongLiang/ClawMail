# ClawMail 侧改动设计

> **实现状态**：Phase 1（数据层 + REST API）、Phase 2（AI 层迁移）和 Phase 3（Legacy 清理）已全部完成。✅

本文档描述 Skill-Driven 迁移中 ClawMail 需要做的所有改动。
配套文档：`SkillDesign.md`（OpenClaw Skill 侧设计）。

---

## 改动概览

```
clawmail/
├── api/server.py              ← 新增 REST API 端点
├── infrastructure/
│   ├── database/
│   │   └── storage_manager.py ← 新增 pending_facts 表 + 查询方法
│   └── ai/
│       ├── ai_processor.py    ← 瘦身为 thin wrapper，不再拼 prompt
│       └── ai_service.py      ← 触发方式改变
└── ui/app.py                  ← 新增用户撰写时触发习惯提取
```

---

## 1. 新增数据库表：pending_facts

### 表结构

```sql
CREATE TABLE IF NOT EXISTS pending_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_account_id TEXT NOT NULL,
    fact_key TEXT NOT NULL,          -- 事实的唯一标识，如 "职业.职位", "联系人.Alice.关系"
    fact_category TEXT NOT NULL,     -- 分类：career, contact, organization, project, writing_habit, communication_style
    fact_content TEXT NOT NULL,      -- 事实内容（纯文本描述）
    confidence REAL NOT NULL DEFAULT 0.0,  -- 当前累积置信度 0.0-1.0
    evidence_count INTEGER NOT NULL DEFAULT 1,  -- 被多少封邮件/事件佐证
    source_emails TEXT NOT NULL DEFAULT '[]',    -- JSON 数组：佐证来源 [{email_id, extracted_at, individual_confidence}]
    status TEXT NOT NULL DEFAULT 'pending',      -- pending | promoted | dismissed
    promoted_at TEXT,               -- 提升到 USER.md 的时间
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_pending_facts_account ON pending_facts(user_account_id, status);
CREATE UNIQUE INDEX idx_pending_facts_key ON pending_facts(user_account_id, fact_key);
```

### 置信度累加规则

Skill 每次提交一个 pending fact 时携带 `individual_confidence`。ClawMail 侧负责累加：

```python
# 新 fact 到达时的更新逻辑
def upsert_pending_fact(self, account_id, fact_key, fact_category, fact_content, confidence, source_email_id):
    existing = self.get_pending_fact(account_id, fact_key)
    if existing and existing.status == 'pending':
        # 已存在：累加置信度（取更高值或加权平均）
        new_confidence = min(1.0, existing.confidence + confidence * 0.3)
        new_evidence = existing.evidence_count + 1
        sources = json.loads(existing.source_emails)
        sources.append({"email_id": source_email_id, "extracted_at": now(), "individual_confidence": confidence})
        # UPDATE ...
    else:
        # 新 fact：直接插入
        # INSERT ...
```

### 提升阈值

| fact_category | 提升阈值 | 说明 |
|---------------|---------|------|
| career | 0.75 | 职业信息需要较高确认 |
| contact | 0.60 | 联系人关系相对容易确认 |
| organization | 0.70 | 组织结构需要多次确认 |
| project | 0.55 | 项目信息变化快，低一点 |
| writing_habit | 0.65 | 需要多次撰写行为确认 |
| communication_style | 0.65 | 沟通风格需要多次确认 |

---

## 2. storage_manager.py 新增方法

### Pending Facts 相关

```python
def upsert_pending_fact(self, account_id: str, fact_key: str, fact_category: str,
                        fact_content: str, confidence: float, source_email_id: str) -> None:
    """插入或更新 pending fact，累加置信度。"""

def get_pending_facts(self, account_id: str, status: str = 'pending') -> list[dict]:
    """获取指定状态的 pending facts。"""

def get_pending_fact(self, account_id: str, fact_key: str) -> dict | None:
    """获取单个 pending fact。"""

def promote_pending_facts(self, account_id: str) -> list[dict]:
    """检查所有 pending facts，将达标的标记为 promoted 并返回。
    调用方（REST API handler）负责将 promoted facts 写入 USER.md。"""

def dismiss_pending_fact(self, account_id: str, fact_key: str) -> None:
    """手动驳回一个 pending fact。"""
```

### Email 数据查询（供 Skill 使用）

```python
def get_email_full(self, email_id: str) -> dict | None:
    """获取邮件完整数据（包括正文、附件信息），供 REST API 返回给 Skill。
    注意：body_text 截断到 4000 字符。"""

def get_unprocessed_emails(self, account_id: str, limit: int = 20) -> list[dict]:
    """获取 ai_status='unprocessed' 的邮件列表。"""
```

### Memory 查询（已有，确认接口）

已有方法可直接复用：
- `get_memories_for_email()` → 供 `GET /memories/{account_id}` 使用
- `upsert_memory()` → 供 `POST /memories/{account_id}` 使用

---

## 3. REST API 新增端点 (server.py)

### 3.1 GET /emails/{email_id}

Skill 获取邮件完整数据。

**Response 200**:
```json
{
    "id": "email_abc123",
    "subject": "Q4 项目进度汇报",
    "from_address": {"name": "张三", "email": "zhangsan@company.com"},
    "to_addresses": [{"name": "李四", "email": "lisi@company.com"}],
    "cc_addresses": [],
    "received_at": "2026-03-01T10:30:00",
    "body_text": "邮件正文内容...(截断到4000字符)",
    "body_html": "<html>...",
    "folder": "INBOX",
    "attachments": [
        {"filename": "report.pdf", "size": 102400}
    ],
    "read_status": "unread",
    "reply_status": "no_need",
    "thread_id": "thread_xyz"
}
```

**Response 404**: `{"error": "Email not found"}`

**实现参考**:
```python
@app.get("/emails/{email_id}")
async def get_email(email_id: str):
    email = _db.get_email_full(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return email
```

### 3.2 GET /emails/{email_id}/ai-metadata

Skill 获取已有的 AI 分析结果。

**Response 200**:
```json
{
    "email_id": "email_abc123",
    "summary": {
        "keywords": ["项目", "进度", "Q4"],
        "one_line": "张三汇报Q4项目进度",
        "brief": "张三发送了Q4项目进度汇报...",
        "key_points": ["完成率85%", "预算超支10%"]
    },
    "categories": ["pending_reply", "项目:Q4"],
    "sentiment": "neutral",
    "is_spam": false,
    "importance_score": 72,
    "action_items": [...],
    "reply_stances": [...],
    "ai_status": "processed",
    "processed_at": "2026-03-01T10:31:00"
}
```

**Response 404**: `{"error": "AI metadata not found"}`

### 3.3 POST /emails/{email_id}/ai-metadata

Analyzer skill 写入分析结果。

**Request Body** (与 analyze_email.py 的输出 `data` 字段一致):
```json
{
    "summary": {
        "keywords": ["项目", "进度", "Q4"],
        "one_line": "张三汇报Q4项目进度",
        "brief": "张三发送了Q4项目进度汇报...",
        "key_points": ["完成率85%", "预算超支10%"]
    },
    "action_items": [
        {
            "text": "回复确认收到",
            "deadline": "2026-03-02",
            "deadline_source": "inferred",
            "priority": "medium",
            "category": "工作",
            "assignee": "me",
            "quote": "请确认"
        }
    ],
    "metadata": {
        "category": ["pending_reply", "项目:Q4"],
        "sentiment": "neutral",
        "language": "zh",
        "confidence": 0.88,
        "is_spam": false,
        "importance_score": 72,
        "importance_breakdown": {
            "sender_weight": 30, "sender_score": 70, "sender_contrib": 21.0,
            "urgency_weight": 25, "urgency_score": 60, "urgency_contrib": 15.0,
            "deadline_weight": 25, "deadline_score": 80, "deadline_contrib": 20.0,
            "complexity_weight": 20, "complexity_score": 80, "complexity_contrib": 16.0,
            "total": 72.0
        },
        "suggested_reply": "收到，我会查看并回复。",
        "reply_stances": ["确认收到并查看", "询问具体细节", "转发给相关同事"]
    }
}
```

**实现要点**:
```python
@app.post("/emails/{email_id}/ai-metadata")
async def write_ai_metadata(email_id: str, body: dict):
    # 将 skill 输出格式映射到 EmailAIMetadata
    metadata = body.get("metadata", {})
    _db.update_email_ai_metadata(
        email_id=email_id,
        summary=json.dumps(body.get("summary", {}), ensure_ascii=False),
        categories=json.dumps(metadata.get("category", []), ensure_ascii=False),
        sentiment=metadata.get("sentiment", "neutral"),
        suggested_reply=metadata.get("suggested_reply"),
        is_spam=metadata.get("is_spam", False),
        action_items=json.dumps(body.get("action_items", []), ensure_ascii=False),
        reply_stances=json.dumps(metadata.get("reply_stances", []), ensure_ascii=False),
        importance_score=metadata.get("importance_score", 50),
        ai_status="processed",
        processing_progress=100,
        processing_stage="completed"
    )
    return {"status": "ok"}
```

### 3.4 GET /emails/unprocessed

Skill 获取待分析的邮件列表。

**Query Params**: `account_id` (required), `limit` (optional, default 20)

**Response 200**:
```json
{
    "emails": [
        {
            "id": "email_abc123",
            "subject": "Q4 项目进度汇报",
            "from_address": {"name": "张三", "email": "zhangsan@company.com"},
            "received_at": "2026-03-01T10:30:00"
        }
    ],
    "total": 1
}
```

### 3.5 GET /memories/{account_id}

Skill 获取用户偏好记忆（MemoryBank）。

**Query Params**: `memory_type` (optional), `memory_key` (optional)

**Response 200**:
```json
{
    "memories": [
        {
            "id": 1,
            "memory_type": "email_analysis",
            "memory_key": "zhangsan@company.com",
            "memory_content": {"preference": "重要性偏高，因为是直属上司"},
            "confidence_score": 0.9,
            "evidence_count": 5,
            "created_at": "2026-02-28T10:00:00",
            "updated_at": "2026-03-01T10:00:00"
        }
    ]
}
```

**实现参考**:
```python
@app.get("/memories/{account_id}")
async def get_memories(account_id: str, memory_type: str = None, memory_key: str = None):
    if memory_type:
        memories = _db.get_memories_by_type(account_id, memory_type)
    elif memory_key:
        memories = _db.get_memories_for_sender(account_id, memory_key)
    else:
        memories = _db.get_all_memories(account_id)
    return {"memories": [m.__dict__ for m in memories]}
```

### 3.6 POST /memories/{account_id}

Executor skill 写入偏好记忆。

**Request Body**:
```json
{
    "memory_type": "email_analysis",
    "memory_key": "zhangsan@company.com",
    "memory_content": {"preference": "该发件人的邮件重要性应偏高"},
    "confidence_score": 0.85,
    "evidence_count": 1
}
```

**实现参考**:
```python
@app.post("/memories/{account_id}")
async def write_memory(account_id: str, body: dict):
    from clawmail.infrastructure.database.models import UserMemory
    memory = UserMemory(
        user_account_id=account_id,
        memory_type=body["memory_type"],
        memory_key=body.get("memory_key"),
        memory_content=body["memory_content"],
        confidence_score=body.get("confidence_score", 0.5),
        evidence_count=body.get("evidence_count", 1)
    )
    _db.upsert_memory(memory)
    return {"status": "ok"}
```

### 3.7 GET /pending-facts/{account_id}

Skill 获取当前的 pending facts。

**Query Params**: `status` (optional, default "pending"), `category` (optional)

**Response 200**:
```json
{
    "facts": [
        {
            "id": 1,
            "fact_key": "career.position",
            "fact_category": "career",
            "fact_content": "可能是软件工程师",
            "confidence": 0.4,
            "evidence_count": 1,
            "source_emails": [{"email_id": "e1", "extracted_at": "...", "individual_confidence": 0.4}],
            "status": "pending",
            "created_at": "2026-03-01T10:00:00"
        }
    ]
}
```

### 3.8 POST /pending-facts/{account_id}

Analyzer skill 写入新的 pending fact。

**Request Body**:
```json
{
    "facts": [
        {
            "fact_key": "career.position",
            "fact_category": "career",
            "fact_content": "软件工程师，在 XYZ 公司工作",
            "confidence": 0.7,
            "source_email_id": "email_abc123"
        }
    ]
}
```

**实现要点**: 对 `facts` 数组中每一项调用 `upsert_pending_fact()`。

**Response 200**:
```json
{
    "status": "ok",
    "updated": 1,
    "created": 0
}
```

### 3.9 POST /pending-facts/{account_id}/promote

触发提升检查。将达标的 pending facts 提升到 USER.md。

**Request Body**: 无（或空 `{}`）

**实现要点**:
```python
@app.post("/pending-facts/{account_id}/promote")
async def promote_pending_facts(account_id: str):
    promoted = _db.promote_pending_facts(account_id)
    if promoted:
        # 将 promoted facts 追加写入 USER.md
        user_md_path = Path.home() / ".openclaw" / "workspace" / "USER.md"
        append_facts_to_user_md(user_md_path, promoted)
    return {"promoted_count": len(promoted), "promoted": promoted}
```

`append_facts_to_user_md()` 的逻辑：
- 读取当前 USER.md
- 按 fact_category 分组，找到对应 section 追加
- 如果 section 不存在则创建
- 避免重复写入（检查是否已有相同 fact_key）

---

## 4. ai_processor.py 改动

### 改动策略

保留 `AIProcessor` 类接口不变，内部从"自己拼 prompt 调 LLM"改为"直接调用 skill 脚本"。

**关键原则：ClawMail 直接调用 skill 脚本，不经过 LLM 判断。**

```
旧方式（有风险）:
ClawMail → bridge.user_chat("分析邮件") → OpenClaw LLM → LLM 决定调不调 skill
                                                         ↑ LLM 可能跳过 skill

新方式（确定性）:
ClawMail → 直接运行 analyze_email.py → 脚本内部调 LLM API 获取结果
                                        ↑ LLM 只回答问题，不决定流程
```

不再使用 `bridge.user_chat()`，而是通过 `subprocess` 或 Python import 直接调用 skill 脚本。

### Skill 脚本路径配置

```python
# ai_processor.py 新增配置
SKILL_BASE = Path.home() / ".openclaw" / "workspace" / "skills"
ANALYZER_SCRIPT = SKILL_BASE / "clawmail-analyzer" / "scripts" / "analyze_email.py"
REPLY_SCRIPT = SKILL_BASE / "clawmail-reply" / "scripts" / "generate_reply.py"
GENERATE_SCRIPT = SKILL_BASE / "clawmail-reply" / "scripts" / "generate_email.py"
POLISH_SCRIPT = SKILL_BASE / "clawmail-reply" / "scripts" / "polish_email.py"
HABITS_SCRIPT = SKILL_BASE / "clawmail-reply" / "scripts" / "extract_habits.py"
EXECUTOR_SCRIPT = SKILL_BASE / "clawmail-executor" / "scripts" / "extract_preference.py"
```

### process_email() 改动

```python
def process_email(self, email, account_id: str) -> EmailAIMetadata:
    """直接调用 analyzer skill 脚本分析邮件。"""
    result = subprocess.run(
        [sys.executable, str(ANALYZER_SCRIPT),
         "--mode", "analyze",
         "--email-id", str(email.id),
         "--account-id", account_id],
        capture_output=True, text=True, timeout=120
    )

    if result.returncode != 0:
        raise AIProcessingError(f"Analyzer skill 失败: {result.stderr}")

    # Skill 脚本执行时已通过 REST API 写入 DB
    # 从 DB 读取最新结果返回
    metadata = self._db.get_email_ai_metadata(email.id)
    if metadata and metadata.ai_status == "processed":
        return metadata

    # Fallback：从 stdout 解析结果
    return self._parse_skill_output(result.stdout, email.id)
```

### generate_reply_draft() 改动

```python
def generate_reply_draft(self, email, stance: str, tone: str,
                         user_notes: str = "", account_id: str = "") -> str:
    """直接调用 reply skill 脚本生成回复草稿。"""
    cmd = [
        sys.executable, str(REPLY_SCRIPT),
        "--email-id", str(email.id),
        "--stance", stance,
        "--tone", tone,
        "--account-id", account_id
    ]
    if user_notes:
        cmd.extend(["--user-notes", user_notes])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        raise AIProcessingError(f"Reply skill 失败: {result.stderr}")

    return result.stdout.strip()
```

### generate_email() / polish_email() 类似改动

同样改为直接调用对应的 skill 脚本，通过命令行参数传入输入数据。

### 可删除的代码

迁移完成后以下内容可以删除：
- `_PROMPT_TEMPLATE` 和 6 个 section 定义
- `_load_prompt_sections()` / `_ensure_prompt_files()`
- `_build_memory_section()`（记忆注入由 skill 通过 API 读取）
- `_build_analysis_prompt()` 等 prompt 构建方法
- `~/clawmail_data/prompts/*.txt` 文件依赖

**Phase 3 已完成**：所有 legacy prompt 模板、fallback 路径、memory 注入代码已清理。当前 `ai_processor.py` 仅保留 skill 调用路径（~245 行）。

---

## 5. app.py 改动：用户撰写时触发习惯提取

### 触发时机

用户**发送**邮件或回复时（不是草稿保存时），通知 reply skill 提取习惯。

### 实现位置

在现有的发送逻辑中添加 hook：

```python
def _on_email_sent(self, email_data: dict):
    """邮件发送成功后触发习惯提取。"""
    try:
        # 异步触发，不阻塞 UI
        asyncio.ensure_future(self._extract_user_habits(email_data))
    except Exception as e:
        print(f"[Habits] 触发失败: {e}")

async def _extract_user_habits(self, email_data: dict):
    """直接调用 reply skill 的 extract_habits.py 提取用户撰写习惯。"""
    compose_json = json.dumps(email_data, ensure_ascii=False)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: subprocess.run(
            [sys.executable, str(HABITS_SCRIPT),
             "--compose-data", compose_json,
             "--account-id", email_data.get("account_id", "")],
            capture_output=True, text=True, timeout=120
        )
    )
```

### 需要找到的 hook 点

- `POST /compose` 端点中发送成功后
- `POST /send-reply` 端点中发送成功后
- ComposeDialog 中用户点击发送后

---

## 6. 迁移顺序（ClawMail 侧）

### Phase 1: 数据层准备 ✅ 已完成
1. ✅ 新增 `pending_facts` 表（DDL + 索引 + 旧数据库兼容）
2. ✅ 新增 storage_manager.py 中的查询方法（5 个 pending_facts CRUD + 2 个邮件查询）
3. ✅ 新增 REST API 端点（server.py，共 9 个端点 + 辅助函数）
4. ✅ 语法验证通过

### Phase 2: AI 层迁移 ✅ 已完成
1. ✅ 修改 `ai_processor.process_email()` 为 try skill → fallback legacy
2. ✅ 修改 `generate_reply_draft()` / `generate_email()` / `polish_email()` 同上模式
3. ✅ 添加用户撰写时的习惯提取 hook（compose_dialog.py + server.py /send-reply）
4. ✅ 保留旧代码作为 fallback（skill 失败时走旧路径）

### Phase 3: Legacy 清理 ✅ 已完成
1. ✅ ai_processor.py：删除 ~450 行 legacy 代码（prompt 模板、fallback 方法、memory 注入）
2. ✅ ai_processor.py：简化构造函数为 `AIProcessor(data_dir)` — 移除 bridge、memory_bank 参数
3. ✅ storage_manager.py：删除 prompts 目录初始化和 legacy import
4. ✅ server.py：删除 `GET /personalization/prompt/{type}` 和 `POST /personalization/update-prompt` 端点
5. ✅ app.py + server.py：适配新 AIProcessor 签名（6 处调用全部更新）
6. ✅ 全部 4 个文件语法验证通过

---

## 7. 注意事项

1. **~~向后兼容~~**：Phase 3 已移除所有 legacy fallback 路径。Skill 失败时直接抛出 `AIProcessingError`。
2. **USER.md 写入**：`promote` 端点需要写文件到 `~/.openclaw/workspace/USER.md`，确保路径存在。
3. **并发安全**：pending_facts 的 upsert 需要处理并发写入（SQLite WAL 模式已足够）。
4. **REST API 权限**：所有新端点只监听 127.0.0.1，不暴露到外部。
5. **数据截断**：`GET /emails/{id}` 返回的 body_text 必须截断到 4000 字符，避免超出 LLM 上下文。
