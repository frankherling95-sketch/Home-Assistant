from datetime import date, datetime, timedelta

import httpx
import pytest
import respx
from conftest import utc
from fastapi.testclient import TestClient

from thuis import api as api_mod
from thuis.config import TZ, Config
from thuis.connectors.weer import URL, OpenMeteo
from thuis.inzicht import dag_grenzen
from thuis.opslag import schrijf_instellingen
from thuis.schema import PRIJS, VERBRUIK, WEER
from thuis.weer import WeerLive, gasmodel, graaddagen, locatie, weer_overzicht

T0 = 1791583200  # 2026-10-10 00:00 in Nederland
ANTWOORD = {
    "current": {
        "time": T0,
        "interval": 900,
        "temperature_2m": 14.0,
        "apparent_temperature": 12.9,
        "relative_humidity_2m": 92,
        "precipitation": 0.0,
        "weather_code": 3,
        "cloud_cover": 83,
        "wind_speed_10m": 13.7,
        "wind_gusts_10m": 31.7,
        "wind_direction_10m": 281,
        "is_day": 0,
    },
    "minutely_15": {"time": [T0, T0 + 900], "precipitation": [0.0, 0.1]},
    "hourly": {
        "time": [T0, T0 + 3600],
        "temperature_2m": [14.0, 12.5],
        "precipitation": [0.1, 0.0],
        "precipitation_probability": [74, 37],
        "weather_code": [51, 3],
        "wind_speed_10m": [13.7, 10.8],
        "is_day": [0, 0],
    },  # niet elke kolom: wat ontbreekt wordt None
    "daily": {
        "time": [T0, T0 + 86400],
        "weather_code": [63, 3],
        "temperature_2m_max": [14.0, 15.0],
        "temperature_2m_min": [9.4, 8.0],
        "temperature_2m_mean": [11.7, 19.0],
        "sunrise": [T0 + 28515, T0 + 28600],
        "sunset": [T0 + 68181, T0 + 68000],
        "sunshine_duration": [26115.6, 0],
    },
}


@respx.mock
def test_verwachting_van_open_meteo():
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=ANTWOORD))
    v = OpenMeteo(0, 0).verwachting(52.1, 5.18)
    p = route.calls[0].request.url.params
    assert p["timezone"] == "Europe/Amsterdam" and p["forecast_hours"] == "48" and p["forecast_days"] == "7"
    assert v["nu"]["temperatuur"] == 14.0 and v["nu"]["windrichting"] == 281 and v["nu"]["dag"] == 0
    assert v["nu"]["tijd"] == datetime.fromtimestamp(T0, TZ)
    assert [k["neerslag"] for k in v["kwartieren"]] == [0.0, 0.1]
    assert v["uren"][1] == {
        "tijd": datetime.fromtimestamp(T0 + 3600, TZ),
        "temperatuur": 12.5,
        "gevoel": None,
        "neerslag": 0.0,
        "neerslagkans": 37,
        "weercode": 3,
        "wind": 10.8,
        "windstoten": None,
        "windrichting": None,
        "dag": 0,
        "straling": None,
    }
    d = v["dagen"][0]
    assert d["datum"] == date(2026, 10, 10) and d["temp_gem"] == 11.7
    assert d["zon_op"].astimezone(TZ).strftime("%H:%M") == "07:55"


class NepBron:
    def __init__(self):
        self.vragen = []

    def verwachting(self, lat, lon):
        self.vragen.append((lat, lon))
        dag = date(2026, 10, 10)
        return {
            "nu": {"tijd": utc(2026, 10, 10, 12), "temperatuur": 14.0},
            "kwartieren": [],
            "uren": [],
            "dagen": [
                {"datum": dag, "temp_gem": 11.0},
                {"datum": dag + timedelta(days=1), "temp_gem": 20.0},
                {"datum": dag + timedelta(days=2), "temp_gem": None},
            ],
        }


class Klok:
    t = 0.0

    def __call__(self):
        return self.t


def test_weerlive_bewaart_tien_minuten():
    bron, klok = NepBron(), Klok()
    live = WeerLive(bron, klok)
    live.haal(52.1, 5.18)
    klok.t = 599
    live.haal(52.1, 5.18)
    assert len(bron.vragen) == 1
    live.haal(52.0, 5.0)  # andere plek: opnieuw
    klok.t = 2000
    live.haal(52.0, 5.0)
    assert len(bron.vragen) == 3


