import json
import time
import types
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from test_bmw import NU, SESSIE, VIN, VOL, _record

from thuis import api as api_mod
from thuis.auto import auto_overzicht, km_per_dag
from thuis.connectors import bmw_gegevens as G
from thuis.connectors.bmw import API, BMW, CONTAINER_DOEL, CONTAINER_DOEL_KERN, naar_details, naar_rij
from thuis.connectors.kia import naar_details as kia_details
from thuis.connectors.kia import naar_rij as kia_rij
from thuis.laden import STANDAARD, maak_plan
from thuis.opslag import DuckOpslag, nu, schrijf_instellingen
from thuis.schema import AUTO, AUTO_DETAILS, AUTO_LAADSESSIE

# ── van BMW naar Thuis ────────────────────────────────────────────────────────


def test_naar_details_per_groep():
    d = naar_details(VOL["telematicData"], {"model": "i4 eDrive40"})
    laden, rijden, onderhoud = d["laden"], d["rijden"], d["onderhoud"]
    assert laden["vermogen_kw"] == 10.95 and laden["resttijd_min"] == 95 and laden["doel_pct"] == 80
    assert laden["capaciteit_kwh"] == 80.7 and laden["gezondheid_pct"] == 97 and laden["fasen"] == "3-PHASES"
    assert rijden["km_stand"] == 12345 and rijden["verbruik_kwh_100km"] == 17.3
    assert rijden["rit"]["eind"] == "2026-10-07T18:42:00+00:00"  # "dd.mm.yyyy hh:mm:ss UTC"
    assert onderhoud["apk"] == "2028-09-30T23:00:00+00:00"
    assert onderhoud["meldingen"] == [{"name": "Bandenspanning", "severity": "LOW"}]
    assert onderhoud["banden"] == {"linksvoor": {"bar": 2.5, "doel_bar": 2.6}}  # kPa → bar, lege weg
    assert d["beveiliging"]["slot"] == "SECURED" and d["beveiliging"]["deuren_open"] == {"linksvoor": False}
    assert (d["locatie"]["lat"], d["locatie"]["lon"]) == (52.09073, 5.12142) and d["basis"] == {
        "model": "i4 eDrive40"
    }
    assert laden["bijgewerkt"] == "2026-10-08T11:55:00+00:00" and "klimaat" not in d  # niets doorgegeven


def test_naar_rij_vult_extra_kolommen():
    rij = naar_rij(VIN, "BMW i4", VOL["telematicData"], NU)
    assert rij["km_stand"] == 12345 and rij["laadvermogen_kw"] == 10.95 and rij["laadtijd_min"] == 95
    assert rij["doel_pct"] == 80 and rij["capaciteit_kwh"] == 80.7 and rij["kwh_tot_vol"] == 26.4
    stil = {**VOL["telematicData"], G.LAADSTATUS: {"value": "NOCHARGING"}}
    rij = naar_rij(VIN, "BMW i4", stil, NU)
    assert rij["laadt"] is False and rij["laadvermogen_kw"] == 0.0 and rij["laadtijd_min"] is None


def test_laadsessies_van_bmw():
    [s] = G.naar_laadsessies(VIN, [SESSIE, {"geen": "start"}])
    assert s["start"] == datetime.fromtimestamp(1791400000, UTC) and s["eind"] - s["start"] == timedelta(
        hours=1
    )
    assert s["plaats"] == "Fastned, Utrecht" and s["publiek"] and s["kosten"] == 24.3 and s["valuta"] == "EUR"
    assert s["km_stand"] == 11265.4 and s["start_pct"] == 22 and s["eind_pct"] == 80  # mijlen → km


# ── container: nieuwe versie en terugval ──────────────────────────────────────


