"""Events: what is coming, name-free, team level. Today is 2026-06-01."""

from dataclasses import replace
from datetime import date

from budgie.core.plan import AllocationPlan, PlanEntry

from perch.core import blocks as _blocks
from perch.core import events
from perch.core.board import load_board
from perch.core.money import load_money
from perch.tests.conftest import build_home

TODAY = date(2026, 6, 1)


def _money(world):
    return load_money(world.parent / "fy26")


def _plan(*rows):
    return AllocationPlan(
        tuple(PlanEntry(n, date.fromisoformat(d), f) for n, d, f in rows)
    )


def _got(evs):
    return [(e.day.isoformat(), e.kind, e.what) for e in evs]


def test_holidays_and_the_quarter_end(world):
    got = _got(events.build("a", _money(world), None, TODAY, 30))
    assert got == [
        ("2026-06-19", "holiday", got[0][2]),  # a Friday, Budgie's own name
        ("2026-06-30", "quarter end", "2026-Q2"),
    ]
    got60 = events.build("a", _money(world), None, TODAY, 60)
    # Independence Day observed Friday 07-03; Saturday 07-04 is dropped
    assert [e.day.isoformat() for e in got60] == [
        "2026-06-19",
        "2026-06-30",
        "2026-07-03",
    ]


def test_budget_revision(quarter_world):
    money = _money(quarter_world)
    got = events.build("a", money, None, TODAY, 30)
    assert [e for e in got if e.kind == "budget"] == []  # 04-15 is past
    got = events.build("a", money, None, date(2026, 4, 1), 30)
    assert _got([e for e in got if e.kind == "budget"]) == [
        ("2026-04-15", "budget", "budget $100,000 → $120,000")
    ]


def test_staffing_has_no_names(world):
    plan = _plan(
        ("Alice", "2026-01-01", 0.5),
        ("Alice", "2026-06-10", 0.75),
        ("Bob", "2026-06-10", 0.5),
        ("Bob", "2026-06-12", 0),
        ("Carol", "2026-06-11", 0.5),
    )
    money = replace(_money(world), plan=plan)
    got = events.build("a", money, None, TODAY, 30)
    staff = [e for e in got if e.kind == "staffing"]
    # same day: ordered by text (the spec's sort), never by a person or a figure
    assert [e.what for e in staff] == [
        "a join · FTE 0 → 0.5",  # Bob, 06-10
        "an FTE change · FTE 0.5 → 0.75",  # Alice, 06-10
        "a join · FTE 0 → 0.5",  # Carol, 06-11
        "a leave · FTE 0.5 → 0",  # Bob, 06-12
    ]
    text = repr(got)
    assert not any(n in text for n in ("Alice", "Bob", "Carol"))


def test_milestones_group_by_name_and_due(world):
    board = load_board(world.parent / "dump.json")
    issues = tuple(
        replace(i, milestone="M1", milestone_due=date(2026, 6, 12))
        if i.iid in (101, 102, 103)
        else replace(i, milestone="M0", milestone_due=date(2026, 5, 20))
        if i.iid == 104
        else replace(i, milestone="M9", milestone_due=date(2026, 9, 1))
        if i.iid == 105
        else i
        for i in board.issues
    )
    got = events.build("a", _money(world), replace(board, issues=issues), TODAY, 30)
    ms = [e for e in got if e.kind == "milestone"]
    assert [(e.day.isoformat(), e.n, e.what) for e in ms] == [
        ("2026-05-20", 1, "milestone M0 · 1 open (dump 04-20) · overdue"),
        ("2026-06-12", 3, "milestone M1 · 3 open (dump 04-20)"),
    ]  # M9 is past the window


def test_empty_window_and_days_zero(world):
    assert events.build("a", _money(world), None, date(2026, 6, 2), 0) == ()
    out = events.blocks(events.Calendar((), (), ()), TODAY, 30)
    assert out == [_blocks.text("nothing in the next 30 days", tone="dim")]


def test_past_the_year_end(world):
    money = _money(world)
    got = events.build("a", money, None, date(2026, 12, 20), 30)
    assert _got(got) == [
        ("2026-12-25", "holiday", got[0].what),
        ("2026-12-31", "year end", "2026 ends"),
    ]
    note = events.span_note("a", money, date(2026, 12, 20), 30)
    assert note == "a: window runs past 2026 end: roll the Budgie year"
    assert events.span_note("a", money, TODAY, 30) == ""


def test_build_all_collapses_and_orders(tmp_path):
    home = build_home(tmp_path, "apollo", "borealis")
    (home.projects_dir / "borealis" / "dump.json").unlink()
    cal = events.build_all(home, TODAY, 30)
    assert [(e.project, e.kind) for e in cal.events] == [
        ("all (2)", "holiday"),
        ("all (2)", "quarter end"),
    ]
    assert cal.errors == () and cal.notes == ()
    one = events.build_all(home, TODAY, 30, names=["apollo"])
    assert {e.project for e in one.events} == {"apollo"}


def test_build_all_names_a_broken_project(tmp_path):
    home = build_home(tmp_path, "apollo", "borealis")
    (home.projects_dir / "borealis" / "fy26" / "budgie.yaml").write_text(": : bad")
    cal = events.build_all(home, TODAY, 30)
    assert cal.errors == ("borealis: budgie unreadable, run perch doctor",)
    assert {e.project for e in cal.events} == {"apollo"}


def test_blocks_are_valid_and_never_rank(tmp_path):
    home = build_home(tmp_path, "apollo")
    cal = events.build_all(home, TODAY, 60)
    out = events.blocks(cal, TODAY, 60)
    assert out[0]["columns"] == ["date", "project", "kind", "what"]
    assert out[0]["rows"][0][:3] == ["2026-06-19", "apollo", "holiday"]
    for b in out:
        assert _blocks.parse(__import__("json").dumps(b)) == b
    text = repr(out).lower()
    assert not any(w in text for w in ("worst", "best", "slow", "underperforming"))
    assert not any(n in text for n in ("alice", "bob"))
