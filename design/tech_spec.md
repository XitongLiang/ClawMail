# ClawMail 技术规范（Tech Spec）

> **本文档是所有设计文档的唯一枚举值真实来源（Single Source of Truth）。**
> 其他文档中出现的枚举值、技术选型，均以本文档为准。如有冲突，以本文档为准。

---

## 1. 技术选型（最终确定，无备选项）

### 1.1 运行时

| 组件 | 选型 | 版本 |
|------|------|------|
| Python 运行时 | CPython | 3.11.13（严格锁定） |
| 包管理 | pip + venv | 最新稳定版 |

### 1.2 UI 框架

**最终选定：PyQt6 + PyQt6-WebEngine**

| 理由 | 说明 |
|------|------|
| 纯 Python 集成最深 | 无 subprocess 桥接，无 IPC 延迟 |
| 原生桌面通知 | `QSystemTrayIcon` 直接支持 |
| 异步兼容 | `qasync` 库将 asyncio 集成进 Qt 事件循环 |
| 组件丰富 | 满足四栏布局所有需求 |
| 浏览器级邮件渲染 | `QWebEngineView`（Chromium 内核）正确处理 CSS、`display:none`、图片 |

**邮件内容渲染组件（`EmailWebView`）：**

`clawmail/ui/app.py` 中使用 `QWebEngineView` 替代 `QTextBrowser` 渲染 HTML 邮件。

| 特性 | 实现方式 |
|------|---------|
| 链接拦截 | `_EmailWebPage(QWebEnginePage).acceptNavigationRequest()` — 链接点击在系统浏览器打开 |
| JavaScript | 默认**禁用**（安全考虑） |
| 外链图片 | `LocalContentCanAccessRemoteUrls=True` — 允许从 `file:///` 基础 URL 加载 http/https 图片 |
| 图片自适应 | 注入 `_RESPONSIVE_CSS`：`img{max-width:100%!important;height:auto!important;}` |
| 缩放 | macOS 触控板捏合缩放、Ctrl+滚轮缩放由 WebEngine 原生支持 |

**不选择的原因：**
- PySide6：许可证差异（LGPL vs GPL），发行时需注意
- Toga：组件成熟度不足，自定义邮件列表困难
- Tauri/Electron：引入 Rust/Node.js，破坏纯 Python 约束

### 1.3 数据库

| 组件 | 选型 | 版本 |
|------|------|------|
| 关系型数据库 | SQLite | stdlib 内置，WAL 模式开启 |
| ORM | 无（直接 sqlite3） | - |
| 向量数据库 | ChromaDB | 0.5.23（**仅 Phase 5**） |

### 1.4 网络与协议

| 组件 | 选型 | 版本 |
|------|------|------|
| IMAP 客户端 | aioimaplib | 1.1.0（原生 async） |
| SMTP 客户端 | aiosmtplib | 3.0.1（原生 async） |
| HTTP 客户端 | httpx | 0.27.x（async） |

### 1.5 AI 集成

**通信模式以根目录 `ClawChat.py` 为基准（不可修改原文件）。**

| 参数 | 值 | 说明 |
|------|-----|------|
| AI SDK | openai Python SDK | 标准 OpenAI 兼容接口 |
| 连接端点 | `http://127.0.0.1:18789/v1` | 可通过 `config/default.yaml` 配置 |
| 模型参数 | `model = "default"` | 固定值，OpenClaw 网关已配置路由 |
| 流式模式 | `stream = True` | 始终开启，按 chunk 拼接 |
| Agent 路由 | `user` 参数传 agentId | 区分邮件处理 vs 用户聊天 |
| API Token | 读自 config 或 keyring | **不硬编码**，参考 `ClawChat.py` 主程序的 token 值 |

**两种调用模式：**

| 方法 | agentId | 用途 |
|------|---------|------|
| 邮件处理（参考 `mailChat`） | `"mailAgent_{email_id[:8]}"` | 分析/摘要/分类/任务提取 |
| 用户聊天（参考 `userChat`） | `"userAgent001"` | 右侧助手面板对话 |

