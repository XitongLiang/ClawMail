# 通过OpenClaw的skill实现用户个性化功能闭环

## 用户邮件重要性排序

在AI邮件分析中，输出一个邮件重要性的评分（0-100），初始评分标准如下：

【importance_score说明】
- 综合评估邮件的重要性，给出0-100的分数
- 90-100：极其重要，需要立即处理（如紧急工作任务、领导直接指示、关键截止日期）
- 70-89：重要，需要尽快处理（如项目进展、会议安排、客户请求）
- 40-69：一般重要（如日常沟通、信息同步、常规通知）
- 20-39：较低重要性（如订阅内容、一般群发通知）
- 0-19：不重要（如广告、推广、垃圾邮件）

此评分标准存储在 `~/clawmail_data/prompts/importance_score.txt`，可由用户或 OpenClaw skill 动态更新。


## 用户更改重要性评分的两种方式

### 方式一：手动输入分数
在 AI 分析面板的重要性分数（如"（75）"）右侧添加一个编辑按钮，用户点击后弹出输入框，输入 0-100 的新分数。

### 方式二：拖拽排序
打开重要性排序功能后，用户可以手动拖拽邮件调整排列顺序：
- 拖到两封邮件之间：新分数 = 上下两封邮件分数的平均值
- 拖到列表最顶部：新分数 = 原第一封邮件的分数 + 5（上限100）
- 拖到列表最底部：新分数 = 原最后一封邮件的分数 - 5（下限0）

两种方式修改后，立即同步更新数据库中 `email_ai_metadata.importance_score`，邮件列表实时刷新。


## 反馈数据记录

当用户修改重要性评分时，在 `~/clawmail_data/feedback/` 目录下记录反馈数据：

文件路径：`~/clawmail_data/feedback/feedback_importance_score.jsonl`

每行一条 JSON，以 `email_id` 为唯一键——同一封邮件多次修改时，只保留最后一次的记录（覆盖之前的条目）。

字段如下：
```json
{
  "timestamp": "2026-02-25T14:30:00",
  "email_id": "uuid-xxx",
  "subject": "邮件主题",
  "keywords": ["项目", "截止日期"],
  "one_line": "AI一句话摘要",
  "brief": "AI简要摘要（2-3句）",
  "key_points": ["要点1", "要点2"],
  "original_score": 45,
  "new_score": 78,
  "mode": "manual_input",
  "context": null
}
```

拖拽模式的 `context` 示例：
```json
{
  "above": {
    "subject": "周报提交提醒",
    "keywords": ["周报", "提交"],
    "one_line": "要求本周五前提交周报",
    "brief": "行政部提醒全员在周五下班前提交本周工作周报。",
    "key_points": ["周五截止", "提交周报"],
    "score": 80
  },
  "below": {
    "subject": "午餐订购通知",
    "keywords": ["午餐", "订购"],
    "one_line": "公司午餐菜单更新",
    "brief": "后勤部通知本周午餐菜单已更新，请在系统中选择。",
    "key_points": ["菜单更新", "系统选择"],
    "score": 60
  }
}
```

| 字段 | 说明 |
|---|---|
| `timestamp` | 修改时间（ISO 格式） |
| `email_id` | 邮件 ID（关联数据库） |
| `subject` | 邮件主题 |
| `keywords` | AI 提取的关键词列表 |
| `one_line` | AI 一句话摘要（`summary_one_line`） |
| `brief` | AI 简要摘要（`summary_brief`） |
| `key_points` | AI 关键要点列表（`summary_key_points`） |
| `original_score` | AI 原始评分 |
| `new_score` | 用户修改后的评分 |
| `mode` | `manual_input`（手动输入）或 `drag_reorder`（拖拽排序） |
| `context` | 拖拽时记录上下邻居的 `subject`、`keywords`、`one_line`、`brief`、`key_points`、`score`；手动输入时为 `null` |


## 用户数据目录结构

