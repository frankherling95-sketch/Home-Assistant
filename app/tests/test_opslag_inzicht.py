from datetime import date, timedelta

from conftest import blokken, utc

from thuis.inzicht import dag_grenzen, dagoverzicht, laden_per_uur
from thuis.opslag import lees_instellingen, schrijf_instellingen
from thuis.schema import LADER, PRIJS, VERBRUIK


def test_actueel_neemt_laatst_opgehaalde_rij(opslag):
    van = utc(2026, 10, 7, 10)
    opslag.voeg_toe(PRIJS, [{**blokken(van, [0.20])[0], "opgehaald": utc(2026, 10, 7, 9)}])
    opslag.voeg_toe(PRIJS, [{**blokken(van, [0.25])[0], "opgehaald": utc(2026, 10, 7, 9, 15)}])
    rijen = opslag.lees("SELECT allin, van FROM {prijs}")
    assert [r["allin"] for r in rijen] == [0.25]
    assert rijen[0]["van"] == van  # terug als UTC-datetime


def test_dag_grenzen_zomertijdwissel():
    start, eind = dag_grenzen(date(2026, 10, 25))  # klok gaat een uur terug: 25 uur
    assert eind - start == timedelta(hours=25)
    assert start == utc(2026, 10, 24, 22)


def test_laden_per_uur_uit_meterstand():
    m = [
        {"tijd": utc(2026, 10, 7, 1, 50), "lader_id": "L", "totaal_kwh": 100.0},
        {"tijd": utc(2026, 10, 7, 2, 5), "lader_id": "L", "totaal_kwh": 102.5},
        {"tijd": utc(2026, 10, 7, 2, 20), "lader_id": "L", "totaal_kwh": 105.0},
        {"tijd": utc(2026, 10, 7, 3, 5), "lader_id": "L", "totaal_kwh": 1.0},  # reset: telt niet
    ]
    assert laden_per_uur(m) == {utc(2026, 10, 7, 2): 5.0}


def test_dagoverzicht_totalen(opslag):
    dag = date(2026, 10, 7)
    start, _ = dag_grenzen(dag)
    opslag.voeg_toe(PRIJS, blokken(start, [0.30] * 24))
    opslag.voeg_toe(
        VERBRUIK,
        [
            {
                "soort": "stroom",
                "van": start + timedelta(minutes=15 * i),
                "tot": start + timedelta(minutes=15 * (i + 1)),
                "hoeveelheid": 0.25,
                "kosten": 0.075,
                "eenheid": "kWh",
            }
            for i in range(8)
        ]
        + [
            {
                "soort": "teruglevering",
                "van": start + timedelta(hours=12),
                "tot": start + timedelta(hours=13),
                "hoeveelheid": 1.5,
                "kosten": 0.30,
                "eenheid": "kWh",
            }
        ],
    )
    opslag.voeg_toe(
        LADER,
        [
            {"tijd": start + timedelta(hours=2, minutes=m), "lader_id": "L", "totaal_kwh": 100 + k}
            for m, k in ((0, 0), (30, 5), (59, 11))
        ],
    )
    d = dagoverzicht(opslag, dag)
    assert len(d["uren"]) == 24
    assert d["reeksen"]["stroom"][:3] == [1.0, 1.0, 0]
    assert d["totalen"]["stroom"] == {"hoeveelheid": 2.0, "kosten": 0.6, "eenheid": "kWh"}
    assert d["totalen"]["teruglevering"]["kosten"] == -0.3
    assert d["reeksen"]["kosten_stroom"][12] == -0.3
    assert d["totalen"]["laden"]["hoeveelheid"] == 11.0
    assert d["totalen"]["laden"]["kosten"] == 3.3


def test_instellingen_roundtrip(opslag):
    std = {"doel_pct": 80, "sturen": False}
    assert lees_instellingen(opslag, std) == std
    schrijf_instellingen(opslag, {"doel_pct": 90, "onbekend": 1})
    assert lees_instellingen(opslag, std) == {"doel_pct": 90, "sturen": False}


def test_alleen_gewijzigde_rijen_erbij(opslag):
    from thuis.opslag import voeg_toe_gewijzigd

    van = utc(2026, 10, 7, 10)
    assert voeg_toe_gewijzigd(opslag, PRIJS, blokken(van, [0.20, 0.21])) == 2
    assert voeg_toe_gewijzigd(opslag, PRIJS, blokken(van, [0.20, 0.21])) == 0  # zelfde ronde nog eens
    assert voeg_toe_gewijzigd(opslag, PRIJS, blokken(van, [0.20, 0.25, 0.30])) == 2  # gewijzigd + nieuw
    assert [r["allin"] for r in opslag.lees("SELECT allin FROM {prijs} ORDER BY van")] == [0.20, 0.25, 0.30]
