from datetime import datetime, time, timedelta, timezone

from thuis.planner import (
    PlanInput,
    PriceSlot,
    make_plan,
    needed_energy,
    next_deadline,
    parse_price_attributes,
)

TZ = timezone(timedelta(hours=2))
T0 = datetime(2026, 10, 7, 18, 0, tzinfo=TZ)


def hourly(prices, start=T0):
    return [
        PriceSlot(start + timedelta(hours=i), start + timedelta(hours=i + 1), p) for i, p in enumerate(prices)
    ]


def plan(**kw):
    base = dict(
        now=T0,
        deadline=T0 + timedelta(hours=12),
        slots=hourly([0.30, 0.25, 0.10, 0.05, 0.12, 0.40] + [0.20] * 6),
        soc=50,
        target_soc=80,
        capacity_kwh=60,
        power_kw=10,
        efficiency=1.0,
    )
    base.update(kw)
    return make_plan(PlanInput(**base))


def test_parse_frank_energie_strings_and_datetimes():
    attrs = {
        "prices": [
            {"from": "2026-10-07T18:00:00+02:00", "till": "2026-10-07T18:15:00+02:00", "price": 0.21},
            {"from": T0 + timedelta(minutes=15), "till": T0 + timedelta(minutes=30), "price": "0.19"},
            {"from": "kapot", "till": None, "price": 1},
        ]
    }
    slots = parse_price_attributes(attrs, TZ)
    assert [s.price for s in slots] == [0.21, 0.19]
    assert slots[0].hours == 0.25


def test_parse_nordpool_raw():
    attrs = {
        "raw_today": [{"start": T0, "end": T0 + timedelta(hours=1), "value": 0.1}],
        "raw_tomorrow": [
            {"start": T0 + timedelta(days=1), "end": T0 + timedelta(days=1, hours=1), "value": 0.2}
        ],
    }
    assert len(parse_price_attributes(attrs, TZ)) == 2


def test_next_deadline_rolls_to_tomorrow():
    assert next_deadline(T0, time(7, 30)) == datetime(2026, 10, 8, 7, 30, tzinfo=TZ)
    assert next_deadline(T0, time(19, 0)) == datetime(2026, 10, 7, 19, 0, tzinfo=TZ)


def test_needed_energy_unknown_soc_assumes_empty():
    assert needed_energy(None, 80, 60, 0.8) == 60.0
    assert needed_energy(90, 80, 60, 0.9) == 0


def test_picks_cheapest_hours():
    p = plan()  # 18 kWh nodig bij 10 kW: 0.05 + 0.10 helemaal (20 kWh > 18)
    assert [s.price for s in p.slots] == [0.10, 0.05]
    assert p.estimated_cost == round(10 * 0.05 + 8 * 0.10, 2)
    assert p.complete and not p.charge_now and p.reason == "wachten"


def test_charge_now_inside_planned_slot():
    p = plan(now=T0 + timedelta(hours=3, minutes=10))
    assert p.charge_now and p.reason == "gepland"
    assert p.slots[0].start == T0 + timedelta(hours=3, minutes=10)  # rest van het lopende blok


def test_incomplete_when_prices_run_out():
    p = plan(soc=0, target_soc=100, slots=hourly([0.2, 0.1]))
    assert not p.complete and len(p.slots) == 2


def test_cheap_threshold_overrides_when_target_reached():
    p = plan(soc=85, slots=hourly([-0.02, 0.3] + [0.3] * 10), cheap_threshold=0.0)
    assert p.needed_kwh == 0 and p.charge_now and p.reason == "onder_drempel"


def test_target_reached():
    p = plan(soc=80)
    assert not p.charge_now and p.reason == "doel_bereikt" and p.slots == []
