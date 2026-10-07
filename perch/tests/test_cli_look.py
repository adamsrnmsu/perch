"""perch detail, events, tape and alerts end to end (numbers: conftest's world)."""

from datetime import datetime

from click.testing import CliRunner

from perch.cli import cli
from perch.core.history import record
from perch.tests.conftest import build_home

TODAY = datetime.now().date()  # noqa: DTZ005


def run(home, *args):
    return CliRunner().invoke(cli, [*args], env={"PERCH_HOME": str(home.root)})


def test_detail_prints_the_burn_table(tmp_path):
    home = build_home(tmp_path, "apollo")
    result = run(home, "detail", "-p", "apollo")
    assert result.exit_code == 0, result.output
    assert "Detail · apollo" in result.output
    assert "Labor only" in result.output


def test_events_all_and_p_are_exclusive(tmp_path):
    home = build_home(tmp_path, "apollo")
    result = run(home, "events", "-p", "apollo", "--all")
    assert result.exit_code == 2
    assert "not both" in result.output


def test_events_lists_a_table_or_says_nothing(tmp_path):
    home = build_home(tmp_path, "apollo")
    result = run(home, "events", "-p", "apollo", "--days", "366")
    assert result.exit_code == 0, result.output
    assert "Events," in result.output or "nothing in the next 366 days" in result.output


def test_events_unknown_project(tmp_path):
    home = build_home(tmp_path, "apollo")
    result = run(home, "events", "-p", "nope")
    assert result.exit_code == 1 and "no project 'nope'" in result.output


def test_tape_shows_a_failed_step(tmp_path):
    home = build_home(tmp_path, "apollo")
    p = home.projects_dir / "apollo"
    (p / "monday.json").write_text(
        f'{{"step": "board", "code": 2, "at": "{TODAY.isoformat()}T08:00:00"}}'
    )
    result = run(home, "tape", "--days", "7")
    assert result.exit_code == 0, result.output
    assert "Tape · last 7 days, from files only" in result.output
    assert "apollo" in result.output


def test_alerts_with_no_rules_is_quiet(tmp_path):
    home = build_home(tmp_path, "apollo")
    result = run(home, "alerts")
    assert result.exit_code == 0, result.output


def test_alerts_lists_a_rule_and_its_state(tmp_path):
    home = build_home(tmp_path, "apollo")
    path = home.root / "perch-home.yaml"
    path.write_text(path.read_text() + "alerts:\n  - when: headroom < 50k\n")
    record(
        home.projects_dir / "apollo" / "history.jsonl",
        TODAY,
        [{"kind": "team", "name": "team", "headroom": 42000}],
    )
    result = run(home, "alerts", "-p", "apollo")
    assert result.exit_code == 0, result.output
    assert "headroom < 50k" in result.output


def test_a_bad_alert_rule_names_its_key(tmp_path):
    home = build_home(tmp_path, "apollo")
    path = home.root / "perch-home.yaml"
    path.write_text(path.read_text() + "alerts:\n  - when: pace < 80\n")
    result = run(home, "alerts")
    assert result.exit_code == 1 and "alerts[0].when" in result.output
    doc = run(home, "doctor", "-p", "apollo")
    assert "Alerts" in doc.output and "alerts[0].when" in doc.output


def test_help_lists_the_new_commands():
    out = CliRunner().invoke(cli, ["--help"]).output
    for name in ("detail", "events", "tape", "alerts"):
        assert name in out


def test_events_prints_a_span_note_once(tmp_path):
    home = build_home(tmp_path, "apollo")
    result = run(home, "events", "-p", "apollo", "--days", "366")
    assert result.output.count("roll the Budgie year") == 1


def test_page_writes_one_html_file_and_records_nothing(tmp_path):
    home = build_home(tmp_path, "apollo")
    folder = home.projects_dir / "apollo"
    result = run(home, "page", "-p", "apollo")
    assert result.exit_code == 0, result.output
    page = (folder / "page.html").read_text()
    for expected in (
        "The open board",
        "$100,000",
        "MODELLED",
        "2.08x",
        "Detail · apollo",
    ):
        assert expected in page
    assert "<h2>History</h2>" not in page  # no week recorded yet
    assert not (folder / "history.jsonl").exists()

    assert run(home, "board", "-p", "apollo").exit_code == 0
    out = tmp_path / "lead.html"
    assert run(home, "page", "-p", "apollo", "--out", str(out)).exit_code == 0
    assert "<td>2026-W17</td><td>GOOD</td>" in out.read_text()


def test_page_without_a_board_dump_shows_the_budget_only(tmp_path):
    home = build_home(tmp_path, "apollo")
    folder = home.projects_dir / "apollo"
    (folder / "dump.json").unlink()
    result = run(home, "page", "-p", "apollo")
    assert result.exit_code == 0, result.output
    page = (folder / "page.html").read_text()
    assert "Detail · apollo" in page and "no board dump yet" in page
    assert "The open board" not in page and "Accuracy" not in page
