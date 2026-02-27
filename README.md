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

### AI Processing
- **Automatic pipeline** — every new email triggers a single OpenClaw/Kimi API call that produces all of the below in one round-trip
- **One-line summary** — shown in the email list as a preview subtitle
- **Smart classification** — 6 system tags (urgent, pending reply, notification, subscription, meeting, approval) plus dynamic project tags; clickable sidebar filter
- **Urgency detection** — separate urgency sidebar filter (urgent / normal / low)
- **Task extraction** — action items from email body are surfaced automatically in the To Do panel
- **AI feedback** — 1–5 star rating + comment on any AI summary; feedback logged for model improvement
- **Offline graceful degradation** — if AI is unavailable, emails appear immediately with a `⚠` badge and are queued for later analysis

### To Do Panel
- Grouped by today / this week / later / completed
- Search, category filter, and sort controls
- Tasks linked back to the source email
- Snooze, priority levels (high / medium / low), custom categories
- Auto-refresh every 2 minutes; snoozed tasks wake up automatically

### AI Chat Assistant — Multi-Agent System
ClawMail features a **6-agent AI system** that adapts to your needs. Each agent is a specialized AI personality that understands different aspects of email management and personal productivity. Switch between agents in Settings → AI Assistant to access different capabilities.

#### Available Agents

| Agent | Purpose | Context-Aware |
|---|---|---|
| **通用对话** (userAgent001) | General conversation, Q&A, brainstorming | ❌ |
| **邮件分析** (mailAgent001) | Deep email analysis, extract keywords/action items | ✅ |
| **个性化助手** (personalizationAgent001) | Learn your preferences, customize AI behavior | ❌ |
| **回复起草** (draftAgent001) | Draft email replies based on your tone and stance | ✅ |
| **邮件生成** (generateAgent001) | Generate complete emails from outline or topic | ❌ |
| **文本润色** (polishAgent001) | Polish and refine email text for professionalism | ❌ |

**Context-aware agents** automatically include the currently selected email in their analysis, so you don't need to copy-paste content.

#### Chat Features
- **Dynamic panel title** — shows active agent name (e.g., "🤖 AI 助手 (个性化助手)")
- **Streaming responses** — real-time typing animation
- **Persistent chat history** — conversations saved locally per session
- **Quick reconnect** — 🔄 button to re-test AI connection
- **Settings integration** — switch agents from ⚙ Settings → AI Assistant

---

## 🌟 Personalization System — Your AI Learns Your Preferences

ClawMail's **Personalization Agent** (`personalizationAgent001`) is a breakthrough feature that makes your email assistant truly yours. Unlike traditional rule-based systems, this agent learns your preferences through natural conversation and adapts ClawMail's AI behavior to match your workflow.

### How Personalization Works

#### 1. Teaching Your Preferences
Open the AI chat panel and switch to **个性化助手 (Personalization Agent)** in Settings:

```
You: "I want meeting invitations to be marked as urgent"
AI: "Understood! I'll prioritize emails with calendar invites or meeting-related keywords..."

You: "Emails from my boss (boss@company.com) should always be high priority"
AI: "Got it! I'll treat all emails from boss@company.com as urgent..."

You: "I prefer formal tone when replying to external clients"
AI: "I'll remember to use formal language for external recipients..."
```

