"""The detail pane's data: from Sources and Budgie's burn series."""

import json
from datetime import date

from perch.core import blocks as bk
from perch.core import detail, sources
from perch.tests.conftest import build_home
from perch.tests.test_watch import BANNED


def _build(tmp_path, rows=()):
    home = build_home(tmp_path, "apollo")
    path = home.projects_dir / "apollo" / "history.jsonl"
    if rows:
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return home, detail.build("apollo", sources.load(home, "apollo"))


def _team(week, headroom, **more):
    return {
        "week": week,
        "date": "2026-09-01",
        "kind": "team",
        "name": "team",
        "headroom": headroom,
        "signal": "green",
        **more,
    }


def test_money_carries_budgies_burn_series(tmp_path):
    home = build_home(tmp_path, "apollo")
    burn = sources.load(home, "apollo").money.burn()
    assert burn.spent_as_of == (date(2026, 4, 19), 26000.0)


def test_build_from_the_world(tmp_path):
    _, d = _build(tmp_path)
    assert d.project == "apollo" and d.headroom == {}
    assert (d.as_of, d.dump_on, d.history_week) == (
        date(2026, 4, 19),
        date(2026, 4, 20),
        None,
    )
    assert d.non_labor == 5000.0 and d.note == ""
    assert d.burn.budget == (95000.0,) * 12


def test_the_spark_line_needs_two_weeks(tmp_path):
    _, none = _build(tmp_path)
    assert detail.spark_line(none) == "no weeks recorded yet"
    _, one = _build(tmp_path / "a", [_team("2026-W36", 5000)])
    assert detail.spark_line(one) == "1 week recorded, need 2 for a trend"
    _, two = _build(tmp_path / "b", [_team("2026-W36", 5000), _team("2026-W37", 2000)])
    assert detail.spark_line(two) == "headroom █▁  $2,000–$5,000  2 weeks"
    assert (
        detail.spark_line(two, upto="2026-W36") == "1 week recorded, need 2 for a trend"
    )


def test_pace_and_scope_come_from_the_latest_team_row(tmp_path):  # review-focus 4
    _, d = _build(
        tmp_path,
        [_team("2026-W36", 5000), _team("2026-W37", 2000, pace=0.85, net_scope=-3)],
    )
    assert d.pace == 0.85 and d.net_scope == -3 and d.history_week == "2026-W37"
    assert "pace 85% · net scope -3" in detail.lines(d)
    _, old = _build(
        tmp_path / "old", [_team("2026-W36", 5000)]
    )  # a row from before pace
    assert "pace — · net scope —" in detail.lines(old)


def test_no_readings_gives_a_note(tmp_path):  # review-focus 1
    home = build_home(tmp_path, "apollo")
    (home.projects_dir / "apollo" / "fy26" / "weekly.csv").unlink()
    d = detail.build("apollo", sources.load(home, "apollo"))
    assert d.as_of is None and "no hours readings yet" in d.note
    assert detail.lines(d)[-1] == d.note


def test_a_failing_fan_and_unreadable_sources_become_fixed_notes(tmp_path):
    home = build_home(tmp_path, "apollo")
    src = sources.load(home, "apollo")

    def boom():
        raise ValueError("Alice")

    from dataclasses import replace

    bad = replace(src, money=replace(src.money, burn=boom), errors=("monday.json",))
    d = detail.build("apollo", bad)
    assert d.burn is None
    assert (
        d.note
        == "monday.json unreadable, run perch doctor; fan unavailable, run perch doctor"
    )
    assert "Alice" not in d.note


def test_blocks_are_valid_and_the_table_is_labor_only(tmp_path):
    _, d = _build(tmp_path)
    out = detail.blocks(d)
    assert all(bk.parse(json.dumps(b)) for b in out)
    md = bk.to_md(out)
    assert "Detail · apollo" in md and "Labor only · cost lines excluded" in md
    assert "2026-12" in md and "$149,400" in md


def test_no_ranking_word_and_no_name(tmp_path):
    _, d = _build(tmp_path, [_team("2026-W36", 5000), _team("2026-W37", 2000)])
    text = ("\n".join(detail.lines(d)) + bk.to_md(detail.blocks(d))).lower()
    assert "alice" not in text and "bob" not in text
    assert not [w for w in BANNED if w in text]
