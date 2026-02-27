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
| `keywords` | AI 提取的关键词列表（来自 `summary.keywords`） |
| `one_line` | AI 一句话摘要（`summary_one_line`） |
| `brief` | AI 简要摘要（`summary_brief`） |
| `key_points` | AI 关键要点列表（`summary_key_points`） |
| `original_score` | AI 原始评分 |
| `new_score` | 用户修改后的评分 |
| `mode` | `manual_input`（手动输入）或 `drag_reorder`（拖拽排序） |
| `context` | 拖拽时记录上下邻居的 `subject`、`keywords`、`one_line`、`brief`、`key_points`、`score`；手动输入时为 `null` |


---

## 邮件分类标签（category）反馈

### 当前状态

AI 从以下固定标签中选择 0-3 个：`urgent`、`pending_reply`、`notification`、`subscription`、`meeting`、`approval`，以及动态标签 `项目:XX`。显示为 AI 分析面板的彩色 badge。用户无法修改。

评分标准存储在 `~/clawmail_data/prompts/category.txt`，可由用户或 OpenClaw skill 动态更新。

### 用户反馈方式

在 AI 分析面板的分类 badge 区域：
- 每个 badge 右侧增加 ✕ 按钮，点击移除该标签
- badge 区域末尾增加 ＋ 按钮，点击弹出下拉列表，可选择 6 个固定标签或输入动态标签（如 `项目:XX`）
- 修改后立即更新数据库 `email_ai_metadata.categories`，AI 面板实时刷新

### 反馈数据记录

文件路径：`~/clawmail_data/feedback/feedback_category.jsonl`

每行一条 JSON，以 `email_id` 为唯一键——同一封邮件多次修改时，只保留最后一次的记录。

```json
{
  "timestamp": "2026-02-27T14:30:00",
  "email_id": "uuid-xxx",
  "subject": "邮件主题",
  "keywords": ["关键词1", "关键词2"],
  "one_line": "AI一句话摘要",
  "brief": "AI简要摘要",
  "key_points": ["要点1", "要点2"],
  "original_categories": ["urgent", "meeting"],
  "new_categories": ["meeting", "approval"],
  "added": ["approval"],
  "removed": ["urgent"]
}
```

| 字段 | 说明 |
|---|---|
| `original_categories` | AI 原始分类标签列表 |
| `new_categories` | 用户修改后的标签列表 |
| `added` | 用户新增的标签 |
| `removed` | 用户移除的标签 |

触发阈值：**5 条**反馈后触发 `_trigger_personalization("category")`。


---

## 垃圾邮件检测（is_spam）反馈

### 当前状态

AI 输出 `true`（垃圾邮件）或 `false`（正常邮件）。用户可通过右键菜单"标记为垃圾邮件"将邮件移入垃圾邮件文件夹，或从垃圾邮件文件夹移回收件箱。但 AI 判断与用户操作之间没有反馈关联。

评分标准存储在 `~/clawmail_data/prompts/is_spam.txt`，可由用户或 OpenClaw skill 动态更新。

### 用户反馈方式

**隐式反馈** — 无需额外 UI，利用现有右键菜单操作自动比对 AI 判断：

- AI 判断 `false`（正常）+ 用户右键"标记为垃圾邮件" → 记录为 `missed_spam`（漏判）
- AI 判断 `true`（垃圾）+ 用户将邮件"移动到收件箱" → 记录为 `false_positive`（误判）
- AI 判断与用户操作一致时 → 不记录（无需学习）

### 反馈数据记录

文件路径：`~/clawmail_data/feedback/feedback_is_spam.jsonl`

每行一条 JSON，以 `email_id` 为唯一键。

```json
{
  "timestamp": "2026-02-27T14:30:00",
  "email_id": "uuid-xxx",
  "subject": "邮件主题",
  "sender": "sender@example.com",
  "keywords": ["关键词"],
  "one_line": "AI一句话摘要",
  "brief": "AI简要摘要",
  "key_points": ["要点"],
  "ai_prediction": false,
  "user_action": "mark_spam",
  "error_type": "missed_spam"
}
```

