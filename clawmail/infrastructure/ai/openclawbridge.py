"""
OpenClawBridge — AI 服务统一接口
参照 ClawChat.py 实现，连接本地 OpenClaw 服务（OpenAI 兼容接口）。
设计规范：design/tech_spec.md OpenClawBridge 节
"""

import httpx
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
    ):
        self.model = model
        # trust_env=False prevents httpx from picking up macOS/system proxy settings
        # (e.g. Clash/V2Ray on 127.0.0.1:7890) which intercept localhost requests and return 502.
        self.client = OpenAI(
            api_key=token,
            base_url=base_url,
            http_client=httpx.Client(trust_env=False),
        )

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
        return full_response
