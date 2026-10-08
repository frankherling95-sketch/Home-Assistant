"""Tabellen: één definitie voor DuckDB en BigQuery.

Alle tabellen zijn append-only (bronslaag). Elke rij krijgt `opgehaald`; lezen gaat via
`actueel()`, dat per sleutel de laatst opgehaalde rij neemt. Zo kan een connector
dezelfde periode gerust opnieuw ophalen (bijv. verbruik van gisteren dat later definitief wordt).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tabel:
    naam: str
    kolommen: tuple[tuple[str, str], ...]  # (naam, BigQuery-type)
    sleutel: tuple[str, ...]
    tijdkolom: str | None = None  # BigQuery: partitie per dag op deze kolom, queries filteren erop


OPGEHAALD = ("opgehaald", "TIMESTAMP")

PRIJS = Tabel(
    "prijs",
    (
        ("soort", "STRING"),
        ("van", "TIMESTAMP"),
        ("tot", "TIMESTAMP"),
        ("marktprijs", "FLOAT64"),
        ("allin", "FLOAT64"),
        OPGEHAALD,
    ),
    ("soort", "van"),
    "van",
)  # soort: stroom | gas; allin in €/kWh of €/m³

VERBRUIK = Tabel(
    "verbruik",
    (
        ("soort", "STRING"),
        ("van", "TIMESTAMP"),
        ("tot", "TIMESTAMP"),
        ("hoeveelheid", "FLOAT64"),
        ("kosten", "FLOAT64"),
        ("eenheid", "STRING"),
        OPGEHAALD,
    ),
    ("soort", "van"),
    "van",
)  # soort: stroom | teruglevering | gas  (bron: Frank Energie, slimme meter)

LADER = Tabel(
    "lader_meting",
    (
        ("tijd", "TIMESTAMP"),
        ("lader_id", "STRING"),
        ("naam", "STRING"),
        ("status", "STRING"),
        ("vermogen_kw", "FLOAT64"),
        ("sessie_kwh", "FLOAT64"),
        ("totaal_kwh", "FLOAT64"),
        OPGEHAALD,
    ),
    ("lader_id", "tijd"),
    "tijd",
)

AUTO = Tabel(
    "auto_meting",
    (
        ("tijd", "TIMESTAMP"),
        ("auto_id", "STRING"),
        ("naam", "STRING"),
        ("accu_pct", "FLOAT64"),
        ("bereik_km", "FLOAT64"),
        ("ingeplugd", "BOOL"),
        ("laadt", "BOOL"),
        ("bijgewerkt", "TIMESTAMP"),
        OPGEHAALD,
    ),
    ("auto_id", "tijd"),
    "tijd",
)

INSTELLING = Tabel(
    "instelling",
    (("sleutel", "STRING"), ("waarde", "STRING"), OPGEHAALD),
    ("sleutel",),
)  # waarde is JSON

STUURACTIE = Tabel(
    "stuuractie",
    (("tijd", "TIMESTAMP"), ("lader_id", "STRING"), ("actie", "STRING"), ("reden", "STRING"), OPGEHAALD),
    ("lader_id", "tijd"),
    "tijd",
)

WEER = Tabel(
    "weer",
    (("van", "TIMESTAMP"), ("tot", "TIMESTAMP"), ("temperatuur", "FLOAT64"), OPGEHAALD),
    ("van",),
    "van",
)  # per uur, °C (Open-Meteo); vooruit is het een verwachting die later wordt bijgewerkt

MELDING = Tabel(
    "melding",
    (("sleutel", "STRING"), ("tijd", "TIMESTAMP"), ("soort", "STRING"), ("tekst", "STRING"), OPGEHAALD),
    ("sleutel",),
    "tijd",
)  # verstuurde meldingen; de sleutel voorkomt dat dezelfde melding twee keer gaat

RONDE = Tabel(
    "ronde",
    (("tijd", "TIMESTAMP"), ("stap", "STRING"), ("uitslag", "STRING"), ("duur_s", "FLOAT64"), OPGEHAALD),
    ("tijd", "stap"),
    "tijd",
)  # rondelog van de verzamelaar: per stap ok | overgeslagen | fout: …

TABELLEN = (PRIJS, VERBRUIK, LADER, AUTO, INSTELLING, STUURACTIE, WEER, MELDING, RONDE)


def actueel(t: Tabel, ref: str) -> str:
    """SELECT op de actuele stand per sleutel. `ref` is de volledig gekwalificeerde tabelnaam.

    QUALIFY werkt in DuckDB en BigQuery; BigQuery wil er een WHERE bij.
    """
    return (
        f"(SELECT * FROM {ref} WHERE TRUE "
        f"QUALIFY ROW_NUMBER() OVER (PARTITION BY {', '.join(t.sleutel)} ORDER BY opgehaald DESC) = 1)"
    )