| 字段 | 说明 |
|---|---|
| `sender` | 发件人地址（垃圾邮件识别的重要特征） |
| `ai_prediction` | AI 原始判断（`true`/`false`） |
| `user_action` | `mark_spam`（用户标记为垃圾）或 `unmark_spam`（用户从垃圾箱移出） |
| `error_type` | `missed_spam`（AI 漏判）或 `false_positive`（AI 误判） |

触发阈值：**5 条**反馈后触发 `_trigger_personalization("is_spam")`。


---

## 行动项分类（action_category）反馈

### 当前状态

AI 为每个 action_item 分配 category（工作/学习/生活/个人），但 UI 中不直接显示此字段，仅在用户点击"＋ 加入待办"时传递给 Task。

评分标准存储在 `~/clawmail_data/prompts/action_category.txt`，可由用户或 OpenClaw skill 动态更新。

### 用户反馈方式

在 AI 分析面板的行动项表格中：
- 每行"＋ 加入待办"按钮旁增加一个分类标签（如 `[工作]`），颜色区分四类
- 点击标签弹出下拉选择：工作、学习、生活、个人
- 修改后立即更新数据库中该 action_item 的 `category` 字段
- 同时更新"加入待办"链接中的 `category` 参数，确保后续加入待办时使用修改后的分类

### 反馈数据记录

文件路径：`~/clawmail_data/feedback/feedback_action_category.jsonl`

每行一条 JSON，以 `email_id` + `action_index` 为联合唯一键。

```json
{
  "timestamp": "2026-02-27T14:30:00",
  "email_id": "uuid-xxx",
  "subject": "邮件主题",
  "keywords": ["关键词"],
  "one_line": "AI一句话摘要",
  "action_text": "提交项目报告",
  "action_index": 0,
  "original_category": "学习",
  "new_category": "工作"
}
```

| 字段 | 说明 |
|---|---|
| `action_text` | 被修改分类的行动项文本 |
| `action_index` | 行动项在列表中的索引 |
| `original_category` | AI 原始分类（工作/学习/生活/个人） |
| `new_category` | 用户修改后的分类 |

触发阈值：**5 条**反馈后触发 `_trigger_personalization("action_category")`。


---

## 回复立场建议（reply_stances）反馈

### 当前状态

AI 生成 2-4 个回复立场选项（动词开头，15 字以内），在回复编辑器的"✨ AI 辅助拟稿"面板中以 toggle 按钮展示。用户选择一个立场 → 选择回复风格 → 生成草稿。

评分标准存储在 `~/clawmail_data/prompts/reply_stances.txt`，可由用户或 OpenClaw skill 动态更新。

### 用户反馈方式

**隐式反馈** — 无需额外 UI，记录用户在回复流程中的选择行为：

- 用户选择了某个 stance 并生成草稿 → 记录被选中的 stance 和 tone（正面信号）
- 用户打开回复编辑器但未使用 AI 辅助，直接手写回复并发送 → 记录所有 stance 未被选中（负面信号：AI 建议不合适）

触发时机：
- 在 `compose_dialog._on_generate_draft()` 中记录选择（用户使用了 AI 辅助）
- 在 `compose_dialog._send_reply()` 中检查是否使用了 AI 辅助（若未使用则记录负面反馈）

### 反馈数据记录

文件路径：`~/clawmail_data/feedback/feedback_reply_stances.jsonl`

每行一条 JSON，以 `email_id` 为唯一键。

用户使用 AI 辅助时：
```json
{
  "timestamp": "2026-02-27T14:30:00",
  "email_id": "uuid-xxx",
  "subject": "原邮件主题",
  "keywords": ["关键词"],
  "one_line": "AI一句话摘要",
  "available_stances": ["同意并确认", "需要更多信息", "暂时无法满足"],
  "selected_stance": "同意并确认",
  "selected_tone": "正式",
  "used_ai_draft": true
}
```

