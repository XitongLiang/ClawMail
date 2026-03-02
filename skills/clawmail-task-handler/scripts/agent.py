"""
ProactiveAgent — OpenClaw 自主执行 agent

基于 JSON 指令模式的工具调用循环（不依赖原生 function calling）。
用户点击"AI 执行"后，agent 自主分析任务、调用工具、起草回复，
最终通过 confirm_and_send 让用户确认后发送。

仅依赖标准库（urllib），无第三方依赖。
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import urllib.request
import urllib.error

CLAWMAIL_API = "http://127.0.0.1:9999"
LLM_API = "http://127.0.0.1:18789/v1/chat/completions"
LLM_MODEL = "kimi-k2.5"

REPLY_SCRIPT = (Path.home() / ".openclaw" / "workspace" / "skills"
                / "clawmail-reply" / "scripts" / "generate_reply.py")

# ── 系统提示词（内含工具描述 + JSON 输出格式要求） ──

SYSTEM_PROMPT = """\
你是 ClawMail 的智能邮件助手。用户点击了一个待办行动项的"AI 执行"按钮，你需要自主完成这个任务。

## 可用工具

1. **get_email** — 获取邮件完整内容
   参数: {"email_id": "邮件ID"}

2. **get_ai_metadata** — 获取邮件的 AI 分析结果（摘要、分类、行动项等）
   参数: {"email_id": "邮件ID"}

3. **get_thread** — 获取邮件线程的历史对话
   参数: {"thread_id": "线程ID", "limit": 5}

4. **search_emails** — 全文搜索邮件
   参数: {"query": "搜索关键词", "limit": 5}

5. **get_memories** — 获取与发件人相关的用户偏好记忆
   参数: {"account_id": "账户ID", "sender_email": "发件人邮箱(可选)"}

6. **search_local_files** — 搜索用户本地文件（Documents/Desktop/Downloads）
   参数: {"keywords": ["关键词1", "关键词2"], "file_type": "pdf/docx/pptx/xlsx/any"}

7. **generate_reply** — AI 生成邮件回复草稿
   参数: {"email_id": "邮件ID", "stance": "回复立场/要点", "user_notes": "补充说明(可选)", "account_id": "账户ID(可选)"}

8. **confirm_and_send** — 【终结工具】弹出确认框让用户预览并发送
   参数: {"email_id": "邮件ID", "reply_body": "回复正文", "attachments": ["文件路径"](可选), "summary": "一句话说明(可选)"}

## 响应格式

每次回复你**只能**输出一个 JSON 对象，不要输出任何其他文本。格式：

调用工具：
```json
{"tool": "工具名", "args": {参数对象}}
```

## 工作流程
1. 理解邮件内容和行动项要求
2. 根据需要调用工具搜索信息（邮件历史、联系人记忆、本地文件）
3. **必须调用 generate_reply** 生成回复草稿（把行动项要点作为 stance 参数）
4. 拿到 generate_reply 返回的 reply_body 后，**调用 confirm_and_send**（把 reply_body 原样传入）

## 重要规则
- 每次只调用一个工具
- **回复正文必须通过 generate_reply 工具生成**，禁止你自己编写回复内容。把 generate_reply 返回的 reply_body 原样传给 confirm_and_send
- 你**必须**在最后调用 confirm_and_send，不能跳过用户确认
- 如果需要附件，先用 search_local_files 搜索，找到后传入 confirm_and_send 的 attachments
- 如果搜索不到信息/文件，在 confirm_and_send 的 summary 中说明
- 尽量高效，通常 2-4 步即可完成
- 不要输出工具调用以外的任何文本
"""


def _load_llm_token() -> str:
    try:
        cfg = json.loads((Path.home() / ".openclaw" / "openclaw.json").read_text("utf-8"))
        return cfg.get("gateway", {}).get("auth", {}).get("token", "")
    except Exception:
        return ""


def _extract_json(text: str) -> Optional[dict]:
    """从 LLM 响应文本中提取 JSON 对象。

    尝试以下策略（按优先级）：
    1. 整个文本就是 JSON
    2. ```json 代码块中的 JSON
    3. 文本中第一个 {...} 块
    """
    text = text.strip()

    # 策略 1：整个文本就是 JSON
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, ValueError):
        pass

    # 策略 2：```json 代码块
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(1).strip())
            if isinstance(obj, dict):
                return obj
        except (json.JSONDecodeError, ValueError):
            pass

    # 策略 3：第一个 {...} 块（支持嵌套）
    start = text.find('{')
    if start != -1:
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == '\\' and in_str:
                escape = True
                continue
            if ch == '"' and not escape:
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except (json.JSONDecodeError, ValueError):
                        pass
                    break

    return None


