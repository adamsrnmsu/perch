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


def test_install_writes_the_command_with_the_checkout_path(tmp_path):
    home = build_home(tmp_path, "apollo")
    walk.install(home)
    text = walk.command_path(home).read_text()
    head, _ = frontmatter(text)
    assert f"Edit(/{home.root}/projects/*/board/*.yaml)" in head["allowed-tools"]
    assert "@PERCH_DIR@" not in text


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


def test_walk_leaves_settings_json_alone(tmp_path):
    home = build_home(tmp_path, "apollo")
    sp = settings_path(home)
    sp.parent.mkdir(parents=True)
    sp.write_text('{"a": 1}')
    walk.install(home)
    assert sp.read_text() == '{"a": 1}'
    assert not any(c.what.startswith("walk: gitboard") for c in walk.checks(home))


def test_walk_allow_glob_is_absolute(tmp_path):
    home = build_home(tmp_path, "apollo")
    text = walk.render(home, "walk")
    head, _ = frontmatter(text)
    # the template's leading "/" plus an absolute root is Claude's absolute-path form
    assert f"Edit(/{home.root}/projects/*/board/*.yaml)" in head["allowed-tools"]
    assert "@PERCH_DIR@" not in text


def test_install_reports_wrote_then_kept(tmp_path):
    home = build_home(tmp_path, "apollo")
    assert walk.install(home)[0].startswith("wrote")
    assert walk.install(home)[0].startswith("kept")


def test_checks_missing_differing_and_ok(tmp_path):
    home = build_home(tmp_path, "apollo")
    assert [c.ok for c in walk.checks(home)] == [False]
    walk.install(home)
    assert [c.ok for c in walk.checks(home)] == [True]
    walk.command_path(home).write_text("edited")
    (command,) = walk.checks(home)
    assert not command.ok and "differs" in command.what


def test_doctor_names_the_walk_fix(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    monkeypatch.setattr("perch.cli._runs", lambda argv, cwd, env: True)
    monkeypatch.setattr("perch.cli._show_gitboard_config", lambda home: True)
    result = CliRunner().invoke(cli, ["doctor"])
    assert "walk: no .claude/commands/walk.md" in result.output
