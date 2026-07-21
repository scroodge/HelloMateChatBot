"""Tests for live LLM processing status."""

from app.services.processing_status_service import ProcessingStatusService


def test_status_lifecycle_and_stale_token_is_ignored() -> None:
    service = ProcessingStatusService()
    first = service.begin(42, "Привет")
    assert service.get(42).status == "queued"

    assert service.set_generating(42, first)
    assert service.get(42).status == "generating"

    second = service.begin(42, "Новое сообщение")
    assert not service.set_failed(42, first, "старый запрос")
    assert service.get(42).status == "queued"

    assert service.set_failed(42, second, "LLM недоступна")
    assert service.get(42).error == "LLM недоступна"
    service.clear(42, first)
    assert service.get(42) is not None
    service.clear(42, second)
    assert service.get(42) is None


def test_status_is_thread_safe_snapshot() -> None:
    service = ProcessingStatusService()
    service.begin(1, "one")
    service.begin(2, "two")
    assert {item.user_id for item in service.list()} == {1, 2}
