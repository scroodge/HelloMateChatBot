"""Persistence for per-user greeting rules."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Protocol

from app.models.greeting_rule import GreetingRule

if TYPE_CHECKING:
    from app.database.sqlite import SQLiteDatabase


class GreetingRulesRepository(Protocol):
    """Persistence contract for greeting rules."""

    def list_rules(self, user_id: int) -> list[GreetingRule]: ...

    def list_enabled_rules(self) -> list[GreetingRule]: ...

    def get_rule(self, rule_id: int) -> GreetingRule | None: ...

    def add_rule(self, rule: GreetingRule) -> GreetingRule: ...

    def delete_rule(self, rule_id: int) -> None: ...

    def update_rule(self, rule: GreetingRule) -> GreetingRule: ...

    def count_rules(self, user_id: int) -> int: ...


def _row_to_rule(row) -> GreetingRule:
    last_sent = row["last_sent_date"]
    return GreetingRule(
        id=int(row["id"]),
        user_id=int(row["user_id"]),
        text=row["text"],
        greeting_interval=row["greeting_interval"],
        greeting_hour=int(row["greeting_hour"]),
        greeting_weekday=int(row["greeting_weekday"]),
        greeting_day=int(row["greeting_day"]),
        enabled=bool(row["enabled"]),
        sort_order=int(row["sort_order"]),
        last_sent_date=date.fromisoformat(last_sent) if last_sent else None,
    )


class SQLiteGreetingRulesRepository:
    """SQLite implementation of GreetingRulesRepository."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def list_rules(self, user_id: int) -> list[GreetingRule]:
        rows = self._database.connection.execute(
            """
            SELECT id, user_id, text, greeting_interval, greeting_hour,
                   greeting_weekday, greeting_day, enabled, sort_order, last_sent_date
            FROM user_greeting_rules
            WHERE user_id = ?
            ORDER BY sort_order, id
            """,
            (user_id,),
        ).fetchall()
        return [_row_to_rule(row) for row in rows]

    def list_enabled_rules(self) -> list[GreetingRule]:
        rows = self._database.connection.execute(
            """
            SELECT id, user_id, text, greeting_interval, greeting_hour,
                   greeting_weekday, greeting_day, enabled, sort_order, last_sent_date
            FROM user_greeting_rules
            WHERE enabled = 1
            ORDER BY user_id, sort_order, id
            """
        ).fetchall()
        return [_row_to_rule(row) for row in rows]

    def get_rule(self, rule_id: int) -> GreetingRule | None:
        row = self._database.connection.execute(
            """
            SELECT id, user_id, text, greeting_interval, greeting_hour,
                   greeting_weekday, greeting_day, enabled, sort_order, last_sent_date
            FROM user_greeting_rules
            WHERE id = ?
            """,
            (rule_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_rule(row)

    def add_rule(self, rule: GreetingRule) -> GreetingRule:
        with self._database.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO user_greeting_rules (
                    user_id, text, greeting_interval, greeting_hour,
                    greeting_weekday, greeting_day, enabled, sort_order, last_sent_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule.user_id,
                    rule.text,
                    rule.greeting_interval,
                    rule.greeting_hour,
                    rule.greeting_weekday,
                    rule.greeting_day,
                    int(rule.enabled),
                    rule.sort_order,
                    rule.last_sent_date.isoformat() if rule.last_sent_date else None,
                ),
            )
            rule_id = int(cursor.lastrowid)
        created = self.get_rule(rule_id)
        if created is None:
            raise RuntimeError("Failed to load greeting rule after insert.")
        return created

    def delete_rule(self, rule_id: int) -> None:
        with self._database.transaction() as connection:
            connection.execute("DELETE FROM user_greeting_rules WHERE id = ?", (rule_id,))

    def update_rule(self, rule: GreetingRule) -> GreetingRule:
        with self._database.transaction() as connection:
            connection.execute(
                """
                UPDATE user_greeting_rules
                SET text = ?,
                    greeting_interval = ?,
                    greeting_hour = ?,
                    greeting_weekday = ?,
                    greeting_day = ?,
                    enabled = ?,
                    sort_order = ?,
                    last_sent_date = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    rule.text,
                    rule.greeting_interval,
                    rule.greeting_hour,
                    rule.greeting_weekday,
                    rule.greeting_day,
                    int(rule.enabled),
                    rule.sort_order,
                    rule.last_sent_date.isoformat() if rule.last_sent_date else None,
                    rule.id,
                ),
            )
        updated = self.get_rule(rule.id)
        if updated is None:
            raise RuntimeError(f"Greeting rule {rule.id} not found after update.")
        return updated

    def count_rules(self, user_id: int) -> int:
        row = self._database.connection.execute(
            "SELECT COUNT(*) AS count FROM user_greeting_rules WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return int(row["count"]) if row is not None else 0
