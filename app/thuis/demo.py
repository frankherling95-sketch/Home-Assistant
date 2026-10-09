"""Realistische voorbeelddata in een lokale DuckDB, om de app zonder accounts te bekijken.

python -m thuis.demo            # ±400 dagen historie t/m morgen in thuis.duckdb
THUIS_AUTH_UIT=1 uvicorn thuis.api:app

Er zitten seizoenen in: 's winters meer gas en duurdere avonden, 's zomers zonnepanelen,
teruglevering en op zonnige weekenden negatieve prijzen rond het middaguur. De auto rijdt
dagelijks en laadt een paar keer per week in de goedkoopste kwartieren, zoals Slim laden doet.
Morgen is altijd een zonnige dag met negatieve prijzen, zodat de inzichten iets te tonen hebben.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from .config import TZ, Config
from .inzicht import dag_grenzen, dagen_grenzen, vandaag
from .opslag import DuckOpslag, Opslag, maak_opslag, nu, schrijf_instellingen
from .schema import (
    AUTO,
    AUTO_DETAILS,
    AUTO_LAADSESSIE,
    LADER,
    PRIJS,
    RONDE,
    STUURACTIE,
    TABELLEN,
    VERBRUIK,
    WEER,
)

KWARTIER = timedelta(minutes=15)
LAADVERMOGEN = 10.8  # kW, 3 fasen 16 A
ACCU_KWH = 77.4
METING = timedelta(seconds=40)  # de verzamelaar draait net na het kwartier
AUTO_NAAM = "BMW i4 eDrive40"
VIN = "WBY00000000DEMO01"
THUIS = {"lat": 52.1009, "lon": 5.1801}  # De Bilt
KWH_PER_KM = 0.175


def _seizoen(d: date) -> float:
    """−1 half januari (winter) … +1 half juli (zomer)."""
    return -math.cos(2 * math.pi * (d.timetuple().tm_yday - 15) / 365.25)


def _lokaal(d: date, uur: float) -> datetime:
    """Lokaal tijdstip op dag `d` als UTC, afgerond op het kwartier."""
    return (datetime.combine(d, time(0), TZ) + timedelta(minutes=round(uur * 4) * 15)).astimezone(UTC)


def _meter(soort: str, van: datetime, hoeveelheid: float, kosten: float) -> dict[str, Any]:
    return {
        "soort": soort,
        "van": van,
        "tot": van + timedelta(hours=1),
        "hoeveelheid": round(hoeveelheid, 3),
        "kosten": round(kosten, 4),
        "eenheid": "m3" if soort == "gas" else "kWh",
    }


def _dagen(rnd: random.Random, eerste: date, laatste: date) -> dict[date, dict[str, Any]]:
    """Weer en ritten per dag."""
    uit, afwijking = {}, 0.0
    for i in range((laatste - eerste).days + 1):
        d = eerste + timedelta(days=i)
        s = _seizoen(d)
        afwijking = 0.75 * afwijking + rnd.gauss(0, 1.6)  # weer blijft een paar dagen hangen
        weekend = d.weekday() >= 5
        uit[d] = {
            "seizoen": s,
            "temp": 10.5 + 7.5 * s + afwijking,
            "zon": min(1.0, max(0.05, rnd.random() ** 0.8 * (0.8 + 0.2 * s))),
            "weekend": weekend,
            "prijs_afwijking": rnd.gauss(0, 0.012),
            "gasprijs": round(1.30 - 0.06 * s + rnd.gauss(0, 0.015), 4),
            "vertrek": _lokaal(d, 11.0 if weekend else 7.75),
            "terug": _lokaal(d, (15.5 if weekend else 17.75) + rnd.random() * (2 if weekend else 1.5)),
            "rit_pct": rnd.uniform(2, 18) if weekend else rnd.uniform(6, 13),  # ±45 km per dag
            "negatief": False,
        }
    uit[laatste].update(zon=1.0, negatief=True)
    return uit


def _marktprijs(dag: dict[str, Any], u: float, rnd: random.Random) -> float:
    s, zon = dag["seizoen"], dag["zon"]
    zomer = (s + 1) / 2
    prijs = (
        0.085
        - 0.02 * s
        + 0.05 * math.exp(-((u - 19) ** 2) / 5)  # avondpiek
        + 0.025 * math.exp(-((u - 8) ** 2) / 2)  # ochtendpiek
        - 0.025 * math.exp(-((u - 4) ** 2) / 6)  # nacht
        - (0.02 + 0.12 * zon * zomer + (0.08 * zon if dag["weekend"] else 0))
        * math.exp(-((u - 13.5) ** 2) / 5)
        + dag["prijs_afwijking"]
        + rnd.gauss(0, 0.006)
    )
    if dag["negatief"]:
        prijs -= 0.16 * math.exp(-((u - 13) ** 2) / 3)
    return prijs


def _temperatuur(dag: dict[str, Any], u: float) -> float:
    amplitude = 2 + 3 * dag["zon"]
    return dag["temp"] + amplitude * math.sin(2 * math.pi * (u - 9) / 24)  # warmst rond 15:00


def _zon_kw(dag: dict[str, Any], d: date, tijd: datetime) -> float:
    """Opwek van ±4 kWp panelen: daglengte en zonhoogte per seizoen, bewolking per dag."""
    lengte = 12 - 4.4 * math.cos(2 * math.pi * (d.timetuple().tm_yday + 10) / 365.25)
    h = tijd.hour + tijd.minute / 60  # UTC: de zon staat rond 11:40 UTC het hoogst
    x = (h - (11.67 - lengte / 2)) / lengte
    if not 0 < x < 1:
        return 0.0
    piek = 3.6 * (0.45 + 0.55 * (dag["seizoen"] + 1) / 2)
    return piek * math.sin(math.pi * x) ** 1.2 * (0.15 + 0.85 * dag["zon"])


def _huis_kw(dag: dict[str, Any], u: float, rnd: random.Random) -> float:
    kw = 0.25 + rnd.random() * 0.15 + 0.08 * max(0.0, -dag["seizoen"])
    if 7 <= u < 8.5:
        kw += 0.35
    if 17.5 <= u < 21.5:
        kw += 0.8
    elif 21.5 <= u < 23.5:
        kw += 0.15
    if dag["weekend"] and 9 <= u < 17:
        kw += 0.2
    return kw


def _gas_m3(dag: dict[str, Any], uur: int, temp: float, rnd: random.Random) -> float:
    stook = max(0.0, 18 - temp)
    gewicht = 1.6 if 6 <= uur < 9 else 1.3 if 17 <= uur < 22 else 0.35 if uur >= 23 or uur < 5 else 0.9
    gas = 0.012 + 0.017 * stook * gewicht + (0.15 if uur == 7 else 0) + (0.05 if uur == 18 else 0)
    return round(gas * (0.85 + rnd.random() * 0.3), 3)


def vul(opslag: Opslag, rond: date | None = None, dagen: int = 400, seed: int = 7) -> None:
    """Historie van `dagen` dagen vóór `rond` t/m de dag na `rond`."""
    rnd = random.Random(seed)
    rond = rond or vandaag()
    eerste, laatste = rond - timedelta(days=dagen), rond + timedelta(days=1)
    moment = nu()
    verbruik_tot = min(moment, dag_grenzen(rond)[1])
    meting_tot = min(moment, dag_grenzen(laatste)[1])
    info = _dagen(rnd, eerste, laatste)
    start, eind = dagen_grenzen(eerste, laatste)

    kwartieren = []
    t = start
    while t < eind:
        lok = t.astimezone(TZ)
        kwartieren.append((t, lok.date(), lok.hour + lok.minute / 60))
        t += KWARTIER

    # ── prijzen ──
    allin: dict[datetime, float] = {}
    prijs_rijen = []
    for t, d, u in kwartieren:
        markt = _marktprijs(info[d], u, rnd)
        allin[t] = round(markt * 1.21 + 0.0182 + 0.1108, 5)  # btw, inkoopvergoeding, energiebelasting
        prijs_rijen.append(
            {
                "soort": "stroom",
                "van": t,
                "tot": t + KWARTIER,
                "marktprijs": round(markt, 5),
                "allin": allin[t],
            }
        )
    for d, dag in info.items():
        van, tot = dag_grenzen(d)
        prijs_rijen.append(
            {
                "soort": "gas",
                "van": van,
                "tot": tot,
                "marktprijs": round(dag["gasprijs"] - 0.95, 4),
                "allin": dag["gasprijs"],
            }
        )

    # ── auto en lader, per kwartier ──
    laad_kwh: dict[datetime, float] = defaultdict(float)
    lader_rijen, auto_rijen, acties = [], [], []
    accu, totaal, sessie = 62.0, 1830.0, 0.0
    km = 18240.0
    laadbeurten: list[dict[str, Any]] = []
    beurt: dict[str, Any] | None = None
    weg, ingeplugd = False, False
    gekozen: dict[datetime, float] = {}
    auto_vanaf = meting_tot - timedelta(days=35)
    for t, d, _u in kwartieren:
        if t >= meting_tot:
            break
        dag = info[d]
        if not weg and dag["vertrek"] <= t < dag["vertrek"] + KWARTIER:
            weg, ingeplugd = True, False
        if weg and dag["terug"] <= t < dag["terug"] + KWARTIER:
            weg = False
            morgen = info.get(d + timedelta(days=1))
            altijd = d == rond - timedelta(days=1)  # zodat `rond` zeker een laadnacht heeft
            if morgen and (altijd or accu < 50 or (accu < 72 and rnd.random() < 0.2)):
                ingeplugd, sessie = True, 0.0
                deadline = morgen["vertrek"] - timedelta(minutes=45)
                # De afgedwongen nacht laadt tot 75%: dan is er vanavond weer een plan te zien.
                doel = 75 if altijd else 80
                nodig = max((doel - accu) / 100 * ACCU_KWH / 0.9, 12 if altijd else 0)
                kandidaten = sorted((k for k in allin if t <= k < deadline), key=lambda k: allin[k])
                gekozen = {}
                for k in kandidaten:
                    if nodig <= 0:
                        break
                    gekozen[k] = min(LAADVERMOGEN / 4, nodig)
                    nodig -= gekozen[k]
                if gekozen and min(gekozen) > t:
                    acties.append(
                        {"tijd": t + METING, "lader_id": "EH000001", "actie": "pauzeer", "reden": "wachten"}
                    )
                if gekozen:
                    acties.append(
                        {
                            "tijd": min(gekozen) + METING,
                            "lader_id": "EH000001",
                            "actie": "hervat",
                            "reden": "gepland",
                        }
                    )

        laadt = ingeplugd and t in gekozen
        if not ingeplugd:
            status = "niet_verbonden"
        elif laadt:
            status = "laden"
        elif any(k > t for k in gekozen):
            status = "wacht_op_start"  # gepauzeerd door Slim laden
        else:
            status = "klaar"
        lader_rijen.append(
            {
                "tijd": t + METING,
                "lader_id": "EH000001",
                "naam": "Oprit",
                "status": status,
                "vermogen_kw": LAADVERMOGEN if laadt else 0.0,
                "sessie_kwh": round(sessie, 3),
                "totaal_kwh": round(totaal, 3),
            }
        )
        if t >= auto_vanaf:
            nog = [k for k in gekozen if k >= t] if laadt else []
            auto_rijen.append(
                {
                    "tijd": t + METING,
                    "auto_id": VIN,
                    "naam": AUTO_NAAM,
                    "accu_pct": round(accu, 1),
                    "bereik_km": round(accu * 4.6),
                    "ingeplugd": ingeplugd,
                    "laadt": laadt,
                    "bijgewerkt": t + METING - timedelta(minutes=5),
                    "km_stand": round(km, 1),
                    "laadvermogen_kw": LAADVERMOGEN if laadt else 0.0,
                    "laadtijd_min": 15.0 * len(nog) if laadt else None,
                    "kwh_tot_vol": round((100 - accu) / 100 * ACCU_KWH, 1),
                    "doel_pct": 80.0,
                    "capaciteit_kwh": ACCU_KWH,
                }
            )
        if laadt and beurt is None:
            beurt = {"start": t, "start_pct": round(accu), "kwh": 0.0}
        if beurt is not None and not ingeplugd:  # één sessie van inpluggen tot uitpluggen
            laadbeurten.append({**beurt, "eind_pct": round(accu), "km_stand": round(km)})
            beurt = None
        if laadt:
            kwh = gekozen[t]
            laad_kwh[t] = kwh
            totaal += kwh
            sessie += kwh
            if beurt is not None:
                beurt["kwh"] += kwh
                beurt["eind"] = t + KWARTIER  # laatste kwartier waarin geladen werd
            accu = min(100.0, accu + kwh * 0.9 / ACCU_KWH * 100)
        if weg:
            kwartieren_weg = max(1, (dag["terug"] - dag["vertrek"]) / KWARTIER)
            daling = min(accu - 5.0, dag["rit_pct"] / kwartieren_weg)
            accu -= daling
            km += daling / 100 * ACCU_KWH / KWH_PER_KM

    # ── meter (Frank): per uur afname, teruglevering en gas ──
    uren: dict[datetime, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for t, d, u in kwartieren:
        uur = t.replace(minute=0)
        if uur >= verbruik_tot:
            break
        netto = (_huis_kw(info[d], u, rnd) - _zon_kw(info[d], d, t)) / 4 + laad_kwh.get(t, 0)
        r = uren[uur]
        r["afname"] += max(netto, 0)
        r["terug"] += max(-netto, 0)
        r["k_afname"] += max(netto, 0) * allin[t]
        r["k_terug"] += max(-netto, 0) * max(allin[t], 0)
    verbruik_rijen = []
    for uur, r in uren.items():
        lok = uur.astimezone(TZ)
        dag = info[lok.date()]
        temp = _temperatuur(dag, lok.hour + 0.5)
        gas = _gas_m3(dag, lok.hour, temp, rnd)
        verbruik_rijen += [
            _meter("stroom", uur, r["afname"], r["k_afname"]),
            _meter("teruglevering", uur, r["terug"], r["k_terug"]),
            _meter("gas", uur, gas, gas * dag["gasprijs"]),
        ]

    # ── weer: per uur, ook morgen (verwachting) ──
    weer_rijen = []
    for t, d, u in kwartieren:
        if t.minute == 0:
            weer_rijen.append(
                {
                    "van": t,
                    "tot": t + timedelta(hours=1),
                    "temperatuur": round(_temperatuur(info[d], u + 0.5), 1),
                }
            )

    opslag.voeg_toe(PRIJS, prijs_rijen)
    opslag.voeg_toe(VERBRUIK, verbruik_rijen)
    opslag.voeg_toe(LADER, lader_rijen)
    opslag.voeg_toe(AUTO, auto_rijen)
    _auto_extra(opslag, auto_rijen[-1], laadbeurten, meting_tot, rnd)
    opslag.voeg_toe(STUURACTIE, acties)
    opslag.voeg_toe(WEER, weer_rijen)

    # Rondelog van de afgelopen twee uur: alles gelukt, meldingen niet ingesteld.
    laatste_ronde = moment.replace(minute=moment.minute // 15 * 15, second=0, microsecond=0)
    opslag.voeg_toe(
        RONDE,
        [
            {
                "tijd": laatste_ronde - i * KWARTIER,
                "stap": stap,
                "uitslag": uitslag,
                "duur_s": round(rnd.uniform(0.2, 2.5), 2),
            }
            for i in range(8)
            for stap, uitslag in (
                ("prijzen", "ok"),
                ("verbruik", "ok"),
                ("lader", "ok"),
                ("auto", "overgeslagen"),
                ("bmw", "ok"),
                ("weer", "ok"),
                ("sturen", "ok"),
                ("meldingen", "overgeslagen"),
            )
        ],
    )


def _auto_extra(
    opslag: Opslag,
    laatste: dict[str, Any],
    laadbeurten: list[dict[str, Any]],
    tot: datetime,
    rnd: random.Random,
) -> None:
    """Wat een BMW verder doorgeeft (pagina Auto): details, laadhistorie en een thuislocatie."""
    import json

    t = laatste["tijd"]
    bij = (t - timedelta(minutes=7)).isoformat()
    details = {
        "laden": {
            "doel_pct": 80.0,
            "bereik_bij_doel_km": 368.0,
            "capaciteit_kwh": ACCU_KWH,
            "capaciteit_nieuw_kwh": 80.7,
            "gezondheid_pct": 96.0,
            "ac_limiet_a": 16.0,
            "methode": "AC_TYPE2PLUG",
            "fasen": "3-PHASES" if laatste["laadt"] else "NO_CHARGING",
            "voorkeur": "NO_PRESELECTION",
            "laatste_einde": "CHARGING_GOAL_REACHED",
            "laatste_resultaat": "SUCCESS",
            "kabelslot": "CHARGING_CABLE_LOCKED" if laatste["ingeplugd"] else "CHARGING_CABLE_NOT_LOCKED",
            "klep_open": bool(laatste["ingeplugd"]),
            "bijgewerkt": bij,
        },
        "rijden": {
            "km_stand": laatste["km_stand"],
            "verbruik_kwh_100km": 17.4,
            "week_km": 318.0,
            "week_km_lang": 296.0,
            "rit": {
                "eind": (t - timedelta(hours=3, minutes=20)).isoformat(),
                "km_stand": laatste["km_stand"],
                "accu_pct": laatste["accu_pct"],
                "teruggewonnen": 1.8,
            },
            "rijstijl": {"optrekken": 3.8, "anticiperen": 4.4},
            "bijgewerkt": bij,
        },
        "onderhoud": {
            "service_km": 12400.0,
            "apk": "2029-03-31T22:00:00+00:00",
            "services": [
                {"type": "BRAKE_FLUID", "status": "OK", "dateTime": "2027-04-30T00:00:00Z"},
                {"type": "VEHICLE_CHECK", "status": "OK", "dateTime": "2027-10-31T00:00:00Z"},
            ],
            "meldingen": [{"name": "Bandenspanning rechtsachter controleren", "severity": "LOW"}],
            "banden": {
                "linksvoor": {"bar": 2.6, "doel_bar": 2.6},
                "rechtsvoor": {"bar": 2.6, "doel_bar": 2.6},
                "linksachter": {"bar": 2.8, "doel_bar": 2.9},
                "rechtsachter": {"bar": 2.5, "doel_bar": 2.9},
            },
            "accu_12v_pct": 84.0,
            "bijgewerkt": bij,
        },
        "beveiliging": {
            "slot": "SECURED",
            "alarm": "doorsTiltCabin",
            "deuren_open": {
                "linksvoor": False,
                "rechtsvoor": False,
                "linksachter": False,
                "rechtsachter": False,
            },
            "ramen": {
                "linksvoor": "CLOSED",
                "rechtsvoor": "CLOSED",
                "linksachter": "CLOSED",
                "rechtsachter": "CLOSED",
            },
            "kofferbak_open": False,
            "motorkap_open": False,
            "dak": "CLOSED",
            "bijgewerkt": bij,
        },
        "klimaat": {"activiteit": "standby", "bijgewerkt": bij},
        "locatie": {**THUIS, "bijgewerkt": bij},
        "basis": {
            "merk": "BMW",
            "model": "i4 eDrive40",
            "serie": "4",
            "carrosserie": "Gran Coupé",
            "aandrijving": "BEV",
            "bouwdatum": "2024-03",
            "kleurcode": "C4P",
        },
    }
    opslag.voeg_toe(AUTO_DETAILS, [{"tijd": t, "auto_id": VIN, "gegevens": json.dumps(details)}])

    sessies = [
        {
            "start": b["start"],
            "auto_id": VIN,
            "eind": b["eind"],
            "kwh": round(b["kwh"] * 0.92, 1),  # wat in de auto komt
            "start_pct": float(b["start_pct"]),
            "eind_pct": float(b["eind_pct"]),
            "plaats": "De Bilt",
            "publiek": False,
            "km_stand": float(b["km_stand"]),
            **THUIS,
        }
        for b in laadbeurten
        if b["start"] >= tot - timedelta(days=35)
    ]
    for dagen_terug, plaats, kwh in ((4, "Fastned, Utrecht", 38.6), (17, "Ionity, Zevenaar", 44.2)):
        start = tot - timedelta(days=dagen_terug, hours=rnd.uniform(2, 6))
        sessies.append(
            {
                "start": start,
                "auto_id": VIN,
                "eind": start + timedelta(minutes=27),
                "kwh": kwh,
                "start_pct": 18.0,
                "eind_pct": 70.0,
                "plaats": plaats,
                "publiek": True,
                "kosten": round(kwh * 0.59, 2),
                "valuta": "EUR",
                "lat": 52.09,
                "lon": 5.12,
            }
        )
    opslag.voeg_toe(AUTO_LAADSESSIE, sessies)
    schrijf_instellingen(opslag, {"auto_thuis": THUIS})


def main() -> None:
    cfg = Config()
    if cfg.opslag != "duckdb":
        raise SystemExit("Demo-data alleen in een lokale DuckDB, niet in BigQuery.")
    opslag = maak_opslag(cfg)
    assert isinstance(opslag, DuckOpslag)
    for t in TABELLEN:  # opnieuw beginnen: twee keer draaien geeft geen dubbele historie
        opslag.con.execute(f"DROP TABLE IF EXISTS thuis.{t.naam}")
    opslag.maak_tabellen()
    vul(opslag)
    print(f"Demo-data geschreven naar {cfg.duckdb_pad}")


if __name__ == "__main__":
    main()
