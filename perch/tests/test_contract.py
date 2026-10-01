"""The exact budgie.core surface perch depends on.

If Budgie renames or moves one of these, this fails first and says which --
rather than a confusing error from somewhere inside the join.
"""

import inspect


def test_budgie_core_names_perch_uses():
    from budgie.core.burndown import BurndownStatus, burndown
    from budgie.core.calendar import workdays_between
    from budgie.core.csvio import as_float, as_required_float, as_str, read_rows
    from budgie.core.montecarlo import simulate
    from budgie.core.monthly import _spent_at  # private until budgie-8u1
    from budgie.core.person import HoursEstimate, Person
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
        "allocations",
        "plan",
    ):
        assert name in Snapshot.__dataclass_fields__ or hasattr(Snapshot, name), name
    assert {"observations", "plan"} <= set(inspect.signature(burndown).parameters)
    assert {"series", "day", "year"} == set(inspect.signature(_spent_at).parameters)
    assert callable(BurndownStatus.expected_on) and callable(workdays_between)
    assert all(
        callable(f)
        for f in (
            as_float, as_required_float, as_str, read_rows, simulate, evaluate,
            load_snapshot, HoursEstimate, Person, SignalResult,
        )
    )  # fmt: skip
