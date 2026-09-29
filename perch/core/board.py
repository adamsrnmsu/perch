"""The gitboard side: a `gitboard stats --dump` file as plain dataclasses.

Read-only, and the only thing perch knows about GitLab. The dump's shape is
gitboard's `board.fetch_history`; perch reads the few fields it needs and
ignores the rest, so gitboard can add fields without breaking this.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

DONE = "Done"  # gitboard's name for the finished column
BLOCKED = "Blocked"  # ...and for the column that means waiting on someone
TYPE_SCOPE = "type::"
UNTYPED = "untyped"


@dataclass(frozen=True)
class Issue:
    iid: int
    title: str
    assignee: str | None  # GitLab username
    labels: tuple[str, ...]
    closed_on: date | None
    blocked_since: date | None = None  # last move into Blocked, if it is there

    @property
    def is_blocked(self) -> bool:
        return self.is_open and BLOCKED in self.labels

    @property
    def is_open(self) -> bool:
        return self.closed_on is None

    @property
    def type(self) -> str:
        """The first `type::x` label's value, the way gitboard reads it."""
        kinds = sorted(
            label[len(TYPE_SCOPE) :]
            for label in self.labels
            if label.startswith(TYPE_SCOPE)
        )
        return kinds[0] if kinds else UNTYPED


@dataclass(frozen=True)
class Board:
    project: str
    name: str
    fetched_on: date
    issues: tuple[Issue, ...]

    @property
    def open(self) -> list[Issue]:
        return [i for i in self.issues if i.is_open]

    @property
    def closed(self) -> list[Issue]:
        return [i for i in self.issues if not i.is_open]


def _day(stamp: str) -> date:
    """The date of a GitLab ISO timestamp (`...Z` is not parseable on 3.10)."""
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()


def _closed_on(record: dict) -> date | None:
    """When the work finished: `closed_at`, else the last move into Done.

    Same rule as gitboard's `stats.done_at`, so the two tools agree on which
    issues are finished.
    """
    if record.get("closed_at"):
        return _day(record["closed_at"])
    moves = [
        stamp
        for stamp, action, label in record.get("transitions") or []
        if label == DONE and action == "add"
    ]
    return _day(moves[-1]) if moves else None


def _blocked_since(record: dict) -> date | None:
    moves = [
        stamp
        for stamp, action, label in record.get("transitions") or []
        if label == BLOCKED and action == "add"
    ]
    return _day(moves[-1]) if moves else None


def load_board(path: str | Path) -> Board:
    path = Path(path)
    try:
        meta = json.loads(path.read_text())
        issues = tuple(
            Issue(
                iid=int(record["iid"]),
                title=str(record.get("title") or ""),
                assignee=record.get("assignee") or None,
                labels=tuple(record.get("labels") or ()),
                closed_on=_closed_on(record),
                blocked_since=_blocked_since(record),
            )
            for record in meta["history"]
        )
        return Board(
            project=str(meta.get("project") or ""),
            name=str(meta.get("board") or ""),
            fetched_on=_day(meta["fetched_at"]),
            issues=issues,
        )
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"{path}: not a `gitboard stats --dump` file ({exc!r})"
        ) from exc
