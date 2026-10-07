from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from thuis import api as api_mod
from thuis.config import TZ
from thuis.demo import vul
from thuis.opslag import DuckOpslag, nu

GISTEREN = nu().astimezone(TZ).date() - timedelta(days=1)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("THUIS_DUCKDB_PAD", str(tmp_path / "t.duckdb"))
    monkeypatch.setenv("TOEGESTANE_EMAILS", "frank@herling.nl")
    monkeypatch.delenv("THUIS_AUTH_UIT", raising=False)
    with TestClient(api_mod.app) as c:
        vul(c.app.state.opslag, rond=GISTEREN)  # volledige dag, los van het tijdstip van de test
        yield c


IAP = {"x-goog-authenticated-user-email": "accounts.google.com:Frank@Herling.nl"}


def test_zonder_iap_geen_toegang(client):
    assert client.get("/api/dag").status_code == 401
    assert (
        client.get("/api/dag", headers={"x-goog-authenticated-user-email": "x:ander@x.nl"}).status_code == 403
    )


def test_dag_en_nu(client):
    dag = client.get(f"/api/dag?datum={GISTEREN}", headers=IAP).json()
    assert len(dag["uren"]) in (23, 24, 25)
    assert dag["totalen"]["stroom"]["hoeveelheid"] > 0
    assert dag["totalen"]["laden"]["hoeveelheid"] == pytest.approx(32.4, abs=0.1)
    nu = client.get("/api/nu", headers=IAP).json()
    assert nu["lader"]["naam"] == "Oprit" and nu["auto"]["naam"] == "EV6"
    assert "blokken" in nu["plan"]


def test_instellingen_valideren_en_opslaan(client):
    std = client.get("/api/instellingen", headers=IAP).json()
    assert client.put("/api/instellingen", headers=IAP, json={**std, "vertrek": "25:00"}).status_code == 422
    nieuw = client.put("/api/instellingen", headers=IAP, json={**std, "doel_pct": 90}).json()
    assert nieuw["doel_pct"] == 90


def test_status(client):
    s = client.get("/api/status", headers=IAP).json()
    assert s["prijs"] and s["stuuractie"] is None


def test_demo_lokaal_zonder_login(monkeypatch, tmp_path):
    monkeypatch.setenv("THUIS_DUCKDB_PAD", str(tmp_path / "d.duckdb"))
    monkeypatch.setenv("THUIS_AUTH_UIT", "1")
    with TestClient(api_mod.app) as c:
        assert c.get("/api/gebruiker").json() == {"email": "lokaal"}
        assert isinstance(c.app.state.opslag, DuckOpslag)
