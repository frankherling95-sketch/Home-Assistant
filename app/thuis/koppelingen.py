"""Koppelingen: de accounts van Frank Energie, Easee, Kia/Hyundai en Google Chat.

Koppelen gebeurt in de app: één keer inloggen, daarna bewaart Thuis alleen de tokens die de
dienst teruggeeft (nooit het wachtwoord) in de kluis. De verzamelaar bouwt zijn connectoren
daaruit, ververst tokens en slaat de nieuwe op. Werken ze niet meer, dan krijgt de koppeling
status "opnieuw" en vraagt de app om opnieuw te koppelen.

Oude installaties met logins uit het setup-script (FRANK_EMAIL, …) blijven gewoon werken.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import Config
from .connectors import KoppelFout
from .opslag import nu

DIENSTEN: dict[str, dict[str, Any]] = {
    "frank": {
        "naam": "Frank Energie",
        "uitleg": "Voor je verbruik en kosten per uur. De stroomprijzen werken ook zonder koppeling.",
        "velden": [
            {"naam": "email", "label": "E-mailadres", "type": "email"},
            {"naam": "wachtwoord", "label": "Wachtwoord", "type": "password"},
        ],
        "oud": ("FRANK_EMAIL", "FRANK_WACHTWOORD"),
    },
    "easee": {
        "naam": "Easee",
        "uitleg": "Voor de lader: status, vermogen en laadsessies, en voor Slim laden.",
        "velden": [
            {"naam": "gebruiker", "label": "E-mailadres of telefoonnummer", "type": "text"},
            {"naam": "wachtwoord", "label": "Wachtwoord", "type": "password"},
        ],
        "oud": ("EASEE_GEBRUIKER", "EASEE_WACHTWOORD"),
    },
    "kia": {
        "naam": "Kia / Hyundai",
        "uitleg": "Voor de accu en het bereik van je auto. De pincode is niet nodig.",
        "velden": [
            {"naam": "merk", "label": "Merk", "type": "keuze", "keuzes": ["kia", "hyundai"]},
            {"naam": "gebruiker", "label": "E-mailadres", "type": "email"},
            {"naam": "wachtwoord", "label": "Wachtwoord", "type": "password"},
        ],
        "oud": ("KIA_GEBRUIKER", "KIA_WACHTWOORD"),
    },
    "google_chat": {
        "naam": "Google Chat",
        "uitleg": "Meldingen in een Chat-ruimte: negatieve prijzen, laden klaar, storingen.",
        "velden": [{"naam": "webhook", "label": "Webhook-adres", "type": "url"}],
        "oud": ("GOOGLE_CHAT_WEBHOOK",),
    },
}


def _verplicht(gegevens: dict[str, str], *namen: str) -> list[str]:
    ontbreekt = [n for n in namen if not (gegevens.get(n) or "").strip()]
    if ontbreekt:
        raise KoppelFout("Vul alle velden in.")
    return [gegevens[n].strip() for n in namen]


def koppel(dienst: str, gegevens: dict[str, str]) -> tuple[dict[str, Any], str]:
    """Eenmalig inloggen bij de dienst. Geeft (wat in de kluis komt, bevestiging voor de gebruiker)."""
    if dienst == "frank":
        from .connectors.frank import Frank

        r = Frank.koppel(*_verplicht(gegevens, "email", "wachtwoord"))
    elif dienst == "easee":
        from .connectors.easee import Easee

        r = Easee.koppel(*_verplicht(gegevens, "gebruiker", "wachtwoord"))
    elif dienst == "kia":
        from .connectors.kia import Kia

        gebruiker, wachtwoord = _verplicht(gegevens, "gebruiker", "wachtwoord")
        r = Kia.koppel(gebruiker, wachtwoord, gegevens.get("merk") or "kia")
    elif dienst == "google_chat":
        from .meldingen import GoogleChat

        (webhook,) = _verplicht(gegevens, "webhook")
        if not webhook.startswith("https://chat.googleapis.com/"):
            raise KoppelFout("Dit is geen Google Chat-webhook (die begint met https://chat.googleapis.com/).")
        try:
            GoogleChat(webhook).stuur("Thuis is gekoppeld aan deze ruimte. Hier komen voortaan de meldingen.")
        except Exception as err:
            raise KoppelFout("Google Chat nam het testbericht niet aan; kopieer de webhook opnieuw.") from err
        r = {"webhook": webhook, "account": "Chat-ruimte", "bericht": "Testbericht verstuurd"}
    else:
        raise KoppelFout(f"Onbekende dienst: {dienst}")
    bericht = r.pop("bericht", "Gekoppeld")
    return {**r, "status": "ok", "gekoppeld": nu().isoformat()}, bericht


def _maskeer(account: str) -> str:
    if "@" in account:
        naam, domein = account.split("@", 1)
        return f"{naam[:2]}…@{domein}"
    return f"{account[:4]}…{account[-2:]}" if len(account) > 6 else account


def overzicht(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Per dienst de status voor de app, zonder tokens of wachtwoorden."""
    koppelingen = data.get("koppelingen") or {}
    uit = []
    for dienst, d in DIENSTEN.items():
        k = koppelingen.get(dienst)
        oud = all(data.get(s) for s in d["oud"])
        if k:
            status, account = k.get("status", "ok"), k.get("account", "")
        elif oud:
            status, account = "script", data.get(d["oud"][0], "")
        else:
            status, account = "niet", ""
        uit.append(
            {
                "dienst": dienst,
                "naam": d["naam"],
                "uitleg": d["uitleg"],
                "velden": d["velden"],
                "status": status,  # ok | opnieuw | script | niet
                "account": _maskeer(account) if dienst != "google_chat" else account,
                "sinds": (k or {}).get("gekoppeld"),
            }
        )
    return uit


