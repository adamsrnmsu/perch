"""The exact budgie.core surface perch depends on.

If Budgie renames or moves one of these, this fails first and says which --
rather than a confusing error from somewhere inside the join.
"""

import inspect


def test_budgie_core_names_perch_uses():
    from budgie.core.csvio import as_float, as_required_float, as_str, read_rows
    from budgie.core.montecarlo import simulate
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
    ):
        assert name in Snapshot.__dataclass_fields__ or hasattr(Snapshot, name), name
    assert all(
        callable(f)
        for f in (
            as_float, as_required_float, as_str, read_rows, simulate, evaluate,
            load_snapshot, HoursEstimate, Person, SignalResult,
        )
    )  # fmt: skip
