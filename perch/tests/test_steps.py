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


def test_budgie_init_passes_year_flags_only_when_given(tmp_path):
    home, _ = apollo(tmp_path)
    step = steps.budgie_init(BIN, home, "gemini", year="2027", year_start="10-01")
    assert step.argv == (
        "/venv/bin/budgie",
        "init",
        "--year",
        "2027",
        "--year-start",
        "10-01",
        "gemini",
    )
    assert steps.budgie_init(BIN, home, "g", year="2027").argv[2:] == (
        "--year",
        "2027",
        "g",
    )


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


def _person(week, name, gap, **extra):
    return {"week": week, "kind": "person", "name": name, "open": 2,
            "hours": 10.0, "left": 10.0 + gap, "gap": gap, **extra}  # fmt: skip


def test_review_opens_claudes_board_command_in_gitboard_with_team_and_people(
    tmp_path,
):
    home, config = apollo(tmp_path)
    (home.gitboard_dir / "boards").mkdir(parents=True)
    (home.gitboard_dir / "boards" / "apollo.yaml").write_text("")
    rows = [
        _person("2026-W39", "Alice", 99.0),  # an older week: dropped
        {"week": "2026-W40", "kind": "team", "name": "team", "headroom": 1.0},
        _person("2026-W40", "Bob", -4.0, rate=150.0, cost=1500.0),
        _person("2026-W40", "Alice", 1234.0),
        _person("2026-W40", "Zed", 0.0),  # not in people: no @login
    ]
    step = steps.review(home, "apollo", config, rows)
    claude, flag, context, prompt = step.argv
    assert (claude, flag, prompt) == (
        "claude",
        "--append-system-prompt",
        "/board grp/apollo",
    )
    lines = context.split("\n")
    assert lines[1].startswith("— · over — · budget — · spent — · headroom $1")
    assert lines[-3:] == [
        "Alice, @asmith · open 2 · to clear 10h · left 1,244h · gap +1,234h",
        "Bob, @bjones · open 2 · to clear 10h · left 6h · gap −4h",
        "Zed · open 2 · to clear 10h · left 10h · gap +0h",
    ]
    assert "150" not in context and "1,500" not in context  # load, not pay
    assert "Never rank" in context and step.cwd == home.gitboard_dir


def test_people_lines_is_empty_before_any_person_row():
    assert steps.people_lines([], {}) == []


def test_review_without_a_pulled_board_says_how_to_pull_it(tmp_path):
    home, config = apollo(tmp_path)
    with pytest.raises(WorkspaceError, match="gitboard pull grp/apollo --base"):
        steps.review(home, "apollo", config, [])
    _, bare = apollo(tmp_path / "bare", gitlab=False)
    with pytest.raises(WorkspaceError, match="gitlab_project"):
        steps.review(home, "apollo", bare, [])


@pytest.mark.parametrize(
    ("sub", "tail"),
    [
        ("show", ("show", "--from", "SPEC", "--markdown")),
        ("graph", ("graph", "--from", "SPEC")),
        ("plan", ("plan", "SPEC", "--against", "BASE")),
        ("estimate", ("estimate", "SPEC", "--history", "DUMP")),
        ("stats", ("stats", "--from", "DUMP")),
        ("report", ("report", "--since", "SPEC")),
        ("status", ("status",)),
        ("push", ("push", "SPEC")),
        ("pull", ("pull", "grp/apollo", "--base")),
    ],
)
def test_gb_fills_in_the_projects_target(tmp_path, sub, tail):
    home, config = apollo(tmp_path)
    spec = str(home.gitboard_dir / "boards" / "apollo.yaml")
    base = home.gitboard_dir / "boards" / "apollo.yaml.base"
    base.parent.mkdir(parents=True)
    base.write_text("")
    want = tuple(
        {"SPEC": spec, "BASE": str(base), "DUMP": str(config.board_dump)}.get(t, t)
        for t in tail
    )
    step = steps.gb(home, "apollo", config, sub)
    gb = home.gitboard_dir
    assert step.argv == (str(gb / ".venv/bin/python"), "-m", "gitboard.cli", *want)
    assert step.cwd == gb and step.env == {"PYTHONPATH": str(gb / "src")}


def test_walk_opens_claude_on_the_slash_command_in_the_workspace(tmp_path):
    home, _ = apollo(tmp_path)
    step = steps.walk(home, "apollo")
    assert step.argv == ("claude", "/walk apollo")
    assert step.cwd == home.root


def test_gb_passes_extra_args_through(tmp_path):
    home, config = apollo(tmp_path)
    step = steps.gb(home, "apollo", config, "push", ("--yes",))
    assert step.argv[-1] == "--yes"


@pytest.mark.parametrize(
    "sub,args",
    [
        ("show", ("--from", "")),
        ("plan", ("--against=",)),
        ("estimate", ("--history", "")),
        ("report", ("--since", "")),
        ("show", ("grp/other",)),
    ],
)
def test_gb_offline_subs_refuse_args_that_override_the_target(tmp_path, sub, args):
    home, config = apollo(tmp_path)
    with pytest.raises(ValueError, match="perch fills in"):
        steps.gb(home, "apollo", config, sub, args)


def test_gb_offline_subs_keep_legit_args(tmp_path):
    home, config = apollo(tmp_path)
    step = steps.gb(home, "apollo", config, "graph", ("-M", "v1"))
    assert step.argv[-2:] == ("-M", "v1")


def test_offline_subs_are_the_ones_walk_may_run():
    assert steps.GB_OFFLINE == (
        "show",
        "report",
        "stats",
        "graph",
        "estimate",
        "plan",
        "status",
    )
    assert set(steps.GB_SUBS) == {*steps.GB_OFFLINE, "push", "pull"}


def test_gb_plan_without_a_base_says_where_to_pull(tmp_path):
    home, config = apollo(tmp_path)
    with pytest.raises(WorkspaceError, match="where GitLab is reachable"):
        steps.gb(home, "apollo", config, "plan")
    spec = home.gitboard_dir / "boards" / "apollo.yaml"
    spec.parent.mkdir(parents=True)
    spec.write_text("")  # a pull without --base: --force would drop edits
    with pytest.raises(
        WorkspaceError, match="--force without a .base discards unpushed edits"
    ):
        steps.gb(home, "apollo", config, "plan")


def test_gb_refuses_an_unknown_sub_and_a_missing_gitlab_project(tmp_path):
    home, config = apollo(tmp_path)
    with pytest.raises(ValueError, match="sync"):
        steps.gb(home, "apollo", config, "sync")
    _, bare = apollo(tmp_path / "bare", gitlab=False)
    with pytest.raises(WorkspaceError, match="gitlab_project"):
        steps.gb(home, "apollo", bare, "show")


def test_bg_runs_budgie_in_the_project_with_args_passed_through(tmp_path):
    _, config = apollo(tmp_path)
    step = steps.bg(BIN, config, "monthly", ("--year", "2026"))
    assert step.argv == ("/venv/bin/budgie", "monthly", "--year", "2026")
    assert (step.name, step.cwd) == ("bg monthly", config.budgie_project)


@pytest.mark.parametrize("args", [("--project", "x"), ("--project=x",)])
def test_bg_refuses_args_that_pick_another_project(tmp_path, args):
    _, config = apollo(tmp_path)
    with pytest.raises(ValueError, match="--project"):
        steps.bg(BIN, config, "plan", args)


def test_bg_refuses_an_unknown_sub(tmp_path):
    _, config = apollo(tmp_path)
    with pytest.raises(ValueError, match="init"):
        steps.bg(BIN, config, "init")
