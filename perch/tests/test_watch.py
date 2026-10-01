"""perch watch, against the conftest world (board fetched 2026-04-20, W17).

Hours vs plan, with no plan.csv: Budgie's even burn plans 996 x 28/365 = 76.4 h
in any four weeks, so out of line is under 70% of that, 53.5 h. Alice's last
reading is 04-19 (200 h); four-week windows ending 04-19, 04-12, 04-05, 03-29
book 40, 45, 50, 55 h (interpolated between 160 at 03-22 and 200), so 3 of 4
are out of line. Bob books 40 h in 8 weeks, 20 h in any four: 4 of 4.
"""

from dataclasses import replace
from datetime import date

import pytest

from perch.core.board import BLOCKED, Board, Issue, load_board
from perch.core.estimates import Estimate
from perch.core.history import week_key
from perch.core.join import calibrate
from perch.core.money import Money, load_money
from perch.core.watch import render, summary, watch
from perch.tests.conftest import week

PEOPLE = {"asmith": "Alice", "bjones": "Bob"}


def history(first, last=16, ratio=lambda n: None):
    """Weeks `first`..`last` before W17, each with a team row and, when
    `ratio(n)` gives one, Alice's estimate ratio that week."""
    rows = []
    for n in range(first, last + 1):
        rows.append({"week": week_key(week(n)), "kind": "team", "name": "team"})
        if ratio(n) is not None:
            rows.append(
                {
                    "week": week_key(week(n)),
                    "kind": "accuracy",
                    "name": "Alice",
                    "ratio": ratio(n),
                }
            )
    return rows


def run(board, money, rows=(), estimates=None):
    rates = calibrate(money.readings, board, PEOPLE, money.year)
    return watch(board, money, rates, estimates or {}, PEOPLE, list(rows))


def world_watch(world, rows=(), estimates=None):
    board = load_board(world.parent / "dump.json")
    return run(board, load_money(world.parent / "fy26"), rows, estimates)


def signal(result, person, name):
    found = next(p for p in result.people if p.name == person)
    return next(s for s in found.signals if s.name == name)


# -- hours vs plan --------------------------------------------------------------


def test_hours_under_plan_3_of_4_weeks_flags(world):
    result = world_watch(world, history(13))
    alice = signal(result, "Alice", "hours vs plan")
    assert alice.flagged
    assert alice.text.startswith(
        "booked 40 h vs 76 h planned over the 4 weeks to 2026-04-19 (1 reading(s));"
    )
    assert "out of line 3 of the last 4 weeks" in alice.text
    bob = signal(result, "Bob", "hours vs plan")
    assert bob.flagged and "booked 20 h vs 76 h" in bob.text
    assert "out of line 4 of the last 4 weeks" in bob.text


def test_hours_under_plan_2_of_4_weeks_does_not_flag(world):
    # 210 at wk16: windows book 50, 52.5, 55, 57.5 h -- two under 53.5
    weekly = world.parent / "fy26" / "weekly.csv"
    weekly.write_text(weekly.read_text().replace("Alice,16,200", "Alice,16,210"))
    alice = signal(world_watch(world, history(13)), "Alice", "hours vs plan")
    assert not alice.flagged and "out of line 2 of the last 4 weeks" in alice.text


def test_zero_fte_in_the_plan_never_flags(world):
    (world.parent / "fy26" / "plan.csv").write_text(
        "name,effective_date,fte\nAlice,2026-01-01,0.5\nAlice,2026-03-01,0\n"
        "Bob,2026-01-01,0.5\n"
    )
    alice = signal(world_watch(world, history(13)), "Alice", "hours vs plan")
    assert not alice.flagged and "0 h planned" in alice.text
    assert "out of line 0 of the last 4 weeks" in alice.text


def test_thin_history_reads_not_enough_history(world):
    result = world_watch(world, history(14))  # W14-W16: 3 weeks
    for name in ("hours vs plan", "hours per issue", "estimates"):
        found = signal(result, "Alice", name)
        assert not found.flagged and found.text == "not enough history: 3 of 8 weeks"
    assert signal(result, "Alice", "work in Doing").text.startswith("nothing")


