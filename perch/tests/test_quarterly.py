"""The quarterly report's numbers, worked by hand from the world in conftest.

Between Alice's readings of Mar 22 (160) and Apr 19 (200) she books 40/28 =
10/7 h a day; Bob, between Feb 22 (80) and Apr 19 (120), 40/56 = 5/7. So the
team books 15/7 h a day from Mar 22 to Apr 19, and $1,250/7 a day.
"""

import json
from dataclasses import replace
from datetime import date

import pytest
from budgie.core.eac import at_completion
from budgie.core.montecarlo import simulate
from budgie.core.signals import evaluate

from perch.core.board import load_board
from perch.core.config import load_config
from perch.core.estimates import load_estimates
from perch.core.join import calibrate
from perch.core.money import load_money
from perch.core.quarterly import build, last_complete_quarter, parse_quarter

FETCH_DAY = date(2026, 4, 20)


def make(world, quarter, today=FETCH_DAY, board=True, estimates=True):
    config = load_config(world)
    the_board = load_board(config.board_dump) if board else None
    money = load_money(config.budgie_project)
    rates = (
        calibrate(money.readings, the_board, config.people, money.year)
        if the_board
        else None
    )
    found = load_estimates(config.estimates) if estimates else {}
    return build(
        the_board, money, found, rates, config.people, quarter, today, "apollo"
    )


def test_a_quarter_is_its_calendar_months():
    assert parse_quarter("2026-Q3") == (date(2026, 7, 1), date(2026, 9, 30))
    assert parse_quarter("2026-q1") == (date(2026, 1, 1), date(2026, 3, 31))
    for bad in ("2026-Q5", "2026-Q0", "Q3", "2026Q3"):
        with pytest.raises(ValueError, match="2026-Q3"):
            parse_quarter(bad)


def test_the_default_is_the_last_complete_quarter():
    assert last_complete_quarter(2026, date(2026, 10, 1)) == "2026-Q3"
    assert last_complete_quarter(2026, date(2026, 9, 30)) == "2026-Q2"
    assert last_complete_quarter(2026, date(2027, 2, 1)) == "2026-Q4"
    # Nothing in the year is over yet: its first quarter, to date.
    assert last_complete_quarter(2026, date(2026, 2, 1)) == "2026-Q1"


def test_a_quarter_outside_the_budgie_year_is_refused(world):
    with pytest.raises(ValueError, match="2026"):
        make(world, "2025-Q4")


def test_budget_position_for_a_quarter_to_date(quarter_world):
    q = make(quarter_world, "2026-Q2")
    assert (q.name, q.start, q.end) == ("2026-Q2", date(2026, 4, 1), date(2026, 6, 30))
    assert q.to_date and q.through == date(2026, 4, 19)  # the latest reading
    p = q.position
    # Apr 1-19: 19 days at $1,250/7 a day.
    assert p.spent_quarter == pytest.approx(19 * 1250 / 7)
    assert p.spent_year == pytest.approx(200 * 100 + 120 * 50)
    assert (p.budget_start, p.budget_end) == (100000, 120000)
    assert [(r.effective_date, r.amount, r.note) for r in p.revisions] == [
        (date(2026, 4, 15), 120000, "Q2 increase")
    ]
    # Budgie's own estimate at completion, as `budgie forecast --as-of` runs it.
    money = load_money(quarter_world.parent / "fy26")
    eac = at_completion(money.people, money.readings, 2026, q.through, money.plan)
    sim = simulate(eac.people, iterations=money.iterations, seed=money.seed)
    sim = replace(sim, total_costs=sim.total_costs + 5000)  # the laptops
    assert p.p50 == pytest.approx(sim.percentile(50))
    assert (p.p10, p.p90) == (
        pytest.approx(sim.percentile(10)),
        pytest.approx(sim.percentile(90)),
    )
    assert p.signal.signal == evaluate(sim, 120000).signal


def test_a_pinned_budget_is_flat(world):
    p = make(world, "2026-Q2").position
    assert p.flat and p.revisions == ()
    assert (p.budget_start, p.budget_end) == (100000, 100000)


def test_throughput_by_iso_week(quarter_world):
    q = make(quarter_world, "2026-Q2")
    rows = [(w.label, w.start, w.end, w.closed) for w in q.weeks]
    assert rows == [
        ("2026-W14", date(2026, 4, 1), date(2026, 4, 5), 1),  # Bob's #13, Apr 1
        ("2026-W15", date(2026, 4, 6), date(2026, 4, 12), 1),  # Alice's #8
        ("2026-W16", date(2026, 4, 13), date(2026, 4, 19), 0),
    ]
    # W15 falls between readings: 7 interpolated days at 15/7 h.
    assert [w.hours for w in q.weeks] == pytest.approx([75 / 7, 15, 15])
    assert q.weeks[1].per_issue == pytest.approx(15)
    assert q.weeks[2].per_issue is None
    total = q.total
    assert (total.closed, total.hours) == (2, pytest.approx(285 / 7))
    assert q.total_per_issue == pytest.approx(285 / 7 / 2)


def test_a_finished_quarter_runs_to_its_last_day(world):
    q = make(world, "2026-Q1")
    assert not q.to_date and q.through == date(2026, 3, 31)
    assert len(q.weeks) == 14 and q.weeks[-1].start == date(2026, 3, 30)
    # Alice by Mar 31: 160 + 9 x 10/7; Bob: 80 + 37 x 5/7.
    alice, bob = 160 + 90 / 7, 80 + 185 / 7
    assert q.total.hours == pytest.approx(alice + bob)
    # Weeks starting before Jan 20 are outside the dump: unknown, not zero, so
    # Alice's two Jan 10 closes are not counted. Feb-Mar: Alice 5, Bob 4.
    assert [w.closed for w in q.weeks[:4]] == [None] * 4
    assert q.total.closed == 9
    known = [w for w in q.weeks if w.closed is not None]
    assert q.total_per_issue == pytest.approx(sum(w.hours for w in known) / 9)
    assert q.position.spent_quarter == pytest.approx(alice * 100 + bob * 50)


