"""`perch tui`: every project in one table, and single keys that run perch on one.

Display and key handling only. The table reads what is already on disk: the
last week `perch board` recorded (never a new simulation), one cell per Monday
step (`perch.core.status`: done, stale, todo, FAIL, ERR), and how many flags
the private watch has. Only the count shows here; the watch itself goes to the
output pane, and only when the lead presses `w`. The cursor is a cell: Enter on
a step runs it (and what follows), on any other column runs the next step.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.coordinate import Coordinate
from textual.message import Message
from textual.widgets import DataTable, Footer, Input, Log

from perch.cli import _bin_dir, _label, _money, _watch
from perch.core.config import load_config
from perch.core.doctor import project_checks
from perch.core.history import latest_week
from perch.core.status import STEPS, next_command, next_step, status
from perch.core.workspace import Home

_ERRORS = (OSError, TypeError, ValueError, KeyError)  # doctor's, for a bad config
COLUMNS = ("Project", "GitLab", "Stoplight", "Headroom", *STEPS, "Flags")
_SHOWN = {  # cell state -> (text, rich style)
    "done": ("✓", "green"),
    "stale": ("stale", "yellow"),
    "todo": ("·", "dim"),
    "failed": ("FAIL", "bold red"),
    "error": ("ERR", "bold red"),
}
COMMANDS = {  # key -> the perch command it runs on the selected project
    "b": "board",
    "m": "monday",
    "d": "doctor",
    "f": "forecast",
    "w": "watch",
    "Q": "quarterly",
}


def _spawn(
    argv: list[str], cwd: Path, started: Callable[[subprocess.Popen], None]
) -> Iterator[str]:
    """Run a command, yielding its output lines as they come; tests replace this.

    `started` gets the process as soon as it exists, so the app can stop it.
    """
    with subprocess.Popen(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",  # an odd byte must not kill the worker, and the app
    ) as proc:
        started(proc)
        for line in proc.stdout:
            yield line.rstrip("\n")
    if proc.returncode:
        yield f"exited {proc.returncode}"


def _flags(config_path: Path) -> str:
    """The watch's flag count; "—" when it can't run or has too little history."""
    try:
        page = _watch(config_path)
    except Exception:  # noqa: BLE001 -- one bad project must not stop the dashboard
        return "—"
    return "—" if page.thin else str(page.flags)


def _step_cells(cells) -> tuple[Text, ...]:
    return tuple(Text(*_SHOWN[cells[step].state]) for step in STEPS)


def row(home: Home, name: str) -> tuple[str | Text, ...]:
    """One project's cells; a config or history that fails to load shows its error."""
    steps = _step_cells(status(home, name, date.today()))  # noqa: DTZ011 -- never raises
    try:
        config = load_config(home.config_path(name), require_dump=False)
        week = latest_week(config.history)
    except Exception as exc:  # noqa: BLE001 -- a display boundary: show, never crash
        return (name, f"error: {type(exc).__name__}: {exc}", "", "", *steps, "")
    team = next((r for r in week if r["kind"] == "team"), {})
    return (
        name,
        config.gitlab_project or "not set",
        _label(team.get("signal")),
        _money(team.get("headroom")),
        *steps,
        _flags(home.config_path(name)),
    )


SUITE = "PI_SUITE"  # JSON: app -> {"cwd", "argv"}; Budgie and gitboard read it


def suite_map(home: Home, name: str) -> dict[str, dict]:
    """Where each app runs for this project: they all find config by walk-up."""
    config = load_config(home.config_path(name), require_dump=False)
    gitlab = [config.gitlab_project] if config.gitlab_project else []
    return {
        "perch": {"cwd": str(home.root), "argv": [str(_bin_dir() / "perch"), "tui"]},
        "budgie": {
            "cwd": str(config.budgie_project),
            "argv": [str(_bin_dir() / "budgie"), "tui"],
        },
        "gitboard": {
            "cwd": str(home.gitboard_dir),
            "argv": ["gitboard", "tui", *gitlab],
        },
    }


def suite_entry(name: str) -> dict | None:
    """$PI_SUITE's entry for ``name``; None when unset, malformed or absent."""
    try:
        entry = json.loads(os.environ.get(SUITE, ""))[name]
        cwd, argv = str(entry["cwd"]), [str(a) for a in entry["argv"]]
    except (ValueError, KeyError, TypeError):
        return None
    return {"cwd": cwd, "argv": argv} if argv else None


def switch(entry: dict) -> None:
    """Become the other app. Call only once the terminal is restored."""
    try:
        os.chdir(entry["cwd"])
        os.execvp(entry["argv"][0], entry["argv"])
    except OSError as exc:
        sys.exit(f"switch failed: {exc}")


class Grid(DataTable):
    """Enter runs the cursor's cell; a click only moves the cursor.

    DataTable also selects on a click of the cursor's cell, and a stray click
    must never start a fetch, so Enter posts its own message instead.
    """

    class Go(Message):
        pass

    def action_select_cursor(self) -> None:
        self.post_message(self.Go())


