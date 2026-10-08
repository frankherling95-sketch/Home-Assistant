"""Open-Meteo: temperatuur per uur (gratis, geen account).

Terug in de tijd is het een modelanalyse, vooruit een verwachting. Beide komen uit hetzelfde
endpoint; een verwachting wordt in latere rondes vanzelf bijgewerkt.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

URL = "https://api.open-meteo.com/v1/forecast"


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