用户未使用 AI 辅助时：
```json
{
  "timestamp": "2026-02-27T14:30:00",
  "email_id": "uuid-xxx",
  "subject": "原邮件主题",
  "keywords": ["关键词"],
  "one_line": "AI一句话摘要",
  "available_stances": ["同意并确认", "需要更多信息", "暂时无法满足"],
  "selected_stance": null,
  "selected_tone": null,
  "used_ai_draft": false
}
```

| 字段 | 说明 |
|---|---|
| `available_stances` | AI 提供的全部立场选项 |
| `selected_stance` | 用户选择的立场（未使用 AI 辅助时为 `null`） |
| `selected_tone` | 用户选择的回复风格（未使用 AI 辅助时为 `null`） |
| `used_ai_draft` | 用户是否使用了 AI 辅助生成草稿 |

触发阈值：**5 条**反馈后触发 `_trigger_personalization("reply_stances")`。


---

## 摘要质量（summary）反馈

### 当前状态

AI 生成三层摘要：`one_line`（20 字一句话概括）、`brief`（3-5 行标准摘要）、`key_points`（2-5 条关键要点），同时提取 `keywords`（3-5 个关键词）。其中 `brief` 和 `key_points` 在 AI 分析面板中展示，均为只读。关键词不在 UI 中独立展示，仅在反馈记录中作为上下文字段使用。

摘要标准（含关键词提取）存储在 `~/clawmail_data/prompts/summary.txt`，可由用户或 OpenClaw skill 动态更新。

### 用户反馈方式

**显式反馈** — 在 AI 摘要区域底部增加评价按钮：

- 👍（满意）/ 👎（不满意）二选一
- 点击 👎 后展开迷你反馈表单：
  - 原因选择（可多选）：太笼统 / 遗漏关键信息 / 重点偏移 / 太长 / 太短 / 关键词不准确
  - 可选填补充说明（自由文本输入框）
- 点击 👍 时直接记录正面反馈（不弹出表单）
- 同一封邮件可修改评价，以最后一次为准

### 反馈数据记录

文件路径：`~/clawmail_data/feedback/feedback_summary.jsonl`

每行一条 JSON，以 `email_id` 为唯一键。

```json
{
  "timestamp": "2026-02-27T14:30:00",
  "email_id": "uuid-xxx",
  "subject": "邮件主题",
  "keywords": ["关键词1", "关键词2"],
  "rating": "bad",
  "reasons": ["遗漏关键信息", "关键词不准确"],
  "user_comment": "没有提到附件中的报价单",
  "original_one_line": "AI生成的一句话摘要",
  "original_brief": "AI生成的标准摘要",
  "original_key_points": ["要点1", "要点2"],
  "original_keywords": ["关键词1", "关键词2"]
}
```

👍 正面反馈时：
```json
{
  "timestamp": "2026-02-27T14:30:00",
  "email_id": "uuid-xxx",
  "subject": "邮件主题",
  "keywords": ["关键词1", "关键词2"],
  "rating": "good",
  "reasons": [],
  "user_comment": null,
  "original_one_line": "AI生成的一句话摘要",
  "original_brief": "AI生成的标准摘要",
  "original_key_points": ["要点1", "要点2"],
  "original_keywords": ["关键词1", "关键词2"]
}
```

| 字段 | 说明 |
|---|---|
| `rating` | `good`（满意）或 `bad`（不满意） |
| `reasons` | 不满意原因列表（满意时为空数组）：`太笼统` / `遗漏关键信息` / `重点偏移` / `太长` / `太短` / `关键词不准确` |
| `user_comment` | 用户补充说明（可选，满意时为 `null`） |
| `original_one_line` | AI 原始一句话摘要 |
| `original_brief` | AI 原始标准摘要 |
| `original_key_points` | AI 原始关键要点列表 |
| `original_keywords` | AI 原始关键词列表（来自 `summary.keywords`） |

触发阈值：**5 条**反馈后触发 `_trigger_personalization("summary")`。


---

## 邮件生成模板（reply_draft + generate_email）反馈

### 当前状态