#### 2. ClawMail ↔ OpenClaw Collaboration Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                         ClawMail (Client)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. User switches to personalizationAgent001                   │
│  2. User teaches preferences via chat:                         │
│     "I want weekly reports to be auto-archived"                │
│                                                                 │
│  3. ClawMail routes to OpenClaw:                               │
│     POST http://127.0.0.1:18789/v1/chat/completions            │
│     {                                                           │
│       "model": "kimi-k2.5",                                     │
│       "messages": [                                             │
│         { "role": "system", "content": "You are personali..." },│
│         { "role": "user", "content": "I want weekly repor..." } │
│       ],                                                        │
│       "user": "personalizationAgent001"  ← Agent routing       │
│     }                                                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP/JSON
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OpenClaw (Local AI Gateway)                  │
│                      http://127.0.0.1:18789                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  4. OpenClaw receives request, identifies agent:                │
│     - Extracts "user": "personalizationAgent001"               │
│     - Loads agent-specific memory & system prompt              │
│     - Applies personalization rules from previous chats        │
│                                                                 │
│  5. Routes to Kimi K2.5 with agent context:                    │
│     - Includes user's historical preferences                   │
│     - Maintains agent conversation memory                      │
│     - Applies learned customization rules                      │
│                                                                 │
│  6. Kimi K2.5 processes with personalization context:          │
│     - Understands "weekly reports" pattern                     │
│     - Remembers user's archive preference                      │
│     - Generates response with personalized rules               │
│                                                                 │
│  7. OpenClaw stores new preference in agent memory:             │
│     Preference DB (~/openclaw_data/agents/)                    │
│     ├── personalizationAgent001/                               │
│     │   ├── preferences.json                                   │
│     │   │   {                                                   │
│     │   │     "email_rules": [                                  │
│     │   │       {                                               │
│     │   │         "pattern": "weekly report",                   │
│     │   │         "action": "auto-archive",                     │
│     │   │         "priority": "low"                             │
│     │   │       }                                               │
│     │   │     ],                                                │
│     │   │     "sender_preferences": {                           │
│     │   │       "boss@company.com": "urgent"                    │
│     │   │     }                                                 │
│     │   │   }                                                   │
│     │   └── chat_history.jsonl                                 │
│     │                                                           │
│     ├── mailAgent001/                                          │
│     ├── draftAgent001/                                         │
│     └── ...                                                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Streaming response
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         ClawMail (Client)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  8. ClawMail displays AI response:                             │
│     "✓ Preference saved! Weekly reports will be archived..."   │
│                                                                 │
│  9. Future emails benefit automatically:                        │
│     - mailAgent001 analyzes new "Weekly Report" email          │
│     - OpenClaw loads personalizationAgent001 preferences       │
│     - Applies learned rules: category=notification, low urgency│
│     - ClawMail UI reflects personalized classification         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

#### 3. Agent Specialization & Memory Isolation

Each of the 6 agents maintains its own conversation memory and context in OpenClaw:

- **mailAgent001** — Remembers your email analysis patterns and keyword preferences
- **personalizationAgent001** — Stores all learned preferences and customization rules
- **draftAgent001** — Learns your writing style, tone preferences, and common reply templates
- **generateAgent001** — Remembers your email structure preferences and common topics
- **polishAgent001** — Adapts to your preferred formality level and writing style
- **userAgent001** — General conversation history for Q&A and brainstorming

When you chat with `personalizationAgent001`, those preferences are **automatically applied** to all other agents' behavior:

```
You (to personalizationAgent001): "I prefer concise summaries, max 20 words"
→ OpenClaw saves to preference DB

Later, when mailAgent001 processes a new email:
→ OpenClaw loads personalizationAgent001 preferences
→ AI summary respects your 20-word limit
→ All future summaries are automatically concise
```

#### 4. Cross-Agent Preference Sharing

```
User Preference Layer (shared across all agents)
       ↓
┌──────────────────────────────────────────────────┐
│  personalizationAgent001 → Preference Database   │
│  - Email priority rules                          │
│  - Sender importance mappings                    │
│  - Category preferences                          │
│  - Tone/style preferences                        │
│  - Summary length preferences                    │
└──────────────────────────────────────────────────┘
       ↓                    ↓                    ↓
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ mailAgent001 │  │ draftAgent001│  │ generateAgent│
│ (Analysis)   │  │ (Replies)    │  │ (Compose)    │
│              │  │              │  │              │
│ Applies your │  │ Uses your    │  │ Follows your │
│ urgency rules│  │ tone prefs   │  │ style guide  │
└──────────────┘  └──────────────┘  └──────────────┘
```

### Example Personalization Conversations

#### Teaching Email Priority Rules
```
You: "Treat emails with '发票' (invoice) in the subject as low priority"
AI: "✓ Saved! Invoice-related emails will be marked as low urgency."

You: "Emails from HR department should be marked for pending reply"
AI: "✓ Understood! HR emails will be tagged with 🟡 pending reply."
```

#### Customizing AI Summaries
```
You: "Make summaries more detailed, include sender's key points"
AI: "✓ I'll provide richer summaries with sender context going forward."

You: "For meeting invites, always extract time and location in the summary"
AI: "✓ Meeting summaries will now highlight time/location info prominently."
```

#### Adapting Reply Tone
```
You: "When replying to clients, use formal language and include 'Best regards'"
AI: "✓ I'll maintain professional tone for external replies."

You: "For team members, keep replies casual and friendly"
AI: "✓ Internal emails will have a relaxed, conversational tone."
```

### Benefits of Personalization

