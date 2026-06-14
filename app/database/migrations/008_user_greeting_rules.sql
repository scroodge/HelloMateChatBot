CREATE TABLE IF NOT EXISTS user_greeting_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    greeting_interval TEXT NOT NULL DEFAULT 'daily',
    greeting_hour INTEGER NOT NULL DEFAULT 9,
    greeting_weekday INTEGER NOT NULL DEFAULT 0,
    greeting_day INTEGER NOT NULL DEFAULT 1,
    enabled INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    last_sent_date TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_greeting_rules_user_id
    ON user_greeting_rules(user_id);
