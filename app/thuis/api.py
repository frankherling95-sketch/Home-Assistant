"""API + web-app. Draait in Google Cloud als Cloud Run-service achter Identity-Aware Proxy.

Lokaal: `THUIS_AUTH_UIT=1 uvicorn thuis.api:app --reload` en open http://localhost:8000
"""

from __future__ import annotations

import logging
import mimetypes
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi import Path as Pad
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, SecretStr

from . import ophalen
from .apparaten import Live, historie, verbruik_vandaag
from .auto import auto_overzicht, zet_thuis
from .bewaar import Bewaard, NietBewaard
from .config import Config
from .connectors import KoppelFout, KoppelingVerlopen
from .inzicht import dagen_grenzen, dagoverzicht, laatste, periodeoverzicht, vandaag
from .inzichten import inzichten
from .kluis import Kluis, maak_kluis, werk_bij
from .koppelingen import DIENSTEN, controleer_code, koppel, overzicht, start_code
from .laden import STANDAARD, maak_plan
from .opslag import Opslag, lees_instellingen, maak_opslag, nu, schrijf_instellingen, tegelijk
from .schema import TABELLEN
from .sessies import laadsessies

# In de container staat de web-app los van het geïnstalleerde pakket (THUIS_WEB=/app/web).
WEB = Path(os.environ.get("THUIS_WEB") or Path(__file__).resolve().parent.parent / "web")
IAP_HEADER = "x-goog-authenticated-user-email"
IAP_JWT_HEADER = "x-goog-iap-jwt-assertion"
IAP_SLEUTELS_URL = "https://www.gstatic.com/iap/verify/public_key"
IAP_UITGEVER = "https://cloud.google.com/iap"
# Windows geeft .js soms als text/plain door; de browser weigert dan de ES-modules.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/manifest+json", ".webmanifest")
_LOG = logging.getLogger(__name__)


@asynccontextmanager
async def _levensloop(app: FastAPI):
    app.state.cfg = Config()
    app.state.opslag = maak_opslag(app.state.cfg)
    app.state.kluis = maak_kluis(app.state.cfg)
    app.state.bewaard = Bewaard() if app.state.cfg.bewaren else NietBewaard()
    demo = None
    if app.state.cfg.demo_apparaten:
        from .demo_apparaten import DemoTuya as demo
    app.state.apparaten = Live(lambda: app.state.kluis.lees(), demo)  # de kluis van nu (tests vervangen hem)
    # BigQuery: de verzamelaar maakt de tabellen (ook direct na elke deploy); dat scheelt
    # hier tien API-aanroepen bij elke koude start.
    if app.state.cfg.opslag != "bigquery":
        app.state.opslag.maak_tabellen()
    yield


app = FastAPI(title="Thuis", lifespan=_levensloop, docs_url=None, redoc_url=None)
# Gecomprimeerd versturen: JSON en de web-app worden zo een paar keer kleiner (scheelt op mobiel).
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def _cache_regels(request: Request, call_next):
    """Web-app altijd hervalideren (ETag maakt dat goedkoop): na een deploy meteen de nieuwe versie.
    API-antwoorden niet in de browser of onderweg bewaren: daar zitten persoonlijke gegevens in.
    Een wijziging via de API (alles behalve GET) maakt de bewaarde antwoorden van de app leeg; een
    apparaat bedienen niet, want dat verandert niets aan wat de database weet."""
    antwoord = await call_next(request)
    pad = request.url.path
    if request.method != "GET" and pad.startswith("/api/") and not pad.startswith("/api/apparaten"):
        request.app.state.bewaard.leeg()
    antwoord.headers.setdefault(
        "Cache-Control", "no-store" if request.url.path.startswith("/api/") else "no-cache"
    )
    return antwoord


