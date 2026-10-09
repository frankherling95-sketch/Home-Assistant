import json
from datetime import timedelta

import httpx
import pytest
import respx
from conftest import blokken, utc
from fastapi.testclient import TestClient

from thuis import api as api_mod
from thuis.apparaten import Live, historie, maak, meting, opdracht, verbruik_vandaag
from thuis.config import Config
from thuis.connectors import KoppelFout, KoppelingVerlopen
from thuis.connectors.tuya import REGIO, Tuya, TuyaFout, compact, onderteken
from thuis.demo_apparaten import DemoTuya
from thuis.kluis import GeheugenKluis
from thuis.koppelingen import overzicht
from thuis.schema import APPARAAT, PRIJS
from thuis.verzamel import ronde

URL = REGIO["eu"]
RECORD = {"regio": "eu", "access_id": "ab12cd34ef56gh78ij90", "access_secret": "S" * 32}


def ok(result):
    return httpx.Response(200, json={"success": True, "result": result, "t": 1})


def fout(code, msg="fout"):
    return httpx.Response(200, json={"success": False, "code": code, "msg": msg, "t": 1})


TOKEN = ok({"access_token": "T1", "expire_time": 7200, "refresh_token": "R1", "uid": "u"})
STEKKER = {
    "id": "st1",
    "name": "Wasmachine",
    "category": "cz",
    "online": True,
    "product_name": "Stekker",
    "status": [
        {"code": "switch_1", "value": True},
        {"code": "cur_power", "value": 4862},
        {"code": "cur_current", "value": 2190},
        {"code": "add_ele", "value": 128},
        {"code": "relay_status", "value": "last"},
    ],
}
SPEC_STEKKER = {
    "category": "cz",
    "functions": [
        {"code": "switch_1", "type": "Boolean", "values": "{}"},
        {"code": "relay_status", "type": "Enum", "values": '{"range":["power_off","power_on","last"]}'},
        {
            "code": "countdown_1",
            "type": "Integer",
            "values": '{"unit":"s","min":0,"max":86400,"scale":0,"step":1}',
        },
    ],
    "status": [
        {"code": "switch_1", "type": "Boolean", "values": "{}"},
        {
            "code": "cur_power",
            "type": "Integer",
            "values": '{"unit":"W","min":0,"max":99999,"scale":1,"step":1}',
        },
        {
            "code": "cur_current",
            "type": "Integer",
            "values": '{"unit":"mA","min":0,"max":30000,"scale":0,"step":1}',
        },
        {
            "code": "add_ele",
            "type": "Integer",
            "values": '{"unit":"kwh","min":0,"max":50000,"scale":3,"step":100}',
        },
        {"code": "colour_data", "type": "Json", "values": "{}"},
    ],
}


# ── handtekening ──────────────────────────────────────────────────────────────


def test_handtekening_volgens_de_voorbeelden_van_tuya():
    """De twee rekenvoorbeelden van https://developer.tuya.com/en/docs/iot/new-singnature."""
    koppen = {"area_id": "29a33e8796834b1efa6", "call_id": "8afdb70ab2ed11eb85290242ac130003"}
    gemeen = {
        "client_id": "1KAD46OrT9HafiKdsXeg",
        "geheim": "4OHBOnWOqaEC1mWXOpVL3yV50s0qGSRC",
        "methode": "GET",
        "t": "1588925778000",
        "nonce": "5138cc3a9033d69856923fd07b491173",
        "koppen": koppen,
    }
    assert (
        onderteken(pad="/v1.0/token?grant_type=1", **gemeen)
        == "9E48A3E93B302EEECC803C7241985D0A34EB944F40FB573C7B5C2A82158AF13E"
    )
    assert (
        onderteken(
            pad="/v2.0/apps/schema/users?page_no=1&page_size=50",
            token="3f4eda2bdec17232f67c0b188af3eec1",
            **gemeen,
        )
        == "AE4481C692AA80B25F3A7E12C3A5FD9BBF6251539DD78E565A1A72A508A88784"
    )


