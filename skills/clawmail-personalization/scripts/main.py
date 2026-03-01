#!/usr/bin/env python3
"""
ClawMail Personalization Skill - 主入口

根据 ClawMail 触发消息，执行完整的个性化闭环：
1. 解析触发消息
2. 读取反馈数据（通过 REST API）
3. 分析用户偏好
4. 调用 LLM 生成新 prompt
5. 更新 prompt（通过 REST API）
6. 归档反馈

Usage:
    python main.py --trigger-message "(ClawMail-Personalization) ..."
"""

import argparse
import json
import sys
from pathlib import Path

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from api_client import ClawMailAPIClient
from feedback_analyzer import FeedbackAnalyzer
from prompt_generator import PromptGenerator
from user_profile import UserProfileLoader


# 支持的反馈类型（8种）
SUPPORTED_TYPES = [
    "importance_score",
    "category",
    "is_spam",
    "action_category",
    "reply_stances",
    "summary",
    "email_generation",  # 合并 reply_draft + generate_email
    "polish_email",
]


def parse_trigger_message(message: str) -> dict:
    """
    解析 ClawMail 触发消息。
    
    消息格式：
    (ClawMail-Personalization) 用户已累积足够的{type}反馈...
    feedback_type: {type}
    feedback_path: ~/clawmail_data/feedback/feedback_{type}.jsonl
    prompt_paths: ["type"] 或 ["reply_draft", "generate_email"]
    related_prompts: []
    archive_dir: ~/clawmail_data/feedback/{type}
    prompt_archive_dir: ~/clawmail_data/prompts/archive
    """
    result = {
        "feedback_type": None,
        "feedback_path": None,
        "prompt_paths": [],  # 改为数组，支持多个 prompt
        "related_prompts": [],
        "archive_dir": None,
        "prompt_archive_dir": None,
    }
    
    lines = message.strip().split("\n")
    
    for line in lines:
        line = line.strip()
        if line.startswith("feedback_type:"):
            result["feedback_type"] = line.split(":", 1)[1].strip()
        elif line.startswith("feedback_path:"):
            result["feedback_path"] = line.split(":", 1)[1].strip()
        elif line.startswith("prompt_paths:"):
            # 解析 JSON 数组
            json_str = line.split(":", 1)[1].strip()
            try:
                result["prompt_paths"] = json.loads(json_str)
            except json.JSONDecodeError:
                result["prompt_paths"] = []
        elif line.startswith("related_prompts:"):
            json_str = line.split(":", 1)[1].strip()
            try:
                result["related_prompts"] = json.loads(json_str)
            except json.JSONDecodeError:
                result["related_prompts"] = []
        elif line.startswith("archive_dir:"):
            result["archive_dir"] = line.split(":", 1)[1].strip()
        elif line.startswith("prompt_archive_dir:"):
            result["prompt_archive_dir"] = line.split(":", 1)[1].strip()
    
    return result


def validate_trigger_info(info: dict) -> tuple[bool, str]:
    """验证触发信息是否完整"""
    if not info["feedback_type"]:
        return False, "缺少 feedback_type"
    
    if info["feedback_type"] not in SUPPORTED_TYPES:
        return False, f"不支持的 feedback_type: {info['feedback_type']}"
    
    if not info["feedback_path"]:
        return False, "缺少 feedback_path"
    
    return True, ""


