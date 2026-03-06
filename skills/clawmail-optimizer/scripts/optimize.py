#!/usr/bin/env python3
"""clawmail-optimizer: 元 Skill，根据用户反馈自动优化其他 Skill 的 prompt 文件。

用法:
    python optimize.py --prompt-type email_generation --account-id <id>
    python optimize.py --prompt-type email_generation --account-id <id> --dry-run
"""

import argparse
import json
import logging
import re
import shutil
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# ── 常量 ──────────────────────────────────────────────────────────
CLAWMAIL_API = "http://127.0.0.1:9999"
LLM_API = "http://127.0.0.1:18789/v1/chat/completions"
MODEL = "kimi-k2.5"
LLM_TOKEN = ""

SKILL_DIR = Path(__file__).parent.parent
REFERENCES_DIR = SKILL_DIR / "references"
SKILLS_BASE = SKILL_DIR.parent  # skills/ 目录（git repo 内）
RUNTIME_SKILLS_BASE = Path.home() / ".openclaw" / "workspace" / "skills"

MIN_FEEDBACK_COUNT = 3       # 反馈条数不足时跳过
MAX_BACKUP_VERSIONS = 10     # 每个 prompt 最多保留备份数
RATE_LIMIT_HOURS = 24        # 同一 prompt-type 的最短优化间隔