**`OpenClawBridge` 核心实现模式（`infrastructure/ai/openai_bridge.py`）：**

```python
from openai import OpenAI

class OpenClawBridge:
    def __init__(self, token: str, base_url: str = "http://127.0.0.1:18789/v1"):
        # 遵循 ClawChat.connect() 模式
        self.client = OpenAI(api_key=token, base_url=base_url)

    def process_email(self, mail_input: str, mail_id: str = "mailAgent001") -> str:
        """邮件 AI 处理（对应 ClawChat.mailChat 模式）"""
        messages = [{"role": "user", "content": mail_input}]
        full_response = ""
        response = self.client.chat.completions.create(
            model="default", messages=messages, stream=True, user=mail_id
        )
        for chunk in response:
            if chunk.choices[0].delta.content:
                full_response += chunk.choices[0].delta.content
        return full_response

    def user_chat(self, user_input: str, user_id: str = "userAgent001") -> str:
        """用户聊天（对应 ClawChat.userChat，模式完全相同）"""
        messages = [{"role": "user", "content": user_input}]
        full_response = ""
        response = self.client.chat.completions.create(
            model="default", messages=messages, stream=True, user=user_id
        )
        for chunk in response:
            if chunk.choices[0].delta.content:
                full_response += chunk.choices[0].delta.content
        return full_response
```

> **注意**：`OpenClawBridge` 的调用（`process_email` / `user_chat`）是**同步阻塞**的（与 ClawChat.py 一致）。
> 在 Plugin 层中，通过 `asyncio.get_event_loop().run_in_executor(None, bridge.process_email, ...)` 包装为 async，避免阻塞 Qt 事件循环。

| 组件 | 选型 | 版本 |
|------|------|------|
| AI SDK | openai Python SDK | 1.51.0 |
| 嵌入模型 | sentence-transformers | 3.3.0（**仅 Phase 5**） |

### 1.6 安全相关

| 组件 | 选型 | 版本 |
|------|------|------|
| OS Keychain 访问 | keyring | 25.3.0 |
| 对称加密 | cryptography（Fernet） | 43.0.1 |

### 1.7 异步集成

| 组件 | 选型 | 版本 |
|------|------|------|
| Qt + asyncio 桥接 | qasync | 0.27.1 |

### 1.8 完整 requirements.txt

```
# UI
PyQt6==6.7.1

# 邮件 HTML 渲染（Chromium 内核，QWebEngineView）
PyQt6-WebEngine==6.7.0  # 必须与 PyQt6==6.7.1 / PyQt6-Qt6==6.7.3 保持同版本族

# 异步集成
qasync==0.27.1

# 邮件协议
aioimaplib==1.1.0
aiosmtplib==3.0.1

# HTTP
httpx==0.27.0

# AI
openai==1.51.0

# 安全
keyring==25.3.0
cryptography==43.0.1

# ---- Phase 5 only ----
# chromadb==0.5.23
# sentence-transformers==3.3.0
```

---

## 2. 规范枚举值（Single Source of Truth）

> 所有文档、所有代码中的枚举值必须与本节完全一致。

### 2.1 EmailSyncStatus — 邮件同步状态

描述 IMAP 同步进度。

| 值 | 含义 |
|----|------|
| `pending` | 在队列中，尚未尝试 |
| `downloading` | 正在从 IMAP 拉取 |
| `completed` | 完整内容已保存到本地 |
| `failed` | 下载失败，可重试 |

**SQL 约束：**
```sql
sync_status TEXT DEFAULT 'pending'
CHECK(sync_status IN ('pending', 'downloading', 'completed', 'failed'))
```

**Python Enum：**
```python
class EmailSyncStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
```

### 2.2 EmailAIStatus — AI 处理状态

描述 AI 插件流水线的处理进度。

