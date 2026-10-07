"""Realistische voorbeelddata in een lokale DuckDB, om de app zonder accounts te bekijken.

python -m thuis.demo            # vult thuis.duckdb met gisteren t/m morgen
THUIS_AUTH_UIT=1 uvicorn thuis.api:app
"""

from __future__ import annotations

import math
import random
from datetime import UTC, date, datetime, time, timedelta

from .config import TZ, Config
from .inzicht import dag_grenzen
from .opslag import Opslag, maak_opslag, nu
from .schema import AUTO, LADER, PRIJS, VERBRUIK


def _prijs(t: datetime) -> float:
    """Dagcurve: goedkoop 's nachts en rond het middaguur (zon), duur in de avondpiek."""
    u = t.astimezone(TZ).hour + t.astimezone(TZ).minute / 60
    markt = 0.09 + 0.05 * math.cos((u - 19) / 24 * 2 * math.pi) - 0.06 * math.exp(-((u - 13.5) ** 2) / 6)
    return round(markt * 1.21 + 0.02 + 0.1108, 4)  # btw, inkoopvergoeding, energiebelasting


def vul(opslag: Opslag, rond: date | None = None, seed: int = 7) -> None:
    rnd = random.Random(seed)
    rond = rond or nu().astimezone(TZ).date()
    prijzen, verbruik = [], []
    for d in (-1, 0, 1):
        start, eind = dag_grenzen(rond + timedelta(days=d))
        t = start
        while t < eind:
            p = _prijs(t)
            prijzen.append(
                {
                    "soort": "stroom",
                    "van": t,
                    "tot": t + timedelta(minutes=15),
                    "marktprijs": p - 0.15,
                    "allin": p,
                }
            )
            t += timedelta(minutes=15)
        prijzen.append({"soort": "gas", "van": start, "tot": eind, "marktprijs": 0.35, "allin": 1.32})
        if d == 1:
            continue  # verbruik van morgen bestaat nog niet
        for h in range(int((eind - start).total_seconds() // 3600)):
            van = start + timedelta(hours=h)
            if van > nu():
                break
            u = van.astimezone(TZ).hour
            zon = max(0.0, math.sin((u - 7) / 12 * math.pi)) * (1.6 + rnd.random())
            basis = 0.25 + (0.6 if 17 <= u <= 21 else 0) + rnd.random() * 0.2
            afname, terug = max(0.0, basis - zon), max(0.0, zon - basis)
            if d == 0 and 2 <= u < 5:
                afname += 10.8  # de auto laadt: zit in de netafname, net als bij een echte meter
            p = _prijs(van + timedelta(minutes=30))
            gas = round((0.45 if u in (6, 7, 18, 19, 20) else 0.08) * (0.8 + rnd.random() * 0.4), 3)
            verbruik += [
                {
                    "soort": "stroom",
                    "van": van,
                    "tot": van + timedelta(hours=1),
                    "hoeveelheid": round(afname, 3),
                    "kosten": round(afname * p, 4),
                    "eenheid": "kWh",
                },
                {
                    "soort": "teruglevering",
                    "van": van,
                    "tot": van + timedelta(hours=1),
                    "hoeveelheid": round(terug, 3),
                    "kosten": round(terug * (p - 0.13), 4),
                    "eenheid": "kWh",
                },
                {
                    "soort": "gas",
                    "van": van,
                    "tot": van + timedelta(hours=1),
                    "hoeveelheid": gas,
                    "kosten": round(gas * 1.32, 4),
                    "eenheid": "m3",
                },
            ]
    opslag.voeg_toe(PRIJS, prijzen)
    opslag.voeg_toe(VERBRUIK, verbruik)

    # Lader: gisteravond ingeplugd, vannacht 02:00–05:00 geladen; elke 15 min een meting.
    lader, auto = [], []
    totaal, accu = 4210.0, 38.0
    start = datetime.combine(rond - timedelta(days=1), time(18), TZ).astimezone(UTC)
    t = start
    while t <= nu():
        lokaal = t.astimezone(TZ)
        nacht = lokaal.date() == rond and 2 <= lokaal.hour < 5
        thuis = t < datetime.combine(rond, time(7, 45), TZ) or lokaal.hour >= 18
        kw = 10.8 if nacht else 0.0
        totaal += kw / 4
        accu = min(100.0, accu + kw / 4 / 77.4 * 100 * 0.9) if nacht else accu - (0.4 if not thuis else 0)
        status = ("laden" if nacht else "wacht_op_start") if thuis else "niet_verbonden"
        lader.append(
            {
                "tijd": t,
                "lader_id": "EH000001",
                "naam": "Oprit",
                "status": status,
                "vermogen_kw": kw,
                "sessie_kwh": round(totaal - 4210.0, 2),
                "totaal_kwh": round(totaal, 2),
            }
        )
        auto.append(
            {
                "tijd": t,
                "auto_id": "demo",
                "naam": "EV6",
                "accu_pct": round(accu, 1),
                "bereik_km": round(accu * 4.6),
                "ingeplugd": thuis,
                "laadt": nacht,
                "bijgewerkt": t,
            }
        )
        t += timedelta(minutes=15)
    opslag.voeg_toe(LADER, lader)
    opslag.voeg_toe(AUTO, auto)


def main() -> None:
    cfg = Config()
    if cfg.opslag != "duckdb":
        raise SystemExit("Demo-data alleen in een lokale DuckDB, niet in BigQuery.")
    opslag = maak_opslag(cfg)
    opslag.maak_tabellen()
    vul(opslag)
    print(f"Demo-data geschreven naar {cfg.duckdb_pad}")


if __name__ == "__main__":
    main()
