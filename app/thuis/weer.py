"""Het weer voor de pagina Weer en het overzicht: de verwachting van Open-Meteo voor thuis, en wat
die betekent voor je gasverbruik.

Locatie: de plek die je bij Auto & laden als thuis hebt ingesteld, anders THUIS_LAT/THUIS_LON
(standaard De Bilt). Afgerond op twee decimalen (±1 km): preciezer rekent een weermodel niet, en zo
gaat je adres niet naar Open-Meteo.

Gas: uit je eigen verbruik van de laatste acht weken een lijn gas = basis + per_graaddag × graaddagen
(kleinste kwadraten). De basis is warm water en koken, het deel per graaddag de verwarming. Met de
verwachte etmaaltemperatuur geeft dat een schatting per dag. De temperaturen in de historie zijn die
van de verzamelaar (THUIS_LAT/THUIS_LON); dat scheelt hooguit een graad met thuis.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from .config import Config
from .inzicht import dagen_grenzen, prijzen, temperatuur_per_dag, vandaag, verbruik_per_dag
from .inzichten import GRAADDAG_BASIS
from .opslag import Opslag, lees_instellingen, nu, tegelijk

HISTORIE_DAGEN = 56
MIN_DAGEN = 10  # minder dagen met gas en temperatuur: geen schatting


class WeerLive:
    """De verwachting van Open-Meteo per locatie, BEWAAR_S bewaard (het model rekent elk uur opnieuw)."""

    BEWAAR_S = 10 * 60.0

    def __init__(self, bron: Any, klok: Callable[[], float] = time.monotonic) -> None:
        self._bron = bron  # iets met .verwachting(lat, lon), zoals connectors.weer.OpenMeteo
        self._klok = klok
        self._slot = threading.Lock()
        self._bewaard: dict[tuple[float, float], tuple[float, dict[str, Any]]] = {}

    def haal(self, lat: float, lon: float) -> dict[str, Any]:
        with self._slot:
            sleutel = (lat, lon)
            oud = self._bewaard.get(sleutel)
            if oud and self._klok() - oud[0] < self.BEWAAR_S:
                return oud[1]
            v = {**self._bron.verwachting(lat, lon), "opgehaald": nu()}
            self._bewaard = {sleutel: (self._klok(), v)}  # één locatie tegelijk is genoeg
            return v


def locatie(opslag: Opslag, cfg: Config) -> dict[str, Any]:
    thuis = lees_instellingen(opslag, {"auto_thuis": None})["auto_thuis"]
    if thuis and thuis.get("lat") is not None and thuis.get("lon") is not None:
        lat, lon = round(float(thuis["lat"]), 2), round(float(thuis["lon"]), 2)
        return {"lat": lat, "lon": lon, "bron": "thuis", "naam": "thuis"}
    lat, lon = round(cfg.lat, 2), round(cfg.lon, 2)
    naam = "De Bilt" if (lat, lon) == (52.1, 5.18) else "je ingestelde plek"  # standaard: THUIS_LAT/THUIS_LON
    return {"lat": lat, "lon": lon, "bron": "instelling", "naam": naam}


def graaddagen(temp_gem: float | None) -> float | None:
    return None if temp_gem is None else round(max(0.0, GRAADDAG_BASIS - temp_gem), 1)


def gasmodel(opslag: Opslag, dag: date) -> dict[str, Any] | None:
    """basis + per_graaddag × graaddagen uit de laatste HISTORIE_DAGEN volle dagen; None zonder genoeg data."""
    start, eind = dagen_grenzen(dag - timedelta(days=HISTORIE_DAGEN), dag - timedelta(days=1))
    per_dag, temps, gasprijzen = tegelijk(
        opslag,
        lambda: verbruik_per_dag(opslag, start, eind),
        lambda: temperatuur_per_dag(opslag, start, eind),
        lambda: prijzen(opslag, "gas", eind - timedelta(days=14), eind + timedelta(days=1)),
    )
    gas = {r["dag"]: r["hoeveelheid"] or 0.0 for r in per_dag if r["soort"] == "gas"}
    punten = [(GRAADDAG_BASIS - min(GRAADDAG_BASIS, temps[d]), g) for d, g in gas.items() if d in temps]
    if len(punten) < MIN_DAGEN:
        return None
    n = len(punten)
    gx = sum(x for x, _ in punten) / n
    gy = sum(y for _, y in punten) / n
    sxx = sum((x - gx) ** 2 for x, _ in punten)
    if sxx < 1:  # (bijna) geen stookdagen: alleen warm water en koken
        basis, per_gd = gy, 0.0
    else:
        per_gd = sum((x - gx) * (y - gy) for x, y in punten) / sxx
        basis = gy - per_gd * gx
        if basis < 0:  # door de oorsprong: geen negatief basisverbruik
            per_gd, basis = sum(y for _, y in punten) / max(sum(x for x, _ in punten), 1e-9), 0.0
        if per_gd < 0:
            per_gd, basis = 0.0, gy
    prijs = gasprijzen[-1]["allin"] if gasprijzen else None
    return {"basis_m3": round(basis, 3), "per_graaddag_m3": round(per_gd, 3), "dagen": n, "prijs": prijs}


def weer_overzicht(opslag: Opslag, cfg: Config, live: WeerLive, dag: date | None = None) -> dict[str, Any]:
    """De verwachting voor thuis met per dag de graaddagen en het verwachte gasverbruik (zie docs/api.md)."""
    dag = dag or vandaag()
    plek, model = tegelijk(opslag, lambda: locatie(opslag, cfg), lambda: gasmodel(opslag, dag))
    v = live.haal(plek["lat"], plek["lon"])
    dagen = []
    for d in v["dagen"]:
        gd = graaddagen(d.get("temp_gem"))
        gas = (
            None
            if model is None or gd is None
            else round(model["basis_m3"] + model["per_graaddag_m3"] * gd, 2)
        )
        kosten = None if gas is None or model["prijs"] is None else round(gas * model["prijs"], 2)
        dagen.append({**d, "graaddagen": gd, "gas_m3": gas, "gas_kosten": kosten})
    return _iso(
        {
            "locatie": plek,
            "bijgewerkt": v["opgehaald"],
            "nu": v["nu"],
            "kwartieren": v["kwartieren"],
            "uren": v["uren"],
            "dagen": dagen,
            "gas": model,
        }
    )


def _iso(w: Any) -> Any:
    if isinstance(w, dict):
        return {k: _iso(v) for k, v in w.items()}
    if isinstance(w, list):
        return [_iso(v) for v in w]
    return w.isoformat() if isinstance(w, (datetime, date)) else w
