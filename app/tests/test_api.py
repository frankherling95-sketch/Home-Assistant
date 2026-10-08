import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from thuis import api as api_mod
from thuis.config import TZ
from thuis.demo import vul
from thuis.opslag import DuckOpslag, nu
from thuis.schema import RONDE

GISTEREN = nu().astimezone(TZ).date() - timedelta(days=1)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv("THUIS_DUCKDB_PAD", str(tmp_path_factory.mktemp("api") / "t.duckdb"))
    mp.setenv("TOEGESTANE_EMAILS", "frank@herling.nl")
    mp.delenv("THUIS_AUTH_UIT", raising=False)
    with TestClient(api_mod.app) as c:
        vul(c.app.state.opslag, rond=GISTEREN, dagen=40)  # volle dagen, los van het tijdstip van de test
        yield c
    mp.undo()


IAP = {"x-goog-authenticated-user-email": "accounts.google.com:Frank@Herling.nl"}


def test_zonder_iap_geen_toegang(client):
    assert client.get("/api/dag").status_code == 401
    assert (
        client.get("/api/dag", headers={"x-goog-authenticated-user-email": "x:ander@x.nl"}).status_code == 403
    )
    assert client.get("/api/periode?type=week").status_code == 401


def test_dag_en_nu(client):
    dag = client.get(f"/api/dag?datum={GISTEREN}", headers=IAP).json()
    assert len(dag["uren"]) in (23, 24, 25)
    t = dag["totalen"]
    assert t["stroom"]["hoeveelheid"] > 0 and t["gas"]["eenheid"] == "m³"
    assert 12 <= t["laden"]["hoeveelheid"] <= t["stroom"]["hoeveelheid"]  # laden zit in de netafname
    assert (
        len(dag["reeksen"]["temperatuur"]) == len(dag["uren"]) and None not in dag["reeksen"]["temperatuur"]
    )
    nu_ = client.get("/api/nu", headers=IAP).json()
    assert nu_["lader"]["naam"] == "Oprit" and nu_["auto"]["naam"] == "EV6"
    assert "blokken" in nu_["plan"]


@pytest.mark.parametrize(("soort", "n"), [("week", 7), ("maand", None), ("jaar", 12)])
def test_periode(client, soort, n):
    p = client.get(f"/api/periode?type={soort}&datum={GISTEREN}", headers=IAP).json()
    assert len(p["bakjes"]) == len(p["bakje_labels"]) == (n or len(p["bakjes"]))
    assert all(len(v) == len(p["bakjes"]) for v in p["reeksen"].values())
    assert p["totalen"]["stroom"]["hoeveelheid"] > 0 and set(p["vorige"]) == set(p["totalen"])
    assert p["van"] <= GISTEREN.isoformat() <= p["tot"]


def test_periode_onbekend_type(client):
    assert client.get("/api/periode?type=decennium", headers=IAP).status_code == 422


def test_laadsessies_nieuwste_eerst(client):
    sessies = client.get("/api/laadsessies", headers=IAP).json()
    assert sessies and sessies == sorted(sessies, key=lambda s: s["start"], reverse=True)
    s = sessies[0]
    assert set(s) >= {"lader_id", "start", "eind", "kwh", "kosten", "gem_prijs", "slim", "klaar", "besparing"}
    assert s["kwh"] > 0 and s["slim"] is True
    van = (GISTEREN + timedelta(days=5)).isoformat()
    assert client.get(f"/api/laadsessies?van={van}&tot={GISTEREN}", headers=IAP).status_code == 422


def test_inzichten(client):
    uit = client.get(f"/api/inzichten?datum={GISTEREN}", headers=IAP).json()
    ids = [i["id"] for i in uit]
    assert "negatieve_prijzen" in ids and "kosten_maand" in ids and "gas_vs_vorige_week" in ids
    assert all(set(i) == {"id", "titel", "waarde", "toelichting", "toon", "icoon"} for i in uit)


def test_status_uit_rondelog(client):
    o = client.app.state.opslag
    t = nu()
    o.voeg_toe(
        RONDE, [{"tijd": t - timedelta(minutes=15), "stap": "prijzen", "uitslag": "ok", "duur_s": 1.0}]
    )
    o.voeg_toe(RONDE, [{"tijd": t, "stap": "prijzen", "uitslag": "fout: HTTP 502", "duur_s": 0.4}])
    s = client.get("/api/status", headers=IAP).json()
    bronnen = {b["stap"]: b for b in s["bronnen"]}
    assert list(bronnen) == ["prijzen", "verbruik", "lader", "auto", "weer", "sturen", "meldingen"]
    assert bronnen["prijzen"]["uitslag"] == "fout: HTTP 502" and bronnen["prijzen"]["tijd"] == t.isoformat()
    assert (t - timedelta(minutes=15)).isoformat() <= bronnen["prijzen"]["laatst_ok"] < t.isoformat()
    assert bronnen["meldingen"]["uitslag"] == "overgeslagen" and bronnen["auto"]["naam"] == "Kia Connect"
    assert s["tabellen"]["prijs"] and s["tabellen"]["melding"] is None


def test_demo_lokaal_zonder_login(monkeypatch, tmp_path):
    monkeypatch.setenv("THUIS_DUCKDB_PAD", str(tmp_path / "d.duckdb"))
    monkeypatch.setenv("THUIS_AUTH_UIT", "1")
    with TestClient(api_mod.app) as c:
        assert c.get("/api/gebruiker").json() == {"email": "lokaal"}
        assert isinstance(c.app.state.opslag, DuckOpslag)


def test_demo_van_400_dagen_is_snel():
    o = DuckOpslag(":memory:")
    o.maak_tabellen()
    begin = time.monotonic()
    vul(o)
    assert time.monotonic() - begin < 30
    dagen = o.lees(
        "SELECT COUNT(DISTINCT CAST(timezone('Europe/Amsterdam', van) AS DATE)) AS n FROM {verbruik}"
    )
    assert dagen[0]["n"] == 401
    assert o.lees("SELECT MIN(allin) AS p FROM {prijs} WHERE soort = 'stroom'")[0]["p"] < 0
