# OpenClaw Agent 记忆系统：现状、缺口与未来改进

**日期：** 2026-03-04
**作者：** AI 分析报告
**参考来源：** OpenClawMemoryResearch.md · AgentMemoryTypesResearch.md · OpenClaw Issues/Discussions

---

## 目录

1. [背景与评估框架](#1-背景与评估框架)
2. [已实现的记忆能力](#2-已实现的记忆能力)
3. [已知缺口与未实现能力](#3-已知缺口与未实现能力)
4. [未来改进方向与实现方案](#4-未来改进方向与实现方案)
5. [优先级路线图](#5-优先级路线图)
6. [参考文献](#6-参考文献)

---

## 1. 背景与评估框架

OpenClaw 是一款本地运行的 AI 代理平台，通过 Markdown 文件与 SQLite 向量数据库的组合，为 agent 提供跨会话记忆能力。记忆系统是 agent 实现长期个性化、持续学习与上下文感知的核心基础设施。

### 1.1 记忆类型分类框架

本报告使用认知科学与 AI 研究领域通行的三类记忆框架进行评估：

| 类型 | 存储内容 | 人类类比 | Agent 等价物 |
|------|---------|---------|------------|
| **情节记忆（Episodic）** | 带时间戳的具体事件与交互历史 | "我记得当时…" | 对话日志、任务执行轨迹、历史结果 |
| **语义记忆（Semantic）** | 抽象事实、通用知识、实体关系 | "我知道…" | 用户画像、世界知识、联系人关系 |
| **程序记忆（Procedural）** | 如何执行任务的技能与工作流 | "我知道怎么做…" | 可执行工作流、skill 模板、工具调用模式 |

前沿研究（arXiv 2512.13564、ICLR 2026 MemAgents Workshop）表明，三类记忆相互补充，最先进的 agent 系统（如 MIRIX）已将六种记忆组件统一管理，并在基准测试上取得 +35% 的精度提升。

---

## 2. 已实现的记忆能力

### 2.1 记忆存储架构

OpenClaw 的记忆系统由三个存储层构成：

**长期事实文件：`MEMORY.md`**
- 存储用户手动维护或 agent 提炼的持久性事实
- 每次私有会话启动时自动注入到上下文
- 人工可编辑，支持直接干预与修正
- 不受时间衰减影响（`MEMORY.md` exempt from decay）

**每日情节日志：`memory/YYYY-MM-DD.md`**
- 每日 append-only 追加日志，记录当天的交互事件
- 会话启动时自动加载当天与昨日的日志文件
- 提供近期情节记忆的时序上下文

**向量检索后端：`sqlite-vec`**
- 使用 SQLite 存储向量嵌入，约 400-token 分块，80-token 重叠
- 混合检索：BM25 关键词精确匹配 + 向量语义召回
- 可选 MMR 重排（Maximal Marginal Relevance，提高结果多样性）
- 自动选择嵌入提供商：本地模型 → OpenAI → Gemini → Voyage → Mistral

### 2.2 检索机制

**`memory_search`：** 对全部记忆文件执行语义召回，支持关键词与向量混合查询
**`memory_get`：** 支持行号范围的精确文件读取，用于定向获取特定记忆片段
**时间衰减：** 30 天半衰期，近期记忆自动获得更高权重（`MEMORY.md` 豁免）

### 2.3 记忆生命周期管理

**自动写入：** agent 在对话过程中可随时调用工具将新信息写入记忆文件，实现持续学习

**Context Compaction 前刷写（`memoryFlush`）：**
当会话接近上下文限制时，OpenClaw 触发"pre-compaction ping"——一次静默的 agentic 轮次，提示模型在上下文压缩重置前将重要信息写入磁盘。机制设计完整，属于平台级保护措施。

**Workspace 隔离：** 不同 workspace 拥有独立的记忆空间，支持多项目并行运行

**实验性后端：QMD**
一个本地优先的搜索侧车（sidecar），组合 BM25、向量检索与重排序（reranking），使用 `better-sqlite3` 代替标准 `sqlite3` 栈，通过 Bun 运行，自动从 HuggingFace 下载 GGUF 重排模型。

### 2.4 记忆类型覆盖情况（现状）

| 记忆类型 | OpenClaw 实现 | 实现方式 |
|---------|-------------|---------|
| 情节记忆 | ✅ 部分实现 | 每日日志文件（`memory/YYYY-MM-DD.md`） |
| 语义记忆 | ✅ 部分实现 | `MEMORY.md` 长期事实 + 向量检索 |
| 程序记忆 | ❌ 未实现 | 无原生 skill/workflow 存储机制 |

---

## 3. 已知缺口与未实现能力

### 3.1 平台级 Bug（已知 Issues）

**🔴 Issue #31677 — SQLite 绑定在 2026.3.1 后损坏**
`memory_search`、`memory_list`、`memory_get` 全部因 native bindings 错误而无法工作。根本原因：`jiti`（v2.6.1）在导入 `sqlite3` 时错误地解析原生模块路径，`bindings` 包相对于 jiti 目录树而非 `sqlite3` 实际安装路径进行搜索。
**临时方案：** 使用 `qmd search "query"` 替代（QMD 使用 `better-sqlite3`，不受影响）。

**🔴 Discussion #25633 — 记忆系统默认禁用，静默数据丢失**
`memoryFlush` 在默认配置中处于禁用状态。未启用时，agent 填满上下文、触发压缩、丢失信息，全程无任何警告或降级提示。这是最高优先级的可靠性缺陷——功能设计完整，但配置默认值有误。
启用后实测效果：某用户 token 成本从 $4.20/天降至 $1.80/天（节省 57%）。

**🟡 Issue #17034 — `softThresholdTokens` 固定值不随上下文窗口扩展**
默认值 `softThresholdTokens: 4000`。对于 1M token 上下文窗口的大模型，实际压缩触发点约为 170K tokens，而刷写阈值是 `1M - 4000 ≈ 996K`，永远无法到达——`memoryFlush` 即使配置开启也形同虚设。

**🟡 Issue #32363 — Context Compaction 后 Agent 日期感知丢失**
执行 `/new`、`/reset` 或 post-compaction 后，agent 不知道当前日期。`AGENTS.md` 文件中的日期变量替换未能正确工作，导致依赖时序推理的 agent 行为异常。

### 3.2 Token 预算膨胀

**🔴 Issue #9157 / Discussion #26472 — Workspace 文件占用 93.5% Token 预算**
复杂 workspace 的文件（包括记忆文件）在每条消息时都被重新注入，约 35,600 tokens/条消息。这被列入"2026 年 OpenClaw 最大的 20 个问题"之一，直接影响使用成本与实际可用上下文窗口。

### 3.3 架构级缺陷

**无关系推理能力（知识图谱缺失）**
向量检索能找到相关事实片段，但无法推断片段之间的结构关系。典型失败案例：agent 分别存储了"Alice 管理 auth 团队"和"auth 权限需要高级审查"，但面对"谁负责审批 auth 权限变更？"这一问题时无法作出正确推断——即便两个相关片段都已被检索出来。

**陈旧记忆排名高于新鲜记忆**
30 天时间衰减在检索**之后**才生效，而非在检索过程中。旧的、语义相似度高的记忆条目依然能在原始结果集中名列前茅，导致过时信息干扰 agent 判断。

**跨项目记忆污染**
在长会话中，`memory_search` 可能返回来自无关项目上下文的记忆片段。记忆系统默认不按项目或 workspace 隔离检索结果。

**Token 预算膨胀的正反馈循环**
随着 `MEMORY.md` 与每日日志不断增长，`memory_search` 返回的上下文也随之膨胀。部分用户为"避免遗漏信息"而注入近乎完整的记忆文件，彻底失去了检索的意义，反而加剧了 token 成本。

### 3.4 记忆类型覆盖缺口

**程序记忆完全缺失**
OpenClaw 没有原生的 skill 或 workflow 存储机制。前沿研究（arXiv 2512.20278）表明，程序记忆的最优表示是**可执行代码**而非自然语言描述，但平台目前无法持久化任何结构化的操作模式。

**情节记忆质量未量化**
每日日志以纯文本追加存储，没有结构化的事件表示、重要性评分或专项评估基准。研究（arXiv 2501.13121）已有专门的情节记忆质量基准，但平台尚未集成。

**跨会话的连续性依赖人工维护**
Agent 会话间完全无状态。连续性完全取决于上一个会话写入了什么、当前会话从磁盘读取了什么。高质量的跨会话记忆依赖用户或 agent 的主动整理，缺乏自动化机制。

---

## 4. 未来改进方向与实现方案

### 4.1 修复 `memoryFlush` 默认行为 ⭐ P0

**问题：** 最关键的记忆保护机制默认禁用，造成静默数据丢失。
**方案：** 将 `memoryFlush` 默认值改为 `true`，并在 settings UI 中增加显式关闭选项与风险说明。
**实现：**
```json
// 建议的默认配置 (~/.openclaw/openclaw.json)
{
  "agents": {
    "defaults": {
      "memory": {
        "enabled": true,
        "memoryFlush": true,
        "softThresholdTokens": 40000
      }
    }
  }
}
```
**预期收益：** 消除静默数据丢失，实测可降低 token 成本约 57%。

---

### 4.2 `softThresholdTokens` 动态比例化 ⭐ P0

**问题：** 固定阈值在大上下文窗口模型（1M+ tokens）下永远无法触发刷写。
**方案：** 将绝对值改为相对比例，按实际上下文窗口大小动态计算：

```
softThresholdTokens = max(4000, contextWindow * threshold_ratio)
```

**建议配置扩展：**
```json
{
  "memory": {
    "softThresholdRatio": 0.15,    // 新增：比例模式
    "softThresholdTokens": 40000   // 保留：绝对值作为最小值保底
  }
}
```

计算逻辑：`effective_threshold = max(softThresholdTokens, contextWindow * softThresholdRatio)`

---

### 4.3 Pre-retrieval 时间衰减评分 ⭐ P1

**问题：** 30 天衰减在检索后才生效，旧的高相似度记忆仍排名靠前。
**方案：** 在向量检索阶段引入综合评分，将时间衰减前置：

```
composite_score = semantic_similarity × exp(-Δdays / half_life)
```

**实现步骤：**
1. 在 `sqlite-vec` 查询中为每条记忆计算 `days_since_update`
2. 计算综合分 `score = similarity * exp(-Δdays / 30)`
3. 按综合分排序，截取 top-K 结果（K 可配置，限制注入 token 数）

**效果：** 新鲜的相关记忆会比旧的高相似度记忆排名更靠前，改善 agent 的时序判断。

---

### 4.4 知识图谱关系推理 ⭐ P1

**问题：** 平面文本向量存储无法推断实体间的结构关系，导致需要多步推理的问题无法作答。
**方案：** 集成 Cognee 插件，在向量检索之外增加知识图谱层。

**架构：**
```
记忆写入时：
  文本事实 → NLP 实体提取 → (subject, predicate, object) 三元组
                                          ↓
                                   写入图数据库

检索时：
  查询 → 向量召回（现有） + 图遍历（新增）
                                ↓
                         两跳邻居：query_entity → rel → related_entity
```

**Cognee 插件工作方式：**
- `before_agent_start` 钩子：从图中召回并注入相关实体关系
- `agent_end` 钩子：增量索引新写入的记忆
- 不替换 Markdown 文件，保持人工可编辑性

**典型场景改进：**
```
存储：Alice → manages → auth_team
存储：auth_permissions → requires → senior_review

查询："谁审批 auth 权限变更？"
图遍历：auth_permissions → requires → senior_review
         auth_team → managed_by → Alice
推断：Alice（通过 auth_team → managed_by → senior_review 路径）
```

---

### 4.5 分层 Local RAG 索引 ⭐ P1

**问题：** 随着记忆文件增长，全量注入导致 token 预算膨胀（Issue #9157）；当前检索缺乏粒度控制。
**方案：** 实现社区 Discussion #30090 提出的三层索引方案：

```
Tier 1（实时热记忆）：MEMORY.md + 当日/昨日日志  → 直接加载，零延迟
Tier 2（近期语义索引）：最近 7 天会话记录        → BM25 + 向量检索
Tier 3（压缩归档）：更早的历史记忆               → 压缩摘要 + 向量索引
```

**检索流程（按层 fallback）：**
1. 优先从 Tier 1 精确匹配
2. Tier 1 无结果 → 查询 Tier 2（近期语义）
3. 必要时向下穿透到 Tier 3（历史归档）

**核心技术组件（参考 Discussion #30090）：**
- 嵌入模型：`BAAI/bge-small-en-v1.5`
- 关键词检索：`rank-bm25`
- 重排序：`cross-encoder/ms-marco-MiniLM-L-6-v2`
- 结果融合：Reciprocal Rank Fusion (RRF)
- Parent-child 分块：~75-token 子块（精确匹配）+ ~375-token 父块（上下文）

**实测性能（Intel N150 CPU-only）：**
- 检索延迟：12–39ms
- 重排序开销：~150ms
- 相较全量注入，token 减少约 **93%**

---

### 4.6 程序记忆层（Procedural Memory） ⭐ P2

**问题：** OpenClaw 完全缺乏对可重用工作流、skill 模板的原生存储与演化机制。
**方案：** 新增 `procedural/` 记忆目录，以可执行代码形式持久化工作流模板。

**核心原则（arXiv 2512.20278）：**
> 程序记忆的最优表示是**可执行的确定性代码**，而非自然语言描述——代码无需 LLM 重新解释，可直接运行、可测试、可复用。

**实现架构：**
```
~/.openclaw/workspace/procedural/
  ├── send_email_with_review.py     # 具体 workflow 模板
  ├── search_and_summarize.py
  └── index.json                    # 元数据：任务条件、成功次数、最后更新
```

**演化管道（参考情节→语义→程序的三阶段合成）：**
```
情节记忆（每日日志中的高频操作记录）
         ↓ 反思（reflection）
语义记忆（抽象出操作模式与参数）
         ↓ 合成（experience）
程序记忆（生成可执行的参数化 workflow 代码）
```

**召回机制：** 任务执行时，根据任务描述匹配 `index.json` 中的条件标签，选择最相关的 workflow 模板直接执行或作为 prompt 上下文注入。

**参考实现：** MACLA（Memory-Augmented Continual Learning Agent）将程序记忆与 LLM 推理解耦，LLM 冻结权重，学习完全发生在外部程序记忆中——可作为不依赖模型 fine-tuning 的持续学习方案。

---

### 4.7 情节-语义统一图（Synapse 架构） ⭐ P2

**问题：** 每日日志（情节）与 `MEMORY.md`（语义）是两个独立文件，无法相互关联与推理。
**方案：** 参考 Synapse 论文（arXiv 2601.02744）的双层拓扑设计，将情节事件与语义概念连接到同一图结构中。

**检索机制：扩散激活（Spreading Activation）**
- 从查询节点出发，相关性沿图边传播
- 侧抑制（Lateral Inhibition）抑制冗余结果，提高检索多样性
- 情节节点与语义节点均可作为查询起点

**实际收益：** 能够回答跨越情节与语义边界的问题，例如：
"上周我处理的那个 API 问题（情节），通常的解决模式是什么（语义）？"

---

## 5. 优先级路线图

| 优先级 | 改进项 | 实现复杂度 | 预期收益 | 依赖 |
|--------|--------|-----------|---------|------|
| **P0** | 修复 `memoryFlush` 默认值 | 极低（配置变更） | 消除静默数据丢失，降低 57% token 成本 | 无 |
| **P0** | `softThresholdTokens` 动态比例化 | 低（计算逻辑修改） | 兼容 1M+ token 大模型 | 无 |
| **P0** | 修复 Issue #31677 SQLite 绑定 | 中（依赖 jiti 版本修复） | 恢复记忆工具基础功能 | jiti 上游修复 |
| **P1** | Pre-retrieval 时间衰减评分 | 低（SQL 查询修改） | 新鲜记忆优先，改善时序判断 | 无 |
| **P1** | 分层 Local RAG 索引 | 中（索引架构重构） | 93% token 减少，维持召回精度 | 无 |
| **P1** | 知识图谱关系推理（Cognee） | 高（新依赖、钩子集成） | 多步关系推断能力 | Cognee 插件 |
| **P2** | 程序记忆层 | 高（新存储目录 + 合成管道） | Skill 自动演化，无需 fine-tuning | 情节记忆质量提升 |
| **P2** | 情节-语义统一图（Synapse） | 很高（图数据库 + 检索重构） | 跨记忆类型推理 | 知识图谱基础 |

---

## 6. 参考文献

### 平台 Issues & Discussions
- [Issue #31677 — SQLite Bindings Broken After 2026.3.1](https://github.com/openclaw/openclaw/issues/31677)
- [Discussion #25633 — Memory Is Broken By Default](https://github.com/openclaw/openclaw/discussions/25633)
- [Issue #17034 — softThresholdTokens Doesn't Scale](https://github.com/openclaw/openclaw/issues/17034)
- [Issue #32363 — Date Awareness Lost Post-Compaction](https://github.com/openclaw/openclaw/issues/32363)
- [Discussion #26472 — 20 Biggest OpenClaw Problems in 2026](https://github.com/openclaw/openclaw/discussions/26472)
- [Discussion #30090 — Local RAG Memory Plugin](https://github.com/openclaw/openclaw/discussions/30090)
- [Issue #32421 — Enhanced LanceDB Memory Plugin](https://github.com/openclaw/openclaw/issues/32421)

### 社区插件
- [Mem0 for OpenClaw](https://mem0.ai/blog/mem0-memory-for-openclaw)
- [Cognee + OpenClaw Integration](https://www.cognee.ai/blog/integrations/what-is-openclaw-ai-and-how-we-give-it-memory-with-cognee)

### 前沿研究论文（2025–2026）
| 论文 | arXiv | 年份 |
|-----|-------|------|
| Memory in the Age of AI Agents | [2512.13564](https://arxiv.org/abs/2512.13564) | 2025 |
| Episodic Memory is the Missing Piece | [2502.06975](https://arxiv.org/pdf/2502.06975) | 2026 |
| Synapse: Episodic-Semantic via Spreading Activation | [2601.02744](https://arxiv.org/html/2601.02744v1) | 2026 |
| MIRIX: Multi-Agent Memory System | [2507.07957](https://arxiv.org/abs/2507.07957) | 2025 |
| A-MEM: Agentic Memory for LLM Agents | [2502.12110](https://arxiv.org/abs/2502.12110) | 2026 |
| Synthesizing Procedural Memory | [2512.20278](https://arxiv.org/pdf/2512.20278) | 2025 |
| Procedural Memory Is Not All You Need | [2505.03434](https://arxiv.org/abs/2505.03434) | 2025 |
| Hierarchical Procedural Memory | [2512.18950](https://arxiv.org/html/2512.18950v1) | 2025 |
| Real-Time Procedural Learning From Experience | [2511.22074](https://arxiv.org/html/2511.22074) | 2025 |
| Benchmark for Procedural Memory Retrieval | [2511.21730](https://arxiv.org/html/2511.21730v1) | 2025 |
| From Storage to Experience: Evolution of Agent Memory | [Preprints.org](https://www.preprints.org/manuscript/202601.0618) | 2026 |
| Human-Like Remembering and Forgetting (ACT-R) | [ACM HAI 2025](https://dl.acm.org/doi/10.1145/3765766.3765803) | 2025 |
| ICLR 2026 Workshop: MemAgents | [OpenReview](https://openreview.net/pdf?id=U51WxL382H) | 2026 |

### 项目内部文档
- [design/OpenClawMemoryResearch.md](OpenClawMemoryResearch.md) — 平台问题详细分析
- [design/AgentMemoryTypesResearch.md](AgentMemoryTypesResearch.md) — 记忆类型研究综述