```
~/clawmail_data/
├── chat_logs/                                  ← AI 对话记录（按 agent 分文件，追加模式）
│   ├── mailAgent001.log                        ← 邮件 AI 分析对话
│   ├── draftAgent001.log                       ← AI 回复草稿对话
│   ├── generateAgent001.log                    ← AI 写邮件对话
│   ├── polishAgent001.log                      ← AI 润色邮件对话
│   └── personalizationAgent001.log             ← 个性化反馈/触发对话
├── feedback/
│   ├── feedback_importance_score.jsonl          ← 当前生效的反馈（按 email_id 去重）
│   └── importance_score/                        ← 修改历史存档
│       └── 2026-02-27T14-30-00.jsonl            ← 每次 OpenClaw skill 消费后归档
├── prompts/
│   ├── importance_score.txt                     ← 当前生效的评分 prompt
│   ├── category.txt
│   ├── urgency.txt
│   ├── ...
│   └── archive/                                 ← 旧版 prompt 存档
│       ├── importance_score_2026-02-25.txt
│       └── importance_score_2026-02-27.txt
└── clawmail.db
```

### feedback/importance_score/ — 修改历史存档

OpenClaw skill 每次读取并消费 `feedback_importance_score.jsonl` 后，将已消费的内容归档到 `importance_score/` 目录下，文件名为消费时间戳（如 `2026-02-27T14-30-00.jsonl`），随后清空主文件。这样可以追溯用户历史偏好变化。

### chat_logs/ — AI 对话记录

所有与 OpenClaw 的对话（ClawMail 发送的消息 + OpenClaw 的回复）由 `OpenClawBridge` 在底层统一记录，按 agent ID 分文件存储，追加模式写入。已有旧记录时不覆盖，持续往下追加。

日志格式：
```
===== 2026-02-27 14:30:00 =====
[ClawMail → OpenClaw]
(ClawMail)发送的消息内容...

[OpenClaw → ClawMail]
OpenClaw 的回复内容...

```

| 文件 | 对应 Agent | 内容 |
|------|-----------|------|
| `mailAgent001.log` | 邮件 AI 分析 | 每封邮件的分析 prompt 和 AI 返回的 JSON 结果 |
| `draftAgent001.log` | AI 回复草稿 | 回复草稿生成的 prompt 和结果 |
| `generateAgent001.log` | AI 写邮件 | 邮件生成的 prompt 和结果 |
| `polishAgent001.log` | AI 润色邮件 | 润色请求和结果 |
| `personalizationAgent001.log` | 个性化 | 星级反馈、个性化触发消息和 OpenClaw 的回复 |

用途：调试 AI 行为、追溯个性化更新过程、分析 OpenClaw 的决策逻辑。

### prompts/archive/ — 旧版 prompt 存档

OpenClaw skill 更新 prompt 文件前，先将当前版本复制到 `archive/` 目录下，文件名加上日期后缀（如 `importance_score_2026-02-27.txt`）。便于回溯和对比不同版本的评分标准。


## 个性化闭环路径

```
用户修改评分 → 记录到 feedback_importance_score.jsonl（同一邮件仅保留最新记录）
                        ↓
        OpenClaw skill 定期读取反馈数据
                        ↓
        归档已消费的反馈 → feedback/importance_score/（带时间戳）
                        ↓
        统计分析用户偏好模式（如：用户倾向于提高会议类邮件的分数）
                        ↓
        备份旧 prompt → prompts/archive/（带日期后缀）
                        ↓
        自动更新 ~/clawmail_data/prompts/importance_score.txt
        （调整评分标准，使 AI 后续评分更贴合用户习惯）
                        ↓
        下次 AI 分析邮件时加载更新后的 prompt → 评分更符合用户预期
```



## OpenClaw 运用 skill 更新 prompts，以实现用户个性化

### 触发条件

当 `~/clawmail_data/feedback/feedback_importance_score.jsonl` 中的记录数达到 **5 条**时，ClawMail 自动向 OpenClaw 发送消息，触发名为 `clawmail-personalization` 的 skill。

### Skill 执行流程

`clawmail-personalization` skill 收到触发后，按以下步骤执行：

1. **确定更新目标** — 根据触发来源确定要更新的 prompt（本 case 中为 `importance_score.txt`）
2. **读取反馈数据** — 从 `~/clawmail_data/feedback/feedback_importance_score.jsonl` 读取全部用户修改记录
3. **读取当前 prompt** — 从 `~/clawmail_data/prompts/importance_score.txt` 读取当前评分标准
4. **调取用户侧写** — 从 OpenClaw 记忆系统中获取用户画像（偏好、工作场景等）
5. **大模型分析** — 将反馈数据 + 当前 prompt + 用户侧写一起传给大模型，分析用户偏好模式，生成更新后的个性化评分标准
6. **备份旧 prompt** — 将当前 `importance_score.txt` 复制到 `prompts/archive/importance_score_{日期}.txt`
7. **写入新 prompt** — 用大模型生成的新评分标准覆盖 `importance_score.txt`
8. **归档旧反馈** — 将已消费的 `feedback_importance_score.jsonl` 移动到 `feedback/importance_score/{时间戳}.jsonl`，清空主文件
9. **更新 OpenClaw 记忆**（可选） — OpenClaw 根据收到的信息自行判断是否需要更新自己的记忆（如用户文档、偏好标签等）

