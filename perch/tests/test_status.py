"""status(): one cell per Monday step, from files on disk. today = Mon 2026-04-20 (W17).

The world's last weekly.csv reading is week 16, dated Sunday 2026-04-19, so
hours is done on 04-20 and todo a week later.
"""

# ruff: noqa: DTZ001  (naive local datetimes: the cutoff is local, like mtimes)
import json
import os
from datetime import date, datetime

from perch.core import status as st
from perch.core.history import record
from perch.tests.conftest import build_home

TODAY = date(2026, 4, 20)
OLD, MON, NEW, NEWER = (
    datetime(2026, 4, 17, 9),
    datetime(2026, 4, 20, 8),
    datetime(2026, 4, 21, 9),
    datetime(2026, 4, 22, 9),
)
TEAM = [{"kind": "team", "name": "team"}]


def touch(path, when):
    """Make the file (or the emails directory) and set its mtime."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.mkdir() if not path.suffix else path.write_text("x")
    os.utime(path, (when.timestamp(), when.timestamp()))


def setup(tmp_path):
    home = build_home(tmp_path, "apollo")
    project = home.projects_dir / "apollo"
    touch(project / "dump.json", OLD)  # the world was just written; age its inputs
    touch(project / "fy26" / "weekly.csv", OLD)
    return (
        home,
        project,
        project / "fy26" / "emails",
        tmp_path / "gb" / "reports" / "apollo",
    )


def states(home, today=TODAY):
    return {k: c.state for k, c in st.status(home, "apollo", today).items()}


def test_fresh_project_only_hours_is_done(tmp_path):
    home, *_ = setup(tmp_path)
    cells = st.status(home, "apollo", TODAY)
    assert list(cells) == list(st.STEPS)
    assert states(home) == dict.fromkeys(st.STEPS, "todo") | {"hours": "done"}
    assert cells["weekly"].when == "never"


def test_hours_needs_last_sundays_reading(tmp_path):
    home, *_ = setup(tmp_path)
    assert states(home, date(2026, 4, 27))["hours"] == "todo"


def test_fetch_and_emails_by_mtime(tmp_path):
    home, p, emails, _ = setup(tmp_path)
    touch(p / "dump.json", OLD)
    touch(emails, OLD)
    assert states(home)["fetch"] == states(home)["emails"] == "todo"
    touch(p / "dump.json", NEW)
    touch(emails, NEW)
    assert states(home)["fetch"] == states(home)["emails"] == "done"


def test_board_weekly_watch_digest_done(tmp_path):
    home, p, _, reports = setup(tmp_path)
    record(p / "history.jsonl", date(2026, 4, 13), TEAM)
    assert states(home)["board"] == "todo"  # last week's rows
    record(p / "history.jsonl", TODAY, TEAM)
    touch(p / "history.jsonl", NEW)
    touch(p / "weekly" / "2026-W17.md", NEW)
    touch(p / "watch" / "2026-W17.md", NEW)
    touch(reports / "2026-04-13", OLD)
    assert states(home)["digest"] == "todo"  # last week's folder
    touch(reports / "2026-04-20", NEW)
    (reports / "notes").mkdir()  # not a date: ignored
    s = states(home)
    assert (s["board"], s["weekly"], s["watch"], s["digest"]) == ("done",) * 4


def test_stale_when_an_input_is_newer(tmp_path):
    home, p, emails, reports = setup(tmp_path)
    record(p / "history.jsonl", TODAY, TEAM)
    touch(p / "history.jsonl", NEW)
    touch(p / "weekly" / "2026-W17.md", OLD)
    touch(p / "watch" / "2026-W17.md", OLD)
    touch(p / "dump.json", NEW)
    touch(emails, NEW)
    touch(reports / "2026-04-20", MON)
    s = states(home)
    assert s["weekly"] == s["watch"] == s["digest"] == "stale"
    assert s["board"] == s["emails"] == "done"
    touch(p / "dump.json", NEWER)  # newer than history
    touch(p / "fy26" / "weekly.csv", NEWER)  # newer than the emails dir
    s = states(home)
    assert s["board"] == s["emails"] == "stale" and s["fetch"] == "done"


def test_failure_record_marks_the_step_failed(tmp_path):
    home, p, *_ = setup(tmp_path)
    st.record_failure(home, "apollo", "2026-W17", "fetch", 2, NEW)
    assert st.failure_path(home, "apollo") == p / "monday.json"
    cell = st.status(home, "apollo", TODAY)["fetch"]
    assert (cell.state, cell.why) == ("failed", "fetch exited 2")
    touch(p / "dump.json", NEWER)  # later output clears it
    assert states(home)["fetch"] == "done"


def test_failure_record_for_last_week_or_garbage_is_ignored(tmp_path):
    home, *_ = setup(tmp_path)
    st.record_failure(home, "apollo", "2026-W16", "fetch", 2, NEW)
    assert states(home)["fetch"] == "todo"
    st.failure_path(home, "apollo").write_text("{not json")
    assert states(home)["fetch"] == "todo"


def test_record_clear_round_trip(tmp_path):
    home, *_ = setup(tmp_path)
    st.clear_failure(home, "apollo")  # missing file is fine
    st.record_failure(home, "apollo", "2026-W17", "board", 1, NEW)
    data = json.loads(st.failure_path(home, "apollo").read_text())
    assert data == {
        "week": "2026-W17",
        "step": "board",
        "code": 1,
        "at": NEW.isoformat(),
    }
    st.clear_failure(home, "apollo")
    assert not st.failure_path(home, "apollo").exists()


def test_broken_config_is_error_cells_not_a_raise(tmp_path):
    home, p, *_ = setup(tmp_path)
    (p / "perch.yaml").write_text("nonsense: 1\n")
    cells = st.status(home, "apollo", TODAY)
    assert {c.state for c in cells.values()} == {"error"}
    assert "unknown keys" in cells["hours"].why


def test_next_step_and_command():
    done, todo = st.Cell("done", "x"), st.Cell("todo", "never")
    cells = dict.fromkeys(st.STEPS, done)
    assert st.next_step(cells) is None
    assert st.next_step(cells | {"digest": todo, "watch": todo}) == "digest"
    assert st.next_command("a", "hours") == ["hours", "-p", "a"]
    assert st.next_command("a", "watch") == ["watch", "-p", "a"]
    assert st.next_command("a", "weekly") == ["monday", "-p", "a", "--from", "weekly"]


def test_a_directory_is_as_new_as_its_newest_file(tmp_path):
    """Budgie rewrites the same .eml names weekly; the directory mtime stays put."""
    home, _, emails, reports = setup(tmp_path)
    touch(emails / "ann.eml", NEW)
    touch(reports / "2026-04-20" / "apollo" / "team.md", NEW)
    os.utime(emails, (OLD.timestamp(), OLD.timestamp()))
    os.utime(reports / "2026-04-20", (OLD.timestamp(),) * 2)
    s = states(home)
    assert s["emails"] == "done" and s["digest"] == "done"


def test_digest_is_this_weeks_by_when_written_not_by_folder_name(tmp_path):
    """gitboard names the folder by the UTC day: a Sunday-evening run in UTC-6
    lands in Monday's folder but was written last week."""
    home, _, _, reports = setup(tmp_path)
    touch(reports / "2026-04-20", datetime(2026, 4, 19, 20))
    assert states(home)["digest"] == "todo"


def test_clear_failure_keeps_a_record_the_run_did_not_reach(tmp_path):
    home, *_ = setup(tmp_path)
    st.record_failure(home, "apollo", "2026-W17", "fetch", 2, NEW)
    st.clear_failure(home, "apollo", ("weekly", "digest", "emails"))
    assert st.failure_path(home, "apollo").exists()
    st.clear_failure(home, "apollo", ("fetch", "board"))
    assert not st.failure_path(home, "apollo").exists()