class PersonalizationSkill:
    """个性化 Skill 主类"""
    
    def __init__(
        self,
        clawmail_api_url: str = "http://127.0.0.1:9999",
        openclaw_url: str = "http://127.0.0.1:18789",
        model: str = "kimi-k2.5"
    ):
        self.api_client = ClawMailAPIClient(clawmail_api_url)
        self.prompt_generator = PromptGenerator(openclaw_url, model)
        self.profile_loader = UserProfileLoader()
    
    def run(self, trigger_info: dict, dry_run: bool = False) -> dict:
        """
        执行完整的个性化更新流程。
        
        Args:
            trigger_info: 解析后的触发消息
            dry_run: 如果为 True，只预览不实际执行
        
        Returns:
            执行结果字典
        """
        feedback_type = trigger_info["feedback_type"]
        # prompt_paths 是要更新的 prompt 文件列表（如 ["reply_draft", "generate_email"]）
        prompt_paths = trigger_info.get("prompt_paths") or [feedback_type]
        
        result = {
            "status": "pending",
            "feedback_type": feedback_type,
            "prompt_paths": prompt_paths,
            "steps": {},
            "errors": []
        }
        
        try:
            print(f"\n{'='*60}")
            print(f"ClawMail 个性化更新 - {feedback_type}")
            print(f"{'='*60}\n")
            
            # 步骤 1: 读取反馈数据
            print(f"步骤 1: 读取 {feedback_type} 反馈数据...")
            feedback_data = self.api_client.get_feedback(feedback_type)
            if not feedback_data:
                result["status"] = "skipped"
                result["message"] = "没有反馈数据"
                print(f"⚠️  没有反馈数据，跳过")
                return result
            
            print(f"   ✅ 读取到 {len(feedback_data)} 条反馈")
            result["steps"]["read_feedback"] = {
                "status": "success",
                "count": len(feedback_data)
            }
            
            # 步骤 2: 读取当前 prompts（所有需要更新的）
            current_prompts = {}
            print(f"步骤 2: 读取当前 prompts: {', '.join(prompt_paths)}...")
            for prompt_type in prompt_paths:
                try:
                    current_prompts[prompt_type] = self.api_client.get_prompt(prompt_type)
                    print(f"   ✅ {prompt_type}: {len(current_prompts[prompt_type])} 字符")
                except Exception as e:
                    print(f"   ⚠️  {prompt_type}: 读取失败 - {e}")
                    current_prompts[prompt_type] = ""
            
            result["steps"]["read_prompts"] = {
                "status": "success",
                "count": len(current_prompts)
            }
            
            # 步骤 3: 读取用户侧写
            print(f"步骤 3: 读取用户侧写...")
            user_profile = self.profile_loader.load_profile()
            if user_profile:
                print(f"   ✅ 读取到用户侧写")
            else:
                print(f"   ℹ️  无用户侧写")
            result["steps"]["read_profile"] = {
                "status": "success",
                "has_profile": user_profile is not None
            }
            
            # 步骤 4: 分析反馈数据
            print(f"步骤 4: 分析反馈数据...")
            analyzer = FeedbackAnalyzer(feedback_type)
            analysis = analyzer.analyze(feedback_data)
            print(f"   ✅ 分析完成: {analysis.get('summary', '')[:100]}...")
            result["steps"]["analyze"] = {
                "status": "success",
                "summary": analysis.get("summary", "")[:200]
            }
            
            # 步骤 5-7: 【强制 LLM】为每个 prompt 生成并更新
            updated_prompts = []
            for prompt_type in prompt_paths:
                print(f"\n步骤 5-{len(updated_prompts)+1}: 【强制 LLM】生成 {prompt_type} prompt...")
                
                if dry_run:
                    print(f"   [DRY RUN] 预览模式 - 将调用 LLM 生成")
                    new_prompt = f"[DRY RUN - {prompt_type} prompt 将由 LLM 生成]"
                else:
                    # 【强制】调用 LLM 生成新 prompt - 不允许使用规则模板
                    # 如果 LLM 调用失败，会抛出异常导致整个流程失败
                    try:
                        new_prompt = self.prompt_generator.generate(
                            feedback_type=feedback_type,
                            prompt_type=prompt_type,  # 当前要生成的 prompt 类型
                            feedback_data=feedback_data,
                            analysis=analysis,
                            current_prompt=current_prompts.get(prompt_type, ""),
                            other_prompts={k: v for k, v in current_prompts.items() if k != prompt_type},
                            user_profile=user_profile
                        )
                        print(f"   ✅ {prompt_type} LLM 生成完成: {len(new_prompt)} 字符")
                    except RuntimeError as e:
                        print(f"   ✗ {prompt_type} LLM 生成失败: {e}")
                        raise  # 重新抛出，确保流程失败
                
                # 更新 prompt
                if not dry_run:
                    print(f"   更新 {prompt_type}...")
                    self.api_client.update_prompt(prompt_type, new_prompt)
                    print(f"   ✅ 已更新")
                
                updated_prompts.append(prompt_type)
            
            result["steps"]["generate_and_update"] = {
                "status": "success",
                "updated_prompts": updated_prompts
            }
            
            # 步骤 8: 归档反馈数据
            if not dry_run:
                print(f"\n步骤 8: 归档反馈数据...")
                self.api_client.archive_feedback(feedback_type)
                print(f"   ✅ 已归档")
                result["steps"]["archive_feedback"] = {"status": "success"}
            else:
                print(f"\n   [DRY RUN] 跳过归档")
            
            # 步骤 9: 通知完成
            if not dry_run:
                print(f"步骤 9: 通知 ClawMail 完成...")
                self.api_client.notify_completion(feedback_type, success=True)
                print(f"   ✅ 已通知")
                result["steps"]["notify"] = {"status": "success"}
            
            # 完成
            result["status"] = "success"
            result["message"] = f"{feedback_type} 个性化更新完成"
            
            print(f"\n{'='*60}")
            print(f"✅ {feedback_type} 个性化更新完成！")
            print(f"   - 处理了 {len(feedback_data)} 条反馈")
            print(f"   - 更新了 {len(updated_prompts)} 个 prompt: {', '.join(updated_prompts)}")
            print(f"{'='*60}\n")
            
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            result["errors"].append(str(e))
            print(f"\n❌ 错误: {e}")
            
            # 通知失败
            if not dry_run:
                try:
                    self.api_client.notify_completion(feedback_type, success=False, error=str(e))
                except:
                    pass
        
        return result


