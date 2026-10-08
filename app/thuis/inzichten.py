"""Inzichten voor de overzichtspagina: korte, uitgerekende feiten met een toon en een icoon.

Elk inzicht staat los; zonder data valt het weg in plaats van een nul te tonen. De data wordt
één keer opgehaald (`Gegevens`) en door alle inzichten gedeeld: in BigQuery kost elke query
minimaal 10 MB, en deze pagina wordt het vaakst geopend.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from .config import TZ
from .inzicht import MAANDEN, dag_grenzen, dagcijfers, kosten_van, lokaal, prijzen
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


def tijdgemiddelde(blokken: list[dict[str, Any]]) -> float | None:
    duur = sum((b["tot"] - b["van"]).total_seconds() for b in blokken)
    return sum(b["allin"] * (b["tot"] - b["van"]).total_seconds() for b in blokken) / duur if duur else None


# ── gedeelde gegevens ─────────────────────────────────────────────────────────


@dataclass
class Gegevens:
    dag: date
    moment: datetime
    cijfers: dict[date, dict[str, Any]]  # vorige maand (of 14 dagen terug) t/m `dag`
    prijzen: list[dict[str, Any]]  # stroom, begin van de maand t/m eind van morgen
    sessies: list[dict[str, Any]]  # deze maand

    def stroomprijzen(self, van: datetime, tot: datetime) -> list[dict[str, Any]]:
        return [b for b in self.prijzen if van <= b["van"] < tot]


def gegevens(opslag: Opslag, dag: date, moment: datetime) -> Gegevens:
    maand = dag.replace(day=1)
    vorige_maand = (maand - timedelta(days=1)).replace(day=1)
    vermogen = float(lees_instellingen(opslag, STANDAARD)["vermogen_kw"])
    return Gegevens(
        dag=dag,
        moment=moment,
        cijfers=dagcijfers(opslag, min(vorige_maand, dag - timedelta(days=14)), dag),
        prijzen=prijzen(opslag, "stroom", dag_grenzen(maand)[0], dag_grenzen(dag + timedelta(days=1))[1]),
        sessies=laadsessies(opslag, dag_grenzen(maand)[0], min(moment, dag_grenzen(dag)[1]), vermogen),
    )


# ── de inzichten ──────────────────────────────────────────────────────────────


def negatieve_prijzen(g: Gegevens) -> dict[str, str] | None:
    start = max(dag_grenzen(g.dag)[0], g.moment)
    eind = dag_grenzen(g.dag + timedelta(days=1))[1]
    negatief = [b for b in g.prijzen if b["allin"] < 0 and b["tot"] > start and b["van"] < eind]
    if not negatief:
        return None
    groepen = aaneengesloten(negatief)
    eerste = groepen[0]
    extra = f" · nog {len(groepen) - 1} keer" if len(groepen) > 1 else ""
    return _inzicht(
        "negatieve_prijzen",
        "Negatieve stroomprijs",
        f"{_dagnaam(lokaal(eerste[0]['van']), g.dag)} {klok(eerste[0]['van'])} – {klok(eerste[-1]['tot'])}",
        f"laagste {euro(min(b['allin'] for b in negatief), 3)}/kWh: je krijgt geld voor verbruik{extra}",
        "goed",
        "zon",
    )


def goedkoopste_morgen(g: Gegevens) -> dict[str, str] | None:
    blokken = g.stroomprijzen(*dag_grenzen(g.dag + timedelta(days=1)))
    venster = goedkoopste_venster(blokken, 1)
    if venster is None:
        return None
    van, tot, gem = venster
    return _inzicht(
        "goedkoopste_morgen",
        "Goedkoopste uur morgen",
        f"{klok(van)} – {klok(tot)}",
        f"{euro(gem, 3)}/kWh, daggemiddelde {euro(tijdgemiddelde(blokken), 3)}",
        "neutraal",
        "klok",
    )


def besparing_laden(g: Gegevens) -> dict[str, str] | None:
    sessies = [s for s in g.sessies if s["besparing"] is not None]
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


def kosten_maand(g: Gegevens) -> dict[str, str] | None:
    van = g.dag.replace(day=1)
    deze = {d: c for d, c in g.cijfers.items() if van <= d <= g.dag and c["verbruik"]}
    if not deze:
        return None
    t_m = max(deze)  # meterdata loopt een dag achter: vergelijk alleen dagen die er zijn
    kosten = sum(kosten_van(c) for c in deze.values())
    laatste_vorige = van - timedelta(days=1)
    vorige_van = laatste_vorige.replace(day=1)
    vorige_tot = laatste_vorige.replace(day=min(t_m.day, laatste_vorige.day))
    vorige = [c for d, c in g.cijfers.items() if vorige_van <= d <= vorige_tot and c["verbruik"]]
    toelichting = f"1 – {t_m.day} {MAANDEN[t_m.month - 1]}"
    toon = "neutraal"
    if vorige:
        k_vorig = sum(kosten_van(c) for c in vorige)
        toelichting += f" · vorige maand {euro(k_vorig)} in dezelfde dagen"
        if k_vorig > 0:
            toon = _toon(kosten / k_vorig - 1)
    return _inzicht("kosten_maand", "Energiekosten deze maand", euro(kosten), toelichting, toon, "euro")


def gem_laadprijs(g: Gegevens) -> dict[str, str] | None:
    van = g.dag.replace(day=1)
    dagen = [c for d, c in g.cijfers.items() if van <= d <= g.dag]
    kwh = sum(c["laden_kwh"] for c in dagen)
    if kwh < 1:
        return None
    gem = sum(c["laden_kosten"] for c in dagen) / kwh
    markt = tijdgemiddelde(g.stroomprijzen(dag_grenzen(van)[0], min(g.moment, dag_grenzen(g.dag)[1])))
    toelichting, toon = "deze maand", "neutraal"
    if markt:
        toelichting = f"deze maand · gemiddelde stroomprijs {euro(markt, 3)}"
        if markt > 0:
            toon = _toon(gem / markt - 1)
    return _inzicht(
        "gem_laadprijs", "Gemiddelde laadprijs", f"{euro(gem, 3)}/kWh", toelichting, toon, "bliksem"
    )


def gas_vs_vorige_week(g: Gegevens) -> dict[str, str] | None:
    """Afgelopen 7 dagen (t/m gisteren) tegen de 7 dagen daarvoor, gecorrigeerd met graaddagen."""
    eind = g.dag - timedelta(days=1)

    def week(laatste: date) -> tuple[float, float, int]:
        dagen = [g.cijfers[d] for d in (laatste - timedelta(days=i) for i in range(7)) if d in g.cijfers]
        met = [c for c in dagen if c["verbruik"]]
        gas = sum(c["hoeveelheid"]["gas"] for c in met)
        gd = sum(max(0.0, GRAADDAG_BASIS - c["temperatuur"]) for c in met if c["temperatuur"] is not None)
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
INZICHTEN: tuple[Callable[[Gegevens], dict[str, str] | None], ...] = (
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
    g = gegevens(opslag, dag, moment)
    return [i for f in INZICHTEN if (i := f(g)) is not None]
