"""One load of everything a project's files say, for the slow tier.

The pane, the tape and the events calendar all read config, history, the
Budgie project, the board dump and the failure record. Money costs about 0.4 s
cold, so it is read once here and shared. Each source is read on its own: one
that fails is named in `errors` and the rest still load. The exception text is
never kept, since a loader's message is built from file contents.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from perch.core import history
from perch.core.board import Board, load_board
from perch.core.config import Config, load_config
from perch.core.money import Money, load_money
from perch.core.status import failure_path
from perch.core.workspace import Home


@dataclass(frozen=True)
class Sources:
    config: Config | None = None
    rows: list[dict] = field(default_factory=list)
    money: Money | None = None
    board: Board | None = None
    failure: dict | None = None
    errors: tuple[str, ...] = ()  # names of the sources that would not read


def unreadable(source: str) -> str:
    """The one line a consumer shows for a source that would not read."""
    return f"{source} unreadable, run perch doctor"


def _failure(path: Path) -> dict:
    got = json.loads(path.read_text())
    if not isinstance(got, dict):
        raise TypeError("not a record")
    return got


def load(home: Home, name: str) -> Sources:
    try:
        config = load_config(home.config_path(name), require_dump=False)
    except Exception:  # noqa: BLE001 -- a display boundary: name it, never crash
        return Sources(errors=("perch.yaml",))
    errors: list[str] = []

    def got(source: str, read, default=None):
        try:
            return read()
        except Exception:  # noqa: BLE001 -- as above: one bad source, the rest read
            errors.append(source)
            return default

    rows = got("history", lambda: history.load(config.history), [])
    money = got("budgie", lambda: load_money(config.budgie_project))
    board = (
        got("board", lambda: load_board(config.board_dump))
        if config.board_dump.is_file()
        else None
    )
    path = failure_path(home, name)
    failure = got("monday.json", lambda: _failure(path)) if path.is_file() else None
    return Sources(config, rows, money, board, failure, tuple(errors))


def stamp(home: Home, name: str) -> float:
    """The newest mtime among the files `load` reads (stat calls only), so the
    slow tier can skip a project nothing has touched. -1 when the config will not read."""
    try:
        config = load_config(home.config_path(name), require_dump=False)
    except Exception:  # noqa: BLE001
        return -1.0
    files = [
        p
        for p in (
            home.config_path(name),
            config.history,
            config.board_dump,
            failure_path(home, name),
        )
        if p.is_file()
    ]
    if config.budgie_project.is_dir():
        files += [p for p in config.budgie_project.rglob("*") if p.is_file()]
    return max((p.stat().st_mtime for p in files), default=0.0)
