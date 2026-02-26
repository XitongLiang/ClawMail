"""
ClawDB — SQLite 数据访问层
完整 DDL 与 CRUD 实现。
Schema 来源：design/userDataStorageDesign.md
"""

import json
import sqlite3
import uuid
import hashlib
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from clawmail.domain.models.account import Account
from clawmail.domain.models.email import Email, EmailAIMetadata
from clawmail.domain.models.task import Task


# ============================================================
# DDL
# ============================================================

_PRAGMAS = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;
"""

_DDL = """
-- 1. 账户表
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    email_address TEXT UNIQUE NOT NULL,
    display_name TEXT,
    provider_type TEXT DEFAULT 'imap',
    is_enabled INTEGER DEFAULT 1,
    imap_server TEXT,
    imap_port INTEGER DEFAULT 993,
    smtp_server TEXT,
    smtp_port INTEGER DEFAULT 465,
    credentials_encrypted BLOB,
    sync_interval_minutes INTEGER DEFAULT 2,
    last_sync_at TIMESTAMP,
    sync_cursor TEXT,
    status TEXT DEFAULT 'active'
        CHECK(status IN ('active', 'error', 'paused')),
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. 邮件表
CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    imap_uid TEXT,
    message_id TEXT,
    subject TEXT,
    from_address TEXT,
    to_addresses TEXT,
    cc_addresses TEXT,
    bcc_addresses TEXT,
    body_text TEXT,
    body_html TEXT,
    content_type TEXT,
    charset TEXT DEFAULT 'utf-8',
    sent_at TIMESTAMP,
    received_at TIMESTAMP,
    internal_date TIMESTAMP,
    raw_headers TEXT,
    size_bytes INTEGER,
    hash TEXT UNIQUE,
    sync_status TEXT DEFAULT 'pending'
        CHECK(sync_status IN ('pending', 'downloading', 'completed', 'failed')),
    is_downloaded INTEGER DEFAULT 0,
    read_status TEXT DEFAULT 'unread'
        CHECK(read_status IN ('unread', 'read', 'skimmed')),
    flag_status TEXT DEFAULT 'none'
        CHECK(flag_status IN ('none', 'flagged', 'completed')),
    reply_status TEXT DEFAULT 'no_need'
        CHECK(reply_status IN ('no_need', 'pending', 'replied', 'forwarded')),
    folder TEXT DEFAULT 'INBOX',
    imap_folder TEXT,
    pinned INTEGER DEFAULT 0,
    thread_id TEXT,
    in_reply_to TEXT,
    email_references TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

-- 3. AI 处理结果表
CREATE TABLE IF NOT EXISTS email_ai_metadata (
    email_id TEXT PRIMARY KEY,
    keywords TEXT,
    summary_one_line TEXT,
    summary_brief TEXT,
    summary_key_points TEXT,
    outline TEXT,
    categories TEXT,
    sentiment TEXT
        CHECK(sentiment IN ('urgent', 'positive', 'negative', 'neutral') OR sentiment IS NULL),
    suggested_reply TEXT,
    is_spam INTEGER DEFAULT NULL,
    action_items TEXT,
    reply_stances TEXT,
    urgency TEXT CHECK(urgency IN ('high','medium','low') OR urgency IS NULL),
    feedback_rating INTEGER CHECK(feedback_rating BETWEEN 1 AND 5 OR feedback_rating IS NULL),
    ai_status TEXT DEFAULT 'unprocessed'
        CHECK(ai_status IN ('unprocessed', 'processing', 'processed', 'failed', 'skipped')),
    processing_progress INTEGER DEFAULT 0,
    processing_stage TEXT,
    processed_at TIMESTAMP,
    processing_error TEXT,
    embedding_vector BLOB,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE
);

-- 4. 任务表
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    source_email_id TEXT,
    source_task_index INTEGER,
    source_type TEXT DEFAULT 'manual'
        CHECK(source_type IN ('extracted', 'manual', 'template', 'recurring')),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'pending'
        CHECK(status IN ('pending', 'in_progress', 'snoozed', 'completed', 'cancelled', 'rejected', 'archived')),
    priority TEXT DEFAULT 'medium'
        CHECK(priority IN ('high', 'medium', 'low', 'none')),
    is_flagged INTEGER DEFAULT 0,
    due_date TIMESTAMP,
    due_date_source TEXT
        CHECK(due_date_source IN ('ai_extracted', 'user_set', 'inferred') OR due_date_source IS NULL),
    snoozed_until TIMESTAMP,
    completed_at TIMESTAMP,
    category TEXT,
    tags TEXT,
    metadata TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_email_id) REFERENCES emails(id) ON DELETE SET NULL
);

