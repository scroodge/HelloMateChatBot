"""Persistence for per-user greeting rules."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import delete, func, insert, select, update

from app.database.schema import user_greeting_rules
from app.database.util import now_iso
from app.models.greeting_rule import GreetingRule

if TYPE_CHECKING:
    from app.database.db import Database


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
    return GreetingRule(
        id=int(row.id),
        user_id=int(row.user_id),
        text=row.text,
        greeting_interval=row.greeting_interval,
        greeting_hour=int(row.greeting_hour),
        greeting_weekday=int(row.greeting_weekday),
        greeting_day=int(row.greeting_day),
        enabled=bool(row.enabled),
        sort_order=int(row.sort_order),
        last_sent_date=date.fromisoformat(row.last_sent_date) if row.last_sent_date else None,
    )


class GreetingRulesRepositoryImpl:
    """SQLAlchemy implementation of GreetingRulesRepository."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def list_rules(self, user_id: int) -> list[GreetingRule]:
        with self._db.engine.connect() as connection:
            rows = connection.execute(
                select(user_greeting_rules)
                .where(user_greeting_rules.c.user_id == user_id)
                .order_by(user_greeting_rules.c.sort_order, user_greeting_rules.c.id)
            ).all()
        return [_row_to_rule(row) for row in rows]

    def list_enabled_rules(self) -> list[GreetingRule]:
        with self._db.engine.connect() as connection:
            rows = connection.execute(
                select(user_greeting_rules)
                .where(user_greeting_rules.c.enabled.is_(True))
                .order_by(
                    user_greeting_rules.c.user_id,
                    user_greeting_rules.c.sort_order,
                    user_greeting_rules.c.id,
                )
            ).all()
        return [_row_to_rule(row) for row in rows]

    def get_rule(self, rule_id: int) -> GreetingRule | None:
        with self._db.engine.connect() as connection:
            row = connection.execute(
                select(user_greeting_rules).where(user_greeting_rules.c.id == rule_id)
            ).first()
        return _row_to_rule(row) if row is not None else None

    def add_rule(self, rule: GreetingRule) -> GreetingRule:
        timestamp = now_iso()
        with self._db.engine.begin() as connection:
            result = connection.execute(
                insert(user_greeting_rules).values(
                    user_id=rule.user_id,
                    text=rule.text,
                    greeting_interval=rule.greeting_interval,
                    greeting_hour=rule.greeting_hour,
                    greeting_weekday=rule.greeting_weekday,
                    greeting_day=rule.greeting_day,
                    enabled=rule.enabled,
                    sort_order=rule.sort_order,
                    last_sent_date=(
                        rule.last_sent_date.isoformat() if rule.last_sent_date else None
                    ),
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            rule_id = int(result.inserted_primary_key[0])
        created = self.get_rule(rule_id)
        if created is None:
            raise RuntimeError("Failed to load greeting rule after insert.")
        return created

    def delete_rule(self, rule_id: int) -> None:
        with self._db.engine.begin() as connection:
            connection.execute(
                delete(user_greeting_rules).where(user_greeting_rules.c.id == rule_id)
            )

    def update_rule(self, rule: GreetingRule) -> GreetingRule:
        with self._db.engine.begin() as connection:
            connection.execute(
                update(user_greeting_rules)
                .where(user_greeting_rules.c.id == rule.id)
                .values(
                    text=rule.text,
                    greeting_interval=rule.greeting_interval,
                    greeting_hour=rule.greeting_hour,
                    greeting_weekday=rule.greeting_weekday,
                    greeting_day=rule.greeting_day,
                    enabled=rule.enabled,
                    sort_order=rule.sort_order,
                    last_sent_date=(
                        rule.last_sent_date.isoformat() if rule.last_sent_date else None
                    ),
                    updated_at=now_iso(),
                )
            )
        updated = self.get_rule(rule.id)
        if updated is None:
            raise RuntimeError(f"Greeting rule {rule.id} not found after update.")
        return updated

    def count_rules(self, user_id: int) -> int:
        with self._db.engine.connect() as connection:
            count = connection.execute(
                select(func.count())
                .select_from(user_greeting_rules)
                .where(user_greeting_rules.c.user_id == user_id)
            ).scalar()
        return int(count or 0)