class IapSleutels:
    """Publieke sleutels waarmee IAP zijn JWT ondertekent; een uur bewaard, of opnieuw bij een onbekende sleutel."""

    def __init__(self) -> None:
        self._sleutels: dict[str, str] | None = None
        self._tijd = 0.0
        self._slot = threading.Lock()

    def __call__(self, vers: bool = False) -> dict[str, str]:
        with self._slot:
            if vers or self._sleutels is None or time.monotonic() - self._tijd > 3600:
                r = httpx.get(IAP_SLEUTELS_URL, timeout=10)
                r.raise_for_status()
                self._sleutels, self._tijd = r.json(), time.monotonic()
            return self._sleutels


iap_sleutels = IapSleutels()


def iap_email(token: str, audience: str) -> str:
    """E-mail uit de door IAP ondertekende JWT (ES256), na controle van handtekening, doelgroep en uitgever."""
    from google.auth import jwt

    try:
        claims = jwt.decode(token, certs=iap_sleutels(), audience=audience)
    except ValueError:  # sleutel net geroteerd: één keer vers ophalen
        claims = jwt.decode(token, certs=iap_sleutels(vers=True), audience=audience)
    if claims.get("iss") != IAP_UITGEVER:
        raise ValueError(f"Onverwachte uitgever {claims.get('iss')}")
    return str(claims["email"]).lower()


def gebruiker(request: Request) -> str:
    """E-mail van de ingelogde gebruiker volgens IAP.

    Met IAP_AUDIENCE (in Google Cloud) uit de ondertekende JWT, zoals Google aanraadt; anders
    uit de header "accounts.google.com:naam@domein". Daarna nog de eigen lijst TOEGESTANE_EMAILS.
    """
    cfg: Config = request.app.state.cfg
    email = request.headers.get(IAP_HEADER, "").split(":", 1)[-1].lower()
    if cfg.auth_uit:
        return email or "lokaal"
    if cfg.iap_audience:
        token = request.headers.get(IAP_JWT_HEADER)
        if not token:
            raise HTTPException(401, "Niet ingelogd (geen IAP)")
        try:
            email = iap_email(token, cfg.iap_audience)
        except Exception as err:  # noqa: BLE001 — elke fout betekent: niet vertrouwen
            _LOG.warning("IAP-JWT afgewezen: %s", err)
            raise HTTPException(401, "Ongeldige IAP-handtekening") from err
    if not email:
        raise HTTPException(401, "Niet ingelogd (geen IAP)")
    if cfg.toegestane_emails and email not in [e.lower() for e in cfg.toegestane_emails]:
        raise HTTPException(403, f"{email} heeft geen toegang")
    return email


def opslag(request: Request) -> Opslag:
    return request.app.state.opslag


def kluis(request: Request) -> Kluis:
    return request.app.state.kluis


def bewaard(request: Request, o: Opslag, maak: Callable[[], Any]) -> Any:
    """Het antwoord op dit verzoek, bewaard tot de volgende ronde (zie bewaar.py)."""
    vers = request.headers.get("x-thuis-vers") == "1"
    return request.app.state.bewaard.haal((request.url.path, request.url.query), o, maak, vers=vers)


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
    request: Request, datum: date | None = None, _: str = Depends(gebruiker), o: Opslag = Depends(opslag)
) -> dict[str, Any]:
    return bewaard(request, o, lambda: dagoverzicht(o, datum or vandaag()))


@app.get("/api/periode")
def api_periode(
    request: Request,
    soort: Literal["week", "maand", "jaar"] = Query(alias="type"),
    datum: date | None = None,
    _: str = Depends(gebruiker),
    o: Opslag = Depends(opslag),
) -> dict[str, Any]:
    return bewaard(request, o, lambda: periodeoverzicht(o, soort, datum or vandaag()))


@app.get("/api/laadsessies")
def api_laadsessies(
    request: Request,
    van: date | None = None,
    tot: date | None = None,
    _: str = Depends(gebruiker),
    o: Opslag = Depends(opslag),
) -> list[dict[str, Any]]:
    tot = tot or vandaag()
    van = van or tot - timedelta(days=30)
    if van > tot:
        raise HTTPException(422, "van ligt na tot")

    def maak() -> list[dict[str, Any]]:
        vermogen = float(lees_instellingen(o, STANDAARD)["vermogen_kw"])
        return [_json(s) for s in laadsessies(o, *dagen_grenzen(van, tot), vermogen)]

    return bewaard(request, o, maak)


