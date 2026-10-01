"""perch tui: the projects table and the keys, with every subprocess faked.

Plain `def` tests that drive `App.run_test()` through `asyncio.run`, so perch
needs no pytest-asyncio.
"""

import asyncio
import json
import subprocess
import sys
import threading
from contextlib import nullcontext
from pathlib import Path

import pytest
from textual.widgets import DataTable, Input, Log

from perch import tui
from perch.core.watch import PLAN, PersonWatch, Signal, Watch
from perch.tests.conftest import build_home

PERCH = str(Path(sys.executable).parent / "perch")


def _cells(app) -> list[list[str]]:
    table = app.query_one(DataTable)
    return [[str(c) for c in table.get_row_at(i)] for i in range(table.row_count)]


def _log(app) -> list[str]:
    return list(app.query_one(Log).lines)


def _team_row(home, name, headroom, signal):
    path = home.projects_dir / name / "history.jsonl"
    row = {"week": "2026-W17", "date": "2026-04-20", "kind": "team", "name": "team"}
    path.write_text(json.dumps({**row, "headroom": headroom, "signal": signal}) + "\n")


@pytest.fixture
def spawned(monkeypatch):
    """Every argv the TUI spawns, with its cwd; each prints one line."""
    calls = []

    def fake(argv, cwd):
        calls.append((list(argv), cwd))
        yield "ran"

    monkeypatch.setattr(tui, "_spawn", fake)
    return calls


def run(app, script):
    async def go():
        async with app.run_test(size=(160, 30)) as pilot:
            await script(app, pilot)

    asyncio.run(go())


async def settle(app, pilot):
    await app.workers.wait_for_complete()
    await pilot.pause()


def test_the_table_has_every_project_and_its_last_recorded_week(tmp_path):
    home = build_home(tmp_path, "apollo", "beta")
    _team_row(home, "apollo", 12345.0, "yellow")

    async def script(app, pilot):
        rows = _cells(app)
        assert [r[0] for r in rows] == ["apollo", "beta"]
        assert rows[0][1] == "grp/apollo"
        assert rows[0][2:4] == ["YELLOW", "$12,345"]
        assert rows[1][2:4] == ["—", "—"]  # no history yet
        assert "never" not in rows[0][4:6]  # the dump and weekly.csv exist
        assert rows[0][6] == "—"  # under 4 weeks of history: no watch yet

    run(tui.PerchTUI(home), script)


def test_the_flag_column_counts_the_watch_flags(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    page = Watch("t", [PersonWatch("Alice", (Signal(PLAN, True, "x", 4),))])
    monkeypatch.setattr(tui, "_watch", lambda path: page)

    async def script(app, pilot):
        assert _cells(app)[0][6] == "1"

    run(tui.PerchTUI(home), script)


def test_a_project_without_a_dump_has_no_flag_count(tmp_path):
    home = build_home(tmp_path, "apollo")
    (home.projects_dir / "apollo" / "dump.json").unlink()

    async def script(app, pilot):
        row = _cells(app)[0]
        assert row[4] == "never"
        assert row[6] == "—"

    run(tui.PerchTUI(home), script)


def test_a_broken_project_is_an_error_row(tmp_path):
    home = build_home(tmp_path, "apollo", "beta")
    home.config_path("apollo").write_text("people: [unclosed\n")

    async def script(app, pilot):
        rows = _cells(app)
        assert rows[0][0] == "apollo"
        assert "not valid YAML" in rows[0][1]
        assert rows[1][1] == "grp/beta"

    run(tui.PerchTUI(home), script)


def test_each_key_runs_its_command_on_the_selected_project(tmp_path, spawned):
    home = build_home(tmp_path, "apollo", "beta")
    keys = {
        "b": ["board", "-p", "apollo"],
        "m": ["monday", "-p", "apollo"],
        "a": ["monday", "--all"],  # cli refuses -p with --all
        "d": ["doctor", "-p", "apollo"],
        "f": ["forecast", "-p", "apollo"],
        "w": ["watch", "-p", "apollo"],
        "Q": ["quarterly", "-p", "apollo"],
    }

    async def script(app, pilot):
        for key in keys:
            await pilot.press(key)
            await settle(app, pilot)
        assert [argv for argv, _ in spawned] == [[PERCH, *a] for a in keys.values()]
        assert {cwd for _, cwd in spawned} == {home.root}
        assert _log(app)[-1] == "apollo: ran"
        assert "all: ran" in _log(app)

    run(tui.PerchTUI(home), script)


def test_moving_the_cursor_changes_the_project(tmp_path, spawned):
    home = build_home(tmp_path, "apollo", "beta")

    async def script(app, pilot):
        await pilot.press("down", "b")
        await settle(app, pilot)  # the table refreshes after the command
        await pilot.press("f")
        await settle(app, pilot)
        assert [argv[1:] for argv, _ in spawned] == [
            ["board", "-p", "beta"],
            ["forecast", "-p", "beta"],
        ]

    run(tui.PerchTUI(home), script)


def test_c_passes_the_typed_flags_to_cut(tmp_path, spawned):
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        await pilot.press("c")
        box = app.query_one(Input)
        assert box.display and box.has_focus
        box.value = "--leaves Bob:2026-11-01 --budget 700000"
        await pilot.press("enter")
        await settle(app, pilot)
        assert spawned[0][0][1:] == [
            "cut", "-p", "apollo", "--leaves", "Bob:2026-11-01", "--budget", "700000",
        ]  # fmt: skip
        assert not box.display

    run(tui.PerchTUI(home), script)


def test_h_edits_weekly_csv_in_a_suspended_app_then_refreshes(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.setenv("EDITOR", "myeditor -w")
    monkeypatch.setattr(tui.PerchTUI, "suspend", lambda self: nullcontext())
    edited = []

    def editor(argv, cwd, check):
        edited.append(list(argv))
        _team_row(home, "apollo", 500.0, "green")  # what the table must now show

    monkeypatch.setattr(subprocess, "run", editor)

    async def script(app, pilot):
        assert _cells(app)[0][2] == "—"
        await pilot.press("h")
        await pilot.pause()
        weekly = home.projects_dir / "apollo" / "fy26" / "weekly.csv"
        assert edited == [["myeditor", "-w", str(weekly)]]
        assert _cells(app)[0][2:4] == ["GREEN", "$500"]

    run(tui.PerchTUI(home), script)


def test_a_key_while_a_command_runs_says_busy(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    release = threading.Event()
    calls = []

    def slow(argv, cwd):
        calls.append(argv)
        release.wait(5)
        yield "done"

    monkeypatch.setattr(tui, "_spawn", slow)

    async def script(app, pilot):
        await pilot.press("b")
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        release.set()
        await settle(app, pilot)
        assert "busy: board" in _log(app)
        assert len(calls) == 1
        await pilot.press("m")  # free again once it finished
        await settle(app, pilot)
        assert len(calls) == 2

    try:
        run(tui.PerchTUI(home), script)
    finally:
        release.set()


def test_perch_tui_outside_a_workspace_says_how_to_start(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from perch.cli import cli

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["tui"])
    assert result.exit_code == 1
    assert "perch-home.yaml" in result.output
