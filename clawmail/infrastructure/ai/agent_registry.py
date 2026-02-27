"""Agent registry for ClawMail AI assistants.

This module defines all available AI agents and their configurations
for use in the chat interface.
"""

AGENT_REGISTRY = {
    "user_chat": {
        "id": "userAgent001",
        "name": "通用对话 (userAgent001)",
        "description": "与AI助手自由对话，询问任何问题",
        "method": "user_chat",
        "context_aware": False,
    },
    "mail_chat": {
        "id": "mailAgent001",
        "name": "邮件分析 (mailAgent001)",
        "description": "分析邮件内容，提取关键信息和行动项",
        "method": "process_email",
        "context_aware": True,
    },
    "personalization_chat": {
        "id": "personalizationAgent001",
        "name": "个性化助手 (personalizationAgent001)",
        "description": "讨论您的使用偏好，调整AI行为",
        "method": "user_chat",
        "context_aware": False,
    },
    "draft_chat": {
        "id": "draftAgent001",
        "name": "回复起草 (draftAgent001)",
        "description": "帮助撰写邮件回复草稿",
        "method": "user_chat",
        "context_aware": True,
    },
    "generate_chat": {
        "id": "generateAgent001",
        "name": "邮件生成 (generateAgent001)",
        "description": "根据主题和大纲生成完整邮件",
        "method": "user_chat",
        "context_aware": False,
    },
    "polish_chat": {
        "id": "polishAgent001",
        "name": "文本润色 (polishAgent001)",
        "description": "优化和润色邮件文本",
        "method": "user_chat",
        "context_aware": False,
    },
}
