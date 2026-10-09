"""Lezen en samenvatten: wat de app per dag, per periode en 'nu' toont."""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from .config import TZ
from .opslag import Opslag, nu, tegelijk

MAANDEN = ("jan", "feb", "mrt", "apr", "mei", "jun", "jul", "aug", "sep", "okt", "nov", "dec")
MAANDEN_LANG = (
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
)
WEEKDAGEN = ("ma", "di", "wo", "do", "vr", "za", "zo")
SOORTEN = ("stroom", "teruglevering", "gas")
EENHEID = {"stroom": "kWh", "teruglevering": "kWh", "gas": "m³", "laden": "kWh"}


def dag_grenzen(dag: date) -> tuple[datetime, datetime]:
    """Lokale dag (Europe/Amsterdam) als UTC-interval [start, eind). Klopt ook bij zomertijdwissel."""
    start = datetime.combine(dag, time(0), TZ)
    eind = datetime.combine(dag + timedelta(days=1), time(0), TZ)
    return start.astimezone(UTC), eind.astimezone(UTC)


def dagen_grenzen(van: date, tot: date) -> tuple[datetime, datetime]:
    """Lokale dagen `van` t/m `tot` (inclusief) als UTC-interval [start, eind)."""
    return dag_grenzen(van)[0], dag_grenzen(tot)[1]


def lokaal(moment: datetime) -> date:
    return moment.astimezone(TZ).date()


def vandaag() -> date:
    return lokaal(nu())


# ── lezen ─────────────────────────────────────────────────────────────────────


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


def verbruik_per_dag(opslag: Opslag, van: datetime, tot: datetime) -> list[dict[str, Any]]:
    """Per soort en lokale dag opgeteld in de database: een jaar is zo ±1100 rijen i.p.v. 26.000."""
    return opslag.lees(
        f"SELECT soort, {opslag.lokale_dag('van')} AS dag, SUM(hoeveelheid) AS hoeveelheid, "
        "SUM(kosten) AS kosten FROM {verbruik} WHERE van >= @van AND van < @tot GROUP BY soort, dag",
        van=van,
        tot=tot,
    )


def temperaturen(opslag: Opslag, van: datetime, tot: datetime) -> list[dict[str, Any]]:
    return opslag.lees(
        "SELECT van, temperatuur FROM {weer} WHERE van >= @van AND van < @tot ORDER BY van", van=van, tot=tot
    )


def temperatuur_per_dag(opslag: Opslag, van: datetime, tot: datetime) -> dict[date, float]:
    rijen = opslag.lees(
        f"SELECT {opslag.lokale_dag('van')} AS dag, AVG(temperatuur) AS temperatuur "
        "FROM {weer} WHERE van >= @van AND van < @tot GROUP BY dag",
        van=van,
        tot=tot,
    )
    return {r["dag"]: r["temperatuur"] for r in rijen if r["temperatuur"] is not None}


def lader_metingen(opslag: Opslag, van: datetime, tot: datetime) -> list[dict[str, Any]]:
    return opslag.lees(
        "SELECT tijd, lader_id, naam, status, vermogen_kw, sessie_kwh, totaal_kwh FROM {lader_meting} "
        "WHERE tijd >= @van AND tijd < @tot ORDER BY tijd",
        van=van,
        tot=tot,
    )


def laatste(
    opslag: Opslag, tabel: str, moment: datetime | None = None, dagen: int = 30
) -> dict[str, Any] | None:
    """Meest recente meting tot `moment`. Het tijdfilter houdt de query binnen een paar partities."""
    moment = moment or nu()
    rijen = opslag.lees(
        f"SELECT * FROM {{{tabel}}} WHERE tijd >= @sinds AND tijd <= @tot ORDER BY tijd DESC LIMIT 1",
        sinds=moment - timedelta(days=dagen),
        tot=moment,
    )
    return rijen[0] if rijen else None


# ── laden ─────────────────────────────────────────────────────────────────────


class Prijslijst:
    """Prijsblokken (15 of 60 minuten) op tijdstip opzoeken."""

    def __init__(self, blokken: list[dict[str, Any]]) -> None:
        self.blokken = sorted(blokken, key=lambda b: b["van"])
        self._starts = [b["van"] for b in self.blokken]

    def blok(self, moment: datetime) -> dict[str, Any] | None:
        i = bisect_right(self._starts, moment) - 1
        if i >= 0 and moment < self.blokken[i]["tot"]:
            return self.blokken[i]
        return None

    def op(self, moment: datetime) -> float | None:
        b = self.blok(moment)
        return b["allin"] if b else None