@app.get("/api/inzichten")
def api_inzichten(
    request: Request, datum: date | None = None, _: str = Depends(gebruiker), o: Opslag = Depends(opslag)
) -> list[dict[str, str]]:
    return bewaard(request, o, lambda: inzichten(o, datum or vandaag()))


@app.get("/api/nu")
def api_nu(request: Request, _: str = Depends(gebruiker), o: Opslag = Depends(opslag)) -> dict[str, Any]:
    def maak() -> dict[str, Any]:
        instellingen, auto, lader = tegelijk(
            o,
            lambda: lees_instellingen(o, STANDAARD),
            lambda: laatste(o, "auto_meting"),
            lambda: laatste(o, "lader_meting"),
        )
        return {
            "tijd": nu().isoformat(),
            "auto": _json(auto),
            "lader": _json(lader),
            "plan": maak_plan(o, instellingen, auto=auto),
            "instellingen": instellingen,
        }

    return {**bewaard(request, o, maak), "tijd": nu().isoformat()}  # de tijd altijd van nu


@app.get("/api/auto")
def api_auto(request: Request, _: str = Depends(gebruiker), o: Opslag = Depends(opslag)) -> dict[str, Any]:
    """Alles over de auto voor de pagina Auto (zie docs/api.md)."""
    return bewaard(request, o, lambda: auto_overzicht(o))


@app.put("/api/auto/thuis")
def api_auto_thuis(_: str = Depends(gebruiker), o: Opslag = Depends(opslag)) -> dict[str, Any]:
    """Waar de auto nu staat, is thuis."""
    if not zet_thuis(o):
        raise HTTPException(409, "De auto heeft nog geen locatie doorgegeven.")
    return auto_overzicht(o)


@app.delete("/api/auto/thuis")
def api_auto_thuis_weg(_: str = Depends(gebruiker), o: Opslag = Depends(opslag)) -> dict[str, Any]:
    schrijf_instellingen(o, {"auto_thuis": None})
    return auto_overzicht(o)


@app.get("/api/instellingen")
def api_instellingen(_: str = Depends(gebruiker), o: Opslag = Depends(opslag)) -> dict[str, Any]:
    return lees_instellingen(o, STANDAARD)


@app.put("/api/instellingen")
def api_instellingen_opslaan(
    waarden: Instellingen, _: str = Depends(gebruiker), o: Opslag = Depends(opslag)
) -> dict[str, Any]:
    schrijf_instellingen(o, waarden.model_dump())
    return lees_instellingen(o, STANDAARD)


class KoppelGegevens(BaseModel):
    """Wat de gebruiker invult bij koppelen. Geheimen als SecretStr: nooit in logs of foutmeldingen."""

    email: str | None = Field(default=None, max_length=200)
    gebruiker: str | None = Field(default=None, max_length=200)
    merk: str | None = Field(default=None, pattern=r"^(kia|hyundai|genesis)$")
    wachtwoord: SecretStr | None = Field(default=None, max_length=200)
    webhook: SecretStr | None = Field(default=None, max_length=500)
    client_id: str | None = Field(default=None, pattern=r"^\s*[A-Za-z0-9-]{8,64}\s*$")
    regio: str | None = Field(default=None, pattern=r"^(eu|eu-w|us|us-e|in|cn)$")
    access_id: str | None = Field(default=None, pattern=r"^\s*[A-Za-z0-9]{10,64}\s*$")
    access_secret: SecretStr | None = Field(default=None, max_length=100)

    def als_dict(self) -> dict[str, str]:
        return {k: v.get_secret_value() if isinstance(v, SecretStr) else v for k, v in self if v is not None}


@app.get("/api/koppelingen")
def api_koppelingen(_: str = Depends(gebruiker), k: Kluis = Depends(kluis)) -> list[dict[str, Any]]:
    return overzicht(k.lees())