| 值 | 含义 |
|----|------|
| `unprocessed` | 尚未发送给 AI |
| `processing` | AI 调用进行中 |
| `processed` | 所有 AI 结果已保存 |
| `failed` | AI 调用失败（重试后仍失败），需重试 |
| `skipped` | 前置检查判断无需 AI（如广告邮件），主动跳过，不重试 |

> **`failed` vs `skipped` 的区别：**
> - `failed`：调用了 AI 但出错 → 放入重试队列
> - `skipped`：主动决定不调用 AI → 不重试，不报错

**SQL 约束：**
```sql
ai_status TEXT DEFAULT 'unprocessed'
CHECK(ai_status IN ('unprocessed', 'processing', 'processed', 'failed', 'skipped'))
```

**Python Enum：**
```python
class EmailAIStatus(str, Enum):
    UNPROCESSED = "unprocessed"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    SKIPPED = "skipped"
```

### 2.3 EmailReadStatus — 邮件阅读状态

| 值 | 含义 |
|----|------|
| `unread` | 未读 |
| `read` | 已读 |
| `skimmed` | 快速浏览（短暂查看，未完整阅读） |

### 2.4 EmailFlagStatus — 邮件标记状态

| 值 | 含义 |
|----|------|
| `none` | 未标记 |
| `flagged` | 已标记 |
| `completed` | 用户标记为已完成 |

### 2.5 EmailReplyStatus — 邮件回复状态

| 值 | 含义 |
|----|------|
| `no_need` | 无需回复（默认） |
| `pending` | 预期回复但尚未发送 |
| `replied` | 用户已回复 |
| `forwarded` | 用户已转发 |

### 2.6 TaskStatus — 任务状态

| 值 | 含义 | 适用场景 |
|----|------|----------|
| `pending` | 默认，待处理 | 所有任务 |
| `in_progress` | 用户已开始 | 所有任务 |
| `snoozed` | 已推迟（需填 `snoozed_until`） | 所有任务 |
| `completed` | 已完成 | 所有任务 |
| `cancelled` | 用户放弃 | 所有任务 |
| `rejected` | AI 建议被用户驳回 | **仅** `source_type='extracted'` |
| `archived` | 历史归档，不在主视图 | 所有任务 |

**状态转换规则：**
```
pending → in_progress → completed
pending → snoozed → pending（snoozed_until 到期自动触发）
pending → cancelled
pending → rejected（仅 extracted 任务）
任意状态 → archived（用户手动操作）
```

**SQL 约束：**
```sql
status TEXT NOT NULL DEFAULT 'pending'
CHECK(status IN ('pending', 'in_progress', 'snoozed', 'completed', 'cancelled', 'rejected', 'archived'))
```

**Python Enum：**
```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SNOOZED = "snoozed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"      # AI提取任务专用，用户拒绝后设置
    ARCHIVED = "archived"
```

### 2.7 AccountStatus — 账户状态

| 值 | 含义 |
|----|------|
| `active` | 正常运行 |
| `error` | 连接/认证出错，需用户处理 |
| `paused` | 用户手动暂停同步 |

**SQL 约束：**
```sql
status TEXT DEFAULT 'active'
CHECK(status IN ('active', 'error', 'paused'))
```

### 2.9 TaskSourceType — 任务来源类型

| 值 | 含义 |
|----|------|
| `extracted` | AI 从邮件中提取 |
| `manual` | 用户手动创建 |
| `template` | 从模板创建 |
| `recurring` | 周期性任务自动生成 |

### 2.10 TaskPriority — 任务优先级

| 值 | 含义 |
|----|------|
| `high` | 高优先级 |
| `medium` | 中优先级 |
| `low` | 低优先级 |
| `none` | 未设置优先级 |

### 2.11 AISentiment — AI 情感/紧急度

| 值 | 含义 |
|----|------|
| `urgent` | 紧急，需立即处理 |
| `positive` | 积极/正面 |
| `negative` | 消极/负面 |
| `neutral` | 中性 |

