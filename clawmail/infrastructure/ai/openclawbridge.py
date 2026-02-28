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

    统一方法 user_chat() 处理所有 agent 调用，通过 user_id 区分 agent。
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

    def user_chat(
        self,
        user_input: str,
        user_id: str = "userAgent001",
        system_prompt: Optional[str] = None,
    ) -> str:
        """统一 AI 调用方法，通过 user_id 区分 agent。
        system_prompt: 可选 system 消息，用于强制输出格式（如 JSON-only）。
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": f"(ClawMail){user_input}"})
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
