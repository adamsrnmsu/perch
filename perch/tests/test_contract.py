"""The exact budgie.core surface perch depends on.

If Budgie renames or moves one of these, this fails first and says which --
rather than a confusing error from somewhere inside the join.
"""

import inspect


def test_budgie_core_names_perch_uses():
    from budgie.core.budget import Budget, BudgetRevision
    from budgie.core.burndown import BurndownStatus, burndown
    from budgie.core.calendar import workdays_between
    from budgie.core.costs import CostItem
    from budgie.core.csvio import as_float, as_required_float, as_str, read_rows
    from budgie.core.eac import at_completion
    from budgie.core.montecarlo import simulate
    from budgie.core.monthly import spent_at
    from budgie.core.person import HoursEstimate, Person
    from budgie.core.plan import AllocationPlan, PlanEntry
    from budgie.core.project import Snapshot, load_snapshot
    from budgie.core.signals import SignalResult, evaluate

    assert {"iterations", "seed", "costs"} <= set(
        inspect.signature(simulate).parameters
    )
    # What money.load_money reads off the snapshot: fields and properties.
    for name in (
        "span",
        "people",
        "readings",
        "non_labor",
        "costs",  # quarterly: simulate(costs=), as `budgie forecast`
        "budget",
        "iterations",
        "seed",
        "allocated",
        "spent",
        "pto",
        "budget_revisions",
        "allocations",  # money_from: one pace line per allocation
        "plan",
        "what_if",
    ):
        assert name in Snapshot.__dataclass_fields__ or hasattr(Snapshot, name), name
    assert {"budget", "plan_entries"} <= set(
        inspect.signature(Snapshot.what_if).parameters
    )
    assert set(PlanEntry.__dataclass_fields__) == {"name", "effective_date", "fte"}
    assert {"observations", "plan"} <= set(inspect.signature(burndown).parameters)
    assert {"series", "day", "span"} == set(inspect.signature(spent_at).parameters)
    assert callable(BurndownStatus.expected_on) and callable(workdays_between)
    # What quarterly.build calls on them.
    assert {"people", "observations", "span", "as_of", "plan"} <= set(
        inspect.signature(at_completion).parameters
    )
    from budgie.core.calendar import YearSpan, year_span

    assert callable(year_span) and {"first", "last"} <= set(
        YearSpan.__dataclass_fields__
    )
    # What perch reads off a span: quarters, label, zero, contains.
    for name in ("quarters", "label", "zero", "contains"):
        assert hasattr(YearSpan, name), name
    assert callable(Budget.amount_on)
    for name in ("entries", "fte_on", "allocated_hours"):
        assert (
            hasattr(AllocationPlan, name) or name in AllocationPlan.__dataclass_fields__
        )
    assert all(
        callable(f)
        for f in (
            as_float, as_required_float, as_str, read_rows, simulate, evaluate,
            load_snapshot, HoursEstimate, Person, SignalResult, BudgetRevision,
            CostItem,
        )
    )  # fmt: skip
