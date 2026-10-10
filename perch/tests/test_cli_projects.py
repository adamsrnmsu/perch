import pytest
from click.testing import CliRunner

from perch.cli import cli
from perch.core.config import load_config
from perch.tests.conftest import build_home


def run(*args):
    return CliRunner().invoke(cli, list(args))


def test_board_uses_the_only_project(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.projects_dir / "apollo")  # a subfolder finds the workspace
    result = run("board", "--no-history")
    assert result.exit_code == 0, result.output
    assert "Alice" in result.output


def test_several_projects_need_p(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.root)
    result = run("weekly")
    assert result.exit_code != 0
    assert "several projects: apollo, gemini. Pass -p <name>." in result.output
    assert run("weekly", "-p", "gemini").exit_code == 0


def test_config_wins_over_p(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.root)
    config = str(home.config_path("gemini"))
    result = run("board", "--no-history", "-p", "nope", "--config", config)
    assert result.exit_code == 0, result.output


def test_outside_a_workspace_a_perch_yaml_here_still_works(world, monkeypatch):
    monkeypatch.chdir(world.parent)
    assert run("board", "--no-history").exit_code == 0


def test_outside_a_workspace_with_no_perch_yaml_says_how_to_start(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    result = run("board")
    assert result.exit_code != 0 and "perch init" in result.output


def test_projects_lists_each_with_its_gitlab_project(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    gemini = home.config_path("gemini")
    gemini.write_text(gemini.read_text().replace("gitlab_project: grp/gemini\n", ""))
    monkeypatch.chdir(home.root)
    result = run("projects")
    assert result.exit_code == 0, result.output
    assert "apollo" in result.output and "grp/apollo" in result.output
    assert "gemini" in result.output and "not set" in result.output


def fake_budgie_init(monkeypatch):
    ran = []

    def fake(step):
        ran.append((step.argv[1:], step.cwd))
        step.cwd.mkdir(parents=True, exist_ok=True)
        (step.cwd / "budgie.yaml").write_text("year: 2026\n")

    monkeypatch.setattr("perch.cli._run", fake)
    return ran


def test_init_runs_budgie_init_here_and_writes_perch_yaml(tmp_path, monkeypatch):
    home = build_home(tmp_path)
    monkeypatch.chdir(home.root)
    ran = fake_budgie_init(monkeypatch)
    result = run("init", "apollo")
    assert result.exit_code == 0, result.output
    assert ran == [(("init", "--here"), home.budget_dir("apollo"))]
    config = load_config(home.config_path("apollo"), require_dump=False)
    assert config.budgie_project == home.budget_dir("apollo").resolve()
    assert config.board_dump == home.projects_dir.resolve() / "apollo/board/dump.json"
    assert (
        "gitlab_project" in result.output and "perch doctor -p apollo" in result.output
    )
    assert not (home.root / ".claude").exists()


def test_init_passes_year_and_year_start_to_budgie(tmp_path, monkeypatch):
    home = build_home(tmp_path)
    monkeypatch.chdir(home.root)
    ran = fake_budgie_init(monkeypatch)
    result = run("init", "fed", "--year", "2027", "--year-start", "10-01")
    assert result.exit_code == 0, result.output
    assert ran[0][0] == ("init", "--here", "--year", "2027", "--year-start", "10-01")


def test_init_skips_budgie_init_when_the_budgie_project_exists(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    (home.budget_dir("gemini")).mkdir(parents=True)
    (home.budget_dir("gemini") / "budgie.yaml").write_text("year: 2026\n")
    monkeypatch.chdir(home.root)
    monkeypatch.setattr("perch.cli._run", lambda step: pytest.fail(f"ran {step.name}"))
    assert run("init", "gemini").exit_code == 0
    assert home.config_path("gemini").is_file()


def test_init_refuses_to_overwrite_and_runs_nothing(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    monkeypatch.setattr("perch.cli._run", lambda step: pytest.fail(f"ran {step.name}"))
    result = run("init", "apollo")
    assert result.exit_code != 0 and "exists" in result.output


def test_init_rejects_a_name_that_escapes(tmp_path, monkeypatch):
    home = build_home(tmp_path)
    monkeypatch.chdir(home.root)
    result = run("init", "../x")
    assert result.exit_code != 0 and "not a project name" in result.output
    assert not (home.root.parent / "x").exists()


def test_a_local_perch_yaml_beats_the_checkouts_projects(world, tmp_path, monkeypatch):
    build_home(tmp_path / "other", "apollo", "gemini")
    monkeypatch.chdir(world.parent)
    result = run("board", "--no-history")
    assert result.exit_code == 0, result.output  # not "several projects"


def test_inside_a_project_folder_that_project_is_used(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    deep = home.projects_dir / "gemini" / "weekly"
    deep.mkdir()
    monkeypatch.chdir(deep)
    result = run("weekly")
    assert result.exit_code == 0, result.output
