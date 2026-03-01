# ClawMail

**ClawMail** is an AI-powered desktop email client built entirely in Python. It connects to your email accounts via standard IMAP/SMTP protocols and routes every incoming message through a local AI pipeline — summarising, classifying, and extracting action items automatically — while keeping all data on your machine.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  [👤 user@outlook.com ▼]  [✉ Compose]  [↻ Sync]  [⚙ Settings]  [☀/🌙] │
├──────────┬──────────────────┬──────────────────────────────┬────────────┤
│ 📁 Folders│ 📧 Email List    │ Email Content                │ 📝 To Do  │
│          │                  │                              │            │
│ Inbox    │ ▶ Urgent email   │  Subject: Q4 Progress        │ • Reply… │
│ Drafts   │   Boss <b@c.com> │  From: boss@company.com      │ • Prepare  │
│ Sent     │   Summary line   │  ──────────────────────────  │ • Review   │
│ Trash    │   🔴 urgent      │  Full rendered HTML body…    │            │
│ Spam     │                  │                              │ 🤖 AI Chat │
│          │ Another email    │                              │            │
│ 🏷️ AI Tags│   alice@ex.com  │  [↩ Reply] [↩ All] [→ Fwd]  │ You: …    │
│ 🔴 Urgent │   Summary line  │                              │ AI: …     │
│ 🟡 Reply  │   🟡 reply 🔵  │                              │           │
│ 🔵 Meeting│                 │                              │ [Send]    │
│ 🟣 Approval                │                              │           │
└──────────┴──────────────────┴──────────────────────────────┴────────────┘
```

---

## Features

### Email Core
- **Multi-account** — add multiple accounts (Microsoft/Outlook, 163 Mail, any IMAP provider) and switch between them from the toolbar dropdown
- **IMAP sync** — incremental polling every 2 minutes with per-folder unread counts
- **Full HTML rendering** — emails are rendered by a Chromium-based `QWebEngineView`; external links open in the system browser, JavaScript is disabled
- **Compose / Reply / Forward / Draft** — full compose dialog with rich-text editing, 60-second auto-save, and a draft picker; reply pre-fills recipients and quoted body
- **Folder navigation** — Inbox, Drafts, Sent, Trash, Spam; soft-delete moves to Trash, hard-delete removes from server via Message-ID
- **Search & filter** — keyword search across subject/body/AI summaries; advanced filter by sender, date range, read status, and flag status
- **Context menu** — pin, flag, mark unread, delete, restore from trash, permanently delete

### AI Processing (Skill-Driven Architecture)
- **Skill-driven pipeline** — email analysis is delegated to external OpenClaw skill scripts via `subprocess`, with deterministic execution flow (LLM only answers questions within scripts, not controlling flow)
- **Direct script invocation** — ClawMail calls skill scripts directly (e.g. `analyze_email.py`), not through LLM routing, ensuring reliable execution
- **One-line summary** — shown in the email list as a preview subtitle
- **Smart classification** — 6 system tags (urgent, pending reply, notification, subscription, meeting, approval) plus dynamic project tags; clickable sidebar filter
- **Task extraction** — action items from email body are surfaced automatically in the To Do panel
- **User profile building** — pending facts system accumulates user information (career, contacts, projects) with confidence scoring; facts promote to `USER.md` when reaching category-specific thresholds
- **Graceful fallback** — if skill scripts are unavailable, falls back to legacy prompt-based processing via OpenClawBridge
- **Offline graceful degradation** — if AI is unavailable, emails appear immediately with a `⚠` badge and are queued for later analysis

### To Do Panel
- Grouped by today / this week / later / completed
- Search, category filter, and sort controls
- Tasks linked back to the source email
- Snooze, priority levels (high / medium / low), custom categories
- Auto-refresh every 2 minutes; snoozed tasks wake up automatically

### AI Chat Assistant — Multi-Agent System
ClawMail features a **6-agent routing system** that connects you to specialized AI assistants in OpenClaw. Each agent has a unique ID and expertise area. Switch between agents in Settings → AI Assistant to access different capabilities.

#### Available Agents

| Agent | Agent ID | Purpose | Context-Aware |
|---|---|---|---|
| **通用对话** | userAgent001 | General conversation, Q&A, brainstorming | ❌ |
| **邮件分析** | mailAgent001 | Deep email analysis, extract keywords/action items | ✅ |
| **个性化助手** | personalizationAgent001 | Handles importance score feedback, triggers personalization skills | ❌ |
| **回复起草** | draftAgent001 | Draft email replies in conversational mode | ✅ |
| **邮件生成** | generateAgent001 | Generate complete emails from outline or topic | ❌ |
| **文本润色** | polishAgent001 | Polish and refine email text for professionalism | ❌ |

**Context-aware agents** automatically attach the currently selected email's metadata (subject, sender, date, body preview) to your chat message, so you don't need to copy-paste content.

#### Chat Features
- **Dynamic panel title** — shows active agent name (e.g., "🤖 AI 助手 (个性化助手)")
- **Agent-specific routing** — ClawMail passes the agent ID to OpenClaw via the `user` parameter
- **Streaming responses** — real-time typing animation
- **Conversation logging** — all chats logged to `~/clawmail_data/chat_logs/{agentID}.log`
- **Quick reconnect** — 🔄 button to re-test AI connection
- **Settings integration** — switch agents from ⚙ Settings → AI Assistant

#### How Agent Routing Works

```python
# ClawMail sends:
POST http://127.0.0.1:18789/v1/chat/completions
{
  "model": "kimi-k2.5",
  "messages": [...],
  "user": "draftAgent001"  ← Agent ID for OpenClaw routing
}

