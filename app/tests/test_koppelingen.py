import base64
import json
import sys
import time
import types
from datetime import datetime

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from thuis import api as api_mod
from thuis.config import Config
from thuis.connectors import KoppelFout, KoppelingVerlopen
from thuis.connectors import easee as easee_mod
from thuis.connectors.easee import Easee
from thuis.connectors.frank import URL as FRANK_URL
from thuis.connectors.frank import Frank
from thuis.kluis import SECRET_API, BestandKluis, GeheugenKluis, SecretKluis, werk_bij
from thuis.koppelingen import overzicht
from thuis.verzamel import ronde

# ── kluis ─────────────────────────────────────────────────────────────────────


def test_werk_bij_voegt_samen_en_verwijdert():
    k = GeheugenKluis({"FRANK_EMAIL": "a@b.nl", "koppelingen": {"easee": {"x": 1}, "kia": {"y": 2}}})
    werk_bij(k, {"easee": {"x": 3}, "kia": None, "frank": {"z": 4}})
    assert k.data == {"FRANK_EMAIL": "a@b.nl", "koppelingen": {"easee": {"x": 3}, "frank": {"z": 4}}}


def test_bestandkluis(tmp_path):
    k = BestandKluis(str(tmp_path / "kluis.json"))
    assert k.lees() == {}
    k.schrijf({"koppelingen": {"a": 1}})
    assert BestandKluis(str(tmp_path / "kluis.json")).lees() == {"koppelingen": {"a": 1}}


@respx.mock
def test_secretkluis_leest_schrijft_en_ruimt_oude_versies_op():
    naam = "projects/p/secrets/thuis-geheimen"
    data = base64.b64encode(json.dumps({"koppelingen": {"a": 1}}).encode()).decode()
    respx.get(f"{SECRET_API}/{naam}/versions/latest:access").mock(
        return_value=httpx.Response(200, json={"payload": {"data": data}})
    )
    toevoegen = respx.post(f"{SECRET_API}/{naam}:addVersion").mock(
        return_value=httpx.Response(200, json={"name": f"{naam}/versions/7"})
    )
    respx.get(f"{SECRET_API}/{naam}/versions").mock(
        return_value=httpx.Response(
            200, json={"versions": [{"name": f"{naam}/versions/{v}"} for v in (5, 7, 6)]}
        )
    )
    weg = respx.post(f"{SECRET_API}/{naam}/versions/5:destroy").mock(
        return_value=httpx.Response(200, json={})
    )
    k = SecretKluis("p", "thuis-geheimen", token=lambda: "T")
    assert k.lees() == {"koppelingen": {"a": 1}}
    k.schrijf({"koppelingen": {"a": 2}})
    verzonden = json.loads(toevoegen.calls[0].request.content)
    assert json.loads(base64.b64decode(verzonden["payload"]["data"])) == {"koppelingen": {"a": 2}}
    assert toevoegen.calls[0].request.headers["authorization"] == "Bearer T"
    assert weg.called  # 7 en 6 blijven, 5 gaat weg


# ── Easee ─────────────────────────────────────────────────────────────────────


@respx.mock
def test_easee_ververst_verlopen_token_en_bewaart_de_nieuwe():
    ververs = respx.post(f"{easee_mod.URL}/api/accounts/refresh_token").mock(
        return_value=httpx.Response(200, json={"accessToken": "A2", "refreshToken": "R2", "expiresIn": 3600})
    )
    lijst = respx.get(f"{easee_mod.URL}/api/chargers").mock(
        return_value=httpx.Response(200, json=[{"id": "EH1", "name": "Oprit"}])
    )
    e = Easee(tokens={"access_token": "A1", "refresh_token": "R1", "verloopt": time.time() - 10})
    assert e.laders() == [{"id": "EH1", "naam": "Oprit"}]
    assert json.loads(ververs.calls[0].request.content) == {"accessToken": "A1", "refreshToken": "R1"}
    assert lijst.calls[0].request.headers["authorization"] == "Bearer A2"
    assert e.gewijzigd and e.tokens["refresh_token"] == "R2" and e.tokens["verloopt"] > time.time()