def test_locatie_thuis_of_de_bilt(opslag):
    assert locatie(opslag, Config()) == {"lat": 52.1, "lon": 5.18, "bron": "instelling", "naam": "De Bilt"}
    schrijf_instellingen(opslag, {"auto_thuis": {"lat": 52.123456, "lon": 4.987654}})
    assert locatie(opslag, Config()) == {"lat": 52.12, "lon": 4.99, "bron": "thuis", "naam": "thuis"}


def _historie(opslag, dagen, gas_van_gd, temps):
    """Gas per dag uit de graaddagen, met temperaturen per uur die het gemiddelde geven."""
    for i, (d, t) in enumerate(zip(dagen, temps, strict=True)):
        van, _ = dag_grenzen(d)
        gd = max(0.0, 18 - t)
        opslag.voeg_toe(
            VERBRUIK,
            [
                {
                    "soort": "gas",
                    "van": van,
                    "tot": van + timedelta(hours=1),
                    "hoeveelheid": gas_van_gd(gd),
                    "kosten": 1,
                }
            ],
        )
        opslag.voeg_toe(
            WEER,
            [
                {"van": van + timedelta(hours=h), "tot": van + timedelta(hours=h + 1), "temperatuur": t}
                for h in range(24)
            ],
        )
        if i == 0:  # de prijs van de laatste dag
            opslag.voeg_toe(
                PRIJS,
                [
                    {
                        "soort": "gas",
                        "van": van,
                        "tot": van + timedelta(days=1),
                        "marktprijs": 0.3,
                        "allin": 1.25,
                    }
                ],
            )


def test_gasmodel_haalt_basis_en_verwarming_terug(opslag):
    vandaag = date(2026, 10, 10)
    dagen = [vandaag - timedelta(days=i) for i in range(1, 21)]
    temps = [5 + (i % 10) for i in range(20)]  # 5 … 14 °C
    _historie(opslag, dagen, lambda gd: 0.5 + 0.4 * gd, temps)
    m = gasmodel(opslag, vandaag)
    assert m == {"basis_m3": 0.5, "per_graaddag_m3": 0.4, "dagen": 20, "prijs": 1.25}

    w = weer_overzicht(opslag, Config(), WeerLive(NepBron()), vandaag)
    assert [d["graaddagen"] for d in w["dagen"]] == [7.0, 0.0, None]
    assert [d["gas_m3"] for d in w["dagen"]] == [3.3, 0.5, None]  # 0,5 + 0,4 × 7
    assert w["dagen"][0]["gas_kosten"] == round(3.3 * 1.25, 2) and w["dagen"][0]["datum"] == "2026-10-10"
    assert w["nu"]["tijd"] == "2026-10-10T12:00:00+00:00" and w["locatie"]["naam"] == "De Bilt"


def test_gasmodel_zonder_stookweer_of_te_weinig_dagen(opslag):
    vandaag = date(2026, 7, 10)
    dagen = [vandaag - timedelta(days=i) for i in range(1, 13)]
    _historie(opslag, dagen, lambda gd: 0.6, [22.0] * 12)  # zomer: alleen warm water
    assert gasmodel(opslag, vandaag) == {"basis_m3": 0.6, "per_graaddag_m3": 0.0, "dagen": 12, "prijs": 1.25}
    assert gasmodel(opslag, date(2026, 6, 1)) is None  # nog geen meterdata
    assert graaddagen(None) is None and graaddagen(20) == 0.0 and graaddagen(12.34) == 5.7


@pytest.fixture
def app_weer(monkeypatch, tmp_path):
    monkeypatch.setenv("THUIS_DUCKDB_PAD", str(tmp_path / "w.duckdb"))
    monkeypatch.setenv("THUIS_AUTH_UIT", "1")
    with TestClient(api_mod.app) as c:
        yield c


def test_api_weer(app_weer):
    c = app_weer
    c.app.state.weer = WeerLive(NepBron())
    w = c.get("/api/weer").json()
    assert w["gas"] is None and w["dagen"][0]["gas_m3"] is None and w["locatie"]["bron"] == "instelling"

    class Plat:
        def verwachting(self, lat, lon):
            raise httpx.ConnectError("weg")

    c.app.state.weer = WeerLive(Plat())
    r = c.get("/api/weer", headers={"x-thuis-vers": "1"})
    assert r.status_code == 502 and "niet op te halen" in r.json()["detail"]