@contextmanager
def _dienstfouten(dienst: str) -> Iterator[None]:
    """KoppelFout: tekst voor de gebruiker (400). Al het andere: netwerk of een gewijzigde dienst (502)."""
    try:
        yield
    except KoppelFout as err:
        raise HTTPException(400, str(err)) from err
    except Exception as err:
        _LOG.exception("Koppelen met %s mislukt", dienst)
        raise HTTPException(
            502, f"{DIENSTEN[dienst]['naam']} gaf een onverwacht antwoord; probeer het later nog eens."
        ) from err


@app.post("/api/koppelingen/{dienst}")
def api_koppel(
    dienst: str,
    gegevens: KoppelGegevens,
    request: Request,
    _: str = Depends(gebruiker),
    k: Kluis = Depends(kluis),
) -> dict[str, Any]:
    """Eenmalig inloggen bij de dienst; alleen de tokens gaan de kluis in.

    BMW (methode "code"): geeft een code en een link; de app vraagt daarna met
    /controleer of de code op de site van BMW is bevestigd.
    """
    if dienst not in DIENSTEN:
        raise HTTPException(404, "Onbekende dienst")
    if DIENSTEN[dienst].get("methode") == "code":
        with _dienstfouten(dienst):
            wacht, code = start_code(dienst, gegevens.als_dict())
        werk_bij(k, wachtend={dienst: wacht})
        return {"code": code}
    with _dienstfouten(dienst):
        stand, bericht = koppel(dienst, gegevens.als_dict())
    data = werk_bij(k, {dienst: stand})
    request.app.state.apparaten.vergeet()
    start_ronde(request.app.state.cfg)
    return {"bericht": bericht, "koppelingen": overzicht(data)}


@app.post("/api/koppelingen/{dienst}/controleer")
def api_koppel_controleer(
    dienst: str, request: Request, _: str = Depends(gebruiker), k: Kluis = Depends(kluis)
) -> dict[str, Any]:
    """Is de code al bevestigd? {"wacht": true, "interval": s} of, als het gelukt is, als bij koppelen."""
    if DIENSTEN.get(dienst, {}).get("methode") != "code":
        raise HTTPException(404, "Onbekende dienst")
    wacht = (k.lees().get("wachtend") or {}).get(dienst)
    if not wacht:
        raise HTTPException(409, "Er loopt geen koppeling meer. Begin opnieuw met koppelen.")
    try:
        with _dienstfouten(dienst):
            uit = controleer_code(dienst, wacht)
    except HTTPException:
        werk_bij(k, wachtend={dienst: None})  # deze code werkt niet meer: opnieuw beginnen
        raise
    if uit is None:
        return {"wacht": True, "interval": wacht["interval"]}
    stand, bericht = uit
    data = werk_bij(k, {dienst: stand}, wachtend={dienst: None})
    start_ronde(request.app.state.cfg)
    return {"bericht": bericht, "koppelingen": overzicht(data)}


@app.delete("/api/koppelingen/{dienst}")
def api_ontkoppel(
    dienst: str, request: Request, _: str = Depends(gebruiker), k: Kluis = Depends(kluis)
) -> list[dict[str, Any]]:
    if dienst not in DIENSTEN:
        raise HTTPException(404, "Onbekende dienst")
    data = werk_bij(k, {dienst: None}, wachtend={dienst: None})
    request.app.state.apparaten.vergeet()
    return overzicht(data)


# ── apparaten (Tuya) ──────────────────────────────────────────────────────────

APPARAAT_ID = Pad(pattern=r"^[A-Za-z0-9_-]{4,64}$")


class Wens(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9_]{1,64}$")
    waarde: bool | int | float | str  # JSON true blijft bool, 1 blijft int (smart union van pydantic)


class Bediening(BaseModel):
    opdrachten: list[Wens] = Field(min_length=1, max_length=10)


