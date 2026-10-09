"""Instellingen uit omgevingsvariabelen.

In Google Cloud staan alle wachtwoorden samen in één geheim (JSON) in Secret Manager,
doorgegeven als THUIS_GEHEIMEN. Eén geheim = binnen de gratis limiet van Secret Manager.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Amsterdam")

# Velden die vroeger alleen via het setup-script (in het geheim) gezet werden.
_OUDE_LOGINS = {
    "frank_email": "FRANK_EMAIL",
    "frank_wachtwoord": "FRANK_WACHTWOORD",
    "frank_site": "FRANK_SITE",
    "easee_gebruiker": "EASEE_GEBRUIKER",
    "easee_wachtwoord": "EASEE_WACHTWOORD",
    "easee_lader": "EASEE_LADER",
    "kia_gebruiker": "KIA_GEBRUIKER",
    "kia_wachtwoord": "KIA_WACHTWOORD",
    "kia_pin": "KIA_PIN",
    "kia_merk": "KIA_MERK",
    "chat_webhook": "GOOGLE_CHAT_WEBHOOK",
}


def _geheimen() -> dict[str, str]:
    try:
        return {k: str(v) for k, v in json.loads(os.environ.get("THUIS_GEHEIMEN") or "{}").items()}
    except json.JSONDecodeError as err:
        raise SystemExit("THUIS_GEHEIMEN is geen geldige JSON") from err


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or _geheimen().get(name) or default).strip()


def _lijst(name: str) -> list[str]:
    return [v.strip() for v in _env(name).split(",") if v.strip()]


@dataclass(frozen=True)
class Config:
    opslag: str = field(default_factory=lambda: _env("THUIS_OPSLAG", "duckdb"))  # duckdb | bigquery
    duckdb_pad: str = field(default_factory=lambda: _env("THUIS_DUCKDB_PAD", "thuis.duckdb"))
    gcp_project: str = field(default_factory=lambda: _env("GCP_PROJECT"))
    bq_dataset: str = field(default_factory=lambda: _env("BQ_DATASET", "thuis"))
    bq_locatie: str = field(default_factory=lambda: _env("BQ_LOCATIE", "EU"))
    # API-antwoorden bewaren tot de volgende ronde (bewaar.py). Standaard alleen bij BigQuery.
    bewaren: bool = field(
        default_factory=lambda: (
            _env("THUIS_BEWAREN", "1" if _env("THUIS_OPSLAG", "duckdb") == "bigquery" else "0") == "1"
        )
    )

    frank_email: str = field(default_factory=lambda: _env("FRANK_EMAIL"))
    frank_wachtwoord: str = field(default_factory=lambda: _env("FRANK_WACHTWOORD"))
    frank_site: str = field(default_factory=lambda: _env("FRANK_SITE"))

    easee_gebruiker: str = field(default_factory=lambda: _env("EASEE_GEBRUIKER"))
    easee_wachtwoord: str = field(default_factory=lambda: _env("EASEE_WACHTWOORD"))
    easee_lader: str = field(default_factory=lambda: _env("EASEE_LADER"))

    kia_gebruiker: str = field(default_factory=lambda: _env("KIA_GEBRUIKER"))
    kia_wachtwoord: str = field(default_factory=lambda: _env("KIA_WACHTWOORD"))
    kia_pin: str = field(default_factory=lambda: _env("KIA_PIN"))
    kia_merk: str = field(default_factory=lambda: _env("KIA_MERK", "kia"))  # kia | hyundai

    # Weer (Open-Meteo, geen account). Standaard De Bilt: het KNMI-station waar graaddagen
    # in Nederland mee worden gerekend.
    lat: float = field(default_factory=lambda: float(_env("THUIS_LAT", "52.10")))
    lon: float = field(default_factory=lambda: float(_env("THUIS_LON", "5.18")))

    # Meldingen in een Google Chat-ruimte via een inkomende webhook. Leeg = geen meldingen.
    chat_webhook: str = field(default_factory=lambda: _env("GOOGLE_CHAT_WEBHOOK"))

    # Inloggen regelt Identity-Aware Proxy (IAP) vóór Cloud Run. De app controleert daarnaast
    # het e-mailadres dat IAP doorgeeft tegen deze lijst. Leeg = iedereen die IAP doorlaat.
    toegestane_emails: list[str] = field(default_factory=lambda: _lijst("TOEGESTANE_EMAILS"))
    # Doelgroep van de IAP-JWT: /projects/NUMMER/locations/REGIO/services/thuis-app. Gezet =
    # de ondertekende JWT controleren (aanbevolen) in plaats van alleen de e-mailheader.
    iap_audience: str = field(default_factory=lambda: _env("IAP_AUDIENCE"))

    # De kluis met koppelingen (tokens): Secret Manager in de cloud, een bestand lokaal.
    kluis: str = field(
        default_factory=lambda: _env("THUIS_KLUIS")
    )  # secretmanager | bestand | leeg = automatisch
    kluis_pad: str = field(default_factory=lambda: _env("THUIS_KLUIS_PAD", "thuis-kluis.json"))
    geheim: str = field(default_factory=lambda: _env("THUIS_GEHEIM", "thuis-geheimen"))
    # Volledige naam van de verzamel-job (projects/…/locations/…/jobs/…): na het koppelen meteen een ronde.
    job: str = field(default_factory=lambda: _env("THUIS_JOB"))

    def met_geheimen(self, geheimen: dict[str, Any]) -> Config:
        """Oude logins (van het setup-script) uit de kluis aanvullen waar de omgeving niets zegt."""
        aanvulling = {
            veld: str(geheimen[sleutel]).strip()
            for veld, sleutel in _OUDE_LOGINS.items()
            if not os.environ.get(sleutel) and sleutel not in _geheimen() and geheimen.get(sleutel)
        }
        return replace(self, **aanvulling) if aanvulling else self

    # Alleen lokaal: zonder IAP-header werken. Nooit in Google Cloud zetten.
    auth_uit: bool = field(default_factory=lambda: _env("THUIS_AUTH_UIT") == "1")
    # Alleen lokaal: nagebootste Tuya-apparaten (demo.py) in plaats van de cloud van Tuya.
    demo_apparaten: bool = field(default_factory=lambda: _env("THUIS_DEMO_APPARATEN") == "1")

    @property
    def frank_login(self) -> bool:
        return bool(self.frank_email and self.frank_wachtwoord)

    @property
    def easee(self) -> bool:
        return bool(self.easee_gebruiker and self.easee_wachtwoord)

    @property
    def kia(self) -> bool:
        return bool(self.kia_gebruiker and self.kia_wachtwoord)
