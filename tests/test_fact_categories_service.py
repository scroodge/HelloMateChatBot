"""Tests for custom global fact categories."""

from __future__ import annotations

import pytest

from app.database.db import Database
from app.services.fact_categories_service import FactCategoriesService, _slugify


def _make_service(tmp_path) -> tuple[FactCategoriesService, Database]:
    db = Database(f"sqlite:///{tmp_path / 'cats.db'}")
    db.open()
    return FactCategoriesService(db.fact_categories), db


# ── Slug generation ────────────────────────────────────────────────────────────


def test_slugify_cyrillic() -> None:
    assert _slugify("Любимая еда") == "lyubimaya_eda"
    assert _slugify("Любит") == "lyubit"


def test_slugify_ascii_and_mixed() -> None:
    assert _slugify("Pet Name 2") == "pet_name_2"
    assert _slugify("  Hello,  World!  ") == "hello_world"


def test_slugify_empty_for_symbols_only() -> None:
    assert _slugify("🎉🎉") == ""


# ── add / list / delete ────────────────────────────────────────────────────────


def test_add_derives_key_from_label(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        key = svc.add_category("Любимая еда")
        assert key == "lyubimaya_eda"
        cats = svc.list_categories()
        assert len(cats) == 1
        assert cats[0]["key"] == "lyubimaya_eda"
        assert cats[0]["label"] == "Любимая еда"
        assert cats[0]["multi"] is False


def test_add_multi_flag(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        svc.add_category("Увлечения", multi=True)
        cats = svc.list_categories()
        assert cats[0]["multi"] is True


def test_duplicate_label_gets_unique_key(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        k1 = svc.add_category("Любит")
        k2 = svc.add_category("Любит")
        assert k1 == "lyubit"
        assert k2 == "lyubit_2"
        assert len(svc.list_categories()) == 2


def test_symbol_only_label_falls_back(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        key = svc.add_category("🎉")
        assert key.startswith("cat_")
        assert svc.list_categories()[0]["label"] == "🎉"


def test_list_keys(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        svc.add_category("Питомец")
        assert "pitomets" in svc.list_keys()


def test_delete(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        k1 = svc.add_category("Питомец")
        svc.add_category("Машина")
        svc.delete_category(k1)
        cats = svc.list_categories()
        assert len(cats) == 1
        assert cats[0]["label"] == "Машина"


def test_empty_label_rejected(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        with pytest.raises(ValueError, match="название категории"):
            svc.add_category("   ")


def test_label_too_long_rejected(tmp_path) -> None:
    svc, db = _make_service(tmp_path)
    with db:
        with pytest.raises(ValueError, match="≤ 80"):
            svc.add_category("x" * 81)


def test_explicit_bad_key_rejected(tmp_path) -> None:
    """An explicitly-passed non-slug key is still rejected."""
    svc, db = _make_service(tmp_path)
    with db:
        with pytest.raises(ValueError, match="латинских"):
            svc.add_category("Питомец", key="Имя питомца")


# ── Integration with ContactFactsService ───────────────────────────────────────


def test_custom_key_passes_set_fact(tmp_path) -> None:
    """ContactFactsService.set_fact should accept auto-derived custom keys."""
    from unittest.mock import MagicMock

    from app.services.contact_facts_service import ContactFactsService

    db = Database(f"sqlite:///{tmp_path / 'facts.db'}")
    db.open()
    with db:
        cats_svc = FactCategoriesService(db.fact_categories)
        key = cats_svc.add_category("Кличка питомца")

        facts_svc = ContactFactsService(
            repository=db.facts,
            memory_service=MagicMock(),
            llm_service=MagicMock(),
            settings_service=MagicMock(),
            refresh_interval=5,
            enabled=True,
            categories_service=cats_svc,
        )
        facts_svc.set_fact(1, key, "Шарик")
        assert facts_svc.facts_as_dict(1)[key] == "Шарик"


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
