---
name: project-business-reply-mode
description: Business reply mode feature — per-contact auto/suggest/off with global default suggest
metadata:
  type: project
---

Feature: **Business suggest-reply mode** — owner gets a DM notification with the contact's message + AI-drafted reply + one-tap copy button. Owner pastes reply themselves.

Three modes per contact (+ global default):
- `auto` — bot replies directly to contact (original behavior)
- `suggest` — bot DMs owner with draft + CopyTextButton; no direct reply sent
- `off` — bot does nothing

Resolution chain: per-contact `business_reply_mode` (UserSettings) → global bot setting `business_reply_mode` → builtin default `suggest`.

**Why:** Owner wanted to stay in control of replies for important contacts while still getting AI assistance.

**How to apply:**
- Global default is `suggest` (not `auto`)
- Memory recording: incoming contact message IS recorded; draft is NOT recorded in suggest mode (owner's paste arrives as owner-side business message, recorded as assistant turn automatically)
- Direct bot chat (messages.py) always uses `auto` — this mode only affects Business chats
- CopyTextButton is available in PTB 22.8 — use it for the DM notification
- Owner DM format: contact name + their message + draft text + inline copy button
