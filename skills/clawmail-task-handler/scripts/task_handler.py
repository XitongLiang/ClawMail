"""
ClawMail Task Handler - 自动处理待办任务

使用方法:
    python task_handler.py --task-id <task_id>     # 处理指定任务
    python task_handler.py --all-pending          # 处理所有待处理任务
    python task_handler.py --task-id <id> --dry-run  # 测试模式
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import urllib.request
import urllib.error

CLAWMAIL_API = "http://127.0.0.1:9999"


class TaskHandler:
    """ClawMail 待办任务处理器"""

    def __init__(self, api_base: str = CLAWMAIL_API):
        self.api = api_base
        self.timeout = 60

    # ----------------------------------------------------------------
    # HTTP 辅助方法（仅使用标准库，无需 requests 依赖）
    # ----------------------------------------------------------------

    def _http_get(self, url: str, timeout: int = None) -> Optional[Dict]:
        """GET 请求，返回 JSON dict 或 None。"""
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[HTTP GET] {url} 失败: {e}")
        return None

    def _http_post(self, url: str, payload: dict,
                   timeout: int = None) -> Optional[Dict]:
        """POST JSON 请求，返回 JSON dict 或 None。"""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
                else:
                    print(f"[HTTP POST] {url} 返回 {resp.status}")
        except Exception as e:
            print(f"[HTTP POST] {url} 失败: {e}")
        return None

    def process_task(self, task_id: str, dry_run: bool = False) -> Dict:
        """处理单个任务"""
        print(f"\n{'='*50}")
        print(f"处理任务: {task_id}")
        print(f"{'='*50}")

        # 1. 获取任务详情
        task = self._get_task(task_id)
        if not task:
            return {"success": False, "error": "Task not found"}

        print(f"任务: {task.get('title')}")
        print(f"分类: {task.get('category')}")
        print(f"优先级: {task.get('priority')}")

        # 2. 获取关联邮件
        email = self._get_source_email(task_id)
        if not email:
            print("[!] 未找到关联邮件")
            return {"success": False, "error": "No source email"}

        print(f"关联邮件: {email.get('subject')}")
        print(f"发件人: {email.get('from_name')} <{email.get('from')}>")

        # 3. proactive 任务交给 agent 自主执行
        if task.get('source_type') == 'proactive':
            print("\n任务类型: proactive (agent 模式)")
            if dry_run:
                return {"success": True, "dry_run": True, "message": "proactive agent would run"}
            from agent import ProactiveAgent
            agent_result = ProactiveAgent().run(task, email)
            if agent_result.get('success') and agent_result.get('action') != 'cancelled':
                self._complete_task(task_id)
                print(f"[OK] 任务已标记为完成 (action={agent_result.get('action')})")
            return {"success": agent_result.get('success'), "task_id": task_id, "details": agent_result}

        # 4. 非 proactive 任务：识别类型并生成选项
        task_type, options = self._analyze_task(task, email)
        print(f"\n任务类型: {task_type}")

        if dry_run:
            print("\n[测试模式] 生成的选项:")
            for opt in options:
                print(f"  - {opt['id']}: {opt['label']}")
            return {"success": True, "dry_run": True, "options": options}

        # 5. 显示确认弹窗
        dialog_result = self._show_confirm_dialog(task, options)
        if not dialog_result.get('success'):
            return {"success": False, "error": dialog_result.get('error', 'Dialog cancelled')}

        selected = dialog_result.get('selected_option_id')
        print(f"\n用户选择: {selected}")

        # 6. 执行操作
        action_result = self._execute_action(selected, options, email)

        # 7. 标记任务完成（如果执行成功）
        if action_result.get('success'):
            self._complete_task(task_id)
            print("[OK] 任务已标记为完成")

        return {
            "success": action_result.get('success'),
            "task_id": task_id,
            "action": selected,
            "details": action_result
        }

    def process_all_pending(self, dry_run: bool = False) -> List[Dict]:
        """处理所有待处理任务"""
        tasks = self._get_pending_tasks()
        print(f"\n发现 {len(tasks)} 个待处理任务\n")

        results = []
        for task in tasks:
            result = self.process_task(task['id'], dry_run=dry_run)
            results.append(result)

        return results

    def _get_task(self, task_id: str) -> Optional[Dict]:
        """获取任务详情"""
        return self._http_get(f"{self.api}/tasks/{task_id}")

    def _get_pending_tasks(self) -> List[Dict]:
        """获取所有待处理任务"""
        data = self._http_get(f"{self.api}/tasks?status=pending&limit=50")
        return (data or {}).get('tasks', [])

    def _get_source_email(self, task_id: str) -> Optional[Dict]:
        """获取任务关联的源邮件"""
        data = self._http_get(f"{self.api}/tasks/{task_id}/email")
        return (data or {}).get('email')

    def _analyze_task(self, task: Dict, email: Dict) -> Tuple[str, List[Dict]]:
        """分析非 proactive 任务类型并生成选项。"""
        title = task.get('title', '').lower()
        subject = email.get('subject', '').lower()

        if any(kw in title + subject for kw in ['会议', '时间', '确认', '下午', '上午']):
            return self._generate_meeting_options(task, email)
        if any(kw in title for kw in ['回复', '跟进', 're:', '答复']):
            return self._generate_reply_options(task, email)
        return self._generate_generic_options(task, email)

    def _generate_meeting_options(self, task: Dict, email: Dict) -> Tuple[str, List[Dict]]:
        """生成会议确认选项"""
        body = email.get('body', '')

        # 提取时间段（简化处理）
        options = [
            {
                "id": "reply_14_15",
                "label": "回复确认 14:00-15:00",
                "action": "send_reply",
                "reply_body": self._generate_meeting_reply(email, "14:00-15:00")
            },
            {
                "id": "reply_15_16",
                "label": "回复确认 15:00-16:00",
                "action": "send_reply",
                "reply_body": self._generate_meeting_reply(email, "15:00-16:00")
            },
            {
                "id": "reply_16_17",
                "label": "回复确认 16:00-17:00",
                "action": "send_reply",
                "reply_body": self._generate_meeting_reply(email, "16:00-17:00")
            },
            {
                "id": "ask_time",
                "label": "询问对方建议时间",
                "action": "send_reply",
                "reply_body": self._generate_ask_time_reply(email)
            },
            {
                "id": "skip",
                "label": "暂不处理",
                "action": "skip"
            }
        ]

        return "meeting_confirmation", options

    def _generate_reply_options(self, task: Dict, email: Dict) -> Tuple[str, List[Dict]]:
        """生成邮件回复选项"""
        options = [
            {
                "id": "send_reply",
                "label": "发送回复",
                "action": "send_reply",
                "reply_body": self._generate_generic_reply(email)
            },
            {
                "id": "edit_reply",
                "label": "编辑后发送（打开撰写窗口）",
                "action": "open_compose"
            },
            {
                "id": "skip",
                "label": "跳过",
                "action": "skip"
            }
        ]
        return "email_reply", options

    def _generate_generic_options(self, task: Dict, email: Dict) -> Tuple[str, List[Dict]]:
        """生成通用选项"""
        options = [
            {
                "id": "mark_done",
                "label": "标记为已完成",
                "action": "complete"
            },
            {
                "id": "snooze_1day",
                "label": "推迟1天",
                "action": "snooze",
                "snooze_days": 1
            },
            {
                "id": "skip",
                "label": "跳过",
                "action": "skip"
            }
        ]
        return "generic", options

    def _generate_meeting_reply(self, email: Dict, time_slot: str) -> str:
        """生成会议确认回复"""
        from_name = email.get('from_name', '')
        first_name = from_name.split()[0] if from_name else '您好'

        return f"""{first_name}，

