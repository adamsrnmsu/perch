import pytest

from perch.core.config import load_config
from perch.core.workspace import WorkspaceError, checkout_home


def make_checkout(root):
    (root / "pyproject.toml").write_text("")
    (root / "apps" / "remote-gitboard").mkdir(parents=True)
    (root / "projects").mkdir()
    return checkout_home(root)


def make_home(tmp_path, *projects):
    home = make_checkout(tmp_path)
    for name in projects:
        home.scaffold(name)
    return home


def test_home_is_the_checkout(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "apps").mkdir()
    assert checkout_home(tmp_path).root == tmp_path


def test_home_without_pyproject_names_make_install(tmp_path):
    with pytest.raises(
        WorkspaceError,
        match="perch is not running from a checkout: run make install in your perch clone",
    ):
        checkout_home(tmp_path)


def test_config_yaml_lead_and_alerts_load(tmp_path):
    make_checkout(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "lead: Ryan Adams\nalerts:\n  - when: pace < 0.8\n"
    )
    home = checkout_home(tmp_path)
    assert home.lead == "Ryan Adams" and len(home.alerts()) == 1


def test_no_config_yaml_is_fine(tmp_path):
    home = make_checkout(tmp_path)
    assert home.lead is None and home.alerts() == ()


def test_config_yaml_unknown_key_names_it(tmp_path):
    make_checkout(tmp_path)
    (tmp_path / "config.yaml").write_text("gitboard_dir: /x\n")
    with pytest.raises(WorkspaceError, match="gitboard_dir"):
        checkout_home(tmp_path)


@pytest.mark.parametrize("text", ["lead: 5\n", "lead:\n", 'lead: ""\n'])
def test_config_yaml_lead_must_be_text(tmp_path, text):
    make_checkout(tmp_path)
    (tmp_path / "config.yaml").write_text(text)
    with pytest.raises(WorkspaceError, match="lead"):
        checkout_home(tmp_path)


@pytest.mark.parametrize(
    ("text", "says"), [("[unclosed\n", "not valid YAML"), ("- a\n", "mapping")]
)
def test_a_bad_config_yaml_names_the_problem(tmp_path, text, says):
    make_checkout(tmp_path)
    (tmp_path / "config.yaml").write_text(text)
    with pytest.raises(WorkspaceError, match=says):
        checkout_home(tmp_path)


def test_project_paths_live_under_projects(tmp_path):
    home = make_checkout(tmp_path)
    p = tmp_path / "projects" / "apollo"
    assert home.reports_dir("apollo") == p / "reports"
    assert home.budget_dir("apollo") == p / "budget"
    assert home.gitboard_dir == tmp_path / "apps" / "remote-gitboard"


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


def test_scaffold_points_at_its_budget_and_never_overwrites(tmp_path):
    home = make_home(tmp_path)
    path = home.scaffold("apollo")
    home.budget_dir("apollo").mkdir()
    (home.budget_dir("apollo") / "budgie.yaml").write_text("year: 2026\n")
    config = load_config(path, require_dump=False)
    assert config.budgie_project == home.budget_dir("apollo")
    assert config.board_dump == home.projects_dir / "apollo" / "board" / "dump.json"
    assert config.gitlab_project is None and config.people == {}
    with pytest.raises(FileExistsError, match="edit it instead"):
        home.scaffold("apollo")


@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".hidden", "a b"])
def test_project_names_cannot_escape_projects(tmp_path, bad):
    with pytest.raises(WorkspaceError, match="not a project name"):
        make_home(tmp_path).scaffold(bad)


def test_standing_in_a_project_folder_picks_it(tmp_path):
    home = make_home(tmp_path, "apollo", "gemini")
    deep = home.projects_dir / "gemini" / "weekly"
    deep.mkdir(parents=True)
    assert home.select(None, here=deep) == "gemini"
    assert home.select("apollo", here=deep) == "apollo"  # -p still wins
    with pytest.raises(WorkspaceError, match="several projects"):
        home.select(None, here=home.root)


def test_a_bad_alerts_value_loads_but_alerts_raises(tmp_path):
    make_checkout(tmp_path)
    (tmp_path / "config.yaml").write_text("alerts:\n  - when: bogus\n")
    with pytest.raises(ValueError, match=r"alerts\[0\]\.when"):
        checkout_home(tmp_path).alerts()
