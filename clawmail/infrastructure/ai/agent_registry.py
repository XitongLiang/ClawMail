"""Agent registry for ClawMail AI assistant.

Single unified assistant for email search, organization, and general Q&A.
"""

AGENT_REGISTRY = {
    "user_chat": {
        "id": "userAgent001",
        "name": "邮件助手",
        "description": "AI 助手：检索邮件、整理信息、回答问题",
        "method": "user_chat",
        "context_aware": True,
    },
}