def laad_intervallen(opslag: Opslag, van: datetime, tot: datetime) -> list[dict[str, Any]]:
    """Geladen kWh tussen opeenvolgende metingen van de lader, uit de meterstand (`totaal_kwh`).

    Alleen intervallen waarin geladen is, waarvan de eindmeting in [van, tot) valt. Er wordt een
    uur extra teruggekeken, zodat ook het eerste interval een beginstand heeft. Negatieve
    sprongen (meter vervangen of gereset) vallen weg. Het verschil wordt in de database
    berekend: over een jaar blijven alleen de laadkwartieren over.
    """
    rijen = opslag.lees(
        "SELECT lader_id, vorige, tijd, kwh FROM ("
        "SELECT lader_id, tijd, LAG(tijd) OVER w AS vorige, totaal_kwh - LAG(totaal_kwh) OVER w AS kwh "
        "FROM {lader_meting} WHERE tijd >= @begin AND tijd < @eind "
        "WINDOW w AS (PARTITION BY lader_id ORDER BY tijd)"
        ") WHERE kwh > 0 AND tijd >= @start ORDER BY tijd",
        begin=van - timedelta(hours=1),
        start=van,
        eind=tot,
    )
    return [{"lader_id": r["lader_id"], "van": r["vorige"], "tot": r["tijd"], "kwh": r["kwh"]} for r in rijen]


def met_prijs(intervallen: list[dict[str, Any]], lijst: Prijslijst) -> list[dict[str, Any]]:
    """Prijs per interval: die van het blok waar het midden van het interval in valt."""
    return [{**i, "prijs": lijst.op(i["van"] + (i["tot"] - i["van"]) / 2)} for i in intervallen]


def laden_per_uur(intervallen: list[dict[str, Any]]) -> dict[datetime, float]:
    """kWh per UTC-uur; een interval telt bij het uur van zijn eindmeting."""
    uit: dict[datetime, float] = defaultdict(float)
    for i in intervallen:
        uit[i["tot"].replace(minute=0, second=0, microsecond=0)] += i["kwh"]
    return dict(uit)


def laadkosten(intervallen: list[dict[str, Any]]) -> float:
    return sum(i["kwh"] * (i.get("prijs") or 0) for i in intervallen)


def geladen(opslag: Opslag, van: datetime, tot: datetime) -> list[dict[str, Any]]:
    """Laadintervallen met prijs in [van, tot)."""
    intervallen = laad_intervallen(opslag, van, tot)
    if not intervallen:
        return []
    lijst = Prijslijst(prijzen(opslag, "stroom", intervallen[0]["van"] - timedelta(hours=1), tot))
    return met_prijs(intervallen, lijst)


# ── dag ───────────────────────────────────────────────────────────────────────


def _totalen(
    hoeveel: dict[str, float], kosten: dict[str, float], laden_kwh: float, laden_kosten: float
) -> dict[str, dict[str, Any]]:
    uit = {
        s: {
            "hoeveelheid": round(hoeveel.get(s, 0), 3),
            "kosten": round(kosten.get(s, 0), 2),
            "eenheid": EENHEID[s],
        }
        for s in SOORTEN
    }
    # Teruglevering is opbrengst; het teken verschilt per bron, dus altijd als aftrekpost.
    uit["teruglevering"]["kosten"] = -abs(uit["teruglevering"]["kosten"])
    uit["laden"] = {"hoeveelheid": round(laden_kwh, 3), "kosten": round(laden_kosten, 2), "eenheid": "kWh"}
    return uit


def _blok(p: dict[str, Any]) -> dict[str, Any]:
    return {"van": p["van"].isoformat(), "tot": p["tot"].isoformat(), "prijs": p["allin"]}