-- 5. AI 对话历史表
CREATE TABLE IF NOT EXISTS chat_conversations (
    id TEXT PRIMARY KEY,
    email_id TEXT,
    title TEXT,
    messages TEXT NOT NULL,
    context_type TEXT
        CHECK(context_type IN ('email_assist', 'general_search') OR context_type IS NULL),
    referenced_email_ids TEXT,
    message_count INTEGER DEFAULT 0,
    last_message_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE SET NULL
);

-- 6. 用户设置表
CREATE TABLE IF NOT EXISTS user_settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. 附件表
CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    email_id TEXT NOT NULL,
    filename TEXT,
    content_type TEXT,
    size_bytes INTEGER,
    content_id TEXT,
    storage_path TEXT,
    storage_hash TEXT,
    is_downloaded INTEGER DEFAULT 0,
    ai_description TEXT,
    extracted_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE
);

-- 8. 搜索历史表
CREATE TABLE IF NOT EXISTS search_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    query_type TEXT
        CHECK(query_type IN ('keyword', 'semantic', 'advanced') OR query_type IS NULL),
    result_count INTEGER,
    clicked_email_ids TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 9. 操作日志表
CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action_type TEXT NOT NULL
        CHECK(action_type IN ('create', 'update', 'delete', 'send', 'ai_generate')),
    entity_type TEXT
        CHECK(entity_type IN ('email', 'task', 'conversation', 'settings') OR entity_type IS NULL),
    entity_id TEXT,
    old_value TEXT,
    new_value TEXT,
    user_context TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_emails_account  ON emails(account_id);
CREATE INDEX IF NOT EXISTS idx_emails_folder   ON emails(folder);
CREATE INDEX IF NOT EXISTS idx_emails_thread   ON emails(thread_id);
CREATE INDEX IF NOT EXISTS idx_emails_received ON emails(received_at DESC);
CREATE INDEX IF NOT EXISTS idx_emails_status   ON emails(read_status, flag_status);
CREATE INDEX IF NOT EXISTS idx_emails_hash     ON emails(hash);

CREATE INDEX IF NOT EXISTS idx_ai_status       ON email_ai_metadata(ai_status);

CREATE INDEX IF NOT EXISTS idx_tasks_status    ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_due       ON tasks(due_date);
CREATE INDEX IF NOT EXISTS idx_tasks_email     ON tasks(source_email_id);

CREATE INDEX IF NOT EXISTS idx_attachments_email ON attachments(email_id);
"""

_FTS5 = """
CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts USING fts5(
    subject,
    body_text,
    from_name,
    content='emails',
    content_rowid='rowid',
    tokenize='unicode61'
);
"""

_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS emails_fts_insert
AFTER INSERT ON emails BEGIN
    INSERT INTO emails_fts(rowid, subject, body_text, from_name)
    VALUES (new.rowid, new.subject, new.body_text,
            json_extract(new.from_address, '$.name'));
END;

CREATE TRIGGER IF NOT EXISTS emails_fts_update
AFTER UPDATE OF subject, body_text, from_address ON emails BEGIN
    INSERT INTO emails_fts(emails_fts, rowid, subject, body_text, from_name)
    VALUES ('delete', old.rowid, old.subject, old.body_text,
            json_extract(old.from_address, '$.name'));
    INSERT INTO emails_fts(rowid, subject, body_text, from_name)
    VALUES (new.rowid, new.subject, new.body_text,
            json_extract(new.from_address, '$.name'));
END;

CREATE TRIGGER IF NOT EXISTS emails_fts_delete
AFTER DELETE ON emails BEGIN
    INSERT INTO emails_fts(emails_fts, rowid, subject, body_text, from_name)
    VALUES ('delete', old.rowid, old.subject, old.body_text,
            json_extract(old.from_address, '$.name'));
END;
"""

_DEFAULT_SETTINGS = [
    ("app_theme", '"light"'),
    ("language", '"zh-CN"'),
    ("ai_provider", '{"type": "openclaw", "base_url": "http://127.0.0.1:18789/v1", "model": "default"}'),
    ("sync_settings", '{"interval_minutes": 2, "batch_size": 50, "auto_sync": true}'),
    ("notification_settings", '{"desktop": true, "sound": true, "do_not_disturb": false}'),
    ("display_settings", '{"density": "comfortable", "preview_lines": 3, "show_summary": true}'),
    ("plugin_settings", '{"enabled": ["unified_extract", "smart_classify", "extract_tasks"], "custom": {}}'),
]


def _build_fts_query(raw: str) -> str:
    """将用户输入转换为 FTS5 MATCH 表达式（每词前缀匹配）。"""
    words = [w.strip() for w in raw.split() if w.strip()]
    if not words:
        return '""'
    return " ".join(f'"{w.replace(chr(34), "")}"*' for w in words)