def main():
    parser = argparse.ArgumentParser(
        description="ClawMail Personalization Skill - 根据用户反馈自动优化 AI prompt"
    )
    parser.add_argument(
        "--trigger-message",
        "-m",
        help="ClawMail 触发消息"
    )
    parser.add_argument(
        "--trigger-file",
        "-f",
        help="包含触发消息的文件路径"
    )
    parser.add_argument(
        "--clawmail-api",
        default="http://127.0.0.1:9999",
        help="ClawMail HTTP API 地址（默认: http://127.0.0.1:9999）"
    )
    parser.add_argument(
        "--openclaw-url",
        default="http://127.0.0.1:18789",
        help="OpenClaw Gateway URL（默认: http://127.0.0.1:18789）"
    )
    parser.add_argument(
        "--model",
        default="kimi-k2.5",
        help="使用的模型（默认: kimi-k2.5）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，不实际执行更新"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="输出结果到 JSON 文件"
    )
    
    args = parser.parse_args()
    
    # 获取触发消息
    trigger_message = ""
    if args.trigger_file:
        with open(args.trigger_file, 'r', encoding='utf-8') as f:
            trigger_message = f.read()
    elif args.trigger_message:
        trigger_message = args.trigger_message
    else:
        # 从 stdin 读取
        import sys
        if not sys.stdin.isatty():
            trigger_message = sys.stdin.read()
    
    if not trigger_message:
        print("错误: 请提供触发消息（--trigger-message, --trigger-file 或 stdin）")
        return 1
    
    # 解析触发消息
    trigger_info = parse_trigger_message(trigger_message)
    
    # 验证
    is_valid, error_msg = validate_trigger_info(trigger_info)
    if not is_valid:
        print(f"错误: {error_msg}")
        print(f"解析结果: {json.dumps(trigger_info, ensure_ascii=False, indent=2)}")
        return 1
    
    print(f"解析触发消息:")
    print(f"  feedback_type: {trigger_info['feedback_type']}")
    print(f"  prompt_paths: {trigger_info.get('prompt_paths', [])}")
    
    # 执行
    skill = PersonalizationSkill(
        clawmail_api_url=args.clawmail_api,
        openclaw_url=args.openclaw_url,
        model=args.model
    )
    
    result = skill.run(trigger_info, dry_run=args.dry_run)
    
    # 输出结果
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到: {args.output}")
    
    # 打印 JSON 结果
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    return 0 if result["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
