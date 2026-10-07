from datetime import UTC, datetime, timedelta

import pytest

from thuis.opslag import DuckOpslag


@pytest.fixture
def opslag() -> DuckOpslag:
    o = DuckOpslag(":memory:")
    o.maak_tabellen()
    return o


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def blokken(start: datetime, prijzen: list[float], minuten: int = 60, soort: str = "stroom") -> list[dict]:
    d = timedelta(minutes=minuten)
    return [
        {"soort": soort, "van": start + i * d, "tot": start + (i + 1) * d, "marktprijs": p, "allin": p}
        for i, p in enumerate(prijzen)
    ]
