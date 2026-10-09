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
    mp.setenv("TOEGESTANE_EMAILS", "frank@voorbeeld.nl")
    mp.delenv("THUIS_AUTH_UIT", raising=False)
    with TestClient(api_mod.app) as c:
        vul(c.app.state.opslag, rond=GISTEREN, dagen=40)  # volle dagen, los van het tijdstip van de test
        yield c
    mp.undo()


IAP = {"x-goog-authenticated-user-email": "accounts.google.com:Frank@Voorbeeld.nl"}


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
    assert nu_["lader"]["naam"] == "Oprit" and nu_["auto"]["naam"] == "BMW i4 eDrive40"
    assert "blokken" in nu_["plan"]


@pytest.mark.parametrize(("soort", "n"), [("week", 7), ("maand", None), ("jaar", 12)])
def test_periode(client, soort, n):
    p = client.get(f"/api/periode?type={soort}&datum={GISTEREN}", headers=IAP).json()
    assert len(p["bakjes"]) == len(p["bakje_labels"]) == (n or len(p["bakjes"]))
    assert all(len(v) == len(p["bakjes"]) for v in p["reeksen"].values())
    r = p["reeksen"]
    assert all(
        k is None or abs(k - (s + g)) < 0.02
        for k, s, g in zip(r["kosten"], r["kosten_stroom"], r["kosten_gas"], strict=True)
        if k is not None
    )
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
    assert "tabellen" not in client.get("/api/status", headers=IAP).json()  # standaard één query
    s = client.get("/api/status?tabellen=true", headers=IAP).json()
    bronnen = {b["stap"]: b for b in s["bronnen"]}
    assert list(bronnen) == [
        "prijzen",
        "verbruik",
        "lader",
        "auto",
        "bmw",
        "apparaten",
        "weer",
        "sturen",
        "meldingen",
    ]
    assert bronnen["prijzen"]["uitslag"] == "fout: HTTP 502" and bronnen["prijzen"]["tijd"] == t.isoformat()
    assert (t - timedelta(minutes=15)).isoformat() <= bronnen["prijzen"]["laatst_ok"] < t.isoformat()
    historie = [h["uitslag"] for h in bronnen["prijzen"]["historie"]]
    assert len(historie) <= 8 and historie[-2:] == ["ok", "fout: HTTP 502"]  # oudste eerst
    assert bronnen["meldingen"]["uitslag"] == "overgeslagen" and bronnen["auto"]["naam"] == "Kia Connect"
    assert s["tabellen"]["prijs"] and s["tabellen"]["melding"] is None


def test_iap_jwt_wordt_gecontroleerd(monkeypatch, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from google.auth import jwt
    from google.auth.crypt import es256

    sleutel = ec.generate_private_key(ec.SECP256R1())
    prive = sleutel.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    publiek = (
        sleutel.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    monkeypatch.setattr(api_mod, "iap_sleutels", lambda vers=False: {"k1": publiek})
    aud = "/projects/123/locations/europe-west4/services/thuis-app"
    monkeypatch.setenv("IAP_AUDIENCE", aud)
    monkeypatch.setenv("TOEGESTANE_EMAILS", "frank@voorbeeld.nl")
    monkeypatch.setenv("THUIS_DUCKDB_PAD", str(tmp_path / "j.duckdb"))
    monkeypatch.delenv("THUIS_AUTH_UIT", raising=False)
    nu_ = int(time.time())

    def token(**claims):
        basis = {
            "iss": "https://cloud.google.com/iap",
            "aud": aud,
            "email": "frank@voorbeeld.nl",
            "iat": nu_,
            "exp": nu_ + 600,
        }
        return jwt.encode(es256.ES256Signer.from_string(prive, key_id="k1"), {**basis, **claims}).decode()

    with TestClient(api_mod.app) as c:

        def email(t, kop=None):
            return c.get("/api/gebruiker", headers={"x-goog-iap-jwt-assertion": t, **(kop or {})})

        assert email(token()).json() == {"email": "frank@voorbeeld.nl"}
        assert email(token(aud="/projects/999/x")).status_code == 401  # andere service
        assert email(token(iss="https://evil.example")).status_code == 401
        assert email(token(email="ander@x.nl")).status_code == 403
        # Alleen de header (zonder geldige JWT) is niet genoeg meer.
        assert (
            c.get(
                "/api/gebruiker", headers={"x-goog-authenticated-user-email": "x:frank@voorbeeld.nl"}
            ).status_code
            == 401
        )


def test_web_app_met_juiste_types(client):
    index = client.get("/")
    assert index.status_code == 200 and 'src="js/app.js"' in index.text
    assert client.get("/js/app.js").headers["content-type"].startswith("text/javascript")
    assert client.get("/manifest.webmanifest").headers["content-type"].startswith("application/manifest+json")
    assert client.get("/icons/icon-192.png").headers["content-type"] == "image/png"
    assert index.headers["cache-control"] == "no-cache"  # na een deploy meteen de nieuwe versie
    assert client.get("/api/gebruiker", headers=IAP).headers["cache-control"] == "no-store"


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
