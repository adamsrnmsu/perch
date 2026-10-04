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
    assert "hours still fit: 1,013 h spare" in out  # 1,170 - 157
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


def test_one_issue_reads_as_one_and_the_fit_line_is_about_hours(world):
    dump = world.parent / "dump.json"
    meta = json.loads(dump.read_text())
    for record in meta["history"]:
        if record["iid"] == 105:
            record["assignee"] = None
    dump.write_text(json.dumps(meta))
    out = run(world, "--leaves", "Bob:2026-07-01").output
    assert "Bob leaves 2026-07-01: 1 open issue (24 h) needs a new owner: #104" in out
    assert "hours still fit: " in out


def test_after_the_fact_says_left_includes_hours_spent_since(world):
    assert CliRunner().invoke(cli, ["board", "--config", str(world)]).exit_code == 0
    result = run(world)
    assert "also falls by the hours booked since 2026-W17" in result.output


def test_cut_as_blocks(world):
    from perch.core.blocks import parse

    result = CliRunner().invoke(
        cli,
        ["cut", "--leaves", "Bob:2026-07-01", "--config", str(world)],
        env={"PI_BLOCKS": "1"},
    )
    assert result.exit_code == 0, result.output
    out = [parse(line) for line in result.stdout.splitlines()]
    assert all(out), result.output
    assert [b["block"] for b in out[:2]] == ["heading", "figures"]
    values = {f["label"]: f["value"] for f in out[1]["items"]}
    assert values["Planned hours left"] == "1,672 → 1,170"
    assert values["Stoplight"] == "GOOD → GOOD"
    fits = next(b for b in out if b["block"] == "text" and "still fit" in b["text"])
    assert fits["tone"] == "good" and "1,013 h spare" in fits["text"]
    people = next(
        b for b in out if b["block"] == "table" and b["title"].startswith("People")
    )
    names = [r[0] for r in people["rows"]]
    assert names.index("Alice") < names.index("Bob")  # name order
    leave = next(b for b in out if b["block"] == "list")
    assert "Bob leaves 2026-07-01: 2 open issues" in leave["items"][0]
    assert any(
        b["block"] == "table" and b["title"].startswith("Milestones") for b in out
    )
