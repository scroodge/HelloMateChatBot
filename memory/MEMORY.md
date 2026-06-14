# HelloMate Project Memory

- [Основной язык — русский](feedback_russian_primary_language.md) — дефолт ru, шаблоны и UI на русском первично
- **Telegram Business** — основной режим: бот подключён к аккаунту владельца, отвечает в личных чатах с контактами от его имени (`app/handlers/business.py`)
- [Business reply mode](project_business_reply_mode.md) — per-contact auto/suggest/off; global default = suggest; DM owner with draft + CopyTextButton
- **Deployment** — single-server Docker (SQLite, no Postgres), Mini App behind a reverse proxy with TLS. Infra specifics live in private agent memory, not this repo.
- **Reply debounce** — `REPLY_DEBOUNCE_SECONDS` (дефолт 5): ждёт паузу, склеивает короткие сообщения контакта, один ответ
- Документация: `README.md` (setup + env), `docs/PROJECT_ANALYSIS.md` (архитектура и gaps)
