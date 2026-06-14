---
name: feedback_russian_primary_language
description: Основной язык бота — русский; все шаблоны, дефолты и UI-тексты должны быть на русском
metadata:
  type: feedback
---

Основной язык бота — русский. DEFAULT_LANGUAGE=ru уже установлен в конфиге.

**Why:** Владелец бота и его контакты общаются по-русски. Английский — вторичный язык (поддерживается, но не дефолтный).

**How to apply:**
- Шаблоны персон (`personas.json`) — первичные тексты на русском (`system_template_ru`), английские как fallback
- Дефолтные значения в сервисах (тон, тип отношений, подсказки) — на русском
- `resolve()` и `assemble_from_structured()` — дефолт `language="ru"`
- UI Mini App (web/index.html) — на русском
- Любые новые i18n ключи — сначала `ru`, потом `en`
