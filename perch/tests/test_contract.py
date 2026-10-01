"""The exact budgie.core surface perch depends on.

If Budgie renames or moves one of these, this fails first and says which --
rather than a confusing error from somewhere inside the join.
"""

import inspect


def test_budgie_core_names_perch_uses():
    from budgie.core.allocation import Allocation
    from budgie.core.csvio import as_float, as_required_float, as_str, read_rows
    from budgie.core.montecarlo import simulate
    from budgie.core.person import HoursEstimate, Person
    from budgie.core.plan import AllocationPlan, PlanEntry
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
        "allocations",  # money.what_if: each person's flat fte
        "plan",
        "what_if",
    ):
        assert name in Snapshot.__dataclass_fields__ or hasattr(Snapshot, name), name
    assert {"budget", "plan_entries"} <= set(
        inspect.signature(Snapshot.what_if).parameters
    )
    # money.what_if reads each allocation's fte and the plan's names.
    assert "fte" in Allocation.__dataclass_fields__
    assert hasattr(AllocationPlan, "names")
    assert set(PlanEntry.__dataclass_fields__) == {"name", "effective_date", "fte"}
    assert all(
        callable(f)
        for f in (
            as_float, as_required_float, as_str, read_rows, simulate, evaluate,
            load_snapshot, HoursEstimate, Person, SignalResult,
        )
    )  # fmt: skip
