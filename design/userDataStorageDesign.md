 我来为ClawMail设计完整的用户数据存储框架，涵盖所有数据类型和存储策略。

---

## 整体存储架构

```
clawmail_data/                      # 用户数据主目录
├── clawmail.db                     # 核心SQLite数据库（邮件+任务+配置）
├── vector_store/                   # 向量数据库（语义检索）
│   └── chroma/
├── attachments/                    # 邮件附件文件
│   ├── 2024/
│   │   ├── 01/
│   │   │   └── {hash}.pdf
│   │   └── 02/
│   └── temp/                       # 下载中临时文件
├── cache/                          # 运行时缓存
│   ├── ai_responses/               # AI结果缓存（相同请求复用）
│   ├── thumbnails/                 # 附件缩略图
│   └── search_index/
├── exports/                        # 用户导出数据
│   └── 2024-01-15_backup.zip
├── logs/                           # 运行日志
│   └── clawmail_2024-01-15.log
└── config.yaml                     # 用户配置文件
```

---

## 核心数据库设计（SQLite）

### 数据库文件：clawmail.db

```sql
-- ============================================
-- 1. 账户表（支持多邮箱）
-- ============================================
CREATE TABLE accounts (
    id TEXT PRIMARY KEY,                    -- UUID
    email_address TEXT UNIQUE NOT NULL,     -- 完整邮箱地址
    display_name TEXT,                      -- 显示名称
    provider_type TEXT DEFAULT 'imap',      -- imap/gmail/exchange
    is_enabled INTEGER DEFAULT 1,
    
    -- IMAP/SMTP配置（加密存储）
    imap_server TEXT,
    imap_port INTEGER DEFAULT 993,
    smtp_server TEXT,
    smtp_port INTEGER DEFAULT 465,
    credentials_encrypted BLOB,             -- Fernet(AES-128-CBC+HMAC)加密；主密钥存OS Keychain via keyring
                                            -- 加密实现见 tech_spec.md 第4节
    
    -- 同步设置
    sync_interval_minutes INTEGER DEFAULT 2,
    last_sync_at TIMESTAMP,
    sync_cursor TEXT,                       -- IMAP同步游标
    
    -- 状态
    status TEXT DEFAULT 'active',           -- active/error/paused
    error_message TEXT,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 2. 邮件表（核心数据）
-- ============================================
CREATE TABLE emails (
    id TEXT PRIMARY KEY,                    -- UUID
    account_id TEXT NOT NULL,
    imap_uid TEXT,                          -- 服务器端UID
    message_id TEXT,                        -- RFC Message-ID
    
    -- 信封信息
    subject TEXT,
    from_address TEXT,                      -- JSON: {"name":"", "email":""}
    to_addresses TEXT,                      -- JSON数组
    cc_addresses TEXT,
    bcc_addresses TEXT,
    
    -- 内容
    body_text TEXT,                         -- 纯文本正文
    body_html TEXT,                         -- HTML原文
    content_type TEXT,                      -- text/plain/html/multipart
    charset TEXT DEFAULT 'utf-8',
    
    -- 时间
    sent_at TIMESTAMP,                      -- 邮件发送时间
    received_at TIMESTAMP,                  -- 本地接收时间
    internal_date TIMESTAMP,                -- IMAP服务器时间
    
    -- 原始数据
    raw_headers TEXT,                       -- 完整头部JSON
    size_bytes INTEGER,
    hash TEXT UNIQUE,                       -- 内容哈希防重复
    
    -- 同步状态（规范值见 tech_spec.md 2.1节）
    sync_status TEXT DEFAULT 'pending',     -- pending/downloading/completed/failed
    is_downloaded INTEGER DEFAULT 0,        -- 完整内容已下载

    -- 用户操作状态（规范值见 tech_spec.md 2.3-2.5节）
    read_status TEXT DEFAULT 'unread',      -- unread/read/skimmed
    flag_status TEXT DEFAULT 'none',        -- none/flagged/completed
    reply_status TEXT DEFAULT 'no_need',    -- no_need/pending/replied/forwarded
    folder TEXT DEFAULT 'INBOX',            -- 文件夹路径（软删除后改为"已删除"）
    pinned INTEGER DEFAULT 0,              -- 是否置顶（1=置顶）
    imap_folder TEXT,                      -- 原始 IMAP 文件夹，软删除后不变

    -- 关联
    thread_id TEXT,                         -- 会话线程ID
    in_reply_to TEXT,                       -- 回复目标Message-ID
    references TEXT,                        -- JSON数组引用链
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

-- ============================================
-- 3. AI处理结果表（与邮件分离，便于更新）
-- ============================================
CREATE TABLE email_ai_metadata (
    email_id TEXT PRIMARY KEY,
    
    -- 统一提取结果
    keywords TEXT,                          -- JSON数组
    summary_one_line TEXT,                  -- 一句话摘要
    summary_brief TEXT,                     -- 标准摘要
    summary_key_points TEXT,                -- JSON数组要点
    
    outline TEXT,                           -- JSON大纲结构
    categories TEXT,                        -- JSON分类标签数组（规范值见 tech_spec.md 第3节）
    sentiment TEXT,                         -- urgent/positive/negative/neutral
    suggested_reply TEXT,                   -- AI生成的建议回复草稿（可为空）

    -- 处理状态（规范值见 tech_spec.md 2.2节）
    ai_status TEXT DEFAULT 'unprocessed',   -- unprocessed/processing/processed/failed/skipped
    processing_progress INTEGER DEFAULT 0,  -- 0-100
    processing_stage TEXT,                  -- 当前阶段描述
    processed_at TIMESTAMP,
    processing_error TEXT,
    
    -- 向量嵌入（可选，用于语义搜索）
    embedding_vector BLOB,
    
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE
);

-- ============================================
-- 4. 任务表（ToDo）
-- 注意：tasks 表的完整字段定义以 ToDoListDesign.md 为权威来源。
--       本处为简化概览版，完整 CHECK 约束、时间戳格式等以 ToDoListDesign.md 为准。
-- ============================================
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    source_email_id TEXT,                   -- 关联邮件（可为空）
    source_task_index INTEGER,              -- 邮件中的第几个任务
    source_type TEXT DEFAULT 'manual',      -- extracted/manual/template/recurring（规范值见 tech_spec.md 2.9节）

    -- 内容
    title TEXT NOT NULL,
    description TEXT,
    
    -- 状态（完整状态机见 ToDoListDesign.md；规范枚举见 tech_spec.md 2.6节）
    status TEXT DEFAULT 'pending'           -- pending/in_progress/snoozed/completed/cancelled/rejected/archived
        CHECK(status IN ('pending', 'in_progress', 'snoozed', 'completed', 'cancelled', 'rejected', 'archived')),
    priority TEXT DEFAULT 'medium',         -- high/medium/low
    is_flagged INTEGER DEFAULT 0,
    
    -- 时间
    due_date TIMESTAMP,
    due_date_source TEXT,                   -- ai_extracted/user_set/inferred
    snoozed_until TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- 分类
    category TEXT,
    tags TEXT,                              -- JSON数组
    
    -- 扩展数据
    metadata TEXT,                          -- JSON：来源、子任务、提醒等
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (source_email_id) REFERENCES emails(id) ON DELETE SET NULL
);

-- ============================================
-- 5. AI对话历史表
-- ============================================
CREATE TABLE chat_conversations (
    id TEXT PRIMARY KEY,
    email_id TEXT,                          -- 关联邮件（可选）
    title TEXT,                             -- 对话主题（自动生成）
    
    -- 消息列表（JSON存储，减少表关联）
    messages TEXT NOT NULL,                 -- JSON数组：[{role, content, timestamp}, ...]
    
    -- 上下文
    context_type TEXT,                      -- email_assist/general_search
    referenced_email_ids TEXT,              -- JSON数组引用的邮件
    
    -- 统计
    message_count INTEGER DEFAULT 0,
    last_message_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE SET NULL
);

-- ============================================
-- 6. 用户设置表（键值对+结构化）
-- ============================================
CREATE TABLE user_settings (
    key TEXT PRIMARY KEY,
    value TEXT,                             -- JSON序列化值
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 预置配置项
INSERT INTO user_settings (key, value) VALUES
('app_theme', '"light"'),
('language', '"zh-CN"'),
('ai_provider', '{"type": "openclaw", "base_url": "http://127.0.0.1:18789/v1", "model": "default"}'),
('sync_settings', '{"interval_minutes": 2, "batch_size": 50, "auto_sync": true}'),
('notification_settings', '{"desktop": true, "sound": true, "do_not_disturb": false}'),
('display_settings', '{"density": "comfortable", "preview_lines": 3, "show_summary": true}'),
('plugin_settings', '{"enabled": ["unified_extract", "smart_classify", "extract_tasks"], "custom": {}}');

-- ============================================
-- 7. 附件表（元数据，文件存磁盘）
-- ============================================
CREATE TABLE attachments (
    id TEXT PRIMARY KEY,
    email_id TEXT NOT NULL,
    
    filename TEXT,
    content_type TEXT,
    size_bytes INTEGER,
    content_id TEXT,                        -- HTML内嵌引用ID
    
    -- 本地存储
    storage_path TEXT,                      -- 相对路径
    storage_hash TEXT,                      -- 文件内容哈希
    is_downloaded INTEGER DEFAULT 0,
    
    -- AI处理
    ai_description TEXT,                    -- AI生成的附件描述
    extracted_text TEXT,                    -- OCR或文本提取
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE
);

-- ============================================
-- 8. 搜索历史表
-- ============================================
CREATE TABLE search_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    query_type TEXT,                        -- keyword/semantic/advanced
    result_count INTEGER,
    clicked_email_ids TEXT,                 -- JSON数组
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 9. 操作日志表（审计+撤销）
-- ============================================
CREATE TABLE activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL,              -- create/update/delete/send/ai_generate
    entity_type TEXT,                       -- email/task/conversation/settings
    entity_id TEXT,
    
    old_value TEXT,                         -- JSON（更新前）
    new_value TEXT,                         -- JSON（更新后）
    
    user_context TEXT,                      -- 操作上下文
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================
-- 索引优化
-- ============================================
CREATE INDEX idx_emails_account ON emails(account_id);
CREATE INDEX idx_emails_folder ON emails(folder);
CREATE INDEX idx_emails_thread ON emails(thread_id);
CREATE INDEX idx_emails_received ON emails(received_at DESC);
CREATE INDEX idx_emails_status ON emails(read_status, flag_status);
CREATE INDEX idx_emails_hash ON emails(hash);
CREATE INDEX idx_emails_pinned ON emails(pinned DESC);

CREATE INDEX idx_ai_status ON email_ai_metadata(ai_status);
CREATE INDEX idx_ai_categories ON email_ai_metadata(categories);  -- 需SQLite JSON索引扩展

CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_due ON tasks(due_date);
CREATE INDEX idx_tasks_email ON tasks(source_email_id);

CREATE INDEX idx_attachments_email ON attachments(email_id);

-- ============================================
-- 全文搜索（FTS5）
-- ============================================
-- WAL 模式（初始化时执行，提升并发读写性能）
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE VIRTUAL TABLE emails_fts USING fts5(
    subject,
    body_text,
    from_name,                              -- 发件人姓名（从 from_address JSON 中提取）
    content='emails',
    content_rowid='rowid',
    tokenize='unicode61'                    -- 支持中文、日文等 Unicode 字符
);
-- 注：summary_one_line / keywords 存储在 email_ai_metadata 表，
--     无法通过 content='emails' 的 FTS5 表统一索引。
--     AI 字段的全文检索在 Phase 5 通过 ChromaDB 向量搜索覆盖。

-- 触发器：保持 FTS5 索引与 emails 表同步
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

---

## Python数据访问层

```python
import sqlite3
import json
import uuid
import hashlib
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from contextlib import contextmanager
from pathlib import Path

