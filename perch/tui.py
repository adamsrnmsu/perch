"""`perch tui`: every project in one table, and single keys that run perch on one.

Display and key handling only. The table reads what is already on disk: the
last week `perch board` recorded (never a new simulation), the team's headroom
trend, one cell per Monday step (`perch.core.status`: done, stale, todo, FAIL,
ERR), and how many flags the private watch has. Only the count shows here; the
watch itself goes to the output pane, and only when the lead presses `w`. The
output pane is a stack of run cards: one per command, in the tool's own colours,
with a live status. The cursor is a cell: Enter on a step runs it (and what
follows), on any other column runs the next step; `i` explains the cell in an
info card. `:` opens the command line (`perch.core.command`), `c` prefilled with
CUT. A line above the table says what changed since last week, and a stoplight
that flipped toasts once. All of it reads the team row of history.jsonl.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from datetime import date
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.coordinate import Coordinate
from textual.message import Message
from textual.widgets import DataTable, Footer, Input, Static

from perch.cli import _bin_dir, _label, _money, _watch
from perch.core import history
from perch.core.command import parse
from perch.core.config import load_config
from perch.core.doctor import project_checks
from perch.core.status import STEPS, next_command, next_step, status
from perch.core.trend import Change, change, describe, series, spark, team_lines
from perch.core.workspace import Home

_ERRORS = (OSError, TypeError, ValueError, KeyError)  # doctor's, for a bad config
COLUMNS = ("Project", "GitLab", "Stoplight", "Headroom", "Trend", *STEPS, "Flags")
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


KEEP = 20  # run cards kept in the output pane
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def _spawn(
    argv: list[str],
    cwd: Path,
    started: Callable[[subprocess.Popen], None],
    env: dict[str, str] | None = None,
) -> Iterator[str]:
    """Run a command, yielding its output lines as they come; tests replace this.

    `started` gets the process as soon as it exists, so the app can stop it.
    `env` is added to os.environ.
    """
    with subprocess.Popen(
        argv,
        cwd=cwd,
        env={**os.environ, **(env or {})},
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


def snapshot(home: Home, name: str) -> tuple[tuple[str | Text, ...], Change | None]:
    """One project's cells and its week-on-week change, from one read of history."""
    steps = _step_cells(status(home, name, date.today()))  # noqa: DTZ011 -- never raises
    try:
        config = load_config(home.config_path(name), require_dump=False)
        rows = history.load(config.history)
    except Exception as exc:  # noqa: BLE001 -- a display boundary: show, never crash
        return (
            name,
            f"error: {type(exc).__name__}: {exc}",
            "",
            "",
            "",
            *steps,
            "",
        ), None
    last = max((r["week"] for r in rows), default=None)
    team = next((r for r in rows if r["week"] == last and r["kind"] == "team"), {})
    moved = change(rows)
    stoplight = Text(
        _label(team.get("signal")), style="reverse" if moved and moved.signal else ""
    )
    return (
        name,
        config.gitlab_project or "not set",
        stoplight,
        _money(team.get("headroom")),
        spark(series(rows, "headroom").values()),
        *steps,
        _flags(home.config_path(name)),
    ), moved


def row(home: Home, name: str) -> tuple[str | Text, ...]:
    return snapshot(home, name)[0]


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


