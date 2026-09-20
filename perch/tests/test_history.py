import json
from datetime import date

from perch.core.history import record, week_key


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
