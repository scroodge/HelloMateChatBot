ALTER TABLE user_settings ADD COLUMN greeting_interval TEXT NOT NULL DEFAULT 'daily';
ALTER TABLE user_settings ADD COLUMN greeting_weekday INTEGER NOT NULL DEFAULT 0;
ALTER TABLE user_settings ADD COLUMN greeting_day INTEGER NOT NULL DEFAULT 1;