# ============================================
# 数据模型定义
# ============================================

@dataclass
class Account:
    id: str
    email_address: str
    display_name: Optional[str] = None
    provider_type: str = 'imap'
    is_enabled: bool = True
    imap_server: Optional[str] = None
    imap_port: int = 993
    smtp_server: Optional[str] = None
    smtp_port: int = 465
    credentials_encrypted: Optional[bytes] = None
    sync_interval_minutes: int = 2
    last_sync_at: Optional[datetime] = None
    sync_cursor: Optional[str] = None
    status: str = 'active'
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class Email:
    id: str
    account_id: str
    subject: Optional[str] = None
    from_address: Optional[Dict] = None
    to_addresses: List[Dict] = None
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    sent_at: Optional[datetime] = None
    received_at: Optional[datetime] = None
    read_status: str = 'unread'
    flag_status: str = 'none'
    folder: str = 'INBOX'
    thread_id: Optional[str] = None
    sync_status: str = 'pending'
    is_downloaded: bool = False
    size_bytes: int = 0
    hash: Optional[str] = None
    
    # AI元数据（非数据库字段，关联查询填充）
    ai_metadata: Optional['EmailAIMetadata'] = None
    
    def __post_init__(self):
        if self.to_addresses is None:
            self.to_addresses = []

