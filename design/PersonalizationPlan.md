# ClawMail 个性化方案 — MemSkill

**Status**: Proposed Design (Simplified Architecture)
**Created**: 2026-02-28
**Updated**: 2026-02-28
**Approach**: Self-evolving memory skills for adaptive personalization

**Architecture Note**: This plan uses a **simplified architecture** compared to the original MemSkill paper. Instead of an RL-based Controller for skill selection, we apply **all 5 skills** to every feedback event (computationally cheap since there are so few skills). This reduces complexity while keeping the core benefits: Memory Bank + Self-evolving Skills via Designer.

---

## Executive Summary

This plan implements a **MemSkill-inspired self-evolving personalization system** for ClawMail that learns and improves from user corrections. The system creates a **closed-loop learning system** where:

1. **Memory skills** (6-8 fixed skills) extract user preferences from email interactions
2. **Memory bank** stores user-specific preferences (sender patterns, urgency signals, summary styles)
3. **AI predictions** use these preferences for importance scoring, categorization, summarization
4. **User corrections** are analyzed to identify skill gaps
5. **Skills evolve** automatically via LLM-based Designer to avoid repeating mistakes
6. **System improves** continuously with each user interaction

**Simplified Architecture**: No RL Controller - all skills are applied to every email (only 6-8 skills, computationally cheap).

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          INCOMING EMAIL                          │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SKILL-BASED MEMORY SYSTEM                      │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ SKILL BANK (6-8 Fixed Skills)                            │  │
│  │ - extract_sender_importance                              │  │
│  │ - detect_automated_content                               │  │
│  │ - extract_urgency_signals                                │  │
│  │ - extract_category_patterns                              │  │
│  │ - extract_summary_preferences                            │  │
│  │ - track_response_patterns                                │  │
│  │ - detect_project_context                                 │  │
│  │ - learn_temporal_patterns                                │  │
│  └──────────────┬───────────────────────────────────────────┘  │
│                 │                                               │
│                 ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ EXECUTOR (Memory Builder)                                │  │
│  │ - Receives: Email + Retrieved user memories              │  │
│  │ - Applies: ALL skills (or task-specific subset)          │  │
│  │ - Extracts: User preferences, patterns, signals          │  │
│  │ - Updates: User-specific memory bank                     │  │
│  └──────────────┬───────────────────────────────────────────┘  │
│                 │                                               │
│                 ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ MEMORY BANK (User Preferences)                           │  │
│  │ - Sender importance patterns                             │  │
│  │ - Category preferences                                   │  │
│  │ - Summary style preferences                              │  │
│  │ - Temporal patterns (when user reads/responds)           │  │
│  │ - Urgency indicators                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AI PROCESSING PIPELINE                        │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Importance Scorer (uses memory)                          │  │
│  │ → Predicted Score: 75/100                                │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Categorizer (uses memory)                                │  │
│  │ → Predicted Category: "Work > Client X"                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Summarizer (uses memory)                                 │  │
│  │ → Summary with user's preferred style/details            │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                            │
│  Display: Importance score, category, summary                   │
│  User can: Adjust score, change category, edit summary          │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼ (User makes corrections)
┌─────────────────────────────────────────────────────────────────┐
│                    FEEDBACK COLLECTION                           │
│  Log: Original prediction vs. User correction                   │
│  Store: Hard cases (where AI was significantly wrong)           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼ (Periodic: every 50-100 corrections)
┌─────────────────────────────────────────────────────────────────┐
│                  DESIGNER (Skill Evolver)                        │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. Analyze Hard Cases                                    │  │
│  │    - Cluster by failure type                             │  │
│  │    - Identify missing skills or weak skills              │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 2. Propose Skill Changes                                 │  │
│  │    - Refine existing skills (improve instructions)       │  │
│  │    - Create new skills (fill capability gaps)            │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 3. Update Skill Bank                                     │  │
│  │    - Add evolved skills                                  │  │
│  │    - Rollback if performance degrades                    │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         └──────► LOOP BACK TO EXECUTOR
                                 (Use evolved skills for next emails)
