from dataclasses import replace
from datetime import date

import pytest
from budgie.core.calendar import year_span

from perch.core.board import Board, Issue, load_board
from perch.core.config import load_config
from perch.core.estimates import load_estimates
from perch.core.join import Rates, calibrate, hours_for, notes, person_rows, rollup
from perch.core.money import load_money


@pytest.fixture
def loaded(world):
    config = load_config(world)
    board = load_board(config.board_dump)
    money = load_money(config.budgie_project)
    estimates = load_estimates(config.estimates)
    rates = calibrate(money.readings, board, config.people, money.span)
    return config, board, money, estimates, rates


def test_rows_are_worked_by_hand(loaded):
    config, board, money, estimates, rates = loaded
    rows = {
        r.name: r for r in person_rows(board, estimates, rates, config.people, money)
    }
    assert list(rows) == ["Alice", "Bob", "unassigned", "unmapped"]

    alice = rows["Alice"]
    # #101 is estimated (8, 10, 14); #102 and #103 are 25 h each, spread 20-40.
    assert (alice.open, alice.low, alice.mode, alice.high) == (
        3, pytest.approx(48), pytest.approx(60), pytest.approx(94),
    )  # fmt: skip
    assert alice.cost == pytest.approx(6000)
    assert (alice.left, alice.gap) == (796, pytest.approx(736))
    assert alice.bases == ("estimates", "type model (6 intervals)")

    bob = rows["Bob"]
    assert bob.low == bob.mode == bob.high == pytest.approx(48)  # 2 x 24, no spread
    assert (bob.cost, bob.left) == (pytest.approx(2400), 876)

    # Nobody's issue is costed at the team's pace and the blended $75/h.
    nobody = rows["unassigned"]
    assert nobody.mode == pytest.approx(320 / 13)
    assert nobody.hourly_cost == 75 and nobody.left is None and nobody.gap is None
    assert rows["unmapped"].mode == pytest.approx(320 / 13)


def test_an_issue_falls_down_the_ladder_of_bases(loaded):
    _, board, _, estimates, rates = loaded
    issue = next(i for i in board.open if i.iid == 102)
    flat = Rates(rates.people, rates.team, types=None)
    assert hours_for(issue, "Alice", estimates, flat).basis == "own rate (4 samples)"
    assert hours_for(issue, "Carol", estimates, flat).basis == "team rate (6 samples)"
    assert hours_for(issue, "Alice", estimates, Rates({}, None, None)) is None


def test_the_rollup_uses_budgies_simulation_and_signal(loaded):
    config, board, money, estimates, rates = loaded
    rows = person_rows(board, estimates, rates, config.people, money)
    summary = rollup(rows, money, iterations=5000)

    assert summary.spent_cost == 26000 and summary.as_of == date(2026, 4, 19)
    assert summary.budget_left == 100000 - 26000 - 5000
    assert summary.clear_p10 <= summary.clear_p50 <= summary.clear_p90
    # Alice 48-94 h at $100, Bob 48 h at $50, two issues at 24.6 h and $75.
    assert 10_500 < summary.clear_p10 and summary.clear_p90 < 16_000
    assert summary.headroom == pytest.approx(69000 - summary.clear_p50)
    assert summary.signal.signal.name == "GREEN"
    assert rollup(rows, money, iterations=5000) == summary  # seeded by budgie.yaml

    broke = rollup(rows, replace(money, budget=40000), iterations=5000)
    assert broke.signal.signal.name == "RED"  # 9,000 left cannot clear ~12,000
    assert rollup(rows, replace(money, budget=None)).signal is None


def test_no_actuals_means_no_basis_not_a_made_up_number(loaded):
    config, board, money, estimates, _ = loaded
    rates = calibrate({}, board, config.people, money.span)
    rows = {
        r.name: r for r in person_rows(board, estimates, rates, config.people, money)
    }
    assert (rows["Alice"].mode, rows["Alice"].no_basis) == (10, 2)  # only #101
    assert (rows["Bob"].mode, rows["Bob"].no_basis) == (0, 2)
    said = " ".join(notes(board, list(rows.values()), config.people, money))
    assert "6 open issue(s) have no estimate and no rate" in said


def test_notes_name_what_the_lead_should_distrust(loaded):
    config, board, money, estimates, rates = loaded
    rows = person_rows(board, estimates, rates, config.people, money)
    assert notes(board, rows, config.people, money) == [
        "No entry under `people:` in perch.yaml for: cdoe."
    ]
    stale = replace(board, fetched_on=date(2026, 6, 1))
    people = config.people | {"cdoe": "Carol"}
    said = " ".join(notes(stale, rows, people, money))
    assert "Not in Budgie's people.csv, so uncosted: Carol" in said
    assert "different moments" in said


def test_calibrate_counts_a_december_close_inside_a_fiscal_year():
    fy27 = year_span(2027, "10-01")
    board = Board(
        "grp/proj", "Dev", date(2026, 12, 31),
        (Issue(1, "t", "asmith", (), date(2026, 12, 15)),),
    )  # fmt: skip
    rates = calibrate(
        {"Alice": [(date(2026, 12, 27), 40.0)]}, board, {"asmith": "Alice"}, fy27
    )
    # Oct 1 to Dec 27: 40 h for 1 issue. A calendar-year filter dropped the close.
    assert rates.people["Alice"].mode == 40.0
