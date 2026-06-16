# HelloMate

**Open Source Telegram Companion Bot**

Telegram: [@HelloMateChatBot](https://t.me/HelloMateChatBot)

[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-blue)](https://github.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED.svg)](Dockerfile)

HelloMate is an open-source Telegram companion bot. Its primary mode is **Telegram
Business**: the owner connects the bot to their account, and it replies **in the
owner's name** in private chats with contacts — each contact gets their own AI
persona, memory, and settings.

The bot also works as a standalone 1-to-1 companion when someone chats with it
directly. Features include daily greetings, mood tracking, conversation memory,
AI replies (Ollama / OpenAI-compatible), voice transcription, a Mini App admin
console, reply debouncing for rapid short messages, and a personal RAG knowledge base.

## Features

- **Telegram Business (owner proxy)** — bot manages the owner's private chats with contacts
- **Per-contact AI personas** — custom system prompts via `/setpersona` or the Mini App
- **Reply debounce** — waits for a quiet period, then answers once when a contact sends several short messages in a row
- **Shared chat memory** — per-contact history includes both the contact's and the owner's messages in managed chats
- **Rolling conversation summary** — older history is compressed into a running summary so context survives beyond the recent window
- **Semantic recall** — every contact message is embedded and indexed; the most relevant past messages are retrieved by meaning and injected into the prompt, so the bot can recall things said weeks ago even if they fell out of both the window and the summary
- **Per-contact durable facts** — the bot extracts and remembers stable facts about each contact (name, city, job, birthday, interests…) and injects them into the prompt
- **Openness dial** — per-contact control of how much to disclose (`open` / `neutral` / `reserved`); applied last so it overrides persona and tone
- **Owner style learning (opt-in)** — the bot can learn the owner's real writing manner per contact and mimic it; learns only from genuine owner replies, never from AI-generated ones
- **Few-shot examples** — per-contact curated (contact message → ideal reply) pairs, editable in the Mini App or saved straight from the Playground; injected into the prompt as a tone/format guide (up to 10 per contact)
- **Business reply modes** — per-contact and global: suggest a draft, auto-reply, or stay silent
- **Suggest Inbox** — in suggest mode, drafts are persisted and reviewable in the Mini App: edit inline, copy, save as a few-shot example, or dismiss (with a pending-count badge)
- Daily greetings with timezone-aware calendar logic
- Random conversation starters and scheduled proactive greetings
- Per-user settings, i18n (`ru`, `en`), and admin controls
- User profiles, mood tracking, and conversation memory
- AI replies via Ollama or OpenAI-compatible providers
- Voice message transcription and replies (direct bot chat + Business chats)
- Telegram Mini App admin console with FastAPI backend
- Persona preset library (`data/personas.json`) and structured persona fields (admin API)
- Personal RAG knowledge base via `/remember`
- Live weather context for weather-related questions (Open-Meteo)
- SQLite or PostgreSQL persistence with Alembic migrations
- Docker and Docker Compose deployment
- Python 3.12, async `python-telegram-bot`, Ruff, Black, and Pytest

## Architecture

HelloMate keeps Telegram-specific code thin and moves behavior into testable services.
SQLite (or PostgreSQL) stores greetings, settings, profiles, mood, memory, RAG documents,
and Telegram Business connection state.

```mermaid
flowchart TB
    subgraph business ["Telegram Business (primary)"]
        Contact["Contact e.g. daughter"] <-->|private chat| Owner["Owner Telegram account"]
        Owner -.->|connected bot| Bot["@HelloMateChatBot"]
        Bot -->|business_message| BizHandler["handlers/business.py"]
        BizHandler --> Debounce["ReplyDebounceService"]
        Debounce --> Pipeline["handlers/incoming.py"]
        Pipeline -->|reply via business_connection_id| Contact
    end

    subgraph direct ["Direct bot chat (admin / testing)"]
        User["Any user"] --> Bot
        Bot --> MsgHandler["handlers/messages.py"]
        MsgHandler --> Pipeline
    end

    Pipeline --> Services["services/"]
    Services --> DB["SQLite / PostgreSQL"]
    Services --> LLM["Ollama / OpenAI"]
    MiniApp["Mini App admin"] --> API["FastAPI /admin"]
    API --> Services
    Config[".env"] --> Bot
```

## Quick Start

Requirements:

- Docker
- Docker Compose
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

```bash
cp .env.example .env
nano .env
docker compose up -d --build
```

Set `BOT_TOKEN` in `.env`, then open a private chat with
[@HelloMateChatBot](https://t.me/HelloMateChatBot) or your own bot username.

## Docker Deployment

The Compose service is named `hellomate`, the container is named `hellomate-bot`, and the
database is stored in `./data` so it survives image rebuilds.

```bash
docker compose up -d --build
docker compose logs -f --tail=100
```

Optional Ollama service for local AI:

```bash
docker compose --profile ai up -d --build
docker compose exec ollama ollama pull llama3.2
```

Set in `.env`:

```bash
LLM_PROVIDER=ollama
LLM_BASE_URL=http://ollama:11434
AI_REPLIES_ENABLED=true
```

Stop the bot:

```bash
docker compose down
```

## VPS Deployment

1. Clone the repository on your server.
2. Install Docker and Docker Compose.
3. Create `.env` from `.env.example`.
4. Set `BOT_TOKEN` and optional `ADMIN_USER_IDS`.
5. Start the service with `docker compose up -d --build`.

For AI replies, either run the optional Ollama profile or point `LLM_PROVIDER=openai` at a cloud API.

For the Mini App dashboard, set `MINI_APP_URL` to your HTTPS URL (for example `https://your-domain.com/`)
and expose port `8080` behind a reverse proxy with TLS.

### Telegram Business (owner proxy mode)

This is the **intended production setup**. The owner does not ask contacts to chat
with the bot separately — the bot is plugged into the owner's existing Telegram chats.

#### Setup

1. Enable **Business Mode** for your bot in [@BotFather](https://t.me/BotFather)
   (`/mybots` → your bot → **Bot Settings** → **Business Mode** → Turn on).
2. Set `BUSINESS_MODE_ENABLED=true` in `.env` (default).
3. On the owner's phone: **Settings → Telegram Business → Chatbots** → add your bot.
   Grant **Reply to messages**.
4. Set `ADMIN_USER_IDS` to the owner's Telegram user ID.
5. Set `AI_REPLIES_ENABLED=true` and configure the LLM provider.
6. Configure each contact via `/setpersona <user_id> <prompt>` or the Mini App at
   `http://127.0.0.1:8080` (with `MINI_APP_DEV=true`) or `MINI_APP_URL`.

A contact's `user_id` appears in logs or in the admin roster after their first message
in the managed chat.

#### Message flow

| Who writes | What the bot does |
| --- | --- |
| **Contact** | Buffers rapid messages (`REPLY_DEBOUNCE_SECONDS`), then one AI reply in the owner's voice |
| **Owner** | Records the message into the contact's memory; does **not** auto-reply on top |
| **Bot (echo)** | Ignored — no reply loop |

Example: a child sends `пап`, `разбуди`, `в 7` as three messages within a few seconds.
With `REPLY_DEBOUNCE_SECONDS=5`, the bot waits 5 seconds after the last line, combines them,
and sends **one** reply.

#### Memory model

- Memory is keyed by **contact** `user_id`, not the owner.
- In a managed chat, both sides are stored: contact → `user` role, owner → `assistant` role
  (the owner's voice the bot mimics).
- Scheduled greetings to Business contacts use the stored `business_connection_id`.

#### Tuning

```bash
# Wait longer if the contact types slowly between short messages
REPLY_DEBOUNCE_SECONDS=8

# Disable debounce (reply on every message immediately)
REPLY_DEBOUNCE_SECONDS=0

# Disable Business handlers (direct bot chat only)
BUSINESS_MODE_ENABLED=false
```

Owner identity in prompts: set `OWNER_NAME` and `BOT_NAME` in `.env`.

## Update From Git

Use the included production-friendly update script:

```bash
chmod +x update.sh
./update.sh
```

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `BOT_TOKEN` | Required | Telegram bot token from BotFather |
| `TIMEZONE` | `Europe/Minsk` | Timezone used for daily greeting dates |
| `GREETING_TEXT` | `Привет друг! Как ты)` | Default greeting message |
| `DATABASE_PATH` | `/app/data/hellomate.db` | SQLite database path (used when `DATABASE_URL` is empty) |
| `DATABASE_URL` | empty | SQLAlchemy URL; overrides `DATABASE_PATH`. e.g. `postgresql+psycopg://user:pass@host:5432/hellomate` |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `ADMIN_USER_IDS` | empty | Comma-separated Telegram admin user IDs |
| `DEFAULT_LANGUAGE` | `ru` | Fallback locale |
| `GREETING_HOUR` | `9` | Default proactive greeting hour (0-23) |
| `CONVERSATION_STARTERS` | `data/starters.json` | Path to starters JSON list |
| `MEMORY_WINDOW_SIZE` | `20` | Conversation memory window |
| `LLM_PROVIDER` | `ollama` | `ollama` or `openai` |
| `LLM_BASE_URL` | `http://localhost:11434` | LLM API base URL |
| `LLM_MODEL` | `llama3.2` | Chat model name |
| `LLM_EMBEDDING_MODEL` | `bge-m3:latest` | Embedding model for RAG (`/remember`) and semantic recall |
| `LLM_API_KEY` | empty | API key for cloud provider |
| `LLM_MAX_TOKENS` | `512` | Max response tokens |
| `LLM_TEMPERATURE` | `0.7` | Sampling temperature (0.0–2.0); lower = more focused, less rambling |
| `AI_REPLIES_ENABLED` | `false` | Enable AI replies after greeting |
| `MINI_APP_URL` | empty | HTTPS Mini App URL |
| `MINI_APP_DEV` | `false` | Start API locally without HTTPS; open `http://127.0.0.1:8080` in a browser |
| `API_HOST` | `0.0.0.0` | FastAPI bind host |
| `API_PORT` | `8080` | FastAPI bind port |
| `RAG_CHUNK_SIZE` | `500` | RAG chunk size in characters |
| `RAG_TOP_K` | `3` | Top chunks injected into prompts |
| `WEATHER_CITY` | `Minsk` | City for live weather lookups (Open-Meteo) |
| `OWNER_NAME` | `Owner` | Owner name injected into persona prompts |
| `BOT_NAME` | `HelloMate` | Bot display name in persona templates |
| `BUSINESS_MODE_ENABLED` | `true` | Enable Telegram Business mode (bot manages owner's private chats) |
| `REPLY_DEBOUNCE_SECONDS` | `5` | Wait after the last contact message before replying; batches rapid short messages (`0` = off) |
| `SUMMARY_ENABLED` | `true` | Enable the rolling conversation summary |
| `SUMMARY_REFRESH_INTERVAL` | `10` | Refresh the summary after this many messages age out of the window |
| `SUMMARY_MAX_CHARS` | `1500` | Max length of the stored summary |
| `FACTS_ENABLED` | `true` | Enable per-contact durable fact extraction |
| `FACTS_REFRESH_INTERVAL` | `5` | Re-extract facts after this many new contact messages |
| `STYLE_ENABLED` | `true` | Enable owner writing-style learning (still opt-in per contact) |
| `STYLE_REFRESH_INTERVAL` | `5` | Refresh the learned style after this many new owner messages |
| `STYLE_MAX_CHARS` | `800` | Max length of the stored style profile |
| `RECALL_ENABLED` | `true` | Enable semantic recall (embed + retrieve past messages by meaning) |
| `RECALL_TOP_K` | `3` | Max past messages injected per reply |
| `RECALL_MIN_CHARS` | `15` | Skip indexing messages shorter than this (too little signal) |
| `RECALL_MIN_SCORE` | `0.5` | Cosine-similarity threshold (0-1); a hit must score at least this to be injected |
| `RECALL_BACKFILL_BATCH` | `50` | Messages indexed per incoming message — controls how fast existing history is lazily backfilled |

> All of `SUMMARY_*`, `FACTS_*`, `STYLE_*`, and `RECALL_*` only take effect when `AI_REPLIES_ENABLED=true`. Recall and RAG share `LLM_EMBEDDING_MODEL`, which must be available on your LLM provider.

## Commands

| Command | Description |
| --- | --- |
| `/start` | Welcome message and profile bootstrap |
| `/help` | Explains bot behavior |
| `/about` | Project information |
| `/lang` | Set language (`ru` or `en`) |
| `/profile` | View profile |
| `/setname` | Set display name |
| `/mood` | Record mood with inline buttons |
| `/moodhistory` | View recent mood entries |
| `/remember` | Save a note to your knowledge base |
| `/dashboard` | Open Telegram Mini App dashboard |
| `/admin` | Admin command help |
| `/settings` | View or set global bot settings |
| `/setlang` | Admin: set user language |
| `/setgreeting` | Admin: enable/disable user greetings |
| `/greetings` | Admin: list all greeting rules for a user |
| `/addgreeting` | Admin: add a greeting rule with its own text and schedule |
| `/delgreeting` | Admin: delete a greeting rule by number |
| `/togglegreeting` | Admin: enable/disable a greeting rule by number |
| `/setgreettext` | Admin: set legacy single greeting text (when no rules exist) |
| `/setgreetschedule` | Admin: set legacy single greeting schedule |
| `/setstarters` | Admin: enable/disable random conversation starters |
| `/sethour` | Admin: set user greeting hour |
| `/setpersona` | Admin: set full AI system prompt for a user |
| `/getpersona` | Admin: view effective AI system prompt for a user |
| `/userinfo` | Admin: inspect user settings |

Global bot setting `default_persona` (via `/settings set default_persona ...`) applies when a user has no custom persona.

### How replies are triggered

**Telegram Business (managed chats):** contact text messages go through the debounce
buffer, then greeting check + AI reply. Owner messages are stored only.

**Direct bot chat:** normal private text messages trigger the daily greeting check on
the first message of the day. After the greeting (or when greetings are off), AI replies
are sent when `AI_REPLIES_ENABLED=true`.

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Run checks:

```bash
ruff check .
black --check .
pytest
```

Run the bot locally:

```bash
python -m app.main
```

### Running the Mini App admin console locally

The admin console is a single-page app served by the same FastAPI backend that
runs inside the bot process — **no separate server needed**. In dev mode it skips
Telegram auth so you can use it in a plain browser.

**Step 1 — configure `.env`**

```bash
MINI_APP_DEV=true          # disables Telegram initData auth check
ADMIN_USER_IDS=<your-telegram-id>   # your Telegram user ID
AI_REPLIES_ENABLED=true    # optional — needed for the Playground tab
API_PORT=8080              # FastAPI port (change if 8080 is taken)
```

Your Telegram user ID can be found with [@userinfobot](https://t.me/userinfobot).

**Step 2 — start the bot**

_With Docker (recommended):_

```bash
docker compose up -d --build
docker compose logs -f | grep -E "API server|MINI_APP_DEV"
```

Port `8080` is already mapped in `docker-compose.yml` (`"8080:8080"`), so nothing
extra is needed. The FastAPI server and the Telegram bot run in the same container.

_Without Docker (local venv):_

```bash
source .venv/bin/activate
python -m app.main
```

Either way, once running you'll see:

```
INFO  API server started on 0.0.0.0:8080
WARNING  MINI_APP_DEV is enabled — open http://127.0.0.1:8080 in a browser for local testing
```

**Step 3 — open the console**

Open [http://127.0.0.1:8080](http://127.0.0.1:8080) in your browser.

The yellow "Локальный режим" banner confirms auth is bypassed. All four tabs work:

| Tab | What you can do |
|-----|----------------|
| **Контакты** | Browse contacts; edit AI persona, openness dial, style-learning toggle, durable facts, and greetings per contact; preview the resolved prompt |
| **Плейграунд** | Test a persona live — pick a contact, type a message, see the AI draft and latency |
| **Статистика** | Message / AI reply / greeting counts for the last 7 / 30 / 90 days |
| **Настройки** | Set global reply mode (предлагать / авто / выкл), edit `default_persona`, etc. |

> **Tip:** contacts appear in the roster only after they have sent at least one message
> (direct bot chat or Telegram Business). Use the Playground tab with a known `user_id`
> to test personas even before any contact data exists.

**Trigger contacts to appear (Business mode)**

Send yourself a message via a secondary Telegram account, or use `/userinfo <user_id>` in
your admin chat after the contact writes in a managed Business chat.

**Use a tunnel for in-Telegram testing**

To open the Mini App inside Telegram (via the menu button) you need HTTPS. Use ngrok or
Cloudflare Tunnel, then set `MINI_APP_URL` to the tunnel URL:

```bash
ngrok http 8080
# copy the https URL, e.g. https://abc123.ngrok.io
MINI_APP_URL=https://abc123.ngrok.io
MINI_APP_DEV=false   # auth is enforced when MINI_APP_URL is set
```

Restart the bot, then open your bot in Telegram and tap the Mini App button.

## Roadmap Status

- Phase 1: daily greetings, SQLite, Docker
- Phase 2: conversation starters, scheduled greetings, admin settings, i18n
- Phase 3: profiles, mood tracking, conversation memory
- Phase 4: Ollama/OpenAI LLM replies, voice transcription
- Phase 5: Mini App dashboard, FastAPI, RAG knowledge base
- Phase 6 (partial): structured persona fields, preset library (`data/personas.json`), owner identity env vars
- Phase 7 (partial): admin-gated API, contacts roster, persona playground, HTML admin console
- **Telegram Business transport** (done): `business_connection` / `business_message` handlers, per-contact managed-chat memory, proactive greetings via `business_connection_id`
- **Reply debounce** (done): `REPLY_DEBOUNCE_SECONDS` batches rapid contact messages before one AI reply
- Phase 8 (done): PostgreSQL-ready persistence, admin Mini App contacts/playground/stats, per-contact Business reply modes (suggest / auto / off)
- Phase 10 (done): rolling conversation summary for context beyond the recent window
- Phase 11 (done): per-contact durable facts — LLM extraction, Mini App fact editor, prompt injection
- Phase 12 (done): per-contact openness dial (`open` / `neutral` / `reserved`) and opt-in owner writing-style learning
- Phase 13 (done): semantic recall — per-message embeddings indexed in the background (lazy watermark backfill), retrieved by cosine similarity and injected between the summary and the live window; recall coverage shown in the Mini App **Статистика** tab
- Phase 14 (done): per-contact curated few-shot examples — owner-picked ideal replies injected as a tone/format guide; editable in the contact card or saved directly from the Playground
- Phase 15 (done): Mini App UX overhaul — Suggest Inbox (review/edit/copy/save/dismiss drafts), contacts search + sort + reply-mode/examples badges, contact detail split into sub-tabs (Персона/Факты/Эталоны/История), native Telegram toasts/haptics/BackButton

## Contributing

Contributions are welcome. Please keep changes focused, add or update tests for behavior changes,
and run the local checks before opening a pull request:

```bash
ruff check .
black --check .
pytest
```

## License

HelloMate is released under the [MIT License](LICENSE).