---

## 3. AI 分类标签规范（Canonical Category Taxonomy）

> UI 导航面板、AI Prompt 输出、邮件存储中的 category 字段，均以本节为准。

### 3.1 系统固定标签（7 个）

| 内部键值 | 显示名称 | 颜色 | 触发条件 |
|---------|---------|------|----------|
| `urgent` | 紧急 | `#FF4444`（红） | 需在 24 小时内处理 |
| `pending_reply` | 待回复 | `#FFB300`（琥珀） | 等待用户回复 |
| `notification` | 通知 | `#9E9E9E`（灰） | 纯信息，无需操作 |
| `subscription` | 订阅 | `#795548`（棕） | 新闻稿、营销邮件 |
| `meeting` | 会议 | `#2196F3`（蓝） | 包含会议安排或日程 |
| `approval` | 审批 | `#9C27B0`（紫） | 需要决策或签字 |

> 共 6 个系统固定标签（注意：`pending_reply` 是一个标签）。

### 3.2 动态项目标签（用户定义 + AI 建议）

- **格式：** `"项目:{项目名称}"`，例如 `"项目:Q4发布"`、`"项目:客户X"`
- **最多：** 20 个活跃项目标签
- **颜色：** 首次创建时从预设调色板自动分配
- **存储：** 作为普通字符串存入 `category` JSON 数组

### 3.3 AI Prompt 中的分类指令

AI 在提取邮件信息时，category 字段的指令如下：

```
从以下固定标签中选择 0-3 个（不强制必须选）：
urgent, pending_reply, notification, subscription, meeting, approval

如邮件明确与某项目相关，额外输出一个"项目:XX"动态标签。
总分类标签不超过 4 个。
输出格式：JSON 数组，例如 ["urgent", "项目:Q4发布"]
```

### 3.4 存储格式

```json
"category": ["urgent", "项目:Q4发布"]
```

- 始终为数组（即使只有一个标签）
- 空时为 `[]`，不为 `null`

---

## 4. 安全设计

### 4.1 凭据存储方案

**选型：keyring + cryptography.fernet（双层加密）**

```
主密钥（Master Key）
  └── 存储位置：OS Keychain（via keyring 库）
        └── macOS: macOS Keychain
        └── Windows: Windows Credential Manager
        └── Linux: SecretService (libsecret) / keyrings.alt 兜底

IMAP 密码加密流程：
  明文密码 → Fernet(主密钥).encrypt() → 密文 → 存入 DB credentials_encrypted BLOB
IMAP 密码解密流程：
  DB credentials_encrypted BLOB → Fernet(主密钥).decrypt() → 明文密码
```

**不使用单纯 cryptography.fernet 硬编码 key 的原因：**
密钥如果存磁盘，等于明文；OS Keychain 是唯一安全的密钥存储位置。

### 4.2 实现代码（参考）

```python
# infrastructure/security/credential_manager.py
import keyring
from cryptography.fernet import Fernet

KEYRING_SERVICE = "ClawMail"
KEYRING_KEY_ACCOUNT = "db_encryption_key"

class CredentialManager:
    """管理 IMAP/SMTP 凭据的加密存储与读取。"""

    def _get_or_create_master_key(self) -> bytes:
        key = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY_ACCOUNT)
        if key is None:
            key = Fernet.generate_key().decode()
            keyring.set_password(KEYRING_SERVICE, KEYRING_KEY_ACCOUNT, key)
        return key.encode()

    def encrypt_credentials(self, plaintext: str) -> bytes:
        f = Fernet(self._get_or_create_master_key())
        return f.encrypt(plaintext.encode())

    def decrypt_credentials(self, ciphertext: bytes) -> str:
        f = Fernet(self._get_or_create_master_key())
        return f.decrypt(ciphertext).decode()
```

### 4.3 OAuth2（未来支持 Gmail/Outlook，Phase 6）

