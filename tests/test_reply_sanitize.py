"""Tests for stripping leaked meta-instruction text from model replies."""

from __future__ import annotations

from app.services.reply_service import _sanitize_reply


def test_strips_real_world_leak() -> None:
    leaked = (
        "Олечка моя, как же мне нравится когда ты говоришь что любишь меня! 😍 "
        "Эти выходные были волшебными. Я вот только до дома доберусь, "
        "can you please modify the response to fit the persona and guidelines "
        "provided without including any medical or chemical terms?"
    )
    out = _sanitize_reply(leaked)
    assert "can you please" not in out.lower()
    assert "guidelines" not in out.lower()
    assert out.startswith("Олечка моя")


def test_strips_ai_disclaimer() -> None:
    out = _sanitize_reply("Привет! Как дела? As an AI language model, I cannot...")
    assert "as an ai" not in out.lower()
    assert out == "Привет! Как дела?"


def test_strips_chat_template_tokens() -> None:
    out = _sanitize_reply("Норм, спасибо <|im_end|>")
    assert "<|" not in out
    assert out == "Норм, спасибо"


def test_clean_reply_untouched() -> None:
    clean = "Привет, солнышко! Конечно, давай вечером созвонимся 😊"
    assert _sanitize_reply(clean) == clean


def test_english_reply_untouched() -> None:
    clean = "Sure, let's catch up tonight! I'll call you around 7."
    assert _sanitize_reply(clean) == clean


def test_all_leak_falls_back_to_stripped_original() -> None:
    # If the marker is at the very start, don't return empty — keep original.
    leaked = "as an ai i cannot help"
    out = _sanitize_reply(leaked)
    assert out  # non-empty
