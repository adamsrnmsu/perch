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
from collections.abc import Callable, Generator
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
from textual.worker import get_current_worker

from perch.cli import _bin_dir, _label, _watch
from perch.core import alerts as _alerts
from perch.core import asof as _asof
from perch.core import blocks, detail, history, sources, tape
from perch.core.command import parse
from perch.core.config import load_config
from perch.core.doctor import project_checks
from perch.core.status import STEPS, next_command, next_step, status
from perch.core.suite import entry_of, hop, in_suite, windows
from perch.core.trend import (
    Change,
    _money,
    change,
    money,
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
    "e": "events",
}


BAND, ROWS = "▒", 8  # the fan's glyph; the chart's height


def _level(v: float, top: float) -> int:
    """Which of the ROWS bands from the bottom (0) a value falls in."""
    return min(ROWS - 1, max(0, int(v / top * ROWS)))


def burn_lines(d: detail.Detail, width: int) -> Text:
    """Budgie's burn series as 8 rows by 12 month columns, drawn by glyph:
    `─` budget, `·` plan, `█` a month holding a reading, `▓` an interpolated
    month, `▒` the P10 to P90 fan. Later marks overwrite earlier ones."""
    b = d.burn
    if b is None or not b.months:
        return Text("")
    vals = [v for s in (b.spent, b.plan, b.budget, b.p90) for v in s if v is not None]
    top = max(vals, default=0)
    if top <= 0:
        return Text("")
    wide = max(1, min(width // len(b.months), 3))
    read = {(r.year, r.month) for r in b.reading_dates}
    grid = [[(" ", "") for _ in b.months] for _ in range(ROWS)]  # [row from top][month]

    def put(i: int, level: int, mark: str, style: str) -> None:
        grid[ROWS - 1 - level][i] = (mark, style)

    for i, month in enumerate(b.months):
        if b.p90 and b.p10[i] < b.p90[i]:
            for k in range(_level(b.p10[i], top), _level(b.p90[i], top) + 1):
                put(i, k, BAND, "blue")
        if (spent := b.spent[i]) is not None:
            hit = (month.year, month.month) in read
            for k in range(ROWS):
                if spent > k * top / ROWS:
                    put(i, k, "█" if hit else "▓", "green" if hit else "dim green")
        if b.plan[i] is not None:
            put(i, _level(b.plan[i], top), "·", "yellow")
        if b.budget[i] is not None:
            put(i, _level(b.budget[i], top), "─", "cyan")
    out = Text()
    for r, cells in enumerate(grid):
        for mark, style in cells:
            out.append(mark * wide, style=style)
        if r < ROWS - 1:
            out.append("\n")
    return out


KEEP = 20  # run cards kept in the output pane
SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def _spawn(
    argv: list[str],
    cwd: Path,
    started: Callable[[subprocess.Popen], None],
    env: dict[str, str] | None = None,
) -> Generator[str, None, int]:
    """Run a command, yielding its output lines as they come; tests replace this.
    The return value (StopIteration.value) is its exit code.

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
    return proc.returncode


def _flags(config_path: Path) -> str:
    """The watch's flag count; "—" when it can't run or has too little history."""
    try:
        page = _watch(config_path)
    except Exception:  # noqa: BLE001 -- one bad project must not stop the dashboard
        return "—"
    return "—" if page.thin else str(page.flags)


def _step_cells(cells) -> tuple[Text, ...]:
    return tuple(Text(*_SHOWN[cells[step].state]) for step in STEPS)


NA = "n/a"  # an as-of cell that is not historical: the step cells and Flags


def snapshot(
    home: Home, name: str, asof: str | None = None
) -> tuple[tuple[str | Text, ...], Change | None]:
    """One project's cells and its week-on-week change, from one read of history.

    With ``asof`` (a recorded week) the step cells and Flags are `n/a`, and
    the team figures are that week's own row: `—` when the project has none.
    """
    if asof:
        steps = tuple(Text(NA, style="dim") for _ in STEPS)
    else:
        steps = _step_cells(status(home, name, date.today()))  # noqa: DTZ011 -- never raises
    try:
        config = load_config(home.config_path(name), require_dump=False)
        rows = history.load(config.history)
        if asof:
            rows = _asof.until(rows, asof)
            team = _asof.team_as_of(rows, asof) or {}
            moved = change(rows)
            moved = moved if moved and moved.after == asof else None
            trend = spark(series(rows, "headroom").values()) if team else ""
        else:
            last = max((r["week"] for r in rows), default=None)
            team = next(
                (r for r in rows if r["week"] == last and r["kind"] == "team"), {}
            )
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
        Text(NA, style="dim") if asof else _flags(home.config_path(name)),
    ), moved


def alert_hits(home: Home, name: str, rules) -> list[_alerts.State]:
    """The rules that just turned true for one project (fresh), from its history."""
    if not rules:
        return []
    try:
        rows = history.load(
            load_config(home.config_path(name), require_dump=False).history
        )
        states = _alerts.evaluate(rules, name, rows, date.today())  # noqa: DTZ011
    except _ERRORS:
        return []
    return [s for s in states if s.fresh]


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
            "project": name,  # in the window's @entry: another project respawns
        },
        "gitboard": {
            "cwd": str(home.gitboard_dir),
            "argv": ["gitboard", "tui", *gitlab],
            "project": name,
        },
    }


def suite_entry(name: str) -> dict | None:
    """$PI_SUITE's entry for ``name``; None when unset, malformed or absent."""
    try:
        entry = json.loads(os.environ.get(SUITE, ""))[name]
        cwd, argv = str(entry["cwd"]), [str(a) for a in entry["argv"]]
    except (ValueError, KeyError, TypeError):
        return None
    return {**entry, "cwd": cwd, "argv": argv} if argv else None


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


TAPE_LINES = 200
_TAPE_STYLE = {"hours": "dim", "failed": "red", "error": "yellow"}


def tape_text(entries: list[tape.TapeEntry]) -> Text:
    """The tape, newest first, at most TAPE_LINES lines. Text, never markup."""
    out = Text()
    for i, e in enumerate(entries[:TAPE_LINES]):
        if i:
            out.append("\n")
        out.append(
            f"{e.day:%m-%d}  {e.project}  {e.kind}  {e.text}",
            style=_TAPE_STYLE.get(e.kind, ""),
        )
    return out


class PerchTUI(App):
    AUTO_FOCUS = "#projects"
    HORIZONTAL_BREAKPOINTS = [(0, "-narrow"), (160, "-wide")]  # noqa: RUF012
    CSS = """
    #projects { width: 3fr; }
    #detail { width: 2fr; border-left: solid $panel; padding: 0 1; }
    #detail.off, .-narrow #detail { display: none; }
    #output { width: 2fr; border-left: solid $panel; padding: 0 1; }
    #asof { display: none; background: $warning; color: $background; text-style: bold; padding: 0 1; }
    #projects.historical { opacity: 0.8; }
    #tape { height: 8; display: none; padding: 0 1; }
    #command { display: none; dock: bottom; }
    """
    BINDINGS = [  # noqa: RUF012 -- Textual reads it off the class
        *((key, f"run('{key}')", command) for key, command in COMMANDS.items()),
        ("a", "run('a')", "monday --all"),
        ("colon", "command('')", "command"),
        ("c", "command('CUT ')", "cut"),
        ("i", "info", "info"),
        ("o", "open", "open"),
        ("left_square_bracket", "asof(-1)", "as of"),
        Binding("right_square_bracket", "asof(1)", show=False),
        Binding("L", "live", show=False),
        Binding("E", "events_all", show=False),
        Binding("v", "toggle_detail", show=False),
        Binding("t", "toggle_tape", show=False),
        ("h", "hours", "hours"),
        ("R", "walk", "walk"),
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
        try:  # a bad `alerts:` file never stops the TUI: doctor reports it
            self.rules = home.alerts()
        except _ERRORS:
            self.rules = ()
        self.hits: dict[str, list[_alerts.State]] = {}  # project -> fresh alerts
        self.fired: set[tuple[str, int, str | None]] = set()  # (project, rule, week)
        self.asof_week: str | None = None  # the recorded week on view; None is live
        self.src: dict[str, sources.Sources] = {}  # the slow tier's loads
        self.stamps: dict[str, float] = {}  # project -> input mtime at its last load
        self.details: dict[str, detail.Detail] = {}
        self.tape_by: dict[str, list[tape.TapeEntry]] = {}
        self.tape_rows: list[tape.TapeEntry] = []
        self.tape_on = True

    def compose(self) -> ComposeResult:
        yield Static(id="asof")
        with Horizontal():
            yield Grid(id="projects", cursor_type="cell")
            yield Static(Text("loading…", style="dim"), id="detail")
            yield VerticalScroll(id="output")
        with VerticalScroll(id="tape"):
            yield Static(id="tape-body")
        yield Input(id="command", placeholder="apollo CUT 700k · ALL MON · MON weekly")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#projects", Grid).add_columns(*COLUMNS)
        names = self.home.projects()  # first paint: the table is never empty
        self._rebuild(names, {n: self._snap(n, self.asof_week) for n in names})
        self._warm_all(True)

    def action_refresh(self) -> None:
        self._reload()  # which then warms the slow tier, forced

    @work(thread=True, exclusive=True, group="slow")
    def _warm_all(self, force: bool = False) -> None:
        """The slow tier: Sources once per project, then the pane's Detail, one
        project at a time. A project whose inputs are unchanged is skipped unless
        forced. A cancelled thread worker keeps running, so it checks itself."""
        worker = get_current_worker()
        for name in list(self.names):
            if worker.is_cancelled:
                return
            try:
                stamp = sources.stamp(self.home, name)
                if (
                    not force
                    and name in self.details
                    and self.stamps.get(name) == stamp
                ):
                    continue
                src = sources.load(self.home, name)
                built = detail.build(name, src)
                entries = tape.project_tape(src, name, date.today())  # noqa: DTZ011
                if worker.is_cancelled:
                    return
                self.call_from_thread(self._warmed, name, stamp, src, built, entries)
            except RuntimeError:  # the app closed under the worker
                return
            except Exception:  # noqa: BLE001, S112 -- one project must not stop the rest
                continue

    def _warmed(
        self, name: str, stamp: float, src: sources.Sources, built, entries
    ) -> None:
        self.src[name], self.stamps[name], self.details[name] = src, stamp, built
        if self.asof_week:  # the thread built the live tape: redo it as of the week
            entries = tape.project_tape(
                src,
                name,
                date.today(),  # noqa: DTZ011
                asof=self.asof_week,
            )
        self.tape_by[name] = entries
        self._paint_detail()
        self._paint_tape()

    def _paint_tape(self) -> None:
        self.tape_rows = tape.merge(self.tape_by, self.names)
        body = self.query_one("#tape-body", Static)
        body.update(tape_text(self.tape_rows))
        self.query_one("#tape").display = bool(self.tape_rows) and self.tape_on

    def action_toggle_tape(self) -> None:
        self.tape_on = not self.tape_on
        self._paint_tape()

    def action_toggle_detail(self) -> None:
        self.query_one("#detail").toggle_class("off")

    def on_data_table_cell_highlighted(self, event: DataTable.CellHighlighted) -> None:
        if event.data_table.id == "projects":  # card tables are DataTables too
            self._paint_detail()

    def _paint_detail(self) -> None:
        """The cursor project's pane, from the cache: no file is read here."""
        pane = self.query_one("#detail", Static)
        row = self.query_one("#projects", Grid).cursor_coordinate.row
        if not 0 <= row < len(self.names):  # fires during table.clear()
            pane.update(Text(""))
            return
        name = self.names[row]
        d = self.details.get(name)
        if d is None:
            pane.update(Text(f"{name}\nloading…", style="dim"))
            return
        top, *rest = detail.lines(d, self.asof_week)
        out = Text(name, style="bold")
        out.append(f"\n{top}\n")
        if self.asof_week:
            out.append("burn chart is live only · L\n", style="dim")
        elif d.burn is not None and d.burn.months and d.burn.p90 + d.burn.spent:
            width = max(pane.size.width - 3, 12)
            out.append_text(burn_lines(d, width))
            fan = "fan seeded" if d.burn.p90 else "no fan"
            out.append(
                f"\nlabor only · cost lines {money(d.non_labor)} excluded"
                f" · {len(d.burn.reading_dates)} readings · {fan}\n",
                style="dim",
            )
        out.append("\n".join(rest))
        pane.update(out)

    @work(thread=True, exclusive=True, group="reload")
    def _reload(self) -> None:
        names = self.home.projects()  # a project made meanwhile shows up
        week = self.asof_week
        snaps = {n: self._snap(n, week) for n in names}
        self.call_from_thread(self._if_current, week, self._rebuild, names, snaps)
        self.call_from_thread(self._warm_all, True)

    def _snap(self, name: str, week: str | None) -> tuple:
        """snapshot, naming the week only when there is one."""
        if week:
            return snapshot(self.home, name, week)
        # the alert's file reads happen here, in the worker, never in _report
        self.hits[name] = alert_hits(self.home, name, self.rules)
        return snapshot(self.home, name)

    def _if_current(self, week: str | None, fn: Callable, *args) -> None:
        """Deliver a worker's result only if the view is still the one it began in."""
        if week == self.asof_week:
            fn(*args)

    def _rebuild(self, names: list[str], snaps: dict) -> None:
        table = self.query_one("#projects", Grid)
        at = table.cursor_coordinate
        table.clear()
        self.names = names
        self.changes = {}
        for name in names:
            cells, self.changes[name] = snaps[name]
            table.add_row(*cells, key=name)
        table.move_cursor(row=at.row, column=at.column)
        self._report()

    def on_app_focus(self) -> None:
        """Back in front (a hop in perch suite): refresh behind the table, so the
        hop is instant and the cells catch up a moment later."""
        self._refresh_behind()
        self._warm_all()  # unforced: only projects whose files changed

    @work(thread=True, exclusive=True, group="focus")
    def _refresh_behind(self) -> None:
        week = self.asof_week
        snaps = {name: self._snap(name, week) for name in self.names}
        self.call_from_thread(self._if_current, week, self._fill, snaps)

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
        """Toast each stoplight flip, then each fresh alert, once; none in history.

        More than three pending become one summary toast.
        """
        self._paint_detail()  # a move to the same cell fires no highlight
        if self.asof_week:
            return
        pending = []  # (seen set, key, text, severity)
        for name in self.names:
            moved = self.changes.get(name)
            if moved and moved.signal and (name, moved.after) not in self.alerted:
                old, new = (s.upper() for s in moved.signal)
                pending.append(
                    (
                        self.alerted,
                        (name, moved.after),
                        f"{name}: stoplight {old} → {new} ({moved.after[5:]})",
                        "error" if new == "RED" else "warning",
                    )
                )
        for name in self.names:
            for s in self.hits.get(name, []):
                key = (name, s.rule.index, s.week)
                if key not in self.fired:
                    pending.append((self.fired, key, _alerts.toast_text(s), "warning"))
        for seen, key, _, _ in pending:
            seen.add(key)
        if len(pending) > 3:
            self.notify(
                f"{len(pending)} changes: stoplight flips and alerts, see the tape"
            )
            return
        for _, _, text, severity in pending:
            self.notify(text, severity=severity)

    def action_asof(self, delta: int) -> None:
        self._go(self.asof_week, delta, "")

    def action_live(self) -> None:
        if self.asof_week:
            self._go(self.asof_week, 0, "LIVE")

    @work(thread=True, exclusive=True, group="asof")
    def _go(self, base: str | None, delta: int, text: str) -> None:
        """Resolve the target week, read every project as of it and the tape too,
        all off the UI thread; `_enter_asof` then swaps the view in one go.
        Known limit: two rapid `[` can read the same base and lose a step."""
        worker = get_current_worker()
        names = list(self.names)
        rows = []
        for n in names:
            try:
                config = load_config(self.home.config_path(n), require_dump=False)
                rows.append(history.load(config.history))
            except _ERRORS:
                continue
        recorded = _asof.weeks(rows)
        try:
            week = (
                _asof.resolve(text, recorded)
                if text
                else _asof.step(recorded, base, delta)
            )
        except ValueError as exc:
            self.call_from_thread(self.notify, str(exc), severity="error")
            return
        if not text and len(recorded) < 2:
            self.call_from_thread(
                self.notify, "only one week recorded: nothing to step to"
            )
            return
        snaps = {n: self._snap(n, week) for n in names}
        tapes = {
            n: tape.project_tape(s, n, date.today(), asof=week)  # noqa: DTZ011
            for n, s in dict(self.src).items()
        }
        if worker.is_cancelled:
            return
        try:
            self.call_from_thread(self._enter_asof, week, names, snaps, tapes)
        except RuntimeError:  # the app closed under the worker
            return

    def _enter_asof(
        self, week: str | None, names: list[str], snaps: dict, tapes: dict
    ) -> None:
        self.asof_week = week
        banner = self.query_one("#asof", Static)
        banner.update(
            Text(f"AS OF {week} · history, not live · [ ] step · L live")
            if week
            else Text("")
        )
        banner.display = week is not None
        self.query_one("#projects", Grid).set_class(week is not None, "historical")
        self.tape_by = tapes
        self._rebuild(names, snaps)
        self._paint_tape()

    def _na(self) -> None:
        week = (self.asof_week or "").split("-")[-1]
        self.notify(f"as of {week}: n/a, press L for live")

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

    def action_events_all(self) -> None:
        if self._free():
            self._start(None, "events --all", ["events", "--all"], refresh=False)

    def _start(
        self, name: str | None, action: str, args: list[str], refresh: bool = True
    ) -> None:
        """Run perch on one project, or on every project when ``name`` is None."""
        self.busy = action
        card = self._show(RunCard(f"{action} · {name}" if name else action))
        width = max(
            self.query_one("#output").size.width - 4, 40
        )  # the card's inside: tables fit it
        env = {"FORCE_COLOR": "1", "COLUMNS": str(width), blocks.ENV: "1"}
        self._stream(card, name, [str(_bin_dir() / "perch"), *args], env, refresh)

    def on_grid_go(self) -> None:
        """Enter: a step's cell runs that step; any other column, the next one."""
        if self.asof_week:
            self._na()
            return
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
        self,
        card: RunCard,
        name: str | None,
        argv: list[str],
        env: dict[str, str],
        refresh: bool = True,
    ) -> None:
        """In a thread: every touch of the app goes through call_from_thread.

        The exit code is `_spawn`'s return value, not a line of its output.
        """
        pending, code = None, 0
        try:
            run = _spawn(argv, self.home.root, self._hold, env)
            while True:
                try:
                    line = next(run)
                except StopIteration as done:
                    code = done.value or 0
                    break
                if pending is not None:
                    self.call_from_thread(card.put, pending)
                pending = line
        except OSError as exc:
            code, pending = 1, f"{pending}\n{exc}" if pending else str(exc)
        finally:
            if pending is not None:
                self.call_from_thread(card.put, pending)
            self.call_from_thread(self._finished, name, card, code, refresh)

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

    def _finished(
        self, name: str | None, card: RunCard, code: int, refresh: bool = True
    ) -> None:
        """Close the card; refresh the row that ran (every row after `a`).

        A failure adds the project's FIX lines to its card.
        """
        self.child = None
        self.busy = None
        card.finish(code)
        self.query_one("#output", VerticalScroll).scroll_end(animate=False)
        if not refresh:  # a read-only command: no row changed
            return
        if name not in self.names:  # None (`a`), or a project gone meanwhile
            self.action_refresh()
            return
        self._row_done(name, card, code)
        self._warm_all(True)

    @work(thread=True, group="row")
    def _row_done(self, name: str, card: RunCard, code: int) -> None:
        week = self.asof_week
        snap = self._snap(name, week)
        checks = project_checks(self.home, name) if code else []
        self.call_from_thread(
            self._if_current, week, self._apply_row, name, card, snap, checks
        )

    def _apply_row(self, name: str, card: RunCard, snap: tuple, checks: list) -> None:
        if name not in self.names:  # removed while the worker ran
            return
        table = self.query_one("#projects", Grid)
        at = self.names.index(name)
        cells, self.changes[name] = snap
        for col, cell in enumerate(cells):
            table.update_cell_at(Coordinate(at, col), cell, update_width=True)
        self._report()
        for check in checks:  # ponytail: `a` (monday --all) gets no FIX lines
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
        if _asof.is_command(event.value):
            self._go(self.asof_week, 0, _asof.argument(event.value))
            return
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
        if self.asof_week and (column == "Flags" or column in STEPS):
            self._na()
            return
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
                rows = history.load(config.history)
                if self.asof_week:
                    rows = _asof.until(rows, self.asof_week)
                lines = team_lines(rows)
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

    def action_walk(self) -> None:
        """Hand the terminal to Claude's /walk for the selected project."""
        from perch.core import walk as command
        from perch.core.steps import walk

        name = self._selected() if self._free() else None
        if name is None:
            return
        try:  # a workspace perch cannot write to is a toast, not a crash
            lines = command.install(self.home)
        except _ERRORS as exc:
            self.notify(f"{name}: {exc}", severity="error")
            return
        step = walk(self.home, name)
        with self.suspend():
            subprocess.run(step.argv, cwd=step.cwd, check=False)
        for line in lines:  # after the walk: a toast posted earlier expires unseen
            if line.startswith("left"):
                self.notify(line, severity="warning", timeout=30)
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
            listed = subprocess.run(
                windows(), capture_output=True, text=True, check=False
            )
            if listed.returncode:  # an empty listing would spawn a duplicate
                done = listed
            else:
                current = entry_of(listed.stdout, target)
                argv = hop(target, apps[target], json.dumps(apps), current)
                done = subprocess.run(argv, capture_output=True, text=True, check=False)
                if not done.returncode and argv[3] != "select-window":
                    time.sleep(0.5)  # new-window exits 0 even if the app crashes
                    after = subprocess.run(
                        windows(), capture_output=True, text=True, check=False
                    ).stdout
                    if entry_of(after, target) is None:
                        self.notify(f"{target}: exited at startup", severity="error")
        except OSError as exc:
            self.notify(f"{target}: switch failed: {exc}", severity="error")
            return
        if done.returncode:
            self.notify(
                f"{target}: switch failed: {done.stderr.strip() or 'tmux failed'}",
                severity="error",
            )
