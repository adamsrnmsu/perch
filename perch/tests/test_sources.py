"""Sources: one load of everything a project's files say."""

import os
import time
from datetime import date

from perch.core import sources
from perch.tests.conftest import build_home


def _home(tmp_path):
    return build_home(tmp_path, "apollo")


def test_load_reads_every_source(tmp_path):
    src = sources.load(_home(tmp_path), "apollo")
    assert src.errors == () and src.rows == [] and src.failure is None
    assert src.money.as_of == date(2026, 4, 19)
    assert src.board.fetched_on == date(2026, 4, 20)
    assert src.config.gitlab_project == "grp/apollo"


def test_a_missing_dump_is_no_board_and_no_error(tmp_path):
    home = _home(tmp_path)
    (home.projects_dir / "apollo" / "dump.json").unlink()
    src = sources.load(home, "apollo")
    assert src.board is None and src.errors == () and src.money is not None


def test_a_corrupt_failure_file_is_one_error_and_the_rest_load(
    tmp_path,
):  # review-focus 2
    home = _home(tmp_path)
    (home.projects_dir / "apollo" / "monday.json").write_text("{")
    src = sources.load(home, "apollo")
    assert src.errors == ("monday.json",) and src.failure is None
    assert src.money is not None and src.board is not None
    assert (
        sources.unreadable("monday.json") == "monday.json unreadable, run perch doctor"
    )


def test_a_failing_budgie_load_is_named_not_raised(
    tmp_path, monkeypatch
):  # review-focus 2
    def boom(path):
        raise ValueError("people.csv: row 3: Alice is not a number")

    monkeypatch.setattr(sources, "load_money", boom)
    src = sources.load(_home(tmp_path), "apollo")
    assert src.money is None and src.errors == ("budgie",) and src.board is not None
    assert "Alice" not in repr(src.errors)  # the exception text is never kept


def test_a_failure_record_is_read(tmp_path):
    home = _home(tmp_path)
    (home.projects_dir / "apollo" / "monday.json").write_text(
        '{"week": "2026-W17", "step": "board", "code": 2, "at": "2026-04-19T09:00:00"}'
    )
    assert sources.load(home, "apollo").failure["step"] == "board"


def test_stamp_moves_when_an_input_changes(tmp_path):
    home = _home(tmp_path)
    before = sources.stamp(home, "apollo")
    later = time.time() + 1000
    path = home.projects_dir / "apollo" / "history.jsonl"
    path.write_text("")
    os.utime(path, (later, later))
    assert sources.stamp(home, "apollo") == later > before