# ── voor de verzamelaar ───────────────────────────────────────────────────────


@dataclass
class Connectoren:
    frank: Any = None  # altijd aanwezig (prijzen zijn openbaar)
    frank_account: bool = False  # verbruik ophalen?
    easee: Any = None
    kia: Any = None
    chat: Any = None
    koppelingen: dict[str, dict[str, Any]] = field(default_factory=dict)


def maak_connectoren(cfg: Config, data: dict[str, Any]) -> Connectoren:
    """Connectoren uit de koppelingen in de kluis; anders uit de oude logins (setup-script)."""
    from .connectors.easee import Easee
    from .connectors.frank import Frank

    k = data.get("koppelingen") or {}
    c = Connectoren(koppelingen=k)
    if "frank" in k:
        c.frank = Frank(site=k["frank"].get("site", ""), tokens=k["frank"].get("tokens"))
        c.frank_account = True
    else:
        c.frank = Frank(cfg.frank_email, cfg.frank_wachtwoord, cfg.frank_site)
        c.frank_account = cfg.frank_login
    if "easee" in k:
        c.easee = Easee(tokens=k["easee"].get("tokens"))
    elif cfg.easee:
        c.easee = Easee(cfg.easee_gebruiker, cfg.easee_wachtwoord)
    if "kia" in k or cfg.kia:
        from .connectors.kia import Kia

        if "kia" in k:
            c.kia = Kia(merk=k["kia"].get("merk", "kia"), token=k["kia"].get("token"))
        else:
            c.kia = Kia(cfg.kia_gebruiker, cfg.kia_wachtwoord, cfg.kia_pin, cfg.kia_merk)
    webhook = (k.get("google_chat") or {}).get("webhook") or cfg.chat_webhook
    if webhook:
        from .meldingen import GoogleChat

        c.chat = GoogleChat(webhook)
    return c


def nieuwe_stand(c: Connectoren, verlopen: set[str], gelukt: set[str]) -> dict[str, dict[str, Any]]:
    """Wat er na een ronde in de kluis moet: verse tokens, en de status per koppeling."""
    wijzig: dict[str, dict[str, Any]] = {}
    for dienst, conn, sleutel in (
        ("frank", c.frank, "tokens"),
        ("easee", c.easee, "tokens"),
        ("kia", c.kia, "token"),
    ):
        k = c.koppelingen.get(dienst)
        if k is None or conn is None:
            continue
        nieuw = dict(k)
        if getattr(conn, "gewijzigd", False):
            nieuw[sleutel] = conn.tokens
        if dienst in verlopen:
            nieuw["status"] = "opnieuw"
        elif dienst in gelukt:
            nieuw["status"] = "ok"
        if nieuw != k:
            wijzig[dienst] = nieuw
    return wijzig
