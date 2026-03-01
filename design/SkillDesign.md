# OpenClaw Skill 侧设计

本文档描述 Skill-Driven 迁移中需要创建/修改的所有 OpenClaw Skills。
配套文档：`ClawMailChanges.md`（ClawMail 侧改动）。

所有 Skill 位于 `~/.openclaw/workspace/skills/` 目录下。

---

## 触发方式：直接脚本调用

**关键原则：ClawMail 直接调用 skill 脚本，不经过 LLM 判断。**

Skill 脚本由 ClawMail 通过 `subprocess` 或 Python import 直接调用，不经过 OpenClaw gateway 的 LLM 路由。LLM 只在脚本内部被调用来回答具体问题，不决定执行哪个 skill、不决定执行流程。

```
ClawMail ai_processor.py
    → subprocess.run(["python", "analyze_email.py", "--email-id", id, ...])
        → 脚本读取 references/，拼 prompt
        → 脚本调 LLM API 获取结构化结果
        → 脚本调 ClawMail REST API 写回结果
    → ai_processor 从 DB 读取结果返回
```

这确保了：
- **确定性**：每个事件触发哪个脚本是代码写死的，不是 LLM 判断的
- **可靠性**：LLM 不能跳过 skill 或自作主张
- **可调试**：脚本可以单独运行测试

---

## 共享基础：ClawMail REST API

所有 Skill 通过 `http://127.0.0.1:9999` 与 ClawMail 交互。

| 端点 | 方法 | 用途 |
|------|------|------|
| `/emails/{id}` | GET | 获取邮件完整数据 |
| `/emails/{id}/ai-metadata` | GET | 获取已有 AI 分析结果 |
| `/emails/{id}/ai-metadata` | POST | 写入分析结果 |
| `/emails/unprocessed` | GET | 获取待分析邮件列表 |
| `/memories/{account_id}` | GET | 获取用户偏好记忆 |
| `/memories/{account_id}` | POST | 写入偏好记忆 |
| `/pending-facts/{account_id}` | GET | 获取 pending facts |
| `/pending-facts/{account_id}` | POST | 写入 pending fact |
| `/pending-facts/{account_id}/promote` | POST | 触发 pending fact 提升 |

### LLM 调用

所有 Skill 通过 OpenClaw Gateway 调用 LLM：
- **URL**: `http://127.0.0.1:18789/v1/chat/completions`
- **模型**: `kimi-k2.5`（可配置）
- **格式**: OpenAI 兼容 API
- **HTTP 库**: 使用 stdlib `urllib.request`，零外部依赖

```python
import json
import urllib.request

def _http_post_json(url: str, data: dict, timeout: int = 30) -> dict:
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def call_llm(system_prompt: str, user_prompt: str, model: str = "kimi-k2.5") -> str:
    result = _http_post_json("http://127.0.0.1:18789/v1/chat/completions", {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3
    }, timeout=120)
    return result["choices"][0]["message"]["content"]
```

---

## 1. clawmail-analyzer（已有，需重构）

### 位置

`~/.openclaw/workspace/skills/clawmail-analyzer/`

### 现状

- SKILL.md 已有完整接口定义
- references/ 有 11 个文档（field_definitions, importance_algorithm, summary_guide 等）
- scripts/analyze_email.py 是 stub（返回固定示例数据）

### 需要做的改动

#### 1.1 目录结构调整

现有 references/ 全部平铺，需要拆分为 prompts/ 和 specs/：

```
references/
├── prompts/                          ← 可被 personalization skill 演化
│   ├── importance_algorithm.md       （已有，移入）
│   ├── summary_guide.md              （已有，移入）
│   ├── category_rules.md             （从 field_definitions 中拆出，新建）
│   └── profile_extraction.md         （新建）
└── specs/                            ← 接口契约，不可修改
    ├── output_schema.md              （已有，移入）
    ├── field_definitions.md          （已有，移入）
    ├── error_codes.md                （已有，移入）
    └── memory_injection.md           （已有，移入）
```

