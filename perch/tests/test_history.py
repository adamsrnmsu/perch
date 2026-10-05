import json
from datetime import date

from perch.core.history import latest_week, record, rows_for, week_key


def test_rerunning_in_the_same_week_replaces_that_week(tmp_path):
    path = tmp_path / "history.jsonl"
    record(path, date(2026, 4, 13), [{"kind": "team", "name": "team", "headroom": 1}])
    record(path, date(2026, 4, 20), [{"kind": "team", "name": "team", "headroom": 2}])
    record(path, date(2026, 4, 22), [{"kind": "team", "name": "team", "headroom": 3}])

    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [(r["week"], r["headroom"]) for r in rows] == [
        ("2026-W16", 1),
        ("2026-W17", 3),
    ]
    assert rows[1]["date"] == "2026-04-22"


def test_week_key_is_the_iso_week():
    assert week_key(date(2026, 1, 1)) == "2026-W01"
    assert week_key(date(2027, 1, 1)) == "2026-W53"  # belongs to ISO 2026


def test_latest_week_is_the_last_recorded_week(tmp_path):
    path = tmp_path / "history.jsonl"
    assert latest_week(path) == []  # no file: nothing recorded yet
    record(path, date(2026, 4, 20), [{"kind": "team", "name": "team", "left": 2}])
    record(path, date(2026, 4, 13), [{"kind": "team", "name": "team", "left": 1}])
    assert [(r["week"], r["left"]) for r in latest_week(path)] == [("2026-W17", 2)]


def test_the_team_row_records_budget_left_and_signal(world):
    from perch.cli import _load
    from perch.core.join import person_rows, rollup

    config, board, money, estimates, rates = _load(world)
    rows = person_rows(board, estimates, rates, config.people, money)
    out = rows_for(rows, rates, rollup(rows, money), left=sum(money.left.values()))
    team = out[-1]
    assert team["budget"] == 100000
    assert team["left"] == (996 - 200) + (996 - 120)
    assert team["signal"] == "good"


def test_the_team_row_records_the_quarters_pace_and_scope(world):
    from perch.cli import _load
    from perch.core.join import person_rows, rollup

    config, board, money, estimates, rates = _load(world)
    rows = person_rows(board, estimates, rates, config.people, money)
    summary = rollup(rows, money)
    team = rows_for(rows, rates, summary, quarter={"pace": 0.4, "net_scope": 2})[-1]
    assert (team["pace"], team["net_scope"]) == (0.4, 2)
    team = rows_for(rows, rates, summary)[-1]
    assert (team["pace"], team["net_scope"]) == (None, None)
