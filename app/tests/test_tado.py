import json
import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from thuis import api as api_mod
from thuis.apparaten import Live
from thuis.config import Config
from thuis.connectors import KoppelFout, KoppelingVerlopen
from thuis.connectors.tado import HOPS, LOGIN, MY, Tado, TadoFout, apparaat_v3, apparaat_x
from thuis.demo_apparaten import DemoTado, DemoTuya
from thuis.kluis import GeheugenKluis, werk_velden_bij
from thuis.verzamel import ronde

V3 = {
    "home_id": 7,
    "generatie": "PRE_LINE_X",
    "zones": {
        "1": {"naam": "Woonkamer", "type": "HEATING"},
        "4": {"naam": "Warm water", "type": "HOT_WATER"},
    },
    "access_token": "A1",
    "refresh_token": "R1",
    "verloopt": time.time() + 3000,
    "status": "ok",
}
ZONESTATES = {
    "zoneStates": {
        "1": {
            "setting": {"type": "HEATING", "power": "ON", "temperature": {"celsius": 21.0}},
            "overlay": {"termination": {"type": "TIMER", "projectedExpiry": "2026-10-11T17:00:00Z"}},
            "link": {"state": "ONLINE"},
            "sensorDataPoints": {"insideTemperature": {"celsius": 19.4}, "humidity": {"percentage": 55.2}},
            "activityDataPoints": {"heatingPower": {"percentage": 38.0}},
            "nextScheduleChange": {
                "start": "2026-10-11T20:00:00Z",
                "setting": {"temperature": {"celsius": 18.0}},
            },
            "openWindow": None,
        },
        "4": {"setting": {"type": "HOT_WATER", "power": "OFF"}, "overlay": None, "link": {"state": "ONLINE"}},
        "9": {"setting": {"type": "AIR_CONDITIONING", "power": "OFF"}},  # niet in de zones: telt niet
    }
}
KAMER_X = {
    "id": 3,
    "name": "Badkamer",
    "sensorDataPoints": {"insideTemperature": {"value": 18.1}, "humidity": {"percentage": 71}},
    "setting": {"power": "OFF", "temperature": None},
    "heatingPower": {"percentage": 0},
    "connection": {"state": "CONNECTED"},
    "openWindow": {"activated": True, "expiryInSeconds": 600},
    "manualControlTermination": {"type": "MANUAL", "remainingTimeInSeconds": None, "projectedExpiry": None},
    "nextScheduleChange": None,
}
LIMIET = {"ratelimit": '"perday";r=93;t=4567', "ratelimit-policy": '"perday";q=100;w=86400'}


def ok(data, **kw):
    return httpx.Response(200, json=data, headers=LIMIET, **kw)


def kluis_met(record):
    return GeheugenKluis({"koppelingen": {"tado": dict(record)}})


# ── koppelen ──────────────────────────────────────────────────────────────────


