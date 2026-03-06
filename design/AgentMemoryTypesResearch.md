# AI Agent Memory Types: Recent Research (2025–2026)

**Date:** 2026-03-03
**Focus:** Procedural Memory, Semantic Memory, and Episodic Memory in LLM-based AI agents — storage, retrieval, and architecture.

---

## Table of Contents

1. [Memory Type Overview](#memory-type-overview)
2. [Foundational Surveys](#foundational-surveys)
3. [Episodic Memory](#episodic-memory)
4. [Semantic Memory](#semantic-memory)
5. [Procedural Memory](#procedural-memory)
6. [Unified / All-Three Architectures](#unified--all-three-architectures)
7. [Key Theme: Memory Consolidation Pipeline](#key-theme-memory-consolidation-pipeline)
8. [Storage & Retrieval Approaches Summary](#storage--retrieval-approaches-summary)
9. [References](#references)

---

## Memory Type Overview

| Type | What It Stores | Human Analogy | Agent Equivalent |
|---|---|---|---|
| **Episodic** | Time-stamped events, specific experiences | "I remember when..." | Interaction logs, trajectories, past task outcomes |
| **Semantic** | Abstract facts, general knowledge | "I know that..." | User profiles, world knowledge, entity relationships |
| **Procedural** | How to do things, skills, habits | "I know how to..." | Executable workflows, skills, reusable tool-use patterns |

---

## Foundational Surveys

### Memory in the Age of AI Agents
- **arXiv:** [2512.13564](https://arxiv.org/abs/2512.13564) | Dec 2025
- **Coverage:** Comprehensive taxonomy of memory types, mechanisms, and architectures for LLM agents
- **Paper list:** [GitHub - Agent-Memory-Paper-List](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)

### From Human Memory to AI Memory: A Survey
- **arXiv:** [2504.15965](https://arxiv.org/html/2504.15965v1) | 2025
- **Coverage:** Maps cognitive neuroscience memory types directly to LLM agent architectures; how memory is formed, evolved, and retrieved over time
- **Taxonomy:** Factual, experiential, and working memory

### AI Meets Brain: Memory Systems from Cognitive Neuroscience to Agents
- **arXiv:** [2512.23343](https://arxiv.org/html/2512.23343v1) | Dec 2025
- **Coverage:** Unified survey bridging neuroscience and AI agent memory design

### Agent Skills from the Perspective of Procedural Memory (Survey)
- **Source:** [TechRxiv](https://www.techrxiv.org/users/1016212/articles/1376445/master/file/data/Agent_Skills/Agent_Skills.pdf)
- **Coverage:** Surveys agent skill acquisition and storage specifically through the lens of procedural memory

### ICLR 2026 Workshop: MemAgents
- **Source:** [OpenReview](https://openreview.net/pdf?id=U51WxL382H)
- **Note:** Dedicated ICLR 2026 workshop on memory for LLM-based agentic systems — signals memory is now a primary research focus

---

## Episodic Memory

### Position: Episodic Memory is the Missing Piece for Long-Term LLM Agents
- **arXiv:** [2502.06975](https://arxiv.org/pdf/2502.06975) | Feb 2026
- **Argument:** Episodic memory is the most underserved memory type in current agents
- **Storage approach:** External memory store with time-stamped, context-rich event records
- **Key insight:** Without episodic memory, agents cannot recall *what happened* in prior interactions — only what they generally know

### Synapse: Episodic-Semantic Memory via Spreading Activation
- **arXiv:** [2601.02744](https://arxiv.org/html/2601.02744v1) | Jan 2026
- **Innovation:** Unified episodic-semantic graph with dual-layer topology
- **Storage:** Graph structure linking episodic events to semantic concepts
- **Retrieval:** Spreading activation (relevance propagates through graph) + lateral inhibition (suppresses redundant results)

### Episodic Memories Generation and Evaluation Benchmark
- **arXiv:** [2501.13121](https://arxiv.org/html/2501.13121v1) | Jan 2025
- **Contribution:** First dedicated benchmark for generating and evaluating episodic memory quality in LLMs
- **Use:** Standardizes evaluation of how well agents form and recall episodic memories

### MemRL: Self-Evolving Agents via RL on Episodic Memory
- **Published:** Jan 2026 | [Agent-Memory-Paper-List](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)
- **Innovation:** Agents use reinforcement learning to improve their own episodic memory storage strategies over time
- **Storage:** External episodic memory bank, updated via RL policy

---

## Semantic Memory

### Synapse (see Episodic section)
- Also covers semantic memory as the second layer of the episodic-semantic graph
- Semantic nodes represent abstract, time-independent facts linked to episodic events

### A Survey on the Memory Mechanism of LLM-based Agents
- **Source:** [ACM Transactions on Information Systems](https://dl.acm.org/doi/10.1145/3748302)
- **Coverage:** Semantic memory defined as abstract knowledge independent of specific time or events; survey of storage and retrieval methods

### From Storage to Experience: Evolution of LLM Agent Memory
- **Source:** [Preprints.org](https://www.preprints.org/manuscript/202601.0618) | 2026
- **Framework:** Three-stage evolution — Storage (raw data) → Reflection (refinement) → Experience (abstraction to semantic/procedural)

---

## Procedural Memory

### Learning Hierarchical Procedural Memory via Bayesian Selection and Contrastive Refinement
- **arXiv:** [2512.18950](https://arxiv.org/html/2512.18950v1) | Dec 2025
- **Innovation:** Hierarchical skill storage; Bayesian selection determines which procedures to retain vs. discard
- **Storage:** Hierarchical tree of reusable procedure templates
- **Retrieval:** Contrastive refinement to select the most task-relevant procedure

### Procedural Memory Is Not All You Need: Bridging Cognitive Gaps in LLM-Based Agents
- **arXiv:** [2505.03434](https://arxiv.org/abs/2505.03434) | May 2025
- **Argument:** Pure procedural memory constrains adaptability in environments with shifting rules
- **Proposal:** Hybrid integration of procedural + semantic + associative memory

### Real-Time Procedural Learning From Experience for AI Agents
- **arXiv:** [2511.22074](https://arxiv.org/html/2511.22074) | Nov 2025
- **Innovation:** Agents learn new procedures on-the-fly during task execution, not only offline
- **Storage:** Dynamically updated procedure library from runtime experience

### A Benchmark for Procedural Memory Retrieval in Language Agents
- **arXiv:** [2511.21730](https://arxiv.org/html/2511.21730v1) | Nov 2025
- **Contribution:** First dedicated benchmark for measuring procedural memory retrieval quality and accuracy

### Synthesizing Procedural Memory: Challenges
- **arXiv:** [2512.20278](https://arxiv.org/pdf/2512.20278) | Dec 2025
- **Key insight:** The optimal representation for procedural memory is **executable, deterministic code** — not natural language instructions
- **Pattern:** Search → Evaluate → Refine loop for synthesizing procedures

### MACLA (Memory-Augmented Continual Learning Agent)
- **Source:** [Agent-Memory-Paper-List](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)
- **Innovation:** Decouples reasoning (frozen LLM) from learning (external hierarchical procedural memory)
- **Storage:** Hierarchical external procedural memory updated without touching LLM weights

---

## Unified / All-Three Architectures

### MIRIX: Multi-Agent Memory System for LLM-Based Agents
- **arXiv:** [2507.07957](https://arxiv.org/abs/2507.07957) | July 2025
- **GitHub:** [Mirix-AI/MIRIX](https://github.com/Mirix-AI/MIRIX)
- **Memory types:** 6 components — **Core**, **Episodic**, **Semantic**, **Procedural**, **Resource**, **Knowledge Vault**
- **Architecture:** Multi-agent framework with specialized agents managing each memory type
- **Storage:** Structured modular stores per memory type; supports multimodal data
- **Performance:**
  - ScreenshotVQA: **+35% accuracy** over RAG baseline
  - Storage: **99.9% reduction** vs. naive approaches
  - LOCOMO benchmark: **85.4% SOTA**

### A-MEM: Agentic Memory for LLM Agents
- **arXiv:** [2502.12110](https://arxiv.org/abs/2502.12110) | Feb 2026
- **Innovation:** Zettelkasten-inspired dynamic memory organization
- **Storage:** Interconnected knowledge networks with dynamic indexing and linking between memory notes
- **Key property:** Memory structure evolves as new information is added — links form automatically

### Human-Like Remembering and Forgetting (ACT-R-Inspired)
- **Source:** [ACM HAI 2025](https://dl.acm.org/doi/10.1145/3765766.3765803)
- **Innovation:** Adapts the cognitive architecture ACT-R for LLM agents
- **Models:** Forgetting curves alongside remembering — old, unused memories decay
- **All three types:** ACT-R natively encodes episodic, semantic, and procedural memory with activation-based retrieval

### Agentic Memory: Unified Long-Term and Short-Term Memory Management
- **Published:** Jan 2026 | [Agent-Memory-Paper-List](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)
- **Innovation:** Unified framework managing both short-term (episodic) and long-term (semantic + procedural) memory under one architecture

---

## Key Theme: Memory Consolidation Pipeline

A recurring insight across papers: memory should **evolve across types** over time, mirroring human memory consolidation:

```
Episodic → Semantic → Procedural
  ↓             ↓           ↓
"What       "How things  "How to
happened"   work"        do it"
```

**Three-stage pipeline** (proposed in multiple papers):
1. **Storage** — Preserve raw experience trajectories (episodic)
2. **Reflection** — Refine and abstract patterns from experiences (episodic → semantic)
3. **Experience** — Abstract into reusable, executable skills (semantic → procedural)

---

## Storage & Retrieval Approaches Summary

| Memory Type | Common Storage | Common Retrieval |
|---|---|---|
| **Episodic** | Time-stamped event logs, vector DB with recency weighting | Recency + importance filtering + embedding similarity |
| **Semantic** | Knowledge graphs, vector DB, key-value stores | Semantic similarity search, graph traversal |
| **Procedural** | Executable code/script libraries, hierarchical skill trees | Task-conditioned lookup, Bayesian selection, contrastive retrieval |
| **Unified** | Hybrid multi-store (e.g., MIRIX's 6-component system) | Multi-agent coordination across stores |

**Key storage insight from [arXiv 2512.20278](https://arxiv.org/pdf/2512.20278):**
> Procedural memory is best stored as **executable code**, not natural language — code is deterministic, testable, and reusable without re-interpretation by LLM.

---

## References

| Paper | arXiv / Source | Year |
|---|---|---|
| Memory in the Age of AI Agents | [2512.13564](https://arxiv.org/abs/2512.13564) | 2025 |
| From Human Memory to AI Memory: A Survey | [2504.15965](https://arxiv.org/html/2504.15965v1) | 2025 |
| AI Meets Brain: Cognitive Neuroscience to Agents | [2512.23343](https://arxiv.org/html/2512.23343v1) | 2025 |
| Episodic Memory is the Missing Piece | [2502.06975](https://arxiv.org/pdf/2502.06975) | 2026 |
| Synapse: Episodic-Semantic via Spreading Activation | [2601.02744](https://arxiv.org/html/2601.02744v1) | 2026 |
| Episodic Memories Generation and Evaluation Benchmark | [2501.13121](https://arxiv.org/html/2501.13121v1) | 2025 |
| MIRIX: Multi-Agent Memory System | [2507.07957](https://arxiv.org/abs/2507.07957) | 2025 |
| A-MEM: Agentic Memory for LLM Agents | [2502.12110](https://arxiv.org/abs/2502.12110) | 2026 |
| Hierarchical Procedural Memory | [2512.18950](https://arxiv.org/html/2512.18950v1) | 2025 |
| Procedural Memory Is Not All You Need | [2505.03434](https://arxiv.org/abs/2505.03434) | 2025 |
| Real-Time Procedural Learning From Experience | [2511.22074](https://arxiv.org/html/2511.22074) | 2025 |
| Benchmark for Procedural Memory Retrieval | [2511.21730](https://arxiv.org/html/2511.21730v1) | 2025 |
| Synthesizing Procedural Memory | [2512.20278](https://arxiv.org/pdf/2512.20278) | 2025 |
| Human-Like Remembering and Forgetting (ACT-R) | [ACM HAI 2025](https://dl.acm.org/doi/10.1145/3765766.3765803) | 2025 |
| ACM Survey on Memory Mechanism of LLM Agents | [ACM TOIS](https://dl.acm.org/doi/10.1145/3748302) | 2025 |
| Agent Skills from Procedural Memory (Survey) | [TechRxiv](https://www.techrxiv.org/users/1016212/articles/1376445/master/file/data/Agent_Skills/Agent_Skills.pdf) | 2025 |
| ICLR 2026 Workshop: MemAgents | [OpenReview](https://openreview.net/pdf?id=U51WxL382H) | 2026 |
| GitHub: Agent-Memory-Paper-List | [GitHub](https://github.com/Shichun-Liu/Agent-Memory-Paper-List) | — |

---

*Compiled 2026-03-03. For ClawMail memory architecture reference.*
