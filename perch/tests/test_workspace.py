import pytest

from perch.core.config import load_config
from perch.core.workspace import (
    WorkspaceError,
    create_home,
    find_home,
    load_home,
)


def make_home(tmp_path, *projects):
    home = create_home(tmp_path / "ws", tmp_path / "gb")
    for name in projects:
        home.scaffold(name)
    return home


def test_found_by_walking_up_from_a_subfolder(tmp_path):
    home = make_home(tmp_path, "apollo")
    deep = home.projects_dir / "apollo" / "weekly"
    deep.mkdir(parents=True)
    assert find_home(deep, {}).root == home.root


def test_perch_home_is_the_fallback(tmp_path):
    home = make_home(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert find_home(elsewhere, {"PERCH_HOME": str(home.root)}).root == home.root


def test_no_workspace_says_what_to_run(tmp_path):
    with pytest.raises(WorkspaceError, match="perch init"):
        find_home(tmp_path, {})


def test_perch_home_pointing_nowhere_says_so(tmp_path):
    with pytest.raises(WorkspaceError, match="PERCH_HOME"):
        find_home(tmp_path, {"PERCH_HOME": str(tmp_path / "nope")})


def test_gitboard_dir_takes_tilde_and_relative_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    marker = tmp_path / "perch-home.yaml"
    marker.write_text("gitboard_dir: ~/gb\n")
    assert load_home(marker).gitboard_dir == (tmp_path / "gb").resolve()
    marker.write_text("gitboard_dir: ../gb\n")
    assert load_home(marker).gitboard_dir == (tmp_path.parent / "gb").resolve()


@pytest.mark.parametrize(
    ("text", "says"),
    [
        ("gitboard_dir: x\ngitlab: y\n", "gitlab"),
        ("{}\n", "`gitboard_dir` is required"),
        ("- a\n", "mapping"),
    ],
)
def test_a_bad_home_file_names_the_problem(tmp_path, text, says):
    (tmp_path / "perch-home.yaml").write_text(text)
    with pytest.raises(WorkspaceError, match=says):
        load_home(tmp_path / "perch-home.yaml")


def test_one_project_needs_no_name(tmp_path):
    assert make_home(tmp_path, "apollo").select(None) == "apollo"


def test_several_projects_need_a_name(tmp_path):
    home = make_home(tmp_path, "gemini", "apollo")
    with pytest.raises(WorkspaceError, match="several projects: apollo, gemini"):
        home.select(None)
    assert home.select("gemini") == "gemini"


def test_an_unknown_name_lists_the_known_ones(tmp_path):
    with pytest.raises(WorkspaceError, match="Known: apollo"):
        make_home(tmp_path, "apollo").select("apolo")


def test_no_projects_says_init(tmp_path):
    with pytest.raises(WorkspaceError, match="perch init"):
        make_home(tmp_path).select(None)


def test_folders_without_perch_yaml_are_not_projects(tmp_path):
    home = make_home(tmp_path, "apollo")
    (home.projects_dir / "notes").mkdir()
    assert home.projects() == ["apollo"]


def test_scaffold_points_at_budget_name_and_never_overwrites(tmp_path):
    home = make_home(tmp_path)
    path = home.scaffold("apollo")
    (home.budget_dir("apollo")).mkdir(parents=True)
    (home.budget_dir("apollo") / "budgie.yaml").write_text("year: 2026\n")
    config = load_config(path, require_dump=False)
    assert config.budgie_project == home.root / "budget" / "apollo"
    assert config.board_dump == home.projects_dir / "apollo" / "dumps" / "board.json"
    assert config.gitlab_project is None and config.people == {}
    with pytest.raises(FileExistsError, match="edit it instead"):
        home.scaffold("apollo")


@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".hidden", "a b"])
def test_project_names_cannot_escape_projects(tmp_path, bad):
    with pytest.raises(WorkspaceError, match="not a project name"):
        make_home(tmp_path).scaffold(bad)


def test_broken_home_yaml_is_a_workspace_error(tmp_path):
    bad = tmp_path / "perch-home.yaml"
    bad.write_text("gitboard_dir: [unclosed\n")
    with pytest.raises(WorkspaceError, match="not valid YAML"):
        load_home(bad)


def test_gitboard_dir_with_colon_space_round_trips(tmp_path):
    odd = tmp_path / "a: b #c"
    home = create_home(tmp_path / "ws", odd)
    assert home.gitboard_dir == odd.resolve()


def test_standing_in_a_project_folder_picks_it(tmp_path):
    home = make_home(tmp_path, "apollo", "gemini")
    deep = home.projects_dir / "gemini" / "weekly"
    deep.mkdir(parents=True)
    assert home.select(None, here=deep) == "gemini"
    assert home.select("apollo", here=deep) == "apollo"  # -p still wins
    with pytest.raises(WorkspaceError, match="several projects"):
        home.select(None, here=home.root)


def test_alerts_are_stored_raw_and_validated_on_demand(tmp_path):
    home = make_home(tmp_path, "apollo")
    assert home.alerts() == ()
    path = home.root / "perch-home.yaml"
    path.write_text(
        path.read_text()
        + "alerts:\n  - when: headroom < 50k\n    project: apollo\n  - when: pace < 80%\n"
    )
    loaded = load_home(path)
    assert [(r.figure, r.value, r.project) for r in loaded.alerts()] == [
        ("headroom", 50000, "apollo"),
        ("pace", 0.8, None),
    ]
    assert loaded == home  # alerts_raw is not part of equality


def test_a_bad_alerts_value_loads_but_alerts_raises(tmp_path):
    home = make_home(tmp_path, "apollo")
    path = home.root / "perch-home.yaml"
    path.write_text(path.read_text() + "alerts:\n  - when: bogus\n")
    with pytest.raises(ValueError, match=r"alerts\[0\]\.when"):
        load_home(path).alerts()
