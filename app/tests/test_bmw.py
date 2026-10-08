import base64
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from thuis import api as api_mod
from thuis.config import Config
from thuis.connectors import KoppelFout, KoppelingVerlopen
from thuis.connectors import bmw as bmw_mod
from thuis.connectors.bmw import API, AUTH, BMW, BmwFout, naar_rij
from thuis.kluis import GeheugenKluis
from thuis.verzamel import ronde

VIN = "WBY31AW090FP12345"
NU = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def _formulier(verzoek) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(verzoek.content.decode()).items()}


def _record(**extra):
    return {
        "client_id": "94fc6954-0000-0000-0000-000000000000",
        "tokens": {"access_token": "A1", "refresh_token": "R1", "verloopt": time.time() + 3600},
        "vin": VIN,
        "naam": "BMW i4 eDrive40",
        "container_id": "C1",
        **extra,
    }


def _telematisch(**waarden):
    return {
        "telematicData": {
            k: {"value": v, "unit": "", "timestamp": "2026-10-08T11:55:00Z"} for k, v in waarden.items()
        }
    }


LAADT = _telematisch(
    **{
        bmw_mod.ACCU[0]: "64",
        bmw_mod.BEREIK[0]: "301",
        bmw_mod.STEKKER: "true",
        bmw_mod.LAADSTATUS: "CHARGINGACTIVE",
    }
)

# ── koppelen ──────────────────────────────────────────────────────────────────


@respx.mock
def test_start_koppeling_vraagt_code_met_pkce():
    route = respx.post(f"{AUTH}/device/code").mock(
        return_value=httpx.Response(
            200,
            json={
                "user_code": "ABCD-EFGH",
                "device_code": "D1",
                "interval": 5,
                "expires_in": 300,
                "verification_uri": "https://customer.bmwgroup.com/oneid/link",
                "verification_uri_complete": "https://customer.bmwgroup.com/oneid/link?code=ABCD-EFGH",
            },
        )
    )
    wacht, toon = bmw_mod.start_koppeling("cid")
    verzonden = _formulier(route.calls[0].request)
    assert verzonden["client_id"] == "cid" and verzonden["response_type"] == "device_code"
    assert verzonden["scope"] == "authenticate_user openid cardata:api:read"
    challenge = base64.urlsafe_b64encode(hashlib.sha256(wacht["code_verifier"].encode()).digest())
    assert verzonden["code_challenge"] == challenge.decode().rstrip("=")
    assert verzonden["code_challenge_method"] == "S256"
    assert toon["code"] == "ABCD-EFGH" and toon["link"].endswith("code=ABCD-EFGH")
    assert "code_verifier" not in toon and "device_code" not in toon  # blijft op de server
    assert wacht["device_code"] == "D1" and wacht["verloopt"] > time.time()


@respx.mock
def test_start_koppeling_met_onbekende_client_id():
    respx.post(f"{AUTH}/device/code").mock(return_value=httpx.Response(400, json={"error": "invalid_client"}))
    with pytest.raises(KoppelFout, match="client-ID"):
        bmw_mod.start_koppeling("onbekend")


def _wacht(**extra):
    return {
        "client_id": "cid",
        "device_code": "D1",
        "code_verifier": "V1",
        "interval": 5,
        "verloopt": time.time() + 300,
        **extra,
    }


@respx.mock
def test_controleer_koppeling_wacht_en_vertraagt():
    respx.post(f"{AUTH}/token").mock(
        side_effect=[
            httpx.Response(400, json={"error": "authorization_pending"}),
            httpx.Response(400, json={"error": "slow_down"}),
            httpx.Response(400, json={"error": "access_denied"}),
        ]
    )
    wacht = _wacht()
    assert bmw_mod.controleer_koppeling(wacht) is None
    assert bmw_mod.controleer_koppeling(wacht) is None and wacht["interval"] == 10
    with pytest.raises(KoppelFout, match="geweigerd"):
        bmw_mod.controleer_koppeling(wacht)
    with pytest.raises(KoppelFout, match="verlopen"):
        bmw_mod.controleer_koppeling(_wacht(verloopt=time.time() - 1))


