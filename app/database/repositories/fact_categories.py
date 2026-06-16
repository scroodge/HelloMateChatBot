"""Repository for global custom fact categories."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, insert, select

from app.database.schema import fact_categories

if TYPE_CHECKING:
    from app.database.db import Database


class FactCategoriesRepository:
    def list_categories(self) -> list[dict[str, object]]:
        raise NotImplementedError

    def add_category(self, key: str, label: str, multi: bool = False) -> None:
        raise NotImplementedError

    def delete_category(self, key: str) -> None:
        raise NotImplementedError


class FactCategoriesRepositoryImpl(FactCategoriesRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    def list_categories(self) -> list[dict[str, object]]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(
                select(fact_categories).order_by(fact_categories.c.created_at.asc())
            ).fetchall()
        return [
            {"key": row.key, "label": row.label, "multi": bool(row.multi)} for row in rows
        ]

    def add_category(self, key: str, label: str, multi: bool = False) -> None:
        now = datetime.now().astimezone().isoformat()
        with self._db.engine.begin() as conn:
            conn.execute(
                insert(fact_categories).values(
                    key=key, label=label, multi=multi, created_at=now
                )
            )

    def delete_category(self, key: str) -> None:
        with self._db.engine.begin() as conn:
            conn.execute(delete(fact_categories).where(fact_categories.c.key == key))
