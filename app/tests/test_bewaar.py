import threading

from fastapi.testclient import TestClient

from thuis import api as api_mod
from thuis.bewaar import KWARTIER_S, Bewaard
from thuis.opslag import nu, tegelijk
from thuis.schema import RONDE


class Klok:
    def __init__(self) -> None:
        self.t = 10 * KWARTIER_S + 1.0

    def __call__(self) -> float:
        return self.t


def teller():
    gemaakt = []

    def maak():
        gemaakt.append(1)
        return len(gemaakt)

    return maak


def ronde(opslag, tijd):
    opslag.voeg_toe(RONDE, [{"tijd": tijd, "stap": "prijzen", "uitslag": "ok", "duur_s": 1.0}])


def test_bewaart_tot_een_nieuwe_ronde(opslag):
    klok, maak = Klok(), teller()
    b = Bewaard(klok)
    assert b.haal("dag", opslag, maak) == 1
    assert b.haal("dag", opslag, maak) == 1  # bewaard
    assert b.haal("nu", opslag, maak) == 2  # ander verzoek, eigen antwoord
    ronde(opslag, nu())
    assert b.haal("dag", opslag, maak) == 1  # de laatste ronde wordt hooguit eens per minuut bekeken
    klok.t += 61
    assert b.haal("dag", opslag, maak) == 3  # nieuwe ronde: opnieuw gemaakt
    assert b.haal("dag", opslag, maak) == 3


def test_nieuw_kwartier_vers_en_leeg(opslag):
    klok, maak = Klok(), teller()
    b = Bewaard(klok)
    assert b.haal("nu", opslag, maak) == 1
    assert b.haal("nu", opslag, maak, vers=True) == 2  # x-thuis-vers: altijd opnieuw, en bewaard
    assert b.haal("nu", opslag, maak) == 2
    klok.t += KWARTIER_S  # "nu" schuift op
    assert b.haal("nu", opslag, maak) == 3
    b.leeg()
    assert b.haal("nu", opslag, maak) == 4


def test_status_meldt_de_laatste_ronde(opslag):
    b, maak = Bewaard(Klok()), teller()
    b.zet_ronde("2026-10-09T10:00:00+00:00")
    assert b.haal("dag", opslag, maak) == 1
    b.zet_ronde("2026-10-09T10:00:00+00:00")  # dezelfde ronde: bewaard blijft bewaard
    assert b.haal("dag", opslag, maak) == 1
    b.zet_ronde("2026-10-09T10:15:00+00:00")
    assert b.haal("dag", opslag, maak) == 2


def test_tegelijk_houdt_de_volgorde(opslag):
    class Parallel:
        parallel_lezen = True

    draden = set()

    def taak(n):
        def f():
            draden.add(threading.get_ident())
            return n

        return f

    assert tegelijk(Parallel(), taak(1), taak(2), taak(3)) == [1, 2, 3]
    assert threading.get_ident() not in draden  # in eigen threads
    draden.clear()
    assert tegelijk(opslag, taak(1), taak(2)) == [1, 2]  # DuckDB: na elkaar, in deze thread
    assert draden == {threading.get_ident()}


def test_api_bewaart_en_een_wijziging_maakt_leeg(monkeypatch, tmp_path):
    monkeypatch.setenv("THUIS_DUCKDB_PAD", str(tmp_path / "b.duckdb"))
    monkeypatch.setenv("THUIS_AUTH_UIT", "1")
    monkeypatch.setenv("THUIS_BEWAREN", "1")
    with TestClient(api_mod.app) as c:
        o = c.app.state.opslag
        vragen = []
        lees = o.lees
        monkeypatch.setattr(o, "lees", lambda sql, **p: vragen.append(sql) or lees(sql, **p))

        def aantal(pad, **kw):
            voor = len(vragen)
            assert c.get(pad, **kw).status_code == 200
            return len(vragen) - voor

        assert aantal("/api/nu") > 0
        assert aantal("/api/nu") == 0  # uit het geheugen
        assert aantal("/api/nu", headers={"x-thuis-vers": "1"}) > 0
        instellingen = c.get("/api/instellingen").json()
        assert c.put("/api/instellingen", json={**instellingen, "doel_pct": 70}).status_code == 200
        assert aantal("/api/nu") > 0  # na een wijziging opnieuw
        assert c.get("/api/nu").json()["instellingen"]["doel_pct"] == 70
