---
name: HelloMate Mini App
description: A calm, owner-only control surface for private Telegram reply assistance.
colors:
  canvas: "#ffffff"
  surface: "#f0f0f5"
  ink: "#111111"
  hint: "#888888"
  action-blue: "#2979ff"
  action-ink: "#ffffff"
  border: "#00000014"
  success: "#2e7d32"
  warning: "#f0a500"
  danger: "#c62828"
typography:
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    letterSpacing: "0.05em"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "12px"
    fontWeight: 400
rounded:
  field: "8px"
  card: "12px"
  pill: "20px"
spacing:
  compact: "6px"
  field: "8px"
  base: "12px"
  roomy: "18px"
components:
  button-primary:
    backgroundColor: "{colors.action-blue}"
    textColor: "{colors.action-ink}"
    rounded: "{rounded.field}"
    padding: "9px 11px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "{spacing.base}"
  input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.field}"
    padding: "9px 11px"
---

# Design System: HelloMate Mini App

## Overview

**Creative North Star: "The Quiet Control Room"**

HelloMate is an owner-only operational surface checked in short, private moments between Telegram messages. It is calm, candid, and compact. It must make the next safe action obvious before exposing diagnostics, while preserving the feeling that the owner, not the system, remains in control.

The system is deliberately restrained: Telegram theme values lead, neutral surfaces structure content, and one blue action color directs attention. It rejects a noisy monitoring wall, a generic SaaS metric dashboard, decorative AI effects, and any diagnostic treatment that makes private contacts feel surveilled.

**Key Characteristics:**

- Dense but breathable mobile-first operational information.
- Text-labelled status, never color-only meaning.
- Progressive detail: outcome first, implementation detail second.
- Flat tonal layers, not ornamental depth.

## Colors

The palette is Telegram-aware by default; these fallback values keep the same restrained hierarchy when host theme variables are unavailable.

### Primary

- **Clear Action Blue** (`#2979ff`): used only for the primary next action, active navigation, links, and keyboard focus.

### Neutral

- **Paper Canvas** (`#ffffff`): page and field background.
- **Soft Utility Surface** (`#f0f0f5`): cards, navigation, and grouped owner-only controls.
- **Direct Ink** (`#111111`): primary reading and decisions.
- **Quiet Hint** (`#888888`): metadata, labels, and secondary explanation.
- **Hairline Divider** (`#00000014`): understated separation between operational items.

### Status

- **Resolved Green** (`#2e7d32`): successful or healthy state, always paired with text.
- **Attention Amber** (`#f0a500`): queued or in-progress state, always paired with text.
- **Stop Red** (`#c62828`): failed or unsafe state, always paired with an actionable reason.

**The One-Action Rule.** Clear Action Blue is reserved for the single next useful action and the current selection. It must not become decoration.

## Typography

**Display Font:** System sans stack, no display face.
**Body Font:** `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`.
**Label Font:** The same system sans stack.

**Character:** Familiar, legible, and native to the owner’s phone. Typography carries hierarchy through weight and compact scale, never through theatrical styling.

### Hierarchy

- **Title** (600, 13px, 1.5, 0.05em): uppercase card headings and terse operational grouping.
- **Body** (400, 14px, 1.5): readable actions, explanations, and form values.
- **Metadata** (400, 11px, 1.5): timestamps, provider data, and diagnostic detail.
- **Label** (400, 12px, 1.5): field purpose directly above its control.

**The No-Performance Rule.** Never add display fonts, gradient text, or oversized dashboard numerals. This is a control surface, not an AI showcase.

## Elevation

HelloMate uses tonal layering rather than shadows: Paper Canvas holds the page, Soft Utility Surface groups related controls, and a 1px Hairline Divider separates repeated rows. Elevation appears through state and grouping, not floating decorative cards.

**The Flat-by-Default Rule.** Cards stay flat at rest. Borders and tonal contrast explain structure; shadows are prohibited unless a transient system-level overlay genuinely needs separation.

## Components

### Buttons

- **Shape:** gently curved field radius (8px), full-width for primary mobile actions and auto-width only for compact row actions.
- **Primary:** Clear Action Blue with white text, at least 44px practical tap height.
- **Secondary:** neutral surface, Hairline Divider, and Direct Ink. Use for destructive-adjacent actions such as deletion only after confirmation.
- **Focus:** visible Clear Action Blue border. Do not rely on a color change without a focus treatment.

### Cards / Containers

- **Corner Style:** 12px.
- **Background:** Soft Utility Surface.
- **Border:** none by default; inner rows use a Hairline Divider.
- **Internal Padding:** 12px, with 12px between cards.

### Inputs / Fields

- **Style:** full-width Paper Canvas field, 1px Hairline Divider, 8px radius, 9px × 11px padding.
- **Focus:** border shifts to Clear Action Blue.
- **Errors:** show a concise Russian reason adjacent to the field or action. Never dump raw HTML into a dialog.

### Status and Activity Rows

- **Style:** compact row with a text outcome first, then optional metadata.
- **Status:** use Resolved Green, Attention Amber, or Stop Red only alongside words such as “готово”, “выполняется”, or “ошибка”.
- **Privacy:** diagnostics identify provider/model and error class, never raw prompts or private message text.

### Navigation

- **Style:** horizontally scrollable bottom-border navigation with compact icon plus Russian label.
- **Active state:** Clear Action Blue text and bottom border.
- **Mobile treatment:** maintain a predictable tap target and never hide the current section without a text label.

## Do's and Don'ts

### Do:

- **Do** use Telegram theme variables first, with the documented fallbacks only as a safe baseline.
- **Do** put the next useful, safe action before provider or implementation detail.
- **Do** pair every success, warning, and failure color with a concise Russian text label.
- **Do** use inline confirmation for destructive actions such as deleting an eval candidate.
- **Do** keep owner diagnostics compact and free of raw prompts or hidden conversation content.

### Don't:

- **Don't** build a noisy monitoring wall or a generic SaaS metric dashboard.
- **Don't** use decorative AI effects, gradient text, glassmorphism, or colored side-stripe cards.
- **Don't** make private contacts feel surveilled through excessive diagnostics or copied conversation content.
- **Don't** hide important state behind unexplained jargon or color-only indicators.
- **Don't** use a modal as the first response to ordinary configuration; reserve confirmation for destructive actions.