@respx.mock
def test_controleer_koppeling_zoekt_auto_en_maakt_container():
    token = respx.post(f"{AUTH}/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "A1", "refresh_token": "R1", "id_token": "I", "expires_in": 3600}
        )
    )
    respx.get(f"{API}/customers/vehicles/mappings").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"vin": "WBA00000000000001", "mappingType": "SECONDARY"},
                {"vin": VIN, "mappingType": "PRIMARY"},
            ],
        )
    )
    respx.get(f"{API}/customers/vehicles/{VIN}/basicData").mock(
        return_value=httpx.Response(200, json={"brand": "BMW", "modelName": "i4 eDrive40"})
    )
    respx.get(f"{API}/customers/containers").mock(
        return_value=httpx.Response(
            200,
            json={
                "containers": [
                    {
                        "containerId": "OUD",
                        "name": "Thuis",
                        "purpose": "Thuis energieplatform v0",
                        "state": "ACTIVE",
                    },
                    {"containerId": "ANDER", "name": "Iets anders", "purpose": "x", "state": "ACTIVE"},
                ]
            },
        )
    )
    weg = respx.delete(f"{API}/customers/containers/OUD").mock(return_value=httpx.Response(204))
    maak = respx.post(f"{API}/customers/containers").mock(
        return_value=httpx.Response(201, json={"containerId": "NIEUW", "state": "ACTIVE"})
    )
    r = bmw_mod.controleer_koppeling(_wacht())
    verzonden = _formulier(token.calls[0].request)
    assert verzonden["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"
    assert verzonden["code_verifier"] == "V1" and verzonden["device_code"] == "D1"
    assert r["vin"] == VIN and r["naam"] == "BMW i4 eDrive40" and r["account"] == "BMW i4 eDrive40"
    assert r["container_id"] == "NIEUW" and weg.called  # de oude versie van Thuis gaat weg, de andere niet
    body = json.loads(maak.calls[0].request.content)
    assert body["name"] == "Thuis" and set(body["technicalDescriptors"]) == set(bmw_mod.DESCRIPTORS)
    assert maak.calls[0].request.headers["x-version"] == "v1"
    assert maak.calls[0].request.headers["authorization"] == "Bearer A1"
    assert "id_token" not in json.dumps(r) and len(r["vragen"]) == 5  # telt mee voor het dagmaximum


@respx.mock
def test_controleer_koppeling_zonder_eigen_auto():
    respx.post(f"{AUTH}/token").mock(
        return_value=httpx.Response(200, json={"access_token": "A1", "refresh_token": "R1"})
    )
    respx.get(f"{API}/customers/vehicles/mappings").mock(
        return_value=httpx.Response(200, json=[{"vin": VIN, "mappingType": "SECONDARY"}])
    )
    with pytest.raises(KoppelFout, match="hoofdgebruiker"):
        bmw_mod.controleer_koppeling(_wacht())


# ── uitlezen ──────────────────────────────────────────────────────────────────


@respx.mock
def test_metingen_ververst_token_en_leest_de_auto():
    ververs = respx.post(f"{AUTH}/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "A2", "refresh_token": "R2", "expires_in": 3600}
        )
    )
    lees = respx.get(f"{API}/customers/vehicles/{VIN}/telematicData").mock(
        return_value=httpx.Response(200, json=LAADT)
    )
    b = BMW(_record(tokens={"access_token": "A1", "refresh_token": "R1", "verloopt": 0}))
    [rij] = b.metingen(NU)
    assert _formulier(ververs.calls[0].request) == {
        "grant_type": "refresh_token",
        "refresh_token": "R1",
        "client_id": "94fc6954-0000-0000-0000-000000000000",
    }
    assert lees.calls[0].request.url.params["containerId"] == "C1"
    assert lees.calls[0].request.headers["authorization"] == "Bearer A2"
    assert rij["auto_id"] == VIN and rij["naam"] == "BMW i4 eDrive40"
    assert rij["accu_pct"] == 64 and rij["bereik_km"] == 301 and rij["ingeplugd"] and rij["laadt"]
    assert rij["bijgewerkt"] == datetime(2026, 10, 8, 11, 55, tzinfo=UTC)
    assert b.gewijzigd and b.record["tokens"]["refresh_token"] == "R2"  # nieuw refresh-token bewaren
    assert b.record["toestand"] == {"laadt": True, "ingeplugd": True} and b.record["laatst"] == NU.isoformat()


@respx.mock
def test_geweigerd_refresh_token_is_verlopen():
    respx.post(f"{AUTH}/token").mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(KoppelingVerlopen, match="BMW"):
        BMW(_record(tokens={"access_token": "A1", "refresh_token": "R1", "verloopt": 0})).metingen(NU)


