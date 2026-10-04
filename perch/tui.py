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

Commands run with PI_BLOCKS=1 (`perch.core.blocks`): a stdout line that is a
block becomes a widget in the run card (heading, text, figures tiles, table,
bars, list), any other line stays text. `o` maximizes the newest card; Escape
restores it.
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

from rich.columns import Columns
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.coordinate import Coordinate
from textual.message import Message
from textual.widget import Widget
from textual.widgets import DataTable, Footer, Input, Static

from perch.cli import _bin_dir, _label, _watch
from perch.core import blocks, history
from perch.core.command import parse
from perch.core.config import load_config
from perch.core.doctor import project_checks
from perch.core.status import STEPS, next_command, next_step, status
from perch.core.suite import entry_of, hop, in_suite, windows
from perch.core.trend import (
    Change,
    _money,
    change,
    describe,
    series,
    spark,
    team_lines,
)
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
        last = max((r["week"] for r in rows), default=None)
        team = next((r for r in rows if r["week"] == last and r["kind"] == "team"), {})
        moved = change(rows)
        trend = spark(series(rows, "headroom").values())
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
    stoplight = Text(
        _label(team.get("signal")), style="reverse" if moved and moved.signal else ""
    )
    return (
        name,
        config.gitlab_project or "not set",
        stoplight,
        _money(team.get("headroom")),
        trend,
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
    except (OSError, ValueError) as exc:  # ValueError: an empty program name
        sys.exit(f"switch failed: {exc}")


_TONE = blocks.TONE_STYLE
TABLE_ROWS = 12  # a table shows this many rows, then scrolls


def _num(n: float, unit: str | None) -> str:
    return f"{n:g}" + (f" {unit}" if unit else "")


def bar_lines(items: list, unit: str | None, width: int) -> Text:
    """`label  ████ n` per item: label padded, bar scaled to the largest value."""
    pad = max((len(label) for label, _ in items), default=0)
    nums = [_num(n, unit) for _, n in items]
    room = max(width - pad - max(map(len, nums), default=0) - 2, 1)
    top = max((n for _, n in items), default=0)
    lines = [
        f"{label:<{pad}} {'█' * (round(room * n / top) if top > 0 and n > 0 else 0)} {num}"
        for (label, n), num in zip(items, nums, strict=True)
    ]
    return Text("\n".join(lines))


class Bars(Static):
    """Redrawn at its own width, so a maximized card gets longer bars."""

    def __init__(self, items: list, unit: str | None):
        super().__init__()
        self.items, self.unit = items, unit

    def render(self) -> Text:
        return bar_lines(self.items, self.unit, self.size.width or 40)


def _tile(f: dict) -> Text:
    tile = Text(f["value"], style=f"bold {_TONE.get(f.get('tone'), '')}".strip())
    tile.append(f"\n{f['label']}", style="dim")
    if f.get("note"):
        tile.append(f"\n{f['note']}", style="dim")
    return tile


def _table(b: dict) -> Vertical:
    cols = b["columns"]
    right = [a == "r" for a in b.get("align") or ["l"] * len(cols)]
    table = DataTable(show_cursor=False, zebra_stripes=True)
    table.add_columns(
        *(
            Text(c, justify="right" if r else "left")
            for c, r in zip(cols, right, strict=True)
        )
    )
    for r in b["rows"]:
        table.add_row(
            *(
                Text(c, justify="right" if x else "left")
                for c, x in zip(r, right, strict=True)
            )
        )
    table.styles.height = min(len(b["rows"]), TABLE_ROWS) + 1  # + the header
    return Vertical(*_titled(b), table, classes="block")


def _titled(b: dict) -> list[Static]:
    return [Static(Text(b["title"], style="bold"))] if b.get("title") else []


def block_widget(b: dict) -> Widget:
    """One block as a widget; the kinds are those of perch.core.blocks."""
    kind = b["block"]
    if kind == "table":
        return _table(b)
    if kind == "bars":
        return Vertical(*_titled(b), Bars(b["items"], b.get("unit")), classes="block")
    if kind == "heading":
        level = b["level"]
        w = Static(Text(b["text"], style="bold dim" if level == 3 else "bold"))
        if level == 2:
            w.styles.border_bottom = ("solid", "gray")
        return w
    if kind == "text":
        return Static(Text(b["text"], style=_TONE.get(b.get("tone"), "")))
    if kind == "figures":
        return Static(Columns([_tile(f) for f in b["items"]], padding=(0, 3)))
    return Static(Text("\n".join(f"• {i}" for i in b["items"])))  # list


class RunCard(Vertical):
    """One command's output: its title, a live status, the tool's own colours.

    Plain lines gather in one text widget; a block mounts a widget after it and
    the next plain line starts a fresh text widget below.
    """

    ALLOW_MAXIMIZE = True
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
    RunCard .block { height: auto; margin: 0 0 1 0; }
    RunCard .block Static { height: auto; }
    """

    def __init__(self, title: str, info: bool = False):
        super().__init__()
        self.border_title = title
        self.info = info  # a card of facts: no spinner, nothing to finish
        self.parts: list[tuple[Static, Text]] = []  # the text widgets, oldest first
        self._open = False  # the last widget is a text one still taking lines
        self.began = time.monotonic()
        self.frame = 0

    @property
    def body(self) -> Text:
        """All the plain lines, blocks left out."""
        return Text("\n").join(t for _, t in self.parts)

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
        if not self._open:
            self.parts.append((Static(), Text()))
            self.mount(self.parts[-1][0])
            self._open = True
        widget, body = self.parts[-1]
        if body:
            body.append("\n")
        body.append_text(line)
        widget.update(body)

    def put(self, raw: str) -> None:
        """One output line: a block becomes a widget, anything else is text."""
        if (b := blocks.parse(raw)) is None:
            self.add(Text.from_ansi(raw))
        else:
            self.mount(block_widget(b))
            self._open = False

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
        ("o", "open", "open"),
        ("h", "hours", "hours"),
        ("R", "review", "review"),
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
        self.query_one("#projects", Grid).add_columns(*COLUMNS)
        self.action_refresh()

    def action_refresh(self) -> None:
        table = self.query_one("#projects", Grid)
        at = table.cursor_coordinate
        table.clear()
        self.names = self.home.projects()  # a project made meanwhile shows up
        self.changes = {}
        for name in self.names:
            cells, self.changes[name] = snapshot(self.home, name)
            table.add_row(*cells, key=name)
        table.move_cursor(row=at.row, column=at.column)
        self._report()

    def on_app_focus(self) -> None:
        """Back in front (a hop in perch suite): refresh behind the table, so the
        hop is instant and the cells catch up a moment later."""
        self._refresh_behind()

    @work(thread=True, exclusive=True, group="focus")
    def _refresh_behind(self) -> None:
        snaps = {name: snapshot(self.home, name) for name in self.names}
        self.call_from_thread(self._fill, snaps)

    def _fill(self, snaps: dict) -> None:
        """Rewrite the rows in place: the cursor stays. A project made meanwhile
        shows on `r`."""
        table = self.query_one("#projects", Grid)
        for name, (cells, moved) in snaps.items():
            if name not in self.names:  # removed while the worker ran
                continue
            self.changes[name] = moved
            at = self.names.index(name)
            for col, cell in enumerate(cells):
                table.update_cell_at(Coordinate(at, col), cell, update_width=True)
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
        return self.names[self.query_one("#projects", Grid).cursor_coordinate.row]

    def _free(self) -> bool:
        if self.busy:
            self.notify(f"busy: {self.busy}", severity="warning")
        return not self.busy

    def action_run(self, key: str) -> None:
        if not self._free():
            return
        if key == "a":  # `perch monday` refuses -p with --all
            self._start(None, "monday --all", ["monday", "--all"])
            return
        name = self._selected()
        if name is None:
            return
        command = COMMANDS[key]
        self._start(name, command, [command, "-p", name])

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
        env = {"FORCE_COLOR": "1", "COLUMNS": str(width), blocks.ENV: "1"}
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
                    self.call_from_thread(card.put, pending)
                pending = line
            if pending is not None and pending.startswith("exited "):
                code, pending = int(pending.split()[1]), None
        except (OSError, ValueError) as exc:
            code, pending = 1, f"{pending}\n{exc}" if pending else str(exc)
        finally:
            if pending is not None:
                self.call_from_thread(card.put, pending)
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
        table = self.query_one("#projects", Grid)
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
        self.query_one("#projects", Grid).focus()
        self.screen.minimize()  # Escape also restores a maximized card

    def action_open(self) -> None:
        """Maximize the newest card (its container is the pane: not that)."""
        cards = self.query(RunCard)
        if cards:
            self.screen.maximize(cards.last(), container=False)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.action_close_command()
        try:
            command = parse(event.value, self.names, self._selected())
        except ValueError as exc:
            self.notify(str(exc), severity="error")
            return
        if command.args[0] in ("hours", "review"):
            self.query_one("#projects", Grid).move_cursor(
                row=self.names.index(command.project)
            )
            if command.args[0] == "hours":
                self.action_hours()
            else:
                self.action_review()
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

    def action_review(self) -> None:
        """Hand the terminal to Claude's /board for the selected project."""
        from perch.core.steps import review

        name = self._selected() if self._free() else None
        if name is None:
            return
        try:  # no pull yet is a toast, not a flash behind the suspended screen
            config = load_config(self.home.config_path(name), require_dump=False)
            step = review(self.home, name, config, history.load(config.history))
        except _ERRORS as exc:
            self.notify(f"{name}: {exc}", severity="error")
            return
        with self.suspend():
            subprocess.run(step.argv, cwd=step.cwd, check=False)
        self.action_refresh()

    def action_switch(self, target: str) -> None:
        """Budgie or gitboard for the selected project: in perch suite a hop to
        its window (perch keeps running, busy or not), else an exec."""
        inside = in_suite(os.environ)
        name = self._selected() if inside or self._free() else None
        if name is None:
            return
        try:  # a bad config is a line in the pane, not a crash
            apps = suite_map(self.home, name)
        except _ERRORS as exc:
            self.notify(f"{name}: {exc}", severity="error")
            return
        if inside:
            self._hop(target, apps)
            return
        os.environ[SUITE] = json.dumps(apps)
        self.exit(target)

    def _hop(self, target: str, apps: dict) -> None:
        try:
            listing = subprocess.run(
                windows(), capture_output=True, text=True, check=False
            ).stdout
            current = entry_of(listing, target)
            argv = hop(target, apps[target], json.dumps(apps), current)
            done = subprocess.run(argv, capture_output=True, text=True, check=False)
        except OSError as exc:
            self.notify(f"{target}: switch failed: {exc}", severity="error")
            return
        if done.returncode:
            self.notify(
                f"{target}: switch failed: {done.stderr.strip() or 'tmux failed'}",
                severity="error",
            )