logging.basicConfig(
    level=logging.INFO,
    format="[Optimizer] %(asctime)s %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ── prompt-type → 目标文件映射 ─────────────────────────────────────
PROMPT_TYPE_CONFIG = {
    "email_generation": {
        "feedback_type": "email_generation",
        "targets": [
            "clawmail-reply/references/prompts/reply_guide.md",
            "clawmail-reply/references/prompts/tone_styles.md",
        ],
        "analyzer": "email_generation",
    },
    "polish_email": {
        "feedback_type": "polish_email",
        "targets": [
            "clawmail-reply/references/prompts/polish_guide.md",
        ],
        "analyzer": "polish",
    },
    "importance_score": {
        "feedback_type": "importance_score",
        "targets": [
            "clawmail-analyzer/references/prompts/importance_algorithm.md",
        ],
        "analyzer": "importance",
    },
    "summary": {
        "feedback_type": "summary",
        "targets": [
            "clawmail-analyzer/references/prompts/summary_guide.md",
        ],
        "analyzer": "summary",
    },
}


# ── HTTP 工具 ─────────────────────────────────────────────────────

def _http_get(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post_json(url: str, data: dict, timeout: int = 30) -> dict:
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_get(path: str) -> dict:
    return _http_get(f"{CLAWMAIL_API}{path}")


def api_post(path: str, data: dict) -> dict:
    return _http_post_json(f"{CLAWMAIL_API}{path}", data)


def call_llm(system_prompt: str, user_prompt: str) -> str:
    logger.info("调用 LLM (model=%s)...", MODEL)
    data = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if LLM_TOKEN:
        headers["Authorization"] = f"Bearer {LLM_TOKEN}"
    req = urllib.request.Request(LLM_API, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    content = result["choices"][0]["message"]["content"]
    logger.info("LLM 返回 %d 字符", len(content))
    return content


def load_reference(subpath: str) -> str:
    path = REFERENCES_DIR / subpath
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("Reference 文件不存在: %s", path)
    return ""


def read_user_profile() -> str:
    user_md_path = Path.home() / ".openclaw" / "workspace" / "USER.md"
    if user_md_path.exists():
        return user_md_path.read_text(encoding="utf-8")
    return ""


# ── 分析器加载 ────────────────────────────────────────────────────

def get_analyzer(prompt_type: str):
    """动态加载对应的 analyzer 模块。"""
    analyzer_name = PROMPT_TYPE_CONFIG[prompt_type]["analyzer"]
    if analyzer_name == "email_generation":
        from analyzers.email_generation import analyze_feedback
    elif analyzer_name == "polish":
        from analyzers.polish import analyze_feedback
    elif analyzer_name == "importance":
        from analyzers.importance import analyze_feedback
    elif analyzer_name == "summary":
        from analyzers.summary import analyze_feedback
    else:
        raise ValueError(f"未知 analyzer: {analyzer_name}")
    return analyze_feedback


# ── 速率限制 ──────────────────────────────────────────────────────

def _rate_limit_file() -> Path:
    return SKILL_DIR / "scripts" / ".rate_limits.json"


def check_rate_limit(prompt_type: str) -> bool:
    """检查是否在冷却期内。返回 True 表示允许执行。"""
    rate_file = _rate_limit_file()
    if not rate_file.exists():
        return True
    try:
        limits = json.loads(rate_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return True
    last_run = limits.get(prompt_type)
    if not last_run:
        return True
    last_dt = datetime.fromisoformat(last_run)
    elapsed = (datetime.utcnow() - last_dt).total_seconds() / 3600
    if elapsed < RATE_LIMIT_HOURS:
        logger.info(
            "速率限制: %s 距上次优化仅 %.1f 小时（需 %d 小时）",
            prompt_type, elapsed, RATE_LIMIT_HOURS,
        )
        return False
    return True


def update_rate_limit(prompt_type: str) -> None:
    rate_file = _rate_limit_file()
    limits = {}
    if rate_file.exists():
        try:
            limits = json.loads(rate_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    limits[prompt_type] = datetime.utcnow().isoformat()
    rate_file.write_text(json.dumps(limits, indent=2), encoding="utf-8")


# ── 备份 / 恢复 ──────────────────────────────────────────────────

def backup_prompt(prompt_path: Path) -> Path | None:
    """备份 prompt 文件到 .backups/ 目录，返回备份路径。"""
    if not prompt_path.exists():
        return None
    backup_dir = prompt_path.parent / ".backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{prompt_path.stem}.{ts}{prompt_path.suffix}"
    shutil.copy2(str(prompt_path), str(backup_path))
    logger.info("备份: %s → %s", prompt_path.name, backup_path.name)
    _cleanup_old_backups(backup_dir, prompt_path.stem, prompt_path.suffix)
    return backup_path


def _cleanup_old_backups(backup_dir: Path, stem: str, suffix: str) -> None:
    """保留最近 N 个备份，删除更早的版本。"""
    pattern = f"{stem}.*{suffix}"
    backups = sorted(backup_dir.glob(pattern), key=lambda p: p.stat().st_mtime)
    while len(backups) > MAX_BACKUP_VERSIONS:
        old = backups.pop(0)
        old.unlink()
        logger.info("删除旧备份: %s", old.name)


# ── 结构验证 ──────────────────────────────────────────────────────

def validate_rewritten_prompt(original: str, rewritten: str) -> tuple[bool, str]:
    """验证 LLM 重写的 prompt 保留了原有结构。
    返回 (is_valid, error_message)。"""
    # 检查长度不低于原文的 30%
    if len(rewritten.strip()) < len(original.strip()) * 0.3:
        return False, f"重写后长度过短（{len(rewritten)} < 原文 {len(original)} 的 30%）"

    # 提取原文中所有 ## 标题
    original_headers = set(re.findall(r"^##\s+.+$", original, re.MULTILINE))
    rewritten_headers = set(re.findall(r"^##\s+.+$", rewritten, re.MULTILINE))

    missing = original_headers - rewritten_headers
    if missing:
        return False, f"缺失 section headers: {missing}"

    return True, ""


# ── 写入 prompt ───────────────────────────────────────────────────

def write_prompt(target_rel: str, content: str) -> None:
    """写入 prompt 到 git repo 和 runtime 两个位置。"""
    # git repo 路径
    repo_path = SKILLS_BASE / target_rel
    repo_path.parent.mkdir(parents=True, exist_ok=True)
    repo_path.write_text(content, encoding="utf-8")
    logger.info("写入 repo: %s", repo_path)

    # runtime 路径
    runtime_path = RUNTIME_SKILLS_BASE / target_rel
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(content, encoding="utf-8")
    logger.info("写入 runtime: %s", runtime_path)


# ── 主流程 ────────────────────────────────────────────────────────

def optimize(prompt_type: str, account_id: str, dry_run: bool = False) -> dict:
    """执行一次优化。返回结果摘要 dict。"""
    config = PROMPT_TYPE_CONFIG[prompt_type]
    result = {
        "prompt_type": prompt_type,
        "targets": config["targets"],
        "status": "skipped",
        "details": [],
    }

    # ── Step 0: 速率限制检查 ──
    if not dry_run and not check_rate_limit(prompt_type):
        result["status"] = "rate_limited"
        return result

    # ── Step 1: 获取反馈数据 ──
    logger.info("获取反馈数据: %s", config["feedback_type"])
    feedback_resp = api_get(f"/personalization/feedback/{config['feedback_type']}")
    records = feedback_resp.get("records", [])
    count = feedback_resp.get("count", len(records))
    logger.info("反馈记录数: %d", count)

    if count < MIN_FEEDBACK_COUNT:
        logger.info("反馈不足 %d 条，跳过优化", MIN_FEEDBACK_COUNT)
        result["status"] = "insufficient_feedback"
        result["feedback_count"] = count
        return result

    # ── Step 2: 获取用户偏好和侧写 ──
    memories = {}
    if account_id:
        try:
            memories = api_get(f"/memories/{account_id}")
        except Exception as e:
            logger.warning("获取记忆失败: %s", e)
    user_profile = read_user_profile()

    # ── Step 3: 分析反馈模式（Python, 不调 LLM）──
    analyze_feedback = get_analyzer(prompt_type)
    patterns = analyze_feedback(records)
    if not patterns:
        logger.info("未发现有意义的反馈模式，跳过优化")
        result["status"] = "no_patterns"
        return result
    logger.info("发现 %d 个反馈模式", len(patterns))

    # ── Step 4: 对每个目标 prompt 文件执行 LLM 重写 ──
    optimizer_guide = load_reference("prompts/optimizer_guide.md")
    patterns_text = "\n".join(f"- {p}" for p in patterns)
    memory_text = _format_memories(memories)

    for target_rel in config["targets"]:
        target_detail = {"target": target_rel, "status": "skipped"}

        # 读取当前 prompt
        repo_path = SKILLS_BASE / target_rel
        if not repo_path.exists():
            logger.warning("目标 prompt 文件不存在: %s", repo_path)
            target_detail["status"] = "file_not_found"
            result["details"].append(target_detail)
            continue

        current_prompt = repo_path.read_text(encoding="utf-8")

        # 构建 LLM 输入
        system_prompt = optimizer_guide
        user_prompt = _build_rewrite_prompt(
            current_prompt, patterns_text, memory_text, user_profile, target_rel,
        )

        if dry_run:
            # dry-run: 调用 LLM 但不写文件
            rewritten = call_llm(system_prompt, user_prompt)
            rewritten = _strip_code_fences(rewritten)
            valid, err = validate_rewritten_prompt(current_prompt, rewritten)
            target_detail["status"] = "dry_run"
            target_detail["valid"] = valid
            if not valid:
                target_detail["validation_error"] = err
            target_detail["diff_preview"] = _simple_diff(current_prompt, rewritten)
            result["details"].append(target_detail)
            continue

        # 实际执行
        rewritten = call_llm(system_prompt, user_prompt)
        rewritten = _strip_code_fences(rewritten)

        # 验证
        valid, err = validate_rewritten_prompt(current_prompt, rewritten)
        if not valid:
            logger.error("结构验证失败: %s — %s", target_rel, err)
            target_detail["status"] = "validation_failed"
            target_detail["error"] = err
            result["details"].append(target_detail)
            continue

        # 备份
        backup_prompt(repo_path)
        runtime_path = RUNTIME_SKILLS_BASE / target_rel
        if runtime_path.exists():
            backup_prompt(runtime_path)

        # 写入
        write_prompt(target_rel, rewritten)
        target_detail["status"] = "updated"
        target_detail["diff_preview"] = _simple_diff(current_prompt, rewritten)
        result["details"].append(target_detail)

    # ── Step 5: 归档反馈 + 更新速率限制 ──
    any_updated = any(d["status"] == "updated" for d in result["details"])
    if any_updated and not dry_run:
        try:
            api_post("/personalization/archive-feedback", {
                "feedback_type": config["feedback_type"],
            })
            logger.info("反馈已归档")
        except Exception as e:
            logger.warning("归档反馈失败: %s", e)

        update_rate_limit(prompt_type)

        # 通知 UI
        try:
            api_post("/personalization/status", {
                "prompt_type": prompt_type,
                "success": True,
            })
        except Exception as e:
            logger.warning("通知 UI 失败: %s", e)

    result["status"] = "completed" if any_updated else "no_changes"
    result["feedback_count"] = count
    return result


# ── 记忆清洗 ──────────────────────────────────────────────────────

_CLEAN_SYSTEM_PROMPT = (
    "你是一个 JSON 输出机器。你的唯一任务是根据用户的指令返回一个 JSON 数组。"
    "不要输出任何分析过程、解释、Markdown 标记或其他文字。"
    "只输出一个合法的 JSON 数组，以 [ 开头，以 ] 结尾。"
)

_CLEAN_USER_PROMPT = """你是 ClawMail 的记忆清洗引擎。

以下是用户的全部 AI 偏好记忆。请分析这些记忆，执行清洗操作：

【全部记忆】
{memories_text}

【清洗规则】
1. **合并重复**：相同 memory_type + 相同/相似 memory_key 的多条记忆 → 合并为一条
   - 合并后 evidence_count = 各条之和
   - confidence = 取较高值
   - content 合并关键信息

2. **解决矛盾**：同一 key 但 content 含义矛盾的记忆
   - 保留 evidence_count 更高 / 更新鲜的那条
   - 删除另一条

3. **标注 skill_defect**：content 中 _source="skill_defect" 的记忆
   - 这些是 AI 算法/prompt 本身的问题，不是用户个性化偏好
   - 提取出来放到 defect_summary 中，方便后续优化 prompt

【输出要求】
返回 JSON 数组，每个元素是一个操作：
[
  {{"op": "merge", "keep_id": "保留的记忆ID", "delete_ids": ["被合并删除的ID"], "merged_content": {{}}, "merged_evidence": 5, "merged_confidence": 0.8}},
  {{"op": "delete", "memory_id": "要删除的ID", "reason": "矛盾/过时/无意义"}},
  {{"op": "flag_defect", "memory_id": "skill_defect记忆ID", "defect_type": "importance/summary/reply/category", "description": "缺陷描述"}}
]

如果不需要任何清洗操作，返回空数组：[]
直接返回 JSON 数组，不要 Markdown 标记或解释文字。"""


def clean_memories(account_id: str, dry_run: bool = False) -> dict:
    """清洗用户记忆：合并重复、解决矛盾、标注 skill_defect。"""
    result = {"status": "skipped", "operations": [], "defects": []}

    # 获取全部记忆
    memories_resp = api_get(f"/memories/{account_id}")
    entries = memories_resp.get("memories", [])
    if len(entries) < 5:
        logger.info("记忆不足 5 条，跳过清洗")
        result["status"] = "insufficient"
        result["memory_count"] = len(entries)
        return result

    # 格式化为 LLM 输入
    mem_lines = []
    for m in entries:
        mem_lines.append(
            f"[id={m.get('id', '?')}] type={m.get('memory_type')}, "
            f"key={m.get('memory_key')}, "
            f"evidence={m.get('evidence_count', 1)}, "
            f"confidence={m.get('confidence_score', 0):.2f}, "
            f"content={json.dumps(m.get('memory_content', {}), ensure_ascii=False)}, "
            f"updated={m.get('last_updated', '?')}"
        )
    memories_text = "\n".join(mem_lines)

    user_prompt = _CLEAN_USER_PROMPT.format(memories_text=memories_text)

    logger.info("调用 LLM 清洗 %d 条记忆...", len(entries))
    raw = call_llm(_CLEAN_SYSTEM_PROMPT, user_prompt)

    # 复用 learner 的 JSON 解析
    import re as _re
    text = raw.strip()
    text = _re.sub(r"^```(?:json)?\s*", "", text, flags=_re.IGNORECASE)
    text = _re.sub(r"\s*```\s*$", "", text)
    try:
        operations = json.loads(text)
        if not isinstance(operations, list):
            operations = []
    except (json.JSONDecodeError, ValueError):
        match = _re.search(r'\[.*\]', text, flags=_re.DOTALL)
        operations = json.loads(match.group()) if match else []

    if not operations:
        logger.info("LLM 判断无需清洗")
        result["status"] = "clean"
        return result

    logger.info("LLM 返回 %d 条清洗操作", len(operations))

    if dry_run:
        result["status"] = "dry_run"
        result["operations"] = operations
        return result

    # 执行清洗操作
    applied = 0
    defects = []
    for op in operations:
        if not isinstance(op, dict):
            continue
        action = op.get("op", "")
        try:
            if action == "merge":
                # 更新保留的记忆
                keep_id = op.get("keep_id")
                delete_ids = op.get("delete_ids", [])
                if keep_id and delete_ids:
                    api_post(f"/memories/{account_id}", {
                        "op": "update",
                        "memory_id": keep_id,
                        "content": op.get("merged_content", {}),
                        "confidence": op.get("merged_confidence", 0.7),
                    })
                    for did in delete_ids:
                        api_post(f"/memories/{account_id}", {
                            "op": "delete", "memory_id": did,
                        })
                    applied += 1
                    logger.info("MERGE: keep=%s, delete=%s", keep_id, delete_ids)

            elif action == "delete":
                mid = op.get("memory_id")
                if mid:
                    api_post(f"/memories/{account_id}", {
                        "op": "delete", "memory_id": mid,
                    })
                    applied += 1
                    logger.info("DELETE: %s reason=%s", mid, op.get("reason", ""))

            elif action == "flag_defect":
                defects.append({
                    "memory_id": op.get("memory_id"),
                    "defect_type": op.get("defect_type", "unknown"),
                    "description": op.get("description", ""),
                })
                logger.info("DEFECT: type=%s desc=%s",
                            op.get("defect_type"), op.get("description", "")[:50])

        except Exception as e:
            logger.warning("清洗操作失败 %s: %s", action, e)

    result["status"] = "completed"
    result["applied"] = applied
    result["defects"] = defects
    result["memory_count"] = len(entries)

    # 如果有 skill_defect，尝试触发对应 prompt-type 的优化
    if defects and not dry_run:
        _trigger_defect_optimization(defects, account_id)

    return result


def _trigger_defect_optimization(defects: list, account_id: str) -> None:
    """根据 skill_defect 类型触发对应的 prompt 优化。"""
    # defect_type → prompt_type 映射
    defect_to_prompt = {
        "importance": "importance_score",
        "summary": "summary",
        "reply": "email_generation",
        "category": "importance_score",  # 分类规则在 importance 算法中
    }
    triggered = set()
    for d in defects:
        pt = defect_to_prompt.get(d.get("defect_type", ""))
        if pt and pt not in triggered:
            triggered.add(pt)
            logger.info("Skill 缺陷触发优化: defect_type=%s → prompt_type=%s",
                        d.get("defect_type"), pt)
            try:
                optimize(pt, account_id, dry_run=False)
            except Exception as e:
                logger.warning("缺陷触发优化失败 %s: %s", pt, e)


# ── 辅助函数 ──────────────────────────────────────────────────────

def _format_memories(memories: dict) -> str:
    """将 MemoryBank 记忆格式化为文本。"""
    entries = memories.get("memories", [])
    if not entries:
        return ""
    lines = []
    for m in entries:
        mt = m.get("memory_type", "")
        key = m.get("memory_key", "")
        content = m.get("memory_content", "")
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        lines.append(f"[{mt}] {key}: {content}")
    return "\n".join(lines)


def _build_rewrite_prompt(
    current_prompt: str,
    patterns_text: str,
    memory_text: str,
    user_profile: str,
    target_rel: str,
) -> str:
    """构建发送给 LLM 的 user prompt。"""
    parts = [
        f"## 目标文件\n{target_rel}\n",
        f"## 当前 prompt 全文\n\n{current_prompt}\n",
        f"## 反馈模式摘要\n\n{patterns_text}\n",
    ]
    if memory_text:
        parts.append(f"## 用户偏好记忆\n\n{memory_text}\n")
    if user_profile:
        parts.append(f"## 用户侧写（USER.md）\n\n{user_profile}\n")
    parts.append(
        "请根据以上反馈模式，重写目标 prompt 文件。"
        "在 `## 用户习得偏好` 段落追加规则（如该段落不存在则创建）。"
        "输出完整的更新后 markdown 文件内容，不要用代码围栏包裹。"
    )
    return "\n".join(parts)


def _strip_code_fences(text: str) -> str:
    """去除 LLM 输出中可能包裹的代码围栏。"""
    text = text.strip()
    text = re.sub(r"^```(?:markdown|md)?\s*\n", "", text)
    text = re.sub(r"\n```\s*$", "", text)
    return text.strip()


def _simple_diff(original: str, rewritten: str) -> str:
    """生成简单的变更摘要（新增/删除的行）。"""
    import difflib
    orig_lines = original.splitlines(keepends=True)
    new_lines = rewritten.splitlines(keepends=True)
    diff = difflib.unified_diff(orig_lines, new_lines, fromfile="原版", tofile="更新版", n=2)
    return "".join(diff)


# ── CLI 入口 ──────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="clawmail-optimizer: 根据用户反馈自动优化 Skill prompt 文件 / 清洗记忆",
    )
    parser.add_argument(
        "--mode", choices=["optimize", "clean"], default="optimize",
        help="运行模式: optimize=优化prompt, clean=清洗记忆",
    )
    parser.add_argument(
        "--prompt-type",
        choices=list(PROMPT_TYPE_CONFIG.keys()),
        help="要优化的 prompt 类型（optimize 模式必填）",
    )
    parser.add_argument("--account-id", default="", help="账户 ID")
    parser.add_argument("--dry-run", action="store_true", help="只预览变更，不实际修改文件")
    parser.add_argument(
        "--clawmail-api", default="http://127.0.0.1:9999",
        help="ClawMail REST API 地址",
    )
    parser.add_argument(
        "--llm-api", default="http://127.0.0.1:18789/v1/chat/completions",
        help="LLM API 地址",
    )
    parser.add_argument("--model", default="kimi-k2.5", help="LLM 模型名称")
    parser.add_argument("--llm-token", default="", help="LLM 网关鉴权 token")
    global CLAWMAIL_API, LLM_API, MODEL, LLM_TOKEN, MIN_FEEDBACK_COUNT
    parser.add_argument(
        "--min-feedback", type=int, default=MIN_FEEDBACK_COUNT,
        help=f"最少反馈条数（默认 {MIN_FEEDBACK_COUNT}）",
    )
    args = parser.parse_args()

    CLAWMAIL_API = args.clawmail_api
    LLM_API = args.llm_api
    MODEL = args.model
    LLM_TOKEN = args.llm_token
    MIN_FEEDBACK_COUNT = args.min_feedback

    try:
        if args.mode == "clean":
            if not args.account_id:
                print(json.dumps({"status": "error", "error": "clean 模式需要 --account-id"}))
                sys.exit(1)
            result = clean_memories(args.account_id, dry_run=args.dry_run)
        else:
            if not args.prompt_type:
                print(json.dumps({"status": "error", "error": "optimize 模式需要 --prompt-type"}))
                sys.exit(1)
            result = optimize(args.prompt_type, args.account_id, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if result["status"] in ("completed", "clean", "dry_run", "no_changes") else 1)
    except Exception as e:
        logger.exception("执行失败")
        error_result = {
            "status": "error",
            "error": str(e),
        }
        print(json.dumps(error_result, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