@respx.mock
def test_oude_container_wordt_vervangen():
    respx.get(f"{API}/customers/containers").mock(
        return_value=httpx.Response(
            200,
            json={
                "containers": [{"containerId": "C1", "name": "Thuis", "purpose": "Thuis energieplatform v1"}]
            },
        )
    )
    weg = respx.delete(f"{API}/customers/containers/C1").mock(return_value=httpx.Response(204))
    maak = respx.post(f"{API}/customers/containers").mock(
        return_value=httpx.Response(201, json={"containerId": "C2"})
    )
    lees = respx.get(f"{API}/customers/vehicles/{VIN}/telematicData").mock(
        return_value=httpx.Response(200, json=VOL)
    )
    b = BMW(_record(container_doel=None))  # gekoppeld met versie 1
    b.metingen(NU)
    assert weg.called and json.loads(maak.calls[0].request.content)["purpose"] == CONTAINER_DOEL
    assert (
        lees.calls[0].request.url.params["containerId"] == "C2"
        and b.record["container_doel"] == CONTAINER_DOEL
    )
    assert b.details and json.loads(b.details[0]["gegevens"])["laden"]["doel_pct"] == 80


@respx.mock
def test_weigert_bmw_de_grote_lijst_dan_een_week_de_kern():
    respx.get(f"{API}/customers/containers").mock(return_value=httpx.Response(200, json={"containers": []}))
    maak = respx.post(f"{API}/customers/containers").mock(
        side_effect=[
            httpx.Response(400, json={"exveErrorId": "CU-402", "exveErrorMsg": "Telematic key is invalid"}),
            httpx.Response(201, json={"containerId": "K1"}),
        ]
    )
    respx.get(f"{API}/customers/vehicles/{VIN}/telematicData").mock(
        return_value=httpx.Response(200, json=VOL)
    )
    b = BMW(_record(container_doel=None))
    b.metingen(NU)
    tweede = json.loads(maak.calls[1].request.content)
    assert tweede["purpose"] == CONTAINER_DOEL_KERN and set(tweede["technicalDescriptors"]) == set(G.KERN)
    assert b.record["container_id"] == "K1" and b.record["kern_tot"] > time.time() + 6 * 86400
    # De volgende keer niet opnieuw proberen (dat kost verzoeken), pas na een week.
    b.record["laatst"] = None
    b.metingen(NU)
    assert maak.call_count == 2


@respx.mock
def test_laadhistorie_en_autogegevens_niet_te_vaak():
    historie = respx.get(f"{API}/customers/vehicles/{VIN}/chargingHistory").mock(
        return_value=httpx.Response(200, json={"data": [SESSIE]})
    )
    basis = respx.get(f"{API}/customers/vehicles/{VIN}/basicData").mock(
        return_value=httpx.Response(
            200, json={"brand": "BMW", "modelName": "i4 eDrive35", "colourCode": "475"}
        )
    )
    respx.get(f"{API}/customers/vehicles/{VIN}/telematicData").mock(
        return_value=httpx.Response(200, json=VOL)
    )
    b = BMW(_record(historie_op=None, basis_op=time.time() - 8 * 86400))
    [rij] = b.metingen(NU)
    assert historie.call_count == 1 and basis.call_count == 1 and len(b.laadsessies) == 1
    assert rij["naam"] == "BMW i4 eDrive35" and b.record["basis"]["kleurcode"] == "475"
    b.record["laatst"] = None
    b.metingen(NU + timedelta(hours=1))  # zelfde dag: geen nieuwe historie, geen autogegevens
    assert historie.call_count == 1 and basis.call_count == 1 and b.laadsessies == []
    # Krap budget: dan alleen de accu.
    b.record.update(laatst=None, historie_op=None, vragen=[time.time()] * 35)
    b.metingen(NU + timedelta(days=1))
    assert historie.call_count == 1


# ── Kia / Hyundai ─────────────────────────────────────────────────────────────


