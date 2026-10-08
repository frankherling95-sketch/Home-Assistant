"""API + web-app. Draait in Google Cloud als Cloud Run-service achter Identity-Aware Proxy.

Lokaal: `THUIS_AUTH_UIT=1 uvicorn thuis.api:app --reload` en open http://localhost:8000
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import Config
from .inzicht import dagen_grenzen, dagoverzicht, laatste, periodeoverzicht, vandaag
from .inzichten import inzichten
from .laden import STANDAARD, maak_plan
from .opslag import Opslag, lees_instellingen, maak_opslag, nu, schrijf_instellingen
from .schema import TABELLEN
from .sessies import laadsessies

# In de container staat de web-app los van het geïnstalleerde pakket (THUIS_WEB=/app/web).
WEB = Path(os.environ.get("THUIS_WEB") or Path(__file__).resolve().parent.parent / "web")
IAP_HEADER = "x-goog-authenticated-user-email"


@asynccontextmanager
async def _levensloop(app: FastAPI):
    app.state.cfg = Config()
    app.state.opslag = maak_opslag(app.state.cfg)
    app.state.opslag.maak_tabellen()
    yield


app = FastAPI(title="Thuis", lifespan=_levensloop, docs_url=None, redoc_url=None)


def gebruiker(request: Request) -> str:
    """E-mail van de ingelogde gebruiker, zoals IAP die doorgeeft ("accounts.google.com:naam@domein")."""
    cfg: Config = request.app.state.cfg
    waarde = request.headers.get(IAP_HEADER, "")
    email = waarde.split(":", 1)[-1].lower()
    if cfg.auth_uit:
        return email or "lokaal"
    if not email:
        raise HTTPException(401, "Niet ingelogd (geen IAP)")
    if cfg.toegestane_emails and email not in [e.lower() for e in cfg.toegestane_emails]:
        raise HTTPException(403, f"{email} heeft geen toegang")
    return email


def opslag(request: Request) -> Opslag:
    return request.app.state.opslag


class Instellingen(BaseModel):
    doel_pct: float = Field(ge=10, le=100)
    vertrek: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    capaciteit_kwh: float = Field(gt=5, le=200)
    vermogen_kw: float = Field(gt=1, le=22)
    rendement_pct: float = Field(ge=50, le=100)
    altijd_onder: float = Field(ge=-1, le=1)
    sturen: bool


@app.get("/api/gebruiker")
def api_gebruiker(email: str = Depends(gebruiker)) -> dict[str, str]:
    return {"email": email}


@app.get("/api/dag")
def api_dag(
    datum: date | None = None, _: str = Depends(gebruiker), o: Opslag = Depends(opslag)
) -> dict[str, Any]:
    return dagoverzicht(o, datum or vandaag())


@app.get("/api/periode")
def api_periode(
    soort: Literal["week", "maand", "jaar"] = Query(alias="type"),
    datum: date | None = None,
    _: str = Depends(gebruiker),
    o: Opslag = Depends(opslag),
) -> dict[str, Any]:
    return periodeoverzicht(o, soort, datum or vandaag())


@app.get("/api/laadsessies")
def api_laadsessies(
    van: date | None = None, tot: date | None = None, _: str = Depends(gebruiker), o: Opslag = Depends(opslag)
) -> list[dict[str, Any]]:
    tot = tot or vandaag()
    van = van or tot - timedelta(days=30)
    if van > tot:
        raise HTTPException(422, "van ligt na tot")
    vermogen = float(lees_instellingen(o, STANDAARD)["vermogen_kw"])
    return [_json(s) for s in laadsessies(o, *dagen_grenzen(van, tot), vermogen)]


@app.get("/api/inzichten")
def api_inzichten(
    datum: date | None = None, _: str = Depends(gebruiker), o: Opslag = Depends(opslag)
) -> list[dict[str, str]]:
    return inzichten(o, datum or vandaag())


@app.get("/api/nu")
def api_nu(_: str = Depends(gebruiker), o: Opslag = Depends(opslag)) -> dict[str, Any]:
    instellingen = lees_instellingen(o, STANDAARD)
    auto, lader = laatste(o, "auto_meting"), laatste(o, "lader_meting")
    return {
        "tijd": nu().isoformat(),
        "auto": _json(auto),
        "lader": _json(lader),
        "plan": maak_plan(o, instellingen),
        "instellingen": instellingen,
    }


@app.get("/api/instellingen")
def api_instellingen(_: str = Depends(gebruiker), o: Opslag = Depends(opslag)) -> dict[str, Any]:
    return lees_instellingen(o, STANDAARD)


@app.put("/api/instellingen")
def api_instellingen_opslaan(
    waarden: Instellingen, _: str = Depends(gebruiker), o: Opslag = Depends(opslag)
) -> dict[str, Any]:
    schrijf_instellingen(o, waarden.model_dump())
    return lees_instellingen(o, STANDAARD)


BRONNEN = (
    ("prijzen", "Frank Energie · prijzen"),
    ("verbruik", "Frank Energie · verbruik"),
    ("lader", "Easee"),
    ("auto", "{auto}"),
    ("weer", "Open-Meteo"),
    ("sturen", "Slim laden"),
    ("meldingen", "Google Chat"),
)


@app.get("/api/status")
def api_status(request: Request, _: str = Depends(gebruiker), o: Opslag = Depends(opslag)) -> dict[str, Any]:
    """Gezondheid per bron uit de rondelog, en wanneer elke tabel voor het laatst iets kreeg."""
    sinds = nu() - timedelta(days=30)
    laatste_ronde = {
        r["stap"]: r
        for r in o.lees(
            "SELECT stap, uitslag, tijd FROM {ronde} WHERE tijd >= @sinds "
            "QUALIFY ROW_NUMBER() OVER (PARTITION BY stap ORDER BY tijd DESC) = 1",
            sinds=sinds,
        )
    }
    laatst_ok = {
        r["stap"]: r["tijd"]
        for r in o.lees(
            "SELECT stap, MAX(tijd) AS tijd FROM {ronde} WHERE tijd >= @sinds AND uitslag = 'ok' GROUP BY stap",
            sinds=sinds,
        )
    }
    merk = request.app.state.cfg.kia_merk.lower()
    auto = {"hyundai": "Hyundai Bluelink", "genesis": "Genesis Connected"}.get(merk, "Kia Connect")
    bronnen = []
    for stap, naam in BRONNEN:
        r = laatste_ronde.get(stap) or {}
        bronnen.append(
            {
                "stap": stap,
                "naam": naam.format(auto=auto),
                "uitslag": r.get("uitslag"),
                "tijd": _iso(r.get("tijd")),
                "laatst_ok": _iso(laatst_ok.get(stap)),
            }
        )
    tabellen = {}
    for t in TABELLEN:
        rij = o.lees(f"SELECT MAX(opgehaald) AS laatst FROM {{{t.naam}}}")
        tabellen[t.naam] = _iso(rij[0]["laatst"]) if rij else None
    return {"bronnen": bronnen, "tabellen": tabellen}


def _iso(v: Any) -> str | None:
    return v.isoformat() if v is not None else None


def _json(rij: dict[str, Any] | None) -> dict[str, Any] | None:
    if rij is None:
        return None
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in rij.items()}


# De web-app zelf. Achter IAP: wie de pagina ziet, is al ingelogd.
if WEB.is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
