import os
from datetime import datetime, timezone

import pytest

from perch.core.doctor import age, freshness, project_checks, tool_checks
from perch.tests.conftest import build_home


def test_a_healthy_project_needs_no_fix(tmp_path):
    home = build_home(tmp_path, "apollo")
    assert all(c.ok for c in project_checks(home, "apollo"))


def test_no_dump_yet_is_not_a_fault(tmp_path):
    home = build_home(tmp_path, "apollo")
    (home.projects_dir / "apollo" / "dump.json").unlink()
    assert all(c.ok for c in project_checks(home, "apollo"))


@pytest.mark.parametrize(
    ("old", "new", "says"),
    [
        ("gitlab_project: grp/apollo\n", "", "gitlab_project not set"),
        ("bjones: Bob", "bjones: Bobby", "Bobby"),
        ("budgie_project: fy26", "budgie_project: nope", "budgie.yaml"),
        ("people:\n  asmith: Alice\n  bjones: Bob\n", "", "people: is empty"),
        ("board_dump", "boardump", "unknown keys"),
    ],
)
def test_one_fault_gives_exactly_one_fix(tmp_path, old, new, says):
    home = build_home(tmp_path, "apollo")
    path = home.config_path("apollo")
    assert old in path.read_text()
    path.write_text(path.read_text().replace(old, new))
    failed = [c for c in project_checks(home, "apollo") if not c.ok]
    assert len(failed) == 1, failed
    assert says in failed[0].what and failed[0].fix


def test_freshness_says_never_for_what_has_not_been_written(tmp_path):
    home = build_home(tmp_path, "apollo")
    seen = dict(freshness(home, "apollo"))
    assert seen["history.jsonl"] == "never"
    assert seen["board dump"] != "never" and seen["weekly.csv"] != "never"


def test_age_of_a_missing_file_is_never(tmp_path):
    assert age(tmp_path / "nope") == "never"


def test_age_shows_local_time_not_utc(tmp_path):
    path = tmp_path / "test_file"
    path.write_text("test")
    ts = 1234567890  # 2009-02-13 23:31:30 UTC
    os.utime(path, (ts, ts))
    expected = (
        datetime.fromtimestamp(ts, tz=timezone.utc)
        .astimezone()
        .strftime("%Y-%m-%d %H:%M")
    )
    assert age(path) == expected


def test_tool_checks_name_the_tool_that_does_not_run(tmp_path):
    home = build_home(tmp_path)
    checks = tool_checks(tmp_path, home, lambda argv, cwd, env: "budgie" not in argv[0])
    assert [c.what for c in checks if not c.ok] == ["budgie does not run"]


def test_a_missing_gitboard_says_make_install(tmp_path):
    home = build_home(tmp_path)
    home.gitboard_dir.rmdir()
    failed = [c for c in tool_checks(tmp_path, home, lambda *a: True) if not c.ok]
    assert len(failed) == 1 and "run make install in the perch checkout" in failed[0].fix


def test_alert_checks(tmp_path):
    from perch.core.doctor import alert_checks
    from perch.core.workspace import checkout_home

    home = build_home(tmp_path, "apollo")
    assert all(c.ok for c in alert_checks(home))
    path = home.root / "config.yaml"
    path.write_text("alerts:\n  - when: headroom < 50k\n")
    (ok,) = alert_checks(checkout_home(home.root))
    assert ok.ok and "1 rule" in ok.what
    path.write_text(path.read_text() + "  - when: pace < 80\n")
    (bad,) = alert_checks(checkout_home(home.root))
    assert not bad.ok and "alerts[1].when" in bad.what and "config.yaml" in bad.fix


def old_workspace(tmp_path):
    """A pre-checkout workspace: perch-home.yaml, projects/apollo, budget/fy26, gitboard boards."""
    old = tmp_path / "old"
    (old / "projects/apollo").mkdir(parents=True)
    (old / "perch-home.yaml").write_text("gitboard_dir: gb\n")
    (old / "projects/apollo/perch.yaml").write_text(
        "budgie_project: ../../budget/fy26\ngitlab_project: g/sub/apollo-api\n"
    )
    (old / "budget/fy26").mkdir(parents=True)
    boards = old / "gb/boards"
    boards.mkdir(parents=True)
    for suffix in ("", ".base", ".base.old"):
        (boards / f"apollo-api.yaml{suffix}").write_text("")
    (old / "gb/snapshots.jsonl").write_text("")
    (old / "gb/reports").mkdir()
    (old / "gb/reports/stats.jsonl").write_text("")
    return old


def test_old_layout_prints_mv_commands(tmp_path):
    from perch.core.doctor import old_layout_checks

    home = build_home(tmp_path)
    old = old_workspace(tmp_path)
    (check,) = old_layout_checks(old / "projects", home)
    new = home.projects_dir / "apollo"
    assert not check.ok and f"old workspace at {old.resolve()}" in check.what
    lines = check.fix.split("\n")
    assert f"mkdir -p {new}/board" in lines
    assert f"mv {old.resolve()}/projects/apollo/* {new}/" in lines
    assert f"mv {old.resolve()}/budget/fy26 {new}/budget" in lines
    assert (
        f"mv {old.resolve()}/gb/boards/apollo-api.yaml.base.old "
        f"{new}/board/apollo.yaml.base.old"
    ) in lines
    assert f"cp {old.resolve()}/gb/snapshots.jsonl {new}/board/snapshots.jsonl" in lines
    assert f"cp {old.resolve()}/gb/reports/stats.jsonl {new}/board/stats.jsonl" in lines
    assert "board_dump: board/dump.json" in check.fix


def test_old_layout_existing_destination_is_named_not_moved(tmp_path):
    from perch.core.doctor import old_layout_checks

    home = build_home(tmp_path, "apollo")
    old = old_workspace(tmp_path)
    (home.board_dir("apollo")).mkdir(parents=True)
    (home.board_dir("apollo") / "apollo.yaml").write_text("")
    (check,) = old_layout_checks(old, home)
    assert f"# {home.board_dir('apollo') / 'apollo.yaml'} already exists" in check.fix
    assert not any(
        line.startswith("mv") and line.endswith("board/apollo.yaml")
        for line in check.fix.split("\n")
    )
    assert "perch.yaml already exists" in check.fix
    assert f"mv {old.resolve()}/projects/apollo/*" not in check.fix


def test_no_old_layout_no_check(tmp_path):
    from perch.core.doctor import old_layout_checks

    home = build_home(tmp_path)
    assert old_layout_checks(tmp_path, home) == []
