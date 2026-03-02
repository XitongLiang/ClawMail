# clawmail-optimizer

元 Skill：根据用户反馈数据自动优化其他 Skill 的行为规则 + 清洗用户记忆。

## 功能

1. **Prompt 优化**：读取用户反馈，分析修改模式，用 LLM 重写目标 Skill 的 prompt 文件
2. **记忆清洗**：当记忆累积达阈值（10 条新增），自动合并重复、解决矛盾、分类 skill_defect

## 脚本

| 脚本 | 用途 |
|---|---|
| `optimize.py` | 主入口，支持 optimize / clean 两种模式 |
| `rollback.py` | 回滚 prompt 到之前的备份版本 |

## 调用方式

```bash
# Prompt 优化（反馈计数达阈值时由 ClawMail 后台调用）
python optimize.py --mode optimize --prompt-type email_generation --account-id <id>

# 记忆清洗（learner 累计写入 10 条后自动触发）
python optimize.py --mode clean --account-id <id>

# 预览模式（不实际修改）
python optimize.py --mode clean --account-id <id> --dry-run

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

## 记忆清洗规则

- **合并重复**：同 type + 同/相似 key → 合并为一条，evidence_count 累加
- **解决矛盾**：同 key 但 content 冲突 → 保留高证据/更新鲜的
- **标注缺陷**：`_source=skill_defect` 的记忆 → 提取缺陷描述 → 触发对应 prompt 优化

## 触发机制

- learner 每次写入记忆后累加计数
- 累计 ≥ 10 条新写入 → 后台自动触发 `--mode clean`
- 清洗发现 skill_defect → 自动触发对应 `--mode optimize`

## 安全机制

- 每次修改前自动备份到 `.backups/` 目录
- 结构校验：LLM 输出必须保留原有 section headers
- 速率限制：同一 prompt-type 每 24h 最多优化 1 次
- 支持回滚到任意历史版本

## 依赖

- ClawMail REST API (`GET /memories/`, `POST /memories/`, `GET /personalization/feedback/`)
- OpenClaw LLM Gateway