@respx.mock
def test_easee_zonder_wachtwoord_en_geweigerde_refresh_is_verlopen():
    respx.post(f"{easee_mod.URL}/api/accounts/refresh_token").mock(return_value=httpx.Response(400))
    with pytest.raises(KoppelingVerlopen, match="Easee"):
        Easee(tokens={"access_token": "A", "refresh_token": "R", "verloopt": 0}).laders()


@respx.mock
def test_easee_koppelen():
    respx.post(f"{easee_mod.URL}/api/accounts/login").mock(
        side_effect=[
            httpx.Response(401),
            httpx.Response(200, json={"accessToken": "A", "refreshToken": "R", "expiresIn": 3600}),
        ]
    )
    respx.get(f"{easee_mod.URL}/api/chargers").mock(
        return_value=httpx.Response(200, json=[{"id": "EH1", "name": "Oprit"}])
    )
    with pytest.raises(KoppelFout, match="controleer"):
        Easee.koppel("a@b.nl", "fout")
    r = Easee.koppel("a@b.nl", "goed")
    assert r["tokens"]["access_token"] == "A" and "goed" not in json.dumps(r) and "Oprit" in r["bericht"]


# ── Frank Energie ─────────────────────────────────────────────────────────────


def _jwt(exp: float) -> str:
    deel = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"kop.{deel}.handtekening"


@respx.mock
def test_frank_vernieuwt_bijna_verlopen_token_zonder_wachtwoord():
    oud, nieuw = _jwt(time.time() + 60), _jwt(time.time() + 3600)
    route = respx.post(FRANK_URL)
    route.side_effect = [
        httpx.Response(200, json={"data": {"renewToken": {"authToken": nieuw, "refreshToken": "R2"}}}),
        httpx.Response(200, json={"data": {"periodUsageAndCosts": {}}}),
    ]
    f = Frank(site="S1", tokens={"auth_token": oud, "refresh_token": "R1"})
    assert f.verbruik(datetime(2026, 10, 7).date()) == []
    vernieuw = json.loads(route.calls[0].request.content)
    assert "renewToken" in vernieuw["query"] and vernieuw["variables"] == {
        "authToken": oud,
        "refreshToken": "R1",
    }
    assert "authorization" not in route.calls[0].request.headers
    assert route.calls[1].request.headers["authorization"] == f"Bearer {nieuw}"
    assert f.gewijzigd and f.tokens == {"auth_token": nieuw, "refresh_token": "R2"}


@respx.mock
def test_frank_geweigerde_vernieuwing_is_verlopen():
    respx.post(FRANK_URL).mock(
        return_value=httpx.Response(200, json={"errors": [{"message": "Invalid refresh token"}]})
    )
    f = Frank(site="S1", tokens={"auth_token": _jwt(time.time() - 10), "refresh_token": "R1"})
    with pytest.raises(KoppelingVerlopen, match="Frank Energie"):
        f.verbruik(datetime(2026, 10, 7).date())


@respx.mock
def test_frank_koppelen():
    route = respx.post(FRANK_URL)
    route.side_effect = [
        httpx.Response(200, json={"data": {"login": {"authToken": "T", "refreshToken": "R"}}}),
        httpx.Response(200, json={"data": {"userSites": [{"reference": "S1", "status": "IN_DELIVERY"}]}}),
    ]
    r = Frank.koppel("a@b.nl", "geheim")
    assert r["tokens"] == {"auth_token": "T", "refresh_token": "R"} and r["site"] == "S1"
    assert "geheim" not in json.dumps(r)


# ── Kia (met een nagebootste bibliotheek) ─────────────────────────────────────


