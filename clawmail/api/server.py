"""
ClawMail 本地 HTTP REST API
监听 127.0.0.1:9999，供外部 AI 助手远程调用。
"""
import asyncio
import uuid
from datetime import datetime
from typing import Optional, List

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── 全局引用（main.py 启动后注入）──
_window = None   # ClawMailApp
_db     = None   # ClawDB


def init(window, db):
    global _window, _db
    _window = window
    _db = db


def _check_ready():
    if _window is None or _db is None:
        raise HTTPException(status_code=503, detail="App not ready")


# ── FastAPI 实例 ──
app = FastAPI(title="ClawMail API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic 请求体模型 ──

class ComposeRequest(BaseModel):
    to: Optional[str] = None
    cc: Optional[List[str]] = None
    subject: Optional[str] = None
    body: Optional[str] = None
    draft: bool = False
    attachments: Optional[List[str]] = None   # 附件绝对路径列表


class ReplyRequest(BaseModel):
    email_id: str                    # 原邮件ID（必填）
    reply_all: bool = False          # 是否回复所有人，默认 false
    initial_body: Optional[str] = None   # 预填充的回复内容（可选）


class SendReplyRequest(BaseModel):
    email_id: str                          # 原邮件ID（必填）
    reply_body: str                        # 回复正文（必填）
    reply_all: bool = False                # 是否回复所有人，默认 false
    subject_override: Optional[str] = None  # 可选，覆盖自动生成的主题


class ConfirmDialogOption(BaseModel):
    id: str      # 选项标识符，返回给调用方
    label: str   # 按钮显示文字


class ConfirmDialogRequest(BaseModel):
    title: str
    message: str
    options: List[ConfirmDialogOption]          # 2-4 个选项
    default_option_id: Optional[str] = None     # 保留字段（兼容规范）
    timeout_seconds: int = 60


class SearchRequest(BaseModel):
    query: str
    folder: Optional[str] = None
    limit: int = 50


class MarkRequest(BaseModel):
    email_id: str
    read: Optional[bool] = None
    flag: Optional[bool] = None
    pin: Optional[bool] = None


# ── 端点 ──

@app.post("/compose")
async def compose(req: ComposeRequest):
    """打开撰写窗口，或直接保存草稿（draft=true）。"""
    _check_ready()
    accs = _db.get_all_accounts()
    if not accs:
        raise HTTPException(status_code=400, detail="No account configured")
    account = accs[0]
    cc_str = ", ".join(req.cc) if req.cc else ""

    # 校验附件（仅 UI 模式；draft 模式忽略附件）
    import os as _os
    _MAX_ATTACH_SIZE = 25 * 1024 * 1024  # 25 MB
    validated_attachments: list = []
    for p in (req.attachments or []):
        if not _os.path.isfile(p):
            raise HTTPException(status_code=400, detail=f"Attachment not found: {p}")
        if _os.path.getsize(p) > _MAX_ATTACH_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Attachment exceeds 25 MB limit: {_os.path.basename(p)}",
            )
        validated_attachments.append(p)

    if req.draft:
        # 直接写库，不打开 UI
        from clawmail.domain.models.email import Email
        email = Email(
            id=str(uuid.uuid4()),
            account_id=account.id,
            subject=req.subject or "(无主题)",
            from_address={
                "name": account.display_name or "",
                "email": account.email_address,
            },
            to_addresses=[
                {"name": t.strip(), "email": t.strip()}
                for t in (req.to or "").split(",") if t.strip()
            ] or None,
            body_text=req.body or "",
            folder="草稿箱",
            imap_folder="草稿箱",
            sync_status="completed",
            is_downloaded=True,
            received_at=datetime.utcnow(),
        )
        _db.save_email(email)
        return {"success": True, "draft_id": email.id}
    else:
        # 延迟打开 UI，先返回 HTTP 响应
        from PyQt6.QtCore import QTimer
        from clawmail.ui.components.compose_dialog import ComposeDialog

        def _open():
            dlg = ComposeDialog(
                _db, getattr(_window, "_cred", None), account,
                initial_to=req.to or "",
                initial_cc=cc_str,
                initial_subject=req.subject or "",
                initial_body=req.body or "",
                initial_attachments=validated_attachments or None,
                parent=_window,
            )
            dlg.show()

        QTimer.singleShot(0, _open)
        return {
            "success": True,
            "window_id": "compose",
            "attachments_loaded": len(validated_attachments),
        }


