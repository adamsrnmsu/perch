from datetime import date, timedelta

import pytest
from budgie.core.calendar import year_span

from perch.core.rate import build_intervals, fit_types, person_rates, team_rate
from perch.tests.conftest import week

READINGS = {
    "Alice": [(week(4), 40), (week(8), 100), (week(12), 160), (week(16), 200)],
    "Bob": [(week(8), 80), (week(16), 120)],
}


def closed(name, count, day, kind="untyped"):
    return [(name, day, kind)] * count


CLOSED = (
    closed("Alice", 2, date(2026, 1, 10))
    + closed("Alice", 2, date(2026, 2, 10))
    + closed("Alice", 3, date(2026, 3, 10))
    + closed("Alice", 1, date(2026, 4, 10))
    + closed("Bob", 4, date(2026, 2, 1))
    + closed("Bob", 1, date(2026, 4, 1))
)


def test_intervals_run_reading_to_reading_from_january_first():
    intervals = build_intervals(READINGS, CLOSED, year_span(2026))
    assert [(i.name, i.hours, i.issues) for i in intervals] == [
        ("Alice", 40, 2), ("Alice", 60, 2), ("Alice", 60, 3), ("Alice", 40, 1),
        ("Bob", 80, 4), ("Bob", 40, 1),
    ]  # fmt: skip
    assert intervals[0].start == date(2026, 1, 1)
    assert intervals[1].start == date(2026, 1, 26)  # the day after week 4 ends


def test_own_rate_has_spread_only_with_three_samples():
    rates = person_rates(build_intervals(READINGS, CLOSED, year_span(2026)))
    alice, bob = rates["Alice"], rates["Bob"]
    assert (alice.low, alice.mode, alice.high, alice.samples) == (20, 25, 40, 4)
    assert (bob.low, bob.mode, bob.high, bob.samples) == (24, 24, 24, 2)


def test_team_rate_is_a_single_number():
    team = team_rate(build_intervals(READINGS, CLOSED, year_span(2026)))
    assert team.low == team.mode == team.high == pytest.approx(320 / 13)


def test_an_interval_with_nothing_closed_merges_into_its_neighbour():
    readings = {"A": [(week(4), 10), (week(8), 30), (week(12), 50)]}
    merged = build_intervals(
        readings, closed("A", 2, date(2026, 2, 10)), year_span(2026)
    )
    # week 4 closed nothing (merges forward); week 12 closed nothing (merges back)
    assert [(i.start, i.end, i.hours, i.issues) for i in merged] == [
        (date(2026, 1, 1), week(12), 50, 2)
    ]
    assert build_intervals({"A": [(week(4), 10)]}, [], year_span(2026)) == []
    assert person_rates([]) == {} and team_rate([]) is None


def test_intervals_open_where_the_dump_history_starts():
    # History from Feb 1, between Alice's week 4 and week 8 readings: the
    # week 4 interval and the one straddling Feb 1 are both dropped, rather
    # than piled onto the first interval with closes the dump can see.
    intervals = build_intervals(
        READINGS, CLOSED, year_span(2026), since=date(2026, 2, 1)
    )
    assert [(i.name, i.start, i.hours, i.issues) for i in intervals] == [
        ("Alice", week(8) + timedelta(days=1), 60, 3),
        ("Alice", week(12) + timedelta(days=1), 40, 1),
        ("Bob", week(8) + timedelta(days=1), 40, 1),
    ]  # fmt: skip
    assert build_intervals(
        READINGS, CLOSED, year_span(2026), since=date(2026, 1, 1)
    ) == (build_intervals(READINGS, CLOSED, year_span(2026)))


def _two_type_world(extra=()):
    """hours = 10 x bugs + 30 x features exactly; Q works at 1.5x P's hours."""
    data = [("P", 1, 3, 1), ("P", 2, 2, 2), ("P", 3, 4, 0), ("P", 4, 1, 3),
            ("Q", 1, 2, 2), ("Q", 2, 5, 1), ("Q", 3, 0, 3), ("Q", 4, 3, 3)]  # fmt: skip
    readings, done, total = {"P": [], "Q": []}, [], {"P": 0.0, "Q": 0.0}
    for name, step, bugs, features in data:
        total[name] += (10 * bugs + 30 * features) * (1.5 if name == "Q" else 1.0)
        end = week(4 * step)
        readings[name].append((end, total[name]))
        done += closed(name, bugs, end, "bug") + closed(name, features, end, "feature")
    return build_intervals(readings, done + list(extra), year_span(2026))


def test_the_type_model_recovers_exact_rates_and_factors():
    model = fit_types(_two_type_world())
    assert model.intervals == 8
    assert model.hours("P", "bug") == pytest.approx(10)
    assert model.hours("P", "feature") == pytest.approx(30)
    assert model.hours("Q", "bug") == pytest.approx(15)
    # Nobody's factor: the team's pace, between the two.
    assert 10 < model.hours(None, "bug") < 15


def test_a_single_type_model_agrees_with_the_flat_rates():
    model = fit_types(build_intervals(READINGS, CLOSED, year_span(2026)))
    assert model.hours("Alice", "untyped") == pytest.approx(25)
    assert model.hours("Bob", "untyped") == pytest.approx(24)
    assert model.hours(None, "untyped") == pytest.approx(320 / 13)


def test_a_rare_type_is_counted_with_the_commonest_one():
    model = fit_types(_two_type_world(extra=closed("P", 1, week(4), "docs")))
    assert set(model.rates) == {"bug", "feature"}
    assert model.column("docs") == "bug"
    assert model.column("never-seen") == "bug"
    assert all(rate >= 0 for rate in model.rates.values())


def test_too_few_intervals_refuses_to_fit():
    # Q's first three intervals close 7 bugs and 6 features: two real columns,
    # and three intervals is fewer than 2 + 2.
    intervals = [i for i in _two_type_world() if i.name == "Q"][:3]
    assert fit_types(intervals) is None
    assert fit_types([]) is None