# OpenClaw receives agent ID and:
# - Routes to agent-specific system prompt
# - Loads agent conversation history (if available)
# - Applies agent-specific capabilities
```

Agent conversation histories are logged locally in `~/clawmail_data/chat_logs/` for debugging and analysis.

---

## 🌟 Personalization System — AI Learns From Your Feedback

ClawMail features an **importance scoring feedback loop** that allows the AI to learn your email priorities over time. Unlike static rule-based systems, ClawMail adapts its importance scoring based on your actual behavior.

### How It Works

#### 1. AI Importance Scoring (0-100)

Every email receives an importance score from the AI:

- **90-100**: Extremely important, requires immediate action (urgent tasks, leadership directives, critical deadlines)
- **70-89**: Important, needs prompt attention (project updates, meeting scheduling, client requests)
- **40-69**: Moderately important (routine communication, information sync, general notifications)
- **20-39**: Low importance (subscription content, bulk notifications)
- **0-19**: Not important (ads, promotions, spam)

The scoring criteria is stored in `~/clawmail_data/prompts/importance_score.txt` and can be dynamically updated by OpenClaw.

#### 2. User Feedback — Two Ways

**Method 1: Manual Score Input**
- Click the edit button next to the importance score (e.g., "(75)")
- Enter a new score from 0-100

**Method 2: Drag-to-Reorder** (when importance sorting is enabled)
- Drag emails to reorder them in the list
- Between two emails: new score = average of neighboring scores
- To the top: new score = first email's score + 5 (max 100)
- To the bottom: new score = last email's score - 5 (min 0)

Both methods immediately update the database and refresh the email list.

#### 3. Feedback Logging

Every score modification is logged to `~/clawmail_data/feedback/feedback_importance_score.jsonl`:

```json
{
  "timestamp": "2026-02-27T14:30:00",
  "email_id": "uuid-xxx",
  "subject": "Project Deadline Reminder",
  "keywords": ["project", "deadline"],
  "one_line": "Reminder: Q1 report due Friday",
  "brief": "Manager reminds team to submit Q1 progress reports by Friday EOD.",
  "key_points": ["Q1 report", "Friday deadline"],
  "original_score": 45,
  "new_score": 78,
  "mode": "manual_input",
  "context": null
}
```

For drag-to-reorder, `context` includes the subject, keywords, summaries, and scores of neighboring emails.

#### 4. ClawMail ↔ OpenClaw Personalization Loop

```
┌─────────────────────────────────────────────────────────────────┐
│                      ClawMail (Client)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  User modifies importance score (manual or drag)                │
│         ↓                                                       │
│  Update database + log to feedback_importance_score.jsonl      │
│         ↓                                                       │
│  Check: feedback count ≥ 5?                                    │
│         ↓ Yes                                                   │
│  Trigger personalization via personalizationAgent001:          │
│                                                                 │
│  POST http://127.0.0.1:18789/v1/chat/completions                │
│  {                                                              │
│    "user": "personalizationAgent001",                          │
│    "messages": [{                                               │
│      "content": "(ClawMail-Personalization) 用户已累积...      │
│        feedback_type: importance_score                          │
│        feedback_path: ~/clawmail_data/feedback/...jsonl        │
│        prompt_path: ~/clawmail_data/prompts/importance..."      │
│    }]                                                           │
│  }                                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 OpenClaw (Local AI Gateway)                     │
│                   http://127.0.0.1:18789                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Receives trigger → routes to clawmail-personalization skill   │
│         ↓                                                       │
│  Skill execution:                                               │
│    1. GET /personalization/feedback/importance_score            │
│       ← Read 5 feedback entries from ClawMail API               │
│    2. GET /personalization/prompt/importance_score              │
│       ← Read current scoring criteria                           │
│    3. Load user profile from OpenClaw memory                    │
│    4. Analyze patterns via Kimi K2.5:                           │
│       "User consistently boosts meeting-related emails..."      │
│       "User downgrades subscription newsletters..."             │
│    5. Generate personalized importance_score.txt                │
│    6. POST /personalization/update-prompt                       │
│       → Backup old prompt to archive/, write new version        │
│    7. POST /personalization/archive-feedback                    │
│       → Archive consumed feedback, clear main file              │
│    8. POST /personalization/status                              │
│       → Notify ClawMail: "✅ Importance scoring updated"        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ClawMail (Client)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Display status: "✅ 个性化更新完成"                             │
│         ↓                                                       │
│  Next email AI analysis loads updated prompt                    │
│         ↓                                                       │
│  Importance scores now match user preferences!                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 5. Automatic Prompt Evolution

