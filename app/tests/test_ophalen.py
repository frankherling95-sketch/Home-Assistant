from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from thuis import api as api_mod
from thuis.kluis import GeheugenKluis
from thuis.ophalen import gevraagd, keuze

KWARTIER = datetime(2026, 10, 9, 16, 45, tzinfo=UTC)  # 18:45 in Nederland: de geplande ronde start


def na(s: float) -> datetime:
    return KWARTIER + timedelta(seconds=s)


def test_keuze_blijft_uit_de_buurt_van_de_geplande_ronde():
    assert keuze(na(30)) == {"actie": "wacht", "wacht_s": 90}  # de geplande ronde loopt nog
    assert keuze(na(120)) == {"actie": "gestart", "vanaf": na(120)}
    assert keuze(na(779)) == {"actie": "gestart", "vanaf": na(779)}
    assert keuze(na(780)) == {"actie": "gepland", "vanaf": na(780)}  # de volgende begint zo
    assert keuze(na(899)) == {"actie": "gepland", "vanaf": na(899)}


def test_nog_eens_drukken_is_dezelfde_ronde():
    assert keuze(na(400), vorige=na(300)) == {"actie": "bezig", "vanaf": na(300)}
    assert keuze(na(905), vorige=na(800)) == {"actie": "bezig", "vanaf": na(800)}  # ook binnen "wacht"
    assert keuze(na(500), vorige=na(300))["actie"] == "gestart"


def test_gevraagd_uit_de_kluis():
    kluis = {"ophalen": {"gevraagd": na(300).isoformat()}}
    assert gevraagd(kluis, na(330)) == na(300)
    assert gevraagd(kluis, na(300 + 11 * 60)) is None  # te oud: telt niet meer
    assert gevraagd({}, na(330)) is None
    assert gevraagd({"ophalen": {"gevraagd": "gisteren"}}, na(330)) is None


# ── API ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_met_job(monkeypatch, tmp_path):
    monkeypatch.setenv("THUIS_DUCKDB_PAD", str(tmp_path / "o.duckdb"))
    monkeypatch.setenv("THUIS_AUTH_UIT", "1")
    gestart = []
    monkeypatch.setattr(api_mod, "start_ronde", lambda cfg: gestart.append(cfg.job) or True)
    with TestClient(api_mod.app) as c:
        c.app.state.kluis = GeheugenKluis()
        c.app.state.cfg = replace(
            c.app.state.cfg, job="projects/p/locations/europe-west4/jobs/thuis-verzamel"
        )
        c.gestart = gestart
        yield c


def test_api_ophalen_start_een_ronde(app_met_job, monkeypatch):
    c = app_met_job
    monkeypatch.setattr(api_mod, "nu", lambda: na(300))
    assert c.post("/api/ophalen").json() == {"actie": "gestart", "vanaf": na(300).isoformat()}
    assert c.gestart == ["projects/p/locations/europe-west4/jobs/thuis-verzamel"]
    assert c.app.state.kluis.data["ophalen"] == {"gevraagd": na(300).isoformat()}

    # Nog eens drukken (of een tweede telefoon): geen tweede ronde.
    monkeypatch.setattr(api_mod, "nu", lambda: na(340))
    assert c.post("/api/ophalen").json() == {"actie": "bezig", "vanaf": na(300).isoformat()}
    assert len(c.gestart) == 1 and c.app.state.kluis.schrijfacties == 1


def test_api_ophalen_rond_het_kwartier(app_met_job, monkeypatch):
    c = app_met_job
    monkeypatch.setattr(api_mod, "nu", lambda: na(30))
    assert c.post("/api/ophalen").json() == {"actie": "wacht", "wacht_s": 90}
    assert "ophalen" not in c.app.state.kluis.data  # de lopende ronde moet het niet oppikken
    monkeypatch.setattr(api_mod, "nu", lambda: na(800))
    assert c.post("/api/ophalen").json()["actie"] == "gepland"
    assert c.gestart == [] and c.app.state.kluis.data["ophalen"] == {"gevraagd": na(800).isoformat()}


def test_api_ophalen_zonder_job_of_als_starten_mislukt(app_met_job, monkeypatch):
    c = app_met_job
    monkeypatch.setattr(api_mod, "nu", lambda: na(300))
    monkeypatch.setattr(api_mod, "start_ronde", lambda cfg: False)
    assert c.post("/api/ophalen").status_code == 502
    c.app.state.cfg = replace(c.app.state.cfg, job="")
    r = c.post("/api/ophalen")
    assert r.status_code == 409 and "Google Cloud" in r.json()["detail"]
