"""The exact budgie.core surface perch depends on.

If Budgie renames or moves one of these, this fails first and says which --
rather than a confusing error from somewhere inside the join.
"""

import inspect


def test_budgie_core_names_perch_uses():
    from budgie.core.budget import Budget, BudgetRevision
    from budgie.core.csvio import as_float, as_required_float, as_str, read_rows
    from budgie.core.eac import at_completion
    from budgie.core.montecarlo import simulate
    from budgie.core.person import HoursEstimate, Person
    from budgie.core.plan import AllocationPlan
    from budgie.core.project import Snapshot, load_snapshot
    from budgie.core.signals import SignalResult, evaluate

    assert {"iterations", "seed"} <= set(inspect.signature(simulate).parameters)
    # What money.load_money reads off the snapshot: fields and properties.
    for name in (
        "year",
        "people",
        "readings",
        "non_labor",
        "budget",
        "iterations",
        "seed",
        "allocated",
        "spent",
        "pto",
        "budget_revisions",
        "plan",
    ):
        assert name in Snapshot.__dataclass_fields__ or hasattr(Snapshot, name), name
    # What quarterly.build calls on them.
    assert {"people", "observations", "year", "as_of", "plan"} <= set(
        inspect.signature(at_completion).parameters
    )
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
        )
    )  # fmt: skip