好的，那我们定在明天下午{time_slot}开会。

会议室我会提前预订，到时候见！

谢谢，
Tony"""

    def _generate_ask_time_reply(self, email: Dict) -> str:
        """生成询问时间回复"""
        from_name = email.get('from_name', '')
        first_name = from_name.split()[0] if from_name else '您好'

        return f"""{first_name}，

收到，明天下午我有空。

请问您建议哪个具体时间段比较方便？以下是可选时间：
- 14:00-15:00
- 15:00-16:00
- 16:00-17:00

请告诉我您的偏好，谢谢！

Tony"""

    def _generate_generic_reply(self, email: Dict) -> str:
        """生成通用回复"""
        return "收到，我会尽快处理。谢谢！"

    def _show_confirm_dialog(self, task: Dict, options: List[Dict]) -> Dict:
        """显示确认弹窗"""
        dialog_options = [{"id": opt["id"], "label": opt["label"]} for opt in options]

        payload = {
            "title": "AI待办处理确认",
            "message": f"任务：{task.get('title')}\n\n请选择处理方式：",
            "options": dialog_options,
            "default_option_id": dialog_options[0]["id"] if dialog_options else None,
            "timeout_seconds": 60
        }

        result = self._http_post(f"{self.api}/ui/confirm-dialog", payload, timeout=70)
        return result or {"success": False, "error": "弹窗请求失败"}

    def _execute_action(self, selected_id: str, options: List[Dict], email: Dict) -> Dict:
        """执行选中的操作"""
        selected_opt = next((opt for opt in options if opt["id"] == selected_id), None)
        if not selected_opt:
            return {"success": False, "error": "Invalid option"}

        action = selected_opt.get("action")
        attachments = selected_opt.get("attachments", [])

        if action == "send_reply":
            return self._send_reply(
                email, selected_opt.get("reply_body", ""),
                attachments=attachments,
            )

        elif action == "open_compose":
            return self._open_compose(
                email, selected_opt.get("reply_body", ""),
                attachments=attachments,
            )

        elif action == "complete":
            return {"success": True, "action": "marked_complete"}

        elif action == "snooze":
            return {"success": True, "action": "snoozed"}

        elif action == "skip":
            return {"success": True, "action": "skipped"}

        return {"success": False, "error": "Unknown action"}

    def _send_reply(self, email: Dict, reply_body: str,
                    attachments: List[str] = None) -> Dict:
        """发送回复邮件（可选附件）"""
        email_id = email.get('id')
        if not email_id:
            return {"success": False, "error": "No email ID"}

        payload = {
            "email_id": email_id,
            "reply_body": reply_body,
            "reply_all": False,
        }
        if attachments:
            payload["attachments"] = attachments

        result = self._http_post(f"{self.api}/send-reply", payload)
        if result:
            print(f"[OK] 邮件已发送: {result.get('sent_at')}")
            return {"success": True, "sent_at": result.get('sent_at')}
        return {"success": False, "error": "send-reply 请求失败"}

    def _open_compose(self, email: Dict, reply_body: str,
                      attachments: List[str] = None) -> Dict:
        """通过 API 打开撰写窗口（带预填内容和附件）"""
        payload = {
            "email_id": email.get('id'),
            "reply_body": reply_body,
        }
        if attachments:
            payload["attachments"] = attachments

        result = self._http_post(f"{self.api}/compose", payload)
        if result is not None:
            return {"success": True, "action": "opened_compose"}
        return {"success": False, "error": "compose 请求失败"}

    def _complete_task(self, task_id: str) -> bool:
        """标记任务完成"""
        result = self._http_post(f"{self.api}/tasks/{task_id}/complete", {})
        return result is not None


def main():
    parser = argparse.ArgumentParser(description="ClawMail 任务处理器")
    parser.add_argument("--task-id", help="处理指定任务ID")
    parser.add_argument("--all-pending", action="store_true", help="处理所有待处理任务")
    parser.add_argument("--dry-run", action="store_true", help="测试模式，不实际执行")

    args = parser.parse_args()

    handler = TaskHandler()

    if args.task_id:
        result = handler.process_task(args.task_id, dry_run=args.dry_run)
        print("\n" + "="*50)
        print("处理结果:")
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.all_pending:
        results = handler.process_all_pending(dry_run=args.dry_run)
        print("\n" + "="*50)
        print(f"处理了 {len(results)} 个任务")
        success_count = sum(1 for r in results if r.get('success'))
        print(f"成功: {success_count}/{len(results)}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
