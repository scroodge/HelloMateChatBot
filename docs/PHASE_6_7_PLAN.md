# Phase 6 + 7 — Detailed Implementation Plan

_Last updated: 2026-06-14 · See [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md) for the
overall context, product model, and DB assessment._

> **Parallel delivery (June 2026):** Telegram Business transport (`business_message`,
> managed-chat memory, `business_connection_id` replies) and reply debounce
> (`REPLY_DEBOUNCE_SECONDS`) shipped alongside Phase 6/7 work. Documented in
> [README.md](../README.md#telegram-business-owner-proxy-mode).

**Goal of these two phases:** give the bot owner a fast, friendly way to configure
the bot **per contact** and to **watch what it's doing** — via a Telegram Mini App
admin console — built on a structured persona model with reusable presets.

- **Phase 6 = the data + behavior foundation** (owner identity, structured
  persona, preset library, prompt rendering). No UI; fully testable.
- **Phase 7 = the admin console** (admin-gated API, contacts roster, write
  endpoints, prompt playground, stats, and the HTML UI) built on Phase 6.

Both phases preserve the existing CLI admin commands — the Mini App is an
*additional* surface over the same services, not a replacement.

---

## Guiding principles

1. **Services stay the source of truth.** The API and the Telegram handlers both
   call the same service methods. No business logic in routes or HTML.
2. **Backwards compatible.** Existing `persona_prompt`, admin commands, and tests
   keep working. New structured fields are additive.
3. **Admin-only, target-scoped.** Every console endpoint requires the caller to be
   in `admin_user_ids` and acts on an explicit `{user_id}` in the path.
4. **No build step (yet).** The Mini App stays a single static HTML file with
   vanilla JS until it outgrows it.
5. **Test each slice** before moving on; keep the suite green.

---

## Phase 6 — Persona foundation

### 6.1 Owner identity

The bot replies *in the owner's name*. Today there is no first-class notion of who
the owner is, so personas don't consistently sound like them.

- Store owner identity as **global bot settings** (reuse `bot_settings`; no schema
  change): `owner_name`, `owner_about` (optional one-line description of voice/role).
- Inject it at the **top of every resolved persona** so all personas inherit it
  (e.g. *"You are {owner_name}'s personal assistant. You reply on {owner_name}'s
  behalf in private chats…"*), unless a full custom override opts out.
- Localized (ru/en) framing via i18n.

### 6.2 Structured persona model

Make persona editable as fields (so the console can show form controls) while
keeping the free-text override.

**Migration `011_persona_structured.sql`** — add nullable columns to
`user_settings`:

| Column | Meaning |
| --- | --- |
| `persona_preset` | preset key the owner started from (e.g. `family`, `friend`) |
| `persona_relationship` | how this contact relates to the owner (free text label) |
| `persona_tone` | tone descriptor (e.g. warm, playful, formal) |
| `persona_topics` | topics to lean into |
| `persona_boundaries` | things to avoid / hard limits |

`persona_prompt` (migration 009) is **retained as a full override**.

**Resolution order** (`SettingsService.resolve_persona_prompt`, updated):
1. `persona_prompt` (explicit full override) → use as-is (still inherits owner
   identity prefix unless it already defines one).
2. else if any structured field / preset is set → **render** via `PersonaService`.
3. else global `default_persona` bot setting.
4. else built-in `build_persona_prompt()` (current fallback).

### 6.3 Preset library + PersonaService

- **`data/personas.json`** — localized preset templates. Each preset:
  ```json
  {
    "key": "family",
    "label": {"en": "Family member", "ru": "Член семьи"},
    "relationship": {"en": "close family", "ru": "близкий родственник"},
    "tone": {"en": "warm, caring, informal", "ru": "тёплый, заботливый, неформальный"},
    "topics": {...},
    "boundaries": {...}
  }
  ```
  Starter set: `family`, `friend`, `partner`, `mentor`, `assistant`.
- **`app/services/persona_service.py`** (new):
  - `list_presets(language)` → presets for the UI.
  - `get_preset(key)`.
  - `render(owner_name, owner_about, fields, language)` → final system prompt
    string from owner identity + structured fields. Pure function, no I/O.

### 6.4 Wiring

- `app/models/settings.py` — add the 5 fields to `UserSettings` (defaults `None`).
- `app/database/repositories/settings.py` — include new columns in
  `get_user_settings` / `upsert_user_settings`.
- `app/services/settings_service.py` — inject `PersonaService`; update
  `resolve_persona_prompt`; add `set_persona_fields(...)`, `get_owner_identity()`,
  `set_owner_identity(...)`; extend `persona_source()` to report `structured`.
- `app/services/reply_service.py` — keep `build_persona_prompt` as the final
  fallback; owner-identity prefix applied in the resolution path.
- `app/main.py` — construct `PersonaService`, pass into `SettingsService`.

### 6.5 Phase 6 tests
- `tests/test_persona_service.py` — preset loading, render output (ru/en), owner
  identity inclusion.
- Extend `tests/test_settings_service.py` — resolution order across the 4 levels,
  `set_persona_fields`, owner identity get/set.
- Existing persona/admin tests must stay green.

**Phase 6 Definition of Done:** structured persona + presets render correctly,
resolution order verified, owner identity inherited, suite green. No UI yet.

---

## Phase 7 — Mini App admin console

### 7.1 Admin gating (do first)

Today the API trusts any valid Telegram caller and returns *their own* data. The
console must be **owner-only** and able to read/write *other* users' data.

- `app/api/main.py` / `create_api_app` — pass `admin_user_ids` from config into
  the router.
- `app/api/auth.py` / routes — add a dependency `require_admin_caller` that
  validates `initData`, extracts `user_id`, and raises **403** unless it's in
  `admin_user_ids`.
- New endpoints live under `/api/admin/*`. Existing self-scoped `/profile`,
  `/mood`, `/memory` are marked legacy (kept for compatibility; not used by the
  new UI).

### 7.2 ReplyService refactor (enables the playground + reuse)

Split "assemble context" from "generate + persist":

- Extract context assembly into a reusable method, e.g.
  `build_messages(user_id, user_message, language, *, persona_override=None,
  use_memory=True)` returning the full `messages` list (already mostly exists as
  `_build_messages`).
- Add **`preview_reply(...)`** — assembles messages (optionally with a
  `persona_override` and optionally pulling a target user's memory/mood/RAG, or a
  clean sandbox), calls `llm_service.complete`, and returns
  `{reply, messages, latency_ms}` **without** calling `record_assistant_message`.
- `generate_reply` keeps persisting (unchanged behavior).
- _Token usage:_ providers' `complete()` returns a string today. v1 playground
  shows **assembled context + reply + latency**; token/cost counts are a follow-up
  that requires providers to return a richer result (tracked, not blocking).

### 7.3 Endpoints

| Method & path | Purpose |
| --- | --- |
| `GET /api/admin/users` | Contacts roster: id, display_name, last_seen, language, greeting_enabled, persona_source, message_count |
| `GET /api/admin/users/{id}` | Full detail: profile, settings, structured persona, resolved prompt, recent mood, counts |
| `PUT /api/admin/users/{id}/persona` | Set preset / structured fields / full override |
| `PUT /api/admin/users/{id}/settings` | Language, greeting on/off, hour, timezone, starters |
| `GET/POST/DELETE /api/admin/users/{id}/greetings` | Greeting-rule CRUD (reuse `GreetingRulesService`) |
| `GET /api/admin/presets` | Persona preset library for the UI |
| `GET /api/admin/settings` · `PUT /api/admin/settings` | Global: owner identity, `default_persona`, `greetings_enabled` |
| `GET /api/admin/stats` | Overview aggregates (see 7.4) |
| `POST /api/admin/persona/test` | **Playground**: `{prompt?, fields?, message, target_user_id?}` → `{reply, assembled_messages, latency_ms}` |

All under `require_admin_caller`. Reuse existing services for all reads/writes.

### 7.4 Usage/events for stats

Real monitoring needs recorded activity (nothing to aggregate today beyond raw
messages).

- **Migration `012_events.sql`** — `events(id, user_id, type, tokens, meta, created_at)`
  with index `(created_at)` and `(user_id, created_at)`. Types: `message_in`,
  `reply_out`, `greeting_sent`, `voice_in`, `error`.
- `app/database/repositories/events.py` + `app/services/stats_service.py`
  (record + aggregate).
- Hook recording into `handlers/messages.py`, `reply_service.py`,
  `jobs/greeting_jobs.py`, `handlers/voice.py`.
- `GET /api/admin/stats` returns: total contacts, active today/7d, messages over
  time, replies, greetings sent, error count, provider reachability.

### 7.5 Frontend — admin console (`app/web/index.html`)

Rebuild the read-only dashboard into a multi-view console (vanilla JS, Telegram
theme vars, `X-Telegram-Init-Data` header):

- **Contacts** — roster list → click a contact → editor (persona preset dropdown,
  structured fields, language, greeting schedule, timezone, starters) → Save.
- **Playground** — persona text/fields + test message + optional "test against
  contact" selector → shows the reply and a collapsible **assembled context** view
  (system prompt, memory, mood, RAG, weather) + latency. **Save to contact** button.
- **Stats** — overview cards + simple time series + per-contact drill-down.
- **Settings** — owner identity, default persona, global toggles.

### 7.6 Phase 7 tests
- `tests/test_api_admin.py` — admin gating (403 for non-admin), roster, persona/
  settings writes, greetings CRUD, playground returns reply + messages and
  **does not persist** to memory.
- `tests/test_stats_service.py` — event recording + aggregation.
- Existing `tests/test_api_auth.py` stays green.

**Phase 7 Definition of Done:** owner can, from the Mini App, list contacts,
configure a contact's persona/settings/greetings, tune a prompt in the playground
with full transparency, and view live stats — all admin-gated. Suite green.

---

## Build order (slices)

Each slice is independently shippable and leaves the suite green.

| Slice | Contents | Depends on |
| --- | --- | --- |
| **6A** | Migration 011, `UserSettings` fields, settings repo | — |
| **6B** | `PersonaService` + `data/personas.json` + render | 6A |
| **6C** | Owner identity + updated `resolve_persona_prompt` + tests | 6B |
| **7A** | Admin gating (`require_admin_caller`) + `GET /admin/users` + `/users/{id}` | 6C |
| **7B** | `ReplyService.preview_reply` (dry-run split) + `POST /admin/persona/test` | 7A |
| **7C** | `PUT /persona`, `PUT /settings`, greetings CRUD, `GET /presets`, `GET/PUT /settings` (global) | 7A |
| **7D** | Events migration 012 + recording hooks + `GET /admin/stats` | 7A |
| **7E** | Admin-console HTML (contacts, playground, stats, settings) | 7B–7D |

**Recommended first build:** **6A → 6B → 6C → 7A → 7B**. That delivers a working
prompt playground end-to-end (the owner's explicit ask) and establishes the two
reusable foundations — structured persona and the admin-gated, dry-run-capable
service layer — that every later slice builds on.

---

## Risks & decisions to confirm

- **Token/cost in playground** — deferred to a provider enhancement (return usage
  from `complete()`); v1 shows latency + assembled context only. _OK?_
- **Legacy self-scoped endpoints** (`/profile`,`/mood`,`/memory`) — keep as-is vs.
  remove. Plan: keep, mark legacy.
- **One persona per contact** for now; multi-persona switching is Phase 10.
- **AI disclosure** — whether contacts are told they're talking to an assistant is
  a product/policy decision, not addressed here (flagged in PROJECT_ANALYSIS §5).
- **FKs/cascade & `/forgetme`** — deferred; events table will add the first
  indexed activity log but per-contact purge remains a later cross-cutting item.
</content>

---

## Phase 9: Business suggest-reply mode

**Goal:** owner gets full control over whether the bot replies automatically, suggests a draft for copy-paste, or stays silent — configurable per contact with a global default.

### Modes
| Mode | Behavior |
|------|----------|
| `auto` | Bot replies directly to contact (original behavior) |
| `suggest` | Bot DMs owner: contact name + their message + AI draft + 📋 copy button |
| `off` | Bot does nothing for incoming contact messages |

**Global default:** `suggest`  
**Resolution chain:** per-contact `business_reply_mode` (UserSettings) → bot setting `business_reply_mode` → `"suggest"`

### Slices

| Slice | Contents |
|-------|----------|
| **9A** | `UserSettings.business_reply_mode` field + schema column + Alembic migration |
| **9B** | `SettingsService.get_business_reply_mode()` resolver + `set_business_reply_mode()` |
| **9C** | `ReplyService.draft_reply()` — like generate but skips memory recording |
| **9D** | `incoming.py` pipeline: `reply_mode` param + `on_suggest` callback routing |
| **9E** | `business.py` handler: resolve mode, build owner DM with `CopyTextButton` |
| **9F** | Admin API: expose `business_reply_mode` in GET/PUT /users/{id}/settings |
| **9G** | Mini App UI: global selector in Settings tab, per-contact override in contact detail |
| **9H** | Tests: mode resolution, draft_reply no-memory, business handler routing |

### Memory behaviour
- Contact's incoming message: recorded immediately (always)
- Draft in suggest mode: NOT recorded
- Owner's pasted reply: arrives as business message with sender=owner → existing `sender_is_owner=True` path records it as assistant turn automatically — no extra code needed
