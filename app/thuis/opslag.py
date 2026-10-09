"""Opslag: DuckDB lokaal en in tests, BigQuery in Google Cloud. Zelfde SQL voor beide.

Queries schrijven tabellen als {prijs}, {verbruik}, … en parameters als @naam.
Aggregeren gebeurt zoveel mogelijk in Python, zodat er geen dialectverschillen in de SQL nodig
zijn. Het enige verschil, de lokale datum van een tijdstip, zit in `lokale_dag()`.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, date, datetime
from typing import Any, Protocol

from .config import TZ, Config
from .schema import TABELLEN, Tabel, actueel

_DUCK_TYPES = {"STRING": "VARCHAR", "TIMESTAMP": "TIMESTAMPTZ", "FLOAT64": "DOUBLE", "BOOL": "BOOLEAN"}


def nu() -> datetime:
    return datetime.now(UTC)


class Opslag(Protocol):
    def maak_tabellen(self) -> None: ...
    def voeg_toe(self, tabel: Tabel, rijen: list[dict[str, Any]]) -> int: ...
    def lees(self, sql: str, **params: Any) -> list[dict[str, Any]]: ...
    def lokale_dag(self, kolom: str) -> str: ...  # SQL: lokale datum (Europe/Amsterdam) van een tijdstip


def _vul_aan(tabel: Tabel, rijen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Alleen bekende kolommen, ontbrekende als None, en `opgehaald` invullen."""
    stempel = nu()
    namen = [k for k, _ in tabel.kolommen]
    uit = []
    for r in rijen:
        rij = {k: r.get(k) for k in namen}
        rij["opgehaald"] = rij["opgehaald"] or stempel
        uit.append(rij)
    return uit


