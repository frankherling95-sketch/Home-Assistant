"""API + web-app. Draait in Google Cloud als Cloud Run-service achter Identity-Aware Proxy.

Lokaal: `THUIS_AUTH_UIT=1 uvicorn thuis.api:app --reload` en open http://localhost:8000
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import TZ, Config
from .inzicht import dagoverzicht, laatste
from .laden import STANDAARD, maak_plan
from .opslag import Opslag, lees_instellingen, maak_opslag, nu, schrijf_instellingen
from .schema import TABELLEN

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
    return dagoverzicht(o, datum or nu().astimezone(TZ).date())


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


@app.get("/api/status")
def api_status(_: str = Depends(gebruiker), o: Opslag = Depends(opslag)) -> dict[str, Any]:
    """Wanneer elke bron voor het laatst iets opleverde: snel zien of een connector stilvalt."""
    uit = {}
    for t in TABELLEN:
        rij = o.lees(f"SELECT MAX(opgehaald) AS laatst FROM {{{t.naam}}}")
        uit[t.naam] = rij[0]["laatst"].isoformat() if rij and rij[0]["laatst"] else None
    return uit


def _json(rij: dict[str, Any] | None) -> dict[str, Any] | None:
    if rij is None:
        return None
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in rij.items()}


# De web-app zelf. Achter IAP: wie de pagina ziet, is al ingelogd.
if WEB.is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
