import pytest

from perch.core.accuracy import by_label, by_person
from perch.core.board import load_board
from perch.core.config import load_config
from perch.core.estimates import load_estimates
from perch.core.join import calibrate
from perch.core.money import load_money
from perch.tests.conftest import since


@pytest.fixture
def loaded(world):
    config = load_config(world)
    board = load_board(config.board_dump)
    money = load_money(config.budgie_project)
    rates = calibrate(money.readings, board, config.people, money.span)
    return config, board, money, rates


def test_a_label_is_compared_with_modelled_hours(loaded, world):
    config, board, money, rates = loaded
    estimates = load_estimates(config.estimates)
    (billing,) = by_label(estimates, board, rates, config.people, money)
    # Four closed and one open issue, all Alice's at 25 h: 125 against 60.
    assert (billing.label, billing.issues, billing.open) == ("epic::billing", 5, 1)
    assert billing.modelled == pytest.approx(125)
    assert billing.ratio == pytest.approx(125 / 60)
    assert billing.dollars == pytest.approx(65 * 100)


def test_a_person_needs_half_their_issues_estimated(loaded, world):
    config, board, money, _ = loaded
    thin = load_estimates(config.estimates)  # 2 of Alice's 8 closed issues
    alice, bob = by_person(thin, board, config.people, money)
    assert (alice.closed, alice.covered, alice.ratio) == (8, 2, None)
    assert (bob.closed, bob.covered, bob.ratio) == (5, 0, None)

    (world.parent / "estimates.csv").write_text(
        "key,hours,low,high\n#1,15,,\n#2,15,,\n#3,15,,\n#4,15,,\n"
    )
    alice, _ = by_person(load_estimates(config.estimates), board, config.people, money)
    # Half her issues were estimated, so half her 200 booked hours: 100 / 60.
    assert alice.coverage == 0.5
    assert alice.ratio == pytest.approx(100 / 60)


def test_a_person_is_measured_from_where_the_dump_history_starts(world):
    since(world, "2026-02-01")  # between Alice's week 4 and week 8 readings
    config = load_config(world)
    board = load_board(config.board_dump)
    money = load_money(config.budgie_project)
    alice, bob = by_person({}, board, config.people, money)
    # From the day after week 8: Alice's 3 + 1 closes on 200 - 100 booked hours.
    assert (alice.closed, alice.booked) == (4, 100)
    # Bob's first reading is week 8 too, so his Feb 1 closes fall before it.
    assert (bob.closed, bob.booked) == (1, 40)
