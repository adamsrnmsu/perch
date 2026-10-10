from datetime import date

import yaml

from perch.core import brief, steps
from perch.core.config import load_config
from perch.tests.conftest import build_home

TODAY = date(2026, 4, 20)  # 2026-W17, the world's fetch day


def apollo(tmp_path, gitlab=True):
    home = build_home(tmp_path, "apollo", gitlab=gitlab)
    return home, load_config(home.config_path("apollo"), require_dump=False)


def board_yaml(home, issues, columns=("Doing", "Verify")):
    path = home.board_dir("apollo") / "apollo.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    spec = {"columns": [{"name": c} for c in columns], "issues": issues}
    path.write_text(yaml.safe_dump(spec))
    return path


def section(lines, heading):
    start = lines.index(f"## {heading}") + 1
    end = next(
        (i for i in range(start, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return lines[start:end]


def test_sections_print_in_order(tmp_path):
    home, config = apollo(tmp_path)
    board_yaml(home, [])
    lines = brief.build(home, "apollo", config, TODAY)
    heads = [line for line in lines if line.startswith("## ")]
    assert heads == [
        "## Freshness", "## Team", "## People", "## Forecast", "## Watch",
        "## Follow-ups",
    ]  # fmt: skip


def test_first_week_says_what_is_missing_and_still_prints_the_rest(tmp_path):
    home, config = apollo(tmp_path)
    config.history.unlink(missing_ok=True)
    lines = brief.build(home, "apollo", config, TODAY)
    assert section(lines, "Team") == ["no week recorded yet: run perch board"]
    assert section(lines, "People") == ["no person rows yet"]
    assert section(lines, "Watch") == ["none for 2026-W17; run perch monday -p apollo"]
    assert section(lines, "Follow-ups") == [
        "no board/apollo.yaml; run perch gb pull -p apollo where GitLab is reachable"
    ]
    assert "## Forecast" in lines


def test_forecast_is_team_level_with_no_per_person_money(tmp_path):
    home, config = apollo(tmp_path)
    lines = brief.build(home, "apollo", config, TODAY)
    forecast = section(lines, "Forecast")
    assert forecast[0].startswith("at completion P10 $")
    assert " · budget $100,000 · " in forecast[0]
    people = section(lines, "People") + forecast
    for name in ("Alice", "Bob"):
        assert not any(name in line and "$" in line for line in people)


def test_forecast_with_no_hours_booked_says_nothing_to_forecast_from(tmp_path):
    home, config = apollo(tmp_path)
    (config.budgie_project / "weekly.csv").write_text("name,week,hours_to_date\n")
    lines = brief.build(home, "apollo", config, TODAY)
    assert section(lines, "Forecast") == [
        "no hours booked yet: nothing to forecast from"
    ]


def test_follow_ups_list_open_followup_cards_and_new_ones(tmp_path):
    home, config = apollo(tmp_path)
    board_yaml(
        home,
        [
            {"title": "Decide on 700k cut", "iid": 12, "labels": ["followup", "Doing"],
             "assignee": "asmith", "due_date": "2026-04-30"},
            {"title": "Ask funder about Q3", "labels": ["followup"]},
            {"title": "Not a follow-up", "iid": 13, "labels": ["Doing"]},
        ],
    )  # fmt: skip
    lines = section(brief.build(home, "apollo", config, TODAY), "Follow-ups")
    assert lines == [
        "#12 · Decide on 700k cut · Doing · @asmith · due 2026-04-30",
        "new · Ask funder about Q3 · Backlog · unassigned · no due date",
    ]


def test_no_follow_ups_says_so(tmp_path):
    home, config = apollo(tmp_path)
    board_yaml(home, [{"title": "x", "iid": 1, "labels": []}])
    lines = section(brief.build(home, "apollo", config, TODAY), "Follow-ups")
    assert lines == ["none open"]


def test_watch_is_this_weeks_file_with_headings_under_the_section(tmp_path):
    home, config = apollo(tmp_path)
    path = home.watch_path("apollo", "2026-W17")
    path.parent.mkdir(parents=True)
    path.write_text("# Watch\n\n## Alice\n- **Flag:** work in Doing: #1\n")
    lines = brief.build(home, "apollo", config, TODAY)
    assert section(lines, "Watch") == [
        "### Watch", "", "#### Alice", "- **Flag:** work in Doing: #1",
    ]  # fmt: skip
    assert "## Alice" not in lines


def test_no_gitlab_project_still_prints_money_and_names_the_fix(tmp_path):
    home, config = apollo(tmp_path, gitlab=False)
    lines = brief.build(home, "apollo", config, TODAY)
    fix = "apollo: perch.yaml has no gitlab_project; "
    assert section(lines, "Follow-ups") == [
        fix + "add e.g. `gitlab_project: group/apollo`"
    ]
    assert section(lines, "Forecast")[0].startswith("at completion")


def test_freshness_names_dump_pull_and_week(tmp_path):
    home, config = apollo(tmp_path)
    lines = section(brief.build(home, "apollo", config, TODAY), "Freshness")
    assert lines[0] == "board dump fetched 2026-04-20T08:00:00+00:00"
    assert lines[1] == (
        "board YAML: never pulled; run perch gb pull -p apollo "
        "where GitLab is reachable"
    )
    assert lines[2] == "last week recorded: none; run perch board -p apollo"
    assert lines[-2] == "today: 2026-W17"


def test_freshness_prints_the_board_file_path(tmp_path):
    home, config = apollo(tmp_path)
    lines = section(brief.build(home, "apollo", config, TODAY), "Freshness")
    spec = home.board_dir("apollo") / "apollo.yaml"
    assert f"board file: {spec}" in lines


def test_freshness_names_the_pull_time_when_pulled(tmp_path):
    home, config = apollo(tmp_path)
    board_yaml(home, [])
    (home.board_dir("apollo") / "apollo.yaml.base").write_text("")
    lines = section(brief.build(home, "apollo", config, TODAY), "Freshness")
    assert lines[1].startswith("board YAML pulled 2")


def test_freshness_says_a_board_without_base_cannot_be_planned(tmp_path):
    home, config = apollo(tmp_path)
    board_yaml(home, [])
    lines = section(brief.build(home, "apollo", config, TODAY), "Freshness")
    assert lines[1].startswith("board YAML has no .base (plan cannot diff it)")
    assert "push or copy it first" in lines[1]
    assert "--force without a .base discards unpushed edits" in lines[1]


def test_a_malformed_board_yaml_is_one_line_and_the_rest_prints(tmp_path):
    home, config = apollo(tmp_path)
    path = board_yaml(home, [])
    path.write_text("issues: [{labels: [followup")
    lines = brief.build(home, "apollo", config, TODAY)
    (follow,) = section(lines, "Follow-ups")
    assert follow.startswith("follow-ups: could not read:")
    assert section(lines, "Forecast")[0].startswith("at completion")


def test_a_board_yaml_that_is_not_a_mapping_is_one_line(tmp_path):
    home, config = apollo(tmp_path)
    board_yaml(home, []).write_text("- just\n- a list\n")
    (follow,) = section(brief.build(home, "apollo", config, TODAY), "Follow-ups")
    assert follow.startswith("follow-ups: could not read:")


def test_a_corrupt_history_is_one_line_per_section_and_the_rest_prints(tmp_path):
    home, config = apollo(tmp_path)
    config.history.write_text("{oops\n")
    lines = brief.build(home, "apollo", config, TODAY)
    assert section(lines, "Team")[0].startswith("team: could not read:")
    assert section(lines, "People")[0].startswith("people: could not read:")
    freshness = section(lines, "Freshness")
    assert freshness[0].startswith("board dump fetched")
    assert freshness[2].startswith("last week recorded: history.jsonl unreadable")
    assert section(lines, "Forecast")[0].startswith("at completion")


def test_a_dump_that_is_not_a_mapping_still_prints_freshness(tmp_path):
    home, config = apollo(tmp_path)
    config.board_dump.write_text("[]")
    lines = section(brief.build(home, "apollo", config, TODAY), "Freshness")
    assert lines[0] == "board dump fetched at an unknown time"


def test_spec_path_is_the_gitlab_projects_last_segment(tmp_path):
    home, config = apollo(tmp_path)
    assert steps.spec_path(home, "apollo", config) == (
        home.board_dir("apollo") / "apollo.yaml"
    )


def test_cli_brief_prints_the_sections(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from perch.cli import cli

    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    result = CliRunner().invoke(cli, ["brief", "-p", "apollo"])
    assert result.exit_code == 0, result.output
    assert "## Forecast" in result.output