@contextmanager
def _tuyafouten() -> Iterator[None]:
    """Fouten van Tuya als tekst voor de gebruiker: sleutels weg (409), Tuya zelf (502)."""
    from .connectors.tuya import TuyaFout

    try:
        yield
    except KoppelingVerlopen as err:
        raise HTTPException(
            409, f"De koppeling met Tuya werkt niet meer. {err.reden} Koppel opnieuw bij Koppelingen."
        ) from err
    except TuyaFout as err:
        raise HTTPException(502, err.uitleg) from err
    except httpx.HTTPError as err:
        _LOG.warning("Tuya niet bereikbaar: %s", err)
        raise HTTPException(502, "Tuya is niet bereikbaar; probeer het zo nog eens.") from err


@app.get("/api/apparaten")
def api_apparaten(request: Request, _: str = Depends(gebruiker)) -> dict[str, Any]:
    """De apparaten zoals Tuya ze nu meldt (live, hooguit 15 seconden oud; zie apparaten.Live)."""
    with _tuyafouten():
        return request.app.state.apparaten.lijst(vers=request.headers.get("x-thuis-vers") == "1")


@app.post("/api/apparaten/{apparaat_id}")
def api_bedien(
    body: Bediening, request: Request, apparaat_id: str = APPARAAT_ID, _: str = Depends(gebruiker)
) -> dict[str, Any]:
    """Een apparaat bedienen: {"opdrachten": [{"code": "switch_1", "waarde": true}]}."""
    try:
        with _tuyafouten():
            apparaat = request.app.state.apparaten.bedien(
                apparaat_id, [w.model_dump() for w in body.opdrachten]
            )
    except LookupError as err:
        raise HTTPException(409, str(err)) from err
    except ValueError as err:
        raise HTTPException(422, str(err)) from err
    return {"apparaat": apparaat}


@app.get("/api/apparaten/vandaag")
def api_apparaten_vandaag(
    request: Request, _: str = Depends(gebruiker), o: Opslag = Depends(opslag)
) -> dict[str, Any]:
    """Geschat verbruik en kosten per apparaat vandaag, uit de metingen van de verzamelaar."""
    return bewaard(request, o, lambda: verbruik_vandaag(o, vandaag()))


@app.get("/api/apparaten/{apparaat_id}/historie")
def api_apparaat_historie(
    request: Request,
    apparaat_id: str = APPARAAT_ID,
    dagen: int = Query(1, ge=1, le=7),
    _: str = Depends(gebruiker),
    o: Opslag = Depends(opslag),
) -> dict[str, Any]:
    def maak() -> dict[str, Any]:
        tot = nu()
        return historie(o, apparaat_id, tot - timedelta(days=dagen), tot)

    return bewaard(request, o, maak)


@app.post("/api/ophalen")
def api_ophalen(request: Request, _: str = Depends(gebruiker), k: Kluis = Depends(kluis)) -> dict[str, Any]:
    """Nu ophalen: meteen een ronde bij alle bronnen, ook de auto (zie ophalen.py en docs/api.md)."""
    cfg: Config = request.app.state.cfg
    if not cfg.job:
        raise HTTPException(409, "Nu ophalen kan alleen in Google Cloud. Lokaal: python -m thuis.verzamel")
    moment = nu()
    uit = ophalen.keuze(moment, ophalen.gevraagd(k.lees(), moment))
    if uit["actie"] in ("gestart", "gepland"):
        werk_bij(k, ophalen={"gevraagd": moment.isoformat()})  # vóór de start: de ronde leest het
    if uit["actie"] == "gestart" and not start_ronde(cfg):
        raise HTTPException(502, "De verzamelaar startte niet; probeer het straks nog eens.")
    return {sleutel: w.isoformat() if isinstance(w, datetime) else w for sleutel, w in uit.items()}


def start_ronde(cfg: Config) -> bool:
    """Meteen een ronde (na het koppelen, of met Nu ophalen). False: niet gelukt."""
    if not cfg.job:
        return False
    try:
        from .kluis import _google_token

        httpx.post(
            f"https://run.googleapis.com/v2/{cfg.job}:run",
            headers={"Authorization": f"Bearer {_google_token()}"},
            json={},
            timeout=15,
        ).raise_for_status()
    except Exception:  # noqa: BLE001 — dan komt het binnen een kwartier vanzelf
        _LOG.warning("Ronde niet gestart", exc_info=True)
        return False
    return True


