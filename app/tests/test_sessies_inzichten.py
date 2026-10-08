from datetime import date, timedelta

import pytest
from conftest import blokken, utc

from thuis.inzicht import dag_grenzen, periode_grenzen, periode_label, periodeoverzicht
from thuis.inzichten import euro, goedkoopste_venster, inzichten
from thuis.schema import LADER, PRIJS, STUURACTIE, VERBRUIK, WEER
from thuis.sessies import laadsessies, vind_sessies

PLUG = utc(2026, 10, 6, 16, 15)  # 18:15 lokaal


def _meting(t, status, totaal, sessie, kw=0.0, lader="L"):
    return {
        "tijd": t,
        "lader_id": lader,
        "naam": "Oprit",
        "status": status,
        "vermogen_kw": kw,
        "sessie_kwh": sessie,
        "totaal_kwh": totaal,
    }


def _laadnacht(opslag):
    """Ingeplugd om 18:15, Slim laden wacht tot 03:00 (goedkoop), 7,5 kWh, uitgeplugd om 08:00."""
    metingen = [_meting(PLUG - timedelta(minutes=15), "niet_verbonden", 100.0, 4.0)]
    t = PLUG
    while t < utc(2026, 10, 7, 1):
        metingen.append(_meting(t, "wacht_op_start", 100.0, 0.0))
        t += timedelta(minutes=15)
    for i, status in enumerate(("laden", "laden", "laden", "klaar")):
        metingen.append(_meting(t, status, 100 + 2.5 * i, 2.5 * i, kw=10.0 if status == "laden" else 0.0))
        t += timedelta(minutes=15)
    metingen.append(_meting(utc(2026, 10, 7, 6), "niet_verbonden", 107.5, 7.5))
    opslag.voeg_toe(LADER, metingen)
    # 18:00–03:00 lokaal duur, daarna goedkoop
    opslag.voeg_toe(PRIJS, blokken(utc(2026, 10, 6, 16), [0.40] * 9 + [0.10] * 5 + [0.30] * 10))
    opslag.voeg_toe(STUURACTIE, [{"tijd": PLUG + timedelta(minutes=5), "lader_id": "L", "actie": "pauzeer"}])


def test_sessie_van_inpluggen_tot_uitpluggen(opslag):
    _laadnacht(opslag)
    [s] = laadsessies(opslag, utc(2026, 10, 6), utc(2026, 10, 8))
    assert s["start"] == PLUG and s["eind"] == utc(2026, 10, 7, 1, 45)
    assert s["kwh"] == 7.5 and s["kosten"] == 0.75 and s["gem_prijs"] == 0.1
    assert s["slim"] is True and s["klaar"] is True
    assert s["besparing"] == 2.25  # direct: 7,5 kWh in 45 min vanaf 18:15 à € 0,40


def test_sessie_buiten_venster_en_zonder_lading(opslag):
    _laadnacht(opslag)
    assert laadsessies(opslag, utc(2026, 10, 7), utc(2026, 10, 8)) == []  # begon de dag ervoor
    leeg = [
        _meting(utc(2026, 10, 9, h), s, 50.0, 0.0) for h, s in ((1, "wacht_op_start"), (2, "niet_verbonden"))
    ]
    assert vind_sessies(leeg) == []


def test_teruggesprongen_teller_is_nieuwe_sessie_en_offline_breekt_niet():
    t = utc(2026, 10, 9, 0)
    m = [
        _meting(t, "laden", 10.0, 1.0),
        _meting(t + timedelta(minutes=15), "laden", 12.0, 3.0),
        _meting(t + timedelta(minutes=30), "offline", 14.0, 5.0),
        _meting(t + timedelta(minutes=45), "laden", 15.0, 0.5),  # uitpluggen gemist: teller terug
        _meting(t + timedelta(minutes=60), "klaar", 17.0, 2.5),
    ]
    a, b = vind_sessies(m)
    assert a["kwh"] == 4.0 and a["uitgeplugd"] is True
    assert b["kwh"] == 3.0 and b["start"] == t + timedelta(minutes=30) and b["uitgeplugd"] is False


def test_periodes_en_labels():
    assert periode_grenzen("week", date(2026, 10, 8)) == (date(2026, 10, 5), date(2026, 10, 11))
    assert periode_grenzen("week", date(2026, 10, 11)) == (date(2026, 10, 5), date(2026, 10, 11))
    assert periode_grenzen("maand", date(2028, 2, 10)) == (date(2028, 2, 1), date(2028, 2, 29))
    assert periode_grenzen("jaar", date(2026, 6, 1)) == (date(2026, 1, 1), date(2026, 12, 31))
    assert periode_label("week", date(2026, 10, 5), date(2026, 10, 11)) == "5 – 11 okt 2026"
    assert periode_label("week", date(2026, 9, 28), date(2026, 10, 4)) == "28 sep – 4 okt 2026"
    assert periode_label("week", date(2025, 12, 29), date(2026, 1, 4)) == "29 dec 2025 – 4 jan 2026"
    assert periode_label("maand", date(2026, 10, 1), date(2026, 10, 31)) == "oktober 2026"


def _uren(soort, dag, per_uur, prijs, uren=range(24)):
    start, _ = dag_grenzen(dag)
    return [
        {
            "soort": soort,
            "van": start + timedelta(hours=h),
            "tot": start + timedelta(hours=h + 1),
            "hoeveelheid": per_uur,
            "kosten": per_uur * prijs,
            "eenheid": "m3" if soort == "gas" else "kWh",
        }
        for h in uren
    ]


