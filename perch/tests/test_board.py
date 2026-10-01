import json
from datetime import date

import pytest

from perch.core.board import load_board


def test_open_and_closed_issues(world):
    board = load_board(world.parent / "dump.json")
    assert (board.project, board.name) == ("grp/proj", "Dev")
    assert board.fetched_on == date(2026, 4, 20)
    assert len(board.closed) == 13
    assert [i.iid for i in board.open] == [101, 102, 103, 104, 105, 106, 107]
    assert board.closed[0].closed_on == date(2026, 1, 10)


def _dump(tmp_path, record):
    path = tmp_path / "d.json"
    base = {"iid": 1, "title": "t", "assignee": None, "labels": [], "transitions": []}
    path.write_text(
        json.dumps({"fetched_at": "2026-04-20T08:00:00Z", "history": [base | record]})
    )
    return load_board(path).issues[0]


def test_type_is_the_first_type_label(tmp_path):
    issue = _dump(tmp_path, {"labels": ["type::feature", "epic::x", "type::bug"]})
    assert issue.type == "bug"  # sorted, the way gitboard reads scoped labels
    assert _dump(tmp_path, {"labels": ["epic::x"]}).type == "untyped"


def test_an_issue_moved_into_done_counts_as_finished(tmp_path):
    # gitboard treats Done as finished even if nobody closed the issue.
    moves = [
        ["2026-02-01T09:00:00Z", "add", "Doing"],
        ["2026-02-03T09:00:00Z", "add", "Done"],
    ]
    assert _dump(tmp_path, {"transitions": moves}).closed_on == date(2026, 2, 3)


def test_a_file_that_is_not_a_dump_is_refused(tmp_path):
    path = tmp_path / "d.json"
    path.write_text('{"issues": []}')
    with pytest.raises(ValueError, match="stats --dump"):
        load_board(path)


def test_transitions_are_kept_as_dated_moves(world):
    board = load_board(world.parent / "dump.json")
    eight = next(i for i in board.issues if i.iid == 8)
    assert eight.transitions == (
        (date(2026, 4, 8), "add", "Done"),
        (date(2026, 4, 9), "remove", "Done"),
    )
    assert eight.closed_on == date(2026, 4, 10)  # closed_at still wins