@respx.mock
def test_tuya_vraagt_token_en_ondertekent_elk_verzoek():
    token = respx.get(f"{URL}/v1.0/token", params={"grant_type": "1"}).mock(return_value=TOKEN)
    lijst = respx.get(f"{URL}/v1.0/iot-01/associated-users/devices").mock(
        return_value=ok({"devices": [STEKKER], "has_more": False, "last_row_key": "x"})
    )
    t = Tuya(dict(RECORD), klok=lambda: 1_000_000.0)
    assert t.apparaten() == [STEKKER]
    assert token.call_count == 1 and t.token == "T1" and t.verloopt == 1_007_200 and t.gewijzigd
    verzoek = lijst.calls[0].request
    assert verzoek.headers["access_token"] == "T1" and verzoek.headers["client_id"] == RECORD["access_id"]
    assert verzoek.url.params["size"] == "50"
    verwacht = onderteken(
        RECORD["access_id"],
        RECORD["access_secret"],
        "GET",
        "/v1.0/iot-01/associated-users/devices?size=50",
        verzoek.headers["t"],
        token="T1",
        nonce=verzoek.headers["nonce"],
    )
    assert verzoek.headers["sign"] == verwacht
    assert "S" * 32 not in str(verzoek.headers)  # het geheim gaat nooit mee

    t.apparaten()  # token nog geldig: niet opnieuw
    assert token.call_count == 1


@respx.mock
def test_tuya_bladert_en_vult_ontbrekende_status_aan():
    respx.get(f"{URL}/v1.0/token").mock(return_value=TOKEN)
    zonder = {k: v for k, v in STEKKER.items() if k != "status"}
    respx.get(f"{URL}/v1.0/iot-01/associated-users/devices").mock(
        side_effect=[
            ok({"devices": [zonder], "has_more": True, "last_row_key": "rij2"}),
            ok({"devices": [{**zonder, "id": "st2"}], "has_more": False}),
        ]
    )
    status = respx.get(f"{URL}/v1.0/iot-03/devices/status").mock(
        return_value=ok([{"id": "st1", "status": STEKKER["status"]}])
    )
    lijst = Tuya(dict(RECORD)).apparaten()
    assert [a["id"] for a in lijst] == ["st1", "st2"]
    assert lijst[0]["status"] == STEKKER["status"] and lijst[1]["status"] == []
    assert status.calls[0].request.url.params["device_ids"] == "st1,st2"


@respx.mock
def test_tuya_nieuw_token_als_het_oude_niet_meer_geldt():
    token = respx.get(f"{URL}/v1.0/token").mock(return_value=TOKEN)
    respx.get(f"{URL}/v1.0/iot-01/associated-users/devices").mock(
        side_effect=[fout(1010, "token invalid"), ok({"devices": [], "has_more": False})]
    )
    t = Tuya({**RECORD, "token": "OUD", "verloopt": 9e12})
    assert t.apparaten() == [] and token.call_count == 1 and t.token == "T1"


@respx.mock
def test_tuya_fouten_in_gewone_taal():
    respx.get(f"{URL}/v1.0/token").mock(return_value=fout(1004, "sign invalid"))
    with pytest.raises(KoppelingVerlopen, match="Access Secret klopt niet"):
        Tuya(dict(RECORD)).apparaten()

    respx.get(f"{URL}/v1.0/token").mock(return_value=TOKEN)
    respx.get(f"{URL}/v1.0/iot-01/associated-users/devices").mock(return_value=fout(28841002, "expired"))
    with pytest.raises(TuyaFout, match="proefabonnement van IoT Core is verlopen"):
        Tuya(dict(RECORD)).apparaten()


@respx.mock
def test_koppelen_controleert_sleutels_en_zoekt_apparaten():
    respx.get(f"{URL}/v1.0/token").mock(return_value=TOKEN)
    respx.get(f"{URL}/v1.0/iot-01/associated-users/devices").mock(
        return_value=ok({"devices": [STEKKER], "has_more": False})
    )
    respx.get(f"{URL}/v1.0/iot-03/devices/st1/specification").mock(return_value=ok(SPEC_STEKKER))
    r = Tuya.koppel("eu", RECORD["access_id"], RECORD["access_secret"])
    assert r["bericht"] == "1 apparaat gevonden: Wasmachine" and r["token"] == "T1"
    assert r["specs"]["st1"]["status"]["cur_power"] == {
        "type": "Integer",
        "min": 0,
        "max": 99999,
        "scale": 1,
        "step": 1,
        "eenheid": "W",
    }
    assert "colour_data" not in r["specs"]["st1"]["status"]  # JSON toont Thuis niet

    respx.get(f"{URL}/v1.0/iot-01/associated-users/devices").mock(
        return_value=ok({"devices": [], "has_more": False})
    )
    with pytest.raises(KoppelFout, match="Link App Account"):
        Tuya.koppel("eu", RECORD["access_id"], RECORD["access_secret"])
    respx.get(f"{URL}/v1.0/token").mock(return_value=fout(1004))
    with pytest.raises(KoppelFout, match="Access Secret"):
        Tuya.koppel("eu", RECORD["access_id"], RECORD["access_secret"])