The scoring criteria in `~/clawmail_data/prompts/importance_score.txt` evolves based on your feedback:

```
Initial AI scoring:
"Meeting emails: 60 points (moderately important)"

After 5 feedback entries showing you boost meeting emails to 85+:

Updated AI scoring:
"Meeting emails: 80 points (important, requires prompt attention)"
```

Old prompts are archived to `~/clawmail_data/prompts/archive/` for version tracking.

### Data Storage

```
~/clawmail_data/
├── chat_logs/                              ← AI conversation logs (per agent)
│   ├── mailAgent001.log
│   ├── personalizationAgent001.log
│   └── ...
├── feedback/
│   ├── feedback_importance_score.jsonl      ← Active feedback (email_id deduplicated)
│   └── importance_score/
│       └── 2026-02-27T14-30-00.jsonl        ← Archived after OpenClaw consumes
├── prompts/
│   ├── importance_score.txt                 ← Current scoring criteria
│   └── archive/
│       └── importance_score_2026-02-27.txt  ← Old versions
└── clawmail.db
```

### ClawMail REST API for OpenClaw Skills

ClawMail exposes a local API at `http://127.0.0.1:9999` for OpenClaw skills:

#### Skill-Driven Data Endpoints (New)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/emails/unprocessed` | GET | List emails awaiting AI analysis |
| `/emails/{email_id}` | GET | Get full email data (body truncated to 4000 chars) |
| `/emails/{email_id}/ai-metadata` | GET | Get existing AI analysis results |
| `/emails/{email_id}/ai-metadata` | POST | Skill writes analysis results |
| `/memories/{account_id}` | GET | Get user preference memories (MemoryBank) |
| `/memories/{account_id}` | POST | Write user preference memory |
| `/pending-facts/{account_id}` | GET | Get pending user profile facts |
| `/pending-facts/{account_id}` | POST | Write pending facts (with confidence accumulation) |
| `/pending-facts/{account_id}/promote` | POST | Promote qualified facts to USER.md |

#### Personalization Endpoints (Legacy)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/personalization/feedback/{type}` | GET | Read feedback data (JSON array) |
| `/personalization/prompt/{type}` | GET | Read current prompt content |
| `/personalization/update-prompt` | POST | Backup old prompt + write new version |
| `/personalization/archive-feedback` | POST | Archive consumed feedback + clear main file |
| `/personalization/status` | POST | Notify UI of skill completion |

### Benefits

