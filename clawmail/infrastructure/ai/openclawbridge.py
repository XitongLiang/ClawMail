"""
OpenClawBridge — AI 服务统一接口
使用 OpenClaw Gateway 原生 WebSocket JSON-RPC 协议（chat.send）。
"""

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import websockets


def _extract_text(msg) -> str:
    """从 ChatEvent.message 中提取纯文本（兼容各种格式）。"""
    if not msg:
        return ""
    if isinstance(msg, str):
        return msg
    if isinstance(msg, dict):
        content = msg.get("content")
        if isinstance(content, list):
            # [{type:"text", text:"..."}]
            return "".join(
                item.get("text", "") for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        if isinstance(content, str):
            return content
        return msg.get("text", "")
    return ""


class OpenClawBridge:
    """
    同步 AI 调用封装。在 Plugin 层通过 run_in_executor 转为异步。
    使用 WebSocket 原生协议替代 OpenAI HTTP 兼容层。
    """

    _WS_URL = "ws://127.0.0.1:18789"

    def __init__(
        self,
        token: str,
        log_dir: Optional[Path] = None,
    ):
        self._token = token
        self._log_dir = log_dir
        if self._log_dir:
            self._log_dir.mkdir(parents=True, exist_ok=True)

    def user_chat(
        self,
        user_input: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """AI 对话调用（同步接口）。内部通过 asyncio.run() 执行 WebSocket 流程。"""
        return asyncio.run(self._ws_chat(user_input, system_prompt))

    async def _ws_chat(
        self,
        user_input: str,
        system_prompt: Optional[str],
    ) -> str:
        async with websockets.connect(self._WS_URL) as ws:
            # Step 1: 等待服务端推送 connect.challenge 事件（携带 nonce）
            # 对于 token 认证不需要设备签名，但需等到 challenge 再发 connect 请求
            loop = asyncio.get_event_loop()
            deadline = loop.time() + 5.0
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break  # 超时则直接发 connect，无 nonce
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    frame = json.loads(raw)
                    if frame.get("type") == "event" and frame.get("event") == "connect.challenge":
                        break  # 收到 challenge，可以发 connect 了
                except asyncio.TimeoutError:
                    break

            # Step 2: 发送 connect 请求帧（标准 RPC 格式）
            connect_id = str(uuid.uuid4())[:8]
            await ws.send(json.dumps({
                "type": "req",
                "id": connect_id,
                "method": "connect",
                "params": {
                    "minProtocol": 3,
                    "maxProtocol": 3,
                    "client": {
                        "id": "gateway-client",
                        "mode": "backend",
                        "version": "1.0",
                        "platform": "python",
                        "displayName": "ClawMail",
                    },
                    "auth": {"token": self._token},
                },
            }))

            # Step 3: 等待 connect 的 res 帧（payload 为 hello-ok 内容）
            hello = None
            deadline = loop.time() + 10.0
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    raise RuntimeError("Gateway 握手超时：未收到 hello-ok")
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                frame = json.loads(raw)
                if frame.get("type") == "res" and frame.get("id") == connect_id:
                    if not frame.get("ok"):
                        raise RuntimeError(f"Gateway 认证失败: {frame.get('error')}")
                    hello = frame.get("payload", {})
                    break
                # 跳过 event 等中间帧
            session_key = (
                hello.get("snapshot", {})
                .get("sessionDefaults", {})
                .get("mainSessionKey", "main")
            )

            # Step 3: 构建消息（system_prompt 编码为指令前缀）
            message = f"(ClawMail){user_input}"
            if system_prompt:
                message = f"[Instruction: {system_prompt}]\n\n{message}"

            # Step 4: 发送 chat.send RPC
            req_id = str(uuid.uuid4())[:8]
            await ws.send(json.dumps({
                "type": "req",
                "id": req_id,
                "method": "chat.send",
                "params": {
                    "sessionKey": session_key,
                    "message": message,
                    "idempotencyKey": str(uuid.uuid4()),
                },
            }))

            # Step 5: 收集流式 ChatEvent
            full_response = ""
            async for raw in ws:
                frame = json.loads(raw)

                if frame.get("type") == "res" and frame.get("id") == req_id:
                    if not frame.get("ok"):
                        raise RuntimeError(f"chat.send 失败: {frame.get('error')}")
                    continue

                if frame.get("type") == "event" and frame.get("event") == "chat":
                    payload = frame.get("payload", {})
                    state = payload.get("state")

                    if state == "delta":
                        pass  # delta 文本是累积的，以 final 为准

                    elif state == "final":
                        full_response = _extract_text(payload.get("message"))
                        break

                    elif state in ("aborted", "error"):
                        raise RuntimeError(payload.get("errorMessage", f"Chat {state}"))

        self._save_chat_log(f"(ClawMail){user_input}", full_response)
        return full_response

    def _save_chat_log(self, sent: str, received: str) -> None:
        """将对话追加写入 {log_dir}/chat.log。"""
        if not self._log_dir:
            return
        try:
            log_file = self._log_dir / "chat.log"
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
