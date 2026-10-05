"""The quarterly report's numbers, worked by hand from the world in conftest.

Between Alice's readings of Mar 22 (160) and Apr 19 (200) she books 40/28 =
10/7 h a day; Bob, between Feb 22 (80) and Apr 19 (120), 40/56 = 5/7. So the
team books 15/7 h a day from Mar 22 to Apr 19, and $1,250/7 a day.
"""

import json
from dataclasses import replace
from datetime import date

import pytest
from budgie.core.calendar import year_span
from budgie.core.eac import at_completion
from budgie.core.montecarlo import simulate
from budgie.core.person import HoursEstimate, Person
from budgie.core.signals import evaluate

from perch.core.board import load_board
from perch.core.config import load_config
from perch.core.estimates import load_estimates
from perch.core.join import calibrate
from perch.core.money import Money, load_money, load_snapshot
from perch.core.quarterly import (
    build,
    last_complete_quarter,
    parse_quarter,
    quarter_to_date,
)
from perch.core.report_mail import render_md
from perch.tests.conftest import issue, since

FETCH_DAY = date(2026, 4, 20)


def make(world, quarter, today=FETCH_DAY, board=True, estimates=True):
    config = load_config(world)
    the_board = load_board(config.board_dump) if board else None
    money = load_money(config.budgie_project)
    rates = (
        calibrate(money.readings, the_board, config.people, money.span)
        if the_board
        else None
    )
    found = load_estimates(config.estimates) if estimates else {}
    return build(
        the_board, money, found, rates, config.people, quarter, today, "apollo"
    )


def test_a_quarter_is_its_calendar_months():
    assert parse_quarter("2026-Q3", year_span(2026)) == (
        date(2026, 7, 1),
        date(2026, 9, 30),
    )
    assert parse_quarter("2026-q1", year_span(2026)) == (
        date(2026, 1, 1),
        date(2026, 3, 31),
    )
    for bad in ("2026-Q5", "2026-Q0", "Q3", "2026Q3"):
        with pytest.raises(ValueError, match="2026-Q3"):
            parse_quarter(bad, year_span(2026))


def test_the_default_is_the_last_complete_quarter():
    assert last_complete_quarter(year_span(2026), date(2026, 10, 1)) == "2026-Q3"
    assert last_complete_quarter(year_span(2026), date(2026, 9, 30)) == "2026-Q2"
    assert last_complete_quarter(year_span(2026), date(2027, 2, 1)) == "2026-Q4"
    # Nothing in the year is over yet: its first quarter, to date.
    assert last_complete_quarter(year_span(2026), date(2026, 2, 1)) == "2026-Q1"


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
    eac = at_completion(
        money.people, money.readings, year_span(2026), q.through, money.plan
    )
    # The cost lines go in as `budgie forecast` passes them: the laptops, $5,000.
    sim = simulate(
        eac.people, iterations=money.iterations, seed=money.seed, costs=money.costs
    )
    assert sim.mean == pytest.approx(
        simulate(eac.people, iterations=money.iterations, seed=money.seed).mean + 5000
    )
    assert p.p50 == pytest.approx(sim.percentile(50))
    assert (p.p10, p.p90) == (
        pytest.approx(sim.percentile(10)),
        pytest.approx(sim.percentile(90)),
    )
    assert p.signal.signal == evaluate(sim, 120000).signal


