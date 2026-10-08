import json
from datetime import timedelta

import httpx
import pytest
import respx
from conftest import blokken, utc
from test_sessies_inzichten import _laadnacht, _meting

from thuis.inzicht import dag_grenzen, lokaal
from thuis.meldingen import GoogleChat, controleer
from thuis.schema import LADER, PRIJS

MOMENT = utc(2026, 10, 7, 12)  # 14:00 lokaal: de prijzen van morgen zijn er


class NepChat:
    def __init__(self, fout=False):
        self.berichten, self.fout = [], fout

    def stuur(self, tekst):
        if self.fout:
            raise RuntimeError("webhook weg")
        self.berichten.append(tekst)


def _negatief_morgen(opslag):
    morgen = dag_grenzen(lokaal(MOMENT) + timedelta(days=1))[0]
    opslag.voeg_toe(PRIJS, blokken(morgen, [0.2] * 12 + [-0.03, -0.06] + [0.2] * 10))


def test_negatieve_prijzen_morgen_maar_een_keer(opslag):
    _negatief_morgen(opslag)
    chat = NepChat()
    assert controleer(opslag, chat, MOMENT) == ["negatief:2026-10-08"]
    assert "12:00–14:00" in chat.berichten[0] and "€ -0,060" in chat.berichten[0]
    assert controleer(opslag, chat, MOMENT + timedelta(minutes=15)) == []  # al verstuurd
    assert len(chat.berichten) == 1


def test_lader_fout_vanaf_begin_van_de_reeks(opslag):
    opslag.voeg_toe(
        LADER,
        [
            _meting(MOMENT - timedelta(minutes=45), "laden", 10.0, 1.0),
            _meting(MOMENT - timedelta(minutes=30), "fout", 10.0, 1.0),
            _meting(MOMENT - timedelta(minutes=15), "fout", 10.0, 1.0),
        ],
    )
    chat = NepChat()
    [sleutel] = controleer(opslag, chat, MOMENT)
    assert sleutel == f"laderfout:L:{(MOMENT - timedelta(minutes=30)).isoformat()}"
    assert chat.berichten == ["Lader Oprit meldt een fout (sinds 13:30). Kijk in de Easee-app."]


def test_laadsessie_klaar(opslag):
    _laadnacht(opslag)
    chat = NepChat()
    assert controleer(opslag, chat, utc(2026, 10, 7, 6, 10)) == [
        f"sessie:L:{utc(2026, 10, 6, 16, 15).isoformat()}"
    ]
    assert chat.berichten == [
        "Laden klaar: 7,5 kWh voor € 0,75 (gemiddeld € 0,100/kWh), € 2,25 goedkoper dan direct laden."
    ]
    assert controleer(opslag, NepChat(), utc(2026, 10, 7, 14)) == []  # te lang geleden


def test_mislukte_melding_wordt_niet_als_verstuurd_bewaard(opslag):
    _negatief_morgen(opslag)
    with pytest.raises(RuntimeError, match="webhook weg"):
        controleer(opslag, NepChat(fout=True), MOMENT)
    assert controleer(opslag, NepChat(), MOMENT) == ["negatief:2026-10-08"]  # volgende ronde opnieuw


@respx.mock
def test_google_chat_webhook():
    url = "https://chat.googleapis.com/v1/spaces/X/messages?key=k&token=t"
    route = respx.post(url).mock(return_value=httpx.Response(200, json={}))
    GoogleChat(url).stuur("Hallo")
    assert json.loads(route.calls[0].request.content) == {"text": "Hallo"}
