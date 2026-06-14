"""Tests for Telegram Mini App auth."""

from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import urlencode

from app.api.auth import validate_init_data


def _build_init_data(bot_token: str, user_id: int) -> str:
    payload = {
        "user": json.dumps({"id": user_id, "first_name": "Test"}),
        "auth_date": "1710000000",
    }
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(payload.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    payload["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(payload)


def test_validate_init_data_accepts_valid_payload() -> None:
    bot_token = "123456:ABC"
    init_data = _build_init_data(bot_token, 42)
    parsed = validate_init_data(init_data, bot_token)
    assert parsed is not None
    assert parsed["user_id"] == "42"


def test_validate_init_data_rejects_invalid_hash() -> None:
    parsed = validate_init_data("user=%7B%7D&hash=deadbeef", "123456:ABC")
    assert parsed is None