def test_a_cost_line_with_a_range_is_sampled_as_budgie_forecast_does(quarter_world):
    """Laptops $5,000, low 4,000, high 7,000: Budgie samples the line with the
    labor, so the percentiles are its own `simulate(..., costs=...)`."""
    costs = quarter_world.parent / "fy26" / "costs.csv"
    costs.write_text(costs.read_text().replace("5000,,,", "5000,4000,7000,"))
    q = make(quarter_world, "2026-Q2")
    snap = load_snapshot(quarter_world.parent / "fy26")
    assert [(c.low, c.high) for c in snap.costs] == [(4000, 7000)]
    eac = at_completion(
        snap.people, snap.readings, year_span(2026), q.through, snap.plan
    )
    sim = simulate(eac.people, iterations=snap.iterations, seed=1, costs=snap.costs)
    p = q.position
    assert (p.p10, p.p50, p.p90) == (
        pytest.approx(sim.percentile(10)),
        pytest.approx(sim.percentile(50)),
        pytest.approx(sim.percentile(90)),
    )


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
    # The same once Q1 is long over.
    assert make(world, "2026-Q1", today=date(2026, 10, 1)).misses == (billing,)
    # #1-#4 all closed, the last on Feb 10; Alice's at 25 h: 100 against 60.
    assert (billing.label, billing.issues, billing.open) == ("epic::billing", 4, 0)
    assert billing.modelled == pytest.approx(100)
    assert billing.dollars == pytest.approx(40 * 100)
    # It finished in Q1, so Q2 has nothing to compare.
    q2 = make(world, "2026-Q2")
    assert (q2.misses, q2.in_progress, q2.issue_misses) == ((), (), ())


def test_a_label_finished_later_is_in_progress_at_the_quarters_end(world):
    dump = world.parent / "dump.json"
    meta = json.loads(dump.read_text())
    for record in meta["history"]:
        if record["iid"] == 101:  # after Alice's last reading: rates unchanged
            record["closed_at"] = "2026-04-20T07:00:00.000Z"
    dump.write_text(json.dumps(meta))
    # Run after Q2: #101 was still open on Mar 31, so billing was 4 of 5 then.
    q1 = make(world, "2026-Q1", today=date(2026, 10, 1))
    assert (q1.misses, q1.in_progress) == ((), (("epic::billing", 4, 5),))
    # It finished in Q2, so Q2 compares it whole.
    (billing,) = make(world, "2026-Q2", today=date(2026, 10, 1)).misses
    assert (billing.label, billing.issues, billing.open) == ("epic::billing", 5, 0)


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


def test_the_dumps_since_is_where_its_coverage_starts(world):
    since(world, "2026-02-01")
    q = make(world, "2026-Q1")
    assert q.board_note == "covers Feb 1 – Mar 31; the board dump starts Feb 1"
    assert q.board_span == (date(2026, 2, 1), date(2026, 3, 31))
    # W05 (Jan 26 - Feb 1) starts before the dump: unknown; W06 on is counted.
    assert [w.closed for w in q.weeks[:6]] == [None] * 5 + [0]
    assert q.total.closed == 5  # Alice 2 + 3; Bob's 4 on Feb 1 are in the unknown W05


def test_the_previous_quarter_sits_beside_it_when_the_dump_covers_it(world):
    """Q1, all of it: Alice closed 2 + 2 + 3, Bob 4; Alice booked 160 + 90/7
    and Bob 80 + 185/7 h by Mar 31; every Blocked move is in April."""
    since(world, "2026-01-01")
    q = make(world, "2026-Q2")
    prev = q.previous
    assert (prev.label, prev.start, prev.end) == (
        "2026-Q1",
        date(2026, 1, 1),
        date(2026, 3, 31),
    )
    assert prev.closed == 11
    assert prev.hours == pytest.approx(240 + 275 / 7)
    assert prev.per_issue == pytest.approx((240 + 275 / 7) / 11)
    assert q.previous_blocked == 0
    # Q1's previous quarter is outside the Budgie year.
    assert make(world, "2026-Q1").previous is None


def test_no_previous_quarter_unless_the_dump_covers_all_of_it(world):
    assert make(world, "2026-Q2").previous is None  # an old dump: no since
    since(world, "2026-01-02")
    q = make(world, "2026-Q2")
    assert q.previous is None and q.previous_blocked is None