✅ **Learns from behavior** — no manual rule configuration needed
✅ **Continuous adaptation** — AI improves with every 5 feedback entries
✅ **Privacy-first** — all data stays local (ClawMail + OpenClaw)
✅ **Transparent evolution** — old prompts archived for comparison
✅ **Cross-session persistence** — learned preferences survive app restarts

---

### Accounts & Login
- **Modern login dialog** — deep-blue gradient background, centered floating white card
- **Microsoft Outlook / Hotmail** — device-code OAuth 2.0 via Microsoft Graph (no password stored); tokens stored encrypted with OS Keychain + Fernet
- **163 Mail** — IMAP auth code (授权码) flow with pre-filled server settings
- **Any IMAP provider** — generic form with configurable server/port
- **Account switcher toolbar button** — colored initials avatar, account email, ▼ dropdown; add/remove accounts without restarting

### UI & Theming
- Light and dark mode with a single toolbar toggle; mode persisted across sessions
- System theme detection on first launch
- Responsive email column widths; splitter-resizable four-panel layout
- Email list delegate: sender + time (row 1), subject (row 2), AI summary (row 3, italic), AI category tags (row 4, coloured pills)
- Status bar with sync progress and AI processing count

---

## Requirements

| Dependency | Version | Purpose |
|---|---|---|
| Python | 3.11.x | Runtime (CPython, strictly locked) |
| PyQt6 | 6.7.1 | UI framework |
| PyQt6-WebEngine | 6.7.0 | Chromium email renderer |
| PyQt6-Qt6-SVG | ≥ 6.7 | Logo SVG rendering |
| qasync | 0.27.1 | asyncio ↔ Qt event loop bridge |
| aioimaplib | 1.1.0 | Async IMAP client |
| aiosmtplib | 3.0.1 | Async SMTP client |
| httpx | 0.27.x | HTTP (Microsoft OAuth) |
| openai | 1.51.0 | OpenClaw AI gateway |
| keyring | 25.3.0 | OS Keychain (master key) |
| cryptography | 43.0.1 | Fernet credential encryption |

---

## Installation

```bash
# 1. Clone
git clone https://github.com/your-org/ClawMail.git
cd ClawMail

# 2. Create environment (conda recommended)
conda create -n clawmail python=3.11.13
conda activate clawmail

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python main.py
```

On first launch, the login dialog appears automatically. No configuration files need to be edited manually.

---

## Configuration

ClawMail stores all data in `~/clawmail_data/`:

```
~/clawmail_data/
├── clawmail.db          # SQLite database (emails, accounts, tasks, settings)
├── config.json          # Optional: { "openclaw_token": "…" }
└── oauth_debug.json     # Debug: last Microsoft OAuth token claims (dev only)
```

**AI gateway** — ClawMail communicates with OpenClaw (local AI proxy) at `http://127.0.0.1:18789/v1`. The token can be set in `config.json`:

```json
{ "openclaw_token": "your-token-here" }
```

**Credentials** are stored encrypted:
- Master key → OS Keychain (macOS Keychain / Windows Credential Manager / libsecret)
- IMAP passwords → Fernet-encrypted BLOB in the database
- OAuth tokens → Fernet-encrypted JSON `{ "type":"oauth2", "access_token":…, "refresh_token":…, "expires_at":… }`

---

## Architecture

