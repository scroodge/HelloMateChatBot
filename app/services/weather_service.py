"""Weather lookup via Open-Meteo (no API key required)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

_WEATHER_QUERY_PATTERN = re.compile(
    r"(погод|дожд|осадк|градус|температур|зонт|метео|weather|rain|snow|forecast|umbrella|"
    r"солнц|ветер|мороз|жар|прохлад|облач)",
    re.IGNORECASE,
)

_WMO_DESCRIPTIONS_RU = {
    0: "ясно",
    1: "преимущественно ясно",
    2: "переменная облачность",
    3: "пасмурно",
    45: "туман",
    48: "изморозь",
    51: "морось",
    53: "морось",
    55: "сильная морось",
    61: "дождь",
    63: "дождь",
    65: "сильный дождь",
    71: "снег",
    73: "снег",
    75: "сильный снег",
    80: "ливень",
    81: "ливень",
    82: "сильный ливень",
    95: "гроза",
    96: "гроза с градом",
    99: "сильная гроза с градом",
}

_WMO_DESCRIPTIONS_EN = {
    0: "clear",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "rime fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    80: "rain showers",
    81: "rain showers",
    82: "heavy rain showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "heavy thunderstorm with hail",
}


@dataclass(frozen=True, slots=True)
class _CityLocation:
    name: str
    latitude: float
    longitude: float


def is_weather_query(text: str) -> bool:
    """Return True when the message likely asks about weather."""

    return bool(_WEATHER_QUERY_PATTERN.search(text))


class WeatherService:
    """Fetch factual weather data for LLM context injection."""

    def __init__(self, city: str, timezone: ZoneInfo) -> None:
        self.city = city.strip() or "Minsk"
        self.timezone = timezone
        self._location: _CityLocation | None = None

    async def get_context(self, language: str = "ru") -> str | None:
        """Return a compact weather summary for the configured city."""

        try:
            location = await self._resolve_location(language)
            forecast = await self._fetch_forecast(location)
            return self._format_context(location, forecast, language)
        except Exception:
            logger.exception("Failed to fetch weather for %s", self.city)
            return None

    async def _resolve_location(self, language: str) -> _CityLocation:
        if self._location is not None:
            return self._location

        params = {
            "name": self.city,
            "count": 1,
            "language": language,
            "format": "json",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

        results = data.get("results")
        if not isinstance(results, list) or not results:
            raise RuntimeError(f"City not found: {self.city}")

        first = results[0]
        self._location = _CityLocation(
            name=str(first.get("name", self.city)),
            latitude=float(first["latitude"]),
            longitude=float(first["longitude"]),
        )
        return self._location

    async def _fetch_forecast(self, location: _CityLocation) -> dict[str, object]:
        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code",
            "current": "temperature_2m,weather_code,precipitation",
            "timezone": str(self.timezone),
            "forecast_days": 1,
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("Unexpected weather API response.")
        return data

    def _format_context(
        self,
        location: _CityLocation,
        forecast: dict[str, object],
        language: str,
    ) -> str:
        descriptions = _WMO_DESCRIPTIONS_RU if language == "ru" else _WMO_DESCRIPTIONS_EN
        now = datetime.now(tz=self.timezone)
        current = forecast.get("current", {})
        hourly = forecast.get("hourly", {})

        current_temp = current.get("temperature_2m")
        current_code = current.get("weather_code")
        current_condition = descriptions.get(int(current_code), "unknown") if current_code is not None else "unknown"

        rain_slots = self._rain_slots(hourly, now, descriptions)
        if language == "ru":
            header = (
                f"Актуальная погода в {location.name} ({now:%d.%m %H:%M}): "
                f"сейчас {current_temp}°C, {current_condition}."
            )
            if rain_slots:
                return f"{header} Осадки сегодня: {rain_slots}. Используй эти факты в ответе."
            return f"{header} Значимых осадков сегодня не ожидается. Используй эти факты в ответе."

        header = (
            f"Current weather in {location.name} ({now:%d.%m %H:%M}): "
            f"now {current_temp}°C, {current_condition}."
        )
        if rain_slots:
            return f"{header} Precipitation today: {rain_slots}. Use these facts in your reply."
        return f"{header} No significant precipitation expected today. Use these facts in your reply."

    def _rain_slots(
        self,
        hourly: object,
        now: datetime,
        descriptions: dict[int, str],
    ) -> str:
        if not isinstance(hourly, dict):
            return ""

        times = hourly.get("time")
        probs = hourly.get("precipitation_probability")
        amounts = hourly.get("precipitation")
        codes = hourly.get("weather_code")
        if not isinstance(times, list) or not isinstance(probs, list):
            return ""

        slots: list[str] = []
        for index, time_value in enumerate(times):
            if not isinstance(time_value, str):
                continue
            slot_time = datetime.fromisoformat(time_value).replace(tzinfo=self.timezone)
            if slot_time.date() != now.date() or slot_time < now:
                continue

            prob = probs[index] if index < len(probs) else 0
            amount = amounts[index] if isinstance(amounts, list) and index < len(amounts) else 0
            code = codes[index] if isinstance(codes, list) and index < len(codes) else None
            if not prob and not amount:
                continue
            if prob < 30 and (not amount or amount <= 0):
                continue

            condition = descriptions.get(int(code), "") if code is not None else ""
            label = f"{slot_time:%H:%M} — {prob}%"
            if amount and amount > 0:
                label += f", {amount} мм"
            if condition:
                label += f", {condition}"
            slots.append(label)
            if len(slots) >= 4:
                break

        return "; ".join(slots)