✅ **Zero manual rules** — just talk to the AI like a human assistant
✅ **Persistent learning** — preferences saved permanently in OpenClaw
✅ **Cross-agent consistency** — your preferences apply to all 6 agents
✅ **Privacy-first** — all preference data stays on your machine
✅ **Evolving intelligence** — agents get smarter with every conversation
✅ **Natural language interface** — no complicated config files or regex

### Technical Architecture

The personalization system is built on three key components:

1. **Agent Registry** (`clawmail/infrastructure/ai/agent_registry.py`)
   - Defines all 6 agents with metadata (ID, name, description, capabilities)
   - Routes chat messages to the correct OpenClaw agent endpoint

2. **OpenClaw Agent Memory** (server-side, `~/openclaw_data/`)
   - Per-agent conversation history and preference storage
   - Shared preference layer accessed by all agents
   - Persistent across ClawMail restarts

3. **Dynamic Routing** (`clawmail/ui/app.py`)
   - Context-aware agents automatically attach current email
   - Agent ID passed to OpenClaw for memory/preference lookup
   - Seamless switching between 6 specialized personalities

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
│   │   │   ├── ai_processor.py          # Prompt building + JSON response parsing
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

#### Email Sync & AI Processing
```
IMAP server
    │  aioimaplib (async)
    ▼
SyncService.start(account)
    │  email_synced signal
    ▼
AIService.enqueue(email_id)
    │  run_in_executor (OpenClaw is sync)
    ▼
AIProcessor → OpenClawBridge → OpenClaw (local) → Kimi K2.5
    │  Agent: mailAgent001
    │  JSON: { summary, category, sentiment, action_items }
    ▼
ClawDB.update_email_ai(…)
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
    │    → _build_email_context() → attach email metadata
    │  Agent ID routing:
    │    → mailAgent001: process_email()
    │    → all others: user_chat(message, agent_id)
    ▼
OpenClawBridge → POST /v1/chat/completions
    │  Headers: { "user": "personalizationAgent001" }
    │  OpenClaw routes to agent-specific memory & preferences
    ▼
OpenClaw (local) → Agent Memory Lookup
    │  Loads ~/openclaw_data/agents/{agent_id}/
    │    - preferences.json (if personalization agent)
    │    - chat_history.jsonl (conversation context)
    │  Applies learned rules to prompt
    ▼
Kimi K2.5 response (streaming)
    │  Personalized based on agent memory
    ▼
ClawMailApp._append_ai_message()
    │  Real-time typing animation
    │  Response displayed in chat panel
    ▼
OpenClaw updates agent memory
    │  New preferences saved (if personalizationAgent001)
    │  Chat history appended
    │  Preferences propagated to other agents
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
| 2 — AI core | ✅ Done | OpenClaw pipeline, summaries, classification, urgency, task extraction |
| 3 — To Do panel | ✅ Done | Task CRUD, groups, snooze, search, AI extraction |
| 4 — AI assistant | ✅ Done | AI chat panel, streaming, compose assist, feedback rating |
| Multi-account | ✅ Done | Account switcher, modern login dialog, Microsoft OAuth |
| Multi-agent system | ✅ Done | 6 specialized agents, personalization learning, cross-agent memory |
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
| `userDataStorageDesign.md` | SQLite schema, table definitions, FTS5 triggers |
| `emailFileDesign.md` | Email model, MIME parsing, attachment handling |
| `ToDoListDesign.md` | Task model, status state machine, UI interactions |
| `ClawConnect.md` | OpenClaw AI gateway integration protocol |
| `prompt.md` | AI prompt templates and output format specifications |
| `PersonalizationPlan.md` | Multi-agent system architecture, personalization workflow |

---

## Security Notes

- **No cloud sync** — all email data is stored locally in `~/clawmail_data/clawmail.db`
- **Credentials encrypted at rest** — master key in OS Keychain; IMAP passwords and OAuth tokens encrypted with Fernet (AES-128-CBC) before writing to the database
- **OAuth tokens only** — for Microsoft accounts, no password is ever entered into ClawMail
- **AI requests stay local** — all AI calls go to the OpenClaw local proxy (`127.0.0.1:18789`); no email content is sent to external servers
- **JavaScript disabled** — `QWebEngineView` renders email HTML with JS off; external links open in the system browser
- **IMAP/SMTP TLS** — IMAP on port 993 (SSL), SMTP on port 465 (SSL) or 587 (STARTTLS)
