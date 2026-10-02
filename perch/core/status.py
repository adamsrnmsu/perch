"""Where Monday stands: one cell per step, read from the files each step writes.

Nothing here runs a step, fits a rate or reads the watch; it only looks at
files and dates, so a TUI can call it on every redraw. A step that failed in
`perch monday` leaves `projects/NAME/monday.json`; the cell shows `failed`
until that step's output is newer than the record.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from perch.core.config import load_config
from perch.core.doctor import age
from perch.core.history import latest_week
from perch.core.steps import iso_week
from perch.core.workspace import Home

STEPS = ("hours", "fetch", "board", "weekly", "digest", "emails", "watch")
_DATED = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class Cell:
    state: str  # "done" | "stale" | "todo" | "failed" | "error"
    when: str  # doctor.age() of the step's output; "never" if none
    why: str = ""


def failure_path(home: Home, name: str) -> Path:
    return home.projects_dir / name / "monday.json"


def record_failure(
    home: Home, name: str, week: str, step: str, code: int, at: datetime
) -> None:
    path = failure_path(home, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"week": week, "step": step, "code": code, "at": at.isoformat()}
    path.write_text(json.dumps(rec))


def clear_failure(home: Home, name: str, ran: tuple[str, ...] = STEPS) -> None:
    """Drop the record once a run got through its step (`ran`: the steps run)."""
    path = failure_path(home, name)
    try:
        if json.loads(path.read_text())["step"] not in ran:
            return  # `--from` a later step: the earlier failure still stands
    except (ValueError, KeyError, TypeError):
        pass  # unreadable: nothing worth keeping
    except OSError:
        return  # no record
    path.unlink(missing_ok=True)


def _mtime(path: Path) -> float | None:
    """A file's mtime; a directory's newest file, since rewriting a file in
    place (Budgie's .eml drafts, a same-day digest) leaves the directory's own."""
    if not path.exists():
        return None
    if path.is_dir():
        return max(
            (p.stat().st_mtime for p in path.rglob("*") if p.is_file()),
            default=path.stat().st_mtime,
        )
    return path.stat().st_mtime


def _newest_report(reports: Path) -> Path:
    """The latest YYYY-MM-DD folder gitboard wrote; `reports` itself if none."""
    days = [p for p in reports.glob("*") if p.is_dir() and _DATED.fullmatch(p.name)]
    return max(days, key=lambda p: p.name, default=reports / "never")


def _failed(home: Home, name: str, week: str, mtimes: dict[str, float | None]):
    """(step, code) of this week's recorded failure not yet overtaken, else None."""
    try:
        rec = json.loads(failure_path(home, name).read_text())
        step, code = rec["step"], int(rec["code"])
        at = datetime.fromisoformat(rec["at"]).timestamp()
        if rec["week"] != week or step not in STEPS:
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None  # missing or unreadable: no failure to show
    out = mtimes[step]
    return (step, code) if out is None or out <= at else None


def status(home: Home, name: str, today: date) -> dict[str, Cell]:
    """Every step's cell; a project that will not load is `error` throughout."""
    from perch.core.money import load_money

    week = iso_week(today)
    monday = today - timedelta(days=today.weekday())
    cutoff = datetime.combine(monday, time.min).timestamp()
    try:
        config = load_config(home.config_path(name), require_dump=False)
        as_of = load_money(config.budgie_project).as_of
        latest = {r["week"] for r in latest_week(config.history)}
    except Exception as exc:  # noqa: BLE001 -- a display boundary: show, never crash
        return dict.fromkeys(STEPS, Cell("error", "", f"{type(exc).__name__}: {exc}"))

    weekly_csv = config.budgie_project / "weekly.csv"
    paths = {
        "hours": weekly_csv,
        "fetch": config.board_dump,
        "board": config.history,
        "weekly": home.weekly_path(name, week),
        "emails": config.budgie_project / "emails",
        "watch": home.watch_path(name, week),
        "digest": _newest_report(home.reports_dir(name)),
    }
    m = {k: _mtime(p) for k, p in paths.items()}
    dump, csv, hist = m["fetch"], m["hours"], m["board"]

    def newer(a, b) -> bool:  # is input a newer than output b
        return a is not None and b is not None and a > b

    done = {
        "hours": as_of is not None and as_of >= monday - timedelta(days=1),
        "fetch": dump is not None and dump >= cutoff,
        "board": latest == {week},
        "weekly": m["weekly"] is not None,
        # by mtime, not the folder's name: gitboard names it by the UTC day
        "digest": m["digest"] is not None and m["digest"] >= cutoff,
        "emails": m["emails"] is not None and m["emails"] >= cutoff,
        "watch": m["watch"] is not None,
    }
    stale = {
        "board": (
            "weekly.csv" if newer(csv, hist) else "dump" if newer(dump, hist) else ""
        ),
        "weekly": "history" if newer(hist, m["weekly"]) else "",
        "watch": "history" if newer(hist, m["watch"]) else "",
        "digest": "dump" if newer(dump, m["digest"]) else "",
        "emails": "weekly.csv" if newer(csv, m["emails"]) else "",
    }
    cells = {}
    for step in STEPS:
        when = age(paths[step])
        if not done[step]:
            cells[step] = Cell("todo", when)
        elif stale.get(step):
            cells[step] = Cell("stale", when, f"{stale[step]} newer than {step}")
        else:
            cells[step] = Cell("done", when)
    if (failed := _failed(home, name, week, m)) is not None:
        step, code = failed
        cells[step] = Cell("failed", cells[step].when, f"{step} exited {code}")
    return cells


def next_step(cells: dict[str, Cell]) -> str | None:
    return next((s for s in STEPS if cells[s].state != "done"), None)


def next_command(name: str, step: str) -> list[str]:
    """The perch argv (after `perch`) that does `step` for `name`."""
    if step in ("hours", "watch"):
        return [step, "-p", name]
    return ["monday", "-p", name, "--from", step]