def _temperatuur(dag, graden):
    start, _ = dag_grenzen(dag)
    return [
        {"van": start + timedelta(hours=h), "tot": start + timedelta(hours=h + 1), "temperatuur": graden}
        for h in range(24)
    ]


def test_week_per_dag_met_vorige_week(opslag):
    rijen = _uren("stroom", date(2026, 10, 5), 0.5, 0.2) + _uren("gas", date(2026, 10, 6), 0.1, 1.3)
    rijen += _uren("teruglevering", date(2026, 10, 6), 1.0, 0.1, uren=range(10, 14))
    rijen += _uren("stroom", date(2026, 9, 30), 0.25, 0.2)  # vorige week
    opslag.voeg_toe(VERBRUIK, rijen)
    opslag.voeg_toe(WEER, _temperatuur(date(2026, 10, 5), 8.0))
    _laadnacht(opslag)

    p = periodeoverzicht(opslag, "week", date(2026, 10, 8))
    assert p["van"] == "2026-10-05" and p["tot"] == "2026-10-11" and p["label"] == "5 – 11 okt 2026"
    assert p["bakje_labels"][:2] == ["ma 5", "di 6"] and len(p["bakjes"]) == 7
    r = p["reeksen"]
    assert r["stroom"][:3] == [12.0, 0.0, None]  # dag zonder meterdata: None, niet 0
    assert r["gas"][1] == pytest.approx(2.4) and r["teruglevering"][1] == 4.0
    assert r["kosten"][:2] == [2.4, pytest.approx(2.4 * 1.3 - 0.4)]
    assert r["temperatuur"][:2] == [8.0, None]
    assert r["laden"][:3] == [0.0, 0.0, 7.5]  # laden telt op de dag van de meting
    assert p["totalen"]["laden"] == {"hoeveelheid": 7.5, "kosten": 0.75, "eenheid": "kWh"}
    assert p["totalen"]["teruglevering"]["kosten"] == -0.4
    assert p["vorige"]["stroom"]["hoeveelheid"] == 6.0 and p["vorige_label"] == "28 sep – 4 okt 2026"


def test_jaar_per_maand(opslag):
    opslag.voeg_toe(
        VERBRUIK, _uren("gas", date(2026, 1, 15), 0.5, 1.4) + _uren("gas", date(2025, 3, 1), 0.1, 1.2)
    )
    p = periodeoverzicht(opslag, "jaar", date(2026, 7, 1))
    assert (
        p["bakjes"][0] == "2026-01"
        and p["bakje_labels"][:3] == ["jan", "feb", "mrt"]
        and len(p["bakjes"]) == 12
    )
    assert p["reeksen"]["gas"][:2] == [12.0, None]
    assert p["totalen"]["gas"]["kosten"] == 16.8 and p["vorige"]["gas"]["hoeveelheid"] == 2.4


def test_goedkoopste_venster_over_kwartieren():
    b = blokken(utc(2026, 10, 7, 0), [0.3, 0.1, 0.1, 0.1, 0.1, 0.2, 0.05, 0.4], minuten=15)
    van, tot, gem = goedkoopste_venster(b, 1)
    assert van == utc(2026, 10, 7, 0, 15) and tot - van == timedelta(hours=1) and gem == pytest.approx(0.1)
    assert goedkoopste_venster(b[:3], 1) is None


def test_euro_notatie():
    assert euro(1234.5) == "€ 1.234,50" and euro(-0.05, 3) == "€ -0,050"


def test_inzichten(opslag):
    dag, moment = date(2026, 10, 7), utc(2026, 10, 7, 12)
    morgen = dag_grenzen(dag + timedelta(days=1))[0]
    opslag.voeg_toe(PRIJS, blokken(morgen, [0.25] * 11 + [-0.05] + [0.25] * 12))  # 11:00 lokaal negatief
    _laadnacht(opslag)
    rijen = []
    for i in range(14):  # gas: elke dag 2 m³; deze week warmer (10 °C) dan vorige week (8 °C)
        d = dag - timedelta(days=i + 1)
        rijen += _uren("gas", d, 2 / 24, 1.3)
        opslag.voeg_toe(WEER, _temperatuur(d, 10.0 if i < 7 else 8.0))
    for d in range(1, 7):
        rijen += _uren("stroom", date(2026, 10, d), 0.5, 0.25) + _uren("stroom", date(2026, 9, d), 0.5, 0.20)
    opslag.voeg_toe(VERBRUIK, rijen)

    uit = {i["id"]: i for i in inzichten(opslag, dag, moment)}
    assert list(uit)[:2] == ["negatieve_prijzen", "goedkoopste_morgen"]
    assert uit["negatieve_prijzen"]["waarde"] == "morgen 11:00 – 12:00"
    assert uit["goedkoopste_morgen"]["waarde"] == "11:00 – 12:00"
    assert uit["besparing_laden"]["waarde"] == "€ 2,25" and uit["besparing_laden"]["toon"] == "goed"
    assert uit["kosten_maand"]["toon"] == "let_op"  # oktober duurder dan dezelfde dagen in september
    assert uit["gem_laadprijs"]["waarde"] == "€ 0,100/kWh" and uit["gem_laadprijs"]["toon"] == "goed"
    gas = uit["gas_vs_vorige_week"]
    assert gas["waarde"] == "+25%" and gas["toon"] == "let_op" and gas["icoon"] == "trend_op"
    assert {i["toon"] for i in uit.values()} <= {"goed", "neutraal", "let_op"}


def test_inzichten_zonder_data(opslag):
    assert inzichten(opslag, date(2026, 10, 7), utc(2026, 10, 7, 12)) == []
