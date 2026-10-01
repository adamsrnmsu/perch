import email
from email import policy

from click.testing import CliRunner

from perch.cli import cli
from perch.tests.conftest import build_home


def run(*args):
    return CliRunner().invoke(cli, list(args))


def test_quarterly_writes_the_project_s_draft_and_markdown(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.root)
    result = run("quarterly", "-p", "gemini", "--quarter", "2026-Q1")
    assert result.exit_code == 0, result.output
    folder = home.projects_dir / "gemini" / "quarterly"
    for path in (folder / "2026-Q1.eml", folder / "2026-Q1.md"):
        assert path.is_file() and f"Wrote {path}" in result.output
    draft = email.message_from_bytes(
        (folder / "2026-Q1.eml").read_bytes(), policy=policy.default
    )
    assert draft["Subject"].startswith(
        "gemini, 2026-Q1: $22,607 labor spent of $100,000"
    )
    assert not (home.projects_dir / "apollo" / "quarterly").exists()


def test_a_quarter_outside_the_year_is_an_error(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    result = run("quarterly", "--quarter", "2025-Q4")
    assert result.exit_code != 0 and "year, 2026" in result.output


def test_all_carries_on_past_a_broken_project(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "broken", "gemini")
    (home.projects_dir / "broken" / "dump.json").write_text("not json")
    monkeypatch.chdir(home.root)
    out = tmp_path / "out"
    result = run("quarterly", "--all", "--quarter", "2026-Q1", "--out", str(out))
    assert result.exit_code == 1, result.output
    assert (out / "apollo" / "2026-Q1.eml").is_file()
    assert (out / "gemini" / "2026-Q1.md").is_file()
    assert "broken FAILED" in result.output and "gemini ok" in result.output
