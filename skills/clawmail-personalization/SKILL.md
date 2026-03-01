# ClawMail Personalization Skill

通过分析用户对邮件 AI 各项功能的反馈，自动优化对应的 prompt，实现个性化闭环。

---

## 支持的反馈类型

本 Skill 支持 **8 种反馈类型**的个性化优化：

| 反馈类型 | 说明 | Prompt 文件 | 关联说明 |
|----------|------|-------------|----------|
| `importance_score` | 邮件重要性评分 | `importance_score.txt` | — |
| `category` | 邮件分类标签 | `category.txt` | — |
| `is_spam` | 垃圾邮件检测 | `is_spam.txt` | — |
| `action_category` | 行动项分类 | `action_category.txt` | — |
| `reply_stances` | 回复立场建议 | `reply_stances.txt` | — |
| `summary` | 邮件摘要质量（含关键词提取） | `summary.txt` | 关键词提取已合并到摘要 |
| `email_generation` | 邮件生成（回复草稿 + 写新邮件） | `reply_draft.txt` + `generate_email.txt` | 同时更新两个 prompt |
| `polish_email` | 邮件润色 | `polish_email.txt` | — |

**注意**：
- `keywords` 不再作为独立反馈类型，已合并到 `summary`
- `reply_draft` 和 `generate_email` 合并为 `email_generation`，通过 `prompt_paths` 同时更新两个 prompt

---

## 触发信号

### 谁来触发

**触发 Agent**: `clawmail-monitor` (ClawMail 系统内的监控模块)

**执行 Agent**: `clawmail-personalization` (本 Skill)

### 触发条件

当任一 `~/clawmail_data/feedback/feedback_{type}.jsonl` 中的记录数达到 **5 条**时，ClawMail 自动向 OpenClaw 发送消息触发本 Skill。

### 触发消息格式

```
(ClawMail-Personalization) 用户已累积足够的{type}反馈，请触发 clawmail-personalization skill。
feedback_type: {type}
feedback_path: ~/clawmail_data/feedback/feedback_{type}.jsonl
prompt_paths: ["{type}"]
related_prompts: []
archive_dir: ~/clawmail_data/feedback/{type}
prompt_archive_dir: ~/clawmail_data/prompts/archive
```

**字段说明**：
- `feedback_type`: 反馈类型（如 `importance_score`, `email_generation` 等）
- `prompt_paths`: 要更新的 prompt 文件列表（JSON 数组）
  - 大多数类型：`["importance_score"]` 等单一 prompt
  - `email_generation`：`["reply_draft", "generate_email"]` 同时更新两个
- `related_prompts`: 其他需要一并考虑的关联 prompts（目前大部分为空）

**示例 - importance_score**：
```
(ClawMail-Personalization) 用户已累积足够的importance_score反馈...
feedback_type: importance_score
feedback_path: ~/clawmail_data/feedback/feedback_importance_score.jsonl
prompt_paths: ["importance_score"]
related_prompts: []
```

**示例 - email_generation**（同时更新两个 prompt）：
```
(ClawMail-Personalization) 用户已累积足够的email_generation反馈...
feedback_type: email_generation
feedback_path: ~/clawmail_data/feedback/feedback_email_generation.jsonl
prompt_paths: ["reply_draft", "generate_email"]
related_prompts: []
```

### 手动触发

```bash
# 通过消息触发
python scripts/main.py -m "(ClawMail-Personalization) ..."

# 通过文件触发
python scripts/main.py -f trigger_message.txt

# 从 stdin 触发
echo "(ClawMail-Personalization) ..." | python scripts/main.py
```

---

## 执行流程

```
ClawMail 检测到反馈≥5条
        ↓
发送触发消息 (personalizationAgent001)
        ↓
┌─────────────────────────────────────┐
│   clawmail-personalization Skill    │
├─────────────────────────────────────┤
│ 1. 解析触发消息                     │
│    - 确定 feedback_type             │
│    - 提取 prompt_paths（数组）       │
├─────────────────────────────────────┤
│ 2. 读取反馈数据                     │
│    GET /personalization/feedback/{type}
├─────────────────────────────────────┤
│ 3. 读取当前 prompts（prompt_paths）  │
│    GET /personalization/prompt/{type}
├─────────────────────────────────────┤
│ 4. 读取用户侧写                     │
│    - MEMORY.md                      │
│    - USER.md                        │
│    - memory/*.md                    │
├─────────────────────────────────────┤
│ 5. 分析反馈数据                     │
│    - 统计模式                       │
│    - 提取洞察                       │
├─────────────────────────────────────┤
│ 6. 【强制 LLM】生成新 prompts       │
│    POST 127.0.0.1:18789/v1/chat/completions
│    - 反馈数据 + 当前 prompt + 侧写  │
│    - 【必须】使用 LLM 生成          │
│    - 【禁止】使用规则模板           │
│    （为 prompt_paths 中每个 prompt   │
│     分别调用 LLM 生成）              │
├─────────────────────────────────────┤
│ 7. 更新所有 prompts（prompt_paths）  │
│    POST /personalization/update-prompt
│    （逐个更新 prompt_paths 中的      │
│     每个 prompt）                    │
├─────────────────────────────────────┤
│ 8. 归档反馈数据                     │
│    POST /personalization/archive-feedback
├─────────────────────────────────────┤
│ 9. 通知完成                         │
│    POST /personalization/status     │
└─────────────────────────────────────┘
        ↓
下次 AI 使用更新后的 prompt → 输出更符合用户预期
```

