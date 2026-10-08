"""Laadsessies: van inpluggen tot uitpluggen, afgeleid uit de metingen van de lader.

Easee telt per sessie (`sessie_kwh`) vanaf het inpluggen; de meterstand (`totaal_kwh`) loopt
altijd door. Een sessie eindigt bij uitpluggen of als de sessieteller terugspringt (een
nieuwe sessie waarvan we het uitpluggen tussen twee metingen hebben gemist).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .inzicht import Prijslijst, lader_metingen, prijzen
from .opslag import Opslag

LOS = "niet_verbonden"
ONBEKEND = {None, "offline"}  # zegt niets over de stekker: een lopende sessie loopt door
MIN_KWH = 0.5  # ingeplugd zonder (noemenswaardig) te laden telt niet als sessie


def vind_sessies(metingen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sessies uit metingen (op tijd gesorteerd, mag meerdere laders bevatten)."""
    klaar: list[dict[str, Any]] = []
    open_: dict[str, dict[str, Any]] = {}
    vorige: dict[str, dict[str, Any]] = {}

    def sluit(lader_id: str, uitgeplugd: bool) -> None:
        s = open_.pop(lader_id)
        s["uitgeplugd"] = uitgeplugd
        if s["kwh"] >= MIN_KWH:
            klaar.append(s)

    for m in metingen:
        lid, v = m["lader_id"], vorige.get(m["lader_id"])
        delta = 0.0
        if v is not None and m["totaal_kwh"] is not None and v["totaal_kwh"] is not None:
            delta = max(0.0, m["totaal_kwh"] - v["totaal_kwh"])
        teller_terug = (
            v is not None
            and m["sessie_kwh"] is not None
            and v["sessie_kwh"] is not None
            and m["sessie_kwh"] + 0.5 < v["sessie_kwh"]
        )
        if lid in open_ and teller_terug:
            sluit(lid, uitgeplugd=True)

        verbonden = m["status"] not in ONBEKEND and m["status"] != LOS
        if lid not in open_ and (verbonden or delta > 0):
            # Laadde de auto al vóór deze meting, dan is hij eerder ingeplugd.
            start = v["tijd"] if delta > 0 and v is not None else m["tijd"]
            open_[lid] = {
                "lader_id": lid,
                "start": start,
                "eind": None,
                "kwh": 0.0,
                "max_kw": 0.0,
                "intervallen": [],
                "status": m["status"],
                "laatst": m["tijd"],
            }
        s = open_.get(lid)
        if s is not None:
            if delta > 0:
                s["kwh"] += delta
                s["intervallen"].append({"van": v["tijd"], "tot": m["tijd"], "kwh": delta})
                s["eind"] = m["tijd"]
            s["max_kw"] = max(s["max_kw"], m.get("vermogen_kw") or 0)
            if m["status"] not in ONBEKEND:
                s["status"] = m["status"]
            s["laatst"] = m["tijd"]
            if m["status"] == LOS:
                sluit(lid, uitgeplugd=True)
        vorige[lid] = m

    for lid in list(open_):
        sluit(lid, uitgeplugd=False)
    return sorted(klaar, key=lambda s: s["start"])


def direct_kosten(start: datetime, kwh: float, kw: float, lijst: Prijslijst) -> float | None:
    """Wat dezelfde kWh hadden gekost bij direct laden vanaf het inpluggen, op vol vermogen.

    None als de prijzen dat venster niet helemaal dekken.
    """
    t, rest, kosten = start, kwh, 0.0
    while rest > 1e-6:
        blok = lijst.blok(t)
        if blok is None:
            return None
        uren = min((blok["tot"] - t).total_seconds() / 3600, rest / kw)
        kosten += uren * kw * blok["allin"]
        rest -= uren * kw
        t += timedelta(hours=uren)
    return kosten


def laadsessies(
    opslag: Opslag, van: datetime, tot: datetime, vermogen_kw: float = 11.0
) -> list[dict[str, Any]]:
    """Sessies die in [van, tot) begonnen, nieuwste eerst."""
    # Ruimer lezen: een sessie kan vóór `van` beginnen of na `tot` doorlopen.
    begin, eind = van - timedelta(days=3), tot + timedelta(days=2)
    sessies = [s for s in vind_sessies(lader_metingen(opslag, begin, eind)) if van <= s["start"] < tot]
    if not sessies:
        return []
    lijst = Prijslijst(prijzen(opslag, "stroom", begin, eind + timedelta(days=1)))
    acties = opslag.lees(
        "SELECT tijd, lader_id FROM {stuuractie} WHERE tijd >= @van AND tijd < @tot", van=begin, tot=eind
    )

    uit = []
    for s in reversed(sessies):
        kosten = sum(
            i["kwh"] * (lijst.op(i["van"] + (i["tot"] - i["van"]) / 2) or 0) for i in s["intervallen"]
        )
        kw = s["max_kw"] if s["max_kw"] >= 1 else vermogen_kw
        direct = direct_kosten(s["start"], s["kwh"], kw, lijst)
        uit.append(
            {
                "lader_id": s["lader_id"],
                "start": s["start"],
                "eind": s["eind"],
                "kwh": round(s["kwh"], 2),
                "kosten": round(kosten, 2),
                "gem_prijs": round(kosten / s["kwh"], 4),
                "slim": any(
                    a["lader_id"] == s["lader_id"] and s["start"] <= a["tijd"] <= s["laatst"] for a in acties
                ),
                "klaar": s["uitgeplugd"] or s["status"] == "klaar",
                "besparing": None if direct is None else round(direct - kosten, 2),
            }
        )
    return uit
