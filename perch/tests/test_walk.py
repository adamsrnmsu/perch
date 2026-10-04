import json
import re

import yaml
from click.testing import CliRunner

from perch.cli import cli
from perch.core import walk
from perch.tests.conftest import build_home


def frontmatter(text):
    _, head, body = text.split("---", 2)
    return yaml.safe_load(head), body


def settings_path(home):
    return home.root / ".claude" / "settings.json"


def test_install_writes_the_command_with_the_gitboard_path(tmp_path):
    home = build_home(tmp_path, "apollo")
    walk.install(home)
    text = walk.command_path(home).read_text()
    head, _ = frontmatter(text)
    assert f"Edit(/{home.gitboard_dir}/boards/*.yaml)" in head["allowed-tools"]
    assert "@GITBOARD_DIR@" not in text


def test_install_never_overwrites_the_leads_copy(tmp_path):
    home = build_home(tmp_path, "apollo")
    path = walk.command_path(home)
    path.parent.mkdir(parents=True)
    path.write_text("mine")
    walk.install(home)
    assert path.read_text() == "mine"


def test_every_perch_command_in_allowed_tools_exists(tmp_path):
    head, _ = frontmatter(walk.render(build_home(tmp_path, "apollo")))
    used = set(re.findall(r"Bash\(perch (\w+)", head["allowed-tools"]))
    assert used <= set(cli.commands)
    assert used >= {"brief", "cut", "gb"}


def test_walk_never_pushes_or_pulls(tmp_path):
    from perch.core.steps import GB_OFFLINE

    head, _ = frontmatter(walk.render(build_home(tmp_path, "apollo")))
    subs = set(re.findall(r"Bash\(perch gb (\w+)", head["allowed-tools"]))
    assert subs == set(GB_OFFLINE)


def test_the_body_says_what_to_do_without_perch_on_path(tmp_path):
    _, body = frontmatter(walk.render(build_home(tmp_path, "apollo")))
    assert "perch is not on PATH" in body
    assert "conversation only" in body
    assert "There is no GitLab here" in body


def test_settings_created_with_the_gitboard_dir(tmp_path):
    home = build_home(tmp_path, "apollo")
    walk.install(home)
    settings = json.loads(settings_path(home).read_text())
    assert settings["permissions"]["additionalDirectories"] == [str(home.gitboard_dir)]


def test_settings_merge_keeps_other_keys_and_adds_once(tmp_path):
    home = build_home(tmp_path, "apollo")
    path = settings_path(home)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"model": "x", "permissions": {"allow": ["Read"]}}))
    walk.install(home)
    walk.install(home)
    settings = json.loads(path.read_text())
    assert settings["model"] == "x"
    assert settings["permissions"]["allow"] == ["Read"]
    assert settings["permissions"]["additionalDirectories"] == [str(home.gitboard_dir)]


def test_settings_that_are_not_valid_json_are_left_alone(tmp_path):
    home = build_home(tmp_path, "apollo")
    path = settings_path(home)
    path.parent.mkdir(parents=True)
    path.write_text("{oops")
    lines = walk.install(home)
    assert path.read_text() == "{oops"
    assert any("by hand" in line and str(home.gitboard_dir) in line for line in lines)


def test_settings_with_a_non_list_additional_directories_are_left_alone(tmp_path):
    home = build_home(tmp_path, "apollo")
    path = settings_path(home)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"permissions": {"additionalDirectories": "x"}}))
    walk.install(home)
    assert json.loads(path.read_text())["permissions"]["additionalDirectories"] == "x"


def test_checks_missing_differing_and_ok(tmp_path):
    home = build_home(tmp_path, "apollo")
    assert [c.ok for c in walk.checks(home)] == [False, False]
    walk.install(home)
    assert [c.ok for c in walk.checks(home)] == [True, True]
    walk.command_path(home).write_text("edited")
    command, _ = walk.checks(home)
    assert not command.ok and "differs" in command.what


def test_doctor_names_the_walk_fix(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    monkeypatch.setattr("perch.cli._runs", lambda argv, cwd, env: True)
    monkeypatch.setattr("perch.cli._show_gitboard_config", lambda home: True)
    result = CliRunner().invoke(cli, ["doctor"])
    assert "walk: no .claude/commands/walk.md" in result.output


def test_checks_unparseable_settings_say_fix_by_hand_not_perch_walk(tmp_path):
    home = build_home(tmp_path, "apollo")
    walk.install(home)
    settings_path(home).write_text("{oops")
    _, board = walk.checks(home)
    assert not board.ok and "by hand" in board.fix and "perch walk," not in board.fix