def _kia(**extra):
    basis = dict(
        id="1",
        name="EV6",
        model="EV6",
        year=2023,
        ev_battery_percentage=55,
        ev_driving_range=280,
        ev_driving_range_unit="km",
        ev_battery_is_plugged_in=True,
        ev_battery_is_charging=True,
        ev_charging_power=10.8,
        ev_estimated_current_charge_duration=120,
        ev_charge_limits_ac=90,
        ev_charge_limits_dc=80,
        ev_battery_soh_percentage=98,
        ev_battery_capacity=77400,  # Wh
        odometer=23456.0,
        odometer_unit="km",
        is_locked=False,
        front_left_door_is_open=True,
        front_left_window_is_open=False,
        tire_pressure_front_left=2.7,
        tire_pressure_unit=2,  # bar
        washer_fluid_warning_is_on=True,
        car_battery_percentage=81,
        location_latitude=52.1,
        location_longitude=5.18,
        last_updated_at=datetime(2026, 10, 8, 11, 50),
    )
    return types.SimpleNamespace(**{**basis, **extra})


def test_kia_vult_dezelfde_groepen():
    v = _kia()
    rij = kia_rij(v, NU)
    assert rij["km_stand"] == 23456 and rij["doel_pct"] == 90 and rij["capaciteit_kwh"] == 77.4
    assert rij["laadvermogen_kw"] == 10.8 and rij["laadtijd_min"] == 120
    d = kia_details(v, "kia")
    assert d["laden"]["gezondheid_pct"] == 98 and d["laden"]["doel_snelladen_pct"] == 80
    assert d["onderhoud"]["banden"] == {"linksvoor": {"bar": 2.7}}
    assert d["onderhoud"]["meldingen"] == [{"naam": "Ruitensproeiervloeistof bijvullen"}]
    assert d["beveiliging"]["slot"] == "UNLOCKED" and d["beveiliging"]["deuren_open"] == {"linksvoor": True}
    assert d["beveiliging"]["ramen"] == {"linksvoor": "CLOSED"} and d["locatie"] == {"lat": 52.1, "lon": 5.18}
    assert d["basis"] == {"merk": "Kia", "model": "EV6", "bouwdatum": "2023"}
    assert d["laden"]["bijgewerkt"] == "2026-10-08T11:50:00+00:00"
    # Bandenspanning in psi, capaciteit zonder bruikbare eenheid.
    v = _kia(tire_pressure_front_left=38, tire_pressure_unit=0, ev_battery_capacity=3)
    assert (
        kia_details(v)["onderhoud"]["banden"]["linksvoor"]["bar"] == 2.62
        and kia_rij(v, NU)["capaciteit_kwh"] is None
    )


# ── pagina Auto ───────────────────────────────────────────────────────────────


def _vul(o: DuckOpslag, moment: datetime) -> None:
    rijen = []
    for uur in range(0, 24 * 10, 6):  # tien dagen, elke zes uur; 50 km per dag
        t = moment - timedelta(hours=uur)
        rijen.append(
            {
                "tijd": t,
                "auto_id": VIN,
                "naam": "BMW i4",
                "accu_pct": 60.0,
                "km_stand": 10000 + (240 - uur) / 24 * 50,
                "laadt": False,
            }
        )
    o.voeg_toe(AUTO, rijen)
    details = naar_details(VOL["telematicData"], {"model": "i4"})
    o.voeg_toe(AUTO_DETAILS, [{"tijd": moment, "auto_id": VIN, "gegevens": json.dumps(details)}])
    s = G.naar_laadsessies(VIN, [{**SESSIE, "startTime": int((moment - timedelta(days=2)).timestamp())}])
    o.voeg_toe(AUTO_LAADSESSIE, s)


def test_km_per_dag_uit_de_kilometerstand():
    t = datetime(2026, 10, 1, 10, tzinfo=UTC)
    rijen = [{"tijd": t + timedelta(hours=h), "km_stand": 100 + h} for h in (0, 5, 24, 30, 48)]
    assert km_per_dag(rijen) == [{"dag": "2026-10-02", "km": 25.0}, {"dag": "2026-10-03", "km": 18.0}]
    assert km_per_dag([{"tijd": t, "km_stand": None}]) == []