class PerchTUI(App):
    AUTO_FOCUS = "#projects"
    CSS = """
    #projects { width: 3fr; }
    #output { width: 2fr; border-left: solid $panel; }
    #flags { display: none; dock: bottom; }
    """
    BINDINGS = [  # noqa: RUF012 -- Textual reads it off the class
        *((key, f"run('{key}')", command) for key, command in COMMANDS.items()),
        ("a", "run('a')", "monday --all"),
        ("c", "cut", "cut"),
        ("h", "hours", "hours"),
        ("r", "refresh", "refresh"),
        ("B", "switch('budgie')", "budgie"),
        ("G", "switch('gitboard')", "gitboard"),
        ("question_mark", "show_help_panel", "help"),
        ("q", "quit", "quit"),
        Binding("escape", "close_cut", show=False),
    ]

    def __init__(self, home: Home):
        super().__init__()
        self.home = home
        self.names = home.projects()
        self.busy: str | None = None
        self.child: subprocess.Popen | None = None  # the running command's process

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Grid(id="projects", cursor_type="cell")
            yield Log(id="output")
        yield Input(id="flags", placeholder="cut flags, e.g. --budget 700000")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(DataTable).add_columns(*COLUMNS)
        self.action_refresh()

    def action_refresh(self) -> None:
        table = self.query_one(DataTable)
        at = table.cursor_coordinate
        table.clear()
        self.names = self.home.projects()  # a project made meanwhile shows up
        for name in self.names:
            table.add_row(*row(self.home, name), key=name)
        table.move_cursor(row=at.row, column=at.column)

    def _selected(self) -> str | None:
        if not self.names:
            self.query_one(Log).write_line("no projects yet. Run: perch init <name>")
            return None
        return self.names[self.query_one(DataTable).cursor_coordinate.row]

    def _free(self) -> bool:
        if self.busy:
            self.query_one(Log).write_line(f"busy: {self.busy}")
        return not self.busy

    def action_run(self, key: str, extra: tuple[str, ...] = ()) -> None:
        if not self._free():
            return
        if key == "a":  # `perch monday` refuses -p with --all
            self._start(None, "monday --all", ["monday", "--all"])
            return
        name = self._selected()
        if name is None:
            return
        command = COMMANDS.get(key, key)  # `cut` comes here by name
        self._start(name, command, [command, "-p", name, *extra])

    def _start(self, name: str | None, action: str, args: list[str]) -> None:
        """Run perch on one project, or on every project when ``name`` is None."""
        self.busy = action
        self._stream(self.query_one(Log), name, [str(_bin_dir() / "perch"), *args])

    def on_grid_go(self) -> None:
        """Enter: a step's cell runs that step; any other column, the next one."""
        name = self._selected() if self._free() else None
        if name is None:
            return
        column = COLUMNS[self.query_one(Grid).cursor_coordinate.column]
        step = (
            column
            if column in STEPS
            else next_step(status(self.home, name, date.today()))  # noqa: DTZ011
        )
        if step is None:
            self.query_one(Log).write_line(f"{name}: Monday done")
        elif step == "hours":
            self.action_hours()
        else:
            argv = next_command(name, step)
            self._start(name, " ".join(argv), argv)

    @work(thread=True)
    def _stream(self, log: Log, name: str | None, argv: list[str]) -> None:
        """In a thread: every touch of the app goes through call_from_thread."""
        prefix = name or "all"
        last = ""
        try:
            for last in _spawn(argv, self.home.root, self._hold):
                self.call_from_thread(log.write_line, f"{prefix}: {last}")
        except OSError as exc:
            self.call_from_thread(log.write_line, f"{prefix}: {exc}")
        finally:  # _spawn's last line is "exited N" when the command failed
            failed = last.startswith("exited ")
            self.call_from_thread(self._finished, name, failed)

    def _hold(self, proc: subprocess.Popen) -> None:
        self.child = proc

    def on_unmount(self) -> None:
        """Quitting must not leave the child running: ask it to stop, then force."""
        proc, self.child = self.child, None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(3)
        except subprocess.TimeoutExpired:
            proc.kill()

    def _finished(self, name: str | None = None, failed: bool = False) -> None:
        """Refresh the row that ran (every row after `a`); a failure logs its FIXes."""
        self.child = None
        self.busy = None
        if name not in self.names:  # None (`a`), or a project gone meanwhile
            self.action_refresh()
            return
        table = self.query_one(DataTable)
        at = self.names.index(name)
        for col, cell in enumerate(row(self.home, name)):
            table.update_cell_at(Coordinate(at, col), cell, update_width=True)
        if failed:  # ponytail: `a` (monday --all) gets no FIX lines
            log = self.query_one(Log)
            for check in project_checks(self.home, name):
                if not check.ok:
                    log.write_line(f"{name}: FIX  {check.what}  ->  {check.fix}")

    def action_cut(self) -> None:
        if self._free() and self.names:
            box = self.query_one(Input)
            box.display = True
            box.focus()

    def action_close_cut(self) -> None:
        box = self.query_one(Input)
        box.display = False
        box.value = ""
        self.query_one(DataTable).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_close_cut()
        try:
            flags = tuple(shlex.split(event.value))
        except ValueError as exc:
            self.query_one(Log).write_line(f"cut: {exc}")
            return
        self.action_run("cut", flags)

    def action_hours(self) -> None:
        from perch.core.steps import hours

        name = self._selected() if self._free() else None
        if name is None:
            return
        try:  # a bad config or a missing editor is a line in the pane
            config = load_config(self.home.config_path(name), require_dump=False)
            step = hours(os.environ.get("EDITOR") or "vim", config)
            with self.suspend():
                subprocess.run(step.argv, cwd=step.cwd, check=False)
        except _ERRORS as exc:
            self.query_one(Log).write_line(f"{name}: {exc}")
        self.action_refresh()

    def action_switch(self, target: str) -> None:
        """Hand the terminal to Budgie or gitboard for the selected project."""
        name = self._selected() if self._free() else None
        if name is None:
            return
        try:  # a bad config is a line in the pane, not a crash
            os.environ[SUITE] = json.dumps(suite_map(self.home, name))
        except _ERRORS as exc:
            self.query_one(Log).write_line(f"{name}: {exc}")
            return
        self.exit(target)
