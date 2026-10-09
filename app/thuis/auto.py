"""De pagina Auto: alles wat de auto doorgeeft, plus kilometers, accu en laden over de laatste weken.

Vier queries per keer (BigQuery rekent minimaal 10 MB per tabel per query): metingen van de
laatste 31 dagen, de nieuwste details, de laadhistorie van 90 dagen en de instellingen.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Any

from .inzicht import lokaal
from .opslag import Opslag, lees_instellingen, nu, schrijf_instellingen, tegelijk

THUIS_STRAAL_KM = 0.3  # binnen deze afstand van "thuis" staat de auto thuis


def afstand_km(a: dict[str, float], b: dict[str, float]) -> float:
    """Afstand over het aardoppervlak (haversine)."""
    la1, lo1, la2, lo2 = map(radians, (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * asin(sqrt(h))


def _iso(v: Any) -> Any:
    return v.isoformat() if hasattr(v, "isoformat") else v


def km_per_dag(rijen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gereden km per lokale dag: kilometerstand aan het eind van de dag min die van de dag ervoor."""
    eind: dict[Any, float] = {}
    for r in rijen:
        if r.get("km_stand") is not None:
            eind[lokaal(r["tijd"])] = float(r["km_stand"])  # rijen staan op tijd: de laatste blijft
    dagen = sorted(eind)
    return [
        {"dag": d.isoformat(), "km": round(max(eind[d] - eind[vorige], 0.0), 1)}
        for vorige, d in zip(dagen, dagen[1:], strict=False)
    ]


def auto_overzicht(opslag: Opslag, moment: datetime | None = None) -> dict[str, Any]:
    moment = moment or nu()
    rijen = opslag.lees(
        "SELECT * FROM {auto_meting} WHERE tijd >= @van AND tijd <= @tot ORDER BY tijd",
        van=moment - timedelta(days=31),
        tot=moment,
    )
    if not rijen:
        return {"auto": None}
    auto = rijen[-1]
    rijen = [r for r in rijen if r["auto_id"] == auto["auto_id"]]  # bij twee auto's: de laatste

    # Details, thuislocatie en laadhistorie hangen niet van elkaar af: tegelijk.
    d, instellingen, laadhistorie = tegelijk(
        opslag,
        lambda: opslag.lees(
            "SELECT tijd, gegevens FROM {auto_details} WHERE tijd >= @van AND tijd <= @tot AND auto_id = @id "
            "ORDER BY tijd DESC LIMIT 1",
            van=moment - timedelta(days=30),
            tot=moment,
            id=auto["auto_id"],
        ),
        lambda: lees_instellingen(opslag, {"auto_thuis": None}),
        lambda: opslag.lees(
            "SELECT * FROM {auto_laadsessie} WHERE start >= @van AND auto_id = @id ORDER BY start DESC",
            van=moment - timedelta(days=90),
            id=auto["auto_id"],
        ),
    )
    details = json.loads(d[0]["gegevens"]) if d else None
    thuis = instellingen["auto_thuis"]

    locatie = (details or {}).get("locatie")
    if locatie and thuis:
        locatie["afstand_km"] = round(afstand_km(locatie, thuis), 1)
        locatie["thuis"] = locatie["afstand_km"] <= THUIS_STRAAL_KM

    sessies = []
    for s in laadhistorie:
        s = {k: _iso(v) for k, v in s.items() if k not in ("opgehaald", "auto_id")}
        if thuis and s.get("lat") is not None and s.get("lon") is not None:
            s["thuis"] = afstand_km(s, thuis) <= THUIS_STRAAL_KM
        s.pop("lat", None), s.pop("lon", None)  # de pagina toont de plaats, niet de coördinaten
        sessies.append(s)

    per_dag = km_per_dag(rijen)
    week = (lokaal(moment) - timedelta(days=6)).isoformat()
    maand_terug = (moment - timedelta(days=30)).isoformat()
    recent = [s for s in sessies if s["start"] >= maand_terug and s.get("kwh") is not None]
    return {
        "auto": {k: _iso(v) for k, v in auto.items() if k != "opgehaald"},
        "details": details,
        "details_tijd": _iso(d[0]["tijd"]) if d else None,
        "thuis": thuis,
        "accu": [
            {"tijd": _iso(r["tijd"]), "pct": r["accu_pct"], "laadt": bool(r["laadt"])}
            for r in rijen
            if r["tijd"] >= moment - timedelta(days=7) and r["accu_pct"] is not None
        ],
        "km_per_dag": per_dag,
        "km": {
            "zeven_dagen": round(sum(x["km"] for x in per_dag if x["dag"] >= week), 1) if per_dag else None,
            "dertig_dagen": round(sum(x["km"] for x in per_dag), 1) if per_dag else None,
        },
        "laadsessies": sessies,
        "laden_30_dagen": {
            "sessies": len(recent),
            "kwh": round(sum(s["kwh"] for s in recent), 1),
            "kwh_onderweg": round(sum(s["kwh"] for s in recent if s.get("publiek")), 1),
        },
    }


def zet_thuis(opslag: Opslag) -> bool:
    """De huidige plek van de auto onthouden als thuis. False: de auto gaf geen locatie door."""
    d = opslag.lees(
        "SELECT gegevens FROM {auto_details} WHERE tijd >= @van ORDER BY tijd DESC LIMIT 1",
        van=nu() - timedelta(days=30),
    )
    locatie = json.loads(d[0]["gegevens"]).get("locatie") if d else None
    if not locatie:
        return False
    schrijf_instellingen(opslag, {"auto_thuis": {"lat": locatie["lat"], "lon": locatie["lon"]}})
    return True