def test_auto_overzicht_met_thuis(opslag):
    moment = nu()
    _vul(opslag, moment)
    a = auto_overzicht(opslag, moment)
    assert a["auto"]["naam"] == "BMW i4" and a["details"]["laden"]["doel_pct"] == 80
    assert a["km"]["zeven_dagen"] == pytest.approx(350, abs=1) and len(a["km_per_dag"]) >= 9
    assert a["accu"] and all(p["tijd"] >= (moment - timedelta(days=7)).isoformat() for p in a["accu"])
    assert a["laden_30_dagen"] == {"sessies": 1, "kwh": 41.2, "kwh_onderweg": 41.2}
    assert "thuis" not in a["laadsessies"][0] and "lat" not in a["laadsessies"][0]
    schrijf_instellingen(opslag, {"auto_thuis": {"lat": 52.0907, "lon": 5.1214}})
    a = auto_overzicht(opslag, moment)
    assert a["details"]["locatie"]["thuis"] and a["details"]["locatie"]["afstand_km"] == 0.0
    assert a["laadsessies"][0]["thuis"] is True  # 52.09/5.12 ligt binnen 300 m
    assert auto_overzicht(_leeg())["auto"] is None


def _leeg() -> DuckOpslag:
    o = DuckOpslag(":memory:")
    o.maak_tabellen()
    return o


def test_api_auto_en_thuis(monkeypatch, tmp_path):
    monkeypatch.setenv("THUIS_DUCKDB_PAD", str(tmp_path / "a.duckdb"))
    monkeypatch.setenv("THUIS_AUTH_UIT", "1")
    with TestClient(api_mod.app) as c:
        assert c.get("/api/auto").json() == {"auto": None}
        assert c.put("/api/auto/thuis").status_code == 409  # nog geen locatie
        _vul(c.app.state.opslag, nu())
        a = c.put("/api/auto/thuis").json()
        assert a["thuis"] == {"lat": 52.09073, "lon": 5.12142} and a["details"]["locatie"]["thuis"]
        assert c.delete("/api/auto/thuis").json()["thuis"] is None


# ── laadplan en opslag ────────────────────────────────────────────────────────


def test_laadplan_rekent_met_inhoud_en_laaddoel_van_de_auto(opslag):
    moment = datetime(2026, 10, 8, 18, tzinfo=UTC)
    auto = {"accu_pct": 50.0, "capaciteit_kwh": 80.0, "doel_pct": 70.0}
    p = maak_plan(opslag, dict(STANDAARD), moment, auto=auto)
    assert (
        p["doel_pct"] == 70 and p["doel_van_auto"] and p["capaciteit_kwh"] == 80 and p["capaciteit_van_auto"]
    )
    assert p["nodig_kwh"] == pytest.approx(20 / 100 * 80 / 0.9, abs=0.1)
    p = maak_plan(opslag, dict(STANDAARD), moment, auto={"accu_pct": 50.0, "doel_pct": 100.0})
    assert p["doel_pct"] == 80 and not p["doel_van_auto"] and p["capaciteit_kwh"] == 77.4


def test_oude_tabel_krijgt_nieuwe_kolommen(tmp_path):
    o = DuckOpslag(str(tmp_path / "oud.duckdb"))
    o.con.execute(
        "CREATE TABLE thuis.auto_meting (tijd TIMESTAMPTZ, auto_id VARCHAR, naam VARCHAR, accu_pct DOUBLE, "
        "bereik_km DOUBLE, ingeplugd BOOLEAN, laadt BOOLEAN, bijgewerkt TIMESTAMPTZ, opgehaald TIMESTAMPTZ)"
    )
    o.con.execute("INSERT INTO thuis.auto_meting (tijd, auto_id, accu_pct) VALUES (now(), 'x', 50)")
    o.maak_tabellen()
    o.voeg_toe(AUTO, [{"tijd": nu(), "auto_id": "x", "accu_pct": 60.0, "km_stand": 100.0}])
    rijen = o.lees("SELECT accu_pct, km_stand FROM thuis.auto_meting ORDER BY accu_pct")
    assert rijen == [{"accu_pct": 50.0, "km_stand": None}, {"accu_pct": 60.0, "km_stand": 100.0}]
