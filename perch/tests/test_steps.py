from datetime import date
from pathlib import Path

import pytest

from perch.core import steps
from perch.core.config import load_config
from perch.core.workspace import WorkspaceError
from perch.tests.conftest import build_home

BIN = Path("/venv/bin")


def apollo(tmp_path, gitlab=True):
    home = build_home(tmp_path, "apollo", gitlab=gitlab)
    return home, load_config(home.config_path("apollo"), require_dump=False)


def test_monday_is_five_steps_in_order_each_in_its_tool(tmp_path):
    home, config = apollo(tmp_path)
    run = steps.monday(BIN, home, "apollo", config, "2026-W40")
    assert [s.name for s in run] == ["fetch", "board", "weekly", "digest", "emails"]
    fetch, board, weekly, digest, emails = run
    gb = home.gitboard_dir
    assert fetch.argv == (
        str(gb / ".venv/bin/python"), "-m", "gitboard.cli",
        "stats", "grp/apollo", "--history-days", "276", "--dump", str(config.board_dump),
    )  # fmt: skip
    assert fetch.cwd == gb and fetch.env == {"PYTHONPATH": str(gb / "src")}
    assert fetch.makes == (config.board_dump.parent,)
    assert board.argv == (
        "/venv/bin/perch",
        "board",
        "--config",
        str(home.config_path("apollo")),
    )
    weekly_md = home.projects_dir / "apollo" / "weekly" / "2026-W40.md"
    assert weekly.argv[-2:] == ("--out", str(weekly_md))
    assert weekly.makes == (weekly_md.parent,)
    assert digest.argv[-4:] == (
        "--from",
        str(config.board_dump),
        "--out",
        str(gb / "reports" / "apollo"),
    )
    assert emails.argv == (
        "/venv/bin/budgie",
        "emails",
        "--out-dir",
        "emails",
        "--no-preview",
    )
    assert emails.cwd == config.budgie_project


def test_monday_from_a_step_runs_it_and_the_rest(tmp_path):
    home, config = apollo(tmp_path)
    run = steps.monday(BIN, home, "apollo", config, "2026-W40", "weekly")
    assert [s.name for s in run] == ["weekly", "digest", "emails"]
    assert steps.MONDAY_STEPS == ("fetch", "board", "weekly", "digest", "emails")
    assert len(steps.monday(BIN, home, "apollo", config, "2026-W40", None)) == 5
    with pytest.raises(ValueError, match="nope"):
        steps.monday(BIN, home, "apollo", config, "2026-W40", "nope")


def test_fetch_without_gitlab_project_says_what_to_add(tmp_path):
    home, config = apollo(tmp_path, gitlab=False)
    with pytest.raises(WorkspaceError, match="gitlab_project"):
        steps.monday(BIN, home, "apollo", config, "2026-W40")


def test_budgie_steps_run_inside_the_budgie_project(tmp_path):
    _, config = apollo(tmp_path)
    assert steps.forecast(BIN, config).argv == ("/venv/bin/budgie", "forecast")
    assert steps.budget(BIN, config).argv == ("/venv/bin/budgie", "status")
    assert steps.budget(BIN, config).cwd == config.budgie_project


def test_hours_opens_weekly_csv_with_an_editor_that_has_flags(tmp_path):
    _, config = apollo(tmp_path)
    step = steps.hours("code -w", config)
    assert step.argv == ("code", "-w", str(config.budgie_project / "weekly.csv"))


def test_budgie_init_runs_from_the_workspace_root(tmp_path):
    home, _ = apollo(tmp_path)
    step = steps.budgie_init(BIN, home, "gemini")
    assert step.argv == ("/venv/bin/budgie", "init", "gemini") and step.cwd == home.root


def test_iso_week_matches_date_G_W_V():
    assert steps.iso_week(date(2026, 1, 1)) == "2026-W01"
    assert steps.iso_week(date(2027, 1, 1)) == "2026-W53"


def test_shown_is_a_command_you_could_paste(tmp_path):
    step = steps.Step("x", ("echo", "a b"), Path("/tmp/w s"))
    assert step.shown() == "(cd '/tmp/w s' && echo 'a b')"
    with_env = steps.Step("x", ("py",), Path("/x"), env={"PYTHONPATH": "/x/s p"})
    assert with_env.shown() == "(cd /x && PYTHONPATH='/x/s p' py)"


def test_run_projects_carries_on_past_a_failure():
    ran = []

    def run_one(name):
        ran.append(name)
        if name == "b":
            raise steps.StepFailed(steps.Step("fetch", ("x",), Path(".")), 2)

    results = steps.run_projects(["a", "b", "c"], run_one)
    assert ran == ["a", "b", "c"]
    assert [(n, e and str(e)) for n, e in results] == [
        ("a", None),
        ("b", "fetch exited 2"),
        ("c", None),
    ]