HISTORIE = 8  # zoveel rondes per bron op de pagina Koppelingen

BRONNEN = (
    ("prijzen", "Frank Energie · prijzen"),
    ("verbruik", "Frank Energie · verbruik"),
    ("lader", "Easee"),
    ("auto", "{auto}"),
    ("bmw", "BMW CarData"),
    ("apparaten", "Tuya"),
    ("weer", "Open-Meteo"),
    ("sturen", "Slim laden"),
    ("meldingen", "Google Chat"),
)


@app.get("/api/status")
def api_status(
    request: Request, tabellen: bool = False, _: str = Depends(gebruiker), o: Opslag = Depends(opslag)
) -> dict[str, Any]:
    """Gezondheid per bron uit de rondelog; met `tabellen=true` ook wanneer elke tabel iets kreeg.

    De web-app vraagt dit elke paar minuten op. BigQuery rekent minimaal 10 MB per tabel per
    query, dus standaard één query op één tabel; de tabellen (9 queries) alleen op verzoek.
    """
    # De laatste HISTORIE uitslagen per stap in dezelfde query (zelfde tabel, dus geen extra kosten).
    per_stap: dict[str, list[dict[str, Any]]] = {}
    for r in o.lees(
        "SELECT stap, uitslag, tijd, laatst_ok, nr FROM ("
        "SELECT stap, uitslag, tijd, "
        "MAX(CASE WHEN uitslag = 'ok' THEN tijd END) OVER (PARTITION BY stap) AS laatst_ok, "
        "ROW_NUMBER() OVER (PARTITION BY stap ORDER BY tijd DESC) AS nr "
        "FROM {ronde} WHERE tijd >= @sinds) WHERE nr <= @n",
        sinds=nu() - timedelta(days=30),
        n=HISTORIE,
    ):
        per_stap.setdefault(r["stap"], []).append(r)
    for rijen in per_stap.values():
        rijen.sort(key=lambda r: r["nr"])
    rondes = {stap: rijen[0] for stap, rijen in per_stap.items()}
    merk = request.app.state.cfg.kia_merk.lower()
    auto = {"hyundai": "Hyundai Bluelink", "genesis": "Genesis Connected"}.get(merk, "Kia Connect")
    bronnen = []
    for stap, naam in BRONNEN:
        r = rondes.get(stap) or {}
        bronnen.append(
            {
                "stap": stap,
                "naam": naam.format(auto=auto),
                "uitslag": r.get("uitslag"),
                "tijd": _iso(r.get("tijd")),
                "laatst_ok": _iso(r.get("laatst_ok")),
                # oudste eerst
                "historie": [
                    {"tijd": _iso(h["tijd"]), "uitslag": h["uitslag"]}
                    for h in reversed(per_stap.get(stap, []))
                ],
            }
        )
    # Wat de app al weet over de laatste ronde: bewaarde antwoorden van een oudere ronde vervallen.
    tijden = [r["tijd"] for r in rondes.values() if r.get("tijd") is not None]
    request.app.state.bewaard.zet_ronde(max(tijden).isoformat() if tijden else None)
    uit: dict[str, Any] = {"bronnen": bronnen}
    if tabellen:
        laatst = tegelijk(
            o, *[lambda t=t: o.lees(f"SELECT MAX(opgehaald) AS laatst FROM {{{t.naam}}}") for t in TABELLEN]
        )
        uit["tabellen"] = {
            t.naam: _iso(rij[0]["laatst"]) if rij else None for t, rij in zip(TABELLEN, laatst, strict=True)
        }
    return uit


def _iso(v: Any) -> str | None:
    return v.isoformat() if v is not None else None


def _json(rij: dict[str, Any] | None) -> dict[str, Any] | None:
    if rij is None:
        return None
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in rij.items()}


# De web-app zelf. Achter IAP: wie de pagina ziet, is al ingelogd.
if WEB.is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
