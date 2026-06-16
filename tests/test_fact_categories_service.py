"""Tests for custom global fact categories."""

from __future__ import annotations

import pytest

from app.database.db import Database
from app.services.fact_categories_service import FactCategoriesService


def _make_service(tmp_path) -> tuple[FactCategoriesService, Database]:
    db = Database(f"sqlite:///{tmp_path / 'cats.db'}")
    db.open()
    return FactCategoriesService(db.fact_categories), db


def test_add_and_list(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        svc.add_category("pet_name", "Кличка питомца")
        svc.add_category("favorite_movie", "Любимый фильм")
        cats = svc.list_categories()
        assert len(cats) == 2
        assert cats[0]["key"] == "pet_name"
        assert cats[0]["label"] == "Кличка питомца"


def test_list_keys(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        svc.add_category("pet_name", "Питомец")
        keys = svc.list_keys()
        assert "pet_name" in keys


def test_delete(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        svc.add_category("pet_name", "Питомец")
        svc.add_category("car", "Машина")
        svc.delete_category("pet_name")
        cats = svc.list_categories()
        assert len(cats) == 1
        assert cats[0]["key"] == "car"


def test_invalid_key_slug_rejected(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        with pytest.raises(ValueError, match="key must be"):
            svc.add_category("Имя питомца", "Питомец")  # spaces/Cyrillic


def test_key_too_long_rejected(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        with pytest.raises(ValueError, match="key must be"):
            svc.add_category("a" * 31, "Too long key")


def test_empty_label_rejected(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        with pytest.raises(ValueError, match="label is required"):
            svc.add_category("pet", "")


def test_label_too_long_rejected(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        with pytest.raises(ValueError, match="≤ 80"):
            svc.add_category("pet", "x" * 81)


def test_custom_key_passes_set_fact(tmp_path) -> None:
    """ContactFactsService.set_fact should accept custom category keys."""
    from unittest.mock import MagicMock

    from app.services.contact_facts_service import ContactFactsService

    db = Database(f"sqlite:///{tmp_path / 'facts.db'}")
    db.open()
    with db:
        cats_svc = FactCategoriesService(db.fact_categories)
        cats_svc.add_category("pet_name", "Кличка питомца")

        facts_svc = ContactFactsService(
            repository=db.facts,
            memory_service=MagicMock(),
            llm_service=MagicMock(),
            settings_service=MagicMock(),
            refresh_interval=5,
            enabled=True,
            categories_service=cats_svc,
        )
        facts_svc.set_fact(1, "pet_name", "Шарик")
        assert facts_svc.facts_as_dict(1)["pet_name"] == "Шарик"


def test_unknown_key_still_rejected(tmp_path) -> None:
    """Keys not in KNOWN_KEYS and not in custom categories should be rejected."""
    from unittest.mock import MagicMock

    from app.services.contact_facts_service import ContactFactsService

    db = Database(f"sqlite:///{tmp_path / 'facts2.db'}")
    db.open()
    with db:
        cats_svc = FactCategoriesService(db.fact_categories)
        facts_svc = ContactFactsService(
            repository=db.facts,
            memory_service=MagicMock(),
            llm_service=MagicMock(),
            settings_service=MagicMock(),
            refresh_interval=5,
            enabled=True,
            categories_service=cats_svc,
        )
        with pytest.raises(ValueError, match="Unknown fact key"):
            facts_svc.set_fact(1, "totally_unknown_key", "value")


def test_custom_key_in_extraction_prompt(tmp_path) -> None:
    """Custom categories should appear in keys_hint in the extraction prompt."""
    from app.services.contact_facts_service import _build_extraction_messages

    extra_keys = [("pet_name", "Кличка питомца"), ("car_model", "Марка авто")]
    msgs = _build_extraction_messages(
        [{"role": "user", "content": "У меня есть собака Шарик"}],
        {},
        "ru",
        extra_keys=extra_keys,
    )
    system_content = msgs[0]["content"]
    assert "pet_name" in system_content
    assert "Кличка питомца" in system_content
    assert "car_model" in system_content


def test_custom_key_passes_parse_facts_json(tmp_path) -> None:
    """_parse_facts_json should accept custom keys when they're in allowed_keys."""
    import json

    from app.services.contact_facts_service import KNOWN_KEYS, _parse_facts_json

    allowed = frozenset(KNOWN_KEYS | {"pet_name"})
    raw = json.dumps({"name": "Катя", "pet_name": "Шарик", "hacker_key": "evil"})
    result = _parse_facts_json(raw, allowed)
    assert result["name"] == "Катя"
    assert result["pet_name"] == "Шарик"
    assert "hacker_key" not in result