邮件生成功能覆盖两个场景：
1. **回复草稿**：用户在回复编辑器中选择立场（stance）和风格（tone）后，AI 根据 `reply_draft.txt` 模板生成回复草稿
2. **写新邮件**：用户输入大纲后，AI 根据 `generate_email.txt` 模板生成邮件正文

两者共享"生成邮件正文"的风格偏好（措辞习惯、开头/结尾风格、段落结构等），因此合并为同一套反馈机制，统一收集、统一触发、同时更新两个 prompt。

模板分别存储在 `~/clawmail_data/prompts/reply_draft.txt` 和 `~/clawmail_data/prompts/generate_email.txt`，可由用户或 OpenClaw skill 动态更新。

### 用户反馈方式

**隐式反馈** — 无需额外 UI，在用户发送邮件时自动比对 AI 生成版本与最终版本：

- **回复草稿场景**：在 `compose_dialog._on_generate_draft()` 中保存 AI 原始草稿到 `self._ai_draft_text`
- **写新邮件场景**：在 `compose_dialog._on_generate_email()` 中保存 AI 生成正文到 `self._ai_draft_text`
- 在 `compose_dialog._send_reply()` / `_send_email()` 中提取用户最终正文，与 `self._ai_draft_text` 比较
- 计算文本相似度（SequenceMatcher ratio）作为初筛：
  - 相似度 ≥ 0.95 → 不记录（AI 生成已足够好，用户几乎未改）
  - 相似度 < 0.95 → 记录反馈（用户对 AI 生成做了修改）
- 如果用户未使用 AI 生成功能（`self._ai_draft_text` 为 None），不记录

### 反馈数据记录

文件路径：`~/clawmail_data/feedback/feedback_email_generation.jsonl`

每行一条 JSON，以 `email_id` 为唯一键。两个场景的反馈记录到同一个文件中，通过 `source` 字段区分。

```json
{
  "timestamp": "2026-02-27T14:30:00",
  "email_id": "uuid-xxx",
  "source": "reply_draft",
  "subject": "原邮件主题",
  "keywords": ["关键词"],
  "one_line": "AI一句话摘要",
  "stance": "同意并确认",
  "tone": "正式",
  "ai_draft": "AI生成的完整邮件正文",
  "user_final": "用户最终发送的完整邮件正文",
  "similarity_ratio": 0.62
}
```

写新邮件场景示例：
```json
{
  "timestamp": "2026-02-27T15:00:00",
  "email_id": "uuid-yyy",
  "source": "generate_email",
  "subject": "用户填写的邮件主题",
  "outline": "用户输入的大纲",
  "tone": "正式",
  "ai_draft": "AI生成的完整邮件正文",
  "user_final": "用户最终发送的完整邮件正文",
  "similarity_ratio": 0.71
}
```

| 字段 | 说明 |
|---|---|
| `source` | 来源场景：`reply_draft`（回复草稿）或 `generate_email`（写新邮件） |
| `stance` | 用户选择的回复立场（仅 reply_draft 场景） |
| `tone` | 用户选择的风格 |
| `ai_draft` | AI 生成的完整邮件正文 |
| `user_final` | 用户最终发送的完整邮件正文 |
| `similarity_ratio` | AI 版本与用户最终版本的文本相似度（0-1），用于初筛 |

触发阈值：**5 条**反馈后触发 `_trigger_personalization("email_generation")`。

触发时 OpenClaw skill 同时更新 `reply_draft.txt` 和 `generate_email.txt` 两个 prompt，触发消息中携带 `prompt_paths: ["reply_draft", "generate_email"]`。OpenClaw skill 通过 AI 分析 `ai_draft` 与 `user_final` 的差异，识别用户的写作偏好模式（如措辞倾向、段落结构、开头/结尾风格等），据此调整两个模板的生成指令。


---

## 邮件润色模板（polish_email）反馈

### 当前状态

用户在编辑器中选择润色风格（tone）后，AI 根据 `polish_email.txt` 模板对正文进行润色，结果替换编辑器内容。用户可继续编辑后发送。目前润色结果与用户最终发送的内容之间没有反馈关联。

模板存储在 `~/clawmail_data/prompts/polish_email.txt`，可由用户或 OpenClaw skill 动态更新。

