"""perch cut against the conftest world: Alice 796 h left, Bob 876 h, board 157 h.

Board hours: Alice 60 (10 + 25 + 25), Bob 48 (24 + 24), #106 and #107 at the
team rate 320/13 = 24.6 each. Budget 100,000 less 26,000 spent and 5,000
non-labor leaves 69,000 for a board that costs ~12,700 (P10 ~11,600).
"""

import json
from datetime import date

import pytest
from budgie.core.plan import PlanEntry

from perch.core.cut import compare, parse_change
from perch.core.money import load_snapshot, money_from, what_if

NAMES = {"Alice", "Bob"}


def _load(world):
    from perch.cli import _load

    config, board, _, estimates, rates = _load(world)
    return config, board, estimates, rates, load_snapshot(config.budgie_project)


def test_bob_leaving_on_july_1(world):
    config, board, estimates, rates, snap = _load(world)
    leaves = parse_change("Bob:2026-07-01", NAMES, 2026, leaves=True)
    assert leaves == PlanEntry("Bob", date(2026, 7, 1), 0.0)
    cut = compare(
        money_from(snap),
        money_from(what_if(snap, changes=[leaves])),
        board,
        estimates,
        rates,
        config.people,
        changes=[leaves],
    )
    # 0.5 x 124 working days x 7.968 h = 494.016 h for Jan-Jun (test_money).
    bob = next(p for p in cut.people if p.name == "Bob")
    assert bob.left_before == 876
    assert bob.left_after == pytest.approx(494.016 - 120)
    assert bob.leaves == date(2026, 7, 1)
    assert bob.issues == (104, 105)
    assert (bob.row.open, bob.row.mode) == (2, 48)
    alice = next(p for p in cut.people if p.name == "Alice")
    assert (alice.left_before, alice.left_after, alice.leaves) == (796, 796, None)
    assert [p.name for p in cut.people] == ["Alice", "Bob", "unassigned", "unmapped"]

    assert cut.before.left == 796 + 876
    assert cut.after.left == pytest.approx(796 + 494.016 - 120)
    assert cut.board_hours == pytest.approx(60 + 48 + 2 * 320 / 13)
    assert cut.spare == pytest.approx(cut.after.left - cut.board_hours)
    assert cut.before.budget == cut.after.budget == 100000


def test_a_budget_cut_flips_the_stoplight(world):
    """40,000 less 31,000 committed leaves 9,000: under even the P10 cost."""
    config, board, estimates, rates, snap = _load(world)
    cut = compare(
        money_from(snap),
        money_from(what_if(snap, budget=40000)),
        board,
        estimates,
        rates,
        config.people,
    )
    assert (cut.before.signal, cut.after.signal) == ("good", "bad")
    assert cut.after.budget == 40000
    assert cut.before.clear_p50 == cut.after.clear_p50  # the board is unchanged
    assert cut.before.headroom == pytest.approx(69000 - cut.before.clear_p50)
    assert cut.after.headroom == pytest.approx(9000 - cut.after.clear_p50)


def test_after_the_fact_reads_the_history_week(world):
    config, board, estimates, rates, snap = _load(world)
    week = [
        {"kind": "person", "name": "Bob", "left": 900},
        {"kind": "person", "name": "unassigned", "left": None},
        {
            "kind": "team",
            "week": "2026-W16",
            "budget": 120000,
            "left": 1700,
            "clear_p50": 12000,
            "headroom": 50000,
            "signal": "good",
        },
    ]
    cut = compare(week, money_from(snap), board, estimates, rates, config.people)
    assert (cut.before.budget, cut.before.left, cut.before.headroom) == (
        120000,
        1700,
        50000,
    )
    assert not cut.before.old_row
    assert cut.after.budget == 100000
    bob = next(p for p in cut.people if p.name == "Bob")
    assert (bob.left_before, bob.left_after) == (900, 876)
    alice = next(p for p in cut.people if p.name == "Alice")
    assert alice.left_before is None  # no row for her that week


def test_an_old_history_row_has_no_budget(world):
    config, board, estimates, rates, snap = _load(world)
    old = [{"kind": "team", "clear_p50": 12000, "headroom": 50000}]
    cut = compare(old, money_from(snap), board, estimates, rates, config.people)
    assert cut.before.old_row
    assert (cut.before.budget, cut.before.left, cut.before.signal) == (None,) * 3


def test_milestones_with_their_open_hours(world):
    """#101 (estimate 10, 8-14) and Bob's #104 (24) are M1: 34 h (32-38)."""
    dump = world.parent / "dump.json"
    meta = json.loads(dump.read_text())
    for record in meta["history"]:
        if record["iid"] in (101, 104):
            record |= {"milestone": "M1", "milestone_due": "2026-06-30"}
        if record["iid"] == 106:
            record["milestone"] = "M2"
    dump.write_text(json.dumps(meta))
    config, board, estimates, rates, snap = _load(world)
    money = money_from(snap)
    cut = compare(money, money, board, estimates, rates, config.people)
    m1, m2, rest = cut.milestones
    assert (m1.name, m1.due, m1.open) == ("M1", date(2026, 6, 30), 2)
    assert (m1.low, m1.mode, m1.high) == (32, 34, 38)
    assert (m2.name, m2.due, m2.open) == ("M2", None, 1)
    assert m2.mode == pytest.approx(320 / 13)
    assert (rest.name, rest.open) == (None, 4)


@pytest.mark.parametrize(
    ("flag", "leaves", "error"),
    [
        ("Carol:2026-07-01", True, "not in the Budgie project's people"),
        ("Bob:2027-01-01", True, "outside 2026"),
        ("Bob:2026-13-01", True, "not a YYYY-MM-DD date"),
        ("Bob:2026-07-01:0.5", True, "NAME:YYYY-MM-DD$"),
        ("Alice:2026-07-01:1.5", False, "FTE must be between 0 and 1"),
        ("Alice:2026-07-01:half", False, "FTE must be between 0 and 1"),
    ],
)
def test_flags_are_checked_and_the_error_names_the_flag(flag, leaves, error):
    option = "--leaves" if leaves else "--fte"
    with pytest.raises(ValueError, match=error) as caught:
        parse_change(flag, NAMES, 2026, leaves=leaves)
    assert str(caught.value).startswith(f"{option} {flag}: ")


def test_fte_flag(world):
    assert parse_change("Alice:2026-11-01:0.5", NAMES, 2026) == PlanEntry(
        "Alice", date(2026, 11, 1), 0.5
    )
