from datetime import date

import pytest

from perch.core import alerts
from perch.core.alerts import evaluate, parse


def one(when, project=None, projects=("apollo",)):
    item = {"when": when} | ({"project": project} if project else {})
    return parse([item], projects)[0]


def team(week, **figs):
    return {"kind": "team", "name": "team", "week": week, **figs}


TODAY = date(2026, 10, 1)  # ISO 2026-W40


@pytest.mark.parametrize(
    ("when", "value"),
    [
        ("headroom < 50k", 50000),
        ("pace < 80%", 0.8),
        ("headroom < -5k", -5000),
        ("budget >= $1,200,000", 1200000),
        ("prob_over > 0.3", 0.3),
        ("clear_p50 != 2m", 2000000),
    ],
)
def test_numbers(when, value):
    assert one(when).value == pytest.approx(value)


@pytest.mark.parametrize(
    ("data", "key"),
    [
        ([{"when": "pace < 80"}], r"alerts\[0\]\.when"),
        ([{"when": "bogus < 1"}], r"alerts\[0\]\.when"),
        ([{"when": "headroom < x"}], r"alerts\[0\]\.when"),
        ([{"when": "headroom < 1", "project": "zed"}], r"alerts\[0\]\.project"),
        ([{"when": "headroom < 1", "nope": 1}], "unknown keys"),
        ({"when": "x"}, "`alerts`"),
    ],
)
def test_errors_name_the_key(data, key):
    with pytest.raises(ValueError, match=key):
        parse(data, ["apollo"])


def test_fresh_when_it_crossed_this_week():
    rows = [team("2026-W39", headroom=60000), team("2026-W40", headroom=42000)]
    (s,) = evaluate([one("headroom < 50k")], "apollo", rows, TODAY)
    assert (s.true, s.fresh, s.figure, s.week) == (True, True, 42000, "2026-W40")
    assert alerts.toast_text(s) == "apollo: headroom < 50k (headroom $42,000, W40)"


def test_not_fresh_when_already_true_one_row_or_stale():
    r = one("headroom < 50k")
    three = [
        team("2026-W38", headroom=60000),
        team("2026-W39", headroom=42000),
        team("2026-W40", headroom=41000),
    ]
    (s,) = evaluate([r], "apollo", three, TODAY)
    assert (s.true, s.fresh) == (True, False)
    (s,) = evaluate([r], "apollo", [team("2026-W40", headroom=42000)], TODAY)
    assert (s.true, s.fresh) == (True, False)
    old = [team("2026-W30", headroom=60000), team("2026-W31", headroom=42000)]
    assert not evaluate([r], "apollo", old, TODAY)[0].fresh
    assert evaluate([r], "apollo", old, None)[0].fresh  # today=None skips recency


def test_missing_figure_is_no_data_and_project_scope():
    rows = [team("2026-W39", headroom=1), team("2026-W40", headroom=1)]
    (s,) = evaluate([one("pace < 80%")], "apollo", rows, TODAY)
    assert s.true is None and not s.fresh
    assert "no data" in alerts.lines([s])[0]
    assert evaluate([one("headroom < 5", "apollo")], "beta", rows) == []
    assert evaluate([one("headroom < 5")], "beta", [])[0].week is None


def test_blocks_are_a_valid_table():
    rows = [team("2026-W40", pace=0.75)]
    (s,) = evaluate([one("pace < 80%")], "apollo", rows, TODAY)
    (b,) = alerts.blocks([s])
    assert b["block"] == "table" and b["rows"][0][2:4] == ["true", "75%"]