@dataclass
class EmailAIMetadata:
    email_id: str
    keywords: List[str] = None
    summary_one_line: Optional[str] = None
    summary_brief: Optional[str] = None
    summary_key_points: List[str] = None
    outline: List[Dict] = None
    categories: List[str] = None
    sentiment: Optional[str] = None
    suggested_reply: Optional[str] = None
    ai_status: str = 'unprocessed'
    processing_progress: int = 0
    processing_stage: Optional[str] = None
    processed_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.keywords is None: self.keywords = []
        if self.summary_key_points is None: self.summary_key_points = []
        if self.outline is None: self.outline = []
        if self.categories is None: self.categories = []

@dataclass
class Task:
    id: str
    source_email_id: Optional[str] = None
    source_task_index: Optional[int] = None
    source_type: str = 'manual'
    title: str = ""
    description: Optional[str] = None
    status: str = 'pending'
    priority: str = 'medium'
    is_flagged: bool = False
    due_date: Optional[datetime] = None
    due_date_source: Optional[str] = None
    snoozed_until: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    category: Optional[str] = None
    tags: List[str] = None
    metadata: Dict = None
    
    def __post_init__(self):
        if self.tags is None: self.tags = []
        if self.metadata is None: self.metadata = {}

# ============================================
# 存储管理器
# ============================================

