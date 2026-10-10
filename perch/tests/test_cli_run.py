import json
from datetime import date
from pathlib import Path

import pytest
from click.testing import CliRunner

from perch.cli import cli
from perch.core import steps
from perch.core.steps import Step, StepFailed
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


def test_hours_falls_back_to_vim_when_editor_is_unset(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    monkeypatch.delenv("EDITOR", raising=False)
    ran = recorder(monkeypatch)
    assert run("hours").exit_code == 0
    assert ran[0].argv[0] == "vim"


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
    # the private watch: a file under the project, and one line
    week = steps.iso_week(date.today())  # noqa: DTZ011 -- as monday names it
    page = home.projects_dir / "apollo" / "watch" / f"{week}.md"
    assert page.read_text().startswith("# Watch, grp/proj Dev, 2026-W17")
    assert result.output.rstrip().endswith("watch: nothing out of line")


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
    from perch.core import walk

    walk.install(home)  # an installed /walk is part of a healthy workspace
    monkeypatch.setattr("perch.cli._runs", lambda argv, cwd, env: True)
    monkeypatch.setattr("perch.cli._show_gitboard_config", lambda home: True)


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


def test_monday_from_inside_a_project_runs_that_project(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.projects_dir / "gemini")
    ran = recorder(monkeypatch)
    result = run("monday")
    assert result.exit_code == 0, result.output
    assert "grp/gemini" in ran[0].argv


def test_doctor_reports_a_missing_gitlab_token(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    quiet_tools(monkeypatch, home)
    monkeypatch.setattr("perch.cli._show_gitboard_config", lambda home: False)
    result = run("doctor")
    assert result.exit_code == 1
    assert "FIX" in result.output and "read token not found" in result.output


def test_a_watch_that_cannot_be_read_does_not_fail_monday(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    (home.projects_dir / "apollo" / "history.jsonl").write_text("not json\n")
    monkeypatch.chdir(home.root)
    recorder(monkeypatch)
    result = run("monday")
    assert result.exit_code == 0, result.output
    assert "watch: could not be read:" in result.output
    assert "Traceback" not in result.output


def test_help_lists_every_command_once_in_workflow_order():
    from perch.cli import _SECTIONS, cli

    listed = [name for names in _SECTIONS.values() for name in names]
    assert sorted(listed) == sorted(cli.commands)
    out = run("--help").output
    steps = ["hours", "fetch", "board", "weekly", "digest", "emails"]
    assert sorted(steps, key=lambda c: out.index(f"  {c} ")) == steps


def blocks_of(result):
    from perch.core.blocks import parse

    out = [parse(line) for line in result.stdout.splitlines()]
    assert all(out), result.output
    return out


def test_doctor_as_blocks(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", gitlab=False)
    monkeypatch.chdir(home.root)
    quiet_tools(monkeypatch, home)
    result = CliRunner().invoke(cli, ["doctor", "-p", "apollo"], env={"PI_BLOCKS": "1"})
    assert result.exit_code == 1
    out = blocks_of(result)
    heads = [b["text"] for b in out if b["block"] == "heading"]
    assert heads[:5] == ["Tools", "Projects", "Walk", "Alerts", "Data (last written)"]
    fix = next(b for b in out if b["block"] == "text" and b["text"].startswith("FIX"))
    assert fix["tone"] == "bad" and "gitlab_project" in fix["text"]
    assert any(b["block"] == "text" and b.get("tone") == "good" for b in out)
    assert any(
        b["block"] == "list" and "apollo: board dump" in b["items"][0] for b in out
    )


def test_monday_as_blocks(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    recorder(monkeypatch)  # _run is faked: no step header
    result = CliRunner().invoke(cli, ["monday"], env={"PI_BLOCKS": "1"})
    assert result.exit_code == 0, result.output
    out = [json.loads(x) for x in result.stdout.splitlines() if x.startswith("{")]
    done = next(b for b in out if b["block"] == "text" and "done. Review" in b["text"])
    paths = out[out.index(done) + 1]
    assert paths["block"] == "list" and len(paths["items"]) == 3
    assert out[-1]["block"] == "text" and out[-1]["text"].startswith("watch:")


def test_run_header_is_a_heading_and_a_dim_command(capsys, monkeypatch):
    from perch.cli import _run

    monkeypatch.setenv("PI_BLOCKS", "1")
    _run(Step("fetch", ("true",), Path.cwd()))
    first, second = (json.loads(x) for x in capsys.readouterr().out.splitlines()[:2])
    assert (first["block"], first["level"], first["text"]) == ("heading", 3, "fetch")
    assert second["block"] == "text" and second["tone"] == "dim"


def test_gb_runs_one_gitboard_step_with_passthrough_args(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    ran = recorder(monkeypatch)
    result = run("gb", "graph", "-p", "apollo", "-M", "v1")
    assert result.exit_code == 0, result.output
    assert [s.name for s in ran] == ["gb graph"]
    assert ran[0].argv[-2:] == ("-M", "v1")


def test_walk_installs_the_command_then_runs_claude(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    ran = recorder(monkeypatch)
    result = run("walk", "-p", "apollo")
    assert result.exit_code == 0, result.output
    assert [s.argv for s in ran] == [("claude", "/walk apollo")]
    assert (home.root / ".claude" / "commands" / "walk.md").is_file()


def test_gb_refuses_sync(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    result = run("gb", "sync", "-p", "apollo")
    assert result.exit_code == 2


def test_gb_help_after_the_sub_goes_to_gitboard(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    ran = recorder(monkeypatch)
    result = run("gb", "show", "-p", "apollo", "--help")
    assert result.exit_code == 0, result.output
    assert ran[0].argv[-1] == "--help"


def test_bg_runs_one_budgie_step_with_passthrough_args(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    ran = recorder(monkeypatch)
    result = run("bg", "monthly", "-p", "apollo", "--year", "2026")
    assert result.exit_code == 0, result.output
    assert [s.name for s in ran] == ["bg monthly"]
    assert ran[0].argv[-3:] == ("monthly", "--year", "2026")


def test_bg_refuses_init(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    assert run("bg", "init", "-p", "apollo").exit_code == 2
