"""
OpenClaw OpenAI API 客户端
使用标准 OpenAI 库连接
"""

import os
from openai import OpenAI


class ClawChat:
    def __init__(self, token, base_url = "http://127.0.0.1:18789/v1"):
        self.token = token
        self.base_url = base_url
        self.connect() 
    
    def mailChat(self, mailInput, mailId = "mailAgent001"):
        messages = []
        messages.append({"role": "user", "content": mailInput})
        
        try:
            # 调用 OpenAI 格式的 API
            response = self.client.chat.completions.create(
                model = "default",  # 或 OpenClaw网关已经设置好相关的模型
                messages = messages,
                stream = True,  # 流式输出
                user = mailId
            )
            
            full_response = ""
            for chunk in response:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    
            messages.append({"role": "assistant", "content": full_response})

        except Exception as e:
            print(f"❌ 错误: {e}")
        
        return messages
    

    
    def userChat(self, userInput, userId = "userAgent001"):

        messages = []
        messages.append({"role": "user", "content": userInput})
        
        try:
            # 调用 OpenAI 格式的 API
            response = self.client.chat.completions.create(
                model = "default",  # 或 OpenClaw 支持的模型名
                messages = messages,
                stream = True,  # 流式输出
                user = userId
            )
            
            full_response = ""
            for chunk in response:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    
            messages.append({"role": "assistant", "content": full_response})

        except Exception as e:
            print(f"❌ 错误: {e}")
        
        return messages
    

    def connect(self):
        try:
            self.client = OpenAI(
                api_key = self.token,  # OpenClaw 可能不验证 key，但必须有
                base_url = self.base_url  # OpenClaw 的 OpenAI 兼容端点
                )
        
        except Exception as e:
            print(f"❌ 错误: {e}")


if __name__ == "__main__":

    # xAir
    # chat = ClawChat(token = "6b777db2700cfcedbaf8d11f5b02580025dd8d90cfce792a")
    
    chat = ClawChat(token = "1529ce1a12f23f4a028a5d3b4ee6c25da680e49f13db4f99")
    
    print("🤖 OpenClaw (OpenAI API 模式)\n输入 'quit' 退出\n")
    
    messages = []
    
    while True:
        userInput = input("👤 你: ").strip()
        if userInput.lower() in ['quit', 'exit', 'q']:
            break

        responsedMessages = chat.userChat(userInput = userInput, userId = "userAgent001")

        print("🤖: ", end="", flush=True)
        print(responsedMessages[1]["content"], end="", flush=True)
        print("")

