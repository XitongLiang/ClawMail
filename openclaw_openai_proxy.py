"""
OpenClaw OpenAI API 代理
把 HTTP REST API 请求转发到 OpenClaw WebSocket Gateway

用法:
1. 安装依赖: pip install fastapi uvicorn websockets
2. 运行: python openclaw_openai_proxy.py
3. 在客户端配置: base_url="http://127.0.0.1:8080/v1", api_key="任意值"
"""

import json
import asyncio
import websockets
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Literal
import uvicorn

app = FastAPI(title="OpenClaw OpenAI API Proxy")

# ===== 配置 =====
GATEWAY_URL = "ws://127.0.0.1:18789"
GATEWAY_TOKEN = "1529ce1a12f23f4a028a5d3b4ee6c25da680e49f13db4f99"  # 从 openclaw.json 复制

# 存储会话的 WebSocket 连接（简单实现）
sessions = {}

class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    model: str
    messages: List[Message]
    stream: bool = False
    user: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None

async def send_to_openclaw(session_id: str, message: str, model: str = None) -> str:
    """通过 WebSocket 发送消息到 OpenClaw Gateway"""
    
    async with websockets.connect(GATEWAY_URL) as ws:
        # OpenClaw 的认证消息
        auth_msg = {
            "type": "auth",
            "token": GATEWAY_TOKEN,
            "session": session_id
        }
        await ws.send(json.dumps(auth_msg))
        
        # 发送用户消息
        user_msg = {
            "type": "agent_turn",
            "text": message,
            "session": session_id,
            "model": model
        }
        await ws.send(json.dumps(user_msg))
        
        # 接收响应
        response_text = ""
        async for msg in ws:
            try:
                data = json.loads(msg)
                msg_type = data.get("type")
                
                if msg_type == "agent_response":
                    content = data.get("content", "")
                    response_text += content
                    
                elif msg_type == "agent_done":
                    break
                    
                elif msg_type == "error":
                    raise Exception(f"Gateway error: {data.get('message', 'Unknown')}")
                    
            except json.JSONDecodeError:
                continue
                
        return response_text

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """OpenAI 兼容的 chat completions 接口"""
    
    try:
        # 取最后一条用户消息
        last_message = ""
        for msg in reversed(request.messages):
            if msg.role == "user":
                last_message = msg.content
                break
        
        if not last_message:
            raise HTTPException(status_code=400, detail="No user message found")
        
        session_id = request.user or f"openai_api_{asyncio.get_event_loop().time()}"
        model = request.model if request.model != "default" else None
        
        # 发送到 OpenClaw
        response_text = await send_to_openclaw(session_id, last_message, model)
        
        # 构造 OpenAI 格式的响应
        completion_id = f"chatcmpl-{hash(asyncio.get_event_loop().time()) % 10000000000}"
        
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": int(asyncio.get_event_loop().time()),
            "model": request.model or "default",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(last_message) // 4,  # 估算
                "completion_tokens": len(response_text) // 4,
                "total_tokens": (len(last_message) + len(response_text)) // 4
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/v1/models")
async def list_models():
    """列出可用模型"""
    return {
        "object": "list",
        "data": [
            {
                "id": "default",
                "object": "model",
                "created": 1700000000,
                "owned_by": "openclaw"
            },
            {
                "id": "kimi-k2.5",
                "object": "model",
                "created": 1700000000,
                "owned_by": "moonshot"
            }
        ]
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "gateway": GATEWAY_URL}

if __name__ == "__main__":
    print("🦞 OpenClaw OpenAI API 代理启动中...")
    print(f"   Gateway: {GATEWAY_URL}")
    print(f"   API 地址: http://127.0.0.1:8080/v1")
    print(f"   健康检查: http://127.0.0.1:8080/health")
    print(f"\n📘 使用方法:")
    print(f'   client = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="任意值")')
    print()
    
    uvicorn.run(app, host="127.0.0.1", port=8080)
