CREATE TABLE IF NOT EXISTS user_greetings (
    user_id INTEGER PRIMARY KEY,
    last_greeting_date TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
