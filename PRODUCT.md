# Product

## Register

product

## Users

HelloMate's primary UI user is the Telegram account owner. They inspect how
their Business chats are being handled, review AI drafts, and correct contact
memory from a phone-sized Telegram Mini App. Their immediate job is to know
whether the reply pipeline is working and whether it acted safely, without
having to read logs or query the database.

## Product Purpose

HelloMate manages or suggests replies in the owner's private Telegram chats.
The Mini App is the owner-only operational console for contacts, suggestions,
memory, prompt testing, and AI-quality feedback. Success means the owner can
understand system state and take the next safe action quickly.

## Brand Personality

Calm, candid, capable. The interface should feel like a thoughtful personal
assistant: quietly precise during normal operation and unmistakably clear when
attention is needed.

## Anti-references

Avoid a noisy monitoring wall, a generic SaaS metric dashboard, and decorative
AI visual effects. Do not hide important state behind unexplained jargon or
make a contact feel surveilled.

## Design Principles

1. Show the next useful action before implementation detail.
2. Separate contact-visible outcomes from owner-only diagnostics.
3. Make automation status legible at a glance, then offer progressive detail.
4. Preserve privacy by default: diagnostics never need raw prompts or hidden
   conversation content.
5. Fit the owner’s actual environment: a compact Telegram Mini App, often
   checked quickly between messages.

## Accessibility & Inclusion

Use semantic labels and text alongside colour for every status. Support the
Telegram theme, respect reduced-motion preferences, preserve tap targets of at
least 44px where practical, and keep operational copy clear in Russian.
