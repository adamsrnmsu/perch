from datetime import date

import pytest

from perch.core.money import load_money


def test_the_budgie_side(world):
    money = load_money(world.parent / "fy26")
    assert money.year == 2026
    assert money.hourly_cost == {"Alice": 100, "Bob": 50}
    assert money.as_of == date(2026, 4, 19)  # ISO week 16 ends on that Sunday
    # 0.5 FTE x 1,992 h = 996 allocated; the latest reading is what is spent.
    assert money.left == {"Alice": 996 - 200, "Bob": 996 - 120}
    assert money.spent_cost == 200 * 100 + 120 * 50
    assert money.non_labor == 5000
    assert money.budget == 100000
    assert money.seed == 1


def test_a_budget_csv_gives_the_latest_revision(world):
    project = world.parent / "fy26"
    (project / "budgie.yaml").write_text("year: 2026\n")
    (project / "budget.csv").write_text(
        "effective_date,amount,note\n2026-01-01,90000,Original\n2026-05-01,95000,Up\n"
    )
    assert load_money(project).budget == 95000


def test_without_actuals_spend_falls_back_to_allocations(world):
    project = world.parent / "fy26"
    (project / "weekly.csv").unlink()
    (project / "allocations.csv").write_text(
        "name,fte,hours_spent\nAlice,0.5,150\nBob,0.5,0\n"
    )
    money = load_money(project)
    assert money.readings == {} and money.as_of is None
    assert money.left["Alice"] == 996 - 150


def test_a_project_without_a_year_is_refused(world):
    (world.parent / "fy26" / "budgie.yaml").write_text("budget: 1\n")
    with pytest.raises(ValueError, match="`year` is not set"):
        load_money(world.parent / "fy26")


def test_the_dated_budget_and_plan_pass_through(quarter_world):
    money = load_money(quarter_world.parent / "fy26")
    assert money.budget_revisions.amount_on(date(2026, 4, 14)) == 100000
    assert money.budget == 120000
    assert money.plan.fte_on("Bob", date(2026, 5, 1)) == 0.25
    assert [p.name for p in money.people] == ["Alice", "Bob"]
    assert money.pto == 0


def test_a_pinned_budget_has_no_revisions(world):
    money = load_money(world.parent / "fy26")
    assert money.budget_revisions is None and money.plan is None