### 用户反馈方式

**隐式反馈** — 无需额外 UI，在用户发送邮件时自动比对润色结果与最终版本：

- 在 `compose_dialog` 润色完成后保存 AI 润色结果到 `self._polished_text` 和润色前原文到 `self._pre_polish_text`
- 在发送时提取用户最终正文，与 `self._polished_text` 比较
- 计算文本相似度（SequenceMatcher ratio）：
  - 相似度 ≥ 0.95 → 不记录（润色结果已满意）
  - 相似度 < 0.95 → 记录反馈（用户对润色结果做了修改）
- 如果用户未使用润色功能（`self._polished_text` 为 None），不记录

### 反馈数据记录

文件路径：`~/clawmail_data/feedback/feedback_polish_email.jsonl`

每行一条 JSON，以 `email_id` 为唯一键。若同一封邮件多次润色，以最后一次为准。

```json
{
  "timestamp": "2026-02-27T14:30:00",
  "email_id": "uuid-xxx",
  "subject": "邮件主题",
  "tone": "正式",
  "original_body": "润色前的原始正文",
  "polished_body": "AI润色后的正文",
  "user_final": "用户最终发送的正文",
  "similarity_ratio": 0.58
}
```

| 字段 | 说明 |
|---|---|
| `tone` | 用户选择的润色风格 |
| `original_body` | 润色前的原始正文 |
| `polished_body` | AI 润色后的正文 |
| `user_final` | 用户最终发送的正文 |
| `similarity_ratio` | AI 润色版与用户最终版本的文本相似度（0-1） |

触发阈值：**5 条**反馈后触发 `_trigger_personalization("polish_email")`。


---

## 关联更新策略（无直接反馈的 prompt）

以下 prompt 文件不单独收集用户反馈，而是在关联类型触发个性化时由 OpenClaw skill 一并更新。

### mail_analysis（邮件分析主模板）

- 这是包含输出 JSON 格式定义的主模板，结构性极强，不宜频繁修改
- **策略**：不主动触发更新。OpenClaw skill 在执行任意个性化任务时，可根据累积的用户偏好自主判断是否需要调整 `mail_analysis.txt` 的指令部分（**严禁修改 JSON 输出格式**）
- **约束**：skill 更新 mail_analysis.txt 时，必须保留 `{prompt_sections}` 和 `{mail_json}` 占位符，以及完整的 JSON 输出格式定义
- prompt 路径：`~/clawmail_data/prompts/mail_analysis.txt`