@respx.mock
def test_opdracht_naar_tuya():
    respx.get(f"{URL}/v1.0/token").mock(return_value=TOKEN)
    stuur = respx.post(f"{URL}/v1.0/iot-03/devices/st1/commands").mock(return_value=ok(True))
    Tuya(dict(RECORD)).stuur("st1", [{"code": "switch_1", "value": False}])
    assert json.loads(stuur.calls[0].request.content) == {"commands": [{"code": "switch_1", "value": False}]}
    assert stuur.calls[0].request.headers["content-type"] == "application/json"


# ── van Tuya naar Thuis ───────────────────────────────────────────────────────


def test_maak_schaalt_en_ordent():
    a = maak(STEKKER, compact(SPEC_STEKKER))
    assert a["soort"] == "stekker" and a["aan"] is True and a["schakelaars"] == ["switch_1"]
    assert a["metingen"] == {"vermogen_w": 486.2, "stroom_a": 2.19, "energie_kwh": 0.128}
    codes = {b["code"]: b for b in a["bediening"]}
    assert codes["relay_status"]["keuzes"] == ["power_off", "power_on", "last"]
    assert codes["countdown_1"] | {} == {
        "code": "countdown_1",
        "type": "Integer",
        "waarde": None,
        "min": 0,
        "max": 86400,
        "stap": 1,
        "eenheid": "s",
    }
    assert {s["code"] for s in a["status"]} == {
        "cur_power",
        "cur_current",
        "add_ele",
    }  # bediening niet dubbel


def test_maak_zonder_specificatie_en_met_meerdere_stopcontacten():
    doos = {
        "id": "pc1",
        "name": "Bureau",
        "category": "pc",
        "status": [
            {"code": "switch_1", "value": False},
            {"code": "switch_2", "value": True},
            {"code": "switch_usb1", "value": False},
            {"code": "cur_power", "value": 153},
        ],
    }
    a = maak(doos, None)
    assert a["schakelaars"] == ["switch_1", "switch_2", "switch_usb1"] and a["aan"] is True
    assert a["metingen"]["vermogen_w"] == 15.3 and a["bediening"] == []  # zonder specificatie: alleen kijken
    sensor = maak(
        {"id": "s", "category": "mcs", "status": [{"code": "doorcontact_state", "value": True}]}, None
    )
    assert sensor["soort"] == "sensor" and sensor["toestand"] == "open" and sensor["aan"] is None
    onbekend = maak({"id": "x", "category": "xyz", "status": [{"code": "bright_value_v2", "value": 5}]}, None)
    assert onbekend["soort"] == "lamp" and onbekend["naam"] == "x"


def test_opdracht_controleert_en_rondt_af():
    spec = {
        "functies": {
            "switch_led": {"type": "Boolean"},
            "temp_set": {"type": "Integer", "min": 50, "max": 300, "scale": 1, "step": 5},
            "mode": {"type": "Enum", "keuzes": ["auto", "manual"]},
        }
    }
    assert opdracht(spec, "switch_led", False) == {"code": "switch_led", "value": False}
    assert opdracht(spec, "temp_set", 21.3) == {"code": "temp_set", "value": 215}  # op halve graden
    assert opdracht(spec, "temp_set", 99) == {"code": "temp_set", "value": 300}  # binnen het bereik
    assert opdracht(spec, "mode", "manual") == {"code": "mode", "value": "manual"}
    for code, waarde in (("switch_led", 1), ("temp_set", True), ("mode", "turbo"), ("reset_factory", True)):
        with pytest.raises(ValueError):
            opdracht(spec, code, waarde)


def test_meting_voor_de_tabel():
    rij = meting(STEKKER, compact(SPEC_STEKKER), utc(2026, 10, 9, 12))
    assert rij["aan"] is True and rij["vermogen_w"] == 486.2 and rij["soort"] == "stekker"
    assert json.loads(rij["status"])["cur_power"] == 4862  # ruw bewaard


# ── live ──────────────────────────────────────────────────────────────────────


