# OpenClaw Memory Systems: Research Report

**Date:** 2026-03-03
**Purpose:** Understand OpenClaw memory architecture, known issues, and community solutions for ClawMail skill integration.

---

## 1. Architecture

OpenClaw uses **Markdown files + SQLite vector search** for memory persistence:

- **`MEMORY.md`** — long-term curated facts, loaded in private sessions
- **`memory/YYYY-MM-DD.md`** — daily append-only logs; today's and yesterday's are auto-loaded at session start
- **`memory_search`** — semantic recall over indexed snippets (hybrid BM25 + vector)
- **`memory_get`** — targeted file reads with line-range support

### Vector Search Details
- ~400-token chunks with 80-token overlap, stored in SQLite via `sqlite-vec`
- Hybrid search: BM25 keyword + vector similarity
- Optional MMR re-ranking for diversity
- Temporal decay: 30-day half-life favoring recent notes (`MEMORY.md` exempt)
- Auto-selects embedding provider: local models → OpenAI → Gemini → Voyage → Mistral

### Context Compaction
As sessions approach the context limit, OpenClaw triggers a "pre-compaction ping" — a silent agentic turn prompting the model to write durable memories to disk before context resets. This is **opt-in** and disabled by default.

### Experimental: QMD Backend
A local-first search sidecar combining BM25, vectors, and reranking. Uses `better-sqlite3` instead of the standard `sqlite3`/`mem0` stack. Runs via Bun, downloads GGUF models from HuggingFace automatically.

---

## 2. Critical Open Issues

### Issue #31677 — SQLite Bindings Broken After 2026.3.1 Update
**Status:** Open (regression)
**Severity:** 🔴 High — memory tools non-functional

`memory_search`, `memory_list`, and `memory_get` all fail with a native bindings error after the 2026.3.1 update. Root cause: `jiti` (v2.6.1) incorrectly resolves native module paths when importing `sqlite3`. The `bindings` package searches relative to `jiti`'s directory tree instead of `sqlite3`'s actual installation path.

**Workaround:** Use `qmd search "query"` instead — QMD uses `better-sqlite3` and is unaffected.