class ProactiveAgent:
    """OpenClaw 自主执行 agent — JSON 指令模式工具调用循环。"""

    MAX_TURNS = 10

    def __init__(self):
        self._llm_token = _load_llm_token()

    # ── 主入口 ──

    def run(self, task: dict, email: dict) -> dict:
        """执行 proactive 任务，返回 {success, action, message, ...}。"""
        metadata = task.get("metadata") or {}
        action_item = metadata.get("action_item", {})
        print(f"[TaskHandler] ═══ Agent 启动 ═══")
        print(f"[TaskHandler] 行动项: {action_item.get('text', task.get('title', ''))}")
        print(f"[TaskHandler] 类型: {metadata.get('action_type', '未知')}")
        print(f"[TaskHandler] 邮件: {email.get('subject', '')}")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self._build_task_prompt(task, email)},
        ]

        for turn in range(self.MAX_TURNS):
            print(f"[TaskHandler] ── Turn {turn + 1}/{self.MAX_TURNS} ──")
            print(f"[TaskHandler] 调用 LLM (messages={len(messages)})...")
            try:
                resp = self._call_llm(messages)
            except Exception as e:
                print(f"[TaskHandler] LLM 调用失败: {e}")
                return {"success": False, "error": f"LLM 调用失败: {e}"}

            choice = resp["choices"][0]
            msg = choice["message"]
            content = msg.get("content", "") or ""

            # 打印 LLM 原始输出（前几行）
            for line in content.strip().split("\n")[:5]:
                print(f"[TaskHandler] LLM: {line[:120]}")

            # 将 assistant 消息加入历史
            messages.append({"role": "assistant", "content": content})

            # 从文本中提取 JSON 工具调用
            action = _extract_json(content)
            if not action or "tool" not in action:
                # LLM 没有输出有效的工具调用 JSON
                print(f"[TaskHandler] ═══ Agent 结束（无工具调用） ═══")
                return {"success": True, "action": "completed", "message": content}

            tool_name = action["tool"]
            tool_args = action.get("args", {})

            # 打印工具调用详情
            args_summary = self._summarize_args(tool_name, tool_args)
            print(f"[TaskHandler] 调用工具: {tool_name}({args_summary})")

            # 分发执行
            result = self._dispatch(tool_name, tool_args, task, email)

            # 打印工具结果摘要
            result_summary = self._summarize_result(tool_name, result)
            print(f"[TaskHandler]    → 结果: {result_summary}")

            # confirm_and_send 是终结工具
            if tool_name == "confirm_and_send":
                act = result.get("action", "unknown")
                print(f"[TaskHandler] ═══ Agent 结束 (action={act}) ═══")
                return result

            # 将工具结果作为 user 消息反馈给 LLM
            result_str = json.dumps(result, ensure_ascii=False, default=str)
            if len(result_str) > 8000:
                result_str = result_str[:8000] + "...(截断)"
            messages.append({
                "role": "user",
                "content": f"工具 `{tool_name}` 返回结果:\n```json\n{result_str}\n```\n\n请继续执行下一步。记住只输出 JSON 工具调用。",
            })

        print(f"[TaskHandler] ═══ Agent 结束（达到最大轮次） ═══")
        return {"success": False, "error": "达到最大轮次限制"}

    @staticmethod
    def _summarize_args(tool_name: str, args: dict) -> str:
        """生成工具参数的简短摘要。"""
        if tool_name in ("get_email", "get_ai_metadata"):
            return args.get("email_id", "")[:12] + "..."
        elif tool_name == "get_thread":
            return f"thread={args.get('thread_id', '')[:12]}..."
        elif tool_name == "search_emails":
            return f"query='{args.get('query', '')}'"
        elif tool_name == "get_memories":
            sender = args.get("sender_email", "全局")
            return f"sender={sender}"
        elif tool_name == "search_local_files":
            kws = args.get("keywords", [])
            return f"keywords={kws}, type={args.get('file_type', 'any')}"
        elif tool_name == "generate_reply":
            return f"stance='{args.get('stance', '')[:40]}'"
        elif tool_name == "confirm_and_send":
            att = args.get("attachments", [])
            att_info = f", 附件={len(att)}个" if att else ""
            return f"回复{len(args.get('reply_body', ''))}字{att_info}"
        return str(list(args.keys()))

    @staticmethod
    def _summarize_result(tool_name: str, result: dict) -> str:
        """生成工具结果的简短摘要。"""
        if result.get("error"):
            return f"[ERR] {result['error'][:80]}"
        if tool_name == "search_local_files":
            files = result.get("files", [])
            if files:
                names = [os.path.basename(f) for f in files[:3]]
                return f"找到 {len(files)} 个文件: {', '.join(names)}"
            return "未找到匹配文件"
        elif tool_name == "generate_reply":
            body = result.get("reply_body", "")
            return f"生成回复 {len(body)} 字" if body else "生成为空"
        elif tool_name == "search_emails":
            results = result.get("results", [])
            return f"搜索到 {len(results)} 封邮件"
        elif tool_name == "get_memories":
            memories = result.get("memories", [])
            return f"获取 {len(memories)} 条记忆"
        elif tool_name in ("get_email", "get_ai_metadata"):
            return f"OK (subject={result.get('subject', result.get('summary', {}).get('one_line', ''))[:40]})"
        elif tool_name == "confirm_and_send":
            return f"用户选择: {result.get('action', 'unknown')}"
        return f"OK ({len(json.dumps(result, ensure_ascii=False))} bytes)"

    # ── LLM 调用（不传 tools 参数） ──

    def _call_llm(self, messages: list) -> dict:
        body = {
            "model": LLM_MODEL,
            "messages": messages,
            "temperature": 0.3,
        }
        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._llm_token:
            headers["Authorization"] = f"Bearer {self._llm_token}"

        req = urllib.request.Request(LLM_API, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ── 任务提示构建 ──

    def _build_task_prompt(self, task: dict, email: dict) -> str:
        metadata = task.get("metadata") or {}
        action_item = metadata.get("action_item", {})

        parts = [
            f"## 待办行动项",
            f"- 内容: {action_item.get('text', task.get('title', ''))}",
            f"- 类型: {metadata.get('action_type', '未知')}",
            f"- 优先级: {action_item.get('priority', 'medium')}",
            "",
            f"## 原始邮件",
            f"- 邮件 ID: {email.get('id', '')}",
            f"- 发件人: {email.get('from_name', '')} <{email.get('from', '')}>",
            f"- 主题: {email.get('subject', '')}",
            f"- 日期: {email.get('date', '')}",
            f"- 正文:\n{(email.get('body', '') or '')[:2000]}",
        ]
        account_id = task.get("account_id") or email.get("account_id", "")
        if account_id:
            parts.append(f"\n- 账户 ID: {account_id}")

        parts.append("\n请分析这个行动项，然后调用工具来完成任务。只输出 JSON 工具调用。")
        return "\n".join(parts)

    # ── 工具分发 ──

    def _dispatch(self, name: str, args: dict,
                  task: dict, email: dict) -> dict:
        try:
            if name == "get_email":
                return self._tool_get_email(args)
            elif name == "get_ai_metadata":
                return self._tool_get_ai_metadata(args)
            elif name == "get_thread":
                return self._tool_get_thread(args)
            elif name == "search_emails":
                return self._tool_search_emails(args)
            elif name == "get_memories":
                return self._tool_get_memories(args)
            elif name == "search_local_files":
                return self._tool_search_local_files(args)
            elif name == "generate_reply":
                return self._tool_generate_reply(args, task)
            elif name == "confirm_and_send":
                return self._tool_confirm_and_send(args)
            else:
                return {"error": f"未知工具: {name}"}
        except Exception as e:
            print(f"[TaskHandler] 工具 {name} 执行出错: {e}")
            return {"error": str(e)}

    # ── HTTP helpers ──

    def _http_get(self, url: str, timeout: int = 30) -> Optional[dict]:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"error": str(e)}

    def _http_post(self, url: str, payload: dict,
                   timeout: int = 60) -> Optional[dict]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return {"error": str(e)}

    # ── 工具实现 ──

    def _tool_get_email(self, args: dict) -> dict:
        return self._http_get(f"{CLAWMAIL_API}/emails/{args['email_id']}") or {}

    def _tool_get_ai_metadata(self, args: dict) -> dict:
        return self._http_get(f"{CLAWMAIL_API}/emails/{args['email_id']}/ai-metadata") or {}

    def _tool_get_thread(self, args: dict) -> dict:
        limit = args.get("limit", 5)
        return self._http_get(f"{CLAWMAIL_API}/emails/thread/{args['thread_id']}?limit={limit}") or {}

    def _tool_search_emails(self, args: dict) -> dict:
        return self._http_post(f"{CLAWMAIL_API}/search", {
            "query": args["query"],
            "limit": args.get("limit", 5),
        }) or {}

    def _tool_get_memories(self, args: dict) -> dict:
        url = f"{CLAWMAIL_API}/memories/{args['account_id']}/for-email"
        params = []
        if args.get("sender_email"):
            params.append(f"sender_email={urllib.request.quote(args['sender_email'])}")
        if params:
            url += "?" + "&".join(params)
        return self._http_get(url) or {}

    def _tool_search_local_files(self, args: dict) -> dict:
        """搜索本地文件，返回匹配的文件路径列表。"""
        keywords = args.get("keywords", [])
        file_type = args.get("file_type", "any")
        if not keywords:
            return {"files": [], "message": "未提供搜索关键词"}

        search_dirs = [
            Path.home() / "Documents",
            Path.home() / "Desktop",
            Path.home() / "Downloads",
        ]
        type_map = {
            "pdf": ["*.pdf"],
            "docx": ["*.doc", "*.docx"],
            "doc": ["*.doc", "*.docx"],
            "pptx": ["*.ppt", "*.pptx"],
            "ppt": ["*.ppt", "*.pptx"],
            "xlsx": ["*.xls", "*.xlsx"],
            "xls": ["*.xls", "*.xlsx"],
        }
        extensions = type_map.get(file_type, [
            "*.pdf", "*.doc", "*.docx", "*.ppt", "*.pptx",
            "*.xls", "*.xlsx", "*.md", "*.txt", "*.zip", "*.rar",
        ])

        found = []
        for d in search_dirs:
            if not d.exists():
                continue
            for ext in extensions:
                for fp in d.rglob(ext):
                    fname = fp.stem.lower()
                    if any(kw.lower() in fname for kw in keywords):
                        found.append(str(fp))
                        if len(found) >= 10:
                            return {"files": found}
        return {"files": found, "message": f"搜索了 {len(search_dirs)} 个目录，找到 {len(found)} 个文件"}

    def _tool_generate_reply(self, args: dict, task: dict) -> dict:
        """调用 generate_reply.py skill 生成回复。"""
        if not REPLY_SCRIPT.exists():
            return {"error": f"回复脚本不存在: {REPLY_SCRIPT}"}

        cmd = [
            sys.executable, str(REPLY_SCRIPT),
            "--email-id", args["email_id"],
            "--stance", args["stance"],
        ]
        if args.get("user_notes"):
            cmd.extend(["--user-notes", args["user_notes"]])
        account_id = args.get("account_id") or task.get("account_id", "")
        if account_id:
            cmd.extend(["--account-id", account_id])

        try:
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            result = subprocess.run(cmd, capture_output=True, env=env, timeout=120)
            stdout = result.stdout.decode("utf-8", errors="replace").strip()
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            if stderr:
                for line in stderr.split("\n")[-5:]:
                    print(f"[TaskHandler] [Reply] {line[:120]}")
            if result.returncode != 0:
                # generate_reply.py 失败时错误 JSON 在 stdout
                err_msg = ""
                if stdout:
                    try:
                        err_data = json.loads(stdout)
                        err_msg = err_data.get("message", "")
                    except (json.JSONDecodeError, ValueError):
                        err_msg = stdout[:300]
                if not err_msg:
                    # 从 stderr 提取 ERROR 行
                    err_lines = [l for l in stderr.split("\n") if "ERROR" in l or "Error" in l or "Exception" in l]
                    err_msg = err_lines[-1][:300] if err_lines else stderr[-300:]
                return {"error": f"生成失败: {err_msg}", "reply_body": ""}
            return {"reply_body": stdout}
        except subprocess.TimeoutExpired:
            return {"error": "生成超时（120s）", "reply_body": ""}

    def _tool_confirm_and_send(self, args: dict) -> dict:
        """终结工具：弹出确认对话框，用户确认后发送。"""
        email_id = args["email_id"]
        reply_body = args["reply_body"]
        attachments = args.get("attachments", [])
        summary = args.get("summary", "")

        # 组装预览
        preview = ""
        if summary:
            preview += f"{summary}\n\n{'─' * 30}\n\n"
        preview += f"{reply_body}"
        if attachments:
            att_list = "\n".join(f"  📎 {os.path.basename(f)}" for f in attachments)
            preview += f"\n\n附件:\n{att_list}"

        # 弹窗确认
        dialog_result = self._http_post(f"{CLAWMAIL_API}/ui/confirm-dialog", {
            "title": "🤖 OpenClaw 执行确认",
            "message": preview,
            "options": [
                {"id": "send", "label": "确认发送"},
                {"id": "edit", "label": "编辑后发送"},
                {"id": "cancel", "label": "取消"},
            ],
            "timeout_seconds": 120,
        }, timeout=130)

        selected = (dialog_result or {}).get("selected_option_id", "cancel")
        print(f"[TaskHandler] 用户选择: {selected}")

        if selected == "send":
            send_result = self._http_post(f"{CLAWMAIL_API}/send-reply", {
                "email_id": email_id,
                "reply_body": reply_body,
                "reply_all": False,
                "attachments": attachments or None,
            })
            if send_result and not send_result.get("error"):
                return {"success": True, "action": "sent",
                        "sent_at": send_result.get("sent_at")}
            return {"success": False, "action": "send_failed",
                    "error": (send_result or {}).get("error", "发送失败")}

        elif selected == "edit":
            self._http_post(f"{CLAWMAIL_API}/compose", {
                "email_id": email_id,
                "reply_body": reply_body,
                "attachments": attachments or None,
            })
            return {"success": True, "action": "opened_compose"}

        else:
            return {"success": True, "action": "cancelled"}