@pytest.fixture
def nep_kia(monkeypatch):
    class Token:
        def __init__(self, **d):
            self.d = d

        @classmethod
        def from_dict(cls, d):
            return cls(**d)

        def to_dict(self):
            return dict(self.d)

    class VehicleManager:
        gedrag = "ververs"

        def __init__(self, region, brand, username, password, pin, language, token=None):
            self.password, self.token, self.vehicles = password, token, {}

        def check_and_refresh_token(self):
            if self.gedrag == "fout":
                raise RuntimeError("AuthenticationError")
            if self.token is None:
                self.token = Token(username="k@b.nl", password=self.password, pin="", refresh_token="R1")
            else:
                self.token = Token(**{**self.token.d, "refresh_token": "R2"})
            self.vehicles = {"1": types.SimpleNamespace(id="1", name="EV6")}
            return True

        def update_all_vehicles_with_cached_state(self):
            pass

    module = types.ModuleType("hyundai_kia_connect_api")
    module.Token, module.VehicleManager = Token, VehicleManager
    monkeypatch.setitem(sys.modules, "hyundai_kia_connect_api", module)
    return VehicleManager


def test_kia_koppelen_bewaart_token_zonder_wachtwoord(nep_kia):
    from thuis.connectors.kia import Kia

    r = Kia.koppel("k@b.nl", "geheim", "kia")
    assert r["token"]["refresh_token"] == "R1" and r["token"]["password"] == "" and "EV6" in r["bericht"]
    k = Kia(merk="kia", token=r["token"])
    k.metingen()
    assert k.gewijzigd and k.tokens["refresh_token"] == "R2" and k.tokens["password"] == ""
    nep_kia.gedrag = "fout"
    with pytest.raises(KoppelingVerlopen, match="Kia Connect"):
        Kia(merk="kia", token=r["token"]).metingen()


# ── overzicht en verzamelaar ──────────────────────────────────────────────────


def test_overzicht_toont_status_zonder_geheimen():
    data = {
        "FRANK_EMAIL": "frank@herling.nl",
        "FRANK_WACHTWOORD": "oud",
        "koppelingen": {
            "easee": {"tokens": {"access_token": "GEHEIM"}, "account": "+31612345678", "status": "opnieuw"},
            "kia": {
                "token": {"refresh_token": "GEHEIM"},
                "account": "kia@x.nl",
                "status": "ok",
                "gekoppeld": "2026-10-08T12:00:00+00:00",
            },
        },
    }
    uit = {d["dienst"]: d for d in overzicht(data)}
    assert uit["frank"]["status"] == "script" and uit["frank"]["account"] == "fr…@herling.nl"
    assert uit["easee"]["status"] == "opnieuw" and uit["easee"]["account"] == "+316…78"
    assert uit["kia"]["status"] == "ok" and uit["google_chat"]["status"] == "niet"
    assert "GEHEIM" not in json.dumps(uit) and "oud" not in json.dumps(uit)


class NepPrijzen:
    def prijzen(self, start, eind):
        return []


class NepWeer:
    def temperaturen(self, terug, vooruit):
        return []


@respx.mock
def test_ronde_bewaart_verse_tokens_en_markeert_verlopen(opslag, monkeypatch):
    for k in ("FRANK_EMAIL", "EASEE_GEBRUIKER", "KIA_GEBRUIKER", "GOOGLE_CHAT_WEBHOOK", "THUIS_GEHEIMEN"):
        monkeypatch.delenv(k, raising=False)
    respx.post(f"{easee_mod.URL}/api/accounts/refresh_token").mock(
        return_value=httpx.Response(200, json={"accessToken": "A2", "refreshToken": "R2", "expiresIn": 3600})
    )
    respx.get(f"{easee_mod.URL}/api/chargers").mock(
        return_value=httpx.Response(200, json=[{"id": "EH1", "name": "Oprit"}])
    )
    respx.get(f"{easee_mod.URL}/api/chargers/EH1/state").mock(
        return_value=httpx.Response(
            200, json={"chargerOpMode": 1, "totalPower": 0, "sessionEnergy": 0, "lifetimeEnergy": 10}
        )
    )
    easee = {
        "tokens": {"access_token": "A1", "refresh_token": "R1", "verloopt": 0},
        "account": "e",
        "status": "opnieuw",
    }
    kluis = GeheugenKluis({"koppelingen": {"easee": easee}})
    uitslag = ronde(Config(), opslag, frank=NepPrijzen(), weer=NepWeer(), kluis=kluis)
    assert uitslag["lader"] == "ok" and uitslag["verbruik"] == "overgeslagen"
    bewaard = kluis.data["koppelingen"]["easee"]
    assert bewaard["tokens"]["refresh_token"] == "R2" and bewaard["status"] == "ok"

    respx.post(f"{easee_mod.URL}/api/accounts/refresh_token").mock(return_value=httpx.Response(400))
    kluis.data["koppelingen"]["easee"]["tokens"]["verloopt"] = 0
    uitslag = ronde(Config(), opslag, frank=NepPrijzen(), weer=NepWeer(), kluis=kluis)
    assert "koppeling met Easee verlopen" in uitslag["lader"]
    assert kluis.data["koppelingen"]["easee"]["status"] == "opnieuw"


