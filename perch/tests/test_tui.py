"""perch tui: the projects table and the keys, with every subprocess faked.

Plain `def` tests that drive `App.run_test()` through `asyncio.run`, so perch
needs no pytest-asyncio.
"""

import asyncio
import json
import os
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

    def fake(argv, cwd, started):
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
        assert [c for c in tui.COLUMNS[4:11]] == list(tui.STEPS)
        assert rows[0][11] == "—"  # under 4 weeks of history: no watch yet

    run(tui.PerchTUI(home), script)


def test_the_flag_column_counts_the_watch_flags(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    page = Watch("t", [PersonWatch("Alice", (Signal(PLAN, True, "x", 4),))], 4)
    monkeypatch.setattr(tui, "_watch", lambda path: page)

    async def script(app, pilot):
        assert _cells(app)[0][11] == "1"

    run(tui.PerchTUI(home), script)


def test_a_project_without_a_dump_has_no_flag_count(tmp_path):
    home = build_home(tmp_path, "apollo")
    (home.projects_dir / "apollo" / "dump.json").unlink()

    async def script(app, pilot):
        row = _cells(app)[0]
        assert row[5] == "·"  # fetch: no dump
        assert row[11] == "—"

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


def test_h_falls_back_to_vim_when_editor_is_unset(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr(tui.PerchTUI, "suspend", lambda self: nullcontext())
    edited = []
    monkeypatch.setattr(subprocess, "run", lambda argv, cwd, check: edited.append(argv))

    async def script(app, pilot):
        await pilot.press("h")
        await pilot.pause()
        assert edited[0][0] == "vim"

    run(tui.PerchTUI(home), script)


def test_a_key_while_a_command_runs_says_busy(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    release = threading.Event()
    calls = []

    def slow(argv, cwd, started):
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


def test_a_corrupt_history_is_an_error_row(tmp_path):
    home = build_home(tmp_path, "apollo")
    (home.projects_dir / "apollo" / "history.jsonl").write_text("{not json\n")

    async def script(app, pilot):
        assert _cells(app)[0][1].startswith("error: ")

    run(tui.PerchTUI(home), script)


def test_a_malformed_dump_is_an_error_row_and_the_others_still_render(tmp_path):
    home = build_home(tmp_path, "apollo", "beta")
    dump = home.projects_dir / "apollo" / "dump.json"
    closed = {"iid": 1, "title": "t", "state": "closed", "closed_at": 5}
    bad = [{**closed, "labels": [], "transitions": []}]  # AttributeError on load
    dump.write_text(json.dumps({**json.loads(dump.read_text()), "history": bad}))

    async def script(app, pilot):
        rows = _cells(app)
        assert rows[0][11] == "—"  # the watch cannot read that dump
        assert rows[1][1] == "grp/beta"

    run(tui.PerchTUI(home), script)


def test_a_row_that_raises_anything_shows_the_error(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "beta")

    def broken(path):
        if "apollo" in str(path):
            raise AttributeError("no fetched_at")
        return original(path)

    original = tui.latest_week
    monkeypatch.setattr(tui, "latest_week", broken)

    async def script(app, pilot):
        rows = _cells(app)
        assert rows[0][1] == "error: AttributeError: no fetched_at"
        assert rows[1][1] == "grp/beta"

    run(tui.PerchTUI(home), script)


def test_escape_closes_the_cut_input_without_running_anything(tmp_path, spawned):
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        await pilot.press("c")
        box = app.query_one(Input)
        box.value = "--budget 700000"
        await pilot.press("escape")
        await settle(app, pilot)
        assert not box.display and box.value == ""
        assert app.query_one(DataTable).has_focus
        assert spawned == []

    run(tui.PerchTUI(home), script)


class _Proc:
    """Process-like: terminate() is recorded and lets the fake's stream end."""

    def __init__(self):
        self.ended = threading.Event()
        self.terminated = 0

    def poll(self):
        return 0 if self.ended.is_set() else None

    def terminate(self):
        self.terminated += 1
        self.ended.set()

    def wait(self, timeout=None):
        return 0

    def kill(self):
        raise AssertionError("terminate was enough")


def test_quitting_while_a_command_runs_terminates_the_child(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    proc = _Proc()

    def long(argv, cwd, started):
        started(proc)
        proc.ended.wait(5)
        yield "cut short"

    monkeypatch.setattr(tui, "_spawn", long)

    async def script(app, pilot):
        await pilot.press("b")
        await pilot.pause()
        while app.child is None:
            await pilot.pause()
        await pilot.press("q")

    run(tui.PerchTUI(home), script)
    assert proc.terminated == 1


def test_quitting_with_nothing_running_is_fine(tmp_path, spawned):
    async def script(app, pilot):
        await pilot.press("q")

    run(tui.PerchTUI(build_home(tmp_path, "apollo")), script)


# --- switching to Budgie and gitboard (PI_SUITE) ----------------------------

BIN = Path(sys.executable).parent


def test_suite_map_points_each_app_at_the_selected_project(tmp_path):
    home = build_home(tmp_path, "apollo")
    m = tui.suite_map(home, "apollo")
    assert m["perch"] == {"cwd": str(home.root), "argv": [str(BIN / "perch"), "tui"]}
    assert m["budgie"] == {
        "cwd": str((home.projects_dir / "apollo" / "fy26").resolve()),
        "argv": [str(BIN / "budgie"), "tui"],
    }
    assert m["gitboard"] == {
        "cwd": str(home.gitboard_dir),
        "argv": ["gitboard", "tui", "grp/apollo"],
    }


def test_suite_map_without_a_gitlab_project_lets_gitboard_choose(tmp_path):
    home = build_home(tmp_path, "apollo", gitlab=False)
    assert tui.suite_map(home, "apollo")["gitboard"]["argv"] == ["gitboard", "tui"]


def test_b_and_g_set_pi_suite_and_exit_with_the_target(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    for key, target in (("B", "budgie"), ("G", "gitboard")):
        monkeypatch.setenv("PI_SUITE", "")  # restored after the test
        app = tui.PerchTUI(home)

        async def script(app, pilot, key=key):
            await pilot.press(key)
            await pilot.pause()

        run(app, script)
        assert app.return_value == target
        assert json.loads(os.environ["PI_SUITE"]) == tui.suite_map(home, "apollo")


def test_switching_while_a_command_runs_says_busy(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    release = threading.Event()

    def slow(argv, cwd, started):
        release.wait(5)
        yield "done"

    monkeypatch.setattr(tui, "_spawn", slow)

    async def script(app, pilot):
        await pilot.press("b")
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()
        assert "busy: board" in _log(app)
        assert app.is_running
        release.set()
        await settle(app, pilot)

    try:
        run(tui.PerchTUI(home), script)
    finally:
        release.set()


def test_switch_chdirs_then_execs(monkeypatch):
    calls = []
    monkeypatch.setattr(os, "chdir", lambda d: calls.append(("chdir", d)))
    monkeypatch.setattr(os, "execvp", lambda f, a: calls.append(("exec", f, a)))
    tui.switch({"cwd": "/b", "argv": ["budgie", "tui"]})
    assert calls == [("chdir", "/b"), ("exec", "budgie", ["budgie", "tui"])]


def test_switch_that_cannot_exec_says_why(tmp_path):
    with pytest.raises(SystemExit) as exc:
        tui.switch({"cwd": str(tmp_path / "gone"), "argv": ["budgie", "tui"]})
    assert "switch failed" in str(exc.value.code)


def test_perch_tui_execs_the_target_it_exited_with(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from perch.cli import cli

    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    entry = {"cwd": "/b", "argv": ["budgie", "tui"]}
    monkeypatch.setenv("PI_SUITE", json.dumps({"budgie": entry}))
    monkeypatch.setattr(tui.PerchTUI, "run", lambda self: "budgie")
    switched = []
    monkeypatch.setattr(tui, "switch", switched.append)
    assert CliRunner().invoke(cli, ["tui"]).exit_code == 0
    assert switched == [entry]


# --- the Monday grid: step cells, Enter, FAIL, one-row refresh ---------------


def _fail(home, name, step="board"):
    from datetime import datetime

    from perch.core.status import record_failure
    from perch.core.steps import iso_week

    now = datetime.now()  # noqa: DTZ005
    record_failure(home, name, iso_week(now.date()), step, 2, now)


def test_a_recorded_failure_shows_a_fail_cell(tmp_path):
    home = build_home(tmp_path, "apollo")
    _fail(home, "apollo", "board")

    async def script(app, pilot):
        row = _cells(app)[0]
        assert row[6] == "FAIL"  # board
        assert row[7] != "FAIL"

    run(tui.PerchTUI(home), script)


def test_enter_on_a_step_cell_runs_monday_from_that_step(tmp_path, spawned):
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        app.query_one(DataTable).move_cursor(row=0, column=tui.COLUMNS.index("weekly"))
        await pilot.press("enter")
        await settle(app, pilot)
        assert [a[1:] for a, _ in spawned] == [
            ["monday", "-p", "apollo", "--from", "weekly"]
        ]

    run(tui.PerchTUI(home), script)


def test_enter_on_watch_runs_watch(tmp_path, spawned):
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        app.query_one(DataTable).move_cursor(row=0, column=tui.COLUMNS.index("watch"))
        await pilot.press("enter")
        await settle(app, pilot)
        assert [a[1:] for a, _ in spawned] == [["watch", "-p", "apollo"]]

    run(tui.PerchTUI(home), script)


def test_enter_on_the_project_cell_runs_the_next_step(tmp_path, spawned, monkeypatch):
    home = build_home(tmp_path, "apollo")
    from perch.core.status import Cell

    cells = {s: Cell("done", "now") for s in tui.STEPS} | {"digest": Cell("todo", "")}
    monkeypatch.setattr(tui, "status", lambda *a: cells)

    async def script(app, pilot):
        await pilot.press("enter")  # cursor starts on the Project cell
        await settle(app, pilot)
        assert [a[1:] for a, _ in spawned] == [
            ["monday", "-p", "apollo", "--from", "digest"]
        ]
        cells["digest"] = Cell("done", "now")
        await pilot.press("enter")
        await settle(app, pilot)
        assert len(spawned) == 1
        assert "apollo: Monday done" in _log(app)

    run(tui.PerchTUI(home), script)


def test_a_failing_run_logs_the_projects_fix_lines(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "beta", gitlab=False)

    def fake(argv, cwd, started):
        yield "boom"
        yield "exited 2"

    monkeypatch.setattr(tui, "_spawn", fake)

    async def script(app, pilot):
        await pilot.press("down", "m")  # beta has no gitlab_project
        await settle(app, pilot)
        fixes = [x for x in _log(app) if "FIX" in x]
        assert len(fixes) == 1 and fixes[0].startswith("beta: FIX  ")
        assert "gitlab_project" in fixes[0] and "  ->  " in fixes[0]

    run(tui.PerchTUI(home), script)


def test_a_passing_run_logs_no_fix_lines(tmp_path, spawned):
    home = build_home(tmp_path, "apollo", gitlab=False)

    async def script(app, pilot):
        await pilot.press("m")
        await settle(app, pilot)
        assert not [x for x in _log(app) if "FIX" in x]

    run(tui.PerchTUI(home), script)


def test_after_a_run_only_that_row_refreshes_and_the_cursor_stays(
    tmp_path, spawned, monkeypatch
):
    home = build_home(tmp_path, "apollo", "beta")
    calls = []
    original = tui.row
    monkeypatch.setattr(tui, "row", lambda h, n: calls.append(n) or original(h, n))

    async def script(app, pilot):
        calls.clear()
        table = app.query_one(DataTable)
        table.move_cursor(row=1, column=3)
        await pilot.press("b")
        await settle(app, pilot)
        assert calls == ["beta"]
        assert table.cursor_coordinate == (1, 3)
        await pilot.press("a")
        await settle(app, pilot)
        assert calls == ["beta", "apollo", "beta"]

    run(tui.PerchTUI(home), script)


def test_a_click_on_the_cursor_cell_runs_nothing(tmp_path, spawned, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.setattr(
        tui.PerchTUI, "action_hours", lambda self: spawned.append("hours")
    )

    async def script(app, pilot):
        await pilot.click("#projects", offset=(2, 1))  # the Project cell, row 0
        await pilot.click("#projects", offset=(2, 1))  # again: DataTable "selects"
        await settle(app, pilot)
        assert spawned == []

    run(tui.PerchTUI(home), script)


def test_monday_all_refreshes_every_row_even_with_a_project_named_all(
    tmp_path, spawned, monkeypatch
):
    home = build_home(tmp_path, "all", "beta")
    calls = []
    original = tui.row
    monkeypatch.setattr(tui, "row", lambda h, n: calls.append(n) or original(h, n))

    async def script(app, pilot):
        calls.clear()
        await pilot.press("a")
        await settle(app, pilot)
        assert calls == ["all", "beta"]

    run(tui.PerchTUI(home), script)