```

---

## Core Components

**Note:** This simplified architecture uses **static skill application** (no RL Controller). All 6-8 skills are applied to every email, or filtered by simple task-based rules.

### 1. Skill Bank (Shared Resource)

**Purpose**: Store reusable memory management operations that know how to extract user preferences.

**Initial Skills** (hand-designed, 6-8 basic skills):

```python
# Example Skill Structure
{
    "name": "extract_sender_importance",
    "description": "Identify importance patterns based on email sender",
    "skill_type": "insert",  # insert, update, delete
    "instruction_template": """
    Skill: Extract Sender Importance Pattern

    Purpose: Identify whether this sender's emails are typically important to the user.

    When to use:
    - Processing a new email
    - User has corrected importance for this sender before

    How to apply:
    - Check sender email address and name
    - Look for patterns: frequency of high/low ratings
    - Consider context: subject matter, email type (newsletter vs. personal)

    Constraints:
    - Distinguish between personal emails and automated messages
    - Track separately for different email types from same sender

    Output: INSERT memory with sender importance pattern
    """,
    "version": 1,
    "created_at": "2026-02-28",
    "performance_score": 0.0  # Updated during training
}
```

**Initial Skill List**:
1. `extract_sender_importance` - Learn sender priority patterns
2. `extract_urgency_signals` - Identify temporal urgency indicators
3. `extract_category_patterns` - Learn user's categorization logic
4. `extract_summary_preferences` - Learn preferred summary style/details
5. `detect_automated_content` - Distinguish human vs. automated emails
6. `track_response_patterns` - Learn which emails user responds to quickly

**Skill Evolution**:
- Designer proposes new skills when gaps are identified
- Skills get refined when they consistently fail
- Performance-tracked: skills with low accuracy are candidates for refinement

---

### 2. Memory Bank (User-Specific)

**Purpose**: Store extracted user preferences and patterns for each ClawMail user.

**Schema** (SQLite extension to existing database):

```sql
-- User preference memory table
CREATE TABLE IF NOT EXISTS user_preference_memory (
    id TEXT PRIMARY KEY,
    user_account_id TEXT NOT NULL,  -- Which user this belongs to
    memory_type TEXT NOT NULL,       -- sender_pattern, category_rule, etc.
    memory_content TEXT NOT NULL,    -- JSON-encoded preference data
    confidence_score REAL DEFAULT 0.5,  -- How confident (0-1)
    evidence_count INTEGER DEFAULT 1,   -- How many examples support this
    last_updated TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

CREATE INDEX idx_memory_user_type ON user_preference_memory(user_account_id, memory_type);
```

**Example Memories**:

```json
// Memory 1: Sender importance pattern
{
    "memory_type": "sender_importance",
    "sender_email": "boss@company.com",
    "sender_name": "Alice Smith",
    "importance_pattern": {
        "personal_emails": 90,
        "newsletters": 20,
        "meeting_invites": 95
    },
    "confidence": 0.85,
    "evidence_count": 12
}

// Memory 2: Category pattern
{
    "memory_type": "category_pattern",
    "rule": "Emails with 'invoice' or 'payment' → Finance",
    "accuracy": 0.92,
    "evidence_count": 8
}

// Memory 3: Summary style preference
{
    "memory_type": "summary_preference",
    "preferences": {
        "include_deadlines": true,
        "include_action_items": true,
        "max_length": "brief",  // brief, moderate, detailed
        "highlight_people": true
    },
    "confidence": 0.75,
    "evidence_count": 15
}

// Memory 4: Urgency signal
{
    "memory_type": "urgency_indicator",
    "pattern": "Emails from legal@company.com with 'review' are urgent",
    "importance_boost": +30,
    "confidence": 0.88,
    "evidence_count": 5
}
```

**Memory Retrieval**:
- Semantic search using embeddings (Qwen3-Embedding-0.6B)
- Retrieve top-20 relevant memories for current email
- Pass to Executor along with all skills

---

### 3. Executor (Memory Builder)

**Purpose**: Apply all skills (or task-specific subset) to extract and update user preference memories.

**Implementation**: LLM-based (uses existing OpenClaw/LLM backend)

**Skill Selection Strategy**:
```python
def select_skills_for_task(task_type: str, all_skills: List[Skill]) -> List[Skill]:
    """Simple rule-based skill filtering (optional)."""

    # Option 1: Apply ALL skills (simplest, only 6-8 skills)
    return all_skills

    # Option 2: Filter by task type (optional optimization)
    # skill_map = {
    #     "importance": ["extract_sender_importance", "detect_automated_content", ...],
    #     "category": ["extract_category_patterns", "extract_sender_importance", ...],
    #     "summary": ["extract_summary_preferences", "detect_project_context"],
    # }
    # relevant_names = skill_map.get(task_type, [])
    # return [s for s in all_skills if s.name in relevant_names]
```

**Prompt Template**:
```
You are a memory management executor for ClawMail personalization.

Your task: Apply the following skills to extract user preferences from this email
and the user's correction.

EMAIL:
Subject: {email.subject}
From: {email.from_address}
Body: {email.body_text[:1000]}

AI PREDICTION:
Importance Score: {predicted_score}/100

USER CORRECTION:
Importance Score: {user_corrected_score}/100
(Difference: {abs(predicted_score - user_corrected_score)})

RETRIEVED USER MEMORIES:
{retrieved_memories}

SKILLS TO APPLY (ALL):
{skill_1.instruction_template}

{skill_2.instruction_template}

{skill_3.instruction_template}

... (all 6-8 skills listed) ...

INSTRUCTIONS:
- Apply each skill as needed
- Extract new preferences or update existing ones
- Output memory operations in the format below

OUTPUT FORMAT:

INSERT:
MEMORY_TYPE: [sender_importance|category_pattern|urgency_indicator|summary_preference]
MEMORY_CONTENT: {JSON-encoded content}
CONFIDENCE: {0.0-1.0}

UPDATE:
MEMORY_ID: {existing memory id}
UPDATED_CONTENT: {JSON-encoded updated content}
CONFIDENCE: {0.0-1.0}

DELETE:
MEMORY_ID: {memory id to remove}
REASON: {why this memory is no longer valid}
```

**Example Execution**:

Input: Email from "boss@company.com" with subject "Newsletter: Company Updates"
- AI predicted: 85/100
- User corrected: 15/100 ❌ (AI was very wrong!)

Selected skills: `extract_sender_importance`, `detect_automated_content`

Executor output:
```
INSERT:
MEMORY_TYPE: sender_importance
MEMORY_CONTENT: {
    "sender_email": "boss@company.com",
    "email_type": "newsletter",
    "importance": 15,
    "pattern": "Automated newsletters from this sender are low priority"
}
CONFIDENCE: 0.7

UPDATE:
MEMORY_ID: mem_12345
UPDATED_CONTENT: {
    "sender_email": "boss@company.com",
    "importance_pattern": {
        "personal_emails": 90,
        "newsletters": 15,  // Updated from 85
        "meeting_invites": 95
    }
}
CONFIDENCE: 0.85
```

---

### 4. Designer (Skill Evolver)

**Purpose**: Analyze failures and evolve the skill bank to prevent future mistakes.

**Trigger**: Periodically (every 50-100 user corrections)

**Process**:

#### Step 1: Collect Hard Cases
```python
def collect_hard_cases(feedback_log, threshold=30):
    """Collect cases where AI was significantly wrong."""
    hard_cases = []
    for entry in feedback_log:
        error = abs(entry['predicted_score'] - entry['user_score'])
        if error >= threshold:
            hard_cases.append({
                'email_id': entry['email_id'],
                'predicted': entry['predicted_score'],
                'actual': entry['user_score'],
                'error': error,
                'email_data': entry['email'],
                'retrieved_memories': entry['memories'],
                'selected_skills': entry['skills_used']
            })
    return hard_cases
```

#### Step 2: Cluster & Analyze Failures
```python
def analyze_failures(hard_cases, llm):
    """Use LLM to analyze failure patterns."""

    # Cluster cases by similarity (k-means on email embeddings)
    clusters = cluster_cases(hard_cases, n_clusters=5)

    # For each cluster, analyze with LLM
    analysis_prompt = f"""
    Analyze these {len(cluster)} failure cases where AI importance prediction was wrong.

    CASES:
    {format_cases(cluster)}

    CURRENT SKILLS:
    {format_skill_bank(skill_bank)}

    QUESTIONS:
    1. What pattern of failures do you see?
    2. What information is the AI missing?
    3. Which skill is failing or missing?
    4. How should we fix it?

    Output format:
    {{
        "failure_pattern": "...",
        "root_cause": "storage_failure|retrieval_failure|memory_quality_failure",
        "missing_information": "...",
        "recommendation": "add_new_skill|refine_existing_skill|no_change",
        "target_skill": "...",
        "proposed_change": "..."
    }}
    """

    analysis = llm.generate(analysis_prompt)
    return analysis
```

#### Step 3: Propose Skill Changes
```python
def propose_skill_changes(analysis, llm):
    """Generate new or refined skills."""

    if analysis['recommendation'] == 'add_new_skill':
        prompt = f"""
        Create a new memory skill to address this gap:

        PROBLEM: {analysis['failure_pattern']}
        MISSING: {analysis['missing_information']}

        Design a new skill following this template:
        {{
            "name": "skill_name_in_snake_case",
            "description": "Brief description",
            "skill_type": "insert|update",
            "instruction_template": "
                Skill: [Name]
                Purpose: [What it does]
                When to use: [Triggers]
                How to apply: [Steps]
                Constraints: [What to avoid]
                Output: [Memory type]
            "
        }}
        """
        new_skill = llm.generate(prompt)
        return {"action": "add", "skill": new_skill}

    elif analysis['recommendation'] == 'refine_existing_skill':
        prompt = f"""
        Refine this existing skill to handle the failure pattern:

        CURRENT SKILL:
        {skill_bank[analysis['target_skill']]}

        PROBLEM: {analysis['failure_pattern']}

        Provide improved instruction_template that addresses the issue.
        """
        refined_template = llm.generate(prompt)
        return {
            "action": "refine",
            "skill_name": analysis['target_skill'],
            "new_template": refined_template
        }

    else:
        return {"action": "no_change"}
```

#### Step 4: Update Skill Bank
```python
def update_skill_bank(skill_bank, changes):
    """Apply skill changes with rollback support."""

    # Save current skill bank snapshot
    snapshot = copy.deepcopy(skill_bank)

    # Apply changes
    for change in changes:
        if change['action'] == 'add':
            skill_bank.append(change['skill'])
        elif change['action'] == 'refine':
            idx = find_skill_index(skill_bank, change['skill_name'])
            skill_bank[idx]['instruction_template'] = change['new_template']
            skill_bank[idx]['version'] += 1

    # Test on validation set
    val_performance = evaluate_skill_bank(skill_bank, validation_data)

    # Rollback if performance degrades
    if val_performance < baseline_performance * 0.95:
        print("[Designer] Performance degraded, rolling back...")
        skill_bank = snapshot
    else:
        print(f"[Designer] Skill bank updated! Performance: {val_performance:.3f}")
        save_skill_bank(skill_bank)

    return skill_bank
```

---

## Implementation Phases

### Phase 1: Foundation (Weeks 1-2)

**Goal**: Set up basic infrastructure without ML components.

**Tasks**:
1. ✅ Extend database schema
   - Add `user_preference_memory` table
   - Add `skill_bank` table (JSON storage)
   - Add `feedback_log` table (enhanced logging)

2. ✅ Implement Memory Bank
   - CRUD operations for user memories
   - Semantic retrieval (use existing Qwen3-Embedding)
   - Memory confidence tracking

3. ✅ Create Initial Skill Bank
   - Hand-design 6-8 basic skills
   - Store in JSON format
   - Load skills on startup

4. ✅ Implement Executor (Static)
   - LLM-based memory extraction
   - Apply ALL skills (6-8 skills, no selection needed)
   - Parse and store extracted memories

5. ✅ Enhanced Feedback Collection
   - Log: email_id, predicted_score, user_score, error
   - Track: retrieved_memories, skills_used (all of them)
   - Identify hard cases (error > threshold)

**Deliverable**: Basic system that extracts preferences using all hand-designed skills.

---

### Phase 2: Designer Integration (Weeks 3-4)

**Goal**: Add automatic skill evolution from failure analysis.

**Tasks**:
1. ✅ Implement Hard Case Collection
   - Buffer of recent failures (error > 30)
   - Clustering by failure type (k-means)
   - Representative case selection

2. ✅ Implement LLM-based Analyzer
   - Failure pattern identification
   - Root cause analysis (storage vs. quality vs. retrieval)
   - Skill gap identification

3. ✅ Implement Skill Proposer
   - Generate new skill templates
   - Refine existing skill instructions
   - Validate proposed changes

4. ✅ Implement Evolution Loop
   - Trigger: every 50-100 corrections
   - Analyze → Propose → Test → Rollback if needed
   - Log skill evolution history

5. ✅ Skill Performance Tracking
   - Track per-skill accuracy over time
   - Identify low-performing skills
   - Prioritize for refinement

**Deliverable**: Fully self-evolving system that improves skills based on user corrections.

---

### Phase 3: Multi-Task Extension (Weeks 5-6)

**Goal**: Extend beyond importance scoring to categorization and summarization.

**Tasks**:
1. ✅ Category Prediction
   - Add skills for category pattern extraction
   - Apply skills to extract category preferences
   - Collect category correction feedback

2. ✅ Summary Style Learning
   - Add skills for summary preference extraction
   - Learn: preferred length, detail level, elements to include
   - Apply to summary generation prompts

3. ✅ Unified Memory Bank
   - Single retrieval across all preference types
   - Cross-task memory sharing (sender patterns help both importance and category)

**Deliverable**: Holistic personalization across all AI tasks in ClawMail.

---

### Phase 4: Production Optimization (Week 7+)

**Goal**: Optimize for real-world deployment.

**Tasks**:
1. ✅ Performance Optimization
   - Cache skill embeddings (if needed)
   - Batch memory retrieval
   - Optimize executor inference (<2s)

2. ✅ User Controls
   - UI to view learned preferences
   - Ability to edit/delete memories
   - Privacy: clear all personalization data

3. ✅ A/B Testing
   - Compare MemSkill vs. Static approach
   - Metrics: user satisfaction, correction frequency, engagement

4. ✅ Monitoring & Debugging
   - Dashboard: skill usage, accuracy trends, evolution history
   - Alerts: performance degradation, skill failures
   - Logging: full pipeline traces for debugging

5. ✅ Documentation
   - User guide: how personalization works
   - Developer guide: how to add new skills
   - Research notes: evolution insights

**Deliverable**: Production-ready self-evolving personalization system.

---

## Technical Specifications

### Data Flow

```
1. Email arrives
   ↓
2. Retrieve user memories (semantic search, top-20)
   ↓
3. Executor applies ALL skills (6-8 skills, LLM-based)
   ↓
4. Extract preferences and update memory bank (insert/update memories)
   ↓
5. AI prediction (importance/category/summary using memories)
   ↓
6. User views & possibly corrects
   ↓
7. Log feedback (if corrected)
   ↓
8. If error > threshold → hard case buffer
   ↓
9. Every 50-100 corrections → Designer evolves skills
    ↓
10. Loop back to step 1 with evolved skills
```

### File Structure

```
clawmail/
├── domain/
│   └── models/
│       ├── memory.py          # Memory, Skill data classes
│       └── feedback.py        # Feedback, HardCase data classes
│
├── infrastructure/
│   ├── database/
│   │   └── storage_manager.py # Extended with memory & skill CRUD
│   │
│   ├── personalization/       # NEW MODULE
│   │   ├── __init__.py
│   │   ├── memory_bank.py     # Memory CRUD, retrieval
│   │   ├── skill_bank.py      # Skill CRUD, management
│   │   ├── executor.py        # LLM-based memory builder (applies all skills)
│   │   ├── designer.py        # Skill evolution logic
│   │   └── utils.py           # Embeddings, clustering, etc.
│   │
│   └── ai/
│       └── ai_processor.py    # Modified to use memories
│
├── ui/
│   ├── app.py                 # UI integration
│   └── personalization_view.py # NEW: View/manage preferences
│
└── tests/
    └── test_personalization/  # NEW: Unit tests
        ├── test_memory_bank.py
        ├── test_executor.py
        └── test_designer.py
```

### Database Schema Changes

```sql
-- User preference memories
CREATE TABLE IF NOT EXISTS user_preference_memory (
    id TEXT PRIMARY KEY,
    user_account_id TEXT NOT NULL,
    memory_type TEXT NOT NULL,  -- sender_importance, category_pattern, etc.
    memory_content TEXT NOT NULL,  -- JSON
    confidence_score REAL DEFAULT 0.5,
    evidence_count INTEGER DEFAULT 1,
    last_updated TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_account_id) REFERENCES accounts(id) ON DELETE CASCADE
);

