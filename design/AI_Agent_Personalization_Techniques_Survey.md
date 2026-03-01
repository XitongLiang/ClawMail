# AI Agent User Preference Learning & Personalization: Techniques Survey

**Compiled:** 2026-02-28
**Focus:** Closed-loop learning systems, preference elicitation, and adaptive personalization for AI agents

---

## Table of Contents

1. [Overview](#overview)
2. [Core Techniques](#core-techniques)
3. [Academic Research Papers](#academic-research-papers)
4. [Open Source Projects](#open-source-projects)
5. [Memory-Based Approaches](#memory-based-approaches)
6. [Preference Learning Methods](#preference-learning-methods)
7. [Continual Learning & Online Adaptation](#continual-learning--online-adaptation)
8. [Evaluation & Benchmarking](#evaluation--benchmarking)
9. [Comparison Table](#comparison-table)
10. [Future Directions](#future-directions)

---

## Overview

Personalization has become a cornerstone in modern AI systems. Recent research explores how AI agents can learn and adapt to user preferences through closed-loop systems that continuously improve based on user feedback.

**Market Growth:** The AI agent market is projected to grow from $5.1 billion in 2024 to $47.1 billion by 2030, driven by advancements in machine learning, large language models, and automation technologies. ([Source](https://www.labellerr.com/blog/what-are-ai-agents-a-comprehensive-guide/))

**Key Challenge:** Current methods largely rely on implicit preference modeling and offline fine-tuning, which requires extensive historical user data and can be costly to update when preferences change. ([Source](https://arxiv.org/html/2411.00027v3))

---

## Core Techniques

### 1. **Closed-Loop Feedback Systems**

Personalization agents incorporate a feedback loop to continuously improve their recommendations by:
- Analyzing user responses to suggestions
- Refining algorithms to enhance accuracy of future recommendations
- Creating adaptive systems that learn from every interaction

**Source:** [AI Agents for UX Personalization Guide 2025](https://www.rapidinnovation.io/post/ai-agents-for-user-experience-personalization)

---

### 2. **User Preference Modeling Approaches**

#### **A. Memory-Based Approaches**

Recent systems integrate multiple memory types:
- **Working Memory:** Immediate processing
- **Short-term Memory:** Quick access to recent context
- **Long-term Memory:** Key knowledge retention
- **Dual Memory Banks:** Separate short-term and long-term banks that encode events as parametric vector representations

**Sources:**
- [Personalization of Large Language Models: A Survey](https://arxiv.org/html/2411.00027v3)
- [Agent Memory Paper List](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)

#### **B. Retrieval-Augmented Methods**

Retrieval-augmented generation (RAG) enhances LLM performance by:
- Retrieving relevant document segments from external knowledge bases
- Using semantic similarity calculations
- Retrieving personalized information to enable customized outputs

**Source:** [A Survey of Personalized Large Language Models](https://arxiv.org/html/2502.11528v2)

#### **C. Prompt-Based Learning**

Systems maintain misaligned responses and create personalized prompts by:
- Using LLMs to progressively refine prompting strategies
- Adapting based on user profiles and past opinions
- Continuously updating prompt templates

**Source:** [Personalization of Large Language Models Survey](https://arxiv.org/html/2411.00027v3)

---

### 3. **Preference Elicitation Techniques**

#### **Structured Interview Approach**

The first step in evaluating personalized agents assesses the agent's ability to:
- Elicit user needs, requirements, and preferences through reference interviews
- Use structured interviews and think-aloud protocols
- Extract and iteratively refine user preferences

**Source:** [Dynamic Evaluation Framework for Personalized Agents](https://arxiv.org/html/2504.06277v1)

#### **Active Learning**

Intelligent agents use multi-user preference elicitation to:
- Dynamically ask clarifying questions
- Balance exploration (learning) vs. exploitation (using known preferences)
- Minimize user burden while maximizing information gain

**Source:** [Intelligent Agents for Multi-user Preference Elicitation](https://link.springer.com/chapter/10.1007/978-3-030-85365-5_15)

---

## Academic Research Papers

### 1. **MemSkill: Learning and Evolving Memory Skills for Self-Evolving Agents**

**Authors:** Haozhen Zhang et al.
**Published:** February 2, 2026
**arXiv:** [2602.02474](https://arxiv.org/abs/2602.02474)

**Problem:** Most LLM agent memory systems rely on static, hand-designed operations for extracting memory. These fixed procedures hard-code human priors about what to store and how to revise memory.

**Solution:** MemSkill reframes these operations as **learnable and evolvable memory skills** - structured and reusable routines for extracting, consolidating, and pruning information.

**Key Components:**
1. **Controller:** Learns to select relevant skills (RL-based)
2. **Executor:** LLM-based, produces skill-guided memories
3. **Designer:** Periodically reviews hard cases and evolves the skill set

**Results:** Experiments on LoCoMo, LongMemEval, HotpotQA, and ALFWorld demonstrate improved task performance over strong baselines.

**Code:** [GitHub - MemSkill](https://github.com/ViktorAxelsen/MemSkill)

**Sources:**
- [arXiv Paper](https://arxiv.org/abs/2602.02474)
- [Project Page](https://viktoraxelsen.github.io/MemSkill/)
- [Hugging Face](https://huggingface.co/papers/2602.02474)

---

### 2. **Learning Personalized Agents from Human Feedback (PAHF)**

**arXiv:** [2602.16173](https://arxiv.org/abs/2602.16173)
**Published:** 2026

**Framework:** Enables continual personalization where agents learn online from live interaction.

**Key Features:**
- **Explicit per-user memory:** Stores individual preferences
- **Pre-action clarification:** Asks before taking uncertain actions
- **Grounding in preferences:** Actions based on retrieved memory
- **Post-action feedback integration:** Updates memory when preferences drift

**Approach:** Addresses limitations of implicit preference modeling and offline fine-tuning by enabling real-time adaptation.

**Source:** [arXiv - Learning Personalized Agents](https://arxiv.org/html/2602.16173v1)

---

### 3. **RLHF: Reinforcement Learning from Human Feedback**

**Core Concept:** Align AI agents with human preferences by training a reward model to represent preferences, then using RL to train the agent.

**How It Works:**
1. **Reward Model Training:** Supervised learning to predict if response is good/bad based on human rankings
2. **RL Policy Training:** Use reward model to train agent via reinforcement learning
3. **Iterative Refinement:** Collect more feedback, update reward model, retrain policy

**Applications:**
- Personalized recommendations (learns individual user preferences)
- Adaptive training materials
- Dynamic content generation
- User-specific differentiation

**Notable Examples:** ChatGPT, InstructGPT, Sparrow, Gemini, Claude

**Sources:**
- [Hugging Face RLHF Guide](https://huggingface.co/blog/rlhf)
- [AWS RLHF Explanation](https://aws.amazon.com/what-is/reinforcement-learning-from-human-feedback/)
- [CMU ML Blog - RLHF 101](https://blog.ml.cmu.edu/2025/06/01/rlhf-101-a-technical-tutorial-on-reinforcement-learning-from-human-feedback/)
- [GitHub - Awesome RLHF](https://github.com/opendilab/awesome-RLHF)

---

### 4. **Continual Learning, Not Training: Online Adaptation for Agents**

**arXiv:** [2511.01093](https://arxiv.org/abs/2511.01093)

**Problem:** Traditional continual learning focuses on mitigating catastrophic forgetting through gradient-based retraining - ill-suited for deployed agents that must adapt in real time.

**Solution: ATLAS** - A dual-agent architecture:
- **Teacher Agent:** Reasoning and guidance
- **Student Agent:** Execution
- **Persistent Learning Memory:** Stores distilled guidance from experience
- **Gradient-free Learning:** Dynamically adjusts strategies at inference time

**Innovation:** Achieves continual learning without backpropagation, enabling real-time adaptation.

**Source:** [arXiv - Continual Learning for Agents](https://arxiv.org/html/2511.01093)

---

### 5. **Enabling Personalized Long-term Interactions in LLM-based Agents**

**arXiv:** [2510.07925](https://arxiv.org/abs/2510.07925)

**Framework Components:**
1. **Persistent Memory:** Remembers user preferences, history, style
2. **Dynamic Coordination:** Adapts to changing contexts
3. **Self-validation:** Checks consistency of responses
4. **Evolving User Profiles:** Updates understanding of user over time

**Memory Types:**
- **Semantic Memory:** Specific facts and structured knowledge
- **Episodic Memory:** Past events or specific experiences
- **Procedural Memory:** Internalized rules for task performance

**Source:** [arXiv - Personalized Long-term Interactions](https://arxiv.org/abs/2510.07925)

---

### 6. **Agentic Feedback Loop Modeling for Recommendation**

**Conference:** SIGIR '25 (July 13-18, 2025, Padua, Italy)
**Paper:** [Agentic Feedback Loop Modeling](http://staff.ustc.edu.cn/~hexn/papers/sigir25-agent-rec.pdf)

**Focus:** Improving recommendation systems and user simulation through agentic feedback loops.

**Innovation:** Models the bi-directional interaction between recommendations and user responses, creating a closed-loop system that continuously improves.

---

### 7. **Survey Papers on Personalization**

#### **A. Personalization of Large Language Models: A Survey**
- **arXiv:** [2411.00027](https://arxiv.org/html/2411.00027v3)
- **Focus:** Personalized text generation and downstream task personalization

#### **B. A Survey of Personalized Large Language Models: Progress and Future Directions**
- **arXiv:** [2502.11528](https://arxiv.org/html/2502.11528v2)
- **Comprehensive coverage** of personalization techniques for LLMs

#### **C. A Survey on Personalized and Pluralistic Preference Alignment**
- **arXiv:** [2504.07070](https://arxiv.org/html/2504.07070v1)
- **Focus:** Aligning LLMs with diverse user preferences

#### **D. A Survey of Personalization: From RAG to Agent**
- **GitHub:** [Awesome-Personalized-RAG-Agent](https://github.com/Applied-Machine-Learning-Lab/Awesome-Personalized-RAG-Agent)
- **Coverage:** Evolution from retrieval-augmented generation to agent-based architectures

---

## Open Source Projects

### 1. **Mem0: Universal Memory Layer for AI Agents**

**GitHub:** [mem0ai/mem0](https://github.com/mem0ai/mem0) (34.8k+ stars)

**Description:** Enhances AI assistants with intelligent memory layer.

**Features:**
- Remembers user preferences across sessions
- Adapts to individual needs
- Continuously learns over time
- Provides persistent memory storage

**Use Cases:**
- Personalized AI interactions
- Long-term user modeling
- Adaptive assistants

**Sources:**
- [GitHub Repository](https://github.com/mem0ai/mem0)
- [Memory in Agents Guide](https://www.philschmid.de/memory-in-agents)

---

### 2. **Awesome Self-Evolving Agents**

**GitHub:** [EvoAgentX/Awesome-Self-Evolving-Agents](https://github.com/EvoAgentX/Awesome-Self-Evolving-Agents)

**Description:** Comprehensive survey of self-evolving AI agents bridging foundation models and lifelong agentic systems.

**Coverage:**
- Survey papers on self-evolution
- Code repositories
- Benchmarks and datasets
- Reading list of key papers

---

### 3. **Agent Memory Paper List**

**GitHub:** [Shichun-Liu/Agent-Memory-Paper-List](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)

**Description:** Curated list of papers on "Memory in the Age of AI Agents: A Survey"

**Categories:**
- Memory architectures
- Memory management techniques
- Memory-augmented agents
- Long-term memory systems

**Source:** [GitHub Repository](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)

---

### 4. **DeepTutor: AI-Powered Personalized Learning Assistant**

**GitHub:** [HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor)

**Description:** Personalized learning assistant that adapts to individual student needs.

**Features:**
- Personalized content recommendations
- Adaptive learning paths
- Student preference modeling
- Performance tracking

---

### 5. **GenAI Agents: Tutorials and Implementations**

**GitHub:** [NirDiamant/GenAI_Agents](https://github.com/NirDiamant/GenAI_Agents)

**Description:** Comprehensive guide for building intelligent, interactive AI systems.

**Coverage:**
- Basic to advanced agent techniques
- Generative AI implementations
- Tutorial notebooks
- Best practices

**Source:** [GitHub Repository](https://github.com/NirDiamant/GenAI_Agents)

---

### 6. **500 AI Agents Projects**

**GitHub:** [ashishpatel26/500-AI-Agents-Projects](https://github.com/ashishpatel26/500-AI-Agents-Projects)

**Description:** Curated collection of AI agent use cases across industries.

**Industries Covered:**
- Healthcare
- Finance
- Education
- Retail
- Customer service

**Source:** [GitHub Repository](https://github.com/ashishpatel26/500-AI-Agents-Projects)

---

### 7. **Awesome AI Agents**

**GitHub:** [e2b-dev/awesome-ai-agents](https://github.com/e2b-dev/awesome-ai-agents)

**Description:** List of AI autonomous agents with code examples and resources.

---

### 8. **Autonomous Agents Research Papers**

**GitHub:** [tmgthb/Autonomous-Agents](https://github.com/tmgthb/Autonomous-Agents)

**Description:** Research papers on autonomous agents (LLMs), updated daily.

**Source:** [GitHub Repository](https://github.com/tmgthb/Autonomous-Agents)

---

## Memory-Based Approaches

### Google Cloud Vertex AI Memory Bank

**Documentation:** [Vertex AI Agent Engine Memory Bank](https://docs.cloud.google.com/agent-builder/agent-engine/memory-bank/overview)

**Features:**
- Scopes memories to specific identities
- Remembers user preferences, history, key details
- Persistent across multiple sessions

**Memory Generation Process:**
1. Extract meaningful information from source data
2. Refine and consolidate with existing memories
3. Manage memory lifecycle (creation, update, deletion)

**Source:** [Google Cloud Docs](https://docs.cloud.google.com/agent-builder/agent-engine/memory-bank/overview)

---

### Letta Agent Memory

**Website:** [Letta Agent Memory](https://www.letta.com/blog/agent-memory)

**Approach:** Build agents that learn and remember through structured memory management.

**Key Concepts:**
- Core memory (always accessible)
- Archival memory (searchable long-term storage)
- Recall memory (conversation history)

**Source:** [Letta Blog](https://www.letta.com/blog/agent-memory)

---

### Reflective Memory Management

**Paper:** [ACL 2025 - Reflective Memory Management](https://aclanthology.org/2025.acl-long.413.pdf)

**Innovation:** Long-term memory management through self-reflection.

**Process:**
1. Agent reflects on past interactions
2. Identifies important information to retain
3. Consolidates memories to prevent redundancy
4. Prunes outdated or irrelevant memories

---

## Preference Learning Methods

### 1. **Adaptive Preference Arithmetic**

**OpenReview:** [Adaptive Preference Arithmetic](https://openreview.net/forum?id=gkG8JOOUF4)

**Concept:** Personalized agent with adaptive preference arithmetic for dynamic preference modeling.

**Key Insight:** User preferences are often stable in content but their relative strengths shift over time due to changing goals and contexts.

**Approach:** Model dynamic preference strengths for finer-grained personalization.

---

### 2. **Unsupervised Human Preference Learning**

**Project:** [Preference Agents](https://preference-agents.github.io/)

**Innovation:** Small parameter models as "preference agents" generate natural language rules that guide larger pre-trained models.

**Architecture:**
- **Small "steering wheel" model:** Generates preference rules
- **Large foundation model:** Follows rules to produce personalized content

**Benefits:**
- Efficient (small model for preference learning)
- Transparent (natural language rules)
- Adaptable (easy to update preferences)

---

### 3. **Learning User Preferences for Image Generation**

**Project:** [Learn User Preferences](https://learn-user-pref.github.io/)

**Focus:** Learning preferences for generative models through user feedback.

**Techniques:**
- Pairwise comparisons (A vs B)
- Rating-based feedback
- Implicit signals (time spent, selections)

---

## Continual Learning & Online Adaptation

### 1. **Autonomous Continual Learning of Computer-Use Agents**

**arXiv:** [2602.10356](https://arxiv.org/abs/2602.10356)

**Focus:** Agents that adapt to changing environments autonomously.

**Key Features:**
- Environment adaptation without manual retraining
- Continuous learning from interactions
- Graceful handling of distribution shift

**Source:** [arXiv Paper](https://arxiv.org/html/2602.10356)

---

### 2. **Self-Learning AI Agents**

**Approaches:**

#### **A. Reinforcement Learning + Human Feedback**
- Users rate responses
- Corrections become training data
- Agents incorporate feedback immediately

**Source:** [Beam AI - Self-Learning Agents](https://beam.ai/agentic-insights/self-learning-ai-agents-transforming-automation-with-continuous-improvement)

#### **B. Human-in-the-Loop Design**
- Captures explicit and implicit feedback
- Human approvals reinforce decision patterns
- Human modifications become training examples

**Source:** [Terralogic - Self-Learning Agents](https://terralogic.com/self-learning-ai-agents-how-they-improve-over-time/)

#### **C. Real-time Adaptation**
- Updates models continuously
- No forgetting of previous knowledge
- Adapts to environmental changes

**Source:** [IBM - AI Agent Learning](https://www.ibm.com/think/topics/ai-agent-learning)

---

### 3. **Agentic AI & Continuous Learning**

**Source:** [Xoriant - Agentic AI](https://www.xoriant.com/thought-leadership/article/agentic-ai-and-continuous-learning-creating-ever-evolving-systems)

**Framework:** Ever-evolving systems that continuously improve.

**Components:**
- Perception (sensing environment)
- Learning (updating models)
- Action (applying knowledge)
- Feedback (measuring outcomes)

---

## Evaluation & Benchmarking

### 1. **Dynamic Evaluation Framework**

**Paper:** [Dynamic Evaluation for Personalized Agents](https://arxiv.org/html/2504.06277v1)

**Framework Components:**
1. **Persona-based user simulation:** Temporally evolving preference models
2. **Structured elicitation protocols:** Reference interviews to extract preferences
3. **Adaptation-aware evaluation:** Measures how agent behavior improves across sessions

**Multi-Session Approach:** Evaluates preference adaptability over time, not just single-interaction performance.

---

### 2. **Beyond Static Evaluation**

**Paper:** [Rethinking Assessment of Personalized Agent Adaptability](https://arxiv.org/html/2510.03984)

**Critique:** Static benchmarks fail to capture dynamic nature of personalization.

**Proposed Metrics:**
- Adaptation speed (how quickly agent learns)
- Preference drift handling (adapts when users change)
- Cross-session consistency
- Long-term performance trends

---

## Comparison Table

| Technique | Learning Type | Feedback | Memory | Adaptation Speed | Complexity |
|-----------|--------------|----------|--------|-----------------|------------|
| **MemSkill** | RL + LLM Designer | Implicit (corrections) | Evolving skills | Moderate | High |
| **PAHF** | Online learning | Explicit + Implicit | Per-user memory | Fast | Moderate |
| **RLHF** | Offline RL | Explicit rankings | Reward model | Slow (retraining) | High |
| **Mem0** | Memory retrieval | Implicit | Persistent memory bank | Fast | Low |
| **ATLAS** | Gradient-free continual | Experience-based | Learning memory | Real-time | Moderate |
| **RAG + Personalization** | Retrieval-based | Implicit | Knowledge base | Fast | Low |
| **Prompt-based** | Prompt tuning | Explicit | User profiles | Moderate | Low |
| **Preference Agents** | Rule generation | Explicit | Natural language rules | Fast | Low |

---

## Key Insights

### 1. **Trade-offs**

**Complexity vs. Adaptability:**
- Simple methods (RAG, prompt-based): Fast, but limited learning
- Complex methods (MemSkill, RLHF): Powerful, but require infrastructure

**Explicit vs. Implicit Feedback:**
- Explicit: More accurate but burdens users
- Implicit: Seamless but noisier signals

**Offline vs. Online Learning:**
- Offline: More stable, requires retraining
- Online: Adaptive, risk of instability

---

### 2. **Emerging Patterns**

**Hybrid Approaches Win:**
- Combine memory (fast retrieval) + learning (adaptation)
- Use both explicit and implicit feedback
- Balance exploration (learning) and exploitation (using knowledge)

**Multi-Modal Memory:**
- Semantic (facts)
- Episodic (events)
- Procedural (how-to)

**Persona-Based Modeling:**
- Dynamic user profiles that evolve
- Context-aware preference modeling
- Multi-session continuity

---

### 3. **Best Practices**

1. **Start Simple, Add Complexity as Needed**
   - Begin with memory retrieval + prompt augmentation
   - Add learning mechanisms when patterns emerge
   - Evolve skills when static approaches fail

2. **Design for Transparency**
   - Explain why decisions were made
   - Show which memories/preferences were used
   - Allow users to edit/delete preferences

3. **Balance Automation and Control**
   - Learn implicitly where possible
   - Ask clarifying questions for ambiguity
   - Let users override any decision

4. **Measure What Matters**
   - Correction frequency (is agent learning?)
   - User satisfaction (is personalization helpful?)
   - Long-term engagement (does it improve over time?)

---

## Future Directions

### 1. **Multi-User Personalization**

Current research focuses on single-user agents. Future work:
- Shared preferences in teams
- Preference conflict resolution
- Group recommendation with personalization

**Paper:** [Intelligent Agents for Multi-user Preference Elicitation](https://link.springer.com/chapter/10.1007/978-3-030-85365-5_15)

---

### 2. **Privacy-Preserving Personalization**

Challenge: Personalization requires data, but users want privacy.

**Research Directions:**
- Federated learning for agents
- Local-only memory banks
- Differential privacy for preference learning

**Paper:** [Towards Aligning Personalized AI Agents with Users' Privacy Preference](https://dl.acm.org/doi/10.1145/3733816.3760752)

---

### 3. **Cross-Domain Transfer**

Current systems learn preferences per-domain. Future:
- Transfer preferences across tasks (email → calendar → docs)
- Meta-learning for faster adaptation
- Universal user models

---

### 4. **Agentic Recommender Systems**

**Paper:** [Towards Agentic Recommender Systems](https://arxiv.org/html/2503.16734v1)

**Vision:** Recommender systems with:
- Proactive preference elicitation
- Multi-turn clarification dialogues
- Contextual awareness
- Long-term memory of user journey

---

### 5. **Pluralistic Alignment**

**Challenge:** Users have diverse, sometimes contradictory preferences.

**Research:** [Survey on Personalized and Pluralistic Preference Alignment](https://arxiv.org/html/2504.07070v1)

**Goal:** Align LLMs with multiple user preferences simultaneously while respecting individual differences.

---

## Recommended Reading Order

### For Beginners:
1. [Hugging Face RLHF Guide](https://huggingface.co/blog/rlhf) - Understand basic feedback loop
2. [Mem0 GitHub](https://github.com/mem0ai/mem0) - See practical memory implementation
3. [Self-Learning AI Agents (Beam AI)](https://beam.ai/agentic-insights/self-learning-ai-agents-transforming-automation-with-continuous-improvement) - High-level overview

### For Intermediate:
1. [Personalization of LLMs Survey](https://arxiv.org/html/2411.00027v3) - Comprehensive techniques
2. [PAHF Paper](https://arxiv.org/html/2602.16173v1) - Online learning framework
3. [Dynamic Evaluation Framework](https://arxiv.org/html/2504.06277v1) - How to measure success

### For Advanced:
1. [MemSkill Paper](https://arxiv.org/abs/2602.02474) - Self-evolving skills
2. [ATLAS Paper](https://arxiv.org/html/2511.01093) - Continual learning architecture
3. [Agentic Feedback Loop Modeling](http://staff.ustc.edu.cn/~hexn/papers/sigir25-agent-rec.pdf) - Closed-loop systems

---

## Conclusion

The field of personalized AI agents is rapidly evolving from static, hand-designed systems to **adaptive, self-evolving systems** that learn continuously from user interactions.

**Key Trends:**
1. **Memory-based architectures** are becoming standard
2. **Online learning** is replacing offline fine-tuning
3. **Hybrid approaches** combining multiple techniques are most effective
4. **Transparency and control** are essential for user trust

**For ClawMail:**
- **MemSkill approach** aligns well with closed-loop personalization goals
- **Simplified architecture** (no RL Controller) is practical for email domain
- **Memory Bank + Designer** provides core self-evolution benefits
- **PAHF-style online learning** enables real-time adaptation

**Next Steps:**
1. Implement memory bank foundation
2. Start with static skills (6-8 hand-designed)
3. Add Designer for skill evolution
4. Measure and iterate based on user corrections

---

## References

### Papers (arXiv)
- [2602.02474 - MemSkill](https://arxiv.org/abs/2602.02474)
- [2602.16173 - PAHF](https://arxiv.org/abs/2602.16173)
- [2511.01093 - ATLAS](https://arxiv.org/abs/2511.01093)
- [2510.07925 - Long-term Interactions](https://arxiv.org/abs/2510.07925)
- [2411.00027 - Personalization Survey](https://arxiv.org/html/2411.00027v3)
- [2502.11528 - Personalized LLMs Survey](https://arxiv.org/html/2502.11528v2)
- [2504.07070 - Pluralistic Alignment](https://arxiv.org/html/2504.07070v1)

### GitHub Projects
- [mem0ai/mem0](https://github.com/mem0ai/mem0)
- [ViktorAxelsen/MemSkill](https://github.com/ViktorAxelsen/MemSkill)
- [EvoAgentX/Awesome-Self-Evolving-Agents](https://github.com/EvoAgentX/Awesome-Self-Evolving-Agents)
- [Shichun-Liu/Agent-Memory-Paper-List](https://github.com/Shichun-Liu/Agent-Memory-Paper-List)
- [Applied-Machine-Learning-Lab/Awesome-Personalized-RAG-Agent](https://github.com/Applied-Machine-Learning-Lab/Awesome-Personalized-RAG-Agent)

### Documentation & Guides
- [Google Vertex AI Memory Bank](https://docs.cloud.google.com/agent-builder/agent-engine/memory-bank/overview)
- [Hugging Face RLHF](https://huggingface.co/blog/rlhf)
- [AWS RLHF](https://aws.amazon.com/what-is/reinforcement-learning-from-human-feedback/)
- [Letta Agent Memory](https://www.letta.com/blog/agent-memory)

---

*Document compiled from web search results on 2026-02-28. For ClawMail personalization implementation reference.*