class RunCard(Static):
    """One command's output: its title, a live status, the tool's own colours."""

    DEFAULT_CSS = """
    RunCard {
        height: auto;
        border: round $panel-lighten-2;
        border-title-color: $text;
        border-subtitle-color: $text-muted;
        padding: 0 1;
    }
    RunCard.ok { border: round $success; border-subtitle-color: $success; }
    RunCard.failed { border: round $error; border-subtitle-color: $error; }
    """

    def __init__(self, title: str, info: bool = False):
        super().__init__()
        self.border_title = title
        self.info = info  # a card of facts: no spinner, nothing to finish
        self.body = Text()
        self.began = time.monotonic()
        self.frame = 0

    def on_mount(self) -> None:
        if self.info:
            self.border_subtitle = "info"
            return
        self.ticker = self.set_interval(0.1, self._tick)
        self._tick()

    def _tick(self) -> None:
        self.border_subtitle = f"{SPINNER[self.frame % len(SPINNER)]} running"
        self.frame += 1

    def add(self, line: Text) -> None:
        if self.body:
            self.body.append("\n")
        self.body.append_text(line)
        self.update(self.body)

    def finish(self, code: int) -> None:
        self.ticker.stop()
        took = f"{time.monotonic() - self.began:.1f}s"
        self.border_subtitle = f"✓ {took}" if not code else f"✗ exited {code} · {took}"
        self.add_class("failed" if code else "ok")


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
    #output { width: 2fr; border-left: solid $panel; padding: 0 1; }
    #changes { display: none; padding: 0 1; }
    #command { display: none; dock: bottom; }
    """
    BINDINGS = [  # noqa: RUF012 -- Textual reads it off the class
        *((key, f"run('{key}')", command) for key, command in COMMANDS.items()),
        ("a", "run('a')", "monday --all"),
        ("colon", "command('')", "command"),
        ("c", "command('CUT ')", "cut"),
        ("i", "info", "info"),
        ("h", "hours", "hours"),
        ("r", "refresh", "refresh"),
        ("B", "switch('budgie')", "budgie"),
        ("G", "switch('gitboard')", "gitboard"),
        ("question_mark", "show_help_panel", "help"),
        ("q", "quit", "quit"),
        Binding("escape", "close_command", show=False),
    ]

    def __init__(self, home: Home):
        super().__init__()
        self.home = home
        self.names = home.projects()
        self.busy: str | None = None
        self.child: subprocess.Popen | None = None  # the running command's process
        self.changes: dict[str, Change | None] = {}  # project -> its latest change
        self.alerted: set[tuple[str, str]] = set()  # (project, week) already toasted

    def compose(self) -> ComposeResult:
        yield Static(id="changes")
        with Horizontal():
            yield Grid(id="projects", cursor_type="cell")
            yield VerticalScroll(id="output")
        yield Input(id="command", placeholder="apollo CUT 700k · ALL MON · MON weekly")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(DataTable).add_columns(*COLUMNS)
        self.action_refresh()

    def action_refresh(self) -> None:
        table = self.query_one(DataTable)
        at = table.cursor_coordinate
        table.clear()
        self.names = self.home.projects()  # a project made meanwhile shows up
        self.changes = {}
        for name in self.names:
            cells, self.changes[name] = snapshot(self.home, name)
            table.add_row(*cells, key=name)
        table.move_cursor(row=at.row, column=at.column)
        self._report()

    def _report(self) -> None:
        """The what-changed line, and one toast per stoplight flip."""
        lines = [describe(n, self.changes.get(n)) for n in self.names]
        strip = self.query_one("#changes", Static)
        strip.update(Text("  ·  ".join(line for line in lines if line)))
        strip.display = any(lines)
        for name in self.names:
            moved = self.changes.get(name)
            if moved and moved.signal and (name, moved.after) not in self.alerted:
                self.alerted.add((name, moved.after))
                old, new = (s.upper() for s in moved.signal)
                self.notify(
                    f"{name}: stoplight {old} → {new} ({moved.after[5:]})",
                    severity="error" if new == "RED" else "warning",
                )

    def _selected(self) -> str | None:
        if not self.names:
            self.notify("no projects yet. Run: perch init <name>", severity="warning")
            return None
        return self.names[self.query_one(DataTable).cursor_coordinate.row]

    def _free(self) -> bool:
        if self.busy:
            self.notify(f"busy: {self.busy}", severity="warning")
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

    def _show(self, card: RunCard) -> RunCard:
        """Add a card to the output pane, dropping the oldest beyond KEEP."""
        pane = self.query_one("#output", VerticalScroll)
        pane.mount(card)
        for old in list(pane.query(RunCard))[:-KEEP]:
            old.remove()
        pane.scroll_end(animate=False)
        return card

    def _start(self, name: str | None, action: str, args: list[str]) -> None:
        """Run perch on one project, or on every project when ``name`` is None."""
        self.busy = action
        card = self._show(RunCard(f"{action} · {name}" if name else action))
        width = max(
            self.query_one("#output").size.width - 4, 40
        )  # the card's inside: tables fit it
        env = {"FORCE_COLOR": "1", "COLUMNS": str(width)}
        self._stream(card, name, [str(_bin_dir() / "perch"), *args], env)

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
            self.notify(f"{name}: Monday done")
        elif step == "hours":
            self.action_hours()
        else:
            argv = next_command(name, step)
            self._start(name, " ".join(argv), argv)

    @work(thread=True)
    def _stream(
        self, card: RunCard, name: str | None, argv: list[str], env: dict[str, str]
    ) -> None:
        """In a thread: every touch of the app goes through call_from_thread.

        Each line is shown one behind, so `_spawn`'s closing "exited N" can go
        to the card's status instead of its body.
        """
        pending, code = None, 0
        try:
            for line in _spawn(argv, self.home.root, self._hold, env):
                if pending is not None:
                    self.call_from_thread(card.add, Text.from_ansi(pending))
                pending = line
            if pending is not None and pending.startswith("exited "):
                code, pending = int(pending.split()[1]), None
        except (OSError, ValueError) as exc:
            code, pending = 1, f"{pending}\n{exc}" if pending else str(exc)
        finally:
            if pending is not None:
                self.call_from_thread(card.add, Text.from_ansi(pending))
            self.call_from_thread(self._finished, name, card, code)

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

    def _finished(self, name: str | None, card: RunCard, code: int) -> None:
        """Close the card; refresh the row that ran (every row after `a`).

        A failure adds the project's FIX lines to its card.
        """
        self.child = None
        self.busy = None
        card.finish(code)
        self.query_one("#output", VerticalScroll).scroll_end(animate=False)
        if name not in self.names:  # None (`a`), or a project gone meanwhile
            self.action_refresh()
            return
        table = self.query_one(DataTable)
        at = self.names.index(name)
        cells, self.changes[name] = snapshot(self.home, name)
        for col, cell in enumerate(cells):
            table.update_cell_at(Coordinate(at, col), cell, update_width=True)
        self._report()
        if code:  # ponytail: `a` (monday --all) gets no FIX lines
            for check in project_checks(self.home, name):
                if not check.ok:
                    fix = Text.assemble(("▲ FIX  ", "bold yellow"), check.what)
                    fix.append(f"\n       → {check.fix}", style="yellow")
                    card.add(fix)

    def action_command(self, text: str) -> None:
        box = self.query_one("#command", Input)
        box.value = text
        box.cursor_position = len(text)
        box.display = True
        box.focus()

    def action_close_command(self) -> None:
        box = self.query_one("#command", Input)
        box.display = False
        box.value = ""
        self.query_one(DataTable).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_close_command()
        try:
            command = parse(event.value, self.names, self._selected())
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        if command.args[0] == "hours":
            self.query_one(DataTable).move_cursor(row=self.names.index(command.project))
            self.action_hours()
        elif self._free():
            self._start(command.project, " ".join(command.args), list(command.args))

    def action_info(self) -> None:
        """Explain the cursor's cell in an info card; Flags runs the watch."""
        name = self._selected()
        if name is None:
            return
        column = COLUMNS[self.query_one(Grid).cursor_coordinate.column]
        if column == "Flags":
            self.action_run("w")
            return
        try:
            if column in ("Project", "GitLab"):
                checks = project_checks(self.home, name)
                lines = [
                    f"✓ {c.what}" if c.ok else f"✗ {c.what} → {c.fix}" for c in checks
                ]
            elif column in STEPS:
                cell = status(self.home, name, date.today())[column]  # noqa: DTZ011
                lines = [
                    f"{cell.state} · {cell.when}",
                    *([cell.why] if cell.why else []),
                ]
            else:
                config = load_config(self.home.config_path(name), require_dump=False)
                lines = team_lines(history.load(config.history))
        except _ERRORS as exc:
            self.notify(f"{name}: {exc}", severity="error")
            return
        card = self._show(RunCard(f"{column} · {name}", info=True))
        card.add(Text("\n".join(lines)))

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
            self.notify(f"{name}: {exc}", severity="error")
        self.action_refresh()

    def action_switch(self, target: str) -> None:
        """Hand the terminal to Budgie or gitboard for the selected project."""
        name = self._selected() if self._free() else None
        if name is None:
            return
        try:  # a bad config is a line in the pane, not a crash
            os.environ[SUITE] = json.dumps(suite_map(self.home, name))
        except _ERRORS as exc:
            self.notify(f"{name}: {exc}", severity="error")
            return
        self.exit(target)