def test_an_issue_created_after_the_quarter_is_not_in_its_label(world):
    """#108 joins epic::billing on Apr 5, after Q1: Q1's billing was still
    4 of 5 (#101 open). With #101 out of the label, billing finished in Q1 as
    its 4 issues, whatever was added to it later."""
    dump = world.parent / "dump.json"
    meta = json.loads(dump.read_text())
    late = issue(108, "asmith", labels=["epic::billing"])
    late["created_at"] = "2026-04-05T09:00:00.000Z"
    meta["history"].append(late)
    dump.write_text(json.dumps(meta))
    q1 = make(world, "2026-Q1", today=date(2026, 10, 1))
    assert q1.in_progress == (("epic::billing", 4, 5),)
    for record in meta["history"]:
        if record["iid"] == 101:
            record["labels"] = []
    dump.write_text(json.dumps(meta))
    (billing,) = make(world, "2026-Q1", today=date(2026, 10, 1)).misses
    assert (billing.label, billing.issues, billing.open) == ("epic::billing", 4, 0)


FY27 = year_span(2027, "10-01")


def test_fiscal_quarters_come_from_budgies_year():
    assert parse_quarter("FY27-Q1", FY27) == (date(2026, 10, 1), date(2026, 12, 31))
    assert parse_quarter("fy27-q4", FY27) == (date(2027, 7, 1), date(2027, 9, 30))
    with pytest.raises(ValueError, match="outside the Budgie project's year, FY27"):
        parse_quarter("2026-Q3", FY27)
    with pytest.raises(ValueError, match="FY27-Q3"):
        parse_quarter("FY27Q1", FY27)


def test_the_default_fiscal_quarter_is_the_last_complete_one():
    assert last_complete_quarter(FY27, date(2026, 12, 31)) == "FY27-Q1"  # none over yet
    assert last_complete_quarter(FY27, date(2027, 1, 1)) == "FY27-Q1"
    assert last_complete_quarter(FY27, date(2027, 4, 1)) == "FY27-Q2"


def test_a_fiscal_quarter_report_is_named_and_dated_by_the_span():
    money = Money(
        span=FY27,
        hourly_cost={"Alice": 50.0},
        people=[Person("Alice", 50.0, HoursEstimate.constant(1000.0))],
    )
    q = build(None, money, {}, None, {}, "FY27-Q1", date(2027, 1, 15), "proj")
    assert (q.name, q.start, q.end, q.year_start) == (
        "FY27-Q1",
        date(2026, 10, 1),
        date(2026, 12, 31),
        date(2026, 10, 1),
    )
    assert "FY27-Q1 runs Oct 1 – Dec 31" in render_md(q)


def test_pace_is_hours_booked_against_hours_planned(quarter_world):
    """Apr 1-19 holds 13 working days of 7.968 h. Alice and Bob are both
    planned at 0.5 (Bob's cut is May 1), so 2 x 0.5 x 13 x 7.968 = 103.584 h
    planned; booked is the 19 days at 15/7 h."""
    p = make(quarter_world, "2026-Q2").position
    assert p.planned_quarter == pytest.approx(13 * 7.968)
    assert p.booked_quarter == pytest.approx(285 / 7)


def test_without_allocations_nothing_is_planned(quarter_world):
    config = load_config(quarter_world)
    board = load_board(config.board_dump)
    money = replace(load_money(config.budgie_project), pace={})
    q = build(board, money, {}, None, config.people, "2026-Q2", FETCH_DAY, "apollo")
    assert q.position.planned_quarter is None
    assert q.position.booked_quarter == pytest.approx(285 / 7)


def test_readings_that_stop_before_the_quarter_give_no_pace(world):
    # The readings end Apr 19, before Q3: neither figure, not planned alone.
    p = make(world, "2026-Q3").position
    assert (p.booked_quarter, p.planned_quarter) == (None, None)


# Issues created in Q2; every other issue gets created()'s default, Jan 2.
APRIL = {103: "2026-04-02", 105: "2026-04-07", 106: "2026-04-08", 107: "2026-04-14"}


