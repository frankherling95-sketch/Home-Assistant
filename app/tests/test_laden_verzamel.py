from datetime import timedelta

from conftest import blokken, utc

from thuis.config import Config
from thuis.laden import STANDAARD, maak_plan, stuur
from thuis.opslag import schrijf_instellingen
from thuis.schema import AUTO, LADER, PRIJS
from thuis.verzamel import ronde

NU = utc(2026, 10, 7, 18, 0)  # 20:00 lokaal


class NepEasee:
    def __init__(self):
        self.acties = []

    def laders(self):
        return [{"id": "L", "naam": "Oprit"}]

    def meting(self, lader_id, naam=""):
        return {
            "tijd": NU,
            "lader_id": lader_id,
            "naam": naam,
            "status": "laden",
            "vermogen_kw": 11.0,
            "sessie_kwh": 1.0,
            "totaal_kwh": 500.0,
        }

    def pauzeer(self, lader_id):
        self.acties.append("pauzeer")

    def hervat(self, lader_id):
        self.acties.append("hervat")


def _vul(opslag, prijzen):
    opslag.voeg_toe(PRIJS, blokken(NU, prijzen))
    opslag.voeg_toe(AUTO, [{"tijd": NU, "auto_id": "A", "accu_pct": 60.0}])
    opslag.voeg_toe(LADER, [NepEasee().meting("L")])


def test_plan_kiest_goedkoopste_uur(opslag):
    _vul(opslag, [0.40, 0.10, 0.35] + [0.30] * 20)
    plan = maak_plan(opslag, STANDAARD, NU)
    assert plan["accu_pct"] == 60.0
    assert plan["blokken"][0]["prijs"] == 0.10
    assert plan["nu_laden"] is False and plan["reden"] == "wachten"


def test_stuur_alleen_als_aan_en_niet_herhalen(opslag):
    _vul(opslag, [0.40, 0.10, 0.35] + [0.30] * 20)
    e = NepEasee()
    assert stuur(opslag, e, NU) is None  # sturen staat standaard uit
    schrijf_instellingen(opslag, {"sturen": True})
    assert stuur(opslag, e, NU) == "pauzeer"
    opslag.voeg_toe(
        LADER, [{**NepEasee().meting("L"), "tijd": NU + timedelta(minutes=1), "status": "wacht_op_start"}]
    )
    assert stuur(opslag, e, NU + timedelta(minutes=1)) is None  # al gepauzeerd
    assert stuur(opslag, e, NU + timedelta(hours=1, minutes=1)) == "hervat"  # goedkoopste uur
    assert e.acties == ["pauzeer", "hervat"]


class NepFrank:
    def prijzen(self, start, eind):
        return blokken(NU, [0.2] * 4)

    def verbruik(self, dag):
        raise RuntimeError("Frank plat")


class NepWeer:
    def temperaturen(self, terug, vooruit):
        return [{"van": NU, "tot": NU + timedelta(hours=1), "temperatuur": 11.5}]


def test_ronde_bron_valt_los_uit(opslag, monkeypatch):
    monkeypatch.setenv("FRANK_EMAIL", "a@b.nl")
    monkeypatch.setenv("FRANK_WACHTWOORD", "x")
    monkeypatch.delenv("GOOGLE_CHAT_WEBHOOK", raising=False)
    uitslag = ronde(Config(), opslag, frank=NepFrank(), easee=NepEasee(), weer=NepWeer())
    assert uitslag["prijzen"] == "ok"
    assert uitslag["verbruik"].startswith("fout")
    assert (
        uitslag["lader"] == "ok"
        and uitslag["auto"] == uitslag["bmw"] == "overgeslagen"
        and uitslag["sturen"] == "ok"
    )
    assert uitslag["weer"] == "ok" and uitslag["meldingen"] == "overgeslagen"
    assert len(opslag.lees("SELECT * FROM {lader_meting}")) == 1
    assert opslag.lees("SELECT temperatuur FROM {weer}") == [{"temperatuur": 11.5}]
    log = {r["stap"]: r["uitslag"] for r in opslag.lees("SELECT stap, uitslag FROM {ronde}")}
    assert log["verbruik"] == "fout: Frank plat" and log["prijzen"] == "ok" and len(log) == 8


def test_geheimen_uit_een_json(monkeypatch):
    monkeypatch.setenv("THUIS_GEHEIMEN", '{"EASEE_GEBRUIKER": "u", "EASEE_WACHTWOORD": "p"}')
    monkeypatch.delenv("EASEE_GEBRUIKER", raising=False)
    assert Config().easee is True
