"""
OpenClawBridge — AI 服务统一接口
参照 ClawChat.py 实现，连接本地 OpenClaw 服务（OpenAI 兼容接口）。
设计规范：design/tech_spec.md OpenClawBridge 节
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from openai import OpenAI


class OpenClawBridge:
    """
    同步 AI 调用封装。在 Plugin 层通过 run_in_executor 转为异步。

    两种 agent 类型：
    - mailAgent_{email_id[:8]}  —— 邮件处理（process_email）
    - userAgent001              —— 用户对话（user_chat）
    """

    def __init__(
        self,
        token: str,
        base_url: str = "http://127.0.0.1:18789/v1",
        model: str = "default",
        log_dir: Optional[Path] = None,
    ):
        self.model = model
        self.client = OpenAI(api_key=token, base_url=base_url)
        self._log_dir = log_dir
        if self._log_dir:
            self._log_dir.mkdir(parents=True, exist_ok=True)

    def process_email(
        self,
        mail_input: str,
        mail_id: str = "mailAgent001",
    ) -> str:
        """
        邮件 AI 处理，对应 ClawChat.mailChat 模式。
        mail_id 固定使用 mailAgent001。
        """
        messages = [{"role": "user", "content": f"(ClawMail){mail_input}"}]
        full_response = ""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            user=mail_id,
        )
        for chunk in response:
            if chunk.choices[0].delta.content:
                full_response += chunk.choices[0].delta.content
        self._save_chat_log(mail_id, f"(ClawMail){mail_input}", full_response)
        return full_response

    def user_chat(
        self,
        user_input: str,
        user_id: str = "userAgent001",
    ) -> str:
        """用户 AI 对话，对应 ClawChat.userChat 模式。"""
        messages = [{"role": "user", "content": f"(ClawMail){user_input}"}]
        full_response = ""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            user=user_id,
        )
        for chunk in response:
            if chunk.choices[0].delta.content:
                full_response += chunk.choices[0].delta.content
        self._save_chat_log(user_id, f"(ClawMail){user_input}", full_response)
        return full_response

    def _save_chat_log(self, agent_id: str, sent: str, received: str) -> None:
        """将对话追加写入 {log_dir}/{agent_id}.log。"""
        if not self._log_dir:
            return
        try:
            log_file = self._log_dir / f"{agent_id}.log"
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry = (
                f"===== {ts} =====\n"
                f"[ClawMail → OpenClaw]\n{sent}\n\n"
                f"[OpenClaw → ClawMail]\n{received}\n\n"
            )
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass  # 日志写入失败不影响主流程