class StorageManager:
    """统一数据存储管理"""
    
    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = Path.home() / '.clawmail' / 'data'
        
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.db_path = self.data_dir / 'clawmail.db'
        self.attachments_dir = self.data_dir / 'attachments'
        self.cache_dir = self.data_dir / 'cache'
        
        # 初始化子目录
        for subdir in [self.attachments_dir, self.cache_dir]:
            subdir.mkdir(exist_ok=True)
        
        # 初始化数据库
        self._init_database()
    
    @contextmanager
    def _connect(self):
        """数据库连接上下文"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")  # 启用外键约束
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_database(self):
        """执行所有建表语句，并自动迁移旧数据库新增列。"""
        schema = """
        -- [粘贴上面的完整SQL Schema到这里]
        """

        with self._connect() as conn:
            conn.executescript(schema)
            # 列迁移：兼容旧数据库（ALTER TABLE 若列已存在会静默失败）
            cols = {r[1] for r in conn.execute("PRAGMA table_info(emails)")}
            if "pinned" not in cols:
                conn.execute("ALTER TABLE emails ADD COLUMN pinned INTEGER DEFAULT 0")
            if "imap_folder" not in cols:
                conn.execute("ALTER TABLE emails ADD COLUMN imap_folder TEXT")
            conn.commit()
    
    # ========================================
    # 账户操作
    # ========================================
    
    def create_account(self, account: Account) -> str:
        account.id = str(uuid.uuid4())[:8]
        account.created_at = datetime.now()
        account.updated_at = datetime.now()
        
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO accounts VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                account.id, account.email_address, account.display_name,
                account.provider_type, int(account.is_enabled),
                account.imap_server, account.imap_port,
                account.smtp_server, account.smtp_port,
                account.credentials_encrypted,
                account.sync_interval_minutes, account.last_sync_at,
                account.sync_cursor, account.status, account.error_message,
                account.created_at, account.updated_at
            ))
        
        return account.id
    
    def get_account(self, account_id: str) -> Optional[Account]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE id = ?", 
                (account_id,)
            ).fetchone()
            return self._row_to_account(row) if row else None
    
    def get_all_accounts(self) -> List[Account]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM accounts WHERE is_enabled = 1").fetchall()
            return [self._row_to_account(r) for r in rows]
    
    # ========================================
    # 邮件操作
    # ========================================
    
    def save_email(self, email: Email) -> str:
        """保存或更新邮件"""
        if not email.id:
            email.id = str(uuid.uuid4())[:8]
            email.created_at = datetime.now()
        
        email.updated_at = datetime.now()
        email.hash = self._compute_email_hash(email)
        
        with self._connect() as conn:
            # 检查是否已存在（通过hash去重）
            existing = conn.execute(
                "SELECT id FROM emails WHERE hash = ?", 
                (email.hash,)
            ).fetchone()
            
            if existing:
                return existing['id']  # 已存在，返回现有ID
            
            conn.execute("""
                INSERT INTO emails (
                    id, account_id, imap_uid, message_id, subject,
                    from_address, to_addresses, cc_addresses, bcc_addresses,
                    body_text, body_html, content_type, charset,
                    sent_at, received_at, internal_date,
                    raw_headers, size_bytes, hash,
                    sync_status, is_downloaded, read_status, flag_status, folder,
                    thread_id, in_reply_to, references,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                email.id, email.account_id, None, None, email.subject,
                json.dumps(email.from_address) if email.from_address else None,
                json.dumps(email.to_addresses) if email.to_addresses else None,
                None, None,  # cc, bcc
                email.body_text, email.body_html, 'text/plain', 'utf-8',
                email.sent_at, email.received_at, None,
                None, email.size_bytes, email.hash,
                email.sync_status, int(email.is_downloaded),
                email.read_status, email.flag_status, email.folder,
                email.thread_id, None, None,
                email.created_at, email.updated_at
            ))
            
            # 初始化AI元数据记录
            conn.execute(
                "INSERT OR IGNORE INTO email_ai_metadata (email_id) VALUES (?)",
                (email.id,)
            )
        
        return email.id
    
    def get_email(self, email_id: str, with_ai: bool = True) -> Optional[Email]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM emails WHERE id = ?", 
                (email_id,)
            ).fetchone()
            
            if not row:
                return None
            
            email = self._row_to_email(row)
            
            if with_ai:
                ai_row = conn.execute(
                    "SELECT * FROM email_ai_metadata WHERE email_id = ?",
                    (email_id,)
                ).fetchone()
                if ai_row:
                    email.ai_metadata = self._row_to_ai_metadata(ai_row)
            
            return email
    
    def get_emails_by_folder(self, account_id: str, folder: str = 'INBOX', 
                            limit: int = 50, offset: int = 0) -> List[Email]:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT e.*, 
                       m.summary_one_line, m.summary_brief, 
                       m.categories, m.ai_status, m.processing_progress
                FROM emails e
                LEFT JOIN email_ai_metadata m ON e.id = m.email_id
                WHERE e.account_id = ? AND e.folder = ?
                ORDER BY e.pinned DESC, e.received_at DESC
                LIMIT ? OFFSET ?
            """, (account_id, folder, limit, offset)).fetchall()
            
            return [self._row_to_email(r, with_ai_preview=True) for r in rows]
    
    def update_email_ai_metadata(self, email_id: str, metadata: EmailAIMetadata):
        """更新AI处理结果"""
        with self._connect() as conn:
            conn.execute("""
                UPDATE email_ai_metadata SET
                    keywords = ?,
                    summary_one_line = ?,
                    summary_brief = ?,
                    summary_key_points = ?,
                    outline = ?,
                    categories = ?,
                    sentiment = ?,
                    suggested_reply = ?,
                    ai_status = ?,
                    processing_progress = ?,
                    processing_stage = ?,
                    processed_at = ?,
                    updated_at = ?
                WHERE email_id = ?
            """, (
                json.dumps(metadata.keywords, ensure_ascii=False),
                metadata.summary_one_line,
                metadata.summary_brief,
                json.dumps(metadata.summary_key_points, ensure_ascii=False),
                json.dumps(metadata.outline, ensure_ascii=False),
                json.dumps(metadata.categories, ensure_ascii=False),
                metadata.sentiment,
                metadata.suggested_reply,
                metadata.ai_status,
                metadata.processing_progress,
                metadata.processing_stage,
                metadata.processed_at or datetime.now(),
                datetime.now(),
                email_id
            ))
    
    def mark_email_read(self, email_id: str, read: bool = True):
        with self._connect() as conn:
            conn.execute("""
                UPDATE emails SET read_status = ?, updated_at = ? WHERE id = ?
            """, ('read' if read else 'unread', datetime.now(), email_id))

    def update_email_flag(self, email_id: str, flag_status: str) -> None:
        """更新旗标状态。flag_status: 'none' | 'flagged' | 'completed'"""
        with self._connect() as conn:
            conn.execute(
                "UPDATE emails SET flag_status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (flag_status, email_id),
            )
            conn.commit()

    def update_email_folder(self, email_id: str, folder: str) -> None:
        """将邮件移动到指定文件夹（软删除/恢复/移动）。"""
        with self._connect() as conn:
            conn.execute(
                "UPDATE emails SET folder=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (folder, email_id),
            )
            conn.commit()

    def update_email_pinned(self, email_id: str, pinned: bool) -> None:
        """设置或取消置顶。置顶邮件在列表中排在最前（ORDER BY pinned DESC）。"""
        with self._connect() as conn:
            conn.execute(
                "UPDATE emails SET pinned=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (1 if pinned else 0, email_id),
            )
            conn.commit()

    def delete_email(self, email_id: str) -> None:
        """彻底从本地数据库删除邮件（外键级联删除 email_ai_metadata）。"""
        with self._connect() as conn:
            conn.execute("DELETE FROM emails WHERE id=?", (email_id,))
            conn.commit()

    def update_draft(self, draft_id: str, to_addresses, cc_addresses,
                     subject: str, body_text: str, body_html) -> None:
        """更新草稿箱中已有草稿的内容（仅对 folder='草稿箱' 生效）。
        与 save_email() 的 INSERT OR IGNORE 不同，此方法执行 UPDATE。
        """
        new_hash = hashlib.sha256((subject + (body_text or "")).encode()).hexdigest()
        with self._connect() as conn:
            conn.execute(
                """UPDATE emails
                   SET to_addresses=?, cc_addresses=?, subject=?,
                       body_text=?, body_html=?, hash=?,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND folder='草稿箱'""",
                (
                    json.dumps(to_addresses) if to_addresses else None,
                    json.dumps(cc_addresses) if cc_addresses else None,
                    subject, body_text, body_html, new_hash, draft_id,
                ),
            )
            conn.commit()

    def count_emails(self, account_id: Optional[str] = None) -> int:
        """返回本地存储的邮件总数。account_id 为 None 时统计所有账户。"""
        with self.get_conn() as conn:
            if account_id:
                row = conn.execute(
                    "SELECT COUNT(*) FROM emails WHERE account_id = ?", (account_id,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM emails").fetchone()
            return row[0] if row else 0

    def delete_all_emails(self, account_id: Optional[str] = None) -> int:
        """删除本地所有邮件（级联删除 email_ai_metadata、attachments），
        并重置对应账户的 sync_cursor 为 NULL，使下次同步重新从服务器拉取。
        返回删除的邮件数量。"""
        with self.get_conn() as conn:
            if account_id:
                count = conn.execute(
                    "SELECT COUNT(*) FROM emails WHERE account_id = ?", (account_id,)
                ).fetchone()[0]
                conn.execute("DELETE FROM emails WHERE account_id = ?", (account_id,))
                conn.execute(
                    "UPDATE accounts SET sync_cursor = NULL, updated_at = ? WHERE id = ?",
                    (datetime.utcnow().isoformat(), account_id)
                )
            else:
                count = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
                conn.execute("DELETE FROM emails")
                conn.execute(
                    "UPDATE accounts SET sync_cursor = NULL, updated_at = ?",
                    (datetime.utcnow().isoformat(),)
                )
            conn.commit()
        return count
    
    # ========================================
    # 任务操作
    # ========================================
    
    def create_task(self, task: Task) -> str:
        if not task.id:
            task.id = f"task_{str(uuid.uuid4())[:6]}"
        
        task.created_at = datetime.now()
        task.updated_at = datetime.now()
        
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO tasks (
                    id, source_email_id, source_task_index, source_type,
                    title, description,
                    status, priority, is_flagged,
                    due_date, due_date_source, snoozed_until, completed_at,
                    category, tags, metadata,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                task.id, task.source_email_id, task.source_task_index, task.source_type,
                task.title, task.description,
                task.status, task.priority, int(task.is_flagged),
                task.due_date, task.due_date_source, task.snoozed_until, task.completed_at,
                task.category,
                json.dumps(task.tags, ensure_ascii=False),
                json.dumps(task.metadata, ensure_ascii=False),
                task.created_at, task.updated_at
            ))
        
        return task.id
    
    def get_tasks(self, status: Optional[str] = None, 
                  due_before: Optional[datetime] = None) -> List[Task]:
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        if due_before:
            query += " AND due_date <= ?"
            params.append(due_before)
        
        query += " ORDER BY due_date ASC NULLS LAST, priority DESC"
        
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_task(r) for r in rows]
    
    def update_task_status(self, task_id: str, status: str):
        with self._connect() as conn:
            conn.execute("""
                UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?
            """, (status, datetime.now(), task_id))
    
    # ========================================
    # 设置操作
    # ========================================
    
    def get_setting(self, key: str, default=None) -> Any:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM user_settings WHERE key = ?", 
                (key,)
            ).fetchone()
            
            if row:
                return json.loads(row['value'])
            return default
    
    def set_setting(self, key: str, value: Any):
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO user_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
            """, (key, json.dumps(value, ensure_ascii=False), datetime.now()))
    
    # ========================================
    # 附件存储
    # ========================================
    
    def save_attachment(self, email_id: str, filename: str, 
                       content_type: str, data: bytes) -> str:
        """保存附件到磁盘，返回存储路径"""
        # 按年月组织目录
        now = datetime.now()
        subdir = self.attachments_dir / str(now.year) / f"{now.month:02d}"
        subdir.mkdir(parents=True, exist_ok=True)
        
        # 哈希命名防重
        file_hash = hashlib.sha256(data).hexdigest()[:16]
        ext = Path(filename).suffix
        storage_name = f"{file_hash}{ext}"
        storage_path = subdir / storage_name
        
        # 写入文件
        storage_path.write_bytes(data)
        
        # 记录元数据
        rel_path = str(storage_path.relative_to(self.data_dir))
        with self._connect() as conn:
            attach_id = str(uuid.uuid4())[:8]
            conn.execute("""
                INSERT INTO attachments (id, email_id, filename, content_type,
                                        size_bytes, storage_path, storage_hash, is_downloaded)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """, (attach_id, email_id, filename, content_type, 
                  len(data), rel_path, file_hash))
        
        return str(storage_path)
    
    def get_attachment_path(self, attachment_id: str) -> Optional[Path]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT storage_path FROM attachments WHERE id = ?", 
                (attachment_id,)
            ).fetchone()
            
            if row:
                return self.data_dir / row['storage_path']
            return None
    
    # ========================================
    # 辅助方法
    # ========================================
    
    def _compute_email_hash(self, email: Email) -> str:
        """计算邮件内容哈希用于去重"""
        content = f"{email.subject}:{email.body_text}:{email.sent_at}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]
    
    def _row_to_account(self, row) -> Account:
        return Account(
            id=row['id'],
            email_address=row['email_address'],
            display_name=row['display_name'],
            # ... 其他字段映射
        )
    
    def _row_to_email(self, row, with_ai_preview=False) -> Email:
        email = Email(
            id=row['id'],
            account_id=row['account_id'],
            subject=row['subject'],
            from_address=json.loads(row['from_address']) if row['from_address'] else None,
            to_addresses=json.loads(row['to_addresses']) if row['to_addresses'] else [],
            body_text=row['body_text'],
            read_status=row['read_status'],
            flag_status=row['flag_status'],
            folder=row['folder'],
            thread_id=row['thread_id'],
            received_at=row['received_at'],
            sync_status=row['sync_status']
        )
        
        if with_ai_preview and 'summary_one_line' in row.keys():
            email.ai_metadata = EmailAIMetadata(
                email_id=row['id'],
                summary_one_line=row['summary_one_line'],
                summary_brief=row['summary_brief'],
                categories=json.loads(row['categories']) if row['categories'] else [],
                ai_status=row['ai_status'],
                processing_progress=row['processing_progress']
            )
        
        return email
    
    def _row_to_ai_metadata(self, row) -> EmailAIMetadata:
        return EmailAIMetadata(
            email_id=row['email_id'],
            keywords=json.loads(row['keywords']) if row['keywords'] else [],
            summary_one_line=row['summary_one_line'],
            summary_brief=row['summary_brief'],
            summary_key_points=json.loads(row['summary_key_points']) if row['summary_key_points'] else [],
            outline=json.loads(row['outline']) if row['outline'] else [],
            categories=json.loads(row['categories']) if row['categories'] else [],
            sentiment=row['sentiment'],
            ai_status=row['ai_status'],
            processing_progress=row['processing_progress'],
            processing_stage=row['processing_stage'],
            processed_at=row['processed_at']
        )
    
    def _row_to_task(self, row) -> Task:
        return Task(
            id=row['id'],
            source_email_id=row['source_email_id'],
            title=row['title'],
            status=row['status'],
            priority=row['priority'],
            due_date=row['due_date'],
            tags=json.loads(row['tags']) if row['tags'] else [],
            metadata=json.loads(row['metadata']) if row['metadata'] else {}
        )