---

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
│   ├── feedback_importance_score.jsonl          ← 重要性评分反馈（按 email_id 去重）
│   ├── feedback_category.jsonl                  ← 分类标签反馈（按 email_id 去重）
│   ├── feedback_is_spam.jsonl                   ← 垃圾邮件检测反馈（按 email_id 去重）
│   ├── feedback_action_category.jsonl           ← 行动项分类反馈（按 email_id+index 去重）
│   ├── feedback_reply_stances.jsonl             ← 回复立场反馈（按 email_id 去重）
│   ├── feedback_summary.jsonl                   ← 摘要质量反馈（按 email_id 去重）
│   ├── feedback_email_generation.jsonl           ← 邮件生成反馈（reply_draft + generate_email，按 email_id 去重）
│   ├── feedback_polish_email.jsonl              ← 润色反馈（按 email_id 去重）
│   ├── importance_score/                        ← 重要性评分反馈存档
│   │   └── 2026-02-27T14-30-00.jsonl
│   ├── category/                                ← 分类标签反馈存档
│   ├── is_spam/                                 ← 垃圾邮件检测反馈存档
│   ├── action_category/                         ← 行动项分类反馈存档
│   ├── reply_stances/                           ← 回复立场反馈存档
│   ├── summary/                                 ← 摘要质量反馈存档
│   ├── email_generation/                        ← 邮件生成反馈存档
│   └── polish_email/                            ← 润色反馈存档
├── prompts/
│   ├── summary.txt                              ← 摘要生成 prompt（含关键词提取）
│   ├── category.txt                             ← 分类标签 prompt
│   ├── is_spam.txt                              ← 垃圾邮件检测 prompt
│   ├── action_category.txt                      ← 行动项分类 prompt
│   ├── reply_stances.txt                        ← 回复立场 prompt
│   ├── importance_score.txt                     ← 重要性评分 prompt
│   ├── mail_analysis.txt                        ← 邮件分析主模板（OpenClaw 自主判断更新）
│   ├── reply_draft.txt                          ← 回复草稿模板
│   ├── generate_email.txt                       ← 写邮件模板（与 reply_draft 统一反馈更新）
│   ├── polish_email.txt                         ← 润色模板
│   └── archive/                                 ← 旧版 prompt 存档
│       ├── importance_score_2026-02-25.txt
│       └── importance_score_2026-02-27.txt
└── clawmail.db
```

### feedback/{type}/ — 修改历史存档

OpenClaw skill 每次读取并消费 `feedback_{type}.jsonl` 后，将已消费的内容归档到对应的 `{type}/` 目录下，文件名为消费时间戳（如 `2026-02-27T14-30-00.jsonl`），随后清空主文件。这样可以追溯用户历史偏好变化。

各反馈类型共用同一套归档机制，目录一一对应：

| 反馈文件 | 归档目录 | 对应 prompt | 关联更新 |
|----------|----------|-------------|----------|
| `feedback_importance_score.jsonl` | `importance_score/` | `importance_score.txt` | — |
| `feedback_category.jsonl` | `category/` | `category.txt` | — |
| `feedback_is_spam.jsonl` | `is_spam/` | `is_spam.txt` | — |
| `feedback_action_category.jsonl` | `action_category/` | `action_category.txt` | — |
| `feedback_reply_stances.jsonl` | `reply_stances/` | `reply_stances.txt` | — |
| `feedback_summary.jsonl` | `summary/` | `summary.txt` | — |
| `feedback_email_generation.jsonl` | `email_generation/` | `reply_draft.txt` + `generate_email.txt` | — |
| `feedback_polish_email.jsonl` | `polish_email/` | `polish_email.txt` | — |

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


## 个性化闭环路径（通用）

所有反馈类型共用同一套闭环路径，仅 `{type}` 不同：

```
用户操作触发反馈 → 记录到 feedback_{type}.jsonl（按唯一键去重）
                        ↓
        反馈数 ≥ 5 → _trigger_personalization("{type}")
                        ↓
        OpenClaw skill 读取反馈数据
                        ↓
        归档已消费的反馈 → feedback/{type}/（带时间戳）
                        ↓
        统计分析用户偏好模式
                        ↓
        备份旧 prompt → prompts/archive/（带日期后缀）
                        ↓
        自动更新 ~/clawmail_data/prompts/{type}.txt
        （调整标准，使 AI 后续输出更贴合用户习惯）
                        ↓
        下次 AI 分析邮件时加载更新后的 prompt → 输出更符合用户预期