def created(world, days, default="2026-01-02"):
    """Give every issue in the world's dump a `created_at`: `days` maps an iid
    to its day, the rest get `default`."""
    dump = world.parent / "dump.json"
    meta = json.loads(dump.read_text())
    for record in meta["history"]:
        record["created_at"] = f"{days.get(record['iid'], default)}T09:00:00.000Z"
    dump.write_text(json.dumps(meta))


def test_opened_issues_by_iso_week(quarter_world):
    """#103 on Apr 2 (W14), #105 and #106 on Apr 7 and 8 (W15), #107 on Apr 14
    (W16); closes are Bob's #13 (W14) and Alice's #8 (W15)."""
    created(quarter_world, APRIL)
    q = make(quarter_world, "2026-Q2")
    assert [w.opened for w in q.weeks] == [1, 2, 1]
    assert (q.total.opened, q.total.closed) == (4, 2)
    assert q.net_scope == 2


def test_open_work_can_shrink(quarter_world):
    created(quarter_world, {103: "2026-04-02"})
    q = make(quarter_world, "2026-Q2")
    assert [w.opened for w in q.weeks] == [1, 0, 0]
    assert q.net_scope == -1


def test_a_dump_without_creation_days_counts_no_opened(quarter_world):
    q = make(quarter_world, "2026-Q2")  # the world's dump has no created_at
    assert [w.opened for w in q.weeks] == [None] * 3
    assert q.total.opened is None and q.net_scope is None


def test_a_dump_missing_some_creation_days_counts_no_opened(quarter_world):
    """A partial count would undercount what opened: all or nothing."""
    created(quarter_world, APRIL)
    dump = quarter_world.parent / "dump.json"
    meta = json.loads(dump.read_text())
    del meta["history"][0]["created_at"]
    dump.write_text(json.dumps(meta))
    q = make(quarter_world, "2026-Q2")
    assert [w.opened for w in q.weeks] == [None] * 3
    assert q.net_scope is None


def test_a_week_outside_the_dump_has_no_opened_count(world):
    """Weeks starting before Jan 20 are outside the dump, as for closes. Every
    issue was created Jan 2, so the counted weeks open nothing and close 9."""
    created(world, {})
    q = make(world, "2026-Q1")
    assert [w.opened for w in q.weeks[:4]] == [None] * 4
    assert q.total.opened == 0
    assert q.net_scope == -9


def test_the_previous_quarter_counts_opened_too(world):
    """20 issues in the dump (#1-#13 closed, #101-#107 open); 4 created in
    April, so 16 opened in Q1."""
    created(world, APRIL)
    since(world, "2026-01-01")
    prev = make(world, "2026-Q2").previous
    assert (prev.opened, prev.closed) == (16, 11)


def test_the_history_figures_for_the_quarter_so_far(quarter_world):
    """The latest reading is Apr 19, so Q2 through Apr 19: the pace and net
    scope the report shows."""
    created(quarter_world, APRIL)
    config = load_config(quarter_world)
    board, money = load_board(config.board_dump), load_money(config.budgie_project)
    got = quarter_to_date(board, money, FETCH_DAY)
    assert got["pace"] == pytest.approx(285 / 7 / (13 * 7.968))
    assert got["net_scope"] == 2


def test_outside_the_budgie_year_there_are_no_history_figures(quarter_world):
    config = load_config(quarter_world)
    board = load_board(config.board_dump)
    money = replace(load_money(config.budgie_project), readings={})
    got = quarter_to_date(board, money, date(2027, 2, 1))
    assert got == {"pace": None, "net_scope": None}


def test_without_a_dump_only_the_pace_is_known(quarter_world):
    money = load_money(load_config(quarter_world).budgie_project)
    got = quarter_to_date(None, money, FETCH_DAY)
    assert got["pace"] == pytest.approx(285 / 7 / (13 * 7.968))
    assert got["net_scope"] is None
