#!/usr/bin/env python3
"""回滚 prompt 文件到之前的备份版本。

用法:
    python rollback.py --prompt-type email_generation --target reply_guide.md --version latest
    python rollback.py --prompt-type email_generation --target reply_guide.md --list
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

SKILLS_BASE = Path(__file__).parent.parent.parent  # skills/ 目录
RUNTIME_SKILLS_BASE = Path.home() / ".openclaw" / "workspace" / "skills"

# 与 optimize.py 保持一致的映射
PROMPT_TYPE_CONFIG = {
    "email_generation": {
        "targets": [
            "clawmail-reply/references/prompts/reply_guide.md",
            "clawmail-reply/references/prompts/tone_styles.md",
        ],
    },
    "polish_email": {
        "targets": [
            "clawmail-reply/references/prompts/polish_guide.md",
        ],
    },
    "importance_score": {
        "targets": [
            "clawmail-analyzer/references/prompts/importance_algorithm.md",
        ],
    },
    "summary": {
        "targets": [
            "clawmail-analyzer/references/prompts/summary_guide.md",
        ],
    },
}


def find_backups(target_rel: str) -> list[Path]:
    """查找指定目标文件的所有备份，按时间降序排列。"""
    repo_path = SKILLS_BASE / target_rel
    backup_dir = repo_path.parent / ".backups"
    if not backup_dir.exists():
        return []
    stem = repo_path.stem
    suffix = repo_path.suffix
    backups = sorted(
        backup_dir.glob(f"{stem}.*{suffix}"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return backups


def list_backups(prompt_type: str, target_name: str | None) -> None:
    """列出所有备份版本。"""
    config = PROMPT_TYPE_CONFIG[prompt_type]
    for target_rel in config["targets"]:
        filename = Path(target_rel).name
        if target_name and filename != target_name:
            continue
        backups = find_backups(target_rel)
        print(f"\n{target_rel}:")
        if not backups:
            print("  (无备份)")
            continue
        for i, bp in enumerate(backups):
            size = bp.stat().st_size
            mtime = bp.stat().st_mtime
            from datetime import datetime
            ts = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            label = "（最新）" if i == 0 else ""
            print(f"  [{i}] {bp.name}  ({size} bytes, {ts}){label}")


def rollback(prompt_type: str, target_name: str, version: str) -> dict:
    """回滚指定文件到备份版本。"""
    config = PROMPT_TYPE_CONFIG[prompt_type]
    target_rel = None
    for t in config["targets"]:
        if Path(t).name == target_name:
            target_rel = t
            break
    if not target_rel:
        return {"success": False, "error": f"目标文件 {target_name} 不在 {prompt_type} 的映射中"}

    backups = find_backups(target_rel)
    if not backups:
        return {"success": False, "error": f"无可用备份: {target_rel}"}

    # 解析版本
    if version == "latest":
        backup_path = backups[0]
    else:
        try:
            idx = int(version)
            if idx < 0 or idx >= len(backups):
                return {"success": False, "error": f"版本索引 {idx} 超出范围 (0-{len(backups)-1})"}
            backup_path = backups[idx]
        except ValueError:
            # 尝试按文件名匹配
            matched = [b for b in backups if version in b.name]
            if not matched:
                return {"success": False, "error": f"未找到匹配版本: {version}"}
            backup_path = matched[0]

    content = backup_path.read_text(encoding="utf-8")

    # 写回 repo
    repo_path = SKILLS_BASE / target_rel
    repo_path.write_text(content, encoding="utf-8")

    # 写回 runtime
    runtime_path = RUNTIME_SKILLS_BASE / target_rel
    if runtime_path.parent.exists():
        runtime_path.write_text(content, encoding="utf-8")

    return {
        "success": True,
        "target": target_rel,
        "restored_from": backup_path.name,
        "content_length": len(content),
    }


def main():
    parser = argparse.ArgumentParser(description="回滚 prompt 文件到备份版本")
    parser.add_argument(
        "--prompt-type", required=True,
        choices=list(PROMPT_TYPE_CONFIG.keys()),
        help="prompt 类型",
    )
    parser.add_argument("--target", default=None, help="目标文件名（如 reply_guide.md）")
    parser.add_argument("--version", default="latest", help="版本: latest / 索引号 / 文件名片段")
    parser.add_argument("--list", action="store_true", help="列出所有备份版本")
    args = parser.parse_args()

    if args.list:
        list_backups(args.prompt_type, args.target)
        sys.exit(0)

    if not args.target:
        print("错误: 非 --list 模式需要 --target 参数", file=sys.stderr)
        sys.exit(1)

    result = rollback(args.prompt_type, args.target, args.version)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
