# CLAUDE.md

Guidance for AI agents working in this repo. Keep it short; prefer fixing the code/docs over expanding this file.

## What this is

HelloMate — a Telegram **Business companion** bot. The bot manages the owner's private chats with their contacts (drafts/auto-replies), learns each contact (facts, style, summary, semantic recall), and exposes an admin **Mini App**. It also has an owner-only **personal-assistant** mode (`/assistant`) in the direct bot chat.

## Architecture (thin handlers, fat services)

- `app/handlers/` — Telegram entry points (`business.py`, `messages.py`, `voice.py`, `commands.py`, `admin.py`, `assistant.py`); the shared pipeline is `incoming.py`.
- `app/services/` — business logic (reply, memory, summary, facts, recall, examples, suggestions, style, assistant, settings, persona…). Put behavior here, keep handlers thin.
- `app/database/` — `schema.py` is the single source of truth (SQLAlchemy Core); `repositories/` wrap tables; `db.py` owns the engine and provisions schema on startup.
- `app/api/` — FastAPI admin API (`admin_routes.py`) behind Telegram initData auth; serves the Mini App.
- `app/web/index.html` — the entire Mini App (one HTML file with inline JS; no build step).
- Backends: SQLite (local/tests) and PostgreSQL (prod) — keep all SQL dialect-agnostic.

## Conventions

- **Migrations:** add a file under `alembic/versions/` for every `schema.py` change; chain `down_revision` to the current head. Fresh DBs use `create_all` + stamp head; existing DBs run `alembic upgrade head` automatically on container start (`db.py:_provision_schema`). Use `render_as_batch`/`batch_alter_table` for SQLite ALTERs. Test the upgrade path against a DB stamped at the prior head, not just `create_all`.
- **i18n:** user-facing strings live in `app/i18n/locales/{ru,en}.json`; keys must match across both. `translate()` only calls `.format` when kwargs are passed.
- **Tests/lint (run before committing):**
  ```
  .venv/bin/python -m pytest
  .venv/bin/python -m ruff check <changed files>
  ```
  Use the venv interpreter (`.venv/bin/python`), not bare `python`. For Mini App JS changes, sanity-check syntax with `node --check` on the extracted `<script>`.
- **Commits:** end messages with the `Co-Authored-By` trailer. Commit/push only when asked.

## Security / privacy (important)

- This is a **public repo**. NEVER commit real infrastructure details (server IPs, DNS domains/subdomains, owner Telegram user IDs, tokens). Use placeholders in tests (e.g. user id `100000001`). Real deployment specifics live only in the agent's private memory, never here.
- The bot handles private personal conversations. Treat contact messages/facts as sensitive; default to local LLM for contact data.

## LLM provider

- Pluggable via env: `LLM_PROVIDER=ollama|openai`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_EMBEDDING_MODEL`, `LLM_TEMPERATURE`. Provider is currently global (chat + embeddings + transcription). Switching embedding models invalidates the existing recall index (different vector space) — re-index if you change it.

## Deploy

Prod tracks `main` and is deployed via Docker; Alembic upgrades run on container start. Exact host/commands are in the private agent memory, not in this public repo.
