"""`perch tui`: every project in one table, and single keys that run perch on one.

Display and key handling only. The table reads what is already on disk: the
last week `perch board` recorded (never a new simulation), how fresh the files
are, and how many flags the private watch has. Only the count shows here; the
watch itself goes to the output pane, and only when the lead presses `w`.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import DataTable, Footer, Input, Log

from perch.cli import _bin_dir, _label, _money, _watch
from perch.core.config import load_config
from perch.core.doctor import freshness
from perch.core.history import latest_week
from perch.core.workspace import Home

_ERRORS = (OSError, TypeError, ValueError, KeyError)  # doctor's, for a bad config
COLUMNS = ("Project", "GitLab", "Stoplight", "Headroom", "Dump", "weekly.csv", "Flags")
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


def row(home: Home, name: str) -> tuple[str, ...]:
    """One project's cells; a config or history that fails to load shows its error."""
    try:
        config = load_config(home.config_path(name), require_dump=False)
        week = latest_week(config.history)
    except Exception as exc:  # noqa: BLE001 -- a display boundary: show, never crash
        return (name, f"error: {type(exc).__name__}: {exc}", "", "", "", "", "")
    team = next((r for r in week if r["kind"] == "team"), {})
    ages = dict(freshness(home, name))
    return (
        name,
        config.gitlab_project or "not set",
        _label(team.get("signal")),
        _money(team.get("headroom")),
        ages.get("board dump", "—"),
        ages.get("weekly.csv", "—"),
        _flags(home.config_path(name)),
    )


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
            yield DataTable(id="projects", cursor_type="row")
            yield Log(id="output")
        yield Input(id="flags", placeholder="cut flags, e.g. --budget 700000")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(DataTable).add_columns(*COLUMNS)
        self.action_refresh()

    def action_refresh(self) -> None:
        table = self.query_one(DataTable)
        at = table.cursor_row
        table.clear()
        self.names = self.home.projects()  # a project made meanwhile shows up
        for name in self.names:
            table.add_row(*row(self.home, name), key=name)
        table.move_cursor(row=at)

    def _selected(self) -> str | None:
        if not self.names:
            self.query_one(Log).write_line("no projects yet. Run: perch init <name>")
            return None
        return self.names[self.query_one(DataTable).cursor_row]

    def _free(self) -> bool:
        if self.busy:
            self.query_one(Log).write_line(f"busy: {self.busy}")
        return not self.busy

    def action_run(self, key: str, extra: tuple[str, ...] = ()) -> None:
        if not self._free():
            return
        if key == "a":  # `perch monday` refuses -p with --all
            self._start("all", "monday --all", ["monday", "--all"])
            return
        name = self._selected()
        if name is None:
            return
        command = COMMANDS.get(key, key)  # `cut` comes here by name
        self._start(name, command, [command, "-p", name, *extra])

    def _start(self, prefix: str, action: str, args: list[str]) -> None:
        self.busy = action
        self._stream(self.query_one(Log), prefix, [str(_bin_dir() / "perch"), *args])

    @work(thread=True)
    def _stream(self, log: Log, prefix: str, argv: list[str]) -> None:
        """In a thread: every touch of the app goes through call_from_thread."""
        try:
            for line in _spawn(argv, self.home.root, self._hold):
                self.call_from_thread(log.write_line, f"{prefix}: {line}")
        except OSError as exc:
            self.call_from_thread(log.write_line, f"{prefix}: {exc}")
        finally:
            self.call_from_thread(self._finished)

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

    def _finished(self) -> None:
        self.child = None
        self.busy = None
        self.action_refresh()

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
            step = hours(os.environ.get("EDITOR") or "vi", config)
            with self.suspend():
                subprocess.run(step.argv, cwd=step.cwd, check=False)
        except _ERRORS as exc:
            self.query_one(Log).write_line(f"{name}: {exc}")
        self.action_refresh()
