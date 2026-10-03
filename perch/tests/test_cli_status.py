import json

from click.testing import CliRunner

from perch.cli import cli
from perch.core.status import failure_path
from perch.core.steps import StepFailed
from perch.tests.conftest import build_home


def run(*args):
    return CliRunner().invoke(cli, list(args))


def recorder(monkeypatch, fail=lambda step: False):
    ran = []

    def fake(step):
        ran.append(step)
        if fail(step):
            raise StepFailed(step, 3)

    monkeypatch.setattr("perch.cli._run", fake)
    return ran


def test_monday_from_runs_that_step_onward_and_writes_the_watch(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    ran = recorder(monkeypatch)
    result = run("monday", "-p", "apollo", "--from", "board")
    assert result.exit_code == 0, result.output
    assert [s.name for s in ran] == ["board", "weekly", "digest", "emails"]
    assert "watch:" in result.output


def test_from_with_all_is_a_usage_error(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    assert run("monday", "--all", "--from", "board").exit_code == 2


def test_a_failing_step_is_recorded_and_a_passing_run_clears_it(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    recorder(monkeypatch, fail=lambda s: s.name == "weekly")
    assert run("monday", "-p", "apollo").exit_code == 1
    rec = json.loads(failure_path(home, "apollo").read_text())
    assert (rec["step"], rec["code"]) == ("weekly", 3)
    recorder(monkeypatch)
    assert run("monday", "-p", "apollo", "--from", "weekly").exit_code == 0
    assert not failure_path(home, "apollo").exists()


def test_monday_all_records_only_the_failing_project(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.root)
    recorder(monkeypatch, fail=lambda s: s.name == "fetch" and "grp/apollo" in s.argv)
    assert run("monday", "--all").exit_code == 1
    assert failure_path(home, "apollo").exists()
    assert not failure_path(home, "gemini").exists()


def test_status_shows_the_grid_a_failure_and_the_next_command(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.root)
    recorder(monkeypatch, fail=lambda s: s.name == "weekly")
    run("monday", "-p", "apollo")
    result = run("status")
    assert result.exit_code == 0, result.output
    assert "hours" in result.output and "emails" in result.output
    assert "FAIL" in result.output
    assert "next: perch hours -p apollo" in result.output
    assert "gemini" in result.output


def test_status_dash_p_shows_one_project(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.root)
    result = run("status", "-p", "gemini")
    assert result.exit_code == 0, result.output
    assert "gemini" in result.output and "apollo" not in result.output


def test_a_tool_that_will_not_start_is_recorded_against_its_step(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)

    def fake(step):
        if step.name == "digest":
            raise FileNotFoundError("no gitboard python")

    monkeypatch.setattr("perch.cli._run", fake)
    assert run("monday", "-p", "apollo").exit_code == 1
    rec = json.loads(failure_path(home, "apollo").read_text())
    assert (rec["step"], rec["code"]) == ("digest", 1)


def test_from_a_later_step_keeps_an_earlier_failure(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    recorder(monkeypatch, fail=lambda s: s.name == "fetch")
    assert run("monday", "-p", "apollo").exit_code == 1
    recorder(monkeypatch)
    assert run("monday", "-p", "apollo", "--from", "weekly").exit_code == 0
    assert json.loads(failure_path(home, "apollo").read_text())["step"] == "fetch"


def test_status_outside_a_workspace_or_for_no_such_project_is_a_clean_error(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("PERCH_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    result = run("status")
    assert result.exit_code == 1 and isinstance(result.exception, SystemExit)
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    result = run("status", "-p", "zzz")
    assert result.exit_code == 1 and isinstance(result.exception, SystemExit)


def test_watch_for_a_project_writes_the_weeks_copy(tmp_path, monkeypatch):
    from datetime import date

    from perch.core.steps import iso_week

    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    assert run("watch", "-p", "apollo").exit_code == 0
    assert home.watch_path("apollo", iso_week(date.today())).is_file()  # noqa: DTZ011


def test_status_as_blocks(tmp_path, monkeypatch):
    from perch.core.blocks import parse

    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.root)
    recorder(monkeypatch, fail=lambda s: s.name == "weekly")
    run("monday", "-p", "apollo")
    result = CliRunner().invoke(cli, ["status"], env={"PI_BLOCKS": "1"})
    assert result.exit_code == 0, result.output
    out = [parse(line) for line in result.stdout.splitlines()]
    assert all(out), result.output
    table, nxt = out
    assert table["block"] == "table" and table["columns"][0] == "project"
    assert [r[0] for r in table["rows"]] == ["apollo", "gemini"]
    assert "FAIL" in table["rows"][0]
    assert nxt["block"] == "list" and "next: perch hours -p apollo" in nxt["items"]