@respx.mock
def test_verdwenen_container_wordt_opnieuw_gemaakt():
    url = f"{API}/customers/vehicles/{VIN}/telematicData"
    respx.get(url).mock(
        side_effect=[
            httpx.Response(
                403, json={"exveErrorId": "CU-105", "exveErrorMsg": "No permission for containerId"}
            ),
            httpx.Response(200, json=LAADT),
        ]
    )
    respx.get(f"{API}/customers/containers").mock(return_value=httpx.Response(200, json={"containers": []}))
    respx.post(f"{API}/customers/containers").mock(
        return_value=httpx.Response(201, json={"containerId": "C2"})
    )
    b = BMW(_record())
    assert b.metingen(NU)[0]["laadt"] and b.record["container_id"] == "C2"


@respx.mock
def test_dagmaximum_van_bmw_pauzeert():
    respx.get(f"{API}/customers/vehicles/{VIN}/telematicData").mock(
        return_value=httpx.Response(
            429, json={"exveErrorId": "CU-429", "exveErrorMsg": "API rate limit reached"}
        )
    )
    b = BMW(_record())
    with pytest.raises(BmwFout, match="50 verzoeken"):
        b.metingen(NU)
    assert not b.aan_de_beurt(datetime.now(UTC) + timedelta(hours=1))


def test_hoe_vaak_de_auto_gevraagd_wordt():
    nu_ = datetime.now(UTC)

    def wacht(toestand, gedaan=0):
        vragen = [nu_.timestamp() - 60 * i for i in range(gedaan)]
        return BMW(_record(toestand=toestand, vragen=vragen)).wachttijd(nu_)

    assert wacht({"laadt": True, "ingeplugd": True}) == timedelta(minutes=15)
    assert wacht({"laadt": False, "ingeplugd": True}) == timedelta(minutes=30)
    assert wacht({}) == timedelta(minutes=60)
    assert wacht({"laadt": True}, gedaan=35) == timedelta(minutes=60)  # zuinig als het krap wordt
    assert wacht({"laadt": True}, gedaan=45) is None  # nooit meer dan 45 per 24 uur
    # Verzoeken van meer dan 24 uur geleden tellen niet meer.
    oud = BMW(_record(vragen=[nu_.timestamp() - 90000] * 45))
    assert oud.wachttijd(nu_) == timedelta(minutes=60) and oud.record["vragen"] == []

    b = BMW(_record(toestand={"laadt": True}, laatst=(nu_ - timedelta(minutes=14, seconds=30)).isoformat()))
    assert b.aan_de_beurt(nu_)  # de volgende ronde, ook al start die een halve minuut te vroeg
    b.record["laatst"] = (nu_ - timedelta(minutes=5)).isoformat()
    assert not b.aan_de_beurt(nu_) and b.metingen(nu_) == []  # niet aan de beurt: geen verzoek


def test_naar_rij_met_terugvallers_en_mijlen():
    data = _telematisch(
        **{
            bmw_mod.ACCU[0]: "INVALID",
            bmw_mod.ACCU[1]: "81.5",
            bmw_mod.BEREIK[0]: "100",
            bmw_mod.LAADPOORT: "DISCONNECTED",
            bmw_mod.HV_STATUS: "NOT_CHARGING",
        }
    )["telematicData"]
    data[bmw_mod.BEREIK[0]]["unit"] = "mi"
    rij = naar_rij(VIN, "BMW iX", data, NU)
    assert rij["accu_pct"] == 81.5 and rij["bereik_km"] == 160.9
    assert rij["ingeplugd"] is False and rij["laadt"] is False
    leeg = naar_rij(VIN, "BMW iX", {}, NU)
    assert leeg["accu_pct"] is None and leeg["ingeplugd"] is None and leeg["bijgewerkt"] is None


# ── verzamelaar en API ────────────────────────────────────────────────────────


class NepPrijzen:
    def prijzen(self, start, eind):
        return []


class NepWeer:
    def temperaturen(self, terug, vooruit):
        return []


