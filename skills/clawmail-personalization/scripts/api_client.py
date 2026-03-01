#!/usr/bin/env python3
"""
ClawMail HTTP API 客户端

通过 REST API 与 ClawMail 交互，读写反馈数据和 prompt。
"""

import httpx
from typing import List, Dict, Any, Optional


class ClawMailAPIClient:
    """ClawMail HTTP API 客户端"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:9999", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)
    
    def _url(self, path: str) -> str:
        """构建完整 URL"""
        return f"{self.base_url}{path}"
    
    def get_feedback(self, feedback_type: str) -> List[Dict[str, Any]]:
        """
        获取反馈数据。
        
        GET /personalization/feedback/{type}
        
        Returns:
            反馈数据列表（JSON 数组）
        """
        url = self._url(f"/personalization/feedback/{feedback_type}")
        response = self.client.get(url)
        response.raise_for_status()
        return response.json()
    
    def get_prompt(self, prompt_type: str) -> str:
        """
        获取当前 prompt 内容。
        
        GET /personalization/prompt/{type}
        
        Returns:
            prompt 文本内容
        """
        url = self._url(f"/personalization/prompt/{prompt_type}")
        response = self.client.get(url)
        response.raise_for_status()
        # 如果返回的是 JSON，提取 content 字段
        data = response.json()
        if isinstance(data, dict):
            return data.get("content", "")
        return data if isinstance(data, str) else ""
    
    def update_prompt(self, prompt_type: str, content: str) -> Dict[str, Any]:
        """
        更新 prompt（自动备份旧版本）。
        
        POST /personalization/update-prompt
        body: {"prompt_type": "...", "content": "..."}
        
        Returns:
            API 响应数据
        """
        url = self._url("/personalization/update-prompt")
        response = self.client.post(
            url,
            json={"prompt_type": prompt_type, "content": content}
        )
        response.raise_for_status()
        return response.json()
    
    def archive_feedback(self, feedback_type: str) -> Dict[str, Any]:
        """
        归档反馈数据并清空主文件。
        
        POST /personalization/archive-feedback
        body: {"feedback_type": "..."}
        
        Returns:
            API 响应数据
        """
        url = self._url("/personalization/archive-feedback")
        response = self.client.post(
            url,
            json={"feedback_type": feedback_type}
        )
        response.raise_for_status()
        return response.json()
    
    def notify_completion(
        self,
        prompt_type: str,
        success: bool = True,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        通知 ClawMail 个性化更新完成。
        
        POST /personalization/status
        body: {"prompt_type": "...", "success": true/false, "error": "..."}
        
        Returns:
            API 响应数据
        """
        url = self._url("/personalization/status")
        payload = {
            "prompt_type": prompt_type,
            "success": success
        }
        if error:
            payload["error"] = error
        
        response = self.client.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    
    def close(self):
        """关闭 HTTP 客户端"""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
