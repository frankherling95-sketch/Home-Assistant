"""Laadplanner: kies de goedkoopste prijsblokken tot het vertrekmoment.

Bewust zonder Home Assistant-imports, zodat de rekenkern los te testen is.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any


@dataclass(frozen=True)
class PriceSlot:
    start: datetime
    end: datetime
    price: float  # EUR/kWh

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600


@dataclass(frozen=True)
class PlanInput:
    now: datetime
    deadline: datetime
    slots: list[PriceSlot]
    soc: float | None  # % — None als de auto onbekend is
    target_soc: float  # %
    capacity_kwh: float
    power_kw: float
    efficiency: float = 0.9
    cheap_threshold: float | None = None  # EUR/kWh — altijd laden op of onder deze prijs


@dataclass
class Plan:
    needed_kwh: float  # uit het net, inclusief laadverlies
    slots: list[PriceSlot] = field(default_factory=list)  # gekozen, op tijd gesorteerd
    estimated_cost: float = 0.0
    complete: bool = True  # False: bekende prijzen dekken de behoefte niet
    charge_now: bool = False
    reason: str = "geen_behoefte"
    current_price: float | None = None

    @property
    def start(self) -> datetime | None:
        return self.slots[0].start if self.slots else None

    @property
    def end(self) -> datetime | None:
        return self.slots[-1].end if self.slots else None


# Sleutelparen (start, eind, prijs) die prijsintegraties gebruiken.
_KEYSETS = (
    ("from", "till", "price"),  # Frank Energie
    ("start", "end", "value"),  # Nord Pool raw_today / raw_tomorrow
    ("start", "end", "price"),  # EnergyZero, Zonneplan e.a.
    ("start_time", "end_time", "price"),
)
_ATTRS = ("prices", "prices_today", "prices_tomorrow", "raw_today", "raw_tomorrow", "forecast")


def _as_datetime(value: Any, tz) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=tz)


def parse_price_attributes(attrs: Mapping[str, Any], tz) -> list[PriceSlot]:
    """Lees prijsblokken uit de attributen van een prijssensor.

    Ondersteunt Frank Energie (`prices` met from/till/price) en de gangbare
    alternatieven. Blokken mogen 15 of 60 minuten zijn; dubbelingen worden
    op starttijd ontdubbeld.
    """
    found: dict[datetime, PriceSlot] = {}
    for attr in _ATTRS:
        records = attrs.get(attr)
        if not isinstance(records, (list, tuple)):
            continue
        for rec in records:
            if not isinstance(rec, Mapping):
                continue
            for k_start, k_end, k_price in _KEYSETS:
                if k_start in rec and k_price in rec:
                    start = _as_datetime(rec[k_start], tz)
                    end = _as_datetime(rec.get(k_end), tz)
                    try:
                        price = float(rec[k_price])
                    except (TypeError, ValueError):
                        break
                    if start is None:
                        break
                    if end is None or end <= start:
                        end = start + timedelta(hours=1)
                    found[start] = PriceSlot(start, end, price)
                    break
    return sorted(found.values(), key=lambda s: s.start)


def next_deadline(now: datetime, departure: time) -> datetime:
    """Eerstvolgende vertrekmoment na `now` (vandaag of morgen)."""
    candidate = now.replace(hour=departure.hour, minute=departure.minute, second=0, microsecond=0)
    return candidate if candidate > now else candidate + timedelta(days=1)


def needed_energy(soc: float | None, target_soc: float, capacity_kwh: float, efficiency: float) -> float:
    """kWh uit het net om van `soc` naar `target_soc` te komen.

    Onbekende SoC telt als leeg: liever te veel uren inplannen dan een lege auto.
    """
    current = 0.0 if soc is None else soc
    gap = max(0.0, target_soc - current) / 100 * capacity_kwh
    return gap / max(efficiency, 0.01)


def make_plan(inp: PlanInput) -> Plan:
    needed = needed_energy(inp.soc, inp.target_soc, inp.capacity_kwh, inp.efficiency)

    # Alleen de (rest van de) blokken tussen nu en vertrek tellen mee.
    window: list[PriceSlot] = []
    for s in inp.slots:
        if s.end <= inp.now or s.start >= inp.deadline:
            continue
        start = max(s.start, inp.now)
        end = min(s.end, inp.deadline)
        if end > start:
            window.append(PriceSlot(start, end, s.price))

    current = next((s for s in inp.slots if s.start <= inp.now < s.end), None)
    plan = Plan(needed_kwh=round(needed, 2), current_price=current.price if current else None)

    chosen: list[PriceSlot] = []
    remaining = needed
    cost = 0.0
    if needed > 0 and inp.power_kw > 0:
        # Goedkoopste eerst; bij gelijke prijs het vroegste blok (eerder vol is beter).
        for s in sorted(window, key=lambda s: (s.price, s.start)):
            if remaining <= 1e-6:
                break
            energy = min(s.hours * inp.power_kw, remaining)
            chosen.append(s)
            cost += energy * s.price
            remaining -= energy
        plan.complete = remaining <= 1e-6

    plan.slots = sorted(chosen, key=lambda s: s.start)
    plan.estimated_cost = round(cost, 2)

    in_plan = any(s.start <= inp.now < s.end for s in plan.slots)
    cheap = (
        inp.cheap_threshold is not None
        and current is not None
        and current.price <= inp.cheap_threshold
        and (inp.soc is None or inp.soc < 100)
    )
    if in_plan:
        plan.charge_now, plan.reason = True, "gepland"
    elif cheap:
        plan.charge_now, plan.reason = True, "onder_drempel"
    elif needed <= 0:
        plan.reason = "doel_bereikt"
    elif not window:
        plan.reason = "geen_prijzen"
    else:
        plan.reason = "wachten"
    return plan
