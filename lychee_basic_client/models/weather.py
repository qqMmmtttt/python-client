from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class WeatherState:
    active: list[dict[str, Any]] = field(default_factory=list)
    forecast: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: Optional[dict[str, Any]]) -> "WeatherState":
        raw = raw or {}
        active = raw.get("active") or raw.get("current") or []
        forecast = raw.get("forecast") or raw.get("upcoming") or []
        if isinstance(active, dict):
            active = [active]
        if isinstance(forecast, dict):
            forecast = [forecast]
        return cls(active=list(active), forecast=list(forecast), raw=raw)

    def has_active(self, weather_type: str) -> bool:
        expected = weather_type.upper()
        return any(_weather_type(weather) == expected for weather in self.active)

    def route_multiplier(self, route_type: str) -> float:
        route = route_type.upper()
        if route == "WATER" and self.has_active("HEAVY_RAIN"):
            return 1.35
        if route == "MOUNTAIN" and self.has_active("MOUNTAIN_FOG"):
            return 1.10
        return 1.0

    def freshness_multiplier(self) -> float:
        multiplier = 1.0
        if self.has_active("HOT"):
            multiplier *= 1.5
        if self.has_active("HEAVY_RAIN"):
            multiplier *= 1.3
        return multiplier


def _weather_type(weather: dict[str, Any]) -> str:
    value = (
        weather.get("weatherType")
        or weather.get("type")
        or weather.get("name")
        or weather.get("weather")
        or ""
    )
    return str(value).upper()
