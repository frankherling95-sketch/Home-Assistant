"""Connectoren naar externe diensten. Elke connector levert rijen voor thuis.schema.

Connectoren die met een account werken, kunnen met een wachtwoord inloggen (eenmalig, bij het
koppelen in de app) of met bewaarde tokens. Ze houden hun tokens bij in `.tokens` en zetten
`.gewijzigd` als die ververst zijn, zodat de verzamelaar ze kan opslaan.
"""


class KoppelingVerlopen(RuntimeError):
    """De bewaarde tokens werken niet meer: opnieuw koppelen in de app."""

    def __init__(self, dienst: str, reden: str = "") -> None:
        super().__init__(f"koppeling met {dienst} verlopen{f' ({reden})' if reden else ''}: opnieuw koppelen")
        self.dienst = dienst
        self.reden = reden


class KoppelFout(RuntimeError):
    """Koppelen lukte niet; de tekst is bedoeld voor de gebruiker."""
