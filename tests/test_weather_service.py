"""Tests for weather service."""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import pytest

from app.services.weather_service import WeatherService, is_weather_query
from zoneinfo import ZoneInfo


def test_is_weather_query_matches_russian_and_english() -> None:
    assert is_weather_query("какая погода в Минске?")
    assert is_weather_query("будет дождь сегодня?")
    assert is_weather_query("what's the weather like?")


def test_is_weather_query_ignores_unrelated_messages() -> None:
    assert not is_weather_query("как дела?")
    assert not is_weather_query("что нового?")


@pytest.mark.asyncio
async def test_weather_service_formats_russian_context(monkeypatch: pytest.MonkeyPatch) -> None:
    timezone = ZoneInfo("Europe/Minsk")
    service = WeatherService("Minsk", timezone)
    now = datetime.now(tz=timezone)
    slot_one = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    slot_two = slot_one + timedelta(hours=3)

    class GeoResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "results": [
                    {
                        "name": "Минск",
                        "latitude": 53.9,
                        "longitude": 27.56667,
                    }
                ]
            }

    class ForecastResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "current": {
                    "temperature_2m": 18.5,
                    "weather_code": 3,
                    "precipitation": 0.0,
                },
                "hourly": {
                    "time": [slot_one.isoformat(timespec="minutes"), slot_two.isoformat(timespec="minutes")],
                    "precipitation_probability": [70, 35],
                    "precipitation": [0.4, 0.0],
                    "weather_code": [61, 3],
                },
            }

    class MockClient:
        async def __aenter__(self) -> MockClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, params: dict[str, object]) -> GeoResponse | ForecastResponse:
            if "geocoding-api" in url:
                return GeoResponse()
            return ForecastResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: MockClient())
    context = await service.get_context("ru")
    assert context is not None
    assert "Минск" in context
    assert "18.5°C" in context
    assert "Осадки сегодня" in context
    assert slot_one.strftime("%H:%M") in context