class DuckOpslag:
    def __init__(self, pad: str = ":memory:") -> None:
        import duckdb

        self.con = duckdb.connect(pad)
        self.con.execute("SET TimeZone = 'UTC'")
        self.con.execute("CREATE SCHEMA IF NOT EXISTS thuis")

    def _ref(self, t: Tabel) -> str:
        return f"thuis.{t.naam}"

    def maak_tabellen(self) -> None:
        for t in TABELLEN:
            kolommen = ", ".join(f"{k} {_DUCK_TYPES[v]}" for k, v in t.kolommen)
            self.con.execute(f"CREATE TABLE IF NOT EXISTS {self._ref(t)} ({kolommen})")
            # Bestaande tabel uit een oudere versie: nieuwe kolommen erbij.
            for k, v in t.kolommen:
                self.con.execute(f"ALTER TABLE {self._ref(t)} ADD COLUMN IF NOT EXISTS {k} {_DUCK_TYPES[v]}")

    def voeg_toe(self, tabel: Tabel, rijen: list[dict[str, Any]]) -> int:
        if not rijen:
            return 0
        rijen = _vul_aan(tabel, rijen)
        # Via een NDJSON-bestand in één keer inlezen: executemany zet elke waarde los om
        # (en probeert daarbij telkens pandas te importeren), wat bij duizenden rijen minuten kost.
        fd, pad = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for r in rijen:
                    f.write(json.dumps({k: _json_waarde(v) for k, v in r.items()}) + "\n")
            namen = ", ".join(k for k, _ in tabel.kolommen)
            kolommen = ", ".join(f"'{k}': '{_DUCK_TYPES[v]}'" for k, v in tabel.kolommen)
            bestand = pad.replace("\\", "/").replace("'", "''")
            self.con.cursor().execute(
                f"INSERT INTO {self._ref(tabel)} ({namen}) SELECT {namen} "
                f"FROM read_json('{bestand}', format = 'newline_delimited', columns = {{{kolommen}}})"
            )
        finally:
            os.unlink(pad)
        return len(rijen)

    def lees(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        sql = _vul_tabellen(sql, self._ref).replace("@", "$")
        # Eigen cursor per aanroep: de API leest vanuit meerdere threads.
        cur = self.con.cursor().execute(sql, params)
        namen = [d[0] for d in cur.description]
        return [_naar_utc(dict(zip(namen, r, strict=True))) for r in cur.fetchall()]

    def lokale_dag(self, kolom: str) -> str:
        return f"CAST(timezone('{TZ.key}', {kolom}) AS DATE)"


class BigQueryOpslag:
    def __init__(self, project: str, dataset: str, locatie: str = "EU") -> None:
        from google.cloud import bigquery

        self.bq = bigquery
        # Zonder project: dat van het service-account waar Cloud Run mee draait.
        self.client = bigquery.Client(project=project or None)
        self.dataset = f"{self.client.project}.{dataset}"
        self.locatie = locatie

    def _ref(self, t: Tabel) -> str:
        return f"`{self.dataset}.{t.naam}`"

    def _schema(self, t: Tabel) -> list:
        return [self.bq.SchemaField(k, v) for k, v in t.kolommen]

    def maak_tabellen(self) -> None:
        from google.api_core.exceptions import NotFound

        ds = self.bq.Dataset(self.dataset)
        ds.location = self.locatie  # anders wordt een nieuwe dataset in de VS aangemaakt
        self.client.create_dataset(ds, exists_ok=True)
        for t in TABELLEN:
            try:
                bestaand = self.client.get_table(f"{self.dataset}.{t.naam}")
            except NotFound:
                tabel = self.bq.Table(f"{self.dataset}.{t.naam}", schema=self._schema(t))
                # Partitie op de tijd waar queries op filteren, clustering op de sleutel:
                # zo leest een dagoverzicht alleen die dag in plaats van de hele historie.
                if t.tijdkolom:
                    tabel.time_partitioning = self.bq.TimePartitioning(field=t.tijdkolom)
                tabel.clustering_fields = list(t.sleutel)[:4]
                self.client.create_table(tabel, exists_ok=True)
                continue
            # Tabel uit een oudere versie: nieuwe kolommen erbij (BigQuery staat toevoegen toe).
            namen = {f.name for f in bestaand.schema}
            nieuw = [f for f in self._schema(t) if f.name not in namen]
            if nieuw:
                bestaand.schema = [*bestaand.schema, *nieuw]
                self.client.update_table(bestaand, ["schema"])

    def voeg_toe(self, tabel: Tabel, rijen: list[dict[str, Any]]) -> int:
        if not rijen:
            return 0
        rijen = [{k: _json_waarde(v) for k, v in r.items()} for r in _vul_aan(tabel, rijen)]
        # Laadtaak i.p.v. streaming insert: laadtaken zijn gratis.
        job = self.client.load_table_from_json(
            rijen,
            f"{self.dataset}.{tabel.naam}",
            job_config=self.bq.LoadJobConfig(
                schema=self._schema(tabel), write_disposition=self.bq.WriteDisposition.WRITE_APPEND
            ),
        )
        job.result()
        return len(rijen)

    def lees(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        config = self.bq.QueryJobConfig(
            query_parameters=[self.bq.ScalarQueryParameter(k, _bq_type(v), v) for k, v in params.items()]
        )
        rows = self.client.query(_vul_tabellen(sql, self._ref), job_config=config).result()
        return [_naar_utc(dict(r.items())) for r in rows]

    def lokale_dag(self, kolom: str) -> str:
        return f"DATE({kolom}, '{TZ.key}')"


def _vul_tabellen(sql: str, ref) -> str:
    """{prijs} → actuele stand van die tabel."""
    return sql.format(**{t.naam: actueel(t, ref(t)) for t in TABELLEN})


def _naar_utc(rij: dict[str, Any]) -> dict[str, Any]:
    return {k: v.astimezone(UTC) if isinstance(v, datetime) else v for k, v in rij.items()}


def _json_waarde(v: Any) -> Any:
    return v.isoformat() if isinstance(v, (datetime, date)) else v


def _bq_type(v: Any) -> str:
    if isinstance(v, bool):
        return "BOOL"
    if isinstance(v, datetime):
        return "TIMESTAMP"
    if isinstance(v, date):
        return "DATE"
    if isinstance(v, int):
        return "INT64"
    if isinstance(v, float):
        return "FLOAT64"
    return "STRING"


def maak_opslag(cfg: Config) -> Opslag:
    if cfg.opslag == "bigquery":
        return BigQueryOpslag(cfg.gcp_project, cfg.bq_dataset, cfg.bq_locatie)
    return DuckOpslag(cfg.duckdb_pad)


def voeg_toe_gewijzigd(opslag: Opslag, tabel: Tabel, rijen: list[dict[str, Any]]) -> int:
    """Alleen rijen opslaan die nieuw zijn of afwijken van de actuele stand.

    Prijzen en verbruik worden elke ronde opnieuw opgehaald; zonder deze filter groeit de
    tabel elke 15 minuten met dezelfde gegevens.
    """
    if not rijen or not tabel.tijdkolom:
        return opslag.voeg_toe(tabel, rijen)
    kol = tabel.tijdkolom
    waarden = [k for k, _ in tabel.kolommen if k != "opgehaald"]
    bestaand = opslag.lees(
        f"SELECT {', '.join(waarden)} FROM {{{tabel.naam}}} WHERE {kol} >= @van AND {kol} <= @tot",
        van=min(r[kol] for r in rijen),
        tot=max(r[kol] for r in rijen),
    )

    def vingerafdruk(r: dict[str, Any]) -> tuple:
        return tuple(round(v, 6) if isinstance(v, float) else v for v in (r.get(k) for k in waarden))

    gezien = {vingerafdruk(r) for r in bestaand}
    return opslag.voeg_toe(tabel, [r for r in rijen if vingerafdruk(r) not in gezien])


# ── Instellingen (sleutel/waarde, JSON) ─────────────────────────────────────────


def lees_instellingen(opslag: Opslag, standaard: dict[str, Any]) -> dict[str, Any]:
    uit = dict(standaard)
    for r in opslag.lees("SELECT sleutel, waarde FROM {instelling}"):
        if r["sleutel"] in standaard:
            uit[r["sleutel"]] = json.loads(r["waarde"])
    return uit


def schrijf_instellingen(opslag: Opslag, waarden: dict[str, Any]) -> None:
    from .schema import INSTELLING

    opslag.voeg_toe(INSTELLING, [{"sleutel": k, "waarde": json.dumps(v)} for k, v in waarden.items()])