# ============================================================
# ClawDB
# ============================================================

class ClawDB:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.db_path = data_dir / "clawmail.db"

    def initialize(self) -> None:
        """创建数据目录，建表，插入默认配置。幂等，可多次调用。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "attachments").mkdir(exist_ok=True)
        (self.data_dir / "cache").mkdir(exist_ok=True)
        (self.data_dir / "logs").mkdir(exist_ok=True)

        with self.get_conn() as conn:
            # PRAGMA 语句需逐条执行
            for stmt in _PRAGMAS.strip().split("\n"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)

            conn.executescript(_DDL)
            conn.executescript(_INDEXES)
            conn.executescript(_FTS5)
            conn.executescript(_TRIGGERS)

            # 默认配置（INSERT OR IGNORE 保证幂等）
            conn.executemany(
                "INSERT OR IGNORE INTO user_settings (key, value) VALUES (?, ?)",
                _DEFAULT_SETTINGS,
            )
            conn.commit()

        # 兼容旧数据库：按需添加新列
        with self.get_conn() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(emails)")}
            if "pinned" not in cols:
                conn.execute("ALTER TABLE emails ADD COLUMN pinned INTEGER DEFAULT 0")
            if "imap_folder" not in cols:
                conn.execute("ALTER TABLE emails ADD COLUMN imap_folder TEXT")
            ai_cols = {r[1] for r in conn.execute("PRAGMA table_info(email_ai_metadata)")}
            if "is_spam" not in ai_cols:
                conn.execute("ALTER TABLE email_ai_metadata ADD COLUMN is_spam INTEGER DEFAULT NULL")
            if "action_items" not in ai_cols:
                conn.execute("ALTER TABLE email_ai_metadata ADD COLUMN action_items TEXT")
            if "reply_stances" not in ai_cols:
                conn.execute("ALTER TABLE email_ai_metadata ADD COLUMN reply_stances TEXT")
            if "urgency" not in ai_cols:
                conn.execute("ALTER TABLE email_ai_metadata ADD COLUMN urgency TEXT")
            if "feedback_rating" not in ai_cols:
                conn.execute("ALTER TABLE email_ai_metadata ADD COLUMN feedback_rating INTEGER")
            conn.commit()

    @contextmanager
    def get_conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # --------------------------------------------------------
    # accounts
    # --------------------------------------------------------

    def create_account(self, account: Account) -> None:
        with self.get_conn() as conn:
            conn.execute(
                """INSERT INTO accounts (
                    id, email_address, display_name, provider_type, is_enabled,
                    imap_server, imap_port, smtp_server, smtp_port,
                    credentials_encrypted, sync_interval_minutes,
                    last_sync_at, sync_cursor, status, error_message,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    account.id, account.email_address, account.display_name,
                    account.provider_type, int(account.is_enabled),
                    account.imap_server, account.imap_port,
                    account.smtp_server, account.smtp_port,
                    account.credentials_encrypted,
                    account.sync_interval_minutes,
                    account.last_sync_at, account.sync_cursor,
                    account.status, account.error_message,
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

    def get_account(self, account_id: str) -> Optional[Account]:
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            return self._row_to_account(row) if row else None

    def delete_account(self, account_id: str) -> None:
        """Delete an account and all its associated emails."""
        with self.get_conn() as conn:
            conn.execute("DELETE FROM emails WHERE account_id = ?", (account_id,))
            conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
            conn.commit()

    def _row_to_account(self, row: sqlite3.Row) -> Account:
        d = dict(row)
        d["is_enabled"] = bool(d["is_enabled"])
        for dt_field in ("last_sync_at", "created_at", "updated_at"):
            if d.get(dt_field):
                try:
                    d[dt_field] = datetime.fromisoformat(d[dt_field])
                except (ValueError, TypeError):
                    d[dt_field] = None
        return Account(**{k: v for k, v in d.items() if k in Account.__dataclass_fields__})

    # --------------------------------------------------------
    # emails
    # --------------------------------------------------------

    def save_email(self, email: Email) -> None:
        if not email.hash:
            content = (email.message_id or "") + (email.subject or "") + (email.body_text or "")
            email.hash = hashlib.sha256(content.encode()).hexdigest()

        with self.get_conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO emails (
                    id, account_id, imap_uid, message_id, subject,
                    from_address, to_addresses, cc_addresses, bcc_addresses,
                    body_text, body_html, content_type, charset,
                    sent_at, received_at, internal_date,
                    raw_headers, size_bytes, hash,
                    sync_status, is_downloaded,
                    read_status, flag_status, reply_status, folder, imap_folder,
                    thread_id, in_reply_to, email_references,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    email.id, email.account_id, email.imap_uid, email.message_id, email.subject,
                    json.dumps(email.from_address) if email.from_address else None,
                    json.dumps(email.to_addresses) if email.to_addresses else None,
                    json.dumps(email.cc_addresses) if email.cc_addresses else None,
                    json.dumps(email.bcc_addresses) if email.bcc_addresses else None,
                    email.body_text, email.body_html, email.content_type, email.charset,
                    email.sent_at.isoformat() if email.sent_at else None,
                    email.received_at.isoformat() if email.received_at else None,
                    email.internal_date.isoformat() if email.internal_date else None,
                    json.dumps(email.raw_headers) if email.raw_headers else None,
                    email.size_bytes, email.hash,
                    email.sync_status, int(email.is_downloaded),
                    email.read_status, email.flag_status, email.reply_status, email.folder,
                    email.imap_folder or email.folder,   # 首次保存时记录 IMAP 原始文件夹
                    email.thread_id, email.in_reply_to,
                    json.dumps(email.references) if email.references else None,
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

    def get_email(self, email_id: str) -> Optional[Email]:
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM emails WHERE id = ?", (email_id,)
            ).fetchone()
            return self._row_to_email(row) if row else None

    def get_emails_by_folder(
        self, account_id: str, folder: str = "INBOX", limit: int = 50, offset: int = 0
    ) -> List[Email]:
        with self.get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM emails
                   WHERE account_id = ? AND folder = ?
                   ORDER BY pinned DESC, received_at DESC
                   LIMIT ? OFFSET ?""",
                (account_id, folder, limit, offset),
            ).fetchall()
            return [self._row_to_email(r) for r in rows]

    def _row_to_email(self, row: sqlite3.Row) -> Email:
        d = dict(row)
        # email_references (DB column) → references (dataclass field)
        d["references"] = d.pop("email_references", None)
        for json_field in ("from_address", "to_addresses", "cc_addresses", "bcc_addresses",
                           "raw_headers", "references"):
            if d.get(json_field):
                try:
                    d[json_field] = json.loads(d[json_field])
                except (json.JSONDecodeError, TypeError):
                    d[json_field] = None
        d["is_downloaded"] = bool(d.get("is_downloaded", 0))
        d["pinned"] = bool(d.get("pinned", 0))
        for dt_field in ("sent_at", "received_at", "internal_date", "created_at", "updated_at"):
            if d.get(dt_field):
                try:
                    d[dt_field] = datetime.fromisoformat(d[dt_field])
                except (ValueError, TypeError):
                    d[dt_field] = None
        return Email(**{k: v for k, v in d.items() if k in Email.__dataclass_fields__})

    # --------------------------------------------------------
    # email_ai_metadata
    # --------------------------------------------------------

    def update_email_ai_metadata(self, meta: EmailAIMetadata) -> None:
        with self.get_conn() as conn:
            conn.execute(
                """INSERT INTO email_ai_metadata (
                    email_id, keywords, summary_one_line, summary_brief,
                    summary_key_points, outline, categories, sentiment,
                    suggested_reply, is_spam, action_items, reply_stances,
                    urgency,
                    ai_status, processing_progress,
                    processing_stage, processed_at, processing_error,
                    embedding_vector, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(email_id) DO UPDATE SET
                    keywords = excluded.keywords,
                    summary_one_line = excluded.summary_one_line,
                    summary_brief = excluded.summary_brief,
                    summary_key_points = excluded.summary_key_points,
                    outline = excluded.outline,
                    categories = excluded.categories,
                    sentiment = excluded.sentiment,
                    suggested_reply = excluded.suggested_reply,
                    is_spam = excluded.is_spam,
                    action_items = excluded.action_items,
                    reply_stances = excluded.reply_stances,
                    urgency = excluded.urgency,
                    ai_status = excluded.ai_status,
                    processing_progress = excluded.processing_progress,
                    processing_stage = excluded.processing_stage,
                    processed_at = excluded.processed_at,
                    processing_error = excluded.processing_error,
                    embedding_vector = excluded.embedding_vector,
                    updated_at = excluded.updated_at""",
                (
                    meta.email_id,
                    json.dumps(meta.keywords) if meta.keywords else None,
                    meta.summary_one_line,
                    meta.summary_brief,
                    json.dumps(meta.summary_key_points) if meta.summary_key_points else None,
                    json.dumps(meta.outline) if meta.outline else None,
                    json.dumps(meta.categories, ensure_ascii=False) if meta.categories else None,
                    meta.sentiment,
                    meta.suggested_reply,
                    (1 if meta.is_spam else 0) if meta.is_spam is not None else None,
                    json.dumps(meta.action_items, ensure_ascii=False) if meta.action_items else None,
                    json.dumps(meta.reply_stances, ensure_ascii=False) if meta.reply_stances else None,
                    meta.urgency,
                    meta.ai_status,
                    meta.processing_progress,
                    meta.processing_stage,
                    meta.processed_at.isoformat() if meta.processed_at else None,
                    meta.processing_error,
                    meta.embedding_vector,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

    # --------------------------------------------------------
    # tasks
    # --------------------------------------------------------

    def create_task(self, task: Task) -> None:
        with self.get_conn() as conn:
            conn.execute(
                """INSERT INTO tasks (
                    id, source_email_id, source_task_index, source_type,
                    title, description, status, priority, is_flagged,
                    due_date, due_date_source, snoozed_until, completed_at,
                    category, tags, metadata,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    task.id,
                    task.source_email_id,
                    task.source_task_index,
                    task.source_type,
                    task.title,
                    task.description,
                    task.status,
                    task.priority,
                    int(task.is_flagged),
                    task.due_date.isoformat() if task.due_date else None,
                    task.due_date_source,
                    task.snoozed_until.isoformat() if task.snoozed_until else None,
                    task.completed_at.isoformat() if task.completed_at else None,
                    task.category,
                    json.dumps(task.tags) if task.tags else None,
                    json.dumps(task.metadata) if task.metadata else None,
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

    def get_tasks(
        self, status: Optional[str] = None, limit: int = 100
    ) -> List[Task]:
        with self.get_conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY due_date ASC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks ORDER BY due_date ASC LIMIT ?", (limit,)
                ).fetchall()
            return [self._row_to_task(r) for r in rows]

    def _row_to_task(self, row: sqlite3.Row) -> Task:
        d = dict(row)
        for json_field in ("tags", "metadata"):
            if d.get(json_field):
                try:
                    d[json_field] = json.loads(d[json_field])
                except (json.JSONDecodeError, TypeError):
                    d[json_field] = None
        d["is_flagged"] = bool(d.get("is_flagged", 0))
        for dt_field in ("due_date", "snoozed_until", "completed_at", "created_at", "updated_at"):
            if d.get(dt_field):
                try:
                    d[dt_field] = datetime.fromisoformat(d[dt_field])
                except (ValueError, TypeError):
                    d[dt_field] = None
        return Task(**{k: v for k, v in d.items() if k in Task.__dataclass_fields__})

    def search_emails(
        self,
        account_id: str,
        query: str = "",
        limit: int = 100,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        sender: Optional[str] = None,
        read_status: Optional[str] = None,
        is_flagged: Optional[bool] = None,
        folder: Optional[str] = None,
    ) -> List[Email]:
        """FTS5 全文搜索 + 高级筛选（日期范围 / 发件人 / 已读状态 / 标记）。"""
        has_query = bool(query.strip())
        has_filter = any([
            date_from, date_to, sender,
            read_status, is_flagged is not None, folder,
        ])
        if not has_query and not has_filter:
            return []

        # ── 构建通用 WHERE 子句（全部参数化，防注入）──
        f_clauses: list = ["e.account_id = ?"]
        f_params: list = [account_id]
        if date_from:
            f_clauses.append("e.received_at >= ?")
            f_params.append(date_from.isoformat())
        if date_to:
            f_clauses.append("e.received_at <= ?")
            f_params.append(date_to.isoformat())
        if sender:
            f_clauses.append("e.from_address LIKE ?")
            f_params.append(f"%{sender}%")
        if read_status:
            f_clauses.append("e.read_status = ?")
            f_params.append(read_status)
        if is_flagged is True:
            f_clauses.append("e.flag_status = 'flagged'")
        elif is_flagged is False:
            f_clauses.append("e.flag_status != 'flagged'")
        if folder:
            f_clauses.append("e.folder = ?")
            f_params.append(folder)
        where = " AND ".join(f_clauses)

        with self.get_conn() as conn:
            if not has_query:
                # 纯筛选模式（无关键词）
                rows = conn.execute(
                    f"SELECT e.* FROM emails e WHERE {where}"
                    " ORDER BY e.pinned DESC, e.received_at DESC LIMIT ?",
                    f_params + [limit],
                ).fetchall()
                result = []
                for r in rows:
                    try:
                        result.append(self._row_to_email(r))
                    except Exception:
                        continue
                return result

            # FTS + 筛选模式
            fts_q = _build_fts_query(query)
            try:
                rows_fts = conn.execute(
                    f"""SELECT e.* FROM emails e
                       INNER JOIN emails_fts ON emails_fts.rowid = e.rowid
                       WHERE {where} AND emails_fts MATCH ?
                       ORDER BY e.pinned DESC, emails_fts.rank, e.received_at DESC
                       LIMIT ?""",
                    f_params + [fts_q, limit * 2],
                ).fetchall()
            except Exception:
                rows_fts = []
            like = f"%{query}%"
            rows_ai = conn.execute(
                f"""SELECT e.* FROM emails e
                   JOIN email_ai_metadata m ON e.id = m.email_id
                   WHERE {where}
                     AND (m.keywords LIKE ? OR m.summary_one_line LIKE ?)
                   ORDER BY e.received_at DESC LIMIT ?""",
                f_params + [like, like, limit],
            ).fetchall()

        seen: set = set()
        result: List[Email] = []
        for row in list(rows_fts) + list(rows_ai):
            try:
                email = self._row_to_email(row)
            except Exception:
                continue
            if email.id in seen:
                continue
            seen.add(email.id)
            result.append(email)
            if len(result) >= limit:
                break
        return result

    def update_task_status(self, task_id: str, status: str) -> None:
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE tasks SET status=?, updated_at=? WHERE id=?",
                (status, datetime.utcnow().isoformat(), task_id),
            )
            conn.commit()

    def get_task(self, task_id: str) -> Optional[Task]:
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE id=?", (task_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            return self._row_to_task(row)
        except Exception:
            return None

    def update_task(
        self,
        task_id: str,
        title: str,
        priority: str,
        due_date: Optional[datetime],
        description: Optional[str],
        category: Optional[str],
    ) -> None:
        with self.get_conn() as conn:
            conn.execute(
                """UPDATE tasks SET title=?, priority=?, due_date=?,
                   description=?, category=?, due_date_source='user_set',
                   updated_at=? WHERE id=?""",
                (
                    title,
                    priority,
                    due_date.isoformat() if due_date else None,
                    description or None,
                    category or None,
                    datetime.utcnow().isoformat(),
                    task_id,
                ),
            )
            conn.commit()

    def get_tasks_for_todo(self) -> List[Task]:
        with self.get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM tasks
                   WHERE status NOT IN ('archived','rejected','cancelled')
                   ORDER BY due_date ASC, created_at DESC"""
            ).fetchall()
        result = []
        for r in rows:
            try:
                result.append(self._row_to_task(r))
            except Exception:
                pass
        return result

    def delete_all_tasks(self) -> int:
        """删除全部任务，返回删除条数。"""
        with self.get_conn() as conn:
            cur = conn.execute("DELETE FROM tasks")
            conn.commit()
            return cur.rowcount

    # --------------------------------------------------------
    # 账户辅助方法（Phase 1 新增）
    # --------------------------------------------------------

    def get_all_accounts(self) -> List["Account"]:
        """返回所有已启用的账户列表。"""
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM accounts WHERE is_enabled = 1 ORDER BY created_at ASC"
            ).fetchall()
            return [self._row_to_account(r) for r in rows]

    def update_account_sync_cursor(self, account_id: str, cursor_json: str) -> None:
        """
        更新账户的 sync_cursor 字段。
        cursor_json 格式：'{"INBOX": "1234", "垃圾邮件": "56"}'
        """
        with self.get_conn() as conn:
            conn.execute(
                """UPDATE accounts SET sync_cursor = ?, last_sync_at = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    cursor_json,
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                    account_id,
                ),
            )
            conn.commit()

    def update_account_credentials(self, account_id: str, encrypted: bytes) -> None:
        """更新账户加密凭据（OAuth token 刷新后调用）。"""
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE accounts SET credentials_encrypted = ?, updated_at = ? WHERE id = ?",
                (encrypted, datetime.utcnow().isoformat(), account_id),
            )
            conn.commit()

    def update_account_status(
        self,
        account_id: str,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        """更新账户同步状态（active/error/paused）及错误信息。"""
        with self.get_conn() as conn:
            conn.execute(
                """UPDATE accounts SET status = ?, error_message = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    status,
                    error_message,
                    datetime.utcnow().isoformat(),
                    account_id,
                ),
            )
            conn.commit()

    def save_attachment(
        self,
        email_id: str,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_path: str,
    ) -> None:
        """将附件元数据写入 attachments 表。"""
        with self.get_conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO attachments
                   (id, email_id, filename, content_type, size_bytes, storage_path, is_downloaded)
                   VALUES (?,?,?,?,?,?,1)""",
                (str(uuid.uuid4()), email_id, filename, content_type, size_bytes, storage_path),
            )
            conn.commit()

    def get_attachments_by_email(self, email_id: str) -> list:
        """返回邮件的附件列表，每项为 dict {filename, content_type, size_bytes, storage_path}。"""
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT filename, content_type, size_bytes, storage_path FROM attachments WHERE email_id = ?",
                (email_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_email_read(self, email_id: str, read: bool = True) -> None:
        """将邮件标记为已读（read）或未读（unread）。"""
        status = "read" if read else "unread"
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE emails SET read_status = ?, updated_at = ? WHERE id = ?",
                (status, datetime.utcnow().isoformat(), email_id),
            )
            conn.commit()

    def count_emails(self, account_id: Optional[str] = None) -> int:
        """返回本地邮件总数；传入 account_id 则只统计该账户。"""
        with self.get_conn() as conn:
            if account_id:
                row = conn.execute(
                    "SELECT COUNT(*) FROM emails WHERE account_id = ?", (account_id,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM emails").fetchone()
            return row[0] if row else 0

    def delete_all_emails(self, account_id: Optional[str] = None) -> int:
        """
        删除本地所有邮件（含级联的 ai_metadata、attachments 记录），
        同时重置关联账户的 sync_cursor，使下次同步从头拉取。
        返回删除的邮件条数。
        """
        with self.get_conn() as conn:
            if account_id:
                count = conn.execute(
                    "SELECT COUNT(*) FROM emails WHERE account_id = ?", (account_id,)
                ).fetchone()[0]
                conn.execute("DELETE FROM emails WHERE account_id = ?", (account_id,))
                conn.execute(
                    "UPDATE accounts SET sync_cursor = NULL, updated_at = ? WHERE id = ?",
                    (datetime.utcnow().isoformat(), account_id),
                )
            else:
                count = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
                conn.execute("DELETE FROM emails")
                conn.execute(
                    "UPDATE accounts SET sync_cursor = NULL, updated_at = ?",
                    (datetime.utcnow().isoformat(),),
                )
            conn.commit()
        return count

    def update_email_flag(self, email_id: str, flagged: bool) -> None:
        """设置/取消旗标（flag_status: 'flagged' / 'none'）。"""
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE emails SET flag_status = ?, updated_at = ? WHERE id = ?",
                ("flagged" if flagged else "none", datetime.utcnow().isoformat(), email_id),
            )
            conn.commit()

    def delete_email(self, email_id: str) -> None:
        """删除单封邮件及其关联的 AI 元数据和附件记录。"""
        with self.get_conn() as conn:
            conn.execute("DELETE FROM email_ai_metadata WHERE email_id = ?", (email_id,))
            conn.execute("DELETE FROM attachments WHERE email_id = ?", (email_id,))
            conn.execute("DELETE FROM emails WHERE id = ?", (email_id,))
            conn.commit()

    def update_email_folder(self, email_id: str, folder: str) -> None:
        """将邮件移动到指定文件夹。"""
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE emails SET folder = ?, updated_at = ? WHERE id = ?",
                (folder, datetime.utcnow().isoformat(), email_id),
            )
            conn.commit()

    def update_email_pinned(self, email_id: str, pinned: bool) -> None:
        """置顶或取消置顶邮件。"""
        with self.get_conn() as conn:
            conn.execute(
                "UPDATE emails SET pinned = ?, updated_at = ? WHERE id = ?",
                (1 if pinned else 0, datetime.utcnow().isoformat(), email_id),
            )
            conn.commit()

    # --------------------------------------------------------
    # AI 元数据辅助方法（Phase 2）
    # --------------------------------------------------------

    def get_email_ai_metadata(self, email_id: str) -> Optional["EmailAIMetadata"]:
        """返回单封邮件的 AI 元数据，不存在时返回 None。"""
        from clawmail.domain.models.email import EmailAIMetadata
        with self.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM email_ai_metadata WHERE email_id = ?", (email_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        for json_field in ("keywords", "summary_key_points", "outline",
                          "categories", "action_items", "reply_stances"):
            if d.get(json_field):
                try:
                    d[json_field] = json.loads(d[json_field])
                except (json.JSONDecodeError, TypeError):
                    d[json_field] = None
        for dt_field in ("processed_at", "updated_at"):
            if d.get(dt_field):
                try:
                    d[dt_field] = datetime.fromisoformat(d[dt_field])
                except (ValueError, TypeError):
                    d[dt_field] = None
        return EmailAIMetadata(
            **{k: v for k, v in d.items() if k in EmailAIMetadata.__dataclass_fields__}
        )

    def get_unprocessed_email_ids(
        self, account_id: str, limit: int = 200
    ) -> List[str]:
        """
        返回尚未 AI 处理（无记录或 ai_status in ('unprocessed','failed')）的邮件 ID。
        跳过草稿箱、回收站、垃圾邮件。
        """
        with self.get_conn() as conn:
            rows = conn.execute(
                """SELECT e.id FROM emails e
                   LEFT JOIN email_ai_metadata m ON e.id = m.email_id
                   WHERE e.account_id = ?
                     AND e.folder NOT IN ('草稿箱', '已删除', '已发送')
                     AND (m.email_id IS NULL
                          OR m.ai_status IN ('unprocessed', 'failed'))
                   ORDER BY e.received_at DESC
                   LIMIT ?""",
                (account_id, limit),
            ).fetchall()
        return [r[0] for r in rows]

    def get_emails_by_category(
        self, account_id: str, category: str, limit: int = 100
    ) -> List["Email"]:
        """
        按 AI 分类标签筛选邮件。
        使用 Python 端 JSON 解析（而非 SQL LIKE），正确处理中文
        分类被 json.dumps 转义为 \\uXXXX 的情况。
        category 例：'urgent'、'项目:Q4发布'
        """
        with self.get_conn() as conn:
            rows = conn.execute(
                """SELECT e.*, m.categories AS _cats
                   FROM emails e
                   JOIN email_ai_metadata m ON e.id = m.email_id
                   WHERE e.account_id = ?
                     AND m.categories IS NOT NULL
                     AND e.folder != '垃圾邮件'
                   ORDER BY e.pinned DESC, e.received_at DESC""",
                (account_id,),
            ).fetchall()

        result = []
        for row in rows:
            try:
                cats = json.loads(row["_cats"])
            except (json.JSONDecodeError, TypeError):
                cats = []
            if category in cats:
                result.append(self._row_to_email(row))
                if len(result) >= limit:
                    break
        return result

    def get_all_categories(self, account_id: str) -> List[str]:
        """
        返回当前账户所有邮件 AI 分类标签的去重列表（含动态项目标签）。
        """
        with self.get_conn() as conn:
            rows = conn.execute(
                """SELECT m.categories FROM email_ai_metadata m
                   JOIN emails e ON e.id = m.email_id
                   WHERE e.account_id = ?
                     AND m.categories IS NOT NULL
                     AND m.categories != '[]'
                     AND m.ai_status = 'processed'
                     AND e.folder != '垃圾邮件'""",
                (account_id,),
            ).fetchall()

        category_set: set = set()
        for (cats_json,) in rows:
            try:
                cats = json.loads(cats_json)
                if isinstance(cats, list):
                    category_set.update(cats)
            except (json.JSONDecodeError, TypeError):
                pass
        return sorted(category_set)

    def get_emails_by_urgency(
        self, account_id: str, urgency: str, limit: int = 100
    ) -> List["Email"]:
        """按 AI 紧急度（high/medium/low）筛选邮件。"""
        with self.get_conn() as conn:
            rows = conn.execute(
                """SELECT e.* FROM emails e
                   JOIN email_ai_metadata m ON e.id = m.email_id
                   WHERE e.account_id = ? AND m.urgency = ?
                     AND e.folder != '垃圾邮件'
                   ORDER BY e.pinned DESC, e.received_at DESC
                   LIMIT ?""",
                (account_id, urgency, limit),
            ).fetchall()
        result = []
        for row in rows:
            try:
                result.append(self._row_to_email(row))
            except Exception:
                pass
        return result

    def get_urgency_counts(self, account_id: str) -> Dict[str, int]:
        """返回各紧急度级别的邮件数量，格式：{'high': N, 'medium': N, 'low': N}。"""
        with self.get_conn() as conn:
            rows = conn.execute(
                """SELECT m.urgency, COUNT(*) FROM emails e
                   JOIN email_ai_metadata m ON e.id = m.email_id
                   WHERE e.account_id = ?
                     AND m.urgency IS NOT NULL
                     AND e.folder != '垃圾邮件'
                   GROUP BY m.urgency""",
                (account_id,),
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def update_draft(self, draft_id: str, to_addresses, cc_addresses,
                     subject: str, body_text: str, body_html) -> None:
        """更新草稿箱中已有草稿的可编辑字段。"""
        new_hash = hashlib.sha256((subject + (body_text or "")).encode()).hexdigest()
        with self.get_conn() as conn:
            conn.execute(
                """UPDATE emails
                   SET to_addresses = ?, cc_addresses = ?, subject = ?,
                       body_text = ?, body_html = ?, hash = ?,
                       updated_at = CURRENT_TIMESTAMP
                   WHERE id = ? AND folder = '草稿箱'""",
                (
                    json.dumps(to_addresses) if to_addresses else None,
                    json.dumps(cc_addresses) if cc_addresses else None,
                    subject,
                    body_text,
                    body_html,
                    new_hash,
                    draft_id,
                ),
            )
            conn.commit()