# ── API ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_met_kluis(monkeypatch, tmp_path):
    monkeypatch.setenv("THUIS_DUCKDB_PAD", str(tmp_path / "k.duckdb"))
    monkeypatch.setenv("THUIS_AUTH_UIT", "1")
    with TestClient(api_mod.app) as c:
        c.app.state.kluis = GeheugenKluis()
        yield c


def test_api_koppelen_bewaart_alleen_wat_koppel_teruggeeft(app_met_kluis, monkeypatch):
    c = app_met_kluis
    gezien = {}

    def nep_koppel(dienst, gegevens):
        gezien.update(gegevens)
        if gegevens["wachtwoord"] == "fout":
            raise KoppelFout("Inloggen bij Easee mislukt: controleer je gegevens.")
        return {
            "tokens": {"access_token": "A"},
            "account": gegevens["gebruiker"],
            "status": "ok",
            "gekoppeld": "nu",
        }, "Laders gevonden: Oprit"

    monkeypatch.setattr(api_mod, "koppel", nep_koppel)
    r = c.post("/api/koppelingen/easee", json={"gebruiker": "a@b.nl", "wachtwoord": "fout"})
    assert r.status_code == 400 and "controleer" in r.json()["detail"]
    r = c.post("/api/koppelingen/easee", json={"gebruiker": "a@b.nl", "wachtwoord": "geheim123"})
    assert r.status_code == 200 and r.json()["bericht"] == "Laders gevonden: Oprit"
    assert gezien["wachtwoord"] == "geheim123"
    assert "geheim123" not in json.dumps(c.app.state.kluis.data)  # wachtwoord komt de kluis niet in
    lijst = {d["dienst"]: d for d in c.get("/api/koppelingen").json()}
    assert lijst["easee"]["status"] == "ok" and "access_token" not in json.dumps(lijst)
    assert c.delete("/api/koppelingen/easee").status_code == 200
    assert "easee" not in c.app.state.kluis.data["koppelingen"]


def test_api_echoot_geen_wachtwoord_bij_fouten(app_met_kluis):
    r = app_met_kluis.post(
        "/api/koppelingen/kia", json={"merk": "tesla", "gebruiker": "x", "wachtwoord": "supergeheim"}
    )
    assert r.status_code == 422 and "supergeheim" not in r.text
    assert app_met_kluis.post("/api/koppelingen/onbekend", json={}).status_code == 404


def test_config_vult_oude_logins_aan_uit_de_kluis(monkeypatch):
    monkeypatch.delenv("FRANK_EMAIL", raising=False)
    monkeypatch.delenv("THUIS_GEHEIMEN", raising=False)
    monkeypatch.setenv("EASEE_GEBRUIKER", "omgeving")
    cfg = Config().met_geheimen({"FRANK_EMAIL": "kluis@x.nl", "EASEE_GEBRUIKER": "kluis"})
    assert cfg.frank_email == "kluis@x.nl" and cfg.easee_gebruiker == "omgeving"
