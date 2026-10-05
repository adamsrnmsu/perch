"""The tape: newest-first events from files, team level only."""

import json
from dataclasses import fields, replace
from datetime import date

from budgie.core.budget import Budget, BudgetRevision
from budgie.core.plan import AllocationPlan, PlanEntry

from perch.core import sources, tape
from perch.tests.conftest import build_home

TODAY = date(2026, 4, 20)  # window since 02-23


def _src(tmp_path, name="apollo"):
    home = build_home(tmp_path, name)
    return home, sources.load(home, name)


def _team(week, day, headroom, signal):
    return {
        "week": week,
        "date": day,
        "kind": "team",
        "name": "team",
        "headroom": headroom,
        "signal": signal,
    }


FLIPS = [
    _team("2026-W36", "2026-09-01", 20000.0, "green"),
    _team("2026-W37", "2026-09-03", 10000.0, "yellow"),
    _team("2026-W38", "2026-09-09", -22000.0, "red"),
]


def test_the_worked_world_in_order(tmp_path):
    home, src = _src(tmp_path)
    (home.projects_dir / "apollo" / "monday.json").write_text(
        '{"week": "2026-W17", "step": "board", "code": 2, "at": "2026-04-19T09:00:00"}'
    )
    src = sources.load(home, "apollo")
    got = tape.project_tape(src, "apollo", TODAY)
    assert [(e.day.isoformat(), e.kind, e.text) for e in got] == [
        ("2026-04-20", "board", "board fetched, 7 open"),
        ("2026-04-19", "hours", "hours reading through 04-19"),
        ("2026-04-19", "failed", "monday: board exited 2"),
        ("2026-04-10", "closed", "1 issue closed"),
        ("2026-04-01", "closed", "1 issue closed"),
        ("2026-03-10", "closed", "3 issues closed"),
    ]
    assert {e.project for e in got} == {"apollo"}


def test_the_horizon_and_future_rows(tmp_path):
    _, src = _src(tmp_path)
    got = tape.project_tape(src, "apollo", TODAY, days=10)
    assert [e.day for e in got if e.kind == "closed"] == [date(2026, 4, 10)]
    assert (
        tape.project_tape(src, "apollo", date(2026, 4, 5), days=30)[0].kind == "closed"
    )
    assert not [
        e
        for e in tape.project_tape(src, "apollo", date(2026, 4, 5))
        if e.kind == "board"
    ]  # the 04-20 fetch is in the future


def test_flips_and_figures(tmp_path):
    _, src = _src(tmp_path)
    src = replace(src, rows=FLIPS, board=None, money=None)
    got = tape.project_tape(src, "apollo", date(2026, 9, 10))
    assert [(e.day.isoformat(), e.kind, e.text) for e in got] == [
        ("2026-09-09", "flip", "W37→W38: YELLOW→RED, headroom −$32,000"),
        ("2026-09-03", "flip", "W36→W37: GREEN→YELLOW, headroom −$10,000"),
    ]
    quiet = [
        replace(
            r,
        )
        if False
        else dict(r, signal="green")
        for r in FLIPS[:2]
    ]
    got = tape.project_tape(replace(src, rows=quiet), "apollo", date(2026, 9, 10))
    assert [e.kind for e in got] == ["figures"]


def test_a_duplicated_history_week_counts_once(tmp_path):
    _, src = _src(tmp_path)
    rows = [FLIPS[0], FLIPS[1], dict(FLIPS[1])]
    got = tape.project_tape(
        replace(src, rows=rows, board=None, money=None), "apollo", date(2026, 9, 10)
    )
    assert len(got) == 1


def test_budget_and_plan_moves_carry_no_name_or_note(tmp_path):
    _, src = _src(tmp_path)
    money = replace(
        src.money,
        budget_revisions=Budget(
            (
                BudgetRevision(date(2026, 1, 1), 100000.0, "Original"),
                BudgetRevision(date(2026, 4, 15), 120000.0, "backfill for Alice"),
            )
        ),
        plan=AllocationPlan(
            (
                PlanEntry("Alice", date(2026, 1, 1), 0.5),
                PlanEntry("Alice", date(2026, 4, 12), 0),
                PlanEntry("Bob", date(2026, 1, 1), 0),  # no first-day row
            )
        ),
    )
    got = tape.project_tape(replace(src, money=money), "apollo", TODAY)
    texts = {e.kind: e.text for e in got}
    assert texts["budget"] == "budget $100,000 → $120,000"
    assert texts["plan"] == "plan: a leave · FTE 0.5 → 0"
    assert [e.kind for e in got if e.kind in ("budget", "plan")] == ["budget", "plan"]
    assert "Alice" not in repr(got)
    assert not {"name", "person"} & {f.name for f in fields(tape.TapeEntry)}


