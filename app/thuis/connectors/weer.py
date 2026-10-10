"""Open-Meteo: temperatuur per uur, en de verwachting voor de pagina Weer (gratis, geen account).

Terug in de tijd is het een modelanalyse, vooruit een verwachting. Beide komen uit hetzelfde
endpoint; een verwachting wordt in latere rondes vanzelf bijgewerkt. Voor Nederland combineert
Open-Meteo de modellen van KNMI, DWD en ECMWF. Gratis voor persoonlijk gebruik (onder 10.000
verzoeken per dag), met bronvermelding (CC BY 4.0): https://open-meteo.com/en/terms.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from ..config import TZ

URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo-naam → naam in Thuis. Wind in km/u, neerslag in mm, straling in W/m², zon in seconden.
NU = {
    "temperature_2m": "temperatuur",
    "apparent_temperature": "gevoel",
    "relative_humidity_2m": "vochtigheid",
    "precipitation": "neerslag",
    "weather_code": "weercode",
    "cloud_cover": "bewolking",
    "wind_speed_10m": "wind",
    "wind_gusts_10m": "windstoten",
    "wind_direction_10m": "windrichting",
    "is_day": "dag",
}
UREN = {
    "temperature_2m": "temperatuur",
    "apparent_temperature": "gevoel",
    "precipitation": "neerslag",
    "precipitation_probability": "neerslagkans",
    "weather_code": "weercode",
    "wind_speed_10m": "wind",
    "wind_gusts_10m": "windstoten",
    "wind_direction_10m": "windrichting",
    "is_day": "dag",
    "shortwave_radiation": "straling",
}
DAGEN = {
    "weather_code": "weercode",
    "temperature_2m_max": "temp_max",
    "temperature_2m_min": "temp_min",
    "temperature_2m_mean": "temp_gem",
    "precipitation_sum": "neerslag",
    "precipitation_probability_max": "neerslagkans",
    "sunrise": "zon_op",
    "sunset": "zon_onder",
    "sunshine_duration": "zon_s",
    "wind_speed_10m_max": "wind",
    "wind_gusts_10m_max": "windstoten",
    "wind_direction_10m_dominant": "windrichting",
    "uv_index_max": "uv",
}
TIJDEN = {"zon_op", "zon_onder"}  # unixtijd → tijdstip


class OpenMeteo:
    def __init__(self, lat: float, lon: float, client: httpx.Client | None = None) -> None:
        self.lat, self.lon = lat, lon
        self.client = client or httpx.Client(timeout=30)

    def temperaturen(self, terug: int = 2, vooruit: int = 2) -> list[dict[str, Any]]:
        """Uurblokken van `terug` dagen geleden t/m `vooruit` dagen (vandaag telt als 1)."""
        r = self.client.get(
            URL,
            params={
                "latitude": self.lat,
                "longitude": self.lon,
                "hourly": "temperature_2m",
                "past_days": terug,
                "forecast_days": vooruit,
                "timeformat": "unixtime",  # geen gedoe met tijdzones
            },
        )
        r.raise_for_status()
        uur = r.json().get("hourly") or {}
        rijen = []
        for t, temp in zip(uur.get("time") or [], uur.get("temperature_2m") or [], strict=False):
            if temp is None:
                continue
            van = datetime.fromtimestamp(t, UTC)
            rijen.append({"van": van, "tot": van + timedelta(hours=1), "temperatuur": round(float(temp), 1)})
        return rijen

    def verwachting(self, lat: float, lon: float, uren: int = 48, dagen: int = 7) -> dict[str, Any]:
        """Het weer nu, neerslag per kwartier (3 uur), per uur (`uren`) en per dag (`dagen`, vanaf vandaag).

        Dagen lopen van middernacht tot middernacht in Nederland. Tijden als datetime in UTC.
        """
        r = self.client.get(
            URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "timezone": "Europe/Amsterdam",  # voor de dagen; tijden blijven unixtijd
                "timeformat": "unixtime",
                "current": ",".join(NU),
                "minutely_15": "precipitation",
                "forecast_minutely_15": 12,
                "hourly": ",".join(UREN),
                "forecast_hours": uren,
                "daily": ",".join(DAGEN),
                "forecast_days": dagen,
            },
        )
        r.raise_for_status()
        data = r.json()
        nu = data.get("current") or {}
        kwartier = data.get("minutely_15") or {}
        return {
            "nu": {"tijd": _tijd(nu.get("time")), **{naar: nu.get(van) for van, naar in NU.items()}},
            "kwartieren": [
                {"tijd": _tijd(t), "neerslag": n}
                for t, n in zip(kwartier.get("time") or [], kwartier.get("precipitation") or [], strict=False)
            ],
            "uren": _reeks(data.get("hourly") or {}, UREN, "tijd"),
            "dagen": [
                {**d, "datum": datetime.fromtimestamp(d["datum"], UTC).astimezone(TZ).date()}
                for d in _reeks(data.get("daily") or {}, DAGEN, "datum", ruw=True)
            ],
        }


def _tijd(t: Any) -> datetime | None:
    return datetime.fromtimestamp(t, UTC) if isinstance(t, (int, float)) else None


def _reeks(
    blok: dict[str, Any], namen: dict[str, str], tijdnaam: str, ruw: bool = False
) -> list[dict[str, Any]]:
    """Kolommen van Open-Meteo ({"time": [...], "temperature_2m": [...]}) → een rij per tijdstip."""
    uit = []
    for i, t in enumerate(blok.get("time") or []):
        rij: dict[str, Any] = {tijdnaam: t if ruw else _tijd(t)}
        for van, naar in namen.items():
            waarden = blok.get(van) or []
            w = waarden[i] if i < len(waarden) else None
            rij[naar] = _tijd(w) if naar in TIJDEN else w
        uit.append(rij)
    return uit
