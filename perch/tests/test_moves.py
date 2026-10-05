"""Budget and staffing changes, name-free."""

from dataclasses import fields, replace
from datetime import date

from budgie.core.budget import Budget, BudgetRevision
from budgie.core.plan import AllocationPlan, PlanEntry

from perch.core import moves
from perch.core.money import load_money


def _money(world):
    return load_money(world.parent / "fy26")


def _plan(*rows):
    return AllocationPlan(
        tuple(PlanEntry(n, date.fromisoformat(d), f) for n, d, f in rows)
    )


def test_budget_moves_drop_the_note_and_the_starting_revision(world):
    revs = Budget(
        (
            BudgetRevision(date(2026, 1, 1), 100000.0, "Original"),
            BudgetRevision(date(2026, 4, 15), 120000.0, "backfill for Alice"),
        )
    )
    money = replace(_money(world), budget_revisions=revs)
    got = moves.budget(money, date(2026, 1, 1), date(2026, 12, 31))
    assert [(m.day, m.before, m.after) for m in got] == [
        (date(2026, 4, 15), 100000.0, 120000.0)
    ]
    assert "note" not in {f.name for f in fields(moves.BudgetMove)}
    assert moves.describe_budget(got[0]) == "budget $100,000 → $120,000"
    assert moves.budget(money, date(2026, 5, 1), date(2026, 6, 1)) == ()
    assert (
        moves.budget(
            replace(money, budget_revisions=None), date(2026, 1, 1), date(2026, 12, 31)
        )
        == ()
    )


def test_staffing_kinds_and_the_starting_team(world):
    plan = _plan(
        ("Alice", "2026-01-01", 0.5),
        ("Alice", "2026-06-10", 0.75),
        ("Bob", "2026-06-10", 0),
        ("Carol", "2026-06-10", 0.5),
    )
    money = replace(_money(world), plan=plan)
    got = moves.staffing(money, date(2026, 6, 1), date(2026, 6, 30))
    # Bob's 0 with nothing before it is not a change; Carol joins
    assert [(m.kind, m.fte_before, m.fte_after) for m in got] == [
        ("fte", 0.5, 0.75),
        ("join", 0.0, 0.5),
    ]
    assert moves.describe(got[0]) == "an FTE change · FTE 0.5 → 0.75"
    assert not {"name", "hours", "dollars"} & {f.name for f in fields(moves.StaffMove)}
    first_day = date(2026, 1, 1)  # a first-day row is the starting team
    assert moves.staffing(money, first_day, first_day) == ()
    assert (
        moves.staffing(replace(money, plan=None), first_day, date(2026, 12, 31)) == ()
    )


def test_a_leave_and_a_join(world):
    plan = _plan(
        ("Bob", "2026-01-01", 0.5),
        ("Bob", "2026-06-10", 0),
        ("Carol", "2026-06-10", 0.5),
    )
    got = moves.staffing(
        replace(_money(world), plan=plan), date(2026, 6, 1), date(2026, 6, 30)
    )
    assert [(m.kind, m.fte_before, m.fte_after) for m in got] == [
        ("leave", 0.5, 0.0),
        ("join", 0.0, 0.5),
    ]
    assert [moves.describe(m) for m in got] == [
        "a leave · FTE 0.5 → 0",
        "a join · FTE 0 → 0.5",
    ]


def test_two_joins_on_one_day_both_stay(world):  # review-focus 3
    plan = _plan(("Carol", "2026-06-10", 0.5), ("Dave", "2026-06-10", 0.5))
    got = moves.staffing(
        replace(_money(world), plan=plan), date(2026, 6, 1), date(2026, 6, 30)
    )
    assert [moves.describe(m) for m in got] == ["a join · FTE 0 → 0.5"] * 2