def test_a_label_still_in_progress_is_not_compared(world):
    q = make(world, "2026-Q1")
    # #101 is open, so epic::billing is 4 of 5 closed: no comparison yet.
    assert q.misses == ()
    assert q.in_progress == (("epic::billing", 4, 5),)
    # #1 and #2 carry their own 15 h; Alice's rate models 25 h each, at $100.
    rows = [(m.key, m.estimated, m.modelled, m.dollars) for m in q.issue_misses]
    assert rows == [
        ("#1", 15, pytest.approx(25), pytest.approx(1000)),
        ("#2", 15, pytest.approx(25), pytest.approx(1000)),
    ]


def test_a_label_finished_in_the_quarter_is_compared_whole(world):
    dump = world.parent / "dump.json"
    meta = json.loads(dump.read_text())
    for record in meta["history"]:
        if record["iid"] == 101:
            record["labels"] = []
    dump.write_text(json.dumps(meta))
    (billing,) = make(world, "2026-Q1").misses
    # #1-#4 all closed, the last on Feb 10; Alice's at 25 h: 100 against 60.
    assert (billing.label, billing.issues, billing.open) == ("epic::billing", 4, 0)
    assert billing.modelled == pytest.approx(100)
    assert billing.dollars == pytest.approx(40 * 100)
    # It finished in Q1, so Q2 has nothing to compare.
    q2 = make(world, "2026-Q2")
    assert (q2.misses, q2.in_progress, q2.issue_misses) == ((), (), ())


def test_without_estimates_there_is_no_miss_table(world):
    q = make(world, "2026-Q1", estimates=False)
    assert q.misses is None and q.issue_misses == () and q.in_progress == ()


def test_waiting_counts_blocked_days_and_moves_out_of_done(world):
    q = make(world, "2026-Q2")
    # #104 blocked Apr 6 through Apr 19 (14 days), #102 Apr 2-7 (5).
    assert q.blocked_days == 14 + 5
    assert q.reopened == 1  # #8 back out of Done on Apr 9


def test_a_done_label_dropped_on_close_is_not_a_reopen(world):
    dump = world.parent / "dump.json"
    meta = json.loads(dump.read_text())
    for record in meta["history"]:
        if record["iid"] == 13:  # Bob's, closed Apr 1: GitLab drops the label
            record["transitions"] = [["2026-04-01T13:00:00.000Z", "remove", "Done"]]
    dump.write_text(json.dumps(meta))
    assert make(world, "2026-Q2").reopened == 1


def test_staffing_changes_cost_the_year(quarter_world):
    (change,) = make(quarter_world, "2026-Q2").staffing
    assert (change.name, change.day, change.kind) == (
        "Bob",
        date(2026, 5, 1),
        "FTE change",
    )
    assert (change.fte_before, change.fte_after) == (0.5, 0.25)
    assert change.hours == pytest.approx(-332.664)
    assert change.dollars == pytest.approx(-16633.20)
    # Jan 1 rows are the starting team, not a change.
    assert make(quarter_world, "2026-Q1").staffing == ()


def test_a_dump_that_starts_mid_quarter_says_what_it_covers(world):
    q = make(world, "2026-Q1")
    assert q.board_note == "covers Jan 20 – Mar 31; the board dump keeps 90 days"
    assert make(world, "2026-Q2").board_note is None


def test_without_a_dump_or_readings_the_report_still_builds(world):
    (world.parent / "fy26" / "weekly.csv").unlink()
    q = make(world, "2026-Q1", board=False)
    assert q.board_note == "no board dump; run `perch fetch`"
    assert q.hours_note == "no hours readings; run `perch hours`"
    assert q.position.spent_quarter is None
    assert q.misses is None and q.blocked_days is None and q.reopened is None
    assert all(w.closed is None and w.hours is None for w in q.weeks)


def test_a_finished_quarter_stops_where_its_sources_stop(world):
    q = make(world, "2026-Q2", today=date(2026, 10, 1))
    assert q.through == date(2026, 6, 30)
    # Weeks after the Apr 19 reading are unknown, not zero.
    assert q.weeks[2].hours == pytest.approx(15) and q.weeks[3].hours is None
    assert q.total.hours == pytest.approx(285 / 7)
    # #104 counts to the Apr 20 fetch (15 days), not to Jun 30.
    assert q.blocked_days == 15 + 5


def test_a_dump_from_before_the_quarter_says_so(world):
    q = make(world, "2026-Q3", today=date(2026, 10, 1))
    assert q.board_note == "the board dump is from 2026-04-20; run `perch fetch`"
    assert q.blocked_days is None and q.reopened is None
    assert q.total.closed is None and q.total_per_issue is None


def test_readings_that_stop_early_say_so(world):
    q = make(world, "2026-Q2", today=date(2026, 10, 1))
    assert q.hours_note == (
        "readings run to Apr 19; spent covers Apr 1 – Apr 19; run `perch hours`"
    )
    assert q.read_to == date(2026, 4, 19)
    assert q.position.spent_quarter == pytest.approx(19 * 1250 / 7)
    q3 = make(world, "2026-Q3", today=date(2026, 10, 1))
    assert (
        q3.hours_note == "readings run to Apr 19, before the quarter; run `perch hours`"
    )
    assert q3.position.spent_quarter is None
    assert q3.position.spent_year == 200 * 100 + 120 * 50
    assert make(world, "2026-Q1").hours_note is None