**说明**：
- `prompt_paths` 是要更新的 prompt 文件列表
- 大多数类型只有一个（如 `["importance_score"]`）
- `email_generation` 同时更新两个（`["reply_draft", "generate_email"]`）

---

## REST API 端点

ClawMail 提供以下 HTTP API 供 Skill 调用（`127.0.0.1:9999`）：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/personalization/feedback/{type}` | GET | 读取反馈数据（JSON 数组） |
| `/personalization/prompt/{type}` | GET | 读取当前 prompt 内容 |
| `/personalization/update-prompt` | POST | 备份旧 prompt 并写入新版本 |
| `/personalization/archive-feedback` | POST | 归档反馈并清空主文件 |
| `/personalization/status` | POST | 通知更新完成 |

### API 调用示例

```python
from scripts.api_client import ClawMailAPIClient

client = ClawMailAPIClient("http://127.0.0.1:9999")

# 读取反馈
feedback = client.get_feedback("importance_score")

# 读取 prompt
prompt = client.get_prompt("importance_score")

# 更新 prompt
client.update_prompt("importance_score", new_prompt_content)

# 归档反馈
client.archive_feedback("importance_score")

# 通知完成
client.notify_completion("importance_score", success=True)
```

---

## LLM 调用（强制性）

**⚠️ 重要：本 Skill 必须使用 LLM 生成 prompt，不允许使用规则模板或其他非 LLM 方法。**

Skill 通过 **OpenClaw Gateway** 调用大模型：

- **URL**: `http://127.0.0.1:18789/v1/chat/completions`
- **模型**: `kimi-k2.5`（可配置）
- **输入**: 
  - 反馈数据分析结果
  - 当前 prompt
  - 其他相关 prompts
  - 用户侧写
- **输出**: 新的个性化 prompt（由 LLM 生成）

### 强制性要求

1. **必须使用 LLM**: 所有 prompt 的生成必须通过 LLM 调用完成
2. **不允许回退**: 如果 LLM 调用失败，整个个性化流程会失败，不会回退到规则模板
3. **内容验证**: LLM 返回的 prompt 必须达到一定长度（≥100 字符），否则视为失败
4. **错误传播**: LLM 调用失败会抛出异常，通知 ClawMail 更新失败

### 失败处理

如果 LLM 调用失败：
- 立即终止个性化流程
- 不更新任何 prompt 文件
- 通过 `/personalization/status` 通知 ClawMail 失败
- 保留反馈数据，等待下次重试

---

## 目录结构

```
skills/clawmail-personalization/
├── SKILL.md                    # 本文档
├── scripts/
│   ├── __init__.py
│   ├── main.py                 # 主入口，解析消息，执行完整流程
│   ├── api_client.py           # ClawMail HTTP API 客户端
│   ├── feedback_analyzer.py    # 反馈数据分析（9种类型）
│   ├── prompt_generator.py     # 调用 LLM 生成 prompt
│   └── user_profile.py         # 读取用户侧写
└── config/
    └── config.json             # 配置示例
```

---

## 使用方法

### 自动触发（推荐）

ClawMail 系统自动检测并触发，无需人工干预。

### 手动触发

```bash
# 使用默认配置
python scripts/main.py -m "(ClawMail-Personalization) feedback_type: importance_score ..."

# 指定 API 地址
python scripts/main.py \
    -m "(ClawMail-Personalization) ..." \
    --clawmail-api http://127.0.0.1:9999 \
    --openclaw-url http://127.0.0.1:18789

# 预览模式（不实际更新）
python scripts/main.py -m "..." --dry-run

# 保存结果到文件
python scripts/main.py -m "..." -o result.json
```

---

## 配置

### 环境变量

```bash
# ClawMail HTTP API 地址
export CLAWMAIL_API_URL="http://127.0.0.1:9999"

# OpenClaw Gateway 地址
export OPENCLAW_URL="http://127.0.0.1:18789"

# 使用的模型
export MODEL="kimi-k2.5"
```

### 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--trigger-message, -m` | 触发消息内容 | — |
| `--trigger-file, -f` | 触发消息文件 | — |
| `--clawmail-api` | ClawMail API 地址 | `http://127.0.0.1:9999` |
| `--openclaw-url` | OpenClaw Gateway 地址 | `http://127.0.0.1:18789` |
| `--model` | LLM 模型 | `kimi-k2.5` |
| `--dry-run` | 预览模式 | `False` |
| `--output, -o` | 输出结果文件 | — |

---

## 数据目录结构