class Klok:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_live_bewaart_kort_en_toont_de_gevraagde_stand():
    klok = Klok()
    gemaakt = []

    def maak_demo(record):
        gemaakt.append(record)
        return DemoTuya(record)

    live = Live(lambda: {"koppelingen": {"tuya": RECORD}}, maak_demo, klok=klok)
    eerste = live.lijst()
    assert eerste["gekoppeld"] and len(eerste["apparaten"]) == 11
    lamp = next(a for a in eerste["apparaten"] if a["id"] == "demo-ledstrip")
    assert lamp["aan"] is False

    uit = live.bedien("demo-ledstrip", [{"code": "switch_led", "waarde": True}])
    assert uit["aan"] is True
    klok.t = 5  # nog bewaard: de gevraagde stand
    assert next(a for a in live.lijst()["apparaten"] if a["id"] == "demo-ledstrip")["aan"] is True
    with pytest.raises(LookupError, match="offline"):
        live.bedien("demo-lamp-hal", [{"code": "switch_led", "waarde": True}])
    with pytest.raises(ValueError):
        live.bedien("demo-ledstrip", [{"code": "switch_led", "waarde": "aan"}])
    assert len(gemaakt) == 1

    live.bedien("demo-ledstrip", [{"code": "switch_led", "waarde": False}])  # terug, voor de andere tests
    assert Live(lambda: {}, maak_demo).lijst() == {"gekoppeld": False, "apparaten": [], "bijgewerkt": None}


def test_live_vraagt_tuya_niet_vaker_dan_nodig():
    klok = Klok()
    vragen = []

    class Teller(DemoTuya):
        def apparaten(self):
            vragen.append(klok.t)
            return super().apparaten()

    live = Live(lambda: {"koppelingen": {"tuya": RECORD}}, Teller, klok=klok)
    live.lijst()
    klok.t = 10
    live.lijst()  # binnen 15 s: bewaard
    live.lijst(vers=True)  # vers mag na 3 s
    klok.t = 11
    live.lijst(vers=True)
    assert vragen == [0, 10]


# ── historie ──────────────────────────────────────────────────────────────────


def test_verbruik_vandaag_schat_met_metingen_en_prijzen(opslag):
    from datetime import date

    dag = date(2026, 10, 9)
    start = utc(2026, 10, 8, 22)  # 00:00 in Nederland
    opslag.voeg_toe(PRIJS, blokken(start, [0.2, 0.4], minuten=60))
    t = [start, start + timedelta(minutes=30), start + timedelta(minutes=60), start + timedelta(minutes=150)]
    opslag.voeg_toe(
        APPARAAT,
        [
            {"tijd": t[0], "apparaat_id": "a", "vermogen_w": 1000.0},
            {"tijd": t[1], "apparaat_id": "a", "vermogen_w": 1000.0},  # 0,5 kWh à € 0,20
            {
                "tijd": t[2],
                "apparaat_id": "a",
                "vermogen_w": 3000.0,
            },  # 1 kWh, midden in het tweede uur: € 0,40
            {"tijd": t[3], "apparaat_id": "a", "vermogen_w": 3000.0},  # gat van 90 minuten: telt niet
            {"tijd": t[0], "apparaat_id": "lamp", "vermogen_w": None},
        ],
    )
    uit = verbruik_vandaag(opslag, dag)
    assert uit["apparaten"]["a"] == {"kwh": 1.5, "kosten": round(0.5 * 0.2 + 1.0 * 0.2, 4)}
    assert "lamp" not in uit["apparaten"] and uit["kwh"] == 1.5
    h = historie(opslag, "a", start, start + timedelta(hours=3))
    assert h["vermogen_w"] == [1000.0, 1000.0, 3000.0, 3000.0] and len(h["tijden"]) == 4


# ── verzamelaar en koppelingen ────────────────────────────────────────────────


class NepPrijzen:
    def prijzen(self, start, eind):
        return []


class NepWeer:
    def temperaturen(self, terug, vooruit):
        return []


def test_ronde_bewaart_apparaten_en_nieuwe_specs(opslag, monkeypatch):
    for k in ("FRANK_EMAIL", "EASEE_GEBRUIKER", "KIA_GEBRUIKER", "GOOGLE_CHAT_WEBHOOK", "THUIS_GEHEIMEN"):
        monkeypatch.delenv(k, raising=False)
    t = DemoTuya()
    t.gewijzigd = True  # zoals na een nieuw token
    kluis = GeheugenKluis({"koppelingen": {"tuya": {**RECORD, "status": "ok"}}})
    uitslag = ronde(Config(), opslag, frank=NepPrijzen(), weer=NepWeer(), kluis=kluis, tuya=t)
    assert uitslag["apparaten"] == "ok"
    rijen = opslag.lees("SELECT apparaat_id, aan, vermogen_w FROM {apparaat_meting} ORDER BY apparaat_id")
    assert len(rijen) == 11 and {"apparaat_id": "demo-netwerk", "aan": True, "vermogen_w": 23.6} in rijen
    assert "demo-zolder" in kluis.data["koppelingen"]["tuya"]["specs"]