@app.post("/reply")
async def reply(req: ReplyRequest):
    """打开回复窗口，回复指定邮件。
    
    - 自动填充收件人、主题（Re:）、引用原文
    - 如有 AI 元数据，显示 AI 辅助拟稿面板
    - 支持预填充回复内容
    """
    _check_ready()
    
    # 获取原邮件
    source_email = _db.get_email(req.email_id)
    if not source_email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # 获取账户
    accs = _db.get_all_accounts()
    if not accs:
        raise HTTPException(status_code=400, detail="No account configured")
    account = accs[0]
    
    # 获取 AI 元数据
    ai_metadata = _db.get_email_ai_metadata(req.email_id)
    
    # 确定收件人
    from_addr = source_email.from_address or {}
    from_email = from_addr.get("email", "")
    from_name = from_addr.get("name", "")
    
    # 构建收件人列表
    to_addresses = [{"name": from_name, "email": from_email}]
    cc_addresses = []
    
    if req.reply_all:
        # 添加原邮件的收件人到抄送（排除自己）
        if source_email.to_addresses:
            for addr in source_email.to_addresses:
                email = addr.get("email", "")
                if email and email.lower() != account.email_address.lower():
                    cc_addresses.append(addr)
        # 添加原邮件的抄送人
        if source_email.cc_addresses:
            for addr in source_email.cc_addresses:
                email = addr.get("email", "")
                if email and email.lower() != account.email_address.lower():
                    cc_addresses.append(addr)
    
    # 构建主题（添加 Re: 前缀）
    original_subject = source_email.subject or ""
    if not original_subject.lower().startswith("re:"):
        subject = f"Re: {original_subject}"
    else:
        subject = original_subject
    
    # 构建引用 HTML
    quote_html = _build_reply_quote(source_email)
    
    # 预填充的回复内容
    initial_reply_html = req.initial_body or ""
    if initial_reply_html:
        initial_reply_html = initial_reply_html.replace("\n", "<br>")
    
    # 延迟打开 UI
    from PyQt6.QtCore import QTimer
    from clawmail.ui.components.compose_dialog import ComposeDialog
    
    def _open():
        # 用 _ai_bridge 动态构建 AIProcessor（与 app.py._on_reply 一致）
        ai_processor = None
        if _window and getattr(_window, "_ai_bridge", None):
            from clawmail.infrastructure.ai.ai_processor import AIProcessor
            ai_processor = AIProcessor(_window._ai_bridge)
        
        # 格式化收件人和抄送
        to_str = ", ".join([a.get("email", "") for a in to_addresses])
        cc_str = ", ".join([a.get("email", "") for a in cc_addresses]) if cc_addresses else ""
        
        dlg = ComposeDialog(
            _db, getattr(_window, "_cred", None), account,
            initial_to=to_str,
            initial_cc=cc_str,
            initial_subject=subject,
            initial_body="",  # 使用 initial_reply_html 替代
            initial_html_quote=quote_html,
            initial_reply_html=initial_reply_html,
            source_email=source_email,
            ai_metadata=ai_metadata,
            ai_processor=ai_processor,
            parent=_window,
        )
        dlg.show()
    
    QTimer.singleShot(0, _open)
    return {"success": True, "window_id": "reply"}


def _build_reply_quote(email) -> str:
    """构建回复引用 HTML。"""
    from_info = email.from_address or {}
    from_str = from_info.get("name", "") or from_info.get("email", "未知发件人")
    
    date_str = ""
    if email.received_at:
        date_str = email.received_at.strftime("%Y-%m-%d %H:%M")
    
    subject_str = email.subject or ""
    
    # 构建引用头部
    header = f"在 {date_str}，{from_str} 写道："
    
    # 获取正文内容
    body = email.body_html or email.body_text or ""
    
    # 如果是纯文本，转换为 HTML
    if not email.body_html and body:
        body = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        body = body.replace("\n", "<br>")
    
    # 构建引用块
    quote = f"""
    <div style="margin:12px 0;border-left:3px solid #ccc;padding-left:12px;color:#666;">
        <div style="margin-bottom:8px;">{header}</div>
        <div>{body}</div>
    </div>
    """
    return quote


