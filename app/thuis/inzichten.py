"""Inzichten voor de overzichtspagina: korte, uitgerekende feiten met een toon en een icoon.

Elk inzicht staat los; zonder data valt het weg in plaats van een nul te tonen.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from .config import TZ
from .inzicht import (
    MAANDEN,
    dag_grenzen,
    dagcijfers,
    dagen_grenzen,
    geladen,
    kosten_van,
    laadkosten,
    lokaal,
    prijzen,
    temperatuur_per_dag,
)
from .laden import STANDAARD
from .opslag import Opslag, lees_instellingen, nu
from .sessies import laadsessies

GRAADDAG_BASIS = 18.0  # °C; graaddagen = max(0, 18 − etmaalgemiddelde)


def euro(v: float, decimalen: int = 2) -> str:
    tekst = f"{abs(v):,.{decimalen}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"€ {'-' if v < 0 else ''}{tekst}"


def getal(v: float, decimalen: int = 1) -> str:
    return f"{v:.{decimalen}f}".replace(".", ",")


def procent(v: float) -> str:
    return f"{'+' if v > 0 else '−' if v < 0 else ''}{abs(v) * 100:.0f}%"


def klok(t: datetime) -> str:
    return t.astimezone(TZ).strftime("%H:%M")


def _toon(verschil: float, beter_als_lager: bool = True) -> str:
    v = verschil if beter_als_lager else -verschil
    return "goed" if v <= -0.05 else "let_op" if v >= 0.10 else "neutraal"


def _inzicht(id_: str, titel: str, waarde: str, toelichting: str, toon: str, icoon: str) -> dict[str, str]:
    return {
        "id": id_,
        "titel": titel,
        "waarde": waarde,
        "toelichting": toelichting,
        "toon": toon,
        "icoon": icoon,
    }


def _dagnaam(dag: date, ref: date) -> str:
    if dag == ref:
        return "vandaag"
    if dag == ref + timedelta(days=1):
        return "morgen"
    return f"{dag.day} {MAANDEN[dag.month - 1]}"


def aaneengesloten(blokken: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Op elkaar aansluitende prijsblokken groeperen."""
    groepen: list[list[dict[str, Any]]] = []
    for b in sorted(blokken, key=lambda b: b["van"]):
        if groepen and groepen[-1][-1]["tot"] == b["van"]:
            groepen[-1].append(b)
        else:
            groepen.append([b])
    return groepen


def goedkoopste_venster(
    blokken: list[dict[str, Any]], uren: float = 1
) -> tuple[datetime, datetime, float] | None:
    """Het goedkoopste aaneengesloten venster van `uren` lang: (van, tot, gemiddelde prijs)."""
    beste = None
    duur = timedelta(hours=uren)
    for groep in aaneengesloten(blokken):
        for i, b in enumerate(groep):
            if groep[-1]["tot"] - b["van"] < duur:
                break
            som, t, j = 0.0, b["van"], i
            while t < b["van"] + duur:
                blok = groep[j]
                stuk = min(blok["tot"], b["van"] + duur) - t
                som += blok["allin"] * stuk.total_seconds()
                t += stuk
                j += 1
            gem = som / duur.total_seconds()
            if beste is None or gem < beste[2] - 1e-9:
                beste = (b["van"], b["van"] + duur, gem)
    return beste


# ── de inzichten ──────────────────────────────────────────────────────────────


def negatieve_prijzen(opslag: Opslag, dag: date, moment: datetime) -> dict[str, str] | None:
    start = max(dag_grenzen(dag)[0], moment)
    eind = dag_grenzen(dag + timedelta(days=1))[1]
    negatief = [
        b
        for b in prijzen(opslag, "stroom", start - timedelta(hours=1), eind)
        if b["allin"] < 0 and b["tot"] > start
    ]
    if not negatief:
        return None
    groepen = aaneengesloten(negatief)
    eerste = groepen[0]
    laagste = min(b["allin"] for b in negatief)
    extra = f" · nog {len(groepen) - 1} keer" if len(groepen) > 1 else ""
    return _inzicht(
        "negatieve_prijzen",
        "Negatieve stroomprijs",
        f"{_dagnaam(lokaal(eerste[0]['van']), dag)} {klok(eerste[0]['van'])} – {klok(eerste[-1]['tot'])}",
        f"laagste {euro(laagste, 3)}/kWh: je krijgt geld voor verbruik{extra}",
        "goed",
        "zon",
    )


def goedkoopste_morgen(opslag: Opslag, dag: date, moment: datetime) -> dict[str, str] | None:
    morgen = dag + timedelta(days=1)
    blokken = prijzen(opslag, "stroom", *dag_grenzen(morgen))
    venster = goedkoopste_venster(blokken, 1)
    if venster is None:
        return None
    van, tot, gem = venster
    gemiddeld = sum(b["allin"] * (b["tot"] - b["van"]).total_seconds() for b in blokken) / sum(
        (b["tot"] - b["van"]).total_seconds() for b in blokken
    )
    return _inzicht(
        "goedkoopste_morgen",
        "Goedkoopste uur morgen",
        f"{klok(van)} – {klok(tot)}",
        f"{euro(gem, 3)}/kWh, daggemiddelde {euro(gemiddeld, 3)}",
        "neutraal",
        "klok",
    )


