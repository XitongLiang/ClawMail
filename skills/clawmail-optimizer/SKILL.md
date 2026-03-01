# clawmail-optimizer

元 Skill：根据用户反馈数据自动优化其他 Skill 的行为规则。

## 功能

读取用户隐式反馈（编辑 AI 草稿、修正评分、摘要差评），分析修改模式，用 LLM 重写目标 Skill 的 `references/prompts/*.md` 文件，使 AI 输出更贴近用户偏好。

## 脚本

| 脚本 | 用途 |
|---|---|
| `optimize.py` | 主入口，分析反馈 → LLM 重写 prompt → 写回文件 |
| `rollback.py` | 回滚 prompt 到之前的备份版本 |

## 调用方式

```bash
# 自动触发（反馈计数达阈值时由 ClawMail 后台调用）
python optimize.py --prompt-type email_generation --account-id <id>

# 手动预览（不实际修改）
python optimize.py --prompt-type email_generation --account-id <id> --dry-run

# 回滚
python rollback.py --prompt-type email_generation --target reply_guide.md --version latest
```

## prompt-type 映射

| prompt-type | 反馈来源 | 修改目标 |
|---|---|---|
| `email_generation` | 回复/撰写邮件的编辑反馈 | reply_guide.md, tone_styles.md |
| `polish_email` | 润色邮件的编辑反馈 | polish_guide.md |
| `importance_score` | 重要性评分修正 | importance_algorithm.md |
| `summary` | 摘要评价 | summary_guide.md |

## 安全机制

- 每次修改前自动备份到 `.backups/` 目录
- 结构校验：LLM 输出必须保留原有 section headers
- 速率限制：同一 prompt-type 每 24h 最多优化 1 次
- 支持回滚到任意历史版本

## 依赖

- ClawMail REST API (`GET /personalization/feedback/`, `POST /personalization/archive-feedback`)
- OpenClaw LLM Gateway
