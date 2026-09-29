import json

from click.testing import CliRunner

from perch.cli import cli
from perch.core.history import record
from perch.tests.conftest import week

BLOCK = "## Alice"


def run(world, *args):
    return CliRunner().invoke(cli, ["weekly", *args, "--config", str(world)])


def seed_history(world, weeks, ratio=1.5):
    """`weeks` prior weeks before the fixture's 2026-W17: Alice's pace factor 1.0,
    the team's `untyped` rate 20 h/issue, her estimate ratio 1.5."""
    for n in range(17 - weeks, 17):
        record(
            world.parent / "history.jsonl",
            week(n),
            [
                {"kind": "person", "name": "Alice", "factor": 1.0},
                {"kind": "type", "name": "untyped", "rate": 20.0},
                {"kind": "accuracy", "name": "Alice", "ratio": ratio},
            ],
        )


def cover_alice(world):
    """Estimates on all eight issues Alice closed (15 h each): 200 h booked
    over 120 h estimated is 1.67x."""
    rows = "".join(f"#{n},15,,\n" for n in range(1, 9))
    world.parent.joinpath("estimates.csv").write_text(
        "key,hours,low,high\n#101,10,8,14\n" + rows
    )


def test_full_history_compares_with_her_own_trailing_weeks(world):
    seed_history(world, 8)
    cover_alice(world)
    out = run(world, "--person", "Alice").output
    assert BLOCK in out and "## Bob" not in out
    assert "3 issue(s), about 60 h. Planned hours left: 796. Gap: 736 h." in out
    assert "untyped:" in out and "20 h (8 weeks)" in out
    assert "1.67x now, above your 1.50x over 8 weeks" in out
    assert "not enough history" not in out
    assert "modelled" in out


def test_thin_history_says_so_instead_of_a_trend(world):
    seed_history(world, 2)
    cover_alice(world)
    out = run(world, "--person", "Alice").output
    assert out.count("not enough history: 2 of 8 weeks") == 2  # type row + accuracy
    assert "1.67x now;" in out and "above" not in out and "over 2 weeks" not in out
    assert "20 h (" not in out


def test_no_history_file_and_no_estimates_still_render(world):
    world.write_text(
        "budgie_project: fy26\nboard_dump: dump.json\npeople:\n  bjones: Bob\n"
    )
    out = run(world).output
    assert "not enough history to fit type rates" in out
    assert "no `estimates:` file" in out
    assert "#104 Issue 104: 14 days" in out  # Bob's Blocked issue
    assert not (world.parent / "history.jsonl").exists()  # weekly never writes


def test_low_coverage_is_withheld_not_trended(world):
    seed_history(world, 8)
    out = run(world, "--person", "Alice").output  # fixture covers 2 of 8
    assert "withheld: 2 of 8 closed issues" in out


def test_current_week_is_not_its_own_baseline(world):
    seed_history(world, 8)
    run_board = CliRunner().invoke(cli, ["board", "--config", str(world)])
    assert run_board.exit_code == 0
    rows = [
        json.loads(x) for x in (world.parent / "history.jsonl").read_text().splitlines()
    ]
    assert "2026-W17" in {r["week"] for r in rows}
    assert "(8 weeks)" in run(world, "--person", "Alice").output


def test_out_writes_a_file_and_unknown_person_is_a_clean_error(world, tmp_path):
    target = tmp_path / "w.md"
    assert run(world, "--out", str(target)).exit_code == 0
    assert "## Alice" in target.read_text() and "## Bob" in target.read_text()
    bad = run(world, "--person", "Zed")
    assert bad.exit_code != 0 and "Traceback" not in bad.output
