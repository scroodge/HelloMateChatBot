"""Persistence for immutable, owner-only model decision snapshots."""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import insert, select

from app.database.schema import model_decision_reports
from app.models.model_decision_report import ModelDecisionReport


class ModelDecisionReportsRepositoryImpl:
    def __init__(self, db: object) -> None:
        self._db = db

    def create(self, criteria_version: str, report: dict[str, object]) -> ModelDecisionReport:
        created_at = datetime.now().astimezone().isoformat()
        with self._db.engine.begin() as conn:
            result = conn.execute(
                insert(model_decision_reports).values(
                    criteria_version=criteria_version,
                    report=json.dumps(report, ensure_ascii=False),
                    created_at=created_at,
                )
            )
        created = self.get(int(result.inserted_primary_key[0]))
        assert created is not None
        return created

    def get(self, report_id: int) -> ModelDecisionReport | None:
        with self._db.engine.connect() as conn:
            row = conn.execute(
                select(model_decision_reports).where(model_decision_reports.c.id == report_id)
            ).first()
        return self._from_row(row) if row else None

    def recent(self, *, limit: int = 10) -> list[ModelDecisionReport]:
        with self._db.engine.connect() as conn:
            rows = conn.execute(
                select(model_decision_reports)
                .order_by(model_decision_reports.c.id.desc())
                .limit(max(1, min(limit, 50)))
            ).all()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: object) -> ModelDecisionReport:
        return ModelDecisionReport(
            id=int(row.id),
            criteria_version=str(row.criteria_version),
            report=json.loads(str(row.report)),
            created_at=datetime.fromisoformat(str(row.created_at)),
        )
