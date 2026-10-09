"""Nu ophalen: de knop in de app start meteen een ronde van de verzamelaar, bij alle bronnen.

Normaal draait de verzamelaar elk kwartier (Cloud Scheduler: */15). Twee rondes tegelijk kunnen
elkaars ververste tokens ongeldig maken (BMW geeft bij elke verversing een nieuw refresh-token),
dus de knop start geen eigen ronde vlak voor of tijdens een geplande:

- in de eerste 2 minuten na het kwartier loopt de geplande ronde nog: de app wacht even en vraagt
  het daarna opnieuw ("wacht");
- in de laatste 2 minuten voor het kwartier begint de geplande ronde zo: die doet het werk
  ("gepland");
- daartussen start de app meteen een ronde ("gestart").

Wat de ronde moet weten, staat in de kluis onder "ophalen": {"gevraagd": tijdstip}. Wie de knop
binnen 2 minuten nog eens indrukt (of op een tweede telefoon), wacht op dezelfde ronde ("bezig").

De auto wordt dan ook gevraagd als hij nog niet aan de beurt is (BMW: zie `aan_de_beurt` in
connectors/bmw.py). Dat verzoek telt mee voor het dagmaximum van BMW. De auto zelf wordt niet
gewekt: BMW geeft de laatste stand die de auto heeft doorgegeven.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

KWARTIER = 15 * 60  # s: zo vaak draait de verzamelaar (deploy/setup-gcp.sh)
LOOPT_NOG = 120  # s na het kwartier: de geplande ronde is dan nog bezig
BEGINT_ZO = 120  # s voor het kwartier: de geplande ronde begint zo
ZELFDE_RONDE = timedelta(minutes=2)  # nog eens drukken: dezelfde ronde
GELDIG = timedelta(minutes=10)  # zo lang telt een verzoek voor de auto (ook als de ronde mislukte)


def keuze(moment: datetime, vorige: datetime | None = None) -> dict[str, Any]:
    """Wat de knop nu doet. `vorige`: wanneer er voor het laatst op is gedrukt.

    Geeft {"actie": "gestart" | "gepland" | "bezig", "vanaf": tijdstip} of {"actie": "wacht",
    "wacht_s": n}. De app wacht daarna op een ronde die na "vanaf" begon.
    """
    if vorige is not None and moment - vorige < ZELFDE_RONDE:
        return {"actie": "bezig", "vanaf": vorige}
    s = (moment.minute % 15) * 60 + moment.second  # kwartieren vallen in UTC en NL gelijk
    if s < LOOPT_NOG:
        return {"actie": "wacht", "wacht_s": LOOPT_NOG - s}
    return {"actie": "gepland" if s >= KWARTIER - BEGINT_ZO else "gestart", "vanaf": moment}


def gevraagd(kluis: dict[str, Any], moment: datetime) -> datetime | None:
    """Wanneer er in de app op Nu ophalen is gedrukt, als dat nog geldt."""
    try:
        t = datetime.fromisoformat((kluis.get("ophalen") or {})["gevraagd"])
    except (KeyError, TypeError, ValueError):
        return None
    return t if -timedelta(minutes=1) <= moment - t <= GELDIG else None  # een minuut speling op de klok