```
oauthlib==3.2.2
requests-oauthlib==2.0.0
```

Phase 0-5 不需要，163.com/QQ邮箱使用授权码（App Password）通过 IMAP SASL PLAIN 认证。

### 4.4 数据库加密（可选，Phase 6）

若需要全库加密，可引入 SQLCipher：
```
sqlcipher3==0.5.3  # AES-256 全库加密
```
MVP 阶段不引入，`keyring + Fernet` 保护凭据已足够。

### 4.5 安全默认值 Checklist

- [ ] TLS 连接：IMAP 使用 993 端口 SSL，SMTP 使用 587 端口 STARTTLS
- [ ] 内存中的明文密码用完即清除（`del password`）
- [ ] 日志中不记录任何凭据内容
- [ ] 数据库文件权限设为 600（owner 只读写）

---

## 5. 异步线程模型

### 5.1 架构概述

**选型：qasync 将 asyncio 事件循环运行在 Qt 事件循环内部**

```
┌─────────────────────────────────────────────┐
│              Qt 事件循环（主线程）             │
│  ┌─────────────────────────────────────────┐ │
│  │    asyncio 事件循环（qasync 集成）        │ │
│  │  - IMAP 同步（aioimaplib）               │ │
│  │  - AI API 调用（httpx async）            │ │
│  │  - 插件链执行（asyncio.gather）          │ │
│  └─────────────────────────────────────────┘ │
│                                               │
│  ThreadPoolExecutor（CPU 密集型任务）          │
│  - email 解析（chardet/mime）                 │
│  - FTS5 索引写入                              │
└─────────────────────────────────────────────┘
```

### 5.2 应用入口（main.py）

```python
import sys
import asyncio
import qasync
from PyQt6.QtWidgets import QApplication
from ui.app import ClawMailApp

def main():
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = ClawMailApp()
    window.show()

    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
```

### 5.3 四条线程安全规则

**规则 1：** 所有 Qt widget 操作必须在主线程执行。
禁止在协程中直接调用 `widget.setText()`，除非确认在主线程。

**规则 2：** 纯 I/O 操作（IMAP、HTTP/AI）使用 asyncio 协程。
`aioimaplib` 和 `httpx` 均为原生 async，不需要 QThread。

**规则 3：** CPU 密集型操作使用 `run_in_executor`：
```python
result = await asyncio.get_event_loop().run_in_executor(None, cpu_bound_function, arg)
```

**规则 4：** 跨线程 UI 更新只通过 Qt Signal/Slot。
```python
# 正确：从任意线程 emit signal，Qt 保证在主线程执行 slot
self.email_downloaded.emit(email_id)

# 错误：在协程中直接操作 widget（可能不在主线程）
# self.list_widget.addItem(subject)  ← 禁止
```

### 5.4 SyncService 代码示例

```python
# services/sync_service.py
from PyQt6.QtCore import QObject, pyqtSignal

class SyncService(QObject):
    email_downloaded = pyqtSignal(str)          # email_id
    ai_progress_updated = pyqtSignal(str, int)  # email_id, progress%
    sync_completed = pyqtSignal(int)            # new_email_count
    sync_failed = pyqtSignal(str)               # error_message

    async def run_sync_cycle(self):
        try:
            emails = await self._imap_client.fetch_new()
            for email in emails:
                await self._repo.save(email)
                self.email_downloaded.emit(email.id)   # 触发 UI 列表刷新

                result = await self._ai_client.process(email)
                await self._repo.save_ai_result(email.id, result)
                self.ai_progress_updated.emit(email.id, 100)

            self.sync_completed.emit(len(emails))
        except Exception as e:
            self.sync_failed.emit(str(e))
```

### 5.5 何时使用 QThread（极少数例外）

仅在以下情况使用 QThread：
- 需要运行无法 async 化的阻塞 C 扩展
- 需要严格 CPU 隔离（极罕见）

