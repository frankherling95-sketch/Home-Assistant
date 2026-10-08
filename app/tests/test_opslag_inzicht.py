from datetime import date, timedelta

from conftest import blokken, utc

from thuis.inzicht import dag_grenzen, dagoverzicht, laad_intervallen, laden_per_uur
from thuis.opslag import lees_instellingen, schrijf_instellingen
from thuis.schema import AUTO, LADER, PRIJS, VERBRUIK, WEER


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


def test_laden_per_uur_uit_meterstand(opslag):
    opslag.voeg_toe(
        LADER,
        [
            {"tijd": utc(2026, 10, 7, 1, 50), "lader_id": "L", "totaal_kwh": 100.0},
            {"tijd": utc(2026, 10, 7, 2, 5), "lader_id": "L", "totaal_kwh": 102.5},
            {"tijd": utc(2026, 10, 7, 2, 20), "lader_id": "L", "totaal_kwh": 105.0},
            {"tijd": utc(2026, 10, 7, 3, 5), "lader_id": "L", "totaal_kwh": 1.0},  # reset: telt niet
            {
                "tijd": utc(2026, 10, 7, 3, 5),
                "lader_id": "M",
                "totaal_kwh": 7.0,
            },  # andere lader, eerste meting
        ],
    )
    intervallen = laad_intervallen(opslag, utc(2026, 10, 7, 2), utc(2026, 10, 7, 4))
    assert [(i["van"], i["kwh"]) for i in intervallen] == [
        (utc(2026, 10, 7, 1, 50), 2.5),
        (utc(2026, 10, 7, 2, 5), 2.5),
    ]
    assert laden_per_uur(intervallen) == {utc(2026, 10, 7, 2): 5.0}


def test_bulk_invoegen_met_lege_waarden_en_booleans(opslag):
    n = opslag.voeg_toe(
        AUTO,
        [
            {"tijd": utc(2026, 3, 29, 1, i), "auto_id": "A", "accu_pct": None, "ingeplugd": i % 2 == 0}
            for i in range(60)
        ],
    )
    rijen = opslag.lees("SELECT * FROM {auto_meting} ORDER BY tijd")
    assert n == 60 and len(rijen) == 60
    assert rijen[0]["accu_pct"] is None and rijen[0]["ingeplugd"] is True and rijen[1]["ingeplugd"] is False
    assert rijen[59]["tijd"] == utc(2026, 3, 29, 1, 59) and rijen[0]["opgehaald"].tzinfo is not None


def test_lokale_dag_in_sql(opslag):
    opslag.voeg_toe(PRIJS, blokken(utc(2026, 10, 24, 21), [0.1] * 4))  # 23:00 t/m 02:00 lokaal
    rijen = opslag.lees(
        f"SELECT {opslag.lokale_dag('van')} AS dag, COUNT(*) AS n FROM {{prijs}} GROUP BY dag ORDER BY dag"
    )
    assert [(r["dag"], r["n"]) for r in rijen] == [(date(2026, 10, 24), 1), (date(2026, 10, 25), 3)]


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
    opslag.voeg_toe(
        WEER,
        [
            {"van": start + timedelta(hours=h), "tot": start + timedelta(hours=h + 1), "temperatuur": 9.5}
            for h in (0, 1)
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
    assert d["reeksen"]["temperatuur"][:3] == [9.5, 9.5, None]


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
