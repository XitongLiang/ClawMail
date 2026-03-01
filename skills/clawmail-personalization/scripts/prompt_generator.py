#!/usr/bin/env python3
"""
Prompt 生成器

调用大模型生成个性化 Prompt。
"""

import json
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime


class PromptGenerator:
    """调用 LLM 生成个性化 Prompt"""
    
    def __init__(self, openclaw_url: str = "http://127.0.0.1:18789", model: str = "kimi-k2.5"):
        self.openclaw_url = openclaw_url.rstrip("/")
        self.model = model
    
    def generate(
        self,
        feedback_type: str,
        prompt_type: str,  # 当前要生成的 prompt 类型
        feedback_data: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        current_prompt: str,
        other_prompts: Optional[Dict[str, str]] = None,  # 其他相关 prompts
        user_profile: Optional[str] = None
    ) -> str:
        """
        【强制】调用 LLM 生成个性化 Prompt。
        
        本方法必须使用 LLM 生成 prompt，不允许使用规则模板或其他非 LLM 方法。
        如果 LLM 调用失败，将抛出异常，整个个性化流程会失败。
        
        Args:
            feedback_type: 反馈类型（如 email_generation）
            prompt_type: 当前要生成的 prompt 类型（如 reply_draft）
            feedback_data: 原始反馈数据
            analysis: 分析结果
            current_prompt: 当前 prompt 内容
            other_prompts: 其他相关 prompts（可选）
            user_profile: 用户侧写（可选）
        
        Returns:
            新的个性化 prompt（由 LLM 生成）
        
        Raises:
            RuntimeError: 如果 LLM 调用失败或返回无效结果
        """
        print(f"   [LLM] 正在调用大模型生成 {prompt_type} prompt...")
        
        # 构建 LLM 提示词
        llm_prompt = self._build_llm_prompt(
            feedback_type=feedback_type,
            prompt_type=prompt_type,
            feedback_data=feedback_data,
            analysis=analysis,
            current_prompt=current_prompt,
            other_prompts=other_prompts,
            user_profile=user_profile
        )
        
        # 【强制】调用 LLM - 不允许回退到规则生成
        try:
            result = self._call_llm(llm_prompt, prompt_type)
            if not result or len(result.strip()) < 100:
                raise RuntimeError(f"LLM 返回的 prompt 内容过短或无效（长度: {len(result) if result else 0}）")
            print(f"   [LLM] ✓ 成功生成 {len(result)} 字符")
            return result
        except Exception as e:
            print(f"   [LLM] ✗ 调用失败: {e}")
            # 重新抛出异常，确保流程失败而不是静默回退
            raise RuntimeError(f"【强制 LLM 失败】无法生成 {prompt_type} prompt: {e}") from e
    
    def _build_llm_prompt(
        self,
        feedback_type: str,
        prompt_type: str,
        feedback_data: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        current_prompt: str,
        other_prompts: Optional[Dict[str, str]],
        user_profile: Optional[str]
    ) -> str:
        """构建给 LLM 的完整提示词"""
        
        # 反馈类型描述（8种反馈类型 + prompts）
        type_descriptions = {
            # 反馈类型
            "importance_score": "邮件重要性评分（0-100分）",
            "category": "邮件分类标签",
            "is_spam": "垃圾邮件检测",
            "action_category": "行动项分类",
            "reply_stances": "回复立场建议",
            "summary": "邮件摘要生成（含关键词提取）",
            "email_generation": "邮件生成（回复草稿 + 写新邮件）",
            "polish_email": "邮件润色",
            # Prompt 类型
            "reply_draft": "回复草稿生成",
            "generate_email": "写新邮件",
        }
        
        feedback_desc = type_descriptions.get(feedback_type, feedback_type)
        prompt_desc = type_descriptions.get(prompt_type, prompt_type)
        
        # 构建提示词
        prompt_parts = [
            f"你是邮件 AI 系统的个性化优化专家。",
            f"",
            f"## 任务",
            f"基于用户的反馈数据，优化「{prompt_desc}」的 AI 提示词（prompt）。",
            f"",
            f"## 反馈来源",
            f"反馈类型: {feedback_type} ({feedback_desc})",
            f"当前优化: {prompt_type} ({prompt_desc})",
            f"",
            f"## 用户反馈分析",
            f"",
            f"**分析摘要**: {analysis.get('summary', '')}",
            f"",
            f"**关键洞察**:",
        ]
        
        for insight in analysis.get('insights', []):
            prompt_parts.append(f"- {insight}")
        
        prompt_parts.extend([
            f"",
            f"**统计信息**:",
            f"```json",
            json.dumps(analysis.get('statistics', {}), ensure_ascii=False, indent=2),
            f"```",
            f"",
            f"**模式识别**:",
            f"```json",
            json.dumps(analysis.get('patterns', {}), ensure_ascii=False, indent=2),
            f"```",
            f"",
        ])
        
        # 添加其他 prompts 信息（如同时更新 reply_draft 和 generate_email）
        if other_prompts:
            prompt_parts.extend([
                f"## 其他相关 Prompts（需要一并考虑保持一致性）",
                f"",
            ])
            for other_type, other_prompt in other_prompts.items():
                other_desc = type_descriptions.get(other_type, other_type)
                prompt_parts.extend([
                    f"### {other_type} ({other_desc})",
                    f"```",
                    other_prompt[:500] + "..." if len(other_prompt) > 500 else other_prompt,
                    f"```",
                    f"",
                ])
        
        # 添加用户侧写
        if user_profile:
            prompt_parts.extend([
                f"## 用户侧写",
                f"```",
                user_profile[:1000],  # 限制长度
                f"```",
                f"",
            ])
        
        # 添加当前 prompt
        prompt_parts.extend([
            f"## 当前 Prompt（需要优化）",
            f"```",
            current_prompt,
            f"```",
            f"",
            f"## 输出要求",
            f"",
            f"请生成一份新的个性化 prompt，要求：",
            f"",
            f"1. **保留原有框架**：保持核心功能和输出格式不变",
            f"2. **基于反馈优化**：根据用户反馈分析，调整判断标准和规则",
            f"3. **具体可操作**：规则要明确，避免模糊描述",
            f"4. **适度调整**：不要过度偏离原 prompt 的结构",
            f"5. **解释说明**：为重要调整添加简要说明",
            f"",
            f"输出格式：",
            f"- 以 `#` 开头的标题",
            f"- 清晰的章节结构（如 ## 评分标准、## 个性化规则）",
            f"- 使用 Markdown 格式",
            f"",
            f"请直接输出新的 prompt 文本（不需要解释，只需要 prompt 内容）：",
        ])
        
        return "\n".join(prompt_parts)
    
    def _call_llm(self, prompt: str, feedback_type: str) -> str:
        """调用 OpenClaw LLM"""
        
        system_prompt = f"""你是邮件 AI 系统的个性化优化专家。
你的任务是基于用户反馈数据，优化 AI 提示词（prompt）。
请直接输出优化后的 prompt 文本，使用 Markdown 格式。"""
        
        try:
            response = httpx.post(
                f"{self.openclaw_url}/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 4000
                },
                timeout=120.0
            )
            response.raise_for_status()
            result = response.json()
            return result["choices"][0]["message"]["content"]
            
        except httpx.TimeoutException:
            raise RuntimeError("LLM 调用超时（120秒）")
        except httpx.ConnectError:
            raise RuntimeError(f"无法连接到 OpenClaw Gateway ({self.openclaw_url})")
        except Exception as e:
            raise RuntimeError(f"LLM 调用失败: {e}")