@app.post("/search")
async def search(req: SearchRequest):
    """搜索邮件（FTS5 全文 + AI 摘要 LIKE）。"""
    _check_ready()
    accs = _db.get_all_accounts()
    if not accs:
        return {"emails": []}

    emails = _db.search_emails(accs[0].id, req.query, limit=req.limit)

    def _ser(e):
        fi = e.from_address or {}
        return {
            "id": e.id,
            "subject": e.subject,
            "from": fi.get("email", ""),
            "from_name": fi.get("name", ""),
            "date": e.received_at.isoformat() if e.received_at else None,
            "folder": e.folder,
            "read": e.read_status != "unread",
            "snippet": (e.body_text or "")[:200],
        }

    return {"emails": [_ser(e) for e in emails]}


@app.get("/stats")
async def stats():
    """邮箱统计：总数、未读数、各文件夹数量。"""
    _check_ready()
    accs = _db.get_all_accounts()
    if not accs:
        return {"total": 0, "unread": 0, "folders": {}}
    aid = accs[0].id

    with _db.get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE account_id=?", (aid,)
        ).fetchone()[0]
        unread = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE account_id=? AND read_status='unread'",
            (aid,)
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT folder, COUNT(*) FROM emails WHERE account_id=? GROUP BY folder",
            (aid,)
        ).fetchall()

    return {
        "total": total,
        "unread": unread,
        "folders": {r[0]: r[1] for r in rows},
    }


@app.post("/mark")
async def mark(req: MarkRequest):
    """标记邮件（已读/旗标/置顶）。"""
    _check_ready()
    if not _db.get_email(req.email_id):
        raise HTTPException(status_code=404, detail="Email not found")

    if req.read is not None:
        _db.mark_email_read(req.email_id, read=req.read)
    if req.flag is not None:
        _db.update_email_flag(req.email_id, req.flag)
    if req.pin is not None:
        _db.update_email_pinned(req.email_id, req.pin)

    # 通知 UI 刷新列表（延迟到 Qt 事件队列）
    if _window:
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: _window._email_list.viewport().update())

    return {"success": True}


# ── 任务管理 ──

VALID_STATUSES = {
    "pending", "in_progress", "snoozed", "completed",
    "cancelled", "rejected", "archived",
}
VALID_PRIORITIES = {"high", "medium", "low", "none"}


class TaskCreateRequest(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    due_date: Optional[str] = None        # ISO 日期字符串，如 "2026-03-01"
    source_email_id: Optional[str] = None
    status: str = "pending"
    category: Optional[str] = None        # 工作/生活/学习/个人/其他


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None        # 空字符串 "" 表示清除
    description: Optional[str] = None


class SnoozeRequest(BaseModel):
    until: str                            # ISO 日期字符串


def _task_to_dict(t) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "description": t.description,
        "status": t.status,
        "priority": t.priority,
        "is_flagged": t.is_flagged,
        "due_date": t.due_date.date().isoformat() if t.due_date else None,
        "snoozed_until": t.snoozed_until.date().isoformat() if t.snoozed_until else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "source_email_id": t.source_email_id,
        "source_type": t.source_type,
        "category": t.category,
        "tags": t.tags,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


@app.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 50,
):
    """获取任务列表，支持 status / priority / limit 过滤。"""
    _check_ready()
    if status and status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    if priority and priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {priority}")

    if priority:
        with _db.get_conn() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE status=? AND priority=?"
                    " ORDER BY due_date ASC LIMIT ?",
                    (status, priority, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE priority=?"
                    " ORDER BY due_date ASC LIMIT ?",
                    (priority, limit),
                ).fetchall()
        tasks = [_db._row_to_task(r) for r in rows]
    else:
        tasks = _db.get_tasks(status=status, limit=limit)

    return {"tasks": [_task_to_dict(t) for t in tasks]}


def _ser_email(e) -> dict:
    """将 Email 对象序列化为 API 响应字典（含完整正文）。"""
    fi = e.from_address or {}
    to_list = e.to_addresses or []
    return {
        "id": e.id,
        "subject": e.subject,
        "from": fi.get("email", ""),
        "from_name": fi.get("name", ""),
        "to": [t.get("email", "") for t in to_list if isinstance(t, dict)],
        "date": e.received_at.isoformat() if e.received_at else None,
        "folder": e.folder,
        "read": e.read_status != "unread",
        "is_flagged": bool(e.is_flagged),
        "body": e.body_text or "",
        "snippet": (e.body_text or "")[:200],
    }


