import json

from click.testing import CliRunner

from perch.cli import cli


def run(world, *args):
    return CliRunner().invoke(cli, [*args, "--config", str(world)])


def test_board_prints_the_join_and_records_the_week(world):
    result = run(world, "board")
    assert result.exit_code == 0, result.output
    for expected in ("Alice", "$6,000", "796", "736", "$26,000", "$100,000", "GOOD"):
        assert expected in result.output
    assert "cdoe" in result.output  # the unmapped username is named
    assert "Not a year forecast" in result.output
    assert "Modelled, not measured" in result.output

    rows = [
        json.loads(line)
        for line in (world.parent / "history.jsonl").read_text().splitlines()
    ]
    assert {r["week"] for r in rows} == {"2026-W17"}
    assert {r["kind"] for r in rows} == {"person", "type", "accuracy", "team"}
    alice = next(r for r in rows if r["kind"] == "person" and r["name"] == "Alice")
    assert (alice["open"], round(alice["hours"]), round(alice["rate"])) == (3, 60, 25)


def test_no_history_leaves_the_file_alone(world):
    assert run(world, "board", "--no-history").exit_code == 0
    assert not (world.parent / "history.jsonl").exists()


def test_accuracy_says_modelled_and_refuses_thin_coverage(world):
    result = run(world, "accuracy")
    assert result.exit_code == 0, result.output
    assert "MODELLED" in result.output and "epic::billing" in result.output
    assert "2.08x" in result.output
    assert "too few estimates" in result.output


def test_accuracy_without_estimates_explains_itself(world):
    world.write_text("budgie_project: fy26\nboard_dump: dump.json\n")
    result = run(world, "accuracy")
    assert result.exit_code != 0 and "nothing to compare" in result.output


def test_a_bad_config_is_a_clean_error_not_a_traceback(world):
    world.write_text("budgie_project: nope\nboard_dump: dump.json\n")
    result = run(world, "board")
    assert result.exit_code != 0 and "budgie.yaml" in result.output
    assert "Traceback" not in result.output


def test_board_on_a_malformed_dump_is_a_clean_error(world):
    dump = world.parent / "dump.json"
    meta = json.loads(dump.read_text())
    meta["history"][0]["closed_at"] = 5
    dump.write_text(json.dumps(meta))
    result = run(world, "board")
    assert result.exit_code == 1
    assert "stats --dump" in result.output and "Traceback" not in result.output
    assert isinstance(result.exception, SystemExit)
