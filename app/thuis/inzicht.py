"""Lezen en samenvatten: wat de app per dag en 'nu' toont."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from .config import TZ
from .opslag import Opslag


def dag_grenzen(dag: date) -> tuple[datetime, datetime]:
    """Lokale dag (Europe/Amsterdam) als UTC-interval [start, eind). Klopt ook bij zomertijdwissel."""
    start = datetime.combine(dag, time(0), TZ)
    eind = datetime.combine(dag + timedelta(days=1), time(0), TZ)
    return start.astimezone(UTC), eind.astimezone(UTC)


def prijzen(opslag: Opslag, soort: str, van: datetime, tot: datetime) -> list[dict[str, Any]]:
    return opslag.lees(
        "SELECT van, tot, marktprijs, allin FROM {prijs} WHERE soort = @soort AND van >= @van AND van < @tot "
        "ORDER BY van",
        soort=soort,
        van=van,
        tot=tot,
    )


def verbruik(opslag: Opslag, van: datetime, tot: datetime) -> list[dict[str, Any]]:
    return opslag.lees(
        "SELECT soort, van, tot, hoeveelheid, kosten FROM {verbruik} WHERE van >= @van AND van < @tot ORDER BY van",
        van=van,
        tot=tot,
    )


def lader_metingen(opslag: Opslag, van: datetime, tot: datetime) -> list[dict[str, Any]]:
    return opslag.lees(
        "SELECT tijd, lader_id, totaal_kwh FROM {lader_meting} WHERE tijd >= @van AND tijd < @tot ORDER BY tijd",
        van=van,
        tot=tot,
    )


def laatste(opslag: Opslag, tabel: str) -> dict[str, Any] | None:
    rijen = opslag.lees(f"SELECT * FROM {{{tabel}}} ORDER BY tijd DESC LIMIT 1")
    return rijen[0] if rijen else None


def per_uur(rijen: list[dict[str, Any]], waarde: str, sleutel: str = "van") -> dict[datetime, float]:
    """Kwartierblokken optellen tot uren (UTC-uur als sleutel)."""
    uit: dict[datetime, float] = defaultdict(float)
    for r in rijen:
        uit[r[sleutel].replace(minute=0, second=0, microsecond=0)] += r[waarde] or 0
    return dict(uit)


def laden_per_uur(metingen: list[dict[str, Any]]) -> dict[datetime, float]:
    """kWh per uur uit de meterstand van de lader (verschil tussen opeenvolgende metingen).

    Een verschil wordt toegerekend aan het uur van de latere meting; negatieve sprongen
    (meter vervangen of reset) tellen niet mee.
    """
    uit: dict[datetime, float] = defaultdict(float)
    vorige: dict[str, dict[str, Any]] = {}
    for m in metingen:
        v = vorige.get(m["lader_id"])
        if v is not None and m["totaal_kwh"] is not None and v["totaal_kwh"] is not None:
            delta = m["totaal_kwh"] - v["totaal_kwh"]
            if delta > 0:
                uit[m["tijd"].replace(minute=0, second=0, microsecond=0)] += delta
        vorige[m["lader_id"]] = m
    return dict(uit)


def prijs_op(blokken: list[dict[str, Any]], moment: datetime) -> float | None:
    for b in blokken:
        if b["van"] <= moment < b["tot"]:
            return b["allin"]
    return None


def dagoverzicht(opslag: Opslag, dag: date) -> dict[str, Any]:
    start, eind = dag_grenzen(dag)
    stroomprijs = prijzen(opslag, "stroom", start, eind)
    gasprijs = prijzen(opslag, "gas", start, eind)
    rijen = verbruik(opslag, start, eind)
    # Eén meting vóór de dag erbij, zodat het eerste uur ook een verschil heeft.
    laden = laden_per_uur(lader_metingen(opslag, start - timedelta(hours=1), eind))
    laden = {u: k for u, k in laden.items() if start <= u < eind}

    uren = [start + timedelta(hours=i) for i in range(int((eind - start).total_seconds() // 3600))]
    per_soort = {s: [r for r in rijen if r["soort"] == s] for s in ("stroom", "teruglevering", "gas")}
    hoeveel = {s: per_uur(v, "hoeveelheid") for s, v in per_soort.items()}
    kosten = {s: per_uur(v, "kosten") for s, v in per_soort.items()}

    laadkosten = 0.0
    for uur, kwh in laden.items():
        p = prijs_op(stroomprijs, uur + timedelta(minutes=30))
        laadkosten += kwh * (p or 0)

    def totaal(s: str, d: dict[str, dict[datetime, float]]) -> float:
        return round(sum(d[s].values()), 3)

    return {
        "datum": dag.isoformat(),
        "uren": [u.isoformat() for u in uren],
        "reeksen": {
            "stroom": [round(hoeveel["stroom"].get(u, 0), 3) for u in uren],
            "teruglevering": [round(hoeveel["teruglevering"].get(u, 0), 3) for u in uren],
            "gas": [round(hoeveel["gas"].get(u, 0), 3) for u in uren],
            "laden": [round(laden.get(u, 0), 3) for u in uren],
            # Teruglevering is opbrengst; het teken verschilt per bron, dus altijd als aftrekpost.
            "kosten_stroom": [
                round(kosten["stroom"].get(u, 0) - abs(kosten["teruglevering"].get(u, 0)), 3) for u in uren
            ],
        },
        "prijzen": {
            "stroom": [
                {"van": p["van"].isoformat(), "tot": p["tot"].isoformat(), "prijs": p["allin"]}
                for p in stroomprijs
            ],
            "gas": [
                {"van": p["van"].isoformat(), "tot": p["tot"].isoformat(), "prijs": p["allin"]}
                for p in gasprijs
            ],
        },
        "totalen": {
            "stroom": {
                "hoeveelheid": totaal("stroom", hoeveel),
                "kosten": totaal("stroom", kosten),
                "eenheid": "kWh",
            },
            "teruglevering": {
                "hoeveelheid": totaal("teruglevering", hoeveel),
                "kosten": -abs(totaal("teruglevering", kosten)),
                "eenheid": "kWh",
            },
            "gas": {"hoeveelheid": totaal("gas", hoeveel), "kosten": totaal("gas", kosten), "eenheid": "m³"},
            "laden": {
                "hoeveelheid": round(sum(laden.values()), 3),
                "kosten": round(laadkosten, 2),
                "eenheid": "kWh",
            },
        },
        "compleet": {"verbruik": bool(rijen), "prijzen": bool(stroomprijs)},
    }