@app.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取单个任务详情。"""
    _check_ready()
    task = _db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_dict(task)


@app.get("/tasks/{task_id}/email")
async def get_task_source_email(task_id: str):
    """返回任务关联的源邮件详情。若无关联邮件则返回 404。"""
    _check_ready()
    task = _db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.source_email_id:
        raise HTTPException(status_code=404, detail="No source email for this task")
    email = _db.get_email(task.source_email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Source email not found")
    return {"email": _ser_email(email)}


@app.post("/tasks", status_code=201)
async def create_task(req: TaskCreateRequest):
    """创建新任务。"""
    _check_ready()
    if req.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {req.status}")
    if req.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {req.priority}")

    due_date = None
    if req.due_date:
        try:
            due_date = datetime.fromisoformat(req.due_date)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid due_date format, use ISO 8601 (e.g. 2026-03-01)",
            )

    from clawmail.domain.models.task import Task as TaskModel
    task = TaskModel(
        id=str(uuid.uuid4()),
        title=req.title,
        description=req.description,
        status=req.status,
        priority=req.priority,
        due_date=due_date,
        source_email_id=req.source_email_id,
        source_type="manual",
        category=req.category,
    )
    _db.create_task(task)
    return {"success": True, "task_id": task.id}


@app.put("/tasks/{task_id}")
async def update_task(task_id: str, req: TaskUpdateRequest):
    """更新任务字段（仅传入需要修改的字段）。"""
    _check_ready()
    task = _db.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if req.status is not None and req.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {req.status}")
    if req.priority is not None and req.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=400, detail=f"Invalid priority: {req.priority}")

    new_title       = req.title       if req.title       is not None else task.title
    new_priority    = req.priority    if req.priority    is not None else task.priority
    new_description = req.description if req.description is not None else task.description
    new_due_date    = task.due_date

    if req.due_date is not None:
        if req.due_date == "":
            new_due_date = None
        else:
            try:
                new_due_date = datetime.fromisoformat(req.due_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid due_date format")

    _db.update_task(task_id, new_title, new_priority, new_due_date,
                    new_description, task.category)
    if req.status is not None:
        _db.update_task_status(task_id, req.status)
    return {"success": True}


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务。"""
    _check_ready()
    if not _db.get_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    with _db.get_conn() as conn:
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.commit()
    return {"success": True}


@app.post("/tasks/{task_id}/complete")
async def complete_task(task_id: str):
    """快捷标记任务完成。"""
    _check_ready()
    if not _db.get_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    _db.update_task_status(task_id, "completed")
    return {"success": True}


@app.post("/tasks/{task_id}/snooze")
async def snooze_task(task_id: str, req: SnoozeRequest):
    """推迟任务到指定日期。"""
    _check_ready()
    if not _db.get_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        snooze_dt = datetime.fromisoformat(req.until)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format for 'until', use ISO 8601 (e.g. 2026-03-15)",
        )
    with _db.get_conn() as conn:
        conn.execute(
            "UPDATE tasks SET status='snoozed', snoozed_until=?, updated_at=? WHERE id=?",
            (snooze_dt.isoformat(), datetime.utcnow().isoformat(), task_id),
        )
        conn.commit()
    return {"success": True}