```

---

## 使用示例

```python
# 初始化存储
storage = StorageManager()

# 创建账户
account = Account(
    email_address="user@163.com",
    display_name="我的工作邮箱",
    imap_server="imap.163.com",
    imap_port=993
)
account_id = storage.create_account(account)

# 保存邮件
email = Email(
    account_id=account_id,
    subject="Q4项目进度汇报",
    from_address={"name": "张三", "email": "zhangsan@company.com"},
    to_addresses=[{"name": "我", "email": "user@163.com"}],
    body_text="项目已完成80%，预计延期两周...",
    received_at=datetime.now(),
    size_bytes=1024
)
email_id = storage.save_email(email)

# 更新AI处理结果
ai_result = EmailAIMetadata(
    email_id=email_id,
    keywords=["Q4项目", "延期", "进度"],
    summary_one_line="张三申请项目延期两周",
    summary_brief="Q4项目因供应商延迟申请延期，预计影响...",
    categories=["紧急", "项目A"],
    ai_status="processed",
    processing_progress=100
)
storage.update_email_ai_metadata(email_id, ai_result)

# 创建关联任务
task = Task(
    source_email_id=email_id,
    title="评估延期申请并回复张三",
    priority="high",
    due_date=datetime(2024, 1, 17),
    due_date_source="ai_extracted",
    metadata={"source_quote": "请周五前确认是否同意"}
)
task_id = storage.create_task(task)

# 查询今日待办
today_tasks = storage.get_tasks(status='pending')
for t in today_tasks:
    print(f"• {t.title} ({t.priority})")

# 读取设置
ai_config = storage.get_setting('ai_provider', 
                                default={"type": "openclaw", "base_url": "http://localhost:8000/v1"})
```

---

## 备份与导出

```python
import shutil
import zipfile

class DataExporter:
    def __init__(self, storage: StorageManager):
        self.storage = storage
    
    def backup_to_zip(self, output_path: str):
        """打包所有数据为ZIP"""
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 数据库
            zf.write(self.storage.db_path, 'clawmail.db')
            
            # 附件
            for file in self.storage.attachments_dir.rglob('*'):
                if file.is_file():
                    zf.write(file, f"attachments/{file.relative_to(self.storage.attachments_dir)}")
            
            # 配置
            config_path = self.storage.data_dir / 'config.yaml'
            if config_path.exists():
                zf.write(config_path, 'config.yaml')
    
    def export_emails_to_mbox(self, output_path: str, account_id: Optional[str] = None):
        """导出为标准MBOX格式（兼容其他邮件客户端）"""
        # 实现MBOX格式写入...
        pass
```