-- Skill bank (shared across users, but can be user-specific later)
CREATE TABLE IF NOT EXISTS skill_bank (
    id TEXT PRIMARY KEY,
    skill_name TEXT UNIQUE NOT NULL,
    skill_type TEXT NOT NULL,  -- insert, update, delete
    description TEXT,
    instruction_template TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    performance_score REAL DEFAULT 0.0,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Enhanced feedback log
CREATE TABLE IF NOT EXISTS personalization_feedback (
    id TEXT PRIMARY KEY,
    user_account_id TEXT NOT NULL,
    email_id TEXT NOT NULL,
    feedback_type TEXT NOT NULL,  -- importance, category, summary
    predicted_value TEXT,  -- JSON
    user_corrected_value TEXT,  -- JSON
    error_magnitude REAL,
    is_hard_case INTEGER DEFAULT 0,
    retrieved_memories TEXT,  -- JSON: list of memory IDs used
    selected_skills TEXT,  -- JSON: list of skill names used
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_account_id) REFERENCES accounts(id) ON DELETE CASCADE,
    FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE
);

-- Skill evolution history
CREATE TABLE IF NOT EXISTS skill_evolution_history (
    id TEXT PRIMARY KEY,
    skill_name TEXT NOT NULL,
    evolution_type TEXT NOT NULL,  -- created, refined, deleted
    previous_version INTEGER,
    new_version INTEGER,
    change_reason TEXT,  -- JSON: failure analysis
    performance_before REAL,
    performance_after REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX idx_memory_user_type ON user_preference_memory(user_account_id, memory_type);
CREATE INDEX idx_feedback_user ON personalization_feedback(user_account_id);
CREATE INDEX idx_feedback_hard_cases ON personalization_feedback(is_hard_case, created_at);
CREATE INDEX idx_skill_performance ON skill_bank(performance_score DESC);
```

### Configuration

```python
# config/personalization_config.py

PERSONALIZATION_CONFIG = {
    # Memory Bank
    "memory": {
        "max_memories_per_user": 1000,
        "retrieval_top_k": 20,
        "confidence_threshold": 0.3,  # Ignore low-confidence memories
        "evidence_decay": 0.95,  # Decay old evidence over time
    },

    # Executor
    "executor": {
        "apply_all_skills": True,  # Apply all skills vs. task-specific filtering
        "max_execution_time": 5.0,  # Timeout for LLM executor (seconds)
    },

    # Designer
    "designer": {
        "trigger_frequency": 100,  # Evolve every N corrections
        "hard_case_threshold": 30,  # Error > 30 is hard case
        "max_hard_cases": 50,  # Buffer size
        "clustering_k": 5,  # Number of failure clusters
        "max_skill_changes": 3,  # Max changes per evolution round
        "rollback_threshold": 0.95,  # Rollback if perf < 95% of baseline
    },
}
```

---

## Example: Complete Flow

### Scenario: User corrects importance for a newsletter

**Step 1: Email Arrives**
```
From: boss@company.com
Subject: Weekly Newsletter: Company Updates
Body: "This week we launched Product X, hired 5 new people..."
```

**Step 2: Memory Retrieval**
```python
retrieved_memories = [
    {
        "id": "mem_001",
        "type": "sender_importance",
        "content": {
            "sender": "boss@company.com",
            "importance": 90,  # Default: boss emails are important
        },
        "confidence": 0.8,
        "evidence": 10
    }
]
```

**Step 3: Executor Applies All Skills**
```python
# All 6-8 skills are applied to extract preferences
applied_skills = [
    "extract_sender_importance",
    "detect_automated_content",
    "extract_urgency_signals",
    "extract_category_patterns",
    "extract_summary_preferences",
    "track_response_patterns",
    "detect_project_context",
    "learn_temporal_patterns"
]
```

**Step 4: AI Prediction (using memory)**
```python
# Importance scorer sees: sender=boss@company.com → memory says 90
predicted_importance = 85
```

**Step 5: User Correction**
```python
user_corrected_importance = 20  # User marks as low priority
error = abs(85 - 20) = 65  # Large error! This is a hard case.
```

**Step 6: Log Feedback**
```python
feedback = {
    "email_id": "email_123",
    "predicted": 85,
    "actual": 20,
    "error": 65,
    "is_hard_case": True,  # error > 30
    "retrieved_memories": ["mem_001"],
    "selected_skills": ["extract_sender_importance", "detect_automated_content", ...]
}
# Add to hard_case_buffer
```

**Step 7: Executor Extracts New Preference**
```python
executor_output = {
    "action": "UPDATE",
    "memory_id": "mem_001",
    "updated_content": {
        "sender": "boss@company.com",
        "importance_pattern": {
            "personal_emails": 90,  # Keep high
            "newsletters": 20,      # NEW: newsletters are low priority
            "meeting_invites": 95
        }
    },
    "confidence": 0.85
}

# Also INSERT new memory
{
    "action": "INSERT",
    "memory_type": "automated_content",
    "content": {
        "sender": "boss@company.com",
        "pattern": "Subject contains 'Newsletter' → automated",
        "importance_modifier": -65  # Reduce importance by 65
    },
    "confidence": 0.7
}
```

**Step 8: Update Memory Bank**
```python
# Memory bank now has:
# 1. Updated sender pattern (newsletters from boss = 20)
# 2. New automated detection pattern
```

**Step 9: Designer Evolution (after 100 hard cases)**
```python
# Designer analyzes this hard case along with others
analysis = {
    "failure_pattern": "AI doesn't distinguish personal vs automated emails from same sender",
    "root_cause": "storage_failure",  # Skill missing
    "recommendation": "add_new_skill"
}

# Designer proposes new skill
new_skill = {
    "name": "distinguish_email_types",
    "description": "Classify email as personal, automated, or transactional",
    "instruction_template": """
        Skill: Distinguish Email Types

        Purpose: Identify whether email is personal communication,
                 automated newsletter, or transactional notification.

        When to use: Always, for sender importance assessment

        How to apply:
        - Check for: "newsletter", "unsubscribe", "automated" in subject/body
        - Look for: personal pronouns, direct questions, unique content
        - Classify: personal | newsletter | transactional

        Output: INSERT memory with email type classification for this sender
    """
}

# Add to skill bank
skill_bank.append(new_skill)
```

**Step 10: Next Newsletter (with evolved skill)**
```
From: boss@company.com
Subject: Weekly Newsletter: Product Launch

Executor applies all skills (including new "distinguish_email_types"):
- Detects: "Weekly Newsletter" → automated
- Retrieves memory: newsletters from boss = 20

AI prediction: 22 ✅ (much closer to user's preference!)
```

---

## Challenges & Solutions

### Challenge 1: Cold Start Problem

**Problem**: System needs user corrections to learn preferences.

**Solutions**:
1. **Start with hand-designed skills**
   - Phase 1: Use 6-8 hand-designed skills immediately
   - System works from day 1 (no training needed)
   - Collect feedback for 2-4 weeks before Designer triggers

3. **Seed with common patterns**
   - Pre-populate memory bank with general rules:
     - "Emails with 'urgent' → +20 importance"
     - "Newsletters → -30 importance"
   - User corrections override these defaults

4. **Gradual rollout**
   - Start with importance scoring only (simplest task)
   - Add category/summary after memory bank is populated

### Challenge 2: Computational Cost

**Problem**: LLM executor + Designer calls can be expensive.

**Solutions**:
1. **Efficient executor**
   - Only 6-8 skills to apply (low overhead)
   - Single LLM call with all skills in prompt
   - Target: <3s per email

2. **Async designer**
   - Run skill evolution in background thread
   - Don't block user experience
   - Only triggers every 100 corrections

3. **Cache aggressively**
   - Cache memory retrieval results (invalidate on memory updates)
   - Pre-compute skill embeddings if needed

4. **Optimize LLM calls**
   - Executor: Use smaller model for memory extraction (e.g., GPT-3.5 / Llama-13B)
   - Designer: Use larger model only for skill evolution (infrequent)

### Challenge 3: Interpretability

**Problem**: Users don't know why AI made certain predictions.

**Solutions**:
1. **Show retrieved memories**
   - UI displays: "Based on: [memory 1], [memory 2], ..."
   - Clickable to see full memory content

2. **Explain predictions**
   - "Importance 85 because: sender is VIP (+40), contains deadline (+30), ..."
   - Show which skills were applied

3. **Memory management UI**
   - View all learned preferences
   - Edit/delete incorrect memories
   - Flag memories as "wrong" → added to hard cases

4. **Skill transparency**
   - Show active skills in settings
   - Display skill evolution history
   - Allow disabling specific skills

### Challenge 4: Privacy & Data Control

**Problem**: Storing user preferences raises privacy concerns.

**Solutions**:
1. **Local storage only**
   - All memories stored in local SQLite database
   - No cloud sync (unless user opts in)

2. **Clear data controls**
   - Settings → "Clear personalization data"
   - Delete all memories for specific sender
   - Export memories as JSON (transparency)

3. **Per-account isolation**
   - Memories tied to user_account_id
   - No cross-account sharing

4. **Opt-out option**
   - Settings → "Disable personalization"
   - Falls back to static importance scoring

### Challenge 5: Skill Evolution Instability

**Problem**: Designer might propose bad skills that degrade performance.

**Solutions**:
1. **Rollback mechanism**
   - Always keep snapshot of previous skill bank
   - Test on validation set before committing
   - Rollback if performance drops >5%

2. **Skill versioning**
   - Track skill evolution history
   - Can revert to previous version

3. **Incremental evolution**
   - Limit to 2-3 skill changes per round
   - Prefer refinement over new skills initially

4. **Human-in-the-loop (optional)**
   - Show proposed skill changes to user (advanced settings)
   - User can approve/reject before applying

5. **Performance monitoring**
   - Track per-skill accuracy over time
   - Auto-disable skills with accuracy <30%

---

## Success Metrics

### Primary Metrics (User Experience)

1. **Correction Rate Reduction**
   - Baseline: Current correction frequency
   - Target: 50% reduction after 3 months
   - Measure: % of emails where user corrects importance/category

2. **Prediction Accuracy**
   - Importance MAE (Mean Absolute Error)
     - Baseline: 25-30 points
     - Target: <15 points after training
   - Category accuracy
     - Baseline: 60-70%
     - Target: >85%

3. **User Satisfaction**
   - Survey: "How well does ClawMail understand your priorities?"
   - Scale: 1-5
   - Target: >4.0 average

### Secondary Metrics (System Health)

1. **Skill Evolution**
   - Number of skills evolved per month
   - Skill performance improvement over time
   - Diversity of evolved skills (covering different failure modes)

2. **Memory Quality**
   - Average confidence score of memories
   - Memory usage in predictions (retrieval hit rate)
   - Stale memory rate (not used in 30 days)

### Performance Metrics (System)

1. **Latency**
   - Memory retrieval: <100ms
   - Executor (memory extraction): <2s
   - Total overhead: <3s per email

2. **Resource Usage**
   - Memory bank size growth: <10MB per 1000 emails
   - Designer compute: <1 hour per month (skill evolution)
   - Storage: <100MB for full system (memories + skill bank)

---

## Comparison Table: Static vs. MemSkill

| Feature | Current ClawMail | MemSkill Approach |
|---------|------------------|-------------------|
| **Personalization** | None (same for all users) | User-specific learned preferences |
| **Learning** | No learning | Continuous learning from corrections |
| **Adaptability** | Fixed prompts | Skills evolve automatically |
| **Memory** | No user preference memory | Structured memory bank |
| **Feedback** | Logged but unused | Active training signal |
| **Improvement** | Manual prompt tuning | Self-improving system |
| **Cold Start** | Works immediately | Works immediately (static skills) |
| **Complexity** | Low (static prompts) | Moderate (LLM designer, no RL) |
| **Compute Cost** | Minimal | Moderate (skill evolution every 100 corrections) |
| **Interpretability** | Transparent (see prompts) | Requires explanation UI |
| **Maintenance** | Low | Medium (monitor skill evolution) |

---

## Migration Path

### Option 1: Parallel Deployment (Recommended)

1. **Keep existing system running**
2. **Deploy MemSkill in shadow mode**
   - Run both systems on each email
   - Log both predictions
   - Only show existing system to user
3. **Collect feedback for both**
   - Compare accuracy over time
4. **Gradual switchover**
   - Once MemSkill outperforms (after 100-200 corrections)
   - Switch to MemSkill for new predictions
5. **Keep fallback**
   - If MemSkill fails, fall back to static system

### Option 2: Opt-in Beta

1. **Add "Enable experimental personalization" toggle in settings**
2. **Beta users get MemSkill**
   - Collect feedback aggressively
   - Monitor performance closely
3. **Iterate based on beta feedback**
4. **Roll out to all users once stable**

### Option 3: Per-Account Gradual Rollout

1. **Enable MemSkill for 10% of accounts**
2. **Monitor metrics for 2 weeks**
3. **If successful, increase to 50%, then 100%**
4. **Rollback if issues detected**

---

## Next Steps

### Immediate (This Week)

1. ✅ Review and approve this plan
2. ✅ Decide: Parallel deployment vs. Opt-in beta vs. Gradual rollout
3. ✅ Set up development environment
   - Install dependencies: scikit-learn (for clustering), sentence-transformers (for embeddings)
   - Prepare development database (copy production for testing)

### Week 1-2 (Foundation)

1. ✅ Extend database schema
2. ✅ Implement Memory Bank CRUD
3. ✅ Create initial 6-8 hand-designed skills
4. ✅ Implement Executor (applies all skills)
5. ✅ Enhanced feedback logging

### Week 3-4 (Designer)

1. ✅ Implement hard case collection
2. ✅ Implement LLM-based failure analyzer
3. ✅ Implement skill proposer
4. ✅ Test skill evolution on hard cases
5. ✅ Validate: Do evolved skills improve accuracy?

### Week 5+ (Production)

1. ✅ Optimize performance (caching, batching)
2. ✅ Add UI for memory management
3. ✅ A/B testing vs. static system
4. ✅ Monitor and iterate

---

## 实际实现的数据流（Implementation Data Flow）

> **Status**: 已实现（Phase 1 Foundation — 不含 Designer）
> **涉及文件**: `ai_processor.py`, `ai_service.py`, `memory_bank.py`, `skill_bank.py`, `executor.py`, `app.py`, `compose_dialog.py`

本节详细描述已实现的三条核心数据流：
1. **收邮件 → 个性化 AI 分析**（importance + summary + action_items）
2. **用户修正 → 记忆提取与存储**（学习闭环）
3. **回复草稿 → 个性化生成**（reply drafting）

---

### 数据流 1：收邮件 → 个性化 AI 分析

当一封新邮件被同步到本地后，经过以下完整链路产出个性化的重要性评分和摘要：

```
SyncService 同步新邮件入库
        │
        │ emit email_synced(email_id)
        ▼
AIService.enqueue(email_id)          ← 加入异步队列
        │
        ▼
AIService._run_loop()                ← 从队列取出
        │
        ▼
AIService._process_with_retry()      ← 带重试（最多 3 次，指数退避）
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  AIProcessor.process_email(email, account_id)           │
│                                                         │
│  Step 1: 序列化邮件                                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │ _build_mail_json(email)                           │  │
│  │ → { subject, from, to, date, body_text }          │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  Step 2: 加载 Prompt 段落                                │
│  ┌───────────────────────────────────────────────────┐  │
│  │ _load_prompt_sections()                           │  │
│  │ → 从 ~/clawmail_data/prompts/*.txt 加载           │  │
│  │   或回退到 DEFAULT_PROMPT_SECTIONS                 │  │
│  │ → 包含：summary、category、is_spam、               │  │
│  │   action_category、reply_stances、importance_score │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  Step 3: ★ 检索并注入用户偏好记忆（个性化关键步骤）        │
│  ┌───────────────────────────────────────────────────┐  │
│  │ _build_memory_section(email, account_id,          │  │
│  │                       "email_analysis")            │  │
│  │                                                   │  │
│  │ 3a. 从 email.from_address 提取:                   │  │
│  │     sender_email = "boss@company.com"              │  │
│  │     sender_domain = "company.com"                  │  │
│  │                                                   │  │
│  │ 3b. MemoryBank.retrieve_for_email(                │  │
│  │         account_id, sender_email, sender_domain)  │  │
│  │     → SQL 查询 user_preference_memory:            │  │
│  │       WHERE user_account_id = ?                   │  │
│  │         AND (memory_key IS NULL                    │  │
│  │              OR memory_key = sender_email          │  │
│  │              OR memory_key = sender_domain)        │  │
│  │     → 返回所有匹配的 UserMemory 列表              │  │
│  │                                                   │  │
│  │ 3c. MemoryBank.format_memories_for_prompt(        │  │
│  │         memories, "email_analysis")               │  │
│  │     → 按 memory_type 分组格式化为中文文本:        │  │
│  │                                                   │  │
│  │     【用户偏好记忆】                               │  │
│  │     以下是根据用户历史反馈学习到的个性化偏好...     │  │
│  │                                                   │  │
│  │     发件人偏好：                                   │  │
│  │     - boss@co.com 的 newsletter 邮件重要性低(15)  │  │
│  │                                                   │  │
│  │     紧急信号偏好：                                 │  │
│  │     - 用户认为"审批"是高优先级信号                 │  │
│  │                                                   │  │
│  │     自动邮件识别：                                 │  │
│  │     - noreply@xx.com 的邮件一律低重要性            │  │
│  │                                                   │  │
│  │     摘要偏好：                                     │  │
│  │     - 用户希望 key_points 包含截止时间             │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  Step 4: 拼接最终 Prompt                                 │
│  ┌───────────────────────────────────────────────────┐  │
│  │  最终 prompt 结构:                                │  │
│  │                                                   │  │
│  │  你是ClawMail智能助手Claw。请分析以下邮件...      │  │
│  │                                                   │  │
│  │  【输入邮件】                                     │  │
│  │  { subject, from, to, date, body_text }           │  │
│  │                                                   │  │
│  │  【用户偏好记忆】        ← ★ 记忆注入在此         │  │
│  │  ...个性化偏好列表...                             │  │
│  │                                                   │  │
│  │  【summary说明】         ← 原有 prompt 段落       │  │
│  │  ...                                              │  │
│  │  【importance_score说明】                          │  │
│  │  ...                                              │  │
│  │                                                   │  │
│  │  【输出要求】                                     │  │
│  │  严格返回JSON...                                  │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  Step 5: 调用 LLM                                        │
│  ┌───────────────────────────────────────────────────┐  │
│  │ bridge.process_email(prompt, "mailAgent001")      │  │
│  │ → OpenClaw API (127.0.0.1:18789)                  │  │
│  │ → 返回 JSON:                                     │  │
│  │   {                                               │  │
│  │     "summary": { keywords, one_line, brief,       │  │
│  │                   key_points },                    │  │
│  │     "action_items": [...],                        │  │
│  │     "metadata": {                                 │  │
│  │       "importance_score": 85,  ← 个性化评分       │  │
│  │       "category": [...],                          │  │
│  │       "is_spam": false,                           │  │
│  │       "reply_stances": [...]                      │  │
│  │     }                                             │  │
│  │   }                                               │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  Step 6: 解析并构建 EmailAIMetadata                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │ _parse_response(raw) → _build_metadata()          │  │
│  │ → EmailAIMetadata(                                │  │
│  │     email_id, summary, categories, sentiment,     │  │
│  │     importance_score, reply_stances, action_items, │  │
│  │     ai_status="processed"                         │  │
│  │   )                                               │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
        │
        ▼
db.update_email_ai_metadata(meta)    ← 写入数据库
        │
        ▼
emit email_processed(email_id, "processed")  ← 通知 UI 刷新
```

**个性化效果**：LLM 在评分和生成摘要时看到了用户的历史偏好记忆，因此输出会偏向用户的个人习惯。例如同一封来自 boss@company.com 的 newsletter，没有记忆时可能评 85 分，有记忆后会评 15 分。

---

### 数据流 2：用户修正 → 记忆提取与存储（学习闭环）

当用户在 UI 上修正 AI 预测时，系统通过 Executor 分析差异并提取偏好记忆：

#### 2a. 重要性评分修正

```
用户在邮件详情页拖动重要性滑块
        │
        ▼
app.py: _apply_importance_change(email_id, old_score, new_score)
        │
        ├─ 1. 写入数据库: db.update_email_importance(email_id, new_score)
        │
        └─ 2. ★ 触发 MemSkill Executor（异步，不阻塞 UI）
               │
               ▼
        _run_executor_importance(email_id, old_score, new_score)
               │
               ├─ 从数据库读取邮件: db.get_email(email_id)
               │
               ├─ 构建 email_data: { subject, from, to, body_text }
               │
               └─ 调用 Executor（在线程池中执行）
                      │
                      ▼
        ┌──────────────────────────────────────────────────┐
        │ Executor.execute_importance_feedback(             │
        │     account_id, email_data,                      │
        │     original_score=85, new_score=20,             │
        │     sender_email, sender_domain                  │
        │ )                                                │
        │                                                  │
        │ 1. 检查修正幅度: |85-20| = 65 > 10 → 继续      │
        │    (差异 < 10 则跳过，无信息增益)                │
        │                                                  │
        │ 2. 检索已有记忆:                                │
        │    MemoryBank.retrieve_for_email(                │
        │        account_id, sender_email, sender_domain)  │
        │    → [已有的 UserMemory 列表]                    │
        │                                                  │
        │ 3. 构建 prediction / correction 文本:            │
        │    prediction = "重要性评分: 85/100"              │
        │    correction = "用户修正为: 20/100（差异: 65）"  │
        │                                                  │
        │ 4. 加载全部 5 个 Skill 的 instruction_template   │
        │    SkillBank.format_skills_for_prompt()           │
        │                                                  │
        │ 5. 拼接 Executor Prompt:                         │
        │    ┌──────────────────────────────────────────┐  │
        │    │ 你是 ClawMail 个性化记忆管理执行器       │  │
        │    │                                          │  │
        │    │ 【当前邮件】                             │  │
        │    │ { subject, from, body... }               │  │
        │    │                                          │  │
        │    │ 【AI 预测】                              │  │
        │    │ 重要性评分: 85/100                       │  │
        │    │                                          │  │
        │    │ 【用户修正】                             │  │
        │    │ 用户修正为: 20/100（差异: 65）           │  │
        │    │                                          │  │
        │    │ 【已有用户记忆】                         │  │
        │    │ - [id=xxx] type=sender_importance...     │  │
        │    │                                          │  │
        │    │ 【可用技能（全部应用）】                  │  │
        │    │ --- 技能 1: extract_sender_importance --- │  │
        │    │ --- 技能 2: extract_urgency_signals ---   │  │
        │    │ --- 技能 3: detect_automated_content ---  │  │
        │    │ --- 技能 4: extract_summary_preferences --│  │
        │    │ --- 技能 5: track_response_patterns ---   │  │
        │    │                                          │  │
        │    │ 输出 JSON 数组:                          │  │
        │    │ [{"op":"insert",...}, {"op":"update",...}]│  │
        │    └──────────────────────────────────────────┘  │
        │                                                  │
        │ 6. 调用 LLM:                                    │
        │    bridge.user_chat(prompt,                      │
        │                     "personalizationAgent001")   │
        │                                                  │
        │ 7. 解析 LLM 返回的 JSON 数组:                   │
        │    _parse_response(raw) → [                      │
        │      {                                           │
        │        "op": "insert",                           │
        │        "memory_type": "sender_importance",       │
        │        "memory_key": "boss@company.com",         │
        │        "content": {                              │
        │          "sender_name": "Boss",                  │
        │          "email_type": "newsletter",             │
        │          "typical_score": 20,                    │
        │          "pattern": "该发件人的 newsletter 类     │
        │                      邮件用户认为不重要"         │
        │        },                                        │
        │        "confidence": 0.75                        │
        │      }                                           │
        │    ]                                             │
        │                                                  │
        │ 8. 写入 Memory Bank:                             │
        │    MemoryBank.apply_memory_operations(            │
        │        account_id, operations)                   │
        │    → INSERT into user_preference_memory          │
        │    → 返回操作数量                                │
        └──────────────────────────────────────────────────┘
               │
               ▼
        记忆已存入 → 下次处理同一发件人的邮件时
                     会在 Step 3 中被检索到并注入 prompt
```

#### 2b. 摘要差评反馈

```
用户在邮件详情页点击 👎 并选择原因
        │
        ▼
app.py: _on_summary_feedback(email_id, "bad", reasons, user_comment)
        │
        └─ ★ 触发 MemSkill Executor（仅 "bad" 评价时）
               │
               ▼
        _run_executor_summary(email_id, original_summary, reasons, user_comment)
               │
               ▼
        Executor.execute_summary_feedback(
            account_id, email_data,
            original_summary = { one_line, brief, key_points, keywords },
            reasons = ["太笼统", "遗漏关键信息"],
            user_comment = "应该提到截止日期"
        )
               │
               ▼
        → LLM 分析后可能输出:
          [{ "op": "insert",
             "memory_type": "summary_preference",
             "memory_key": null,         ← 全局偏好
             "content": {
               "preference_type": "key_points",
               "issue": "摘要未提及截止时间",
               "desired": "key_points 中应包含截止日期信息",
               "pattern": "用户希望摘要重点关注截止时间和行动项"
             },
             "confidence": 0.7
          }]
               │
               ▼
        写入 Memory Bank → 下次生成摘要时注入到 prompt
```

#### 2c. 回复草稿隐式反馈

```
用户在 ComposeDialog 中编辑 AI 生成的回复草稿后发送
        │
        ▼
compose_dialog.py: _record_email_generation_feedback()
        │
        ├─ 计算 similarity_ratio = SequenceMatcher(ai_draft, final_body)
        │
        ├─ 若 similarity < 0.95 且 source == "reply_draft":
        │   └─ ★ 触发 MemSkill Executor
        │          │
        │          ▼
        │   parent._run_executor_reply(
        │       email_id, ai_draft, user_final,
        │       similarity_ratio, stance, tone
        │   )
        │          │
        │          ▼
        │   Executor.execute_reply_feedback(
        │       account_id, email_data,
        │       ai_draft = "AI 生成的原始草稿...",
        │       user_final = "用户最终发送版本...",
        │       similarity_ratio = 0.72,
        │       stance = "同意并确认", tone = "正式"
        │   )
        │          │
        │          ▼
        │   → LLM 分析后可能输出:
        │     [{ "op": "insert",
        │        "memory_type": "response_pattern",
        │        "memory_key": "colleague@co.com",   ← 针对特定收件人
        │        "content": {
        │          "context": "回复同事的工作邮件",
        │          "preference": "用户删除了 AI 添加的客套话",
        │          "tone": "简短",
        │          "pattern": "回复该同事时用户偏好简短直接的风格"
        │        },
        │        "confidence": 0.65
        │     }]
        │
        └─ 若 similarity >= 0.95:
           → 不触发 Executor（用户几乎没修改，无信息增益）
```

---

### 数据流 3：回复草稿 → 个性化生成

当用户在 ComposeDialog 点击"AI 生成回复"时：

```
用户选择回复立场 + 语气 → 点击生成
        │
        ▼
compose_dialog.py: _generate_draft()
        │
        ▼
┌──────────────────────────────────────────────────────┐
│ AIProcessor.generate_reply_draft(                    │
│     email, stance, tone, user_notes, account_id)     │
│                                                      │
│ Step 1: 构建邮件 JSON                                │
│ _build_mail_json(email)                              │
│                                                      │
│ Step 2: ★ 检索回复偏好记忆                           │
│ _build_memory_section(email, account_id,             │
│                       "reply_draft")                  │
│   │                                                  │
│   ├─ MemoryBank.retrieve_for_reply(                  │
│   │       account_id, recipient_email)               │
│   │   → 检索 response_pattern 记忆:                  │
│   │     - memory_key = NULL（通用偏好）               │
│   │     - memory_key = recipient_email（针对性偏好）   │
│   │   → 检索 summary_preference 记忆（辅助参考）     │
│   │                                                  │
│   └─ MemoryBank.format_memories_for_prompt(          │
│           memories, "reply_draft")                    │
│       → 格式化为:                                    │
│         【用户回复风格偏好】                          │
│         - 回复 colleague@co.com 时偏好简短直接        │
│         - 用户通常不使用"尊敬的"开头                  │
│         摘要偏好（参考）：                            │
│         - 用户偏好简短摘要，重点关注截止时间          │
│                                                      │
│ Step 3: 拼接 Prompt                                  │
│ ┌──────────────────────────────────────────────────┐ │
│ │ 你是ClawMail智能助手Claw，请撰写回复邮件草稿   │ │
│ │                                                  │ │
│ │ 【原邮件】 { subject, from, body... }            │ │
│ │ 【回复立场】 同意并确认时间                      │ │
│ │ 【回复风格】 正式严肃，用词规范                  │ │
│ │ 【用户补充说明】                                 │ │
│ │   用户输入的备注                                 │ │
│ │                                                  │ │
│ │   【用户回复风格偏好】  ← ★ 记忆注入在此        │ │
│ │   - 回复该同事时偏好简短直接                     │ │
│ │   - 用户通常不使用"尊敬的"开头                   │ │
│ │                                                  │ │
│ │ 【输出要求】 仅输出正文文本...                   │ │
│ └──────────────────────────────────────────────────┘ │
│                                                      │
│ Step 4: 调用 LLM                                     │
│ bridge.process_email(prompt, "draftAgent001")         │
│ → 返回个性化的回复草稿文本                           │
└──────────────────────────────────────────────────────┘
        │
        ▼
显示在 ComposeDialog 编辑区 → 用户可进一步修改后发送
```

---

### 记忆生命周期总结

```
                    ┌─────────────────┐
                    │   记忆不存在     │
                    │  （冷启动状态）   │
                    └────────┬────────┘
                             │
                    用户做出第一次修正
                    Executor 提取偏好
                             │
                             ▼
                    ┌─────────────────┐
                    │   INSERT 新记忆  │
                    │ confidence=0.5~  │
                    │ evidence_count=1 │
                    └────────┬────────┘
                             │
                    用户再次做出类似修正
                    Executor 发现已有记忆
                             │
                             ▼
                    ┌─────────────────┐
                    │   UPDATE 记忆    │
                    │ confidence 提升  │
                    │ evidence_count++ │
                    └────────┬────────┘
                             │
                    记忆被注入 AI prompt
                    AI 预测更贴近用户偏好
                    用户修正次数减少
                             │
                             ▼
                    ┌─────────────────┐
                    │   稳定状态       │
                    │ 高 confidence    │
                    │ 高 evidence      │
                    │ AI 预测准确      │
                    └────────┬────────┘
                             │
                    用户偏好发生变化
                    新的修正与记忆矛盾
                             │
                             ▼
                    ┌─────────────────┐
                    │  UPDATE/DELETE   │
                    │  Executor 检测到 │
                    │  偏好漂移        │
                    └─────────────────┘
```

---

### 已知问题 & TODO（记忆管理）

> **Status**: 已识别，待实现

#### 问题 1：记忆无限增长

**现状**：`user_preference_memory` 表没有任何数量上限，每次 Executor INSERT 都会新增一行。长期使用后单用户记忆数量会无限增长。

**影响**：
- `format_memories_for_prompt()` 会把所有匹配记忆注入 prompt → prompt 膨胀 → LLM token 消耗增加、注意力分散
- 数据库查询变慢（虽然有索引，但量大后仍有影响）

**设计方向**：
- 设定 **每类 memory_type 的上限**（如 `sender_importance` 上限 N 条）
- 当某类记忆超过上限时，将该类所有记忆 + 新记忆一起发给 LLM，让 LLM 决定如何 **合并/淘汰**，最终只保留上限数量的记忆
- 合并 prompt 示例：「以下是该用户的 N+1 条 sender_importance 记忆，请合并为不超过 N 条，保留最有价值的信息」

#### 问题 2：INSERT 无去重，可能产生重复记忆

**现状**：`apply_memory_operations()` 处理 INSERT 时直接创建新记忆，不检查是否已存在相同 `(memory_type, memory_key)` 的记忆。如果 LLM 没有正确识别已有记忆而输出 INSERT（而非 UPDATE），会产生重复记忆。

**影响**：
- 同一发件人可能存在多条 `sender_importance` 记忆，内容可能矛盾
- 注入 prompt 时给 LLM 矛盾信号，降低预测准确性

**设计方向**：
- INSERT 前检查同 `(account_id, memory_type, memory_key)` 是否已存在
- 如果已存在，自动转为「合并请求」：将新旧记忆一起发给 LLM 合并，而不是简单覆盖或重复插入

#### 问题 3：冲突处理完全依赖 LLM

**现状**：代码层没有任何冲突检测机制。记忆是否更新/删除/合并完全取决于 Executor 的 LLM 输出。LLM 可能：
- 输出 INSERT 而不是 UPDATE（导致重复）
- 输出错误的 `memory_id`（UPDATE 静默失败，无 fallback）
- 不输出 DELETE（旧的错误记忆永远留存）

**设计方向**：
- 上述问题 1、2 的上限 + 去重机制可以兜底大部分情况
- UPDATE 失败时 fallback 到 INSERT（但需结合去重）
- 长期考虑：定期扫描低 `evidence_count` + 久未更新的记忆，触发 LLM 清理

---

### 存储位置与数据格式

| 组件 | 存储位置 | 格式 |
|------|---------|------|
| 用户偏好记忆 | SQLite `user_preference_memory` 表 | `memory_content` 为 JSON TEXT |
| 技能定义 | SQLite `skill_bank` 表 | `instruction_template` 为纯文本 |
| 数据库文件 | `~/clawmail_data/clawmail.db` | SQLite WAL 模式 |
| Prompt 段落 | `~/clawmail_data/prompts/*.txt` | 纯文本（可由用户编辑实现热更新） |
| 邮件生成反馈 | `~/clawmail_data/feedback/feedback_email_generation.jsonl` | JSONL 格式（隐式反馈记录） |

### 记忆类型一览

| memory_type | 含义 | memory_key | 用于 |
|-------------|------|-----------|------|
| `sender_importance` | 发件人重要性偏好 | 发件人邮箱 | importance scoring |
| `urgency_signal` | 紧急信号偏好 | NULL（全局） | importance scoring |
| `automated_content` | 自动邮件识别 | 发件人邮箱/域名 | importance scoring |
| `summary_preference` | 摘要风格偏好 | NULL（全局） | summarizing + reply |
| `response_pattern` | 回复风格偏好 | 收件人邮箱或 NULL | reply drafting |

### 关键代码文件对照

| 数据流步骤 | 代码位置 |
|-----------|---------|
| 邮件入队 | `ai_service.py` → `AIService.enqueue()` |
| 重试循环 | `ai_service.py` → `_process_with_retry()` |
| 记忆检索 | `ai_processor.py` → `_build_memory_section()` |
| 记忆格式化 | `memory_bank.py` → `format_memories_for_prompt()` |
| Prompt 拼接 | `ai_processor.py` → `process_email()` |
| LLM 调用 | `ai_processor.py` → `bridge.process_email()` |
| 重要性修正触发 | `app.py` → `_apply_importance_change()` |
| 摘要差评触发 | `app.py` → `_on_summary_feedback()` |
| 回复草稿触发 | `compose_dialog.py` → `_record_email_generation_feedback()` |
| Executor 运行 | `executor.py` → `_run()` |
| 记忆写入 | `memory_bank.py` → `apply_memory_operations()` |
| 技能加载 | `skill_bank.py` → `_ensure_initial_skills()` |
| DB CRUD | `storage_manager.py` → `upsert_memory()` / `get_memories_for_email()` |

---

## Conclusion

This MemSkill-based personalization system represents a **significant evolution** from the current feedback-logging approach. By creating a **closed-loop learning system**, ClawMail can:

✅ **Learn** truly personalized user preferences
✅ **Adapt** to changing user behavior over time
✅ **Improve** automatically from user corrections
✅ **Evolve** new capabilities without manual engineering

While more complex than the static approach, the potential for **long-term improvement** and **deep personalization** makes this a compelling direction for ClawMail's future.

**Recommendation**: Start with **Phase 1 (Foundation)** as a low-risk way to test the infrastructure. The system works immediately with hand-designed skills, then improves automatically via Designer evolution.

---

## 附录 A：用户反馈交互设计（各 AI 输出类型）

以下列出 ClawMail 中所有可收集用户反馈的 AI 输出类型及其 UI 交互方式。已接入 MemSkill 的类型标注 ✅，待迁移的标注 ⬜。

---

### A.1 重要性评分（importance_score）✅ 已接入 MemSkill

**AI 输出**：0-100 分，评分标准：
- 90-100：极其重要，需要立即处理（如紧急工作任务、领导直接指示、关键截止日期）
- 70-89：重要，需要尽快处理（如项目进展、会议安排、客户请求）
- 40-69：一般重要（如日常沟通、信息同步、常规通知）
- 20-39：较低重要性（如订阅内容、一般群发通知）
- 0-19：不重要（如广告、推广、垃圾邮件）

**用户反馈方式（显式）**：

**方式一：手动输入分数**
在 AI 分析面板的重要性分数（如"（75）"）右侧添加一个编辑按钮，用户点击后弹出输入框，输入 0-100 的新分数。

**方式二：拖拽排序**
打开重要性排序功能后，用户可以手动拖拽邮件调整排列顺序：
- 拖到两封邮件之间：新分数 = 上下两封邮件分数的平均值
- 拖到列表最顶部：新分数 = 原第一封邮件的分数 + 5（上限100）
- 拖到列表最底部：新分数 = 原最后一封邮件的分数 - 5（下限0）

两种方式修改后，立即同步更新数据库中 `email_ai_metadata.importance_score`，邮件列表实时刷新。

**MemSkill 触发**：修改后异步调用 `Executor.execute_importance_feedback()`，提取 `sender_importance`、`urgency_signal`、`automated_content` 记忆。

---

### A.2 摘要质量（summary）✅ 已接入 MemSkill

**AI 输出**：三层摘要（`one_line` 20字一句话、`brief` 3-5行标准摘要、`key_points` 2-5条关键要点）+ `keywords`（3-5个关键词）。

**用户反馈方式（显式）**：

在 AI 摘要区域底部增加评价按钮：
- 👍（满意）/ 👎（不满意）二选一
- 点击 👎 后展开迷你反馈表单：
  - 原因选择（可多选）：太笼统 / 遗漏关键信息 / 重点偏移 / 太长 / 太短 / 关键词不准确
  - 可选填补充说明（自由文本输入框）
- 点击 👍 时直接记录正面反馈（不弹出表单）
- 同一封邮件可修改评价，以最后一次为准

**MemSkill 触发**：仅 👎 时异步调用 `Executor.execute_summary_feedback()`，提取 `summary_preference` 记忆。

---

### A.3 邮件生成 / 回复草稿（email_generation）✅ 已接入 MemSkill

**AI 输出**：
1. **回复草稿**：用户选择立场（stance）和风格（tone）后，AI 生成回复草稿
2. **写新邮件**：用户输入大纲后，AI 生成邮件正文

**用户反馈方式（隐式）**：

在用户发送邮件时自动比对 AI 生成版本与最终版本：
- 计算文本相似度（SequenceMatcher ratio）
- 相似度 ≥ 0.95 → 不记录（AI 生成已足够好）
- 相似度 < 0.95 → 记录反馈（用户对 AI 生成做了有意义的修改）
- 如果用户未使用 AI 生成功能，不记录

**反馈记录**：写入 `~/clawmail_data/feedback/feedback_email_generation.jsonl`（仍保留 JSONL 记录用于数据分析）。

**MemSkill 触发**：相似度 < 0.95 且 source == "reply_draft" 时，异步调用 `Executor.execute_reply_feedback()`，提取 `response_pattern` 记忆。

---

### A.4 邮件润色（polish_email）⬜ 待迁移

**AI 输出**：用户选择润色风格（tone）后，AI 对正文进行润色，结果替换编辑器内容。

**用户反馈方式（隐式）**：

在用户发送邮件时自动比对润色结果与最终版本：
- 润色完成后保存 AI 润色结果到 `self._polished_text`
- 发送时与最终正文比较相似度
- 相似度 ≥ 0.95 → 不记录
- 相似度 < 0.95 → 记录反馈

**反馈记录**：写入 `~/clawmail_data/feedback/feedback_polish_email.jsonl`。

**MemSkill 迁移计划**：可复用 `response_pattern` 记忆类型，提取用户对润色风格的偏好。

---

### A.5 邮件分类标签（category）⬜ 待迁移

**AI 输出**：从固定标签中选择 0-3 个：`urgent`、`pending_reply`、`notification`、`subscription`、`meeting`、`approval`，以及动态标签 `项目:XX`。

**用户反馈方式（显式）**：

在 AI 分析面板的分类 badge 区域：
- 每个 badge 右侧增加 ✕ 按钮，点击移除该标签
- badge 区域末尾增加 ＋ 按钮，点击弹出下拉列表，可选择固定标签或输入动态标签
- 修改后立即更新数据库 `email_ai_metadata.categories`

**MemSkill 迁移计划**：新增 `category_preference` 记忆类型 + 对应 skill。

---

### A.6 垃圾邮件检测（is_spam）⬜ 待迁移

**AI 输出**：`true`（垃圾邮件）或 `false`（正常邮件）。

**用户反馈方式（隐式）**：

利用现有右键菜单操作自动比对 AI 判断：
- AI 判断 `false` + 用户"标记为垃圾邮件" → `missed_spam`（漏判）
- AI 判断 `true` + 用户"移动到收件箱" → `false_positive`（误判）
- AI 判断与用户操作一致时不记录

**MemSkill 迁移计划**：可复用 `automated_content` 记忆类型，或新增 `spam_pattern` 记忆类型。

---

### A.7 行动项分类（action_category）⬜ 待迁移

**AI 输出**：为每个 action_item 分配 category（工作/学习/生活/个人）。

**用户反馈方式（显式）**：

在行动项表格中：
- 每行增加分类标签（如 `[工作]`），颜色区分四类
- 点击标签弹出下拉选择
- 修改后立即更新数据库

**MemSkill 迁移计划**：新增 `action_category_preference` 记忆类型。

---

### A.8 回复立场建议（reply_stances）⬜ 待迁移

**AI 输出**：2-4 个回复立场选项（动词开头，15 字以内）。

**用户反馈方式（隐式）**：

记录用户在回复流程中的选择行为：
- 用户选择了某个 stance 并生成草稿 → 正面信号
- 用户打开回复编辑器但未使用 AI 辅助，直接手写 → 负面信号

**MemSkill 迁移计划**：可扩展 `response_pattern` 记忆类型，记录用户偏好的回复立场模式。

---

## 附录 B：用户数据目录结构

```
~/clawmail_data/
├── chat_logs/                                  ← AI 对话记录（按 agent 分文件，追加模式）
│   ├── mailAgent001.log                        ← 邮件 AI 分析对话
│   ├── draftAgent001.log                       ← AI 回复草稿对话
│   ├── generateAgent001.log                    ← AI 写邮件对话
│   ├── polishAgent001.log                      ← AI 润色邮件对话
│   └── personalizationAgent001.log             ← MemSkill Executor 对话
├── feedback/
│   ├── feedback_email_generation.jsonl          ← 邮件生成隐式反馈（JSONL 记录）
│   └── feedback_polish_email.jsonl              ← 润色隐式反馈（JSONL 记录）
├── prompts/
│   ├── summary.txt                              ← 摘要生成 prompt
│   ├── category.txt                             ← 分类标签 prompt
│   ├── is_spam.txt                              ← 垃圾邮件检测 prompt
│   ├── action_category.txt                      ← 行动项分类 prompt
│   ├── reply_stances.txt                        ← 回复立场 prompt
│   ├── importance_score.txt                     ← 重要性评分 prompt
│   ├── mail_analysis.txt                        ← 邮件分析主模板
│   ├── reply_draft.txt                          ← 回复草稿模板
│   ├── generate_email.txt                       ← 写邮件模板
│   └── polish_email.txt                         ← 润色模板
└── clawmail.db                                  ← SQLite（含 user_preference_memory、skill_bank 表）
```

---

*End of ClawMail Personalization Plan*