@app.post("/send-reply")
async def send_reply(req: SendReplyRequest):
    """直接发送回复邮件（不打开 UI），发送成功后更新原邮件 reply_status。"""
    _check_ready()

    # 获取原邮件
    source_email = _db.get_email(req.email_id)
    if not source_email:
        raise HTTPException(status_code=404, detail="Email not found")

    # 获取账户
    accs = _db.get_all_accounts()
    if not accs:
        raise HTTPException(status_code=400, detail="No account configured")
    account = accs[0]

    # 解密密码
    cred = getattr(_window, "_cred", None)
    if not cred:
        raise HTTPException(status_code=503, detail="Credential manager not available")
    try:
        password = cred.decrypt_credentials(account.credentials_encrypted)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Failed to decrypt credentials: {e}")

    # 构建收件人
    from_addr = source_email.from_address or {}
    to_addresses = [from_addr.get("email", "")]
    cc_addresses = []

    if req.reply_all:
        my_email = account.email_address.lower()
        if source_email.to_addresses:
            for addr in source_email.to_addresses:
                e = addr.get("email", "")
                if e and e.lower() != my_email:
                    cc_addresses.append(e)
        if source_email.cc_addresses:
            for addr in source_email.cc_addresses:
                e = addr.get("email", "")
                if e and e.lower() != my_email:
                    cc_addresses.append(e)

    # 构建主题
    if req.subject_override:
        subject = req.subject_override
    else:
        original_subject = source_email.subject or ""
        subject = original_subject if original_subject.lower().startswith("re:") \
                  else f"Re: {original_subject}"

    # 构建纯文本正文（含引用）
    from_name = from_addr.get("name", "") or from_addr.get("email", "")
    date_str = source_email.received_at.strftime("%Y-%m-%d %H:%M") \
               if source_email.received_at else ""
    original_body = source_email.body_text or ""
    quoted_lines = "\n".join(f"> {line}" for line in original_body.splitlines())
    plain_body = (
        f"{req.reply_body}\n\n"
        f"--- 原邮件 ---\n"
        f"发件人: {from_name}\n"
        f"日期: {date_str}\n"
        f"主题: {source_email.subject or ''}\n\n"
        f"{quoted_lines}"
    )

    # 构建 HTML 正文
    reply_html = req.reply_body.replace("\n", "<br>")
    original_html = source_email.body_html or (
        original_body.replace("&", "&amp;").replace("<", "&lt;")
                     .replace(">", "&gt;").replace("\n", "<br>")
    )
    html_body = (
        f"<div>{reply_html}</div>"
        f"<br>"
        f'<div style="margin:8px 0;border-left:3px solid #ccc;'
        f'padding-left:12px;color:#666;">'
        f"<div>在 {date_str}，{from_name} 写道：</div>"
        f"<div>{original_html}</div>"
        f"</div>"
    )

    # 发送
    from clawmail.infrastructure.email_clients.smtp_client import ClawSMTPClient, SMTPSendError
    smtp = ClawSMTPClient()
    try:
        await smtp.send_email(
            account=account,
            password=password,
            to_addresses=[a for a in to_addresses if a],
            subject=subject,
            body=plain_body,
            cc_addresses=cc_addresses or None,
            html_body=html_body,
        )
    except SMTPSendError as e:
        raise HTTPException(status_code=502, detail=f"SMTP send failed: {e}")

    # 更新原邮件 reply_status + 移除 pending_reply 分类
    try:
        with _db.get_conn() as conn:
            conn.execute(
                "UPDATE emails SET reply_status='replied', updated_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), req.email_id),
            )
            row = conn.execute(
                "SELECT categories FROM email_ai_metadata WHERE email_id=?",
                (req.email_id,),
            ).fetchone()
            if row and row[0]:
                import json as _json
                try:
                    cats = _json.loads(row[0])
                    if "pending_reply" in cats:
                        cats.remove("pending_reply")
                        conn.execute(
                            "UPDATE email_ai_metadata SET categories=? WHERE email_id=?",
                            (_json.dumps(cats, ensure_ascii=False), req.email_id),
                        )
                except Exception:
                    pass
            conn.commit()
    except Exception:
        pass  # 状态更新失败不影响发送结果

    # 通知 UI 刷新
    if _window:
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: _window._email_list.viewport().update())

    sent_at = datetime.utcnow().isoformat()
    return {"success": True, "sent_at": sent_at}


# ── UI 控制接口 ──

class ClickButtonRequest(BaseModel):
    button_id: str

class OpenEmailRequest(BaseModel):
    email_id: str
    window: str = "main"


# button_id → 调用 _window 上对应方法的映射
_UI_BUTTON_ACTIONS = {
    "refresh_tasks":  lambda w: w._refresh_todo_list(),
    "refresh_emails": lambda w: w.refresh_email_list(w._current_folder),
}


@app.post("/ui/refresh-tasks")
async def ui_refresh_tasks():
    """触发主窗口待办列表刷新。"""
    _check_ready()
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(0, _window._refresh_todo_list)
    return {"success": True}


@app.post("/ui/refresh-emails")
async def ui_refresh_emails():
    """触发主窗口邮件列表刷新（保持当前文件夹）。"""
    _check_ready()
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(0, lambda: _window.refresh_email_list(_window._current_folder))
    return {"success": True}