def besparing_laden(opslag: Opslag, dag: date, moment: datetime) -> dict[str, str] | None:
    van = dag.replace(day=1)
    vermogen = float(lees_instellingen(opslag, STANDAARD)["vermogen_kw"])
    sessies = [
        s
        for s in laadsessies(opslag, dag_grenzen(van)[0], min(moment, dag_grenzen(dag)[1]), vermogen)
        if s["besparing"] is not None
    ]
    if not sessies:
        return None
    totaal = sum(s["besparing"] for s in sessies)
    slim = any(s["slim"] for s in sessies)
    n = len(sessies)
    return _inzicht(
        "besparing_laden",
        ("Slim laden bespaarde" if slim else "Laadmoment bespaarde") if totaal >= 0 else "Laden kostte extra",
        euro(abs(totaal)),
        f"deze maand t.o.v. direct laden · {n} {'sessie' if n == 1 else 'sessies'}",
        "goed" if totaal >= 0.005 else "neutraal" if totaal >= 0 else "let_op",
        "auto",
    )


def kosten_maand(opslag: Opslag, dag: date, moment: datetime) -> dict[str, str] | None:
    van = dag.replace(day=1)
    deze = {d: c for d, c in dagcijfers(opslag, van, dag).items() if c["verbruik"]}
    if not deze:
        return None
    t_m = max(deze)  # meterdata loopt een dag achter: vergelijk alleen dagen die er zijn
    kosten = sum(kosten_van(c) for c in deze.values())
    laatste_vorige = van - timedelta(days=1)
    vorige_start = laatste_vorige.replace(day=1)
    vorige_eind = laatste_vorige.replace(day=min(t_m.day, laatste_vorige.day))
    vorige = [c for c in dagcijfers(opslag, vorige_start, vorige_eind).values() if c["verbruik"]]
    toelichting = f"1 – {t_m.day} {MAANDEN[t_m.month - 1]}"
    toon = "neutraal"
    if vorige:
        k_vorig = sum(kosten_van(c) for c in vorige)
        toelichting += f" · vorige maand {euro(k_vorig)} in dezelfde dagen"
        if k_vorig > 0:
            toon = _toon(kosten / k_vorig - 1)
    return _inzicht("kosten_maand", "Energiekosten deze maand", euro(kosten), toelichting, toon, "euro")


def gem_laadprijs(opslag: Opslag, dag: date, moment: datetime) -> dict[str, str] | None:
    start, eind = dagen_grenzen(dag.replace(day=1), dag)
    eind = min(eind, moment)
    laden = geladen(opslag, start, eind)
    kwh = sum(i["kwh"] for i in laden)
    if kwh < 1:
        return None
    gem = laadkosten(laden) / kwh
    blokken = prijzen(opslag, "stroom", start, eind)
    toelichting, toon = "deze maand", "neutraal"
    if blokken:
        markt = sum(b["allin"] * (b["tot"] - b["van"]).total_seconds() for b in blokken) / sum(
            (b["tot"] - b["van"]).total_seconds() for b in blokken
        )
        toelichting = f"deze maand · gemiddelde stroomprijs {euro(markt, 3)}"
        if markt > 0:
            toon = _toon(gem / markt - 1)
    return _inzicht(
        "gem_laadprijs", "Gemiddelde laadprijs", f"{euro(gem, 3)}/kWh", toelichting, toon, "bliksem"
    )


def gas_vs_vorige_week(opslag: Opslag, dag: date, moment: datetime) -> dict[str, str] | None:
    """Afgelopen 7 dagen (t/m gisteren) tegen de 7 dagen daarvoor, gecorrigeerd met graaddagen."""
    eind = dag - timedelta(days=1)
    cijfers = dagcijfers(opslag, eind - timedelta(days=13), eind)
    temps = temperatuur_per_dag(opslag, *dagen_grenzen(eind - timedelta(days=13), eind))

    def week(laatste: date) -> tuple[float, float, int]:
        dagen = [laatste - timedelta(days=i) for i in range(7)]
        met = [d for d in dagen if d in cijfers and cijfers[d]["verbruik"]]
        gas = sum(cijfers[d]["hoeveelheid"]["gas"] for d in met)
        gd = sum(max(0.0, GRAADDAG_BASIS - temps[d]) for d in met if d in temps)
        return gas, gd, len(met)

    gas_a, gd_a, n_a = week(eind)
    gas_b, gd_b, n_b = week(eind - timedelta(days=7))
    if n_a < 5 or n_b < 5 or gas_b <= 0:
        return None
    if gd_a >= 3 and gd_b >= 3:
        verschil = (gas_a / gd_a) / (gas_b / gd_b) - 1
        toelichting = (
            f"per graaddag: {getal(gas_a)} m³ bij {getal(gd_a, 0)} graaddagen, "
            f"vorige week {getal(gas_b)} m³ bij {getal(gd_b, 0)}"
        )
    else:  # zomer: geen stookweer, dus gewoon het verbruik vergelijken
        verschil = gas_a / gas_b - 1
        toelichting = f"{getal(gas_a)} m³, vorige week {getal(gas_b)} m³ (geen stookweer)"
    return _inzicht(
        "gas_vs_vorige_week",
        "Gas t.o.v. vorige week",
        procent(verschil),
        toelichting,
        _toon(verschil),
        "trend_neer" if verschil < 0 else "trend_op" if verschil > 0 else "vlam",
    )


# Volgorde = belangrijkste eerst: wat je vandaag nog kunt doen, dan terugblikken.
INZICHTEN: tuple[Callable[[Opslag, date, datetime], dict[str, str] | None], ...] = (
    negatieve_prijzen,
    goedkoopste_morgen,
    besparing_laden,
    kosten_maand,
    gem_laadprijs,
    gas_vs_vorige_week,
)


def inzichten(opslag: Opslag, dag: date, moment: datetime | None = None) -> list[dict[str, str]]:
    moment = moment or nu()
    if dag != lokaal(moment):  # terugkijken: alsof het het eind van die dag is
        moment = min(moment, dag_grenzen(dag)[1])
    return [i for f in INZICHTEN if (i := f(opslag, dag, moment)) is not None]
