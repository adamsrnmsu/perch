import pytest
from click.testing import CliRunner

from perch.cli import cli
from perch.core.steps import StepFailed
from perch.tests.conftest import build_home


def run(*args):
    return CliRunner().invoke(cli, list(args))


def recorder(monkeypatch, fail=lambda step: False):
    ran = []

    def fake(step):
        ran.append(step)
        if fail(step):
            raise StepFailed(step, 2)

    monkeypatch.setattr("perch.cli._run", fake)
    return ran


@pytest.mark.parametrize(
    ("command", "step"),
    [
        ("fetch", "fetch"),
        ("digest", "digest"),
        ("emails", "emails"),
        ("forecast", "forecast"),
        ("budget", "budget"),
        ("hours", "hours"),
    ],
)
def test_each_step_command_runs_its_one_step(tmp_path, monkeypatch, command, step):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    monkeypatch.setenv("EDITOR", "true")
    ran = recorder(monkeypatch)
    result = run(command)
    assert result.exit_code == 0, result.output
    assert [s.name for s in ran] == [step]


def test_a_failing_step_is_a_clean_error_naming_the_project(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    recorder(monkeypatch, fail=lambda step: True)
    result = run("fetch")
    assert result.exit_code != 0 and "apollo: fetch exited 2" in result.output
    assert "Traceback" not in result.output


def test_monday_runs_the_five_steps_and_says_where_to_look(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    ran = recorder(monkeypatch)
    result = run("monday")
    assert result.exit_code == 0, result.output
    assert [s.name for s in ran] == ["fetch", "board", "weekly", "digest", "emails"]
    assert "Review, then send yourself" in result.output


def test_monday_all_carries_on_past_a_failure_and_exits_1(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.root)
    ran = recorder(
        monkeypatch, fail=lambda s: s.name == "fetch" and "grp/apollo" in s.argv
    )
    result = run("monday", "--all")
    assert result.exit_code == 1
    assert [s.name for s in ran] == [
        "fetch",
        "fetch",
        "board",
        "weekly",
        "digest",
        "emails",
    ]
    assert "apollo FAILED: fetch exited 2" in result.output
    assert "gemini ok" in result.output


def test_monday_without_gitlab_project_runs_nothing(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", gitlab=False)
    monkeypatch.chdir(home.root)
    ran = recorder(monkeypatch)
    result = run("monday")
    assert result.exit_code != 0 and "gitlab_project" in result.output
    assert ran == []


def test_p_and_all_together_is_a_usage_error(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    assert run("monday", "-p", "apollo", "--all").exit_code == 2


def test_monday_all_with_no_projects_says_init(tmp_path, monkeypatch):
    home = build_home(tmp_path)
    monkeypatch.chdir(home.root)
    result = run("monday", "--all")
    assert result.exit_code != 0 and "perch init" in result.output


def quiet_tools(monkeypatch, home):
    home.gitboard_dir.mkdir()
    monkeypatch.setattr("perch.cli._runs", lambda argv, cwd, env: True)
    monkeypatch.setattr("perch.cli._show_gitboard_config", lambda home: None)


def test_doctor_all_well_exits_0_with_no_fix(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.root)
    quiet_tools(monkeypatch, home)
    result = run("doctor")
    assert result.exit_code == 0, result.output
    assert "FIX" not in result.output
    assert (
        "apollo: board dump" in result.output and "gemini: board dump" in result.output
    )


def test_doctor_names_the_fix_and_exits_1(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", gitlab=False)
    monkeypatch.chdir(home.root)
    quiet_tools(monkeypatch, home)
    result = run("doctor", "-p", "apollo")
    assert result.exit_code == 1
    assert "FIX" in result.output and "gitlab_project" in result.output


def break_config(home, name):
    home.config_path(name).write_text("budgie_project: [unclosed\n")


def test_monday_all_survives_a_malformed_perch_yaml(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    break_config(home, "apollo")
    monkeypatch.chdir(home.root)
    ran = recorder(monkeypatch)
    result = run("monday", "--all")
    assert result.exit_code == 1
    assert "apollo FAILED" in result.output and "gemini ok" in result.output
    assert [s.name for s in ran] == ["fetch", "board", "weekly", "digest", "emails"]


def test_doctor_reports_a_malformed_perch_yaml_as_a_fix(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    break_config(home, "apollo")
    monkeypatch.chdir(home.root)
    quiet_tools(monkeypatch, home)
    result = run("doctor")
    assert result.exit_code == 1
    assert "FIX" in result.output and "Traceback" not in result.output


def test_help_short_text_is_not_cut_at_the_step_number():
    assert "Step 1: one GitLab read" in run("--help").output