@respx.mock
def test_koppelen_met_een_code():
    start = respx.post(f"{LOGIN}/device_authorize").mock(
        return_value=httpx.Response(
            200,
            json={
                "device_code": "DC",
                "user_code": "7XKQ2M",
                "verification_uri_complete": "https://login.tado.com/oauth2/device?user_code=7XKQ2M",
                "expires_in": 300,
                "interval": 5,
            },
        )
    )
    wacht, toon = Tado.start_koppeling()
    assert dict(httpx.QueryParams(start.calls[0].request.content.decode())) == {
        "client_id": "1bb50063-6b0c-4d11-bd99-387f4a91cc46",
        "scope": "offline_access",
    }
    assert (
        toon["code"] == "7XKQ2M"
        and toon["link"].startswith("https://login.tado.com")
        and wacht["device_code"] == "DC"
    )

    token = respx.post(f"{LOGIN}/token").mock(
        side_effect=[
            httpx.Response(400, json={"error": "authorization_pending"}),
            httpx.Response(400, json={"error": "slow_down"}),
            httpx.Response(200, json={"access_token": "A", "refresh_token": "R", "expires_in": 599}),
        ]
    )
    respx.get(f"{MY}/me").mock(return_value=ok({"homes": [{"id": 7, "name": "Thuis"}]}))
    respx.get(f"{MY}/homes/7").mock(return_value=ok({"id": 7, "name": "Thuis", "generation": "PRE_LINE_X"}))
    respx.get(f"{MY}/homes/7/zones").mock(
        return_value=ok(
            [
                {"id": 1, "name": "Woonkamer", "type": "HEATING"},
                {"id": 4, "name": "Warm water", "type": "HOT_WATER"},
            ]
        )
    )
    assert Tado.controleer_koppeling(wacht) is None
    assert Tado.controleer_koppeling(wacht) is None and wacht["interval"] == 10
    r = Tado.controleer_koppeling(wacht)
    assert r["home_id"] == 7 and r["generatie"] == "PRE_LINE_X" and r["refresh_token"] == "R"
    assert r["zones"] == {
        "1": {"naam": "Woonkamer", "type": "HEATING"},
        "4": {"naam": "Warm water", "type": "HOT_WATER"},
    }
    assert r["bericht"] == "tado°, zones: Woonkamer, Warm water" and r["quotum"]["over"] == 93
    verzoek = dict(httpx.QueryParams(token.calls[0].request.content.decode()))
    assert (
        verzoek["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"
        and verzoek["device_code"] == "DC"
    )

    respx.post(f"{LOGIN}/token").mock(return_value=httpx.Response(400, json={"error": "access_denied"}))
    with pytest.raises(KoppelFout, match="geweigerd"):
        Tado.controleer_koppeling(wacht)


@respx.mock
def test_koppelen_tado_x_gebruikt_hops():
    respx.post(f"{LOGIN}/token").mock(
        return_value=httpx.Response(200, json={"access_token": "A", "refresh_token": "R"})
    )
    respx.get(f"{MY}/me").mock(return_value=ok({"homes": [{"id": 8}]}))
    respx.get(f"{MY}/homes/8").mock(return_value=ok({"name": "Huis", "generation": "LINE_X"}))
    respx.get(f"{HOPS}/homes/8/rooms").mock(return_value=ok([KAMER_X]))
    r = Tado.controleer_koppeling({"device_code": "DC", "interval": 5, "verloopt": time.time() + 60})
    assert r["generatie"] == "LINE_X" and r["zones"] == {"3": {"naam": "Badkamer", "type": "HEATING"}}
    assert r["bericht"] == "tado° X, zones: Badkamer"


# ── tokens: één keer bruikbaar, gedeeld via de kluis ──────────────────────────


@respx.mock
def test_verversen_schrijft_meteen_naar_de_kluis():
    kluis = kluis_met({**V3, "verloopt": 0})
    respx.post(f"{LOGIN}/token").mock(
        return_value=httpx.Response(
            200, json={"access_token": "A2", "refresh_token": "R2", "expires_in": 599}
        )
    )
    standen = respx.get(f"{MY}/homes/7/zoneStates").mock(return_value=ok(ZONESTATES))
    t = Tado(kluis.data["koppelingen"]["tado"], kluis)
    assert [a["id"] for a in t.apparaten()] == ["tado-1", "tado-4"]
    assert standen.calls[0].request.headers["authorization"] == "Bearer A2"
    bewaard = kluis.data["koppelingen"]["tado"]
    assert bewaard["refresh_token"] == "R2" and bewaard["access_token"] == "A2" and bewaard["home_id"] == 7


@respx.mock
def test_geweigerd_verversen_pakt_het_token_van_de_ander():
    kluis = kluis_met({**V3, "verloopt": 0})
    t = Tado(kluis.data["koppelingen"]["tado"], kluis, slaap=lambda s: None)

    def ander_was_eerder(request):
        werk_velden_bij(
            kluis, "tado", {"access_token": "B", "refresh_token": "RB", "verloopt": time.time() + 600}
        )
        return httpx.Response(400, json={"error": "invalid_grant"})

    respx.post(f"{LOGIN}/token").mock(side_effect=ander_was_eerder)
    standen = respx.get(f"{MY}/homes/7/zoneStates").mock(return_value=ok(ZONESTATES))
    t.apparaten()
    assert standen.calls[0].request.headers["authorization"] == "Bearer B"


@respx.mock
def test_geweigerd_zonder_nieuw_token_is_opnieuw_koppelen():
    kluis = kluis_met({**V3, "verloopt": 0})
    respx.post(f"{LOGIN}/token").mock(return_value=httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(KoppelingVerlopen):
        Tado(kluis.data["koppelingen"]["tado"], kluis, slaap=lambda s: None).apparaten()
    assert kluis.data["koppelingen"]["tado"]["status"] == "opnieuw"


def test_velden_bijwerken_alleen_als_de_koppeling_er_nog_is():
    kluis = kluis_met({"a": 1, "b": 2})
    werk_velden_bij(kluis, "tado", {"b": 3})
    assert kluis.data["koppelingen"]["tado"] == {"a": 1, "b": 3}
    leeg = GeheugenKluis({"koppelingen": {}})
    werk_velden_bij(leeg, "tado", {"b": 3})
    assert leeg.data == {"koppelingen": {}} and leeg.schrijfacties == 0


# ── dagmaximum ────────────────────────────────────────────────────────────────


@respx.mock
def test_quotum_uit_de_header_en_dagmaximum():
    t = Tado(dict(V3))
    respx.get(f"{MY}/homes/7/zoneStates").mock(return_value=ok(ZONESTATES))
    t.apparaten()
    assert t.quotum["over"] == 93 and t.quotum["per_dag"] == 100 and t.zuinig
    respx.get(f"{MY}/homes/7/zoneStates").mock(
        return_value=httpx.Response(429, headers={"ratelimit": '"perday";r=0;t=60'})
    )
    with pytest.raises(TadoFout, match="dagmaximum"):
        t.apparaten()
    assert t.quotum["over"] == 0


def test_verzamelaar_zuinig_zonder_auto_assist():
    moment = datetime(2026, 10, 11, 12, tzinfo=UTC)
    t = Tado(
        {
            **V3,
            "quotum": {"over": 80, "per_dag": 100},
            "gelezen": (moment - timedelta(minutes=30)).isoformat(),
        }
    )
    assert not t.aan_de_beurt(moment)  # half uur geleden: nog niet
    assert t.aan_de_beurt(moment + timedelta(minutes=30))
    assert t.aan_de_beurt(moment, gevraagd=moment)  # Nu ophalen
    t.record["quotum"]["over"] = 20  # reserve voor de app
    assert not t.aan_de_beurt(moment + timedelta(hours=2)) and t.aan_de_beurt(moment, gevraagd=moment)
    t.record["quotum"] = {"over": 19000, "per_dag": 20000}  # Auto-Assist: elke ronde
    assert t.aan_de_beurt(moment) and not t.zuinig


# ── van tado naar Thuis ───────────────────────────────────────────────────────


def test_zone_v3_en_kamer_x():
    a = apparaat_v3("1", V3["zones"]["1"], ZONESTATES["zoneStates"]["1"])
    assert a["id"] == "tado-1" and a["soort"] == "klimaat" and a["aan"] is True  # verwarmt nu
    assert a["metingen"] == {"temperatuur": 19.4, "vochtigheid": 55.2}
    b = {x["code"]: x for x in a["bediening"]}
    assert b["tado_stand"]["waarde"] == "handmatig" and b["temp_set"]["waarde"] == 21.0
    status = {s["code"]: s["waarde"] for s in a["status"]}
    assert status == {
        "verwarming": 38,
        "handmatig_tot": "2026-10-11T17:00:00+00:00",
        "schema_volgende": "2026-10-11T20:00:00+00:00",
        "schema_temp": 18.0,
    }
    w = apparaat_v3("4", V3["zones"]["4"], ZONESTATES["zoneStates"]["4"])
    assert (
        w["aan"] is False and w["toestand"] == "uit" and [x["code"] for x in w["bediening"]] == ["tado_stand"]
    )
    x = apparaat_x(KAMER_X)
    assert x["id"] == "tado-3" and x["toestand"] == "raam_open" and x["product"] == "tado° X"
    bx = {b["code"]: b for b in x["bediening"]}
    assert (
        bx["tado_stand"]["waarde"] == "uit"
        and bx["temp_set"]["waarde"] is None
        and bx["temp_set"]["standaard"] == 20.0
    )


@respx.mock
def test_zetten_v3_en_x():
    t = Tado(dict(V3))
    overlay = respx.put(f"{MY}/homes/7/zones/1/overlay").mock(return_value=ok({}))
    weg = respx.delete(f"{MY}/homes/7/zones/1/overlay").mock(return_value=httpx.Response(204, headers=LIMIET))
    t.zet("1", "blok", 21.5)
    assert json.loads(overlay.calls[0].request.content) == {
        "setting": {"type": "HEATING", "power": "ON", "temperature": {"celsius": 21.5}},
        "termination": {"typeSkillBasedApp": "NEXT_TIME_BLOCK"},
    }
    t.zet("1", "uit")
    assert json.loads(overlay.calls[1].request.content) == {
        "setting": {"type": "HEATING", "power": "OFF"},
        "termination": {"typeSkillBasedApp": "MANUAL"},
    }
    t.zet("1", "schema")
    assert weg.called
    warm = respx.put(f"{MY}/homes/7/zones/4/overlay").mock(return_value=ok({}))
    t.zet("4", "handmatig", 20.0)
    assert json.loads(warm.calls[0].request.content)["setting"] == {"type": "HOT_WATER", "power": "ON"}

    x = Tado({**V3, "generatie": "LINE_X"})
    hand = respx.post(f"{HOPS}/homes/7/rooms/3/manualControl").mock(return_value=ok({}))
    terug = respx.delete(f"{HOPS}/homes/7/rooms/3/manualControl").mock(return_value=httpx.Response(204))
    x.zet("3", "handmatig", 19.0)
    assert json.loads(hand.calls[0].request.content) == {
        "setting": {"power": "ON", "temperature": {"value": 19.0}},
        "termination": {"type": "MANUAL"},
    }
    x.zet("3", "schema")
    assert terug.called


# ── live: zuinig, en elke bron los ────────────────────────────────────────────


class Klok:
    t = 0.0

    def __call__(self):
        return self.t


def test_live_tado_zuinig_en_bedienen():
    klok = Klok()
    vragen = []

    class Teller(DemoTado):
        def apparaten(self):
            vragen.append(klok.t)
            return super().apparaten()

    kluis = GeheugenKluis({"koppelingen": {"tado": {"home_id": 1}}})
    live = Live(lambda: kluis, None, Teller, klok=klok)
    eerst = live.lijst()
    assert eerst["bronnen"]["tado"]["quotum"]["per_dag"] == 100 and len(eerst["apparaten"]) == 4
    klok.t = 299
    live.lijst(vers=True)  # zuinig: ook met vers hooguit eens per vijf minuten
    klok.t = 301
    live.lijst()
    assert vragen == [0, 301]

    slaapkamer = live.bedien("tado-2", [{"code": "temp_set", "waarde": 19.3}])
    b = {x["code"]: x for x in slaapkamer["bediening"]}
    assert b["temp_set"]["waarde"] == 19.5 and b["tado_stand"]["waarde"] == "handmatig"
    uit = live.bedien("tado-1", [{"code": "tado_stand", "waarde": "uit"}])
    assert uit["toestand"] == "uit" and {x["code"]: x for x in uit["bediening"]}["temp_set"]["waarde"] is None
    with pytest.raises(ValueError):
        live.bedien("tado-1", [{"code": "tado_stand", "waarde": "turbo"}])
    with pytest.raises(ValueError):
        live.bedien("tado-1", [{"code": "child_lock", "waarde": True}])
    with pytest.raises(LookupError):
        live.bedien("tado-99", [{"code": "temp_set", "waarde": 20}])


def test_live_elke_bron_los():
    class KapotteTado(DemoTado):
        def apparaten(self):
            raise TadoFout("tado is even niet bereikbaar; probeer het zo nog eens.")

    kluis = GeheugenKluis(
        {
            "koppelingen": {
                "tuya": {"regio": "eu", "access_id": "x", "access_secret": "y"},
                "tado": {"home_id": 1},
            }
        }
    )
    r = Live(lambda: kluis, DemoTuya, KapotteTado).lijst()
    assert r["gekoppeld"] and len(r["apparaten"]) == 11  # de Tuya-apparaten komen gewoon
    assert r["bronnen"]["tado"]["fout"].startswith("tado is even niet bereikbaar")
    alleen_tado = GeheugenKluis({"koppelingen": {"tado": {"home_id": 1}}})
    with pytest.raises(TadoFout):
        Live(lambda: alleen_tado, None, KapotteTado).lijst()


# ── verzamelaar en API ────────────────────────────────────────────────────────


class NepPrijzen:
    def prijzen(self, start, eind):
        return []


class NepWeer:
    def temperaturen(self, terug, vooruit):
        return []


def test_ronde_bewaart_de_kamers(opslag, monkeypatch):
    for k in ("FRANK_EMAIL", "EASEE_GEBRUIKER", "KIA_GEBRUIKER", "GOOGLE_CHAT_WEBHOOK", "THUIS_GEHEIMEN"):
        monkeypatch.delenv(k, raising=False)
    kluis = GeheugenKluis({"koppelingen": {"tado": {"home_id": 1, "status": "ok"}}})
    uitslag = ronde(Config(), opslag, frank=NepPrijzen(), weer=NepWeer(), kluis=kluis, tado=DemoTado())
    assert uitslag["tado"] == "ok"
    rijen = opslag.lees("SELECT apparaat_id, temperatuur, soort FROM {apparaat_meting} ORDER BY apparaat_id")
    assert [r["apparaat_id"] for r in rijen] == ["tado-1", "tado-2", "tado-3", "tado-4"]
    assert rijen[0]["soort"] == "klimaat" and rijen[0]["temperatuur"] is not None


@pytest.fixture
def app_kluis(monkeypatch, tmp_path):
    monkeypatch.setenv("THUIS_DUCKDB_PAD", str(tmp_path / "t.duckdb"))
    monkeypatch.setenv("THUIS_AUTH_UIT", "1")
    with TestClient(api_mod.app) as c:
        c.app.state.kluis = GeheugenKluis()
        yield c


def test_api_koppelt_tado_met_een_code(app_kluis, monkeypatch):
    c = app_kluis
    monkeypatch.setattr(api_mod, "start_ronde", lambda cfg: False)
    monkeypatch.setattr(
        Tado,
        "start_koppeling",
        staticmethod(
            lambda client=None: (
                {"device_code": "DC", "interval": 5, "verloopt": time.time() + 300},
                {"code": "7XKQ2M", "link": "https://login.tado.com/x", "interval": 5, "verloopt": "…"},
            )
        ),
    )
    antwoorden = iter([None, {**V3, "account": "Thuis", "bericht": "tado°, zones: Woonkamer"}])
    monkeypatch.setattr(
        Tado, "controleer_koppeling", classmethod(lambda cls, wacht, client=None: next(antwoorden))
    )
    r = c.post("/api/koppelingen/tado", json={})
    assert r.status_code == 200 and r.json()["code"]["code"] == "7XKQ2M"
    assert c.post("/api/koppelingen/tado/controleer").json() == {"wacht": True, "interval": 5}
    r = c.post("/api/koppelingen/tado/controleer").json()
    assert r["bericht"] == "tado°, zones: Woonkamer"
    tado = next(k for k in r["koppelingen"] if k["dienst"] == "tado")
    assert tado["status"] == "ok" and tado["account"] == "Thuis" and "R1" not in json.dumps(r)
    assert "tado" not in (c.app.state.kluis.data.get("wachtend") or {})