@app.post("/ui/open-email")
async def ui_open_email(req: OpenEmailRequest):
    """在主窗口中打开指定邮件的详情视图（自动切换文件夹并选中）。"""
    _check_ready()
    email = _db.get_email(req.email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(0, lambda: _window._jump_to_source_email(req.email_id))
    return {"success": True, "window": "email_detail"}


@app.post("/ui/focus-compose")
async def ui_focus_compose():
    """将已打开的撰写窗口置于前台；若无则返回 404。"""
    _check_ready()
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    found = False
    try:
        from clawmail.ui.components.compose_dialog import ComposeDialog
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, ComposeDialog) and widget.isVisible():
                found = True
                break
    except Exception:
        pass

    if not found:
        raise HTTPException(status_code=404, detail="No compose window is open")

    def _focus():
        try:
            from clawmail.ui.components.compose_dialog import ComposeDialog
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, ComposeDialog) and widget.isVisible():
                    widget.raise_()
                    widget.activateWindow()
                    break
        except Exception:
            pass

    QTimer.singleShot(0, _focus)
    return {"success": True}


@app.post("/ui/click-button")
async def ui_click_button(req: ClickButtonRequest):
    """通过 button_id 触发预设 UI 操作。支持的 button_id: refresh_tasks, refresh_emails。"""
    _check_ready()
    action = _UI_BUTTON_ACTIONS.get(req.button_id)
    if action is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown button_id '{req.button_id}'. "
                   f"Supported: {list(_UI_BUTTON_ACTIONS.keys())}",
        )
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(0, lambda: action(_window))
    return {"success": True}


@app.post("/ui/confirm-dialog")
async def ui_confirm_dialog(req: ConfirmDialogRequest):
    """弹出确认对话框，等待用户点击后返回 option_id；超时或关闭窗口返回 error。"""
    _check_ready()
    if not req.options:
        raise HTTPException(status_code=400, detail="options cannot be empty")

    loop = asyncio.get_event_loop()
    future: asyncio.Future = loop.create_future()
    _dlg_ref: list = [None]   # 用列表持有对话框引用，供超时时关闭

    def _build_and_show():
        from PyQt6.QtWidgets import (
            QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        )
        from PyQt6.QtCore import Qt

        dlg = QDialog(_window)
        dlg.setWindowTitle(req.title)
        dlg.setMinimumWidth(360)
        dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        _dlg_ref[0] = dlg

        vbox = QVBoxLayout(dlg)
        vbox.setContentsMargins(20, 16, 20, 16)
        vbox.setSpacing(12)

        msg_label = QLabel(req.message)
        msg_label.setTextFormat(Qt.TextFormat.PlainText)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet("font-size:13px;")
        vbox.addWidget(msg_label)

        from clawmail.ui.theme import get_theme as _get_theme
        _bt = _get_theme()
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_style = (
            f"QPushButton{{padding:5px 14px;border:1px solid {_bt.dialog_btn_border()};"
            f"border-radius:4px;background:{_bt.dialog_btn_bg()};font-size:12px;"
            f"color:palette(button-text);}}"
            f"QPushButton:hover{{background:{_bt.dialog_btn_hover()};}}"
        )

        def _make_handler(opt_id):
            def _handler():
                if not future.done():
                    future.set_result(opt_id)
                dlg.close()
            return _handler

        for opt in req.options:
            btn = QPushButton(opt.label)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(_make_handler(opt.id))
            btn_row.addWidget(btn)

        vbox.addLayout(btn_row)

        def _on_finished():
            if not future.done():
                future.set_result(None)

        dlg.finished.connect(_on_finished)
        dlg.show()

    from PyQt6.QtCore import QTimer
    QTimer.singleShot(0, _build_and_show)

    try:
        selected_id = await asyncio.wait_for(
            asyncio.shield(future), timeout=req.timeout_seconds
        )
    except asyncio.TimeoutError:
        if not future.done():
            future.set_result(None)
        dlg = _dlg_ref[0]
        if dlg:
            QTimer.singleShot(0, dlg.close)
        return {"success": False, "error": "timeout", "selected_option_id": None}

    if selected_id is None:
        return {"success": False, "error": "cancelled", "selected_option_id": None}

    return {
        "success": True,
        "selected_option_id": selected_id,
        "confirmed_at": datetime.utcnow().isoformat(),
    }


# ── 启动函数（供 main.py 调用）──

async def start_api_server(host: str = "127.0.0.1", port: int = 9999):
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()
