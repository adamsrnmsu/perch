"""As-of browsing: pure arithmetic over the week keys of history rows.

A week is an ISO string like "2026-W37"; None means live. Nothing here reads
a person row or a file.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date

_WEEK = re.compile(r"(?:(\d{4})-)?W(\d{1,2})")


def weeks(rows_by_project: Iterable[list[dict]]) -> list[str]:
    """Every week any project recorded a team row, oldest first."""
    return sorted(
        {r["week"] for rows in rows_by_project for r in rows if r["kind"] == "team"}
    )


def resolve(text: str, recorded: list[str]) -> str | None:
    """A typed target to a recorded week; None is live."""
    t = text.strip().upper()
    if t in ("", "LIVE", "NOW"):
        return None
    m = _WEEK.fullmatch(t)
    if not m:
        raise ValueError(f"not a week: {text.strip()} (try W38, 2026-W38 or LIVE)")
    year, num = m.groups()
    week = f"{year}-W{int(num):02d}" if year else None
    if week:
        hit = week if week in recorded else None
    else:
        hit = next(
            (w for w in reversed(recorded) if w.endswith(f"-W{int(num):02d}")), None
        )
    if hit:
        return hit
    span = f": {_short(recorded[0])}…{_short(recorded[-1])}" if recorded else ""
    raise ValueError(f"no week {_short(week or f'W{int(num):02d}')} recorded{span}")


def _short(week: str) -> str:
    return week.split("-")[-1]


def step(recorded: list[str], current: str | None, delta: int) -> str | None:
    """Move `delta` positions along recorded[:-1] + [live], clamped."""
    if not recorded:
        return None
    spots: list[str | None] = [*recorded[:-1], None]
    here = (
        spots.index(current)
        if current in spots
        else len(spots) - 1  # live, or the latest week, which live shows
    )
    return spots[max(0, min(len(spots) - 1, here + delta))]


def until(rows: list[dict], week: str) -> list[dict]:
    return [r for r in rows if r["week"] <= week]


def team_as_of(rows: list[dict], week: str) -> dict | None:
    """That week's team row, never the nearest one."""
    return next((r for r in rows if r["kind"] == "team" and r["week"] == week), None)


def week_end(week: str) -> date:
    year, num = week.split("-W")
    return date.fromisocalendar(int(year), int(num), 7)


def _words(text: str) -> list[str]:
    return text.strip().upper().split()


def is_command(text: str) -> bool:
    w = _words(text)
    return bool(w) and (w[0] == "ASOF" or w[:2] == ["AS", "OF"])


def argument(text: str) -> str:
    w = text.split()
    return " ".join(w[2:] if len(w) > 1 and w[0].upper() == "AS" else w[1:])