Source: [Issue #31677](https://github.com/openclaw/openclaw/issues/31677)

---

### Discussion #25633 — Memory Is Broken By Default
**Status:** Open
**Severity:** 🔴 High — silent data loss

`memoryFlush` ships **disabled** in the default config. Without it, agents fill their context, compact, and lose information with no persistent fallback. Enabling it properly reduced one user's token costs from $4.20/day to $1.80/day.

**Fix:**
```json
// ~/.openclaw/openclaw.json
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

Source: [Discussion #25633](https://github.com/openclaw/openclaw/discussions/25633)

---

### Issue #17034 — `memoryFlush.softThresholdTokens` Doesn't Scale with Context Window
**Status:** Open
**Severity:** 🟡 Medium — affects large-context models

`softThresholdTokens` is an absolute value (default: 4,000). With a 1M context model, the flush threshold becomes ~976K tokens — far beyond the actual compaction point (~170K). The flush mechanism never activates, silently losing pre-compaction memory protection.

**Proposed fixes:**
1. Percentage-based: `softThresholdRatio: 0.15`
2. Auto-scaling: `max(4000, contextWindow * 0.15)`

**Manual workaround:** Set `softThresholdTokens: 850000` explicitly for large-context models.

Source: [Issue #17034](https://github.com/openclaw/openclaw/issues/17034)

---

### Issue #32363 — Agent Date Awareness Lost Post-Compaction
**Status:** Open
**Severity:** 🟡 Medium

Agents do not know the current date on `/new`, `/reset`, or post-compaction. Date substitution in `AGENTS.md` files is not working properly, breaking agents that rely on temporal reasoning.

Source: [Issue #32363](https://github.com/openclaw/openclaw/issues/32363)

---

### Issue #9157 / Discussion #26472 — Workspace Files Consume 93.5% of Token Budget
**Status:** Open
**Severity:** 🔴 High — cost impact

Workspace files (including memory files) are re-injected on every single message, consuming ~35,600 tokens per message in complex workspaces. Part of "The 20 Biggest OpenClaw Problems in 2026" discussion.

Source: [Discussion #26472](https://github.com/openclaw/openclaw/discussions/26472)

---

### Issue #32421 — Enhanced LanceDB Memory Plugin
**Status:** Open (enhancement request, 2026-03-03)

Feature request to improve capabilities of the LanceDB memory plugin.

Source: [Issue #32421](https://github.com/openclaw/openclaw/issues/32421)

---

## 3. Structural / Architectural Limitations

### 3.1 Lossy Context Compaction
Compaction summarizes older context to save tokens. Any data in the context window — memory file contents, active reasoning — may be compressed or dropped. The pre-compaction ping helps but does not fully prevent loss.

### 3.2 No Relationship Reasoning
Vector search retrieves facts but cannot reason about relationships between them. Classic failure: agent stores "Alice manages the auth team" and "auth permissions require senior review" separately, but cannot connect them to answer "who approves auth permission changes?" even when both chunks are retrieved.

### 3.3 Stale Memory Can Outrank Fresh Data
Old entries with high semantic similarity can outrank recent, more relevant entries. The 30-day decay is applied **post-retrieval**, not pre-retrieval, so old high-confidence matches still surface in the raw result set.

### 3.4 Cross-Project Memory Bleeding
`memory_search` can return results from unrelated project contexts in long sessions. Memory is not isolated by project or workspace by default.

### 3.5 Token Budget Inflation
As `MEMORY.md` and daily notes grow, `memory_search` returns increasingly large context. Users who inject near-complete memory files "to avoid missing something" defeat the purpose of retrieval and inflate token costs.

### 3.6 Statelessness Between Sessions
Agents are stateless between sessions. Continuity depends entirely on what gets re-read from disk at startup and what was written during the prior session.

---

## 4. Community Solutions and Plugins

### 4.1 Mem0 Plugin
Solves: lost context after resets, history truncation, flaky behavior across sessions.

**How it works:**
- **Auto-Recall:** Before each agent response, searches its store for memories relevant to the current message and injects matches into working context
- **Auto-Store:** After each turn, extracts and stores new information in Mem0's persistent store

Gives agents cross-session memory without relying on OpenClaw's context window or compaction.

Source: [Mem0 for OpenClaw](https://mem0.ai/blog/mem0-memory-for-openclaw)

---

### 4.2 Cognee Plugin (Knowledge Graph Augmentation)
Solves: no relational reasoning between stored facts.

Replaces flat vector search with a knowledge graph layer. Extracts entities and relationships, enabling traversal for structured answers (e.g., `Alice -> manages -> Auth team`).

**Architecture:**
- Lifecycle hooks: `before_agent_start` (recall injection), `agent_end` (incremental indexing)
- Two-phase sync: initial full index on startup, then incremental updates after each run
- Does not replace Markdown files — they remain editable while being indexed into the graph

Source: [Cognee + OpenClaw Integration](https://www.cognee.ai/blog/integrations/what-is-openclaw-ai-and-how-we-give-it-memory-with-cognee)

---

### 4.3 QMD (Built-in Experimental Backend)
Solves: Issue #31677 (SQLite bindings regression).

Uses `better-sqlite3` (immune to the jiti bug), runs locally via Bun, auto-downloads GGUF reranking models. Combines BM25, vectors, and reranking. Currently the most stable retrieval backend post-2026.3.1.

---

### 4.4 Local RAG Plugin Proposal (Discussion #30090)
**Status:** Under community discussion, not merged.

**Architecture:**
- Embeddings: `BAAI/bge-small-en-v1.5`
- Keyword search: `rank-bm25`
- Re-ranking: `cross-encoder/ms-marco-MiniLM-L-6-v2`
- Result merging: Reciprocal Rank Fusion (RRF)
- Tiered indexing: Tier 1 (real-time: MEMORY.md + daily notes), Tier 2 (overnight: session summaries)
- Parent-child chunking: ~75-token child chunks for precision, ~375-token parent for context

**Reported performance (Intel N150, CPU-only):**
- Retrieval: 12–39ms
- Re-ranking: ~150ms overhead
- Token reduction vs. full-context injection: ~93%

Source: [Discussion #30090](https://github.com/openclaw/openclaw/discussions/30090)

---

### 4.5 Signet Plugin
SQLite-based hybrid search with automatic importance scoring and time-based decay. Provides automatic context injection based on conversation relevance, eliminating manual `MEMORY.md` management.

---

## 5. Issue Summary Table

| Issue | Category | Severity | Status |
|---|---|---|---|
| #31677 — SQLite bindings broken (2026.3.1) | Bug | 🔴 High | Open |
| #25633 — Memory disabled by default | Config | 🔴 High | Open discussion |
| #9157 / #26472 — Workspace eats 93.5% token budget | Performance | 🔴 High | Open |
| #17034 — softThresholdTokens doesn't scale | Bug | 🟡 Medium | Open |
| #32363 — Date lost post-compaction | Bug | 🟡 Medium | Open |
| Cross-project memory bleeding | Architecture | 🟡 Medium | No fix |
| No relational reasoning | Architecture | 🔴 High | Plugin workaround (Cognee) |
| Stale memory ranking | Architecture | 🟡 Low-Medium | No fix |
| #32421 — LanceDB plugin enhancement | Enhancement | 🟢 Low | Open |

---

## 6. Sources

- [OpenClaw Memory Docs](https://docs.openclaw.ai/concepts/memory)
- [OpenClaw Memory Is Broken. Here's How to Fix It — Daily Dose of DS](https://blog.dailydoseofds.com/p/openclaws-memory-is-broken-heres)
- [OpenClaw Memory Systems That Don't Forget — Agent Native / Medium](https://agentnativedev.medium.com/openclaw-memory-systems-that-dont-forget-qmd-mem0-cognee-obsidian-4ad96c02c9cc)
- [Discussion #26472 — 20 Biggest OpenClaw Problems in 2026](https://github.com/openclaw/openclaw/discussions/26472)
- [Discussion #25633 — Memory Broken By Default](https://github.com/openclaw/openclaw/discussions/25633)
- [Discussion #30090 — Local RAG Memory Plugin](https://github.com/openclaw/openclaw/discussions/30090)
- [Issue #31677](https://github.com/openclaw/openclaw/issues/31677)
- [Issue #17034](https://github.com/openclaw/openclaw/issues/17034)
- [Issue #32421](https://github.com/openclaw/openclaw/issues/32421)
- [Issue #32363](https://github.com/openclaw/openclaw/issues/32363)
- [Cognee + OpenClaw Integration Guide](https://www.cognee.ai/blog/integrations/what-is-openclaw-ai-and-how-we-give-it-memory-with-cognee)
- [Mem0 for OpenClaw](https://mem0.ai/blog/mem0-memory-for-openclaw)