def test_two_same_day_joins_are_both_kept(tmp_path):
    _, src = _src(tmp_path)
    plan = AllocationPlan(
        (
            PlanEntry("Alice", date(2026, 4, 12), 0.5),
            PlanEntry("Bob", date(2026, 4, 12), 0.5),
        )
    )
    got = tape.project_tape(
        replace(src, money=replace(src.money, plan=plan)), "a", TODAY
    )
    assert [e.text for e in got if e.kind == "plan"] == [
        "plan: a join · FTE 0 → 0.5"
    ] * 2


def test_a_corrupt_failure_file_is_one_fixed_error_entry(tmp_path):
    home, _ = _src(tmp_path)
    (home.projects_dir / "apollo" / "monday.json").write_text("{")
    got = [
        e
        for e in tape.project_tape(sources.load(home, "apollo"), "apollo", TODAY)
        if e.kind == "error"
    ]
    assert [(e.day, e.text) for e in got] == [
        (TODAY, "monday.json unreadable, run perch doctor")
    ]


def test_as_of_caps_today_and_rows(tmp_path):
    _, src = _src(tmp_path)
    src = replace(src, rows=FLIPS, board=None, money=None)
    got = tape.project_tape(src, "apollo", date(2026, 9, 20), asof="2026-W37")
    assert [e.text for e in got] == ["W36→W37: GREEN→YELLOW, headroom −$10,000"]
    # today is capped at W37's Sunday (09-13): a 04-20 board stays in the past
    _, live = _src(tmp_path / "x")
    got = tape.project_tape(live, "apollo", date(2026, 9, 20), asof="2026-W17")
    assert got[0].day == date(2026, 4, 20)  # W17 ends 04-26: the fetch shows
    got = tape.project_tape(live, "apollo", date(2026, 9, 20), asof="2026-W16")
    assert not [e for e in got if e.kind == "board"]  # W16 ends 04-19


def test_merge_sorts_day_then_project_then_kind(tmp_path):
    e = tape.TapeEntry
    d1, d2 = date(2026, 4, 2), date(2026, 4, 1)
    got = tape.merge(
        {
            "b": [e(d1, "b", "closed", "x"), e(d2, "b", "board", "y")],
            "a": [e(d1, "a", "failed", "z"), e(d1, "a", "board", "w")],
        },
        ["b", "a"],
    )
    assert [(x.day, x.project, x.kind) for x in got] == [
        (d1, "b", "closed"),
        (d1, "a", "board"),
        (d1, "a", "failed"),
        (d2, "b", "board"),
    ]


def test_tape_over_a_home_in_project_order(tmp_path):
    home = build_home(tmp_path, "apollo", "beta")
    got = tape.tape(home, TODAY)
    assert [e.project for e in got if e.kind == "board"] == ["apollo", "beta"]
    only = tape.tape(home, TODAY, names=["beta"])
    assert {e.project for e in only} == {"beta"}
    assert tape.tape(home, TODAY, days=0)[0].day == TODAY


def test_privacy_no_person_row_is_read(tmp_path):
    _, src = _src(tmp_path)
    rows = FLIPS + [
        {"week": "2026-W38", "date": "2026-09-09", "kind": "person", "name": "Alice"},
        {"week": "2026-W38", "date": "2026-09-09", "kind": "watch", "name": "Alice"},
    ]
    got = tape.project_tape(replace(src, rows=rows), "apollo", date(2026, 9, 10))
    assert "Alice" not in repr(got)


def test_blocks(tmp_path):
    _, src = _src(tmp_path)
    got = tape.blocks(tape.project_tape(src, "apollo", TODAY))
    assert got[0]["title"] == "Tape · last 56 days, from files only"
    assert got[0]["columns"] == ["date", "project", "kind", "text"]
    assert got[0]["rows"][0] == ["04-20", "apollo", "board", "board fetched, 7 open"]
    empty = tape.blocks([], days=7)
    assert len(empty) == 1 and empty[0]["block"] == "text"
    assert "last 7 days" in empty[0]["text"]
    assert json.dumps(got)
