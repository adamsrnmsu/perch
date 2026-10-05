from datetime import date

import pytest

from perch.core import asof


def team(week, headroom=0):
    return {"week": week, "kind": "team", "name": "team", "headroom": headroom}


APOLLO = [team("2026-W36"), team("2026-W37"), team("2026-W38")]
BETA = [team("2026-W36"), team("2026-W37"), {"week": "2026-W38", "kind": "person"}]
REC = ["2026-W36", "2026-W37", "2026-W38"]


def test_weeks_is_the_union_of_team_weeks():
    assert asof.weeks([APOLLO, BETA]) == REC
    assert asof.weeks([BETA]) == REC[:2]
    assert asof.weeks([]) == []


def test_step():
    assert asof.step(REC, None, -1) == "2026-W37"
    assert asof.step(REC, "2026-W37", -1) == "2026-W36"
    assert asof.step(REC, "2026-W36", -1) == "2026-W36"
    assert asof.step(REC, "2026-W36", +1) == "2026-W37"
    assert asof.step(REC, "2026-W37", +1) is None
    assert asof.step(REC, None, +1) is None
    assert asof.step(REC, "2026-W38", -1) == "2026-W37"  # latest week is live
    assert asof.step(["2026-W38"], None, -1) is None
    assert asof.step([], None, -1) is None


def test_resolve():
    assert asof.resolve("live", REC) is None
    assert asof.resolve("NOW", REC) is None
    assert asof.resolve("w37", REC) == "2026-W37"
    assert asof.resolve("2026-W36", REC) == "2026-W36"
    assert asof.resolve("W5", ["2025-W05", "2026-W05"]) == "2026-W05"
    with pytest.raises(ValueError, match=r"no week W50 recorded: W36…W38"):
        asof.resolve("W50", REC)
    with pytest.raises(ValueError, match="no week W36 recorded"):
        asof.resolve("2025-W36", REC)
    with pytest.raises(ValueError, match="not a week"):
        asof.resolve("soon", REC)


def test_until_and_team_as_of():
    assert [r["week"] for r in asof.until(APOLLO, "2026-W37")] == REC[:2]
    assert asof.team_as_of(APOLLO, "2026-W37") == APOLLO[1]
    assert asof.team_as_of(BETA, "2026-W38") is None  # no nearest week


def test_week_end_is_the_sunday():
    assert asof.week_end("2026-W37") == date(2026, 9, 13)


def test_command_and_argument():
    for text, arg in [
        ("ASOF W38", "W38"),
        ("as of W38", "W38"),
        ("AS OF 2026-W38", "2026-W38"),
        ("asof live", "live"),
    ]:
        assert asof.is_command(text)
        assert asof.argument(text) == arg
    assert not asof.is_command("apollo CUT 700k")
    assert not asof.is_command("")
    assert not asof.is_command("AS")
