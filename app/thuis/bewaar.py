"""Antwoorden van de API bewaren tot de volgende ronde van de verzamelaar.

De data verandert alleen als de verzamelaar een ronde draait (elk kwartier) of als je in de app iets
wijzigt. Een pagina stelt zonder dit tot twintig vragen aan BigQuery, die elk een halve tot
anderhalve seconde duren. Daarom bewaart de app elk antwoord tot er een nieuwe ronde is of een nieuw
kwartier begint (dan schuift ook "nu" op), wat het eerst komt. Een wijziging via de app maakt alles
leeg, en de web-app kan na een wijziging om een vers antwoord vragen (header x-thuis-vers).

Welke ronde de laatste is, vraagt de app hooguit eens per minuut aan de database (één kleine
query); /api/status houdt het daarnaast bij. Alles staat in het geheugen van de instantie: na een
koude start is het leeg.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from datetime import timedelta
from typing import Any

from .opslag import Opslag, nu

KWARTIER_S = 15 * 60
CONTROLE_S = 60  # hoe lang een bekende "laatste ronde" geldt
MAX_ANTWOORDEN = 200


class Bewaard:
    def __init__(self, klok: Callable[[], float] = time.time) -> None:
        self._klok = klok
        self._antwoorden: OrderedDict[Hashable, Any] = OrderedDict()
        self._ronde: str | None = None
        self._gecontroleerd = float("-inf")
        self._slot = threading.Lock()
        self._controle = threading.Lock()  # één vraag naar de laatste ronde tegelijk

    def ronde(self, opslag: Opslag) -> str | None:
        """Tijdstip van de laatste ronde; hooguit eens per CONTROLE_S uit de database."""
        with self._controle:
            if self._klok() - self._gecontroleerd >= CONTROLE_S:
                rijen = opslag.lees(
                    "SELECT MAX(tijd) AS laatst FROM {ronde} WHERE tijd >= @sinds",
                    sinds=nu() - timedelta(days=2),
                )
                laatst = rijen[0]["laatst"] if rijen else None
                self.zet_ronde(laatst.isoformat() if laatst else None)
            return self._ronde

    def zet_ronde(self, laatst: str | None) -> None:
        """Nieuwe stand van de laatste ronde (ook vanuit /api/status). Een nieuwe ronde wist alles."""
        with self._slot:
            if laatst != self._ronde:
                self._antwoorden.clear()
            self._ronde = laatst
            self._gecontroleerd = self._klok()

    def haal(self, sleutel: Hashable, opslag: Opslag, maak: Callable[[], Any], vers: bool = False) -> Any:
        """Het bewaarde antwoord, of `maak()` uitvoeren en bewaren. `vers`: altijd opnieuw maken."""
        k = (sleutel, self.ronde(opslag), int(self._klok() // KWARTIER_S))
        if not vers:
            with self._slot:
                if k in self._antwoorden:
                    self._antwoorden.move_to_end(k)
                    return self._antwoorden[k]
        waarde = maak()
        with self._slot:
            self._antwoorden[k] = waarde
            while len(self._antwoorden) > MAX_ANTWOORDEN:
                self._antwoorden.popitem(last=False)
        return waarde

    def leeg(self) -> None:
        with self._slot:
            self._antwoorden.clear()


class NietBewaard:
    """Lokaal (DuckDB) is elke vraag snel en schrijven tests direct in de database: niets bewaren."""

    def haal(self, sleutel: Hashable, opslag: Opslag, maak: Callable[[], Any], vers: bool = False) -> Any:
        return maak()

    def zet_ronde(self, laatst: str | None) -> None:
        pass

    def leeg(self) -> None:
        pass