# -- hours per issue -----------------------------------------------------------


def per_issue(heavy_from):
    """Alice closes 2 issues every Friday of weeks 1-16 and books 20 h a week,
    40 h a week from `heavy_from` on.

    heavy_from=12: the 4 weeks to wk16, 15, 14, 13 run 20, 20, 17.5, 15 h per
    issue against the 8 weeks before at 11.25, 10, 10, 10 -- out of line when
    over 1.5x, so 3 of 4. heavy_from=13: 20, 17.5, 15, 12.5 vs 10: 2 of 4.
    """
    hours, readings, issues = 0.0, [], []
    for n in range(1, 17):
        hours += 40 if n >= heavy_from else 20
        readings.append((week(n), hours))
        friday = date.fromisocalendar(2026, n, 5)
        issues += [Issue(100 + 2 * n + k, "t", "asmith", (), friday) for k in (0, 1)]
    board = Board("grp/proj", "Dev", date(2026, 4, 20), tuple(issues))
    money = Money(year=2026, hourly_cost={"Alice": 100}, readings={"Alice": readings})
    return run(board, money, history(9))


def test_hours_per_issue_over_own_baseline_3_of_4_weeks_flags():
    alice = signal(per_issue(12), "Alice", "hours per issue")
    assert alice.flagged
    assert alice.text.startswith(
        "20 h over the last 4 weeks vs own 11 h over the 8 before "
        "(8 and 16 issues, 12 reading(s))"
    )
    assert "out of line 3 of the last 4 weeks" in alice.text


def test_hours_per_issue_2_of_4_weeks_does_not_flag():
    alice = signal(per_issue(13), "Alice", "hours per issue")
    assert not alice.flagged and "out of line 2 of the last 4 weeks" in alice.text


def test_too_few_issues_says_so(world):
    alice = signal(world_watch(world, history(9)), "Alice", "hours per issue")
    assert not alice.flagged
    assert alice.text == (
        "too few issues: 1 closed in the last 4 weeks, 5 in the 8 before "
        "(needs 5 in each)"
    )


# -- work in Doing -------------------------------------------------------------


MARCH = date(2026, 3, 2)
ASKED = ("Q: which env?",)


def test_doing_unmoved_10_working_days_flags_and_blocked_never_counts(world):
    board = load_board(world.parent / "dump.json")
    doing = ("Doing",)
    board = replace(
        board,
        columns=("Doing", BLOCKED, "Done", "Failed"),
        issues=board.issues
        + (
            # 04-07..04-20 is 10 working days; 04-08..04-20 is 9
            Issue(108, "t", "asmith", doing, None, last_moved=date(2026, 4, 6)),
            Issue(109, "t", "asmith", doing, None, last_moved=date(2026, 4, 7)),
            # Blocked is someone else's doing; no column label is Backlog
            Issue(110, "t", "bjones", ("Doing", BLOCKED), None, last_moved=MARCH),
            Issue(111, "t", "bjones", (), None, last_moved=MARCH),
            # waiting on an answer is someone else's doing too; Failed is not WIP
            Issue(112, "t", "bjones", doing, None, last_moved=MARCH, questions=ASKED),
            Issue(113, "t", "bjones", ("Failed",), None, last_moved=MARCH),
        ),
    )
    result = run(board, load_money(world.parent / "fy26"))  # no history needed
    alice = signal(result, "Alice", "work in Doing")
    assert alice.flagged and alice.text == "#108 in Doing for 10 working days"
    bob = signal(result, "Bob", "work in Doing")
    assert not bob.flagged
    assert bob.text == "nothing in a Doing column unmoved for 10 working days"


# -- estimates -----------------------------------------------------------------

COVERED = {f"#{n}": Estimate(f"#{n}", 15, 15, 15) for n in range(1, 9)}