```

### 各反馈类型的触发入口

| 反馈类型 | 触发入口 | 反馈方式 | 关联更新 |
|----------|----------|----------|----------|
| `importance_score` | `_apply_importance_change()` 末尾 | 显式：用户手动修改评分 / 拖拽排序 | — |
| `category` | category badge 编辑回调 | 显式：用户增删分类标签 | — |
| `is_spam` | 右键"标记垃圾邮件"/"移动到收件箱"回调 | 隐式：比对 AI 判断与用户操作 | — |
| `action_category` | action_item 分类标签编辑回调 | 显式：用户修改行动项分类 | — |
| `reply_stances` | `compose_dialog._on_generate_draft()` / `_send_reply()` | 隐式：记录用户选择行为 | — |
| `summary` | AI 摘要区 👍/👎 按钮回调 | 显式：用户评价摘要质量（含关键词） | — |
| `email_generation` | `compose_dialog._send_reply()` / `_send_email()` | 隐式：比对 AI 生成版与最终发送版本 | 同时更新 `reply_draft.txt` + `generate_email.txt` |
| `polish_email` | `compose_dialog._send_reply()` / `_send_email()` | 隐式：比对润色版与最终发送版本 | — |



## OpenClaw 运用 skill 更新 prompts，以实现用户个性化

### 触发条件

当任一 `~/clawmail_data/feedback/feedback_{type}.jsonl` 中的记录数达到 **5 条**时，ClawMail 自动向 OpenClaw 发送消息，触发名为 `clawmail-personalization` 的 skill。各反馈类型独立计数、独立触发。

### Skill 执行流程

`clawmail-personalization` skill 收到触发后，按以下步骤执行（以 `{type}` 代指具体反馈类型）：

1. **确定更新目标** — 根据触发消息中的 `feedback_type` 和 `prompt_paths` 确定要更新的 prompt 文件，以及 `related_prompts` 中需要一并更新的关联 prompt
2. **读取反馈数据** — 从 `~/clawmail_data/feedback/feedback_{type}.jsonl` 读取全部用户修改记录
3. **读取当前 prompt** — 从 `prompt_paths` 指定的所有 prompt 文件读取当前标准
4. **调取用户侧写** — 从 OpenClaw 记忆系统中获取用户画像（偏好、工作场景等）
5. **大模型分析** — 将反馈数据 + 当前 prompt + 用户侧写一起传给大模型，分析用户偏好模式，生成更新后的个性化标准。对于 `email_generation` 类型，AI 会逐条对比 `ai_draft`（AI 生成版本）和 `user_final`（用户最终版本）的差异，识别用户的写作偏好模式（措辞倾向、段落结构、开头/结尾风格等）
6. **备份旧 prompt** — 将 `prompt_paths` 中所有 prompt 文件复制到 `prompts/archive/` 下（带日期后缀）
7. **写入新 prompt** — 用大模型生成的新标准覆盖 `prompt_paths` 中所有 prompt 文件
8. **更新关联 prompt**（如有） — 根据 `related_prompts` 字段，读取关联 prompt，结合本次反馈分析结果一并更新（备份旧版本到 archive）
9. **归档旧反馈** — 将已消费的 `feedback_{type}.jsonl` 移动到 `feedback/{type}/{时间戳}.jsonl`，清空主文件
10. **更新 OpenClaw 记忆**（可选） — OpenClaw 根据收到的信息自行判断是否需要更新自己的记忆（如用户文档、偏好标签等）

### ClawMail 端触发实现

#### 触发入口

各反馈类型在各自的回调方法末尾检查反馈计数：

```python
# 通用模式（所有 8 个有反馈的类型）
count = self._db.get_feedback_count("{type}")
if count >= 5 and self._ai_bridge:
    self._trigger_personalization("{type}")