可以保留的（不移动）：
- `integration_guide.md` — 集成指南（参考文档）
- `output_templates.md` — 输出模板（参考文档）
- `priority_criteria.md` — 优先级标准（并入 importance_algorithm）
- `task_detection.md` — 任务检测模式（并入 field_definitions 或保留）
- `feedback_system.md` — 反馈系统（迁移后由 executor/personalization 负责）

#### 1.2 新建 references/prompts/profile_extraction.md

事实性信息提取规则：

```markdown
# 事实性信息提取规则

## 提取目标

从邮件内容中提取关于用户（收件人）的事实性信息，用于构建用户侧写。

## 提取类别

### career（职业信息）
- 行业、公司名称、部门
- 职位、职级
- 工作职责和专业领域
- **fact_key 格式**: career.industry, career.company, career.position, career.department

### contact（联系人关系）
- 发件人与用户的关系（上司、同事、客户、朋友、家人）
- 频繁沟通的联系人
- 联系人的角色和职位
- **fact_key 格式**: contact.{email}.relationship, contact.{email}.role

### organization（组织结构）
- 用户所在团队/部门的结构
- 汇报关系
- 跨部门协作关系
- **fact_key 格式**: org.team, org.report_to, org.collaborate_with

### project（项目上下文）
- 当前参与的项目名称
- 项目角色（负责人、参与者、审批人）
- 项目状态和里程碑
- **fact_key 格式**: project.{name}.role, project.{name}.status

## 输出格式

```json
[
    {
        "fact_key": "career.position",
        "fact_category": "career",
        "fact_content": "软件工程师，专注后端开发",
        "confidence": 0.7
    }
]
```

## 置信度评估

- **0.9-1.0**: 邮件中有明确声明（如签名、自我介绍）
- **0.7-0.8**: 从上下文强烈暗示（如讨论技术架构 + 代码审查）
- **0.5-0.6**: 合理推断（如收到某类邮件较多）
- **0.3-0.4**: 弱信号（如 CC 列表中的位置）
- **<0.3**: 不要提取，信号太弱

## 注意事项

- 只提取关于**用户**（收件人）的信息，不是关于发件人的
- 如果无法提取任何有价值的信息，返回空数组 `[]`
- 不要重复提取已在 USER.md 中存在的信息
- 每封邮件最多提取 3 个 facts，优先提取置信度高的
```

#### 1.3 新建 references/prompts/category_rules.md

从现有 field_definitions.md 中拆出分类规则：

```markdown
# 邮件分类规则

## 固定分类标签

| 标签 | 触发条件 |
|------|---------|
| urgent | 包含紧急关键词或有今日截止的待办 |
| pending_reply | 邮件明确要求回复或确认 |
| notification | 系统通知、自动生成的邮件 |
| subscription | 订阅邮件、newsletter |
| meeting | 会议邀请、日程相关 |
| approval | 审批请求 |

## 动态分类

- `项目:XXX` — 当邮件与已知项目相关时添加
- 最多 4 个标签（含动态标签）

## 分类优先级

urgent > pending_reply > approval > meeting > 其他
```

#### 1.4 补全 scripts/analyze_email.py

从 stub 改为真正的实现。核心逻辑：