@respx.mock
def test_ronde_leest_bmw_en_bewaart_de_stand(opslag, monkeypatch):
    for k in ("FRANK_EMAIL", "EASEE_GEBRUIKER", "KIA_GEBRUIKER", "GOOGLE_CHAT_WEBHOOK", "THUIS_GEHEIMEN"):
        monkeypatch.delenv(k, raising=False)
    respx.post(f"{AUTH}/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "A2", "refresh_token": "R2", "expires_in": 3600}
        )
    )
    lees = respx.get(f"{API}/customers/vehicles/{VIN}/telematicData").mock(
        return_value=httpx.Response(200, json=LAADT)
    )
    kluis = GeheugenKluis(
        {"koppelingen": {"bmw": {**_record(tokens={"refresh_token": "R1"}), "status": "ok", "account": "x"}}}
    )
    uitslag = ronde(Config(), opslag, frank=NepPrijzen(), weer=NepWeer(), kluis=kluis)
    assert uitslag["bmw"] == "ok" and uitslag["auto"] == "overgeslagen"
    rijen = opslag.lees("SELECT auto_id, accu_pct, laadt FROM {auto_meting}")
    assert rijen == [{"auto_id": VIN, "accu_pct": 64.0, "laadt": True}]
    bewaard = kluis.data["koppelingen"]["bmw"]
    assert bewaard["tokens"]["refresh_token"] == "R2" and len(bewaard["vragen"]) == 1
    assert bewaard["status"] == "ok" and bewaard["account"] == "x"

    # Een kwartier later niet opnieuw als de vorige ronde net was: de rij komt pas de ronde erna.
    ronde(Config(), opslag, frank=NepPrijzen(), weer=NepWeer(), kluis=kluis)
    assert lees.call_count == 1


@pytest.fixture
def app_met_kluis(monkeypatch, tmp_path):
    monkeypatch.setenv("THUIS_DUCKDB_PAD", str(tmp_path / "b.duckdb"))
    monkeypatch.setenv("THUIS_AUTH_UIT", "1")
    with TestClient(api_mod.app) as c:
        c.app.state.kluis = GeheugenKluis()
        yield c


def test_api_koppelen_met_code(app_met_kluis, monkeypatch):
    c = app_met_kluis
    antwoorden = iter(
        [None, {"vin": VIN, "naam": "BMW i4", "account": "BMW i4", "bericht": "Auto gevonden: BMW i4"}]
    )
    monkeypatch.setattr(
        bmw_mod,
        "start_koppeling",
        lambda client_id: (
            {
                "client_id": client_id,
                "device_code": "D1",
                "code_verifier": "GEHEIM",
                "interval": 5,
                "verloopt": 0,
            },
            {"code": "ABCD", "link": "https://bmw", "interval": 5, "verloopt": "2026-10-08T12:05:00+00:00"},
        ),
    )
    monkeypatch.setattr(bmw_mod, "controleer_koppeling", lambda wacht: next(antwoorden))

    assert c.post("/api/koppelingen/bmw", json={"client_id": "x/../../y"}).status_code == 422
    assert c.post("/api/koppelingen/bmw/controleer").status_code == 409  # nog niets gestart
    r = c.post("/api/koppelingen/bmw", json={"client_id": " 94fc6954-fc4d-4175-8168-67e2a4c5cf15 "})
    assert r.status_code == 200 and r.json() == {
        "code": {
            "code": "ABCD",
            "link": "https://bmw",
            "interval": 5,
            "verloopt": "2026-10-08T12:05:00+00:00",
        }
    }
    assert c.app.state.kluis.data["wachtend"]["bmw"]["client_id"] == "94fc6954-fc4d-4175-8168-67e2a4c5cf15"
    assert c.post("/api/koppelingen/bmw/controleer").json() == {"wacht": True, "interval": 5}
    r = c.post("/api/koppelingen/bmw/controleer").json()
    assert r["bericht"] == "Auto gevonden: BMW i4"
    bmw = {d["dienst"]: d for d in r["koppelingen"]}["bmw"]
    assert bmw["status"] == "ok" and bmw["account"] == "BMW i4" and bmw["methode"] == "code"
    assert c.app.state.kluis.data["wachtend"] == {} and "GEHEIM" not in json.dumps(r)
    assert c.post("/api/koppelingen/easee/controleer").status_code == 404


def test_api_gestopte_code_moet_opnieuw(app_met_kluis, monkeypatch):
    c = app_met_kluis
    c.app.state.kluis.data = {"wachtend": {"bmw": _wacht()}}

    def geweigerd(wacht):
        raise KoppelFout("Het koppelen is bij BMW geweigerd of afgebroken. Begin opnieuw met koppelen.")

    monkeypatch.setattr(bmw_mod, "controleer_koppeling", geweigerd)
    r = c.post("/api/koppelingen/bmw/controleer")
    assert r.status_code == 400 and "geweigerd" in r.json()["detail"]
    assert c.app.state.kluis.data["wachtend"] == {}