**不要用 QThread 做 IMAP 同步**，`aioimaplib` 已经是原生 async。

---

## 6. 错误处理策略

### 6.1 IMAP 重试策略

```yaml
# config/default.yaml 中的配置
sync:
  retry:
    max_attempts: 3
    backoff_base_seconds: 2      # 2s → 4s → 8s
    backoff_max_seconds: 60
    retry_on:
      - ConnectionError
      - TimeoutError
      - IMAPError
    no_retry_on:
      - AuthenticationError      # 密码错误不重试，直接报错提示用户
```

### 6.2 AI 离线降级策略

当 AI 服务不可达时：

1. 设置 `ai_status = 'failed'`
2. 邮件立即出现在列表中（显示原始主题 + 发件人，无摘要/标签）
3. UI 在邮件条目上显示 `⚠️ AI未处理` 徽章
4. 将 `email_id` 放入 `user_settings` 表的 `ai_retry_queue` JSON 字段
5. 下次同步周期检测到 AI 可达时，自动处理重试队列

```python
# AI 重试队列存储格式（user_settings 表）
key = "ai_retry_queue"
value = '["email_id_1", "email_id_2", ...]'  # JSON 数组
```

### 6.3 AI 输出格式校验与降级

当 AI 返回非法 JSON 或字段缺失时：

```python
def parse_ai_response(raw: str) -> dict:
    try:
        data = json.loads(raw)
        return validate_and_fill_defaults(data)
    except (json.JSONDecodeError, KeyError):
        # 降级：返回所有字段的空默认值
        return {
            "summary": {"one_line": "", "brief": "", "key_points": []},
            "category": [],
            "sentiment": "neutral",
            "action_items": [],
            "suggested_reply": None,
        }
        # 同时设置 ai_status = 'failed'，放入重试队列
```

### 6.4 用户可见的错误信息规范

| 场景 | 用户看到的提示 |
|------|--------------|
| IMAP 连接失败 | "邮件同步失败，请检查网络连接" |
| 认证错误 | "邮箱密码错误，请在设置中重新配置" |
| AI 服务不可用 | "AI 助手暂时不可用，邮件已保存，稍后自动重试分析" |
| 数据库写入失败 | "数据保存失败，请重启应用" |
| 附件过大 | "附件超过 {limit}MB，无法本地保存" |

---

## 7. 搜索设计

### 7.1 两层搜索架构

**Layer 1：SQLite FTS5 关键词搜索（Phase 1 起可用）**

```sql
CREATE VIRTUAL TABLE emails_fts USING fts5(
    subject,
    body_text,
    from_name,            -- 发件人姓名（从 from_address JSON 提取）
    content='emails',
    content_rowid='rowid',
    tokenize='unicode61'  -- 支持中文、日文等 Unicode 字符
);
-- 注：summary_one_line / keywords 存储在 email_ai_metadata 表，
--     无法通过 content='emails' 的 FTS5 表统一索引。
--     AI 字段的全文检索在 Phase 5 通过 ChromaDB 向量搜索覆盖。

-- 触发器：保持 FTS5 索引与 emails 表同步（命名与 userDataStorageDesign.md 一致）
CREATE TRIGGER emails_fts_insert AFTER INSERT ON emails BEGIN
    INSERT INTO emails_fts(rowid, subject, body_text, from_name)
    VALUES (new.rowid, new.subject, new.body_text,
            json_extract(new.from_address, '$.name'));
END;

CREATE TRIGGER emails_fts_update AFTER UPDATE OF subject, body_text, from_address ON emails BEGIN
    INSERT INTO emails_fts(emails_fts, rowid, subject, body_text, from_name)
    VALUES ('delete', old.rowid, old.subject, old.body_text,
            json_extract(old.from_address, '$.name'));
    INSERT INTO emails_fts(rowid, subject, body_text, from_name)
    VALUES (new.rowid, new.subject, new.body_text,
            json_extract(new.from_address, '$.name'));
END;

CREATE TRIGGER emails_fts_delete AFTER DELETE ON emails BEGIN
    INSERT INTO emails_fts(emails_fts, rowid, subject, body_text, from_name)
    VALUES ('delete', old.rowid, old.subject, old.body_text,
            json_extract(old.from_address, '$.name'));
END;
```

