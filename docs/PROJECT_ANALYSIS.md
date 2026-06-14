# HelloMate — Project Analysis & Roadmap

_Last updated: 2026-06-14_

HelloMate ([@HelloMateChatBot](https://t.me/HelloMateChatBot)) is an open-source
Telegram companion bot.

**Product model (important):** the **admin is the bot's owner**. The bot acts as
the owner's **personal AI assistant/proxy** — it replies to the owner's contacts
in private chats **in the owner's name**. The owner configures, **per contact**,
how the bot should behave: like a *family member* with one person, a *friend*
with another, a formal *assistant* with a third. **Only the admin configures the
bot** — this is by design, not a limitation. The desired improvement is a clean
**Telegram Mini App admin console (owner-only)** that does two things:
**(1) setup** — manage every contact's persona/relationship and bot settings
without typing commands or raw user IDs; and **(2) observe** — view stats and
monitor what the bot is doing (per-contact activity, recent conversations, mood,
greeting status, usage/costs).

This document captures: (1) the current architecture, (2) what is already built,
(3) the gap between the current state and the product goal, (4) how comparable
projects approach the same problem, and (5) a prioritized roadmap.

---

## 1. Architecture overview

The codebase deliberately keeps Telegram-specific code thin and pushes behavior
into testable services. Layering:

```
Telegram update ─► handlers/ ─► services/ ─► database/repositories/ ─► SQLite
                                   │
                                   └─► services/llm (Ollama / OpenAI), weather, RAG
Telegram Mini App ─► api/ (FastAPI) ─► services/ ─► SQLite
```

| Layer | Location | Responsibility |
| --- | --- | --- |
| Entrypoint | [app/main.py](../app/main.py) | Wires config → DB → services → handlers, registers jobs, optionally starts the FastAPI thread |
| Config | [app/config.py](../app/config.py) | Frozen dataclass loaded from env (`.env`) |
| Handlers | [app/handlers/](../app/handlers/) | `commands`, `admin`, `messages`, `mood`, `voice`, `callbacks`, `helpers` |
| Services | [app/services/](../app/services/) | Greeting, settings, profile, mood, memory, reply, RAG, embedding, weather, conversation starters, LLM providers |
| Repositories | [app/database/repositories/](../app/database/repositories/) | One module per table; raw SQL over SQLite |
| Migrations | [app/database/migrations/](../app/database/migrations/) | Versioned `.sql` files applied by [migrations.py](../app/database/migrations.py) |
| API / Mini App | [app/api/](../app/api/), [app/web/index.html](../app/web/index.html) | FastAPI read endpoints + a single static HTML dashboard |
| i18n | [app/i18n/](../app/i18n/) | `ru` / `en` JSON locales |
| Tests | [tests/](../tests/) | 51 tests, all passing (`pytest -q`) |

**Tech stack:** Python 3.12, async `python-telegram-bot`, FastAPI + uvicorn,
SQLite (WAL), httpx, Ruff/Black, Pytest. Deploys via Docker Compose with an
optional Ollama profile for local LLMs.

### Data model (SQLite)

Migrations `001`–`009` define:

- `greetings` — last greeting date per user (daily-greeting dedupe).
- `user_settings` — language, greeting on/off, hour, starters, custom greeting
  text, **greeting schedule** (interval/weekday/day), and **`persona_prompt`**
  (the per-user system prompt, migration `009`).
- `bot_settings` — global key/value (e.g. `default_persona`, `greetings_enabled`).
- `profiles` — display name, timezone, created/last-seen.
- `moods` — mood entries (1–5 + note).
- `conversation_messages` + `conversation_summaries` — per-user sliding-window
  memory (default 20) and a summary slot (settable but **not yet auto-populated**).
- `rag_documents` — per-user notes for the `/remember` knowledge base, chunked
  and embedded.
- `user_greeting_rules` (migration `008`) — **multiple** scheduled greetings per
  user, each with its own text + schedule (supersedes the single legacy greeting).

### 1.1 Database assessment

**Verdict: SQLite is the right choice and the schema is sound** for a single-owner
bot with dozens–hundreds of contacts and low write volume. WAL mode, versioned
migrations with a `schema_version` table, and repository-per-table separation are
all in place. No need for Postgres unless this becomes multi-owner/high-concurrency.

**Fixed in this pass:**
- **Cross-thread connections (was a real bug).** A single `sqlite3` connection was
  created in the main thread while the FastAPI Mini App runs in a separate thread
  ([main.py:185](../app/main.py:185)); any API DB call would have raised
  `ProgrammingError` (`check_same_thread`). [sqlite.py](../app/database/sqlite.py)
  now uses **thread-local connections** (each thread gets its own), with
  `busy_timeout=5000` to absorb brief write contention. This unblocks the admin
  console / Mini App.
- **Missing indexes.** Migration `010` adds indexes for the per-user, time-ordered
  queries used by the memory window, mood history, RAG, and the planned stats
  screens: `conversation_messages(user_id, created_at)`,
  `mood_entries(user_id, recorded_at)`, `documents(user_id)`,
  `document_chunks(document_id)`.

**Still open (do with Phase 7):**
- **No usage/events table.** Real monitoring stats (message/reply/error counts,
  token/cost estimates) need their own table — nothing to aggregate today beyond
  raw messages.
- **No foreign keys / cascade.** `foreign_keys=ON` is set but no table declares
  FKs, so a per-contact "delete everything" (privacy/`/forgetme`) means manual
  deletes across tables. SQLite can't add FKs to existing tables without a rebuild;
  add them when introducing new tables / a cleanup routine.
- **Timestamp format drift.** Some columns default to `CURRENT_TIMESTAMP`
  (`YYYY-MM-DD HH:MM:SS`), others store app-written ISO strings; standardize before
  stats parse them.
- **RAG search is brute-force cosine in Python** over BLOB embeddings — fine at
  personal scale; revisit (sqlite-vec/FAISS) only if a contact accrues thousands
  of chunks.

---

## 2. What is already done ✅

### Core messaging
- Private 1-to-1 chat only (groups/channels ignored).
- Daily greeting with timezone-aware "first message of the day" logic
  ([greeting_service.py](../app/services/greeting_service.py)).
- Multiple per-user **greeting rules** with daily/weekly/monthly schedules and
  per-rule text ([greeting_rules_service.py](../app/services/greeting_rules_service.py),
  [greeting_schedule.py](../app/services/greeting_schedule.py)).
- Proactive scheduled greetings via an hourly job
  ([greeting_jobs.py](../app/jobs/greeting_jobs.py)).
- Random conversation starters from `data/starters.json`.

### AI replies
- Pluggable LLM providers: Ollama and OpenAI-compatible
  ([services/llm/](../app/services/llm/)), selected by `LLM_PROVIDER`.
- Context-aware reply assembly ([reply_service.py](../app/services/reply_service.py)):
  system persona + recent memory + latest mood + conversation summary + RAG notes
  + live weather (when the message looks weather-related).
- CJK-leak guard: if the model emits Chinese characters it is asked to rewrite.
- Voice messages: transcription hook + reply ([voice.py](../app/handlers/voice.py)).

### Personalization (the heart of the vision — partially built)
- **Per-user persona** (`persona_prompt`) that fully replaces the system prompt,
  with a resolution chain: **user persona → global `default_persona` → built-in
  inner-voice prompt** (`resolve_persona_prompt` in
  [settings_service.py](../app/services/settings_service.py)).
- Built-in persona is an "informal personal inner voice" (Russian «ты», first
  person, never "I'm a bot").
- Per-user language (`ru`/`en`), greeting prefs, and timezone.

### Memory & knowledge
- Sliding-window conversation memory keyed by Telegram `user_id`.
- Personal RAG knowledge base via `/remember` with embeddings
  ([rag_service.py](../app/services/rag_service.py),
  [embedding_service.py](../app/services/embedding_service.py)).
- Mood tracking with inline buttons + history.

### Mini App & API
- FastAPI backend with **validated Telegram `initData`** auth
  ([api/auth.py](../app/api/auth.py)) — read endpoints `/profile`, `/mood`,
  `/memory`, `/health`.
- Static dashboard ([app/web/index.html](../app/web/index.html)) that renders
  profile, mood, and recent messages.

### Ops
- Versioned migrations, Docker/Compose, optional Ollama profile, `update.sh`,
  GitHub Actions CI, Ruff/Black, 51 passing tests.

---

## 3. The gap: current state vs. the goal ⚠️

Admin-only configuration is **correct and matches the product model** — the owner
sets up the bot for each of his contacts. The engine is in good shape: per-contact
persona, per-contact settings, the resolution chain, memory, and RAG all exist.
The gaps are about **the owner's setup ergonomics** and a few missing capabilities,
**not** about giving end users control.

1. **Setup requires raw user IDs and command syntax.** Every config command
   (`/setpersona`, `/setgreeting`, `/setlang`, `/sethour`, `/addgreeting`, …) is
   admin-gated (correct) but takes a target `user_id` and exact arguments
   ([app/handlers/admin.py](../app/handlers/admin.py)). The owner must already
   know each contact's numeric ID and remember the syntax. This is the main
   friction the Mini App should remove.

2. **No way to browse the owner's contacts.** Nothing lists "who has talked to
   the bot" so the owner can pick a person and configure them. The data exists
   (`profiles`, `user_settings`) but there is no admin-facing roster
   (command or API) — so step one of setup (find the user) is manual.

3. **The Mini App is a read-only dashboard scoped to the caller, not an admin
   console.** The API exposes only `GET` endpoints that return *the requesting
   user's own* data ([api/routes.py](../app/api/routes.py)); the HTML just
   displays it. The stated goal — *"a Mini App to set up the bot"* — needs an
   **admin-only** Mini App that lists contacts and writes their persona/settings.

4. **No persona presets / relationship templates.** Persona is a single free-text
   prompt. There is no "Family member / Friend / Mentor / Assistant" template
   library the owner can pick and tweak per contact, so each persona is written
   from scratch.

5. **Persona is text-only.** No structured personality (assistant name, the
   contact's relationship to the owner, tone, topics, boundaries) that could
   drive both the prompt and a friendly form UI.

6. **Memory summary is never generated.** `conversation_summaries` can be written
   but nothing populates it, so per-contact long-term context silently caps at the
   20-message window.

7. **The bot does not reliably speak "in the owner's name."** The built-in persona
   is a generic "personal inner voice"; there is no first-class notion of *the
   owner's identity* (name/signature/voice) that every persona inherits so replies
   consistently read as coming from the owner's assistant.

These are the difference between "a CLI-configured companion bot" (today) and "an
owner-operated personal-assistant product with a clean admin console" (the goal).

---

## 4. How comparable projects approach this

Research into the current open-source landscape (June 2026):

| Project | Relevant approach | Takeaway for HelloMate |
| --- | --- | --- |
| **BotAnya** ([github](https://github.com/ndrco/BotAnya)) | Role-play bot; multiple "worlds" and characters defined as JSON scenarios; per-chat character selection; Ollama + OpenAI/GigaChat | Validates the **persona-as-structured-data + preset library** idea HelloMate is missing |
| **TelegramRPBot** ([github](https://github.com/Flagro/TelegramRPBot)) | One operator describes the agent and how it should act, scoped per chat | Confirms **operator-defined, per-chat persona** — the same single-owner model as HelloMate |
| **tg-local-llm** ([github](https://github.com/ExposedCat/tg-local-llm)) | Per-chat preferences that modify the system prompt; tool use for local LLMs | Supports **per-contact prompt modifiers** and adding tools |
| **Soul-of-Waifu** ([github](https://github.com/jofizcd/Soul-of-Waifu)) | Companion "engine" with voice + avatars, local LLM | Shows where a companion product can go (voice/persona depth) |
| **OpenClaw** ([site](https://openclaw.ai/)) | Personal-assistant framing, persistent memory, "does things" via tools, companion setup apps | Validates **owner-runs-his-own assistant + memory + a setup app**; closest to HelloMate's model |

**Common patterns HelloMate is missing:** structured/preset personas and a real
**admin setup surface** (console). **HelloMate's genuine strengths vs. these:**
clean service/repository architecture, real test coverage, validated Mini App auth
already in place, and per-contact RAG + mood — a solid base to build the admin
console on.

---

## 5. Recommended roadmap

Ordered by leverage toward the goal: **a frictionless admin setup experience**.

### Phase 6 — Owner identity + persona presets (highest priority)
Make personas fast to author and consistently "in the owner's voice."
- Add an **owner-identity** layer: owner name/signature/voice stored once
  (e.g. `bot_settings`) and inherited by every per-contact persona, so replies
  read as the owner's assistant by default.
- Add a **persona preset library** (`data/personas/*.json` or a table): Family
  member, Friend, Partner, Mentor/Coach, Formal assistant — each a localized
  template the owner picks per contact. Reuse the existing `resolve_persona_prompt`
  chain; presets just fill `persona_prompt`.
- Model persona as **structured fields** (assistant name, the contact's
  relationship to the owner, tone, topics, boundaries, language) rendered into the
  system prompt, so the admin console can show friendly form controls instead of a
  raw textarea.
- _Touches:_ [settings_service.py](../app/services/settings_service.py),
  [reply_service.py](../app/services/reply_service.py),
  [handlers/admin.py](../app/handlers/admin.py), a new migration.

### Phase 7 — Mini App admin console (highest priority)
Turn the read-only, self-scoped dashboard into an **owner-only** console that does
both **setup** and **monitoring**.

**Access:** gate the Mini App and all admin endpoints to the owner — check the
caller's validated `user_id` is in `admin_user_ids` (today the API trusts whoever
calls and returns their own data; that must become admin-gated and target-scoped).

**Setup half**
- **Contacts roster** (`GET /admin/users`) listing everyone in
  `profiles`/`user_settings` so the owner picks a person — no raw IDs needed.
- Authenticated **write** endpoints scoped to a target user
  (`PUT /admin/users/{id}/persona|settings`, CRUD `/admin/users/{id}/greetings`)
  reusing `validate_init_data` + admin check.
- Console flow: list contacts → open one → pick a persona preset → tweak fields →
  set language, greeting schedule, timezone → save. Telegram theme vars already
  wired.
- A **global settings** screen (owner identity, `default_persona`,
  `greetings_enabled`, model/provider info).

**Prompt playground / test section** (explicit owner requirement)
A dedicated screen where the owner **tunes a persona prompt and sees how answers
are generated** before saving it to a contact.
- Inputs: the persona prompt (free text or structured fields) + a test user
  message + an optional "test against contact X" selector (to pull that contact's
  real memory/mood/RAG context) or a clean sandbox.
- Output: the generated reply **plus full transparency** into how it was built —
  show the exact assembled messages (system prompt + memory window + mood +
  summary + RAG notes + weather), token usage, and latency. This answers "how is
  the answer generated," not just "what is the answer."
- Iterate live: edit prompt → re-run → compare, without committing. A **Save to
  contact** button persists the tuned prompt only when the owner is happy.
- **Must be a dry run:** today `ReplyService.generate_reply` records the assistant
  message to memory ([reply_service.py](../app/services/reply_service.py:94)).
  The playground needs a non-persisting path (build messages + `complete()`
  without `record_assistant_message`) so testing never pollutes a contact's
  history.
- _New endpoint:_ `POST /admin/persona/test` → `{prompt, message, target_user_id?}`
  returns `{reply, assembled_messages, usage}`. Admin-gated.

**Monitoring half** (the "view stats / what's going on" requirement)
- **Overview dashboard:** total contacts, active today/this week, messages over
  time, greetings sent, AI-replies count, errors.
- **Per-contact drill-down:** recent conversation transcript, mood trend, last
  seen, greeting status, which persona is active.
- **Activity feed / health:** recent bot actions, LLM/provider reachability,
  job status. (Requires lightweight event/usage logging — see below.)
- _New data:_ add minimal **usage/event logging** (message counts, reply counts,
  errors, token/cost estimates) so stats are real, not guessed. A new
  `events`/`usage` table + repository.
- _Touches:_ [api/routes.py](../app/api/routes.py), [api/auth.py](../app/api/auth.py),
  [app/web/](../app/web/), services (read aggregates + write methods + validation),
  a new migration for usage/events.

### Phase 8 — Admin onboarding & ergonomics
- "Open setup console" button from `/admin` and on first run.
- Resolve contacts by `@username` (not just numeric ID) in admin commands as a
  fallback for users who prefer the CLI.
- Sensible first-run defaults so a contact gets a reasonable persona before the
  owner customizes it.

### Phase 9 — Memory depth
- Populate `conversation_summaries` with a periodic/threshold-based summarization
  job so per-contact context survives beyond the 20-message window.
- Optional: a long-term "facts about this contact" store distinct from RAG notes
  (birthday, relationship details, preferences) injected into every prompt.

### Phase 10 — Companion/assistant richness (optional, differentiators)
- Proactive, persona-flavored check-ins (greeting rules already provide the
  scheduling backbone — make the text LLM-generated in persona voice).
- Multiple personas per contact with switching.
- Image understanding / sending; richer voice (TTS replies).
- Per-contact model/temperature overrides.

### Cross-cutting hardening
- **Rate limiting / cost controls** per contact (the owner pays for all LLM
  usage across every contact, so abuse/runaway costs matter).
- **Safety/boundaries** in persona templates (especially companion personas) and
  content filtering — the owner is accountable for what the bot says in his name.
- **Privacy & disclosure:** decide and document whether/how contacts are told
  they're talking to an AI assistant; expose data export/delete per contact.
- Consider migrating Mini App from a single static HTML to a small build if the
  console grows.

---

## 6. Quick reference

**Run locally:** `python -m app.main` (set `DATABASE_PATH=./data/hellomate.db`).
**Tests:** `pytest -q` (51 passing). **Lint:** `ruff check . && black --check .`.
**Mini App:** starts only when `MINI_APP_URL` is set; API on `API_PORT` (8080).
**AI replies:** require `AI_REPLIES_ENABLED=true` + a reachable LLM provider.

### Sources (comparison research)
- [ai-companion topic — GitHub](https://github.com/topics/ai-companion)
- [BotAnya](https://github.com/ndrco/BotAnya)
- [TelegramRPBot](https://github.com/Flagro/TelegramRPBot)
- [tg-local-llm](https://github.com/ExposedCat/tg-local-llm)
- [Soul-of-Waifu](https://github.com/jofizcd/Soul-of-Waifu)
- [OpenClaw](https://openclaw.ai/)
</content>
</invoke>