```python
#!/usr/bin/env python3
"""
analyze_email.py - 邮件分析主脚本

入口: python analyze_email.py --email-id <id> --account-id <id>
"""

import argparse
import json
import urllib.request
import urllib.error
from pathlib import Path

CLAWMAIL_API = "http://127.0.0.1:9999"
LLM_API = "http://127.0.0.1:18789/v1/chat/completions"
MODEL = "kimi-k2.5"

SKILL_DIR = Path(__file__).parent.parent
REFERENCES_DIR = SKILL_DIR / "references"

# ─── HTTP 工具 ───

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

def call_llm(system_prompt: str, user_prompt: str) -> str:
    result = _http_post_json(LLM_API, {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3
    }, timeout=120)
    return result["choices"][0]["message"]["content"]

def load_reference(subpath: str) -> str:
    path = REFERENCES_DIR / subpath
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""

def api_get(path: str) -> dict:
    return _http_get(f"{CLAWMAIL_API}{path}")

def api_post(path: str, data: dict) -> dict:
    return _http_post_json(f"{CLAWMAIL_API}{path}", data)

# ─── 邮件分析 ───

def analyze_email(email_id: str, account_id: str):
    """
    完整邮件分析流程（脚本控制，LLM 只回答问题）。
    """
    # Step 0: 获取数据
    email = api_get(f"/emails/{email_id}")
    memories = api_get(f"/memories/{account_id}")
    pending_facts = api_get(f"/pending-facts/{account_id}")

    # 读取 USER.md（OpenClaw 自动注入，这里也可以主动读）
    user_md_path = Path.home() / ".openclaw" / "workspace" / "USER.md"
    user_profile = user_md_path.read_text(encoding="utf-8") if user_md_path.exists() else ""

    # Step 1: 摘要 + 分类 + 评分 + 行动项（一次 LLM 调用）
    analysis_system = build_analysis_system_prompt(user_profile, memories)
    analysis_user = build_analysis_user_prompt(email)
    analysis_raw = call_llm(analysis_system, analysis_user)
    analysis = parse_analysis_json(analysis_raw)

    # Step 2: 事实提取（独立 LLM 调用）
    extraction_system = build_extraction_system_prompt(user_profile, pending_facts)
    extraction_user = build_extraction_user_prompt(email)
    facts_raw = call_llm(extraction_system, extraction_user)
    facts = parse_facts_json(facts_raw)

    # Step 3: 写回结果
    api_post(f"/emails/{email_id}/ai-metadata", analysis)

    if facts:
        api_post(f"/pending-facts/{account_id}", {"facts": facts})
        api_post(f"/pending-facts/{account_id}/promote")

    return {"status": "success", "email_id": email_id}

# ─── Prompt 构建 ───

def build_analysis_system_prompt(user_profile: str, memories: dict) -> str:
    """构建邮件分析的 system prompt。"""
    # 加载基准线 reference 文档
    summary_guide = load_reference("prompts/summary_guide.md")
    importance_algo = load_reference("prompts/importance_algorithm.md")
    category_rules = load_reference("prompts/category_rules.md")
    field_defs = load_reference("specs/field_definitions.md")
    output_schema = load_reference("specs/output_schema.md")

    # 构建记忆注入段
    memory_section = format_memories(memories)

    return f"""你是一个邮件分析助手。请严格按照以下规则分析邮件。

## 用户侧写
{user_profile}

## 用户偏好记忆
{memory_section}

## 摘要规则
{summary_guide}

## 重要性评分算法
{importance_algo}

## 分类规则
{category_rules}

## 输出字段定义
{field_defs}

## 输出格式
请严格输出 JSON，格式如下：
{output_schema}

不要输出任何 JSON 之外的内容。"""

def build_analysis_user_prompt(email: dict) -> str:
    """构建邮件分析的 user prompt。"""
    body = email.get("body_text", "")[:4000]
    return f"""请分析以下邮件：

主题: {email.get('subject', '')}
发件人: {json.dumps(email.get('from_address', {}), ensure_ascii=False)}
收件人: {json.dumps(email.get('to_addresses', []), ensure_ascii=False)}
抄送: {json.dumps(email.get('cc_addresses', []), ensure_ascii=False)}
时间: {email.get('received_at', '')}
正文:
{body}"""

def build_extraction_system_prompt(user_profile: str, pending_facts: dict) -> str:
    """构建事实提取的 system prompt。"""
    extraction_rules = load_reference("prompts/profile_extraction.md")
    existing_facts = json.dumps(pending_facts.get("facts", []), ensure_ascii=False, indent=2)

    return f"""你是一个用户信息提取助手。从邮件中提取关于收件人（用户）的事实性信息。

## 提取规则
{extraction_rules}

## 用户当前侧写
{user_profile}

## 已有的 pending facts（避免重复）
{existing_facts}

请输出 JSON 数组，格式为：
[{{"fact_key": "...", "fact_category": "...", "fact_content": "...", "confidence": 0.0}}]

如果没有可提取的信息，输出空数组 []。
不要输出任何 JSON 之外的内容。"""

def build_extraction_user_prompt(email: dict) -> str:
    """同 analysis user prompt。"""
    return build_analysis_user_prompt(email)

# ─── 解析工具函数 ───

def format_memories(memories: dict) -> str:
    """将 memories API 返回值格式化为 prompt 段落。"""
    items = memories.get("memories", [])
    if not items:
        return "（无历史记忆）"
    lines = []
    for m in items:
        content = m.get("memory_content", {})
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        key = m.get("memory_key", "全局")
        lines.append(f"- [{m.get('memory_type', '?')}] {key}: {content}")
    return "\n".join(lines)

def parse_analysis_json(raw: str) -> dict:
    """从 LLM 输出中解析分析结果 JSON。"""
    # 尝试提取 JSON 块
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试找到 JSON 对象
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise

def parse_facts_json(raw: str) -> list:
    """从 LLM 输出中解析 facts JSON 数组。"""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        return []
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        return []

# ─── CLI ───

def main():
    parser = argparse.ArgumentParser(description="ClawMail Analyzer Skill")
    parser.add_argument("--email-id", required=True, help="邮件ID")
    parser.add_argument("--account-id", required=True, help="账户ID")
    parser.add_argument("--clawmail-api", default="http://127.0.0.1:9999")
    parser.add_argument("--llm-api", default="http://127.0.0.1:18789/v1/chat/completions")
    parser.add_argument("--model", default="kimi-k2.5")
    args = parser.parse_args()

    global CLAWMAIL_API, LLM_API, MODEL
    CLAWMAIL_API = args.clawmail_api
    LLM_API = args.llm_api
    MODEL = args.model

    result = analyze_email(args.email_id, args.account_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

#### 1.5 更新 SKILL.md

更新现有 SKILL.md，反映新的目录结构和 pending facts 输出：
- 输出新增：pending facts（除了原有的 ai-metadata）
- 依赖新增：`/pending-facts/*` API 端点

---

## 2. clawmail-reply（新建）

### 位置

`~/.openclaw/workspace/skills/clawmail-reply/`

### 目录结构

```
clawmail-reply/
├── SKILL.md
├── references/
│   ├── prompts/
│   │   ├── reply_guide.md          — 回复生成规则
│   │   ├── generate_email_guide.md — 新邮件生成规则
│   │   ├── polish_guide.md         — 润色规则
│   │   ├── tone_styles.md          — 语气风格定义
│   │   └── habit_extraction.md     — 用户撰写习惯提取规则
│   └── specs/
│       └── output_format.md        — 输出格式规范
└── scripts/
    ├── __init__.py
    ├── generate_reply.py           — 回复生成入口
    ├── generate_email.py           — 新邮件生成入口
    ├── polish_email.py             — 润色入口
    └── extract_habits.py           — 用户撰写习惯提取
```

### SKILL.md

```markdown
# ClawMail Reply Skill

邮件回复、撰写、润色、习惯提取。由 ClawMail 通过 subprocess 直接调用。

## 触发方式

**ClawMail 直接调用脚本，不经过 LLM 路由。**

### 1. 回复草稿生成

python scripts/generate_reply.py \
  --email-id <id> --stance "确认收到" --tone "礼貌" --account-id <id>

### 2. 新邮件生成

python scripts/generate_email.py \
  --subject "主题" --outline "大纲" --tone "正式" --account-id <id>

### 3. 邮件润色

python scripts/polish_email.py \
  --body "原始内容" --tone "礼貌" --account-id <id>

### 4. 用户撰写习惯提取

用户发送邮件/回复后触发，提取写作习惯和沟通风格到 pending facts。

python scripts/extract_habits.py \
  --compose-data '{"subject": "...", "to": "...", "body": "...", "is_reply": true}' \
  --account-id <id>

## 输出

- **回复/生成/润色**（1-3）：纯文本邮件内容，直接 print 到 stdout。
- **习惯提取**（4）：JSON 状态输出到 stdout，实际数据通过 REST API 写入 pending facts。

## REST API 依赖

| 端点 | 方法 | 用途 | 被谁调用 |
|------|------|------|---------|
| `/emails/{id}` | GET | 获取原始邮件 | generate_reply |
| `/emails/{id}/ai-metadata` | GET | 获取分析结果 | generate_reply |
| `/memories/{account_id}` | GET | 获取用户偏好记忆 | 全部 |
| `/pending-facts/{account_id}` | GET | 获取已有 pending facts | extract_habits |
| `/pending-facts/{account_id}` | POST | 写入新 pending facts | extract_habits |
| `/pending-facts/{account_id}/promote` | POST | 触发提升检查 | extract_habits |
```

### references/prompts/reply_guide.md

```markdown
# 回复生成规则

## 输入
- 原始邮件（主题、正文、发件人）
- 用户选择的立场（stance）：从 reply_stances 中选择的一个
- 语气风格（tone）：正式/礼貌/轻松/简短
- 用户补充说明（user_notes）：可选

## 生成要求

1. **忠于立场**: 严格按照用户选择的 stance 生成回复
2. **参考原文**: 回复内容必须与原邮件相关，回应关键点
3. **语气一致**: 按 tone_styles.md 中的定义控制语气
4. **长度控制**: 按 tone 对应的字数范围
5. **自然流畅**: 不要机械翻译，要像真人写的

## 结构

- 问候语（可选，根据 tone）
- 核心回复（1-3 段）
- 结束语（可选，根据 tone）
- 不含签名

## 禁止

- 不要编造原邮件中没有的信息
- 不要添加用户没有要求的承诺
- 不要使用 AI 常见的过度礼貌表达
```

### references/prompts/tone_styles.md

```markdown
# 语气风格定义

| 风格 | 字数范围 | 特征 |
|------|---------|------|
| 正式 | 150-250字 | 完整称呼、正式用语、完整段落、礼貌结尾 |
| 礼貌 | 100-200字 | 称呼 + 正文 + 简短结尾，用语得体但不过度正式 |
| 轻松 | 50-100字 | 简短称呼或无称呼，口语化表达，可用感叹号 |
| 简短 | 30-80字 | 直奔主题，无称呼无结尾，只说关键内容 |
```

### references/prompts/polish_guide.md

```markdown
# 邮件润色规则

## 输入
- 用户已写的邮件原文
- 目标语气（tone）

## 润色要求

1. **保留原意**: 不改变邮件的核心意思和信息
2. **语言润色**: 修正语法错误、改善表达、提升可读性
3. **风格调整**: 按目标 tone 调整语气
4. **长度保持**: 润色后长度与原文相近（±20%）
5. **语言保持**: 原文是中文就输出中文，英文就输出英文

## 禁止

- 不要添加原文没有的信息
- 不要改变邮件的立场或态度（除非 tone 要求）
- 不要添加过度修饰
```

### scripts/generate_reply.py

```python
#!/usr/bin/env python3
"""回复草稿生成。"""

import argparse
import json
import urllib.request
from pathlib import Path

CLAWMAIL_API = "http://127.0.0.1:9999"
LLM_API = "http://127.0.0.1:18789/v1/chat/completions"
MODEL = "kimi-k2.5"
REFERENCES_DIR = Path(__file__).parent.parent / "references"

# HTTP 工具函数同 analyze_email.py（_http_get, _http_post_json, call_llm）
# ...省略...

def generate_reply(email_id: str, stance: str, tone: str,
                   user_notes: str = "", account_id: str = "") -> str:
    email = _http_get(f"{CLAWMAIL_API}/emails/{email_id}")
    ai_meta = _http_get(f"{CLAWMAIL_API}/emails/{email_id}/ai-metadata")
    memories = _http_get(f"{CLAWMAIL_API}/memories/{account_id}")

    # 读取 USER.md
    user_md_path = Path.home() / ".openclaw" / "workspace" / "USER.md"
    user_profile = user_md_path.read_text(encoding="utf-8") if user_md_path.exists() else ""

    # 加载 references
    reply_guide = load_reference("prompts/reply_guide.md")
    tone_styles = load_reference("prompts/tone_styles.md")

    # 构建 prompt
    memory_text = format_memories(memories)

    system_prompt = f"""你是一个邮件回复助手。请根据以下规则生成回复草稿。

## 用户侧写
{user_profile}

## 用户偏好记忆
{memory_text}

## 回复规则
{reply_guide}

## 语气风格
{tone_styles}

请直接输出回复内容（纯文本），不要输出 JSON，不要添加标题或标签。"""

    body = email.get("body_text", "")[:4000]
    user_prompt = f"""原始邮件：
主题: {email.get('subject', '')}
发件人: {json.dumps(email.get('from_address', {}), ensure_ascii=False)}
正文:
{body}

---
用户选择的回复立场: {stance}
目标语气: {tone}"""
    if user_notes:
        user_prompt += f"\n用户补充说明: {user_notes}"

    return call_llm(system_prompt, user_prompt)

def format_memories(memories: dict) -> str:
    items = memories.get("memories", [])
    if not items:
        return "（无历史记忆）"
    lines = []
    for m in items:
        content = m.get("memory_content", {})
        if isinstance(content, dict):
            content = json.dumps(content, ensure_ascii=False)
        lines.append(f"- [{m.get('memory_type')}] {m.get('memory_key', '全局')}: {content}")
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email-id", required=True)
    parser.add_argument("--stance", required=True)
    parser.add_argument("--tone", required=True)
    parser.add_argument("--user-notes", default="")
    parser.add_argument("--account-id", default="")
    args = parser.parse_args()

    result = generate_reply(args.email_id, args.stance, args.tone,
                           args.user_notes, args.account_id)
    print(result)

if __name__ == "__main__":
    main()
```

### scripts/generate_email.py 和 scripts/polish_email.py

结构与 generate_reply.py 类似，区别：
- `generate_email.py`：输入是 subject + outline + tone，不需要读取原始邮件
- `polish_email.py`：输入是 body + tone，直接润色
- `extract_habits.py`：输入是 compose-data JSON + account-id，读取 pending facts 和 USER.md，调 LLM 提取习惯，通过 REST API 写入 pending facts

---

## 3. clawmail-executor（新建）

### 位置

`~/.openclaw/workspace/skills/clawmail-executor/`

### 目录结构

```
clawmail-executor/
├── SKILL.md
├── references/
│   ├── prompts/
│   │   ├── memory_extraction_guide.md  — 偏好提取规则
│   │   └── memory_types.md             — 记忆类型定义
│   └── specs/
│       └── memory_schema.md            — 记忆输出格式
└── scripts/
    ├── __init__.py
    └── extract_preference.py           — 偏好提取入口
```

### SKILL.md

```markdown
# ClawMail Executor Skill

分析用户对 AI 预测的修正，提取偏好记忆并写入 ClawMail MemoryBank。

## 触发方式

消息格式: `(ClawMail)用户修正 type:{feedback_type} email_id:{id} account:{account_id}`
附带数据: 原始预测 + 用户修正

## 支持的修正类型

| feedback_type | 说明 | 输入数据 |
|--------------|------|---------|
| importance_score | 用户修改重要性评分 | original_score, user_score |
| summary_rating | 用户给摘要评分(差评) | summary, rating, comment |
| reply_edit | 用户编辑 AI 回复草稿 | ai_draft, user_edited, similarity |
| category_change | 用户修改分类 | original_categories, user_categories |

## 输出

通过 POST /memories/{account_id} 写入 MemoryBank。
不需要返回值给调用方。

## 依赖

- ClawMail REST API: `/emails/{id}`, `/memories/{account_id}`
- OpenClaw Gateway LLM API
```

### references/prompts/memory_extraction_guide.md

```markdown
# 偏好提取规则

## 目标

分析用户对 AI 预测的修正行为，推断用户的真实偏好，生成记忆条目。

## 分析框架

### importance_score 修正
- 对比 original_score 和 user_score
- 考虑邮件的发件人、主题、类型
- 推断：用户觉得该类邮件应该更重要/不重要
- 记忆粒度：sender 级别 > domain 级别 > 全局

### summary_rating 差评
- 分析用户评价（太长/太短/遗漏重点/语气不对）
- 推断：用户偏好的摘要风格
- 记忆粒度：全局（摘要偏好通常是全局的）

### reply_edit 编辑
- 对比 AI 草稿和用户编辑版本
- 分析差异：语气变化、长度变化、内容增删
- 推断：用户的回复风格偏好
- 记忆粒度：sender 级别（对不同人可能不同）> 全局

## 输出格式

```json
{
    "memory_type": "email_analysis",
    "memory_key": "sender@example.com",
    "memory_content": {
        "preference": "该发件人邮件的重要性应评为70+，因为是直属上司",
        "source_type": "importance_correction",
        "original_value": 45,
        "corrected_value": 80
    },
    "confidence_score": 0.85,
    "evidence_count": 1
}
```

## 注意事项

- 单次修正的 confidence 上限为 0.85（不是绝对确定）
- 如果已有同 key 的记忆，evidence_count 应 +1，confidence 应提升
- 避免过度泛化：用户修改一封邮件的评分，不代表所有邮件都要改
```

### references/prompts/memory_types.md

```markdown
# 记忆类型定义

## memory_type 取值

| memory_type | 说明 | 典型 memory_key |
|-------------|------|----------------|
| email_analysis | 邮件分析偏好 | sender_email / domain / null(全局) |
| reply_draft | 回复生成偏好 | sender_email / null(全局) |
| importance | 重要性判断偏好 | sender_email / domain / category |
| summary_style | 摘要风格偏好 | null(全局) |
| category_preference | 分类偏好 | null(全局) |

## memory_content 结构

灵活 JSON，但必须包含：
- `preference`: 文本描述，LLM 可直接理解的偏好说明
- `source_type`: 来源类型（importance_correction / summary_rating / reply_edit / category_change）
```

### scripts/extract_preference.py

```python
#!/usr/bin/env python3
"""用户偏好提取 — 分析用户修正并写入 MemoryBank。"""

import argparse
import json
import urllib.request
from pathlib import Path

CLAWMAIL_API = "http://127.0.0.1:9999"
LLM_API = "http://127.0.0.1:18789/v1/chat/completions"
MODEL = "kimi-k2.5"
REFERENCES_DIR = Path(__file__).parent.parent / "references"

# HTTP 工具函数同 analyze_email.py（_http_get, _http_post_json, call_llm）
# ...省略...

def extract_preference(feedback_type: str, feedback_data: dict,
                       email_id: str, account_id: str):
    """
    分析用户修正，提取偏好，写入 MemoryBank。
    """
    email = _http_get(f"{CLAWMAIL_API}/emails/{email_id}")
    memories = _http_get(f"{CLAWMAIL_API}/memories/{account_id}")

    # 加载 references
    extraction_guide = load_reference("prompts/memory_extraction_guide.md")
    memory_types = load_reference("prompts/memory_types.md")

    system_prompt = f"""你是一个用户偏好分析助手。分析用户对 AI 预测的修正行为，提取偏好记忆。

## 提取规则
{extraction_guide}

## 记忆类型定义
{memory_types}

## 已有记忆（参考，避免重复）
{json.dumps(memories.get('memories', [])[:10], ensure_ascii=False, indent=2)}

请输出一个 JSON 对象，格式为：
{{"memory_type": "...", "memory_key": "...", "memory_content": {{...}}, "confidence_score": 0.0, "evidence_count": 1}}

如果这次修正没有明确的偏好信号，输出 {{"skip": true, "reason": "..."}}。
不要输出任何 JSON 之外的内容。"""

    sender_email = email.get("from_address", {}).get("email", "unknown")
    user_prompt = f"""用户修正类型: {feedback_type}

邮件信息:
- 主题: {email.get('subject', '')}
- 发件人: {sender_email}
- 分类: {email.get('categories', [])}

修正数据:
{json.dumps(feedback_data, ensure_ascii=False, indent=2)}"""

    raw = call_llm(system_prompt, user_prompt)

    # 解析结果
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    result = json.loads(text)

    if result.get("skip"):
        return {"status": "skipped", "reason": result["reason"]}

    # 写入 MemoryBank
    _http_post_json(f"{CLAWMAIL_API}/memories/{account_id}", result)

    return {"status": "success", "memory": result}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--feedback-type", required=True)
    parser.add_argument("--feedback-data", required=True, help="JSON string")
    parser.add_argument("--email-id", required=True)
    parser.add_argument("--account-id", required=True)
    args = parser.parse_args()

    data = json.loads(args.feedback_data)
    result = extract_preference(args.feedback_type, data, args.email_id, args.account_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

---

## 4. clawmail-personalization（已有，扩展）

### 位置

`~/.openclaw/workspace/skills/clawmail-personalization/`

### 现状

已能根据用户反馈优化 `~/clawmail_data/prompts/*.txt`。

### 需要改动

迁移完成后，personalization skill 的优化目标从 `~/clawmail_data/prompts/*.txt` 改为各 skill 的 `references/prompts/*.md`。

#### 改动点

1. **SKILL.md 更新**：`prompt_paths` 改为指向 skill references 路径
2. **scripts/main.py 更新**：读写路径从 `~/clawmail_data/prompts/` 改为 `~/.openclaw/workspace/skills/{skill}/references/prompts/`

#### 路径映射

| 旧路径 (prompts/*.txt) | 新路径 (skill references) |
|------------------------|--------------------------|
| `importance_score.txt` | `clawmail-analyzer/references/prompts/importance_algorithm.md` |
| `summary.txt` | `clawmail-analyzer/references/prompts/summary_guide.md` |
| `category.txt` | `clawmail-analyzer/references/prompts/category_rules.md` |
| `is_spam.txt` | `clawmail-analyzer/references/prompts/spam_rules.md`（新建）|
| `reply_draft.txt` | `clawmail-reply/references/prompts/reply_guide.md` |
| `generate_email.txt` | `clawmail-reply/references/prompts/generate_email_guide.md` |
| `polish_email.txt` | `clawmail-reply/references/prompts/polish_guide.md` |

**注意**：这个改动可以在 Phase 3 做，不阻塞 Phase 1-2。

---

## 实现顺序

### Phase 1: clawmail-analyzer
1. 重组 references/ 目录（prompts/ vs specs/）
2. 新建 profile_extraction.md, category_rules.md
3. 补全 analyze_email.py（真正调 LLM，2 次调用）
4. 测试：手动运行 → 确认 JSON 输出 → 确认 API 写入

### Phase 2: clawmail-reply
1. 创建完整目录结构
2. 编写 SKILL.md + references（含 habit_extraction.md）
3. 实现 generate_reply.py, generate_email.py, polish_email.py, extract_habits.py
4. 测试

### Phase 3: clawmail-executor + personalization 更新
1. 创建 clawmail-executor 完整目录结构
2. 实现 extract_preference.py
3. 更新 clawmail-personalization 的路径映射
4. 测试完整闭环

---

## 接口契约摘要

供 ClawMail 侧参考的完整 API 调用模式：

```
Analyzer Skill 调用链:
  GET  /emails/{id}                    → 获取邮件
  GET  /memories/{account_id}          → 获取记忆
  GET  /pending-facts/{account_id}     → 获取已有 pending facts
  POST /emails/{id}/ai-metadata        → 写入分析结果
  POST /pending-facts/{account_id}     → 写入新 pending facts
  POST /pending-facts/{account_id}/promote → 触发提升

Reply Skill 调用链（回复/生成/润色）:
  GET  /emails/{id}                    → 获取原始邮件
  GET  /emails/{id}/ai-metadata        → 获取分析结果（reply_stances 等）
  GET  /memories/{account_id}          → 获取记忆
  （不写入，直接返回文本结果）

Reply Skill 调用链（习惯提取 extract_habits.py）:
  GET  /pending-facts/{account_id}     → 获取已有 pending facts
  POST /pending-facts/{account_id}     → 写入新 pending facts
  POST /pending-facts/{account_id}/promote → 触发提升

Executor Skill 调用链:
  GET  /emails/{id}                    → 获取邮件上下文
  GET  /memories/{account_id}          → 获取已有记忆
  POST /memories/{account_id}          → 写入新记忆
```
