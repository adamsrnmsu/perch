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
