"""Telegram Mini App initData validation."""

from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import parse_qsl


def validate_init_data(init_data: str, bot_token: str) -> dict[str, str] | None:
    """Validate Telegram WebApp initData and return parsed fields."""

    if not init_data or not bot_token:
        return None

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        return None

    user_raw = parsed.get("user")
    if user_raw:
        try:
            user_data = json.loads(user_raw)
            if isinstance(user_data, dict) and "id" in user_data:
                parsed["user_id"] = str(user_data["id"])
        except json.JSONDecodeError:
            return None
    return parsed
