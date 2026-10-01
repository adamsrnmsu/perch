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


def test_budgie_pace_and_booked_hours_over_a_window(world):
    """Even burn without a plan: 996 h x 28/365 = 76.4 h planned in four weeks.
    Alice read 160 at wk12 (03-22) and 200 at wk16 (04-19); 04-12 interpolates
    to 160 + 40 x 21/28 = 190."""
    money = load_money(world.parent / "fy26")
    assert money.planned("Alice", date(2026, 3, 22), date(2026, 4, 19)) == (
        pytest.approx(996 * 28 / 365)
    )
    assert money.booked("Alice", date(2026, 3, 22), date(2026, 4, 19)) == 40
    assert money.booked("Alice", date(2026, 3, 22), date(2026, 4, 12)) == 30
    assert money.booked("Alice", date(2025, 12, 1), date(2026, 1, 25)) == 40
    assert money.planned("Carol", date(2026, 3, 22), date(2026, 4, 19)) is None
    assert money.booked("Carol", date(2026, 3, 22), date(2026, 4, 19)) is None


def test_a_week_at_zero_fte_in_plan_csv_plans_zero_hours(world):
    project = world.parent / "fy26"
    (project / "plan.csv").write_text(
        "name,effective_date,fte\nAlice,2026-01-01,0.5\nAlice,2026-03-01,0\n"
        "Bob,2026-01-01,0.5\n"
    )
    money = load_money(project)
    assert money.planned("Alice", date(2026, 3, 22), date(2026, 4, 19)) == 0
    assert money.planned("Bob", date(2026, 3, 22), date(2026, 4, 19)) > 0