```
~/clawmail_data/
├── feedback/
│   ├── feedback_importance_score.jsonl     # 当前反馈
│   ├── feedback_category.jsonl
│   ├── feedback_is_spam.jsonl
│   ├── ... (9种类型)
│   ├── importance_score/                   # 归档历史
│   ├── category/
│   └── ...
├── prompts/
│   ├── importance_score.txt                # 当前 prompt
│   ├── category.txt
│   ├── ... (12个prompts)
│   └── archive/                            # 旧版本存档
└── chat_logs/
    └── personalizationAgent001.log         # 对话记录
```

---

## Agent 协作关系

```
ClawMail (Client)                          OpenClaw (AI Gateway)
    │                                              │
    ├── 用户操作 → 记录反馈                        │
    │       ↓                                      │
    ├── 反馈≥5条 → _trigger_personalization()     │
    │       ↓                                      │
    └── user_chat(msg, "personalizationAgent001") ─┤
                                                   │
                            ┌──────────────────────┤
                            │                      │
                    clawmail-personalization Skill │
                    (通过 REST API 与 ClawMail 交互) │
                            │                      │
                            ├── 读取反馈           │
                            ├── 读取 prompts       │
                            ├── 读取用户侧写       │
                            ├── 调用 LLM 分析      │
                            ├── 生成新 prompt      │
                            ├── 更新 prompts       │
                            └── 归档反馈           │
                                                   │
    ┌──────────────────────────────────────────────┤
    │                                              │
    └── POST /personalization/status ──────────────┘
            ↓
    UI 显示 "✅ 个性化更新完成"
```

---

## 注意事项

1. **API 依赖**: Skill 依赖 ClawMail 的 HTTP API (`127.0.0.1:9999`)，确保 ClawMail 正在运行
2. **LLM 强制依赖**: **必须使用 OpenClaw Gateway (`127.0.0.1:18789`)**，如果 LLM 不可访问，整个流程会失败
3. **超时处理**: LLM 调用默认 120 秒超时，超时视为失败
4. **不允许回退**: LLM 调用失败不会回退到规则模板，整个流程会失败
5. **备份机制**: 每次更新前自动备份旧 prompt 到 `prompts/archive/`
6. **归档机制**: 已消费的反馈自动归档到 `feedback/{type}/`

---

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `无法连接到 ClawMail API` | ClawMail 未运行或端口不对 | 检查 ClawMail 是否启动，确认端口 9999 |
| `无法连接到 OpenClaw` | Gateway 未运行 | 检查 `openclaw gateway status`，必须启动后才能执行个性化 |
| `【强制 LLM 失败】` | LLM 调用失败或返回无效内容 | 检查 OpenClaw 日志，确保模型可访问；失败时不会回退到规则模板 |
| `LLM 调用超时` | 模型响应慢 | 检查网络或模型负载；超时视为失败，不会使用备用方案 |
| `反馈数据为空` | 文件不存在或无记录 | 检查反馈文件路径和内容 |
| `Prompt 内容过短` | LLM 返回内容不足 100 字符 | LLM 可能返回了无效内容，检查 LLM 响应；不会使用原始 prompt |

---

## 路径映射（Skill-Driven 迁移后）

迁移完成后，personalization 的优化目标从 `~/clawmail_data/prompts/*.txt` 改为各 skill 的 `references/prompts/*.md`：

| 旧路径 (prompts/*.txt) | 新路径 (skill references) |
|------------------------|--------------------------|
| `importance_score.txt` | `clawmail-analyzer/references/prompts/importance_algorithm.md` |
| `summary.txt` | `clawmail-analyzer/references/prompts/summary_guide.md` |
| `category.txt` | `clawmail-analyzer/references/prompts/category_rules.md` |
| `is_spam.txt` | `clawmail-analyzer/references/prompts/spam_rules.md`（待新建）|
| `reply_draft.txt` | `clawmail-reply/references/prompts/reply_guide.md` |
| `generate_email.txt` | `clawmail-reply/references/prompts/generate_email_guide.md` |
| `polish_email.txt` | `clawmail-reply/references/prompts/polish_guide.md` |

**注意**：路径迁移在 Phase 3 执行，不阻塞 Phase 1-2。`scripts/main.py` 和 `scripts/api_client.py` 中的路径逻辑需要同步更新。

---

## 更新日志

### v2.1.0 (2026-02-27)
- **【强制 LLM】** 明确 LLM 调用为强制性要求
- 移除任何可能的规则模板回退逻辑
- LLM 失败时整个流程失败，不静默回退
- 添加 LLM 返回内容长度验证（≥100 字符）

### v2.0.0 (2026-02-27)
- 重写架构，支持 8 种反馈类型
- `keywords` 合并到 `summary`
- `reply_draft` + `generate_email` 合并为 `email_generation`
- 改为 REST API 交互（不再是直接文件操作）
- 使用 LLM 生成 prompt（不再是规则模板）

### v1.0.0 (2026-02-27)
- 初始版本，仅支持 importance_score
- 直接操作文件
- 基于规则模板生成 prompt