def test_estimate_overrun_3_of_4_weeks_flags(world):
    """All 8 of Alice's issues estimated at 15 h: 200 / 120 = 1.67x now.
    Her ratio was 1.0 to W13, then 1.2, 1.5, 1.5: W14 is 1.2 against 1.0 (not
    over 1.3x), W15 1.5 against 1.025, W16 1.5 against 1.0875, now 1.67
    against 1.15."""
    rows = history(5, ratio=lambda n: {14: 1.2, 15: 1.5, 16: 1.5}.get(n, 1.0))
    alice = signal(world_watch(world, rows, COVERED), "Alice", "estimates")
    assert alice.flagged
    assert alice.text.startswith(
        "booked over estimate 1.67x now vs own 1.15x over the 8 weeks before "
        "(8 of 8 closed issues estimated"
    )
    assert "out of line 3 of the last 4 weeks" in alice.text


def test_estimate_overrun_2_of_4_weeks_does_not_flag(world):
    rows = history(5, ratio=lambda n: {14: 1.2, 15: 1.2, 16: 1.5}.get(n, 1.0))
    alice = signal(world_watch(world, rows, COVERED), "Alice", "estimates")
    assert not alice.flagged and "out of line 2 of the last 4 weeks" in alice.text


def test_under_half_coverage_gives_no_ratio_and_no_flag(world):
    covered = {k: COVERED[k] for k in ("#1", "#2")}  # 2 of her 8
    rows = history(5, ratio=lambda n: 0.5)
    alice = signal(world_watch(world, rows, covered), "Alice", "estimates")
    assert not alice.flagged
    assert alice.text == (
        "withheld: 2 of 8 closed issues had an estimate, under the 50% needed"
    )


# -- the page ------------------------------------------------------------------

BANNED = ("underperforming", "slow", "worst", "best")


@pytest.mark.parametrize("rows", [(), history(14), history(5)])
def test_no_ranking_words_in_any_output(world, rows):
    for result in (world_watch(world, rows, COVERED), per_issue(12), per_issue(13)):
        text = (render(result) + summary(result)).lower()
        assert not [word for word in BANNED if word in text]


def test_people_in_name_order_and_nothing_out_of_line_reads_so(world):
    page = render(world_watch(world, history(14)))
    assert page.index("## Alice") < page.index("## Bob")
    assert page.count("Nothing out of line.") == 2
    assert page.startswith("# Watch, grp/proj Dev, 2026-W17")
    flagged = world_watch(world, history(13))
    assert "- **Flag:** hours vs plan: booked 40 h" in render(flagged)
    assert summary(flagged) == "watch: 2 flags, run perch watch"
    assert summary(world_watch(world, history(14))) == "watch: nothing out of line"


# -- the commands --------------------------------------------------------------


def seed(path, rows):
    import json

    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_watch_command_prints_the_page_and_weekly_carries_none_of_it(world):
    from click.testing import CliRunner

    from perch.cli import cli

    seed(world.parent / "history.jsonl", history(13))
    page = CliRunner().invoke(cli, ["watch", "--config", str(world)])
    assert page.exit_code == 0, page.output
    assert "- **Flag:** hours vs plan: booked 40 h" in page.output
    draft = CliRunner().invoke(cli, ["weekly", "--config", str(world)]).output
    for phrase in ("Watch", "out of line", "hours vs plan", "Flag", "working days"):
        assert phrase not in draft


def test_watch_all_goes_through_every_project(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from perch.cli import cli
    from perch.tests.conftest import build_home

    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.root)
    result = CliRunner().invoke(cli, ["watch", "--all"])
    assert result.exit_code == 0, result.output
    assert result.output.count("# Watch, grp/proj Dev, 2026-W17") == 2
    assert CliRunner().invoke(cli, ["watch", "-p", "apollo", "--all"]).exit_code == 2


def test_watch_all_with_no_projects_says_init(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from perch.cli import cli
    from perch.tests.conftest import build_home

    monkeypatch.chdir(build_home(tmp_path).root)
    result = CliRunner().invoke(cli, ["watch", "--all"])
    assert result.exit_code != 0
    assert "no projects yet. Run: perch init <name>" in result.output