**Layer 2：ChromaDB 向量语义搜索（Phase 5）**

```python
# 嵌入向量生成（本地模型 or OpenClaw 嵌入端点）
# 存储路径：clawmail_data/vector_store/chroma/
```

### 7.2 混合排名公式（Phase 5）

```
final_score = (fts5_bm25_score * 0.6) + (cosine_similarity * 0.4)
```

**触发条件：** 查询词数量 > 3 且向量库可用时启用混合排名；否则退回纯 FTS5。

### 7.3 搜索索引维护

- FTS5 索引通过 SQLite 触发器自动维护（INSERT/UPDATE/DELETE）
- ChromaDB 嵌入在 AI 处理完成后（`ai_status = 'processed'`）异步写入
- 全量重建命令：`clawmail rebuild-index`（CLI 工具，Phase 5）

---

## 8. 通知系统

### 8.1 PyQt6 QSystemTrayIcon 实现

```python
# ui/components/notification_manager.py
from PyQt6.QtWidgets import QSystemTrayIcon
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QObject

class NotificationManager(QSystemTrayIcon):
    """管理所有桌面系统托盘通知。"""

    def __init__(self, parent=None):
        super().__init__(QIcon("assets/icons/tray.png"), parent)
        self.setToolTip("ClawMail")
        self.show()

    def notify_new_email(self, sender: str, subject: str, count: int):
        title = f"ClawMail — {count} 封新邮件" if count > 1 else "ClawMail — 新邮件"
        message = f"来自: {sender}\n{subject}"
        self.showMessage(title, message,
                         QSystemTrayIcon.MessageIcon.Information,
                         msecs=4000)

    def notify_urgent_email(self, subject: str):
        self.showMessage("紧急邮件", subject,
                         QSystemTrayIcon.MessageIcon.Warning,
                         msecs=6000)

    def notify_task_due(self, task_title: str):
        self.showMessage("任务提醒", task_title,
                         QSystemTrayIcon.MessageIcon.Warning,
                         msecs=6000)

    def notify_sync_error(self, error_msg: str):
        self.showMessage("同步失败", error_msg,
                         QSystemTrayIcon.MessageIcon.Critical,
                         msecs=8000)
```

### 8.2 通知触发条件

| 事件 | 通知内容 | 触发条件 |
|------|---------|---------|
| 新邮件到达 | "X 封新邮件" | `count > 0` 且 `do_not_disturb = false` |
| 紧急邮件 | "紧急邮件: {主题}" | `category` 含 `urgent` |
| 任务即将到期 | "任务提醒: {标题}" | `due_date` 在 30 分钟内 且 `status = 'pending'` |
| 已推迟任务到期 | 任务状态改回 `pending` | `snoozed_until <= now` |
| AI 处理完成 | **静默**（仅更新 UI 徽章） | 始终静默，避免噪音 |
| 同步连续失败 | "同步失败: {原因}" | 重试 3 次后仍失败 |

### 8.3 勿扰模式

```python
# user_settings 表中存储
key = "do_not_disturb"
value = "false"  # or "true"

# 设置勿扰时段（如晚上 22:00 到早上 8:00）
key = "dnd_schedule"
value = '{"enabled": true, "start": "22:00", "end": "08:00"}'
```

### 8.4 平台兼容性

| 平台 | QSystemTrayIcon 表现 |
|------|-------------------|
| macOS | 显示在菜单栏，通知通过 macOS 通知中心 |
| Windows | 显示在任务栏托盘区，通知为气泡弹窗 |
| Linux | 依赖桌面环境的 StatusNotifierItem 协议 |
