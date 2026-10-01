"""`perch cut` end to end; the numbers are worked in test_cut.py's docstring."""

import json

from click.testing import CliRunner

from perch.cli import cli


def run(world, *args):
    return CliRunner().invoke(cli, ["cut", *args, "--config", str(world)])


def test_bob_leaving_shows_the_hours_and_his_issues(world):
    result = run(world, "--leaves", "Bob:2026-07-01")
    assert result.exit_code == 0, result.output
    out = result.output
    assert "1,672 → 1,170" in out  # 796 + 876, less 0.5 x 126 days x 7.968 h
    assert "876 → 374" in out
    assert "leaves 2026-07-01: 2 open issues (48 h) need a new owner: #104, #105" in out
    assert "still fits with 1,013 h spare" in out  # 1,170 - 157
    assert out.index("Alice") < out.index("Bob")  # name order, never ranked


def test_a_budget_cut_flips_good_to_bad(world):
    result = run(world, "--budget", "40000")
    assert result.exit_code == 0, result.output
    assert "$100,000 → $40,000" in result.output
    assert "GOOD → BAD" in result.output


def test_a_what_if_writes_nothing(world):
    budgie = sorted((world.parent / "fy26").iterdir())
    before = {p: p.read_bytes() for p in budgie}
    result = run(world, "--leaves", "Bob:2026-07-01", "--budget", "40000")
    assert result.exit_code == 0, result.output
    assert not (world.parent / "history.jsonl").exists()
    assert sorted((world.parent / "fy26").iterdir()) == budgie
    assert {p: p.read_bytes() for p in budgie} == before


def test_after_the_fact_against_the_recorded_week(world):
    assert CliRunner().invoke(cli, ["board", "--config", str(world)]).exit_code == 0
    yaml = world.parent / "fy26" / "budgie.yaml"
    yaml.write_text(yaml.read_text().replace("100000", "40000"))
    result = run(world)
    assert result.exit_code == 0, result.output
    assert "Since 2026-W17" in result.output
    assert "$100,000 → $40,000" in result.output
    assert "GOOD → BAD" in result.output


def test_an_old_history_row_shows_a_dash_and_says_why(world):
    old = {"week": "2026-W16", "kind": "team", "name": "team", "headroom": 50000}
    (world.parent / "history.jsonl").write_text(json.dumps(old) + "\n")
    result = run(world)
    assert result.exit_code == 0, result.output
    assert "— → $100,000" in result.output
    assert "a fresh `perch board` will record them" in result.output


def test_no_history_and_no_flags_is_refused(world):
    result = run(world)
    assert result.exit_code == 1
    assert "perch board" in result.output


def test_bad_flags_are_named(world):
    unknown = run(world, "--leaves", "Carol:2026-07-01")
    assert unknown.exit_code == 1
    assert "--leaves Carol:2026-07-01" in unknown.output
    assert (
        "--fte Bob:2026-07-01:1.5" in run(world, "--fte", "Bob:2026-07-01:1.5").output
    )
    zero = run(world, "--budget", "0")
    assert zero.exit_code == 2
    assert "--budget" in zero.output