def dagoverzicht(opslag: Opslag, dag: date) -> dict[str, Any]:
    start, eind = dag_grenzen(dag)
    # Eén query voor stroom en gas (BigQuery rekent per query); een uur extra voor het eerste laadinterval.
    # De vier vragen hangen niet van elkaar af: tegelijk.
    alle, rijen, intervallen, temperatuur = tegelijk(
        opslag,
        lambda: opslag.lees(
            "SELECT soort, van, tot, marktprijs, allin FROM {prijs} WHERE van >= @van AND van < @tot ORDER BY van",
            van=start - timedelta(hours=1),
            tot=eind,
        ),
        lambda: verbruik(opslag, start, eind),
        lambda: laad_intervallen(opslag, start, eind),
        lambda: temperaturen(opslag, start, eind),
    )
    stroom = [p for p in alle if p["soort"] == "stroom"]
    stroomprijs = [p for p in stroom if p["van"] >= start]
    gasprijs = [p for p in alle if p["soort"] == "gas" and p["van"] >= start]
    laden = met_prijs(intervallen, Prijslijst(stroom))
    laden_uur = laden_per_uur(laden)
    temp = {t["van"].replace(minute=0, second=0): t["temperatuur"] for t in temperatuur}

    uren = [start + timedelta(hours=i) for i in range(int((eind - start).total_seconds() // 3600))]
    per_soort = {s: [r for r in rijen if r["soort"] == s] for s in SOORTEN}
    hoeveel = {s: per_uur(v, "hoeveelheid") for s, v in per_soort.items()}
    kosten = {s: per_uur(v, "kosten") for s, v in per_soort.items()}

    return {
        "datum": dag.isoformat(),
        "uren": [u.isoformat() for u in uren],
        "reeksen": {
            "stroom": [round(hoeveel["stroom"].get(u, 0), 3) for u in uren],
            "teruglevering": [round(hoeveel["teruglevering"].get(u, 0), 3) for u in uren],
            "gas": [round(hoeveel["gas"].get(u, 0), 3) for u in uren],
            "laden": [round(laden_uur.get(u, 0), 3) for u in uren],
            "kosten_stroom": [
                round(kosten["stroom"].get(u, 0) - abs(kosten["teruglevering"].get(u, 0)), 3) for u in uren
            ],
            "temperatuur": [temp.get(u) for u in uren],
        },
        "prijzen": {"stroom": [_blok(p) for p in stroomprijs], "gas": [_blok(p) for p in gasprijs]},
        "totalen": _totalen(
            {s: sum(v.values()) for s, v in hoeveel.items()},
            {s: sum(v.values()) for s, v in kosten.items()},
            sum(laden_uur.values()),
            laadkosten(laden),
        ),
        "compleet": {"verbruik": bool(rijen), "prijzen": bool(stroomprijs)},
    }


def per_uur(rijen: list[dict[str, Any]], waarde: str, sleutel: str = "van") -> dict[datetime, float]:
    """Kwartierblokken optellen tot uren (UTC-uur als sleutel)."""
    uit: dict[datetime, float] = defaultdict(float)
    for r in rijen:
        uit[r[sleutel].replace(minute=0, second=0, microsecond=0)] += r[waarde] or 0
    return dict(uit)


# ── periode ───────────────────────────────────────────────────────────────────

PERIODES = ("week", "maand", "jaar")


def periode_grenzen(soort: str, dag: date) -> tuple[date, date]:
    """Eerste en laatste dag (inclusief) van de week (ma–zo), maand of het jaar waar `dag` in valt."""
    if soort == "week":
        van = dag - timedelta(days=dag.weekday())
        return van, van + timedelta(days=6)
    if soort == "maand":
        van = dag.replace(day=1)
        return van, (van + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    if soort == "jaar":
        return date(dag.year, 1, 1), date(dag.year, 12, 31)
    raise ValueError(f"Onbekende periode: {soort}")


def periode_label(soort: str, van: date, tot: date) -> str:
    if soort == "jaar":
        return str(van.year)
    if soort == "maand":
        return f"{MAANDEN_LANG[van.month - 1]} {van.year}"
    return dagen_label(van, tot)


def dagen_label(van: date, tot: date) -> str:
    """'5 – 11 okt 2026', '28 sep – 4 okt 2026' of '29 dec 2025 – 4 jan 2026'."""
    if van == tot:
        return f"{van.day} {MAANDEN[van.month - 1]} {van.year}"
    if van.year != tot.year:
        return (
            f"{van.day} {MAANDEN[van.month - 1]} {van.year} – {tot.day} {MAANDEN[tot.month - 1]} {tot.year}"
        )
    if van.month != tot.month:
        return f"{van.day} {MAANDEN[van.month - 1]} – {tot.day} {MAANDEN[tot.month - 1]} {tot.year}"
    return f"{van.day} – {tot.day} {MAANDEN[tot.month - 1]} {tot.year}"


def _lege_dag() -> dict[str, Any]:
    return {
        "hoeveelheid": defaultdict(float),
        "kosten": defaultdict(float),
        "verbruik": False,
        "laden_kwh": 0.0,
        "laden_kosten": 0.0,
        "temperatuur": None,
    }


def dagcijfers(opslag: Opslag, van: date, tot: date) -> dict[date, dict[str, Any]]:
    """Per lokale dag: hoeveelheid en kosten per soort, laden (kWh, €) en gemiddelde temperatuur.

    Alleen dagen met gegevens staan erin; `verbruik` geeft aan of er meterdata is.
    """
    start, eind = dagen_grenzen(van, tot)
    per_dag, intervallen, temperatuur = tegelijk(
        opslag,
        lambda: verbruik_per_dag(opslag, start, eind),
        lambda: geladen(opslag, start, eind),
        lambda: temperatuur_per_dag(opslag, start, eind),
    )
    uit: dict[date, dict[str, Any]] = defaultdict(_lege_dag)
    for r in per_dag:
        d = uit[r["dag"]]
        d["hoeveelheid"][r["soort"]] += r["hoeveelheid"] or 0
        d["kosten"][r["soort"]] += r["kosten"] or 0
        d["verbruik"] = True
    for i in intervallen:
        d = uit[lokaal(i["tot"])]
        d["laden_kwh"] += i["kwh"]
        d["laden_kosten"] += i["kwh"] * (i["prijs"] or 0)
    for dag, t in temperatuur.items():
        uit[dag]["temperatuur"] = t
    return dict(uit)


def kosten_van(d: dict[str, Any]) -> float:
    """Netto energiekosten van een dag: stroom + gas − teruglevering. Laden zit al in stroom."""
    k = d["kosten"]
    return k["stroom"] + k["gas"] - abs(k["teruglevering"])


def _optellen(dagen: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return _totalen(
        {s: sum(d["hoeveelheid"][s] for d in dagen) for s in SOORTEN},
        {s: sum(d["kosten"][s] for d in dagen) for s in SOORTEN},
        sum(d["laden_kwh"] for d in dagen),
        sum(d["laden_kosten"] for d in dagen),
    )


def periodeoverzicht(opslag: Opslag, soort: str, dag: date) -> dict[str, Any]:
    van, tot = periode_grenzen(soort, dag)
    # De vorige periode meteen mee (tegelijk); hoeveel dagen daarvan meetellen, blijkt pas hieronder.
    vvan, vtot = periode_grenzen(soort, van - timedelta(days=1))
    cijfers, vorige = tegelijk(
        opslag, lambda: dagcijfers(opslag, van, tot), lambda: dagcijfers(opslag, vvan, vtot)
    )
    alle_dagen = [van + timedelta(days=i) for i in range((tot - van).days + 1)]
    if soort == "jaar":
        bakjes = [f"{van.year}-{m:02d}" for m in range(1, 13)]
        labels = list(MAANDEN)

        def bakje(d: date) -> str:
            return f"{d.year}-{d.month:02d}"
    else:
        bakjes = [d.isoformat() for d in alle_dagen]
        labels = [f"{WEEKDAGEN[d.weekday()]} {d.day}" if soort == "week" else str(d.day) for d in alle_dagen]

        def bakje(d: date) -> str:
            return d.isoformat()

    per_bakje: dict[str, list[date]] = defaultdict(list)
    for d in alle_dagen:
        per_bakje[bakje(d)].append(d)
    morgen = vandaag() + timedelta(days=1)

    reeksen: dict[str, list[Any]] = {k: [] for k in (*SOORTEN, "laden", "kosten", "temperatuur")}
    for b in bakjes:
        dagen = [cijfers.get(d) or _lege_dag() for d in per_bakje[b]]
        met_meter = [d for d in dagen if d["verbruik"]]
        for s in SOORTEN:
            reeksen[s].append(round(sum(d["hoeveelheid"][s] for d in met_meter), 3) if met_meter else None)
        reeksen["kosten"].append(round(sum(kosten_van(d) for d in met_meter), 2) if met_meter else None)
        toekomst = per_bakje[b][0] >= morgen
        reeksen["laden"].append(None if toekomst else round(sum(d["laden_kwh"] for d in dagen), 3))
        temps = [d["temperatuur"] for d in dagen if d["temperatuur"] is not None]
        reeksen["temperatuur"].append(round(sum(temps) / len(temps), 1) if temps else None)

    vorige_label = periode_label(soort, vvan, vtot)
    # Loopt de periode nog (of mist het eind meterdata), dan dezelfde dagen van de vorige
    # periode vergelijken: een halve week tegen een hele week zegt niets.
    met_meter = [d for d, c in cijfers.items() if c["verbruik"]]
    if met_meter and max(met_meter) < tot:
        vtot = min(vtot, vvan + (max(met_meter) - van))
        vorige_label = dagen_label(vvan, vtot)
    return {
        "type": soort,
        "van": van.isoformat(),
        "tot": tot.isoformat(),
        "label": periode_label(soort, van, tot),
        "bakjes": bakjes,
        "bakje_labels": labels,
        "reeksen": reeksen,
        "totalen": _optellen(list(cijfers.values())),
        "vorige": _optellen([c for d, c in vorige.items() if d <= vtot]),
        "vorige_label": vorige_label,
    }