### ClawMail 端触发实现

#### 触发入口

在 `app.py` 的 `_apply_importance_change()` 方法末尾，每次用户修改评分后检查反馈计数：

```python
count = self._db.get_feedback_count("importance_score")
if count >= 5 and self._ai_bridge:
    self._trigger_personalization("importance_score")
```

`get_feedback_count()` 读取 `feedback_importance_score.jsonl` 的非空行数。

#### 触发方式：通过 OpenClaw 聊天接口发送消息

ClawMail 使用 `OpenClawBridge.user_chat()` 向 OpenClaw 发送一条结构化消息，使用统一的 `personalizationAgent001` agent ID（星级评分反馈也使用此 agent）。

消息格式：
```
(ClawMail-Personalization) 用户已累积足够的重要性评分反馈，请触发 clawmail-personalization skill。
feedback_type: importance_score
feedback_path: ~/clawmail_data/feedback/feedback_importance_score.jsonl
prompt_path: ~/clawmail_data/prompts/importance_score.txt
archive_dir: ~/clawmail_data/feedback/importance_score
prompt_archive_dir: ~/clawmail_data/prompts/archive
```

- 前缀 `(ClawMail-Personalization)` 供 OpenClaw 识别并路由到 `clawmail-personalization` skill
- agent ID `personalizationAgent001` 让 OpenClaw 在同一个对话上下文中关联处理所有用户偏好数据（包括星级评分反馈）
- 异步发送（`asyncio.ensure_future`），不阻塞 UI

#### REST API 端点（供 OpenClaw skill 回调）

ClawMail 的本地 HTTP API（`127.0.0.1:9999`）提供以下端点，供 OpenClaw skill 在执行过程中读写数据：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/personalization/feedback/{type}` | GET | 读取反馈数据（返回 JSON 数组） |
| `/personalization/prompt/{type}` | GET | 读取当前 prompt 内容 |
| `/personalization/update-prompt` | POST | 备份旧 prompt 到 `archive/` 并写入新版本 |
| `/personalization/archive-feedback` | POST | 归档已消费反馈到 `feedback/{type}/` 并清空主文件 |
| `/personalization/status` | POST | skill 完成后回调，通知 UI 显示更新成功消息 |

Skill 执行流程对应的 API 调用顺序：
```
1. GET  /personalization/feedback/importance_score    ← 读取反馈
2. GET  /personalization/prompt/importance_score      ← 读取当前 prompt
3. （OpenClaw 内部：调取用户侧写 + 大模型分析 + 生成新 prompt）
4. POST /personalization/update-prompt               ← 备份旧 + 写入新 prompt
   body: {"prompt_type": "importance_score", "content": "新的评分标准..."}
5. POST /personalization/archive-feedback             ← 归档反馈
   body: {"feedback_type": "importance_score"}
6. POST /personalization/status                       ← 通知完成
   body: {"prompt_type": "importance_score", "success": true}
```

### 触发流程总览

```
用户修改评分 → _apply_importance_change()
    │
    ├── 更新数据库 importance_score
    ├── 记录反馈到 feedback_importance_score.jsonl（email_id 去重）
    ├── 刷新 UI
    │
    └── 检查反馈数 ≥ 5？
         │ 是
         ▼
    _trigger_personalization()
         │
         ▼
    user_chat(trigger_msg, "personalizationAgent001")
         │
         ▼
    OpenClaw 收到消息 → 路由到 clawmail-personalization skill
         │
         ▼
    Skill 通过 REST API 读取反馈 + 当前 prompt
         │
         ▼
    大模型分析用户偏好 → 生成个性化 prompt
         │
         ▼
    Skill 通过 REST API 写入新 prompt + 归档旧反馈
         │
         ▼
    POST /personalization/status → UI 显示 "✅ 个性化更新完成"
         │
         ▼
    下次 AI 分析邮件时加载更新后的 prompt → 评分更符合用户预期
```

