from perch.core.trend import Change, change, describe, series, spark, team_lines
from perch.tests.test_watch import BANNED


def team(week, **kw):
    return {"week": week, "kind": "team", "name": "team", **kw}


def test_spark_rising_flat_single_empty():
    assert spark([1, 2, 3, 4, 5, 6, 7, 8]) == "▁▂▃▄▅▆▇█"
    assert spark([5, 5, 5]) == "▄▄▄"
    low = spark([-10, 0, 10])  # negative headroom is just a low bar
    assert (low[0], low[-1]) == ("▁", "█")
    assert spark([3]) == ""
    assert spark([]) == ""


def test_series_windows_to_eight_and_skips_missing():
    rows = [team(f"2026-W{w:02d}", headroom=w) for w in range(10, 22)]
    rows.append(team("2026-W22"))
    rows.append({"week": "2026-W23", "kind": "person", "name": "Al", "headroom": 1})
    assert list(series(rows, "headroom")) == [f"2026-W{w:02d}" for w in range(14, 22)]
    assert series(rows, "headroom", 2) == {"2026-W20": 20, "2026-W21": 21}


def test_change_none_under_two_weeks():
    assert change([]) is None
    assert change([team("2026-W39", headroom=1)]) is None


def test_change_flip_only_when_both_set_and_different():
    a = team("2026-W39", signal="YELLOW")
    assert change([a, team("2026-W40", signal="RED")]).signal == ("YELLOW", "RED")
    assert change([a, team("2026-W40", signal="YELLOW")]).signal is None
    assert change([a, team("2026-W40", signal=None)]).signal is None
    assert change([team("2026-W39"), team("2026-W40", signal="RED")]).signal is None


def test_change_deltas_nonzero_and_both_present():
    rows = [
        team("2026-W38", headroom=0),
        team("2026-W39", headroom=1000, budget=100, spent_cost=5.0),
        team("2026-W41", headroom=-11000, budget=100, spent_cost=5.2),
    ]
    c = change(rows)
    assert (c.before, c.after) == ("2026-W39", "2026-W41")
    assert c.deltas == {"headroom": -12000}


def test_describe_exact_string():
    c = Change(
        "2026-W39",
        "2026-W40",
        ("YELLOW", "RED"),
        {"headroom": -12000.0, "budget": 50000.0},
    )
    assert (
        describe("apollo", c)
        == "apollo W39→W40: YELLOW→RED, headroom −$12,000, budget +$50,000"
    )
    c = Change("2026-W39", "2026-W40", None, {"spent_cost": 300.0})
    assert describe("apollo", c) == "apollo W39→W40: spent +$300"
    assert describe("apollo", Change("2026-W39", "2026-W40", None, {})) == ""
    assert describe("apollo", None) == ""


def test_team_lines_no_history():
    assert team_lines([]) == ["no week recorded yet: run perch board"]


def seeded():
    return [
        team("2026-W39", signal="YELLOW", headroom=5000.0),
        team(
            "2026-W40",
            signal="RED",
            prob_over=0.35,
            budget=200000.0,
            spent_cost=120000.0,
            headroom=-12000.0,
            left=340.0,
            clear_p10=180000.0,
            clear_p50=200000.0,
            clear_p90=None,
        ),
    ]


def test_team_lines_seeded():
    assert team_lines(seeded()) == [
        (
            "RED · over 35% · budget $200,000 · spent $120,000 · headroom −$12,000"
            " · left 340h · clear $180,000 / $200,000 / —"
        ),
        "2026-W39  $5,000  YELLOW",
        "2026-W40  −$12,000  RED",
    ]


def test_team_lines_missing_figures_are_dashes():
    assert team_lines([team("2026-W40")]) == [
        "— · over — · budget — · spent — · headroom — · left — · clear — / — / —",
    ]


def test_no_person_or_ranking_words_in_output():
    rows = seeded() + [
        {"week": "2026-W40", "kind": "person", "name": "Zelda Slowman", "headroom": 9},
        {"week": "2026-W40", "kind": "accuracy", "name": "Zelda Slowman", "ratio": 1},
    ]
    c = change(rows)
    text = "\n".join(team_lines(rows)) + describe("apollo", c) + repr(c)
    assert "zelda" not in text.lower()
    assert not [w for w in BANNED if w in text.lower()]
