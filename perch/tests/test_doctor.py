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


def test_tool_checks_name_the_tool_that_does_not_run(tmp_path):
    home = build_home(tmp_path)
    home.gitboard_dir.mkdir()
    checks = tool_checks(tmp_path, home, lambda argv, cwd, env: "budgie" not in argv[0])
    assert [c.what for c in checks if not c.ok] == ["budgie does not run"]


def test_a_missing_gitboard_dir_points_at_perch_home(tmp_path):
    home = build_home(tmp_path)
    failed = [c for c in tool_checks(tmp_path, home, lambda *a: True) if not c.ok]
    assert len(failed) == 1 and "perch-home.yaml" in failed[0].fix