```
ClawMail/
├── main.py                              # Entry point; qasync event loop setup
│
├── clawmail/
│   ├── domain/
│   │   └── models/
│   │       ├── account.py               # Account dataclass (provider_type, imap/smtp, status)
│   │       ├── email.py                 # Email dataclass
│   │       └── task.py                  # Task dataclass (ToDo)
│   │
│   ├── infrastructure/
│   │   ├── database/
│   │   │   └── storage_manager.py       # ClawDB — SQLite via WAL; accounts, emails, tasks, settings
│   │   ├── email_clients/
│   │   │   ├── imap_client.py           # ClawIMAPClient — aioimaplib, XOAUTH2 + plain auth
│   │   │   ├── smtp_client.py           # ClawSMTPClient — aiosmtplib, STARTTLS + OAuth
│   │   │   └── graph_client.py          # Microsoft Graph REST client (read/send mail)
│   │   ├── auth/
│   │   │   └── microsoft_graph_oauth.py # Device-code flow helpers
│   │   ├── ai/
│   │   │   ├── openclawbridge.py        # OpenClaw ↔ openai SDK bridge (sync, streamed)
│   │   │   ├── ai_processor.py          # Skill-Driven: subprocess → skill scripts (fallback: legacy prompt)
│   │   │   └── agent_registry.py        # Multi-agent configuration (6 agents)
│   │   └── security/
│   │       └── credential_manager.py    # CredentialManager — keyring + Fernet
│   │
│   ├── services/
│   │   ├── sync_service.py              # SyncService(QObject) — polling loop, Qt signals
│   │   └── ai_service.py               # AIService — queue, per-email AI pipeline
│   │
│   ├── ui/
│   │   ├── app.py                       # ClawMailApp(QMainWindow) — main window
│   │   ├── theme.py                     # ThemeManager — light/dark palette management
│   │   ├── assets/
│   │   │   └── logo.svg                 # Lobster + envelopes vector logo
│   │   └── components/
│   │       ├── account_setup_dialog.py  # Modern gradient login dialog (4-page stack)
│   │       └── compose_dialog.py        # Compose / reply / forward dialog
│   │
│   └── api/
│       └── server.py                    # Local HTTP API (used by external tools)
│
└── design/                              # Architecture & design documents
    ├── framework.md                     # Module structure & data flows
    ├── tech_spec.md                     # Technology choices, enums, security spec
    ├── UIDesign.md                      # UI layout wireframes
    ├── plan.md                          # Development roadmap (Phase 0–6)
    └── …
```

### Data Flow

#### Email Sync & AI Processing (Skill-Driven)
```
IMAP server
    │  aioimaplib (async)
    ▼
SyncService.start(account)
    │  email_synced signal
    ▼
AIService.enqueue(email_id)
    │  run_in_executor
    ▼
AIProcessor.process_email()
    │  Priority: skill script → fallback legacy
    ├─── [Skill Path] subprocess → analyze_email.py
    │      │  Script calls LLM API internally
    │      │  Script writes results via REST API → ClawDB
    │      │  Script extracts pending facts → REST API → pending_facts table
    │      ▼
    │    ClawDB (results already written)
    │
    └─── [Fallback] OpenClawBridge → OpenClaw → Kimi K2.5
           │  Agent: mailAgent001
           │  JSON: { summary, category, sentiment, action_items }
           ▼
         ClawDB.update_email_ai(…)
    │
    │  email_processed signal (Qt, main thread)
    ▼
ClawMailApp — refreshes email list item in place
```

#### Multi-Agent Chat Flow
```
User switches agent in Settings
    │  UI updates panel title (e.g., "🤖 AI 助手 (个性化助手)")
    ▼
User sends message in chat panel
    │  Agent Registry resolves agent ID & capabilities
    ▼
_send_message_async()
    │  If context-aware agent + email selected:
    │    → _build_email_context() → attach email metadata (subject, sender, body preview)
    │  Agent ID routing:
    │    → mailAgent001: process_email(prompt)
    │    → all others: user_chat(prompt, agent_id)
    ▼
OpenClawBridge → POST /v1/chat/completions
    │  Payload: { "user": "draftAgent001", "messages": [...] }
    │  Agent ID passed for OpenClaw-side routing
    ▼
OpenClaw (local) → Routes to agent endpoint
    │  OpenClaw may maintain agent-specific:
    │    - System prompts
    │    - Conversation history
    │    - Skills and capabilities
    │  (Implementation depends on OpenClaw server)
    ▼
Kimi K2.5 response (streaming)
    │  Agent-specific behavior
    ▼
ClawMailApp._append_ai_message()
    │  Real-time typing animation
    │  Response displayed in chat panel
    ▼
OpenClawBridge.log_chat()
    │  Appends to ~/clawmail_data/chat_logs/{agent_id}.log
    │  Format: timestamp + ClawMail message + OpenClaw response
```

### Async Model

`qasync` runs asyncio inside the Qt event loop on the main thread. All Qt widget operations stay on the main thread. Cross-thread communication uses Qt signals only.

```
Main thread (Qt + asyncio via qasync)
├── IMAP polling coroutine       (aioimaplib, native async)
├── SMTP send coroutine          (aiosmtplib, native async)
├── Microsoft OAuth polling      (httpx, in _OAuthWorker QThread)
└── AI calls (via executor)      (blocking OpenClaw SDK → ThreadPoolExecutor)
```

