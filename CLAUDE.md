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

<!-- BEGIN sqz-claude-guidance (auto-installed by sqz init; remove this block to disable) -->

## sqz — Context Compression (READ FIRST)

sqz is installed in this project. It compresses tool output so large
files, long logs, and verbose command output cost far fewer tokens.
There are **two ways** sqz is wired in, and you should prefer each
one in the situations below.

### Preferred tools (MCP)

The `sqz-mcp` server is registered in this project's MCP config. It
exposes three read-only tools that compress their output through the
sqz pipeline:

- **`sqz_read_file`** — read a file from disk and return a compressed
  view. **PREFER this over the built-in `Read` tool** for any file
  larger than ~2KB or any file you might read more than once in the
  same session. Repeat reads return a 13-token `§ref:HASH§` reference
  instead of the full content.

- **`sqz_grep`** — search files for a literal string or regex.
  **PREFER this over the built-in `Grep`** for anything that might
  match more than a handful of lines. Caps at 200 matches by default;
  raise with `max_matches` if needed.

- **`sqz_list_dir`** — list a directory. Skips `.git`, `node_modules`,
  `target`, `dist`, `build`, `vendor`, `__pycache__` so the output
  stays focused. **PREFER this over `ls -la` via Bash** when you want
  to see a project layout.

The built-in `Read`, `Grep`, `Glob` tools remain available. Use them for:
- Tiny config files (<1KB) where compression can't help.
- Byte-exact reads you'll hash or diff (lockfiles, signatures).
- Globbing (sqz has no glob tool; `Glob` is still the right choice).

### Bash commands (hooked automatically)

When you run a shell command through the `Bash` tool, a PreToolUse hook
rewrites it to pipe output through `sqz compress`. This is transparent:
you don't need to remember to add anything, but it's useful to know
that these commands get compressed automatically:

```bash
git status           # → git status 2>&1 | sqz compress --cmd git
cargo test           # → cargo test 2>&1 | sqz compress --cmd cargo
docker ps            # → docker ps 2>&1 | sqz compress --cmd docker
kubectl get pods     # → kubectl get pods 2>&1 | sqz compress --cmd kubectl
```

The rewrite is skipped for interactive commands (`vim`, `ssh`,
`python`), compound commands (`a && b`, `a > file.txt`), and anything
already going through sqz.

### Escape hatch — when you see a `§ref:HASH§` token

If tool output contains a `§ref:a1b2c3d4§` token and you need the full
content it points at, resolve it. Three equivalent ways:

- Shell: `/usr/local/bin/sqz expand a1b2c3d4` (or paste the whole token
  `/usr/local/bin/sqz expand §ref:a1b2c3d4§`).
- MCP tool: call `expand` with `{ "prefix": "a1b2c3d4" }`.
- To get uncompressed output for one command: prefix it with
  `SQZ_NO_DEDUP=1` (e.g. `SQZ_NO_DEDUP=1 git log | sqz compress`).

If the compressed output is actively making the task harder (looping
on refs, small retries replacing one big read), call the `passthrough`
MCP tool to get raw text.

### When NOT to use sqz tools

- Writing or editing files — use the built-in `Write`/`Edit` tools.
  sqz has no write tools (by design; see issue #5 follow-up).
- Running commands interactively or in watch mode.
- Reading very small files (<1KB) where compression can't help.

<!-- END sqz-claude-guidance -->
