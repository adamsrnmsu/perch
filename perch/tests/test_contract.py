"""The exact budgie.core surface perch depends on.

If Budgie renames or moves one of these, this fails first and says which --
rather than a confusing error from somewhere inside the join.
"""

import inspect


def test_budgie_core_names_perch_uses():
    from budgie.core.actuals import load_weekly_actuals, monthly_to_observations
    from budgie.core.allocation import load_allocations
    from budgie.core.budget import coerce_budget
    from budgie.core.calendar import productive_hours
    from budgie.core.costs import load_costs, total_cost
    from budgie.core.csvio import as_float, as_required_float, as_str, read_rows
    from budgie.core.loader import load_people
    from budgie.core.montecarlo import simulate
    from budgie.core.monthly import load_monthly_actuals
    from budgie.core.person import HoursEstimate, Person
    from budgie.core.plan import load_plan
    from budgie.core.signals import evaluate
    from budgie.core.workspace import load_workspace

    assert "plan" in inspect.signature(load_allocations).parameters
    assert {"iterations", "seed"} <= set(inspect.signature(simulate).parameters)
    assert all(
        callable(f)
        for f in (
            load_weekly_actuals, monthly_to_observations, coerce_budget,
            productive_hours, load_costs, total_cost, as_float, as_required_float,
            as_str, read_rows, load_people, load_monthly_actuals, load_plan,
            evaluate, load_workspace, HoursEstimate, Person,
        )
    )  # fmt: skip