---

## Account Setup

### Microsoft Outlook / Hotmail

1. Click the account button → **Add Account** (or it appears automatically on first launch)
2. Click **Sign in with Microsoft**
3. Visit the displayed URL, enter the code, and sign in with your Microsoft account
4. The dialog closes automatically; your account appears in the toolbar

Tokens are refreshed automatically before they expire. No password is ever stored.

### 163 Mail

1. In 163 Mail web settings, go to **Settings → POP3/SMTP/IMAP** and enable IMAP
2. Generate an **auth code** (授权码) — this is different from your login password
3. In ClawMail: **Add Account → Sign in with 163 Mail**
4. Enter your email address and auth code

### Other IMAP providers

Use **Add Account → Add other IMAP account** and fill in:
- Email address
- Password or app password
- IMAP server (e.g. `imap.gmail.com`) and port (usually 993)

---

## Switching Accounts

Click the account button in the top-left of the toolbar. The dropdown shows all configured accounts with a checkmark (✓) on the active one. Switching stops the current sync service and restarts it for the selected account.

To remove an account, select **Remove Current Account** from the dropdown. All local email data for that account is deleted; the app switches to the next available account.

---

## Development Roadmap

| Phase | Status | Description |
|---|---|---|
| 0 — Infrastructure | ✅ Done | SQLite, keyring, minimal UI skeleton |
| 1 — Email basics | ✅ Done | IMAP sync, HTML rendering, compose/reply/draft, folder nav, search |
| 2 — AI core | ✅ Done | OpenClaw pipeline, summaries, classification, task extraction |
| 3 — To Do panel | ✅ Done | Task CRUD, groups, snooze, search, AI extraction |
| 4 — AI assistant | ✅ Done | AI chat panel, streaming, compose assist, feedback rating |
| Multi-account | ✅ Done | Account switcher, modern login dialog, Microsoft OAuth |
| Multi-agent system | ✅ Done | 6 specialized agents, personalization learning, cross-agent memory |
| Skill-Driven migration | ✅ Done | AI logic → OpenClaw skill scripts, pending_facts table, 9 new REST APIs, subprocess invocation with fallback |
| 5 — Search & threads | 🔜 Planned | ChromaDB semantic search, email thread grouping |
| 6 — Polish & expand | 🔜 Planned | Calendar sync, mobile, plugin marketplace, collaboration |

---

## Design Documents

All architecture and design decisions are documented in the `design/` folder:

| File | Contents |
|---|---|
| `tech_spec.md` | Canonical technology choices, enum values, security design, async model |
| `framework.md` | Module structure, layered architecture, data flow diagrams |
| `UIDesign.md` | UI wireframes, interaction rules, keyboard shortcuts |
| `plan.md` | Phase-by-phase development roadmap |
| `userDataStorageDesign.md` | SQLite schema (12 tables incl. pending_facts), FTS5 triggers |
| `emailFileDesign.md` | Email model, MIME parsing, attachment handling |
| `ToDoListDesign.md` | Task model, status state machine, UI interactions |
| `ClawConnect.md` | OpenClaw AI gateway integration protocol |
| `SkillDrivenMigration.md` | Skill-Driven architecture migration plan (ClawMail → OpenClaw Skills) |
| `SkillDesign.md` | OpenClaw Skill implementation design (analyzer, reply, executor) |
| `ClawMailChanges.md` | ClawMail-side changes for Skill-Driven migration |

---

## Security Notes

- **No cloud sync** — all email data is stored locally in `~/clawmail_data/clawmail.db`
- **Credentials encrypted at rest** — master key in OS Keychain; IMAP passwords and OAuth tokens encrypted with Fernet (AES-128-CBC) before writing to the database
- **OAuth tokens only** — for Microsoft accounts, no password is ever entered into ClawMail
- **AI requests stay local** — all AI calls go to the OpenClaw local proxy (`127.0.0.1:18789`); no email content is sent to external servers
- **JavaScript disabled** — `QWebEngineView` renders email HTML with JS off; external links open in the system browser
- **IMAP/SMTP TLS** — IMAP on port 993 (SSL), SMTP on port 465 (SSL) or 587 (STARTTLS)