```

`get_feedback_count()` 读取 `feedback_{type}.jsonl` 的非空行数。

#### 触发方式：通过 OpenClaw 聊天接口发送消息

ClawMail 使用 `OpenClawBridge.user_chat()` 向 OpenClaw 发送一条结构化消息，使用统一的 `personalizationAgent001` agent ID。

消息格式（以 `{type}` 代指具体反馈类型）：
```
(ClawMail-Personalization) 用户已累积足够的{type}反馈，请触发 clawmail-personalization skill。
feedback_type: {type}
feedback_path: ~/clawmail_data/feedback/feedback_{type}.jsonl
prompt_paths: ["{type}"]
related_prompts: []
archive_dir: ~/clawmail_data/feedback/{type}
prompt_archive_dir: ~/clawmail_data/prompts/archive
```

`email_generation` 类型的消息示例：
```
(ClawMail-Personalization) 用户已累积足够的email_generation反馈，请触发 clawmail-personalization skill。
feedback_type: email_generation
feedback_path: ~/clawmail_data/feedback/feedback_email_generation.jsonl
prompt_paths: ["reply_draft", "generate_email"]
related_prompts: []
archive_dir: ~/clawmail_data/feedback/email_generation
prompt_archive_dir: ~/clawmail_data/prompts/archive
```

`related_prompts` 字段指定需要一并更新的关联 prompt（无关联时为空数组 `[]`）。各类型的关联关系：

| 触发类型 | prompt_paths | related_prompts |
|----------|-------------|----------------|
| `email_generation` | `["reply_draft", "generate_email"]` | `[]` |
| 其他 | `["{type}"]` | `[]` |

`email_generation` 类型比较特殊：它直接更新两个 prompt（`reply_draft.txt` 和 `generate_email.txt`），不使用 related_prompts 机制。

- 前缀 `(ClawMail-Personalization)` 供 OpenClaw 识别并路由到 `clawmail-personalization` skill
- agent ID `personalizationAgent001` 让 OpenClaw 在同一个对话上下文中关联处理所有用户偏好数据
- 异步发送（`asyncio.ensure_future`），不阻塞 UI
- 所有反馈类型复用同一个 `_trigger_personalization(prompt_type)` 方法

#### REST API 端点（供 OpenClaw skill 回调）

ClawMail 的本地 HTTP API（`127.0.0.1:9999`）提供以下端点，供 OpenClaw skill 在执行过程中读写数据：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/personalization/feedback/{type}` | GET | 读取反馈数据（返回 JSON 数组） |
| `/personalization/prompt/{type}` | GET | 读取当前 prompt 内容 |
| `/personalization/update-prompt` | POST | 备份旧 prompt 到 `archive/` 并写入新版本 |
| `/personalization/archive-feedback` | POST | 归档已消费反馈到 `feedback/{type}/` 并清空主文件 |
| `/personalization/status` | POST | skill 完成后回调，通知 UI 显示更新成功消息 |

Skill 执行流程对应的 API 调用顺序（以 `{type}` 代指具体反馈类型）：
```
1. GET  /personalization/feedback/{type}              ← 读取反馈
2. GET  /personalization/prompt/{type}                ← 读取当前 prompt
3. （OpenClaw 内部：调取用户侧写 + 大模型分析 + 生成新 prompt）
4. POST /personalization/update-prompt                ← 备份旧 + 写入新 prompt
   body: {"prompt_type": "{type}", "content": "新的标准..."}
5. POST /personalization/archive-feedback              ← 归档反馈
   body: {"feedback_type": "{type}"}
6. POST /personalization/status                        ← 通知完成
   body: {"prompt_type": "{type}", "success": true}
```

REST API 端点已设计为通用，`{type}` 路径参数支持所有反馈类型（`importance_score`、`category`、`is_spam`、`action_category`、`reply_stances`、`summary`、`email_generation`、`polish_email`），无需新增端点。`email_generation` 类型通过 `prompt_paths` 字段同时操作 `reply_draft.txt` 和 `generate_email.txt` 两个 prompt 文件。

### 触发流程总览（通用）

```
用户操作触发反馈（修改评分 / 编辑分类 / 标记垃圾 / 修改行动项分类 / 选择回复立场
                  / 评价摘要 / 发送 AI 生成的邮件 / 发送润色邮件）
    │
    ├── 更新数据库对应字段
    ├── 记录反馈到 feedback_{type}.jsonl（按唯一键去重）
    ├── 刷新 UI
    │
    └── 检查 feedback_{type} 反馈数 ≥ 5？
         │ 是
         ▼
    _trigger_personalization("{type}")
         │
         ├── 保险归档：备份当前反馈文件和 prompt 文件
         ▼
    user_chat(trigger_msg, "personalizationAgent001")
    （消息中包含 prompt_paths 和 related_prompts 字段）
         │
         ▼
    OpenClaw 收到消息 → 路由到 clawmail-personalization skill
         │
         ▼
    Skill 通过 REST API 读取反馈 + 当前 prompt + 关联 prompt
         │
         ▼
    大模型分析用户偏好 → 生成个性化 prompt（含关联 prompt）
         │
         ▼
    Skill 通过 REST API 写入新 prompt + 关联 prompt + 归档旧反馈
         │
         ▼
    POST /personalization/status → UI 显示 "✅ {type} 个性化更新完成"
         │
         ▼
    下次 AI 操作时加载更新后的 prompt → 输出更符合用户预期
```