def test_overzicht_toont_tuya_zonder_geheim():
    data = {"koppelingen": {"tuya": {**RECORD, "token": "T", "account": RECORD["access_id"], "status": "ok"}}}
    tuya = next(d for d in overzicht(data) if d["dienst"] == "tuya")
    assert tuya["status"] == "ok" and tuya["account"] == "ab12…90"
    assert tuya["velden"][0]["keuzes"][0] == {
        "waarde": "eu",
        "label": "Centraal-Europa (Nederland en België)",
    }
    assert "S" * 32 not in json.dumps(tuya) and '"T"' not in json.dumps(tuya)


# ── API ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_demo(monkeypatch, tmp_path):
    monkeypatch.setenv("THUIS_DUCKDB_PAD", str(tmp_path / "a.duckdb"))
    monkeypatch.setenv("THUIS_AUTH_UIT", "1")
    monkeypatch.setenv("THUIS_DEMO_APPARATEN", "1")
    with TestClient(api_mod.app) as c:
        c.app.state.kluis = GeheugenKluis()
        yield c


def test_api_apparaten(app_demo):
    c = app_demo
    assert c.get("/api/apparaten").json() == {"gekoppeld": False, "apparaten": [], "bijgewerkt": None}
    c.app.state.kluis.data = {"koppelingen": {"tuya": {**RECORD, "status": "ok"}}}
    c.app.state.apparaten.vergeet()
    lijst = c.get("/api/apparaten").json()
    assert lijst["gekoppeld"] and lijst["apparaten"][0]["soort"] == "stekker"

    r = c.post("/api/apparaten/demo-tv", json={"opdrachten": [{"code": "switch_3", "waarde": True}]})
    assert r.status_code == 200 and "switch_3" in r.json()["apparaat"]["schakelaars"]
    r = c.post("/api/apparaten/demo-radiator", json={"opdrachten": [{"code": "temp_set", "waarde": 19}]})
    temp = next(b for b in r.json()["apparaat"]["bediening"] if b["code"] == "temp_set")
    assert temp["waarde"] == 19 and temp["eenheid"] == "°C"
    r = c.post("/api/apparaten/demo-tv", json={"opdrachten": [{"code": "switch_3", "waarde": 1}]})
    assert r.status_code == 422 and r.json()["detail"] == "Verwacht aan of uit."
    assert c.post("/api/apparaten/demo-tv", json={"opdrachten": []}).status_code == 422
    assert (
        c.post("/api/apparaten/onbekend", json={"opdrachten": [{"code": "a", "waarde": True}]}).status_code
        == 409
    )
    assert (
        c.post("/api/apparaten/a.b", json={"opdrachten": [{"code": "a", "waarde": True}]}).status_code == 422
    )
    c.post("/api/apparaten/demo-tv", json={"opdrachten": [{"code": "switch_3", "waarde": False}]})

    assert c.get("/api/apparaten/vandaag").json()["apparaten"] == {}
    h = c.get("/api/apparaten/demo-tv/historie?dagen=7").json()
    assert h["tijden"] == [] and c.get("/api/apparaten/demo-tv/historie?dagen=9").status_code == 422


def test_api_bedienen_laat_bewaarde_antwoorden_staan(app_demo):
    c = app_demo
    c.app.state.kluis.data = {"koppelingen": {"tuya": {**RECORD, "status": "ok"}}}
    geleegd = []
    c.app.state.bewaard.leeg = lambda: geleegd.append(1)
    c.post("/api/apparaten/demo-ledstrip", json={"opdrachten": [{"code": "switch_led", "waarde": False}]})
    assert geleegd == []
    c.put("/api/instellingen", json={})  # wel bij een echte wijziging (ook als die faalt)
    assert geleegd == [1]


@respx.mock
def test_api_fouten_van_tuya(app_demo, monkeypatch):
    c = app_demo
    monkeypatch.setattr(c.app.state.apparaten, "_maak_tuya", Tuya)
    c.app.state.kluis.data = {"koppelingen": {"tuya": {**RECORD, "status": "ok"}}}
    c.app.state.apparaten.vergeet()
    respx.get(f"{URL}/v1.0/token").mock(return_value=fout(1004))
    r = c.get("/api/apparaten")
    assert r.status_code == 409 and "Koppel opnieuw" in r.json()["detail"]
    respx.get(f"{URL}/v1.0/token").mock(return_value=TOKEN)
    respx.get(f"{URL}/v1.0/iot-01/associated-users/devices").mock(side_effect=httpx.ConnectError("weg"))
    r = c.get("/api/apparaten")
    assert r.status_code == 502 and "niet bereikbaar" in r.json()["detail"]
