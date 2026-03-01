"""
ClawMail Task Handler - API 工具层
提供对 ClawMail REST API 的封装，供 OpenClaw agent 直接调用。
"""

import json
from typing import Dict, List, Optional

import requests

CLAWMAIL_API = "http://127.0.0.1:9999"


class ClawMailAPI:
    def __init__(self, api_base: str = CLAWMAIL_API):
        self.api = api_base
        self.timeout = 60

    def get_pending_tasks(self, limit: int = 20) -> List[Dict]:
        resp = requests.get(f"{self.api}/tasks?status=pending&limit={limit}", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json().get("tasks", [])

    def get_task(self, task_id: str) -> Dict:
        resp = requests.get(f"{self.api}/tasks/{task_id}", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_task_email(self, task_id: str) -> Optional[Dict]:
        resp = requests.get(f"{self.api}/tasks/{task_id}/email", timeout=self.timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("email")

    def get_ai_metadata(self, email_id: str) -> Optional[Dict]:
        resp = requests.get(f"{self.api}/emails/{email_id}/ai-metadata", timeout=self.timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def show_confirm_dialog(
        self,
        title: str,
        message: str,
        options: List[Dict],
        default_option_id: Optional[str] = None,
        timeout_seconds: int = 60,
    ) -> Dict:
        payload = {
            "title": title,
            "message": message,
            "options": options,
            "default_option_id": default_option_id or options[0]["id"],
            "timeout_seconds": timeout_seconds,
        }
        resp = requests.post(f"{self.api}/ui/confirm-dialog", json=payload, timeout=timeout_seconds + 10)
        resp.raise_for_status()
        return resp.json()

    def send_reply(self, email_id: str, reply_body: str, reply_all: bool = False) -> Dict:
        payload = {"email_id": email_id, "reply_body": reply_body, "reply_all": reply_all}
        resp = requests.post(f"{self.api}/send-reply", json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def open_compose(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: Optional[List[str]] = None,
    ) -> Dict:
        payload = {"to": to, "subject": subject, "body": body}
        if attachments:
            payload["attachments"] = attachments
        resp = requests.post(f"{self.api}/compose", json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def complete_task(self, task_id: str) -> bool:
        resp = requests.post(f"{self.api}/tasks/{task_id}/complete", timeout=self.timeout)
        return resp.status_code == 200


if __name__ == "__main__":
    # 快速测试：列出待办任务
    api = ClawMailAPI()
    tasks = api.get_pending_tasks()
    print(json.dumps(tasks, indent=2, ensure_ascii=False))
