#!/usr/bin/env python3
"""
用户侧写加载器

从 OpenClaw 记忆系统读取用户画像。
"""

from pathlib import Path
from typing import Optional


class UserProfileLoader:
    """加载用户侧写信息"""
    
    def __init__(self, workspace_dir: Optional[str] = None):
        if workspace_dir:
            self.workspace_dir = Path(workspace_dir).expanduser()
        else:
            self.workspace_dir = Path.home() / ".openclaw" / "workspace"
    
    def load_profile(self) -> Optional[str]:
        """
        加载用户侧写。
        
        按优先级读取以下文件：
        1. USER.md - 用户基本信息
        2. MEMORY.md - 长期记忆
        3. memory/YYYY-MM-DD.md - 最近几天的记忆
        
        Returns:
            合并后的用户侧写文本，如果没有则返回 None
        """
        profile_parts = []
        
        # 1. 读取 USER.md
        user_md = self.workspace_dir / "USER.md"
        if user_md.exists():
            content = self._read_file(user_md)
            if content:
                profile_parts.append(f"=== 用户基本信息 ===\n{content}")
        
        # 2. 读取 MEMORY.md
        memory_md = self.workspace_dir / "MEMORY.md"
        if memory_md.exists():
            content = self._read_file(memory_md)
            if content:
                profile_parts.append(f"=== 长期记忆 ===\n{content[:2000]}")  # 限制长度
        
        # 3. 读取最近的 memory 文件
        memory_dir = self.workspace_dir / "memory"
        if memory_dir.exists():
            # 获取最近的 3 个 memory 文件
            memory_files = sorted(
                memory_dir.glob("*.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )[:3]
            
            for mem_file in memory_files:
                content = self._read_file(mem_file)
                if content:
                    profile_parts.append(f"=== {mem_file.name} ===\n{content[:1000]}")
        
        if profile_parts:
            return "\n\n".join(profile_parts)
        
        return None
    
    def _read_file(self, path: Path) -> Optional[str]:
        """安全地读取文件"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return None
