"""perch tui: the projects table and the keys, with every subprocess faked.

Plain `def` tests that drive `App.run_test()` through `asyncio.run`, so perch
needs no pytest-asyncio.
"""

import asyncio
import io
import json
import os
import subprocess
import sys
import threading
from contextlib import nullcontext
from datetime import date
from pathlib import Path

import pytest
from textual.widgets import DataTable, Input, Static
from textual.worker import WorkerCancelled

from perch import tui
from perch.core import asof as _asof
from perch.core import blocks as b
from perch.core import tape
from perch.core.watch import PLAN, PersonWatch, Signal, Watch
from perch.tests.conftest import build_home

PERCH = str(Path(sys.executable).parent / "perch")


def _cells(app) -> list[list[str]]:
    table = app.query_one(DataTable)
    return [[str(c) for c in table.get_row_at(i)] for i in range(table.row_count)]


def _cards(app) -> list[tuple[str, str, str]]:
    """(title, body, status) of each run card, oldest first."""
    return [
        (c.border_title, c.body.plain, c.border_subtitle)
        for c in app.query(tui.RunCard)
    ]


def _notices(app) -> list[str]:
    return [n.message for n in app._notifications]


def _team_row(home, name, headroom, signal):
    path = home.projects_dir / name / "history.jsonl"
    row = {"week": "2026-W17", "date": "2026-04-20", "kind": "team", "name": "team"}
    path.write_text(json.dumps({**row, "headroom": headroom, "signal": signal}) + "\n")


@pytest.fixture
def spawned(monkeypatch):
    """Every argv the TUI spawns, with its cwd; each prints one line."""
    calls = []

    def fake(argv, cwd, started, env=None):
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
    while True:
        try:  # an exclusive worker (the slow tier) cancels its predecessor
            await app.workers.wait_for_complete()
            break
        except WorkerCancelled:
            continue
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
        assert [c for c in tui.COLUMNS[5:12]] == list(tui.STEPS)
        assert rows[0][12] == "—"  # under 4 weeks of history: no watch yet

    run(tui.PerchTUI(home), script)


def test_the_flag_column_counts_the_watch_flags(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    page = Watch("t", [PersonWatch("Alice", (Signal(PLAN, True, "x", 4),))], 4)
    monkeypatch.setattr(tui, "_watch", lambda path: page)

    async def script(app, pilot):
        assert _cells(app)[0][12] == "1"

    run(tui.PerchTUI(home), script)


def test_a_project_without_a_dump_has_no_flag_count(tmp_path):
    home = build_home(tmp_path, "apollo")
    (home.projects_dir / "apollo" / "dump.json").unlink()

    async def script(app, pilot):
        row = _cells(app)[0]
        assert row[6] == "·"  # fetch: no dump
        assert row[12] == "—"

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
        assert _cards(app)[-1][:2] == ("quarterly · apollo", "ran")
        assert ("monday --all", "ran") in [c[:2] for c in _cards(app)]

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

    def slow(argv, cwd, started, env=None):
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
        assert "busy: board" in _notices(app)
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
    result = CliRunner().invoke(cli, ["tui", "--no-suite"])
    assert result.exit_code == 1
    assert "perch-home.yaml" in result.output


def test_a_corrupt_history_is_an_error_row(tmp_path):
    home = build_home(tmp_path, "apollo")
    (home.projects_dir / "apollo" / "history.jsonl").write_text("{not json\n")

    async def script(app, pilot):
        assert _cells(app)[0][1].startswith("error: ")

    run(tui.PerchTUI(home), script)


def test_a_history_row_without_a_week_is_an_error_row(tmp_path):
    home = build_home(tmp_path, "apollo")
    (home.projects_dir / "apollo" / "history.jsonl").write_text(
        '{"kind": "team", "name": "team"}\n'
    )

    async def script(app, pilot):
        assert _cells(app)[0][1] == "error: KeyError: 'week'"

    run(tui.PerchTUI(home), script)


def test_negative_headroom_has_a_real_minus_sign(tmp_path):
    home = build_home(tmp_path, "apollo")
    _team_row(home, "apollo", -12000, "red")

    async def script(app, pilot):
        assert _cells(app)[0][3] == "−$12,000"

    run(tui.PerchTUI(home), script)


def test_a_malformed_dump_is_an_error_row_and_the_others_still_render(tmp_path):
    home = build_home(tmp_path, "apollo", "beta")
    dump = home.projects_dir / "apollo" / "dump.json"
    closed = {"iid": 1, "title": "t", "state": "closed", "closed_at": 5}
    bad = [{**closed, "labels": [], "transitions": []}]  # AttributeError on load
    dump.write_text(json.dumps({**json.loads(dump.read_text()), "history": bad}))

    async def script(app, pilot):
        rows = _cells(app)
        assert rows[0][12] == "—"  # the watch cannot read that dump
        assert rows[1][1] == "grp/beta"

    run(tui.PerchTUI(home), script)


def test_a_row_that_raises_anything_shows_the_error(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "beta")

    def broken(path):
        if "apollo" in str(path):
            raise AttributeError("no fetched_at")
        return original(path)

    original = tui.history.load
    monkeypatch.setattr(tui.history, "load", broken)

    async def script(app, pilot):
        rows = _cells(app)
        assert rows[0][1] == "error: AttributeError: no fetched_at"
        assert rows[1][1] == "grp/beta"

    run(tui.PerchTUI(home), script)


def test_escape_closes_the_cut_input_without_running_anything(tmp_path, spawned):
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        await pilot.press("colon")
        box = app.query_one(Input)
        box.value = "apollo CUT 700k"
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

    def long(argv, cwd, started, env=None):
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
        "project": "apollo",
    }
    assert m["gitboard"] == {
        "cwd": str(home.gitboard_dir),
        "argv": ["gitboard", "tui", "grp/apollo"],
        "project": "apollo",
    }


def test_suite_map_without_a_gitlab_project_lets_gitboard_choose(tmp_path):
    home = build_home(tmp_path, "apollo", gitlab=False)
    assert tui.suite_map(home, "apollo")["gitboard"]["argv"] == ["gitboard", "tui"]


def test_b_and_g_set_pi_suite_and_exit_with_the_target(tmp_path, monkeypatch):
    monkeypatch.delenv("TMUX", raising=False)
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
    monkeypatch.delenv("TMUX", raising=False)
    home = build_home(tmp_path, "apollo")
    release = threading.Event()

    def slow(argv, cwd, started, env=None):
        release.wait(5)
        yield "done"

    monkeypatch.setattr(tui, "_spawn", slow)

    async def script(app, pilot):
        await pilot.press("b")
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()
        assert "busy: board" in _notices(app)
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
    assert CliRunner().invoke(cli, ["tui", "--no-suite"]).exit_code == 0
    assert switched == [entry]


# --- in perch suite: hop to the window, never exit ---------------------------

SUITE_TMUX = "/private/tmp/tmux-501/pi,123,0"


@pytest.fixture
def hops(monkeypatch):
    """In the suite; every tmux argv run, list-windows answering .listing."""
    calls = []

    class Fake:
        listing = ""
        stderr = ""  # non-empty: the hop call fails with it
        fail = False  # True: fails even with empty stderr
        list_fail = ""  # non-empty: list-windows itself fails with it
        dies = False  # True: a spawned window is gone when looked at again

    def run(argv, **kw):
        calls.append(list(argv))
        if "list-windows" in argv:
            if Fake.list_fail:
                return subprocess.CompletedProcess(argv, 1, "", Fake.list_fail)
            spawned = any(c[3] in ("new-window", "respawn-window") for c in calls)
            up = spawned and not Fake.dies
            listing = "perch\t{}\nbudgie\t{}\ngitboard\t{}\n" if up else Fake.listing
            return subprocess.CompletedProcess(argv, 0, listing, "")
        return subprocess.CompletedProcess(
            argv, 1 if Fake.stderr or Fake.fail else 0, "", Fake.stderr
        )

    Fake.calls = calls
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(tui.time, "sleep", lambda s: None)
    monkeypatch.setenv("TMUX", SUITE_TMUX)
    monkeypatch.setenv("PI_SUITE", "untouched")
    return Fake


def test_in_suite_b_hops_and_perch_keeps_running(tmp_path, hops):
    from perch.core import suite

    home = build_home(tmp_path, "apollo")
    m = tui.suite_map(home, "apollo")

    async def script(app, pilot):
        await pilot.press("B")
        await pilot.pause()
        assert app.is_running

    run(tui.PerchTUI(home), script)
    assert hops.calls == [
        suite.windows(),
        suite.hop("budgie", m["budgie"], json.dumps(m), None),
        suite.windows(),  # did the new window survive startup?
    ]
    assert os.environ["PI_SUITE"] == "untouched"


def test_in_suite_hopping_while_a_command_runs_is_fine(tmp_path, hops, monkeypatch):
    home = build_home(tmp_path, "apollo")
    release = threading.Event()

    def slow(argv, cwd, started, env=None):
        release.wait(5)
        yield "done"

    monkeypatch.setattr(tui, "_spawn", slow)

    async def script(app, pilot):
        await pilot.press("b")
        await pilot.pause()
        await pilot.press("G")
        await pilot.pause()
        assert not any(n.startswith("busy") for n in _notices(app))
        assert len(hops.calls) == 3
        release.set()
        await settle(app, pilot)

    try:
        run(tui.PerchTUI(home), script)
    finally:
        release.set()


def test_in_suite_a_failed_hop_says_why(tmp_path, hops):
    hops.stderr = "can't find window: gitboard"
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        await pilot.press("G")
        await pilot.pause()
        assert app.is_running
        assert "gitboard: switch failed: can't find window: gitboard" in _notices(app)

    run(tui.PerchTUI(home), script)


def test_in_suite_a_failed_hop_with_no_stderr_still_says_why(tmp_path, hops):
    hops.fail = True
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        await pilot.press("G")
        await pilot.pause()
        assert "gitboard: switch failed: tmux failed" in _notices(app)

    run(tui.PerchTUI(home), script)


def test_q_in_perch_suite_closes_the_suite(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from perch.cli import cli
    from perch.core import suite

    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    monkeypatch.setenv("TMUX", SUITE_TMUX)
    monkeypatch.setattr(tui.PerchTUI, "run", _fake_run(0))
    ran = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: ran.append(argv))
    assert CliRunner().invoke(cli, ["tui"]).exit_code == 0
    assert ran == [suite.kill()]


def _fake_run(code):
    def run(self):
        self._return_code = code

    return run


def test_a_crash_in_perch_suite_keeps_the_suite(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from perch.cli import cli

    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    monkeypatch.setenv("TMUX", SUITE_TMUX)
    monkeypatch.setattr(tui.PerchTUI, "run", _fake_run(1))
    ran = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: ran.append(argv))
    out = CliRunner().invoke(cli, ["tui"], input="\n")
    assert out.exit_code == 0
    assert ran == []
    assert "perch stopped with an error" in out.output


def test_a_crash_outside_the_suite_runs_no_tmux(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from perch.cli import cli

    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(tui.PerchTUI, "run", _fake_run(1))
    ran = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: ran.append(argv))
    assert CliRunner().invoke(cli, ["tui", "--no-suite"]).exit_code == 0
    assert ran == []


def test_q_outside_the_suite_just_quits(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from perch.cli import cli

    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(tui.PerchTUI, "run", lambda self: None)
    ran = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: ran.append(argv))
    assert CliRunner().invoke(cli, ["tui", "--no-suite"]).exit_code == 0
    assert ran == []


def test_switch_with_an_empty_program_says_why(tmp_path):
    with pytest.raises(SystemExit) as exc:
        tui.switch({"cwd": str(tmp_path), "argv": [""]})
    assert "switch failed" in str(exc.value.code)


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
        assert row[7] == "FAIL"  # board
        assert row[8] != "FAIL"

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
        assert "apollo: Monday done" in _notices(app)

    run(tui.PerchTUI(home), script)


def test_a_last_line_reading_exited_is_output_not_a_failure(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", gitlab=False)

    def fake(argv, cwd, started, env=None):
        yield "exited 3"
        return 0

    monkeypatch.setattr(tui, "_spawn", fake)

    async def script(app, pilot):
        await pilot.press("m")
        await settle(app, pilot)
        _, body, state = _cards(app)[-1]
        assert body == "exited 3" and state.startswith("✓")

    run(tui.PerchTUI(home), script)


def test_a_failing_run_logs_the_projects_fix_lines(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "beta", gitlab=False)

    def fake(argv, cwd, started, env=None):
        yield "boom"
        return 2

    monkeypatch.setattr(tui, "_spawn", fake)

    async def script(app, pilot):
        await pilot.press("down", "m")  # beta has no gitlab_project
        await settle(app, pilot)
        title, body, state = _cards(app)[-1]
        assert title == "monday · beta" and state.startswith("✗ exited 2")
        assert body.startswith("boom\n▲ FIX  ") and body.count("FIX") == 1
        assert "gitlab_project" in body and "→" in body

    run(tui.PerchTUI(home), script)


def test_a_passing_run_logs_no_fix_lines(tmp_path, spawned):
    home = build_home(tmp_path, "apollo", gitlab=False)

    async def script(app, pilot):
        await pilot.press("m")
        await settle(app, pilot)
        _, body, state = _cards(app)[-1]
        assert "FIX" not in body and state.startswith("✓ ")

    run(tui.PerchTUI(home), script)


def test_after_a_run_only_that_row_refreshes_and_the_cursor_stays(
    tmp_path, spawned, monkeypatch
):
    home = build_home(tmp_path, "apollo", "beta")
    calls = []
    original = tui.snapshot
    monkeypatch.setattr(tui, "snapshot", lambda h, n: calls.append(n) or original(h, n))

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


def _cell(app, column: str, row: int = 0) -> tuple[int, int]:
    """The offset of a cell in the projects grid, for pilot.click."""
    grid = app.query_one(tui.Grid)
    widths = [c.get_render_width(grid) for c in grid.columns.values()]
    return sum(widths[: tui.COLUMNS.index(column)]) + 1, row + 1  # +1: header


def test_a_click_on_a_step_cell_shows_its_info_card_and_runs_nothing(tmp_path, spawned):
    home = build_home(tmp_path, "apollo", "beta")

    async def script(app, pilot):
        await pilot.pause()
        await pilot.click("#projects", offset=_cell(app, "fetch", row=1))
        await settle(app, pilot)
        assert spawned == []
        title, body, status = _cards(app)[-1]
        assert (title, status) == ("fetch · beta", "info")
        assert "double-click or Enter runs fetch" in body

    run(tui.PerchTUI(home), script)


def test_a_double_click_on_a_step_cell_runs_that_step(tmp_path, spawned):
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        await pilot.pause()
        await pilot.click("#projects", offset=_cell(app, "fetch"), times=2)
        await settle(app, pilot)
        assert [argv[1:] for argv, _ in spawned] == [
            list(tui.next_command("apollo", "fetch"))
        ]

    run(tui.PerchTUI(home), script)


def test_a_click_on_a_step_cell_as_of_a_week_runs_nothing(tmp_path, spawned):
    home = build_home(tmp_path, "apollo")
    _weeks(home, "apollo", (100, "green"), (50, "green"))

    async def script(app, pilot):
        await pilot.pause()
        await pilot.press("left_square_bracket")
        await settle(app, pilot)
        before = len(_cards(app))
        await pilot.click("#projects", offset=_cell(app, "fetch"), times=2)
        await settle(app, pilot)
        assert spawned == [] and len(_cards(app)) == before
        assert any("n/a, press L for live" in n for n in _notices(app))

    run(tui.PerchTUI(home), script)


def test_monday_all_refreshes_every_row_even_with_a_project_named_all(
    tmp_path, spawned, monkeypatch
):
    home = build_home(tmp_path, "all", "beta")
    calls = []
    original = tui.snapshot
    monkeypatch.setattr(tui, "snapshot", lambda h, n: calls.append(n) or original(h, n))

    async def script(app, pilot):
        calls.clear()
        await pilot.press("a")
        await settle(app, pilot)
        assert calls == ["all", "beta"]

    run(tui.PerchTUI(home), script)


def test_a_run_card_keeps_the_tools_colours(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    seen = {}

    def fake(argv, cwd, started, env=None):
        seen.update(env)
        yield "\x1b[32mok\x1b[0m    weekly.csv"

    monkeypatch.setattr(tui, "_spawn", fake)

    async def script(app, pilot):
        await pilot.press("d")
        await settle(app, pilot)
        card = app.query_one(tui.RunCard)
        assert card.body.plain == "ok    weekly.csv"
        assert [s.style.color.number for s in card.body.spans] == [2]  # ANSI green
        assert seen["FORCE_COLOR"] == "1" and int(seen["COLUMNS"]) >= 40

    run(tui.PerchTUI(home), script)


def test_only_the_last_runs_keep_a_card(tmp_path, spawned, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.setattr(tui, "KEEP", 3)

    async def script(app, pilot):
        for key in "bdfw":
            await pilot.press(key)
            await settle(app, pilot)
        assert [c[0] for c in _cards(app)] == [
            "doctor · apollo",
            "forecast · apollo",
            "watch · apollo",
        ]

    run(tui.PerchTUI(home), script)


# --- the command line, drill, trend, strip, alerts ---------------------------


def _weeks(home, name, *figs):
    """Team rows from W36, one per (headroom, signal[, budget]), plus a person row."""
    rows = []
    for i, (headroom, signal, *budget) in enumerate(figs):
        week = {"week": f"2026-W{36 + i}", "date": date.today().isoformat()}  # noqa: DTZ011
        team = {**week, "kind": "team", "name": "team", "headroom": headroom}
        team["signal"] = signal
        if budget:
            team["budget"] = budget[0]
        rows += [team, {**week, "kind": "person", "name": "Alice", "ratio": 1.0}]
    path = home.projects_dir / name / "history.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _flips(app):
    return {
        n.message: n.severity for n in app._notifications if "stoplight" in n.message
    }


def test_colon_runs_a_typed_command_on_the_named_project(tmp_path, spawned):
    home = build_home(tmp_path, "apollo", "beta")

    async def script(app, pilot):
        await pilot.press("colon")
        box = app.query_one("#command", Input)
        assert box.display and box.has_focus and box.value == ""
        box.value = "beta CUT 700k"
        await pilot.press("enter")
        await settle(app, pilot)
        assert [a[1:] for a, _ in spawned] == [
            ["cut", "-p", "beta", "--budget", "700000"]
        ]
        assert _cards(app)[-1][0] == "cut -p beta --budget 700000 · beta"
        assert not box.display

    run(tui.PerchTUI(home), script)


def test_a_bad_command_line_toasts_and_spawns_nothing(tmp_path, spawned):
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        await pilot.press("colon")
        app.query_one("#command", Input).value = "apollo NOPE"
        await pilot.press("enter")
        await settle(app, pilot)
        assert spawned == []
        toast = [n for n in app._notifications if "NOPE" in n.message]
        assert toast and toast[0].severity == "error"

    run(tui.PerchTUI(home), script)


def test_c_opens_the_command_line_prefilled_with_cut(tmp_path, spawned):
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        await pilot.press("c")
        box = app.query_one("#command", Input)
        assert box.display and box.has_focus and box.value == "CUT "
        box.value = "CUT 1.2m"
        await pilot.press("enter")  # no project named: the cursor's
        await settle(app, pilot)
        assert spawned[0][0][1:] == ["cut", "-p", "apollo", "--budget", "1200000"]

    run(tui.PerchTUI(home), script)


def test_a_command_line_while_busy_says_busy(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    release = threading.Event()
    calls = []

    def slow(argv, cwd, started, env=None):
        calls.append(argv)
        release.wait(5)
        yield "done"

    monkeypatch.setattr(tui, "_spawn", slow)

    async def script(app, pilot):
        await pilot.press("b")
        await pilot.pause()
        await pilot.press("colon")
        app.query_one("#command", Input).value = "apollo DOC"
        await pilot.press("enter")
        await pilot.pause()
        assert "busy: board" in _notices(app)
        release.set()
        await settle(app, pilot)
        assert len(calls) == 1

    try:
        run(tui.PerchTUI(home), script)
    finally:
        release.set()


def test_hrs_opens_the_editor_on_that_projects_row(tmp_path, spawned, monkeypatch):
    home = build_home(tmp_path, "apollo", "beta")
    opened = []
    monkeypatch.setattr(
        tui.PerchTUI, "action_hours", lambda self: opened.append(self._selected())
    )

    async def script(app, pilot):
        await pilot.press("colon")
        app.query_one("#command", Input).value = "beta HRS"
        await pilot.press("enter")
        await settle(app, pilot)
        assert opened == ["beta"] and spawned == []

    run(tui.PerchTUI(home), script)


def test_rev_hands_the_terminal_to_review_on_that_projects_row(
    tmp_path, spawned, monkeypatch
):
    home = build_home(tmp_path, "apollo", "beta")
    opened = []
    monkeypatch.setattr(
        tui.PerchTUI, "action_review", lambda self: opened.append(self._selected())
    )

    async def script(app, pilot):
        await pilot.press("colon")
        app.query_one("#command", Input).value = "beta REV"
        await pilot.press("enter")
        await settle(app, pilot)
        assert opened == ["beta"] and spawned == []

    run(tui.PerchTUI(home), script)


def test_review_without_a_pulled_board_toasts_and_keeps_the_screen(
    tmp_path, monkeypatch
):
    home = build_home(tmp_path, "apollo")
    suspended = []
    monkeypatch.setattr(tui.PerchTUI, "suspend", lambda self: suspended.append(1))

    async def script(app, pilot):
        await pilot.press("colon")
        app.query_one("#command", Input).value = "apollo REV"
        await pilot.press("enter")
        await settle(app, pilot)
        assert suspended == []
        assert any("gitboard pull grp/apollo" in n for n in _notices(app))

    run(tui.PerchTUI(home), script)


def test_capital_r_hands_the_terminal_to_the_walk(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    opened = []
    monkeypatch.setattr(
        tui.PerchTUI, "action_walk", lambda self: opened.append(self._selected())
    )

    async def script(app, pilot):
        await pilot.press("R")
        await settle(app, pilot)
        assert opened == ["apollo"]

    run(tui.PerchTUI(home), script)


def test_walk_toasts_a_settings_file_perch_left_alone(tmp_path, monkeypatch):
    from perch.core import walk as command

    home = build_home(tmp_path, "apollo")
    line = "left x/settings.json alone (not a settings object); add y by hand"
    monkeypatch.setattr(command, "install", lambda home: ["kept z", line])
    monkeypatch.setattr(tui.PerchTUI, "suspend", lambda self: nullcontext())
    events = []
    monkeypatch.setattr(tui.subprocess, "run", lambda *a, **k: events.append("walk"))
    notify = tui.PerchTUI.notify

    def spy(self, message, **kw):
        events.append(("notify", kw.get("timeout")))
        return notify(self, message, **kw)

    monkeypatch.setattr(tui.PerchTUI, "notify", spy)

    async def script(app, pilot):
        await pilot.press("R")
        await settle(app, pilot)
        assert _notices(app) == [line]
        # a toast posted before the walk would expire while Claude owns the terminal
        assert events == ["walk", ("notify", 30)]

    run(tui.PerchTUI(home), script)


def test_the_trend_cell_is_a_sparkline_of_recorded_headroom(tmp_path):
    home = build_home(tmp_path, "apollo", "beta")
    _weeks(home, "apollo", (0, "red"), (50, "yellow"), (100, "green"))
    _team_row(home, "beta", 5.0, "green")  # one week: no line yet

    async def script(app, pilot):
        rows = _cells(app)
        assert tui.COLUMNS[4] == "Trend"
        assert rows[0][4] == "▁▅█" and rows[1][4] == ""

    run(tui.PerchTUI(home), script)


def test_the_tape_lists_each_projects_changes_in_order(tmp_path):
    home = build_home(tmp_path, "apollo", "beta", "gamma")
    _weeks(home, "apollo", (100, "green"), (-50, "red", 10))
    _weeks(home, "gamma", (100, "yellow"), (200, "yellow"))
    _team_row(home, "beta", 5.0, "green")  # one week: nothing to say

    async def script(app, pilot):
        await settle(app, pilot)
        assert app.query_one("#tape").display
        lines = str(app.query_one("#tape-body").render()).splitlines()
        today = f"{date.today():%m-%d}"  # noqa: DTZ011
        flip = f"{today}  apollo  flip  W36→W37: GREEN→RED, headroom −$150"
        move = f"{today}  gamma  figures  W36→W37: headroom +$100"
        assert lines.index(flip) < lines.index(move)
        assert not any("beta  flip" in x for x in lines)

    run(tui.PerchTUI(home), script)


def test_the_tape_is_hidden_when_empty_and_t_toggles_it(tmp_path):
    home = build_home(tmp_path, "apollo")
    _team_row(home, "apollo", 5.0, "green")

    async def script(app, pilot):
        await settle(app, pilot)
        assert not app.tape_rows and not app.query_one("#tape").display
        app.tape_by["apollo"] = [tape.TapeEntry(date.today(), "apollo", "board", "x")]  # noqa: DTZ011
        await pilot.press("t")
        assert not app.tape_on and not app.query_one("#tape").display
        await pilot.press("t")
        assert app.tape_on and app.query_one("#tape").display

    run(tui.PerchTUI(home), script)


def test_tape_text_styles_and_caps_lines():
    d = date(2026, 4, 19)
    es = [
        tape.TapeEntry(d, "a", "hours", "h"),
        tape.TapeEntry(d, "a", "failed", "f"),
        tape.TapeEntry(d, "a", "error", "e"),
    ]
    t = tui.tape_text(es)
    assert t.plain.splitlines()[1] == "04-19  a  failed  f"
    assert [s.style for s in t.spans] == ["dim", "red", "yellow"]
    assert len(tui.tape_text(es * 100).plain.splitlines()) == 200


def test_a_flipped_stoplight_is_reversed_and_toasts_once(tmp_path):
    home = build_home(tmp_path, "apollo", "beta")
    _weeks(home, "apollo", (100, "yellow"), (-5, "red"))
    _weeks(home, "beta", (100, "green"), (90, "yellow"))

    async def script(app, pilot):
        assert app.query_one(DataTable).get_row_at(0)[2].style == "reverse"
        assert _flips(app) == {
            "apollo: stoplight YELLOW → RED (W37)": "error",
            "beta: stoplight GREEN → YELLOW (W37)": "warning",
        }
        app.action_refresh()
        app.action_refresh()
        await pilot.pause()
        assert len(_flips(app)) == 2

    run(tui.PerchTUI(home), script)


def test_a_stoplight_that_did_not_flip_is_plain_and_silent(tmp_path):
    home = build_home(tmp_path, "apollo")
    _weeks(home, "apollo", (100, "green"), (90, "green"))

    async def script(app, pilot):
        assert app.query_one(DataTable).get_row_at(0)[2].style == ""
        assert not _flips(app)

    run(tui.PerchTUI(home), script)


def test_a_flip_a_run_records_toasts_when_its_row_refreshes(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    _weeks(home, "apollo", (100, "green"), (90, "green"))

    def fake(argv, cwd, started, env=None):
        _weeks(home, "apollo", (100, "green"), (90, "green"), (-1, "red"))
        yield "ran"

    monkeypatch.setattr(tui, "_spawn", fake)

    async def script(app, pilot):
        await pilot.press("b")
        await settle(app, pilot)
        assert "apollo: stoplight GREEN → RED (W38)" in _notices(app)
        assert "W37→W38" in str(app.query_one("#tape-body").render())

    run(tui.PerchTUI(home), script)


def test_i_on_headroom_shows_the_team_lines(tmp_path, spawned):
    home = build_home(tmp_path, "apollo")
    _weeks(home, "apollo", (100, "green"), (-5, "red"))

    async def script(app, pilot):
        app.query_one(DataTable).move_cursor(row=0, column=3)
        await pilot.press("i")
        await pilot.pause()
        title, body, status = _cards(app)[-1]
        assert status == "info" and "apollo" in title
        assert body.startswith("RED") and "2026-W36  $100  GREEN" in body
        assert "Alice" not in body and spawned == []

    run(tui.PerchTUI(home), script)


def test_i_on_a_step_cell_shows_its_state(tmp_path, spawned):
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        app.query_one(DataTable).move_cursor(row=0, column=tui.COLUMNS.index("board"))
        await pilot.press("i")
        await pilot.pause()
        title, body, status = _cards(app)[-1]
        assert status == "info" and "board" in title
        assert "todo" in body and "never" in body

    run(tui.PerchTUI(home), script)


def test_i_on_project_shows_the_checks(tmp_path, spawned):
    home = build_home(tmp_path, "apollo", gitlab=False)

    async def script(app, pilot):
        await pilot.press("i")  # the cursor starts on Project
        await pilot.pause()
        _, body, status = _cards(app)[-1]
        assert status == "info"
        assert "✓ apollo: perch.yaml" in body
        assert "✗ apollo: gitlab_project not set → add gitlab_project:" in body

    run(tui.PerchTUI(home), script)


def test_i_on_flags_runs_the_watch(tmp_path, spawned):
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        app.query_one(DataTable).move_cursor(row=0, column=len(tui.COLUMNS) - 1)
        await pilot.press("i")
        await settle(app, pilot)
        assert [a[1:] for a, _ in spawned] == [["watch", "-p", "apollo"]]

    run(tui.PerchTUI(home), script)


def test_coming_to_the_front_refreshes_the_table_in_a_worker(tmp_path):
    from textual import events

    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        assert _cells(app)[0][2] == "—"
        _team_row(home, "apollo", 500.0, "green")  # written by another app meanwhile
        app.post_message(events.AppFocus())
        await pilot.pause()  # deliver the event: the worker starts
        await settle(app, pilot)
        assert _cells(app)[0][2:4] == ["GREEN", "$500"]

    run(tui.PerchTUI(home), script)


# --- blocks: PI_BLOCKS output drawn as widgets --------------------------------


def _j(block) -> str:
    return json.dumps(block, ensure_ascii=False)


def _block_run(monkeypatch, tmp_path, lines, seen=None):
    home = build_home(tmp_path, "apollo")

    def fake(argv, cwd, started, env=None):
        if seen is not None:
            seen.update(env)
        yield from lines

    monkeypatch.setattr(tui, "_spawn", fake)
    return home


def _texts(card) -> list[str]:
    return [w.content.plain for w in card.query(Static) if hasattr(w.content, "plain")]


def test_the_spawn_env_asks_for_blocks(tmp_path, monkeypatch):
    seen = {}
    home = _block_run(monkeypatch, tmp_path, ["x"], seen)

    async def script(app, pilot):
        await pilot.press("d")
        await settle(app, pilot)
        assert seen[b.ENV] == "1" and b.ENV == "PI_BLOCKS"

    run(tui.PerchTUI(home), script)


def test_a_table_block_is_a_data_table_of_its_rows(tmp_path, monkeypatch):
    rows = [["cycle", "4.0"], ["lead", "9.5"]]
    lines = [_j(b.table(["days", "median"], rows, title="Time", align=["l", "r"]))]
    home = _block_run(monkeypatch, tmp_path, lines)

    async def script(app, pilot):
        await pilot.press("d")
        await settle(app, pilot)
        card = app.query_one(tui.RunCard)
        (table,) = card.query(DataTable)
        assert [[str(c) for c in table.get_row_at(i)] for i in range(2)] == rows
        assert [c.label.justify for c in table.columns.values()] == ["left", "right"]
        assert table.styles.height.value == 3 and not table.show_cursor
        assert "Time" in _texts(card)

    run(tui.PerchTUI(home), script)


def test_a_long_table_stops_growing_at_twelve_rows(tmp_path, monkeypatch):
    rows = [[str(i)] for i in range(30)]
    home = _block_run(monkeypatch, tmp_path, [_j(b.table(["n"], rows))])

    async def script(app, pilot):
        await pilot.press("d")
        await settle(app, pilot)
        (table,) = app.query_one(tui.RunCard).query(DataTable)
        assert table.styles.height.value == 13

    run(tui.PerchTUI(home), script)


def test_bars_scale_to_the_largest_and_trim_whole_numbers(tmp_path, monkeypatch):
    items = [("Review", 4), ("Backlog", 2.5), ("Done", 0)]
    home = _block_run(monkeypatch, tmp_path, [_j(b.bars(items, title="By column"))])

    async def script(app, pilot):
        await pilot.press("d")
        await settle(app, pilot)
        card = app.query_one(tui.RunCard)
        bars = card.query_one(tui.Bars).render().plain.split("\n")
        assert [x.split()[0] for x in bars] == ["Review", "Backlog", "Done"]
        assert bars[0].endswith(" 4") and bars[1].endswith(" 2.5")
        counts = [x.count("█") for x in bars]
        assert counts[0] > counts[1] > counts[2] == 0
        assert bars[0].index("█") == bars[1].index("█")  # labels padded alike
        assert counts[1] == round(counts[0] * 2.5 / 4)

    run(tui.PerchTUI(home), script)


def test_bar_lines_scale_to_the_width_and_add_the_unit():
    out = tui.bar_lines([("a", 10), ("bb", 5)], "d", 22).plain.split("\n")
    assert out == ["a  " + "█" * 14 + " 10 d", "bb " + "█" * 7 + " 5 d"]


def test_figures_tiles_show_value_label_and_note(tmp_path, monkeypatch):
    items = [b.figure("Open", "41", "6 unassigned"), b.figure("Done", "7", tone="good")]
    home = _block_run(monkeypatch, tmp_path, [_j(b.figures(items))])

    async def script(app, pilot):
        await pilot.press("d")
        await settle(app, pilot)
        (tiles,) = app.query_one(tui.RunCard).query(Static)
        from rich.console import Console

        con = Console(width=80, record=True, file=io.StringIO())
        con.print(tiles.content)
        out = con.export_text()
        assert "41" in out and "Open" in out and "6 unassigned" in out
        assert "Done" in out and "7" in out
        assert tiles.content.renderables[1].style == "bold green"  # Done's tile

    run(tui.PerchTUI(home), script)


def test_headings_text_and_lists(tmp_path, monkeypatch):
    lines = [
        _j(b.heading("Open", 2)),
        _j(b.text("late", "bad")),
        _j(b.bullets(["one", "two"])),
    ]
    home = _block_run(monkeypatch, tmp_path, lines)

    async def script(app, pilot):
        await pilot.press("d")
        await settle(app, pilot)
        card = app.query_one(tui.RunCard)
        assert _texts(card) == ["Open", "late", "• one\n• two"]
        heading, late, _ = card.query(Static)
        assert heading.content.style == "bold" and heading.styles.border_bottom[0]
        assert late.content.style == "red"

    run(tui.PerchTUI(home), script)


def test_a_bad_block_stays_text_and_text_after_a_block_starts_a_new_widget(
    tmp_path, monkeypatch
):
    bad = _j({"pi": 1, "block": "table", "columns": ["a"]})  # no rows
    lines = ["before", "also", _j(b.heading("H", 1)), bad, "after"]
    home = _block_run(monkeypatch, tmp_path, lines)

    async def script(app, pilot):
        await pilot.press("d")
        await settle(app, pilot)
        card = app.query_one(tui.RunCard)
        assert _texts(card) == ["before\nalso", "H", bad + "\nafter"]
        assert card.body.plain == f"before\nalso\n{bad}\nafter"
        assert card.border_subtitle.startswith("✓")

    run(tui.PerchTUI(home), script)


def test_o_maximizes_the_newest_card_and_escape_restores_it(tmp_path, spawned):
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        await pilot.press("b")
        await settle(app, pilot)
        await pilot.press("f")
        await settle(app, pilot)
        await pilot.press("o")
        await pilot.pause()
        assert app.screen.maximized is list(app.query(tui.RunCard))[-1]
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.maximized is None

    run(tui.PerchTUI(home), script)


def test_a_focus_refresh_keeps_the_cursor(tmp_path):
    from textual import events

    home = build_home(tmp_path, "apollo", "beta")

    async def script(app, pilot):
        await pilot.press("down")
        at = app.query_one(DataTable).cursor_coordinate
        app.post_message(events.AppFocus())
        await pilot.pause()  # deliver the event: the worker starts
        await settle(app, pilot)
        assert app.query_one(DataTable).cursor_coordinate == at

    run(tui.PerchTUI(home), script)


def test_o_with_no_cards_does_nothing(tmp_path):
    async def script(app, pilot):
        await pilot.press("o")
        assert app.screen.maximized is None

    run(tui.PerchTUI(build_home(tmp_path, "apollo")), script)


def test_markup_in_block_strings_shows_literally(tmp_path, monkeypatch):
    lines = [
        _j(b.table(["[/x]"], [["[bold]x[/bold]"]])),
        _j(b.text("[red]hi")),
        _j(b.figures([b.figure("[/l]", "[/v]", note="[/n]")])),
        _j(b.bullets(["[/i]"])),
    ]
    home = _block_run(monkeypatch, tmp_path, lines)

    async def script(app, pilot):
        await pilot.press("d")
        await settle(app, pilot)
        card = app.query_one(tui.RunCard)
        (table,) = card.query(DataTable)
        assert str(table.get_row_at(0)[0]) == "[bold]x[/bold]"
        assert str(next(iter(table.columns.values())).label) == "[/x]"
        assert "[red]hi" in _texts(card)
        assert "[/i]" in "".join(_texts(card))

    run(tui.PerchTUI(home), script)


def test_bar_lines_survive_zero_top_and_negatives():
    assert tui.bar_lines([("a", 0), ("b", -3)], None, 30).plain.count("█") == 0
    assert (
        tui.bar_lines([("a", 4), ("b", -3)], None, 30).plain.split("\n")[1].count("█")
        == 0
    )


def test_the_projects_grid_is_found_by_id_beside_card_tables(tmp_path, monkeypatch):
    home = _block_run(monkeypatch, tmp_path, [_j(b.table(["n"], [["1"]]))])

    async def script(app, pilot):
        await pilot.press("d")
        await settle(app, pilot)
        await pilot.press("r")
        await pilot.pause()
        assert app.query_one("#projects", tui.Grid).row_count == 1

    run(tui.PerchTUI(home), script)


def test_refresh_and_a_finished_run_compute_rows_off_the_ui_thread(
    tmp_path, spawned, monkeypatch
):
    import threading

    home = build_home(tmp_path, "apollo")
    seen = []
    original = tui.snapshot

    def spy(h, n):
        seen.append(threading.current_thread() is threading.main_thread())
        return original(h, n)

    monkeypatch.setattr(tui, "snapshot", spy)

    async def script(app, pilot):
        seen.clear()
        app.action_refresh()
        await settle(app, pilot)
        await pilot.press("b")
        await settle(app, pilot)
        assert seen == [False, False]

    run(tui.PerchTUI(home), script)


def test_in_suite_a_failed_list_windows_says_why_and_spawns_nothing(tmp_path, hops):
    from perch.core import suite

    hops.list_fail = "no server running"
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        await pilot.press("B")
        await pilot.pause()
        assert "budgie: switch failed: no server running" in _notices(app)

    run(tui.PerchTUI(home), script)
    assert hops.calls == [suite.windows()]


def test_in_suite_an_app_that_dies_at_startup_says_so(tmp_path, hops):
    hops.dies = True
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        await pilot.press("B")
        await pilot.pause()
        assert "budgie: exited at startup" in _notices(app)

    run(tui.PerchTUI(home), script)


def test_suite_map_entries_name_the_project(tmp_path):
    home = build_home(tmp_path, "apollo")
    m = tui.suite_map(home, "apollo")
    assert m["budgie"]["project"] == m["gitboard"]["project"] == "apollo"
    assert "project" not in m["perch"]  # a hop to perch never restarts it


def _detail_text(app) -> str:
    return str(app.query_one("#detail_body").render())


def test_the_detail_pane_follows_the_cursor_and_a_move_loads_nothing(
    tmp_path, monkeypatch
):
    from perch.core import sources

    home = build_home(tmp_path, "apollo", "beta")
    calls = []
    real = sources.load
    monkeypatch.setattr(sources, "load", lambda h, n: calls.append(n) or real(h, n))

    async def script(app, pilot):
        await settle(app, pilot)
        assert sorted(calls) == ["apollo", "beta"]
        assert _detail_text(app).startswith("apollo")
        assert "cost lines $5,000 excluded · 4 readings · fan seeded" in _detail_text(
            app
        )
        calls.clear()
        await pilot.press("down")
        await pilot.pause()
        assert _detail_text(app).startswith("beta")
        assert calls == []  # a cursor move reads a dict
        await pilot.press("r")
        await settle(app, pilot)
        assert sorted(calls) == ["apollo", "beta"]  # r forces one load each

    run(tui.PerchTUI(home), script)


def test_the_slow_tier_skips_an_unchanged_project_unless_forced(tmp_path, monkeypatch):
    from perch.core import sources

    home = build_home(tmp_path, "apollo")
    calls = []
    real = sources.load
    monkeypatch.setattr(sources, "load", lambda h, n: calls.append(n) or real(h, n))

    async def script(app, pilot):
        await settle(app, pilot)
        app._warm_all()
        await settle(app, pilot)
        assert calls == ["apollo"]
        app._warm_all(True)
        await settle(app, pilot)
        assert calls == ["apollo", "apollo"]

    run(tui.PerchTUI(home), script)


def test_v_toggles_the_detail_pane(tmp_path):
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        pane = app.query_one("#detail")
        assert pane.display
        await pilot.press("v")
        assert pane.has_class("off") and not pane.display
        await pilot.press("v")
        assert pane.display

    run(tui.PerchTUI(home), script)


def test_the_detail_pane_shows_at_120_columns_below_the_table(tmp_path):
    home = build_home(tmp_path, "apollo")

    async def go():
        async with tui.PerchTUI(home).run_test(size=(120, 30)) as pilot:
            app = pilot.app
            pane, out, table = (
                app.query_one(i) for i in ("#detail", "#output", "#projects")
            )
            assert pane.display
            assert pane.region.y >= table.region.bottom - 1
            assert pane.region.x < out.region.x
            await pilot.press("v")
            assert out.region.width >= 118

    asyncio.run(go())


@pytest.mark.parametrize("width", [120, 160, 200])
def test_the_projects_table_never_scrolls_sideways(tmp_path, width):
    home = build_home(tmp_path, "apollo")

    async def go():
        async with tui.PerchTUI(home).run_test(size=(width, 40)) as pilot:
            await settle(pilot.app, pilot)
            assert pilot.app.query_one("#projects").max_scroll_x == 0

    asyncio.run(go())


def test_the_burn_chart_follows_the_pane_width(tmp_path):
    home = build_home(tmp_path, "apollo")

    async def go():
        async with tui.PerchTUI(home).run_test(size=(120, 40)) as pilot:
            app = pilot.app
            await settle(app, pilot)
            first = max(len(r) for r in _detail_text(app).split("\n"))
            await pilot.resize_terminal(200, 40)
            await settle(app, pilot)
            await pilot.pause(0.2)
            assert max(len(r) for r in _detail_text(app).split("\n")) > first

    asyncio.run(go())


def test_as_of_replaces_the_chart_and_cuts_the_spark(tmp_path):
    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        await settle(app, pilot)
        assert "burn chart is live only" not in _detail_text(app)
        app.asof_week = "2026-W17"
        app._paint_detail()
        assert "burn chart is live only · L" in _detail_text(app)
        assert "█" not in _detail_text(app).split("live only")[1].split("\n")[0]

    run(tui.PerchTUI(home), script)


def test_burn_lines_draws_each_glyph_on_its_row():
    from datetime import date

    from budgie.core.burn import BurnSeries

    months = tuple(date(2026, m, 28) for m in (1, 2, 3, 4))
    # top = 80; levels are 10 apart: 80 -> row 0, 40 -> row 4, 20 -> row 6
    d = tui.detail.Detail(
        "p",
        {},
        BurnSeries(
            months=months,
            spent=(20.0, 20.0, None, None),
            spent_as_of=None,
            plan=(10.0, 30.0, 50.0, 70.0),
            budget=(80.0, 80.0, 80.0, 80.0),
            p10=(20.0, 20.0, 30.0, 40.0),
            p50=(20.0, 20.0, 40.0, 50.0),
            p90=(20.0, 20.0, 50.0, 60.0),
            reading_dates=(date(2026, 1, 25),),
            as_of=date(2026, 2, 28),
        ),
        None,
        None,
        None,
        None,
        None,
        0.0,
        "",
    )
    rows = tui.burn_lines(d, 4).plain.split("\n")
    assert len(rows) == 8
    assert rows[0] == "────"  # budget
    assert [r[0] for r in rows] == list("─      ")[:1] + [
        " ",
        " ",
        " ",
        " ",
        " ",
        "·",
        "█",
    ]
    assert [r[1] for r in rows] == [
        "─",
        " ",
        " ",
        " ",
        "·",
        " ",
        "▓",
        "▓",
    ]  # no Feb reading
    assert [r[2] for r in rows] == [
        "─",
        " ",
        "·",
        "▒",
        "▒",
        " ",
        " ",
        " ",
    ]  # fan, plan on top
    assert [r[3] for r in rows] == [
        "─",
        "▒",
        "▒",
        "▒",
        " ",
        " ",
        " ",
        " ",
    ]  # budget beats plan


# --- as-of browsing -----------------------------------------------------------


def _asof_home(tmp_path):
    home = build_home(tmp_path, "apollo", "beta")
    _weeks(
        home,
        "apollo",
        (5000, "green"),
        (2000, "yellow", 100000),
        (-3000, "red", 90000),
    )
    _weeks(home, "beta", (1000, "green"), (500, "green"))
    for name in ("apollo", "beta"):  # a row is dated in its own week, like a real run
        path = home.projects_dir / name / "history.jsonl"
        rows = [json.loads(x) for x in path.read_text().splitlines()]
        for r in rows:
            r["date"] = _asof.week_end(r["week"]).isoformat()
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return home


def _row(app, i=0):
    return _cells(app)[i]


def test_brackets_step_through_recorded_weeks_and_back_to_live(tmp_path):
    home = _asof_home(tmp_path)

    async def script(app, pilot):
        await settle(app, pilot)
        live = _cells(app)
        assert live[0][2] == "RED"
        await pilot.press("[")
        await settle(app, pilot)
        banner = app.query_one("#asof")
        assert banner.display and "AS OF 2026-W37" in str(banner.render())
        assert app.query_one("#projects").has_class("historical")
        apollo, beta = _row(app, 0), _row(app, 1)
        assert apollo[2:5] == ["YELLOW", "$2,000", "█▁"]
        assert beta[2:5] == ["GREEN", "$500", "█▁"]
        assert all(c == "n/a" for c in apollo[5:])
        flip = app.query_one("#projects").get_row_at(0)[2]
        assert flip.style == "reverse"
        assert beta[2] == "GREEN"
        assert app.query_one("#projects").get_row_at(1)[2].style != "reverse"
        await pilot.press("[")
        await settle(app, pilot)
        assert _row(app, 0)[2:5] == ["GREEN", "$5,000", ""]
        await pilot.press("]")
        await pilot.press("]")
        await settle(app, pilot)
        assert app.asof_week is None and _cells(app) == live
        assert not app.query_one("#asof").display

    run(tui.PerchTUI(home), script)


def test_stepping_toasts_no_stoplight_flip(tmp_path):
    home = _asof_home(tmp_path)

    async def script(app, pilot):
        await settle(app, pilot)
        before = len(_notices(app))
        await pilot.press("[")
        await settle(app, pilot)
        await pilot.press("L")
        await settle(app, pilot)
        assert len(_notices(app)) == before

    run(tui.PerchTUI(home), script)


def test_asof_command_jumps_and_a_project_without_the_week_shows_dashes(tmp_path):
    home = _asof_home(tmp_path)

    async def script(app, pilot):
        await settle(app, pilot)
        app.action_command("ASOF W38")
        await pilot.press("enter")
        await settle(app, pilot)
        assert app.asof_week == "2026-W38"
        beta = _row(app, 1)
        assert beta[2:5] == ["—", "—", ""]
        assert app.query_one("#projects").get_row_at(1)[2].style != "reverse"
        app.action_command("ASOF W50")
        await pilot.press("enter")
        await settle(app, pilot)
        assert "no week W50 recorded: W36…W38" in _notices(app)
        assert app.asof_week == "2026-W38"
        app.action_command("ASOF LIVE")
        await pilot.press("enter")
        await settle(app, pilot)
        assert app.asof_week is None

    run(tui.PerchTUI(home), script)


def test_one_recorded_week_stays_live(tmp_path):
    home = build_home(tmp_path, "apollo")
    _team_row(home, "apollo", 5.0, "green")

    async def script(app, pilot):
        await settle(app, pilot)
        await pilot.press("[")
        await settle(app, pilot)
        assert app.asof_week is None and _notices(app)

    run(tui.PerchTUI(home), script)


def test_asof_does_not_run_status_or_the_watch(tmp_path, monkeypatch):
    home = _asof_home(tmp_path)

    async def script(app, pilot):
        await settle(app, pilot)

        def boom(*a, **k):
            raise AssertionError("live-only call")

        monkeypatch.setattr(tui, "status", boom)
        monkeypatch.setattr(tui, "_flags", boom)
        await pilot.press("[")
        await settle(app, pilot)
        assert app.asof_week == "2026-W37"

    run(tui.PerchTUI(home), script)


def test_the_tape_is_recomputed_as_of_the_week(tmp_path):
    home = _asof_home(tmp_path)

    async def script(app, pilot):
        await settle(app, pilot)
        assert any("W37→W38" in e.text for e in app.tape_rows)
        await pilot.press("[")
        await settle(app, pilot)
        texts = [e.text for e in app.tape_rows]
        assert "W36→W37: GREEN→YELLOW, headroom −$3,000" in texts
        assert not any("W37→W38" in t for t in texts)
        assert "W36→W37" in str(app.query_one("#tape-body").render())

    run(tui.PerchTUI(home), script)


def test_in_asof_i_and_enter_say_n_a_and_run_nothing(tmp_path, spawned):
    home = _asof_home(tmp_path)

    async def script(app, pilot):
        await settle(app, pilot)
        await pilot.press("[")
        await settle(app, pilot)
        n = len(_cards(app))
        await pilot.press("right", "right", "right", "right", "right")  # a step cell
        await pilot.press("i")
        await pilot.press("enter")
        await pilot.pause()
        assert _notices(app).count("as of W37: n/a, press L for live") == 2
        assert len(_cards(app)) == n and spawned == []
        for _ in range(8):
            await pilot.press("right")  # Flags
        await pilot.press("i")
        assert spawned == []
        await pilot.press(
            "left", "left", "left", "left", "left", "left", "left", "left"
        )
        # back to Headroom: team lines only up to the week
        grid = app.query_one("#projects")
        grid.move_cursor(row=0, column=3)
        await pilot.press("i")
        assert "W38" not in _cards(app)[-1][1]
        assert "W37" in _cards(app)[-1][1]

    run(tui.PerchTUI(home), script)


def test_a_worker_result_for_another_view_is_dropped(tmp_path):
    home = _asof_home(tmp_path)

    async def script(app, pilot):
        await settle(app, pilot)
        await pilot.press("[")
        await settle(app, pilot)
        hit = []
        app._if_current(None, hit.append, 1)
        app._if_current("2026-W37", hit.append, 2)
        assert hit == [2]

    run(tui.PerchTUI(home), script)


def test_asof_snapshot_runs_off_the_ui_thread(tmp_path, monkeypatch):
    home = _asof_home(tmp_path)
    seen = []
    original = tui.snapshot

    def spy(h, n, *a):
        seen.append(threading.current_thread() is threading.main_thread())
        return original(h, n, *a)

    async def script(app, pilot):
        await settle(app, pilot)
        monkeypatch.setattr(tui, "snapshot", spy)
        await pilot.press("[")
        await settle(app, pilot)
        assert seen == [False, False]

    run(tui.PerchTUI(home), script)


# --- events keys and lead-only alert toasts (perch-zq2.2, perch-zq2.5) ---


def _alert_home(tmp_path, names=("apollo",), rules="  - when: headroom < 50k\n"):
    from datetime import timedelta

    from perch.core.history import week_key
    from perch.core.workspace import load_home

    home = build_home(tmp_path, *names)
    path = home.root / "perch-home.yaml"
    path.write_text(path.read_text() + "alerts:\n" + rules)
    home = load_home(path)
    today = date.today()  # noqa: DTZ011
    for name in names:
        rows = [
            {"week": week_key(today - timedelta(days=7 * i)), "date": "2026-01-01"}
            | {"kind": "team", "name": "team", "headroom": h, "signal": "green"}
            for i, h in ((1, 60000), (0, 42000))
        ]
        (home.projects_dir / name / "history.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows)
        )
    return home


def _alerts(app):
    return [n.message for n in app._notifications if "headroom <" in n.message]


def test_e_runs_events_on_the_project_and_E_runs_all_without_a_refresh(
    tmp_path, spawned, monkeypatch
):
    home = build_home(tmp_path, "apollo")
    refreshed = []

    async def script(app, pilot):
        monkeypatch.setattr(app, "_warm_all", lambda *a: refreshed.append(a))
        await pilot.press("e")
        await settle(app, pilot)
        assert spawned[-1][0] == [PERCH, "events", "-p", "apollo"]
        assert refreshed  # a normal run refreshes
        refreshed.clear()
        await pilot.press("E")
        await settle(app, pilot)
        assert spawned[-1][0] == [PERCH, "events", "--all"]
        assert not refreshed
        assert _cards(app)[-1][:2] == ("events --all", "ran")

    run(tui.PerchTUI(home), script)


def test_a_fresh_alert_toasts_once_and_not_again_on_r(tmp_path):
    home = _alert_home(tmp_path)

    async def script(app, pilot):
        await settle(app, pilot)
        week = tui.history.load(home.projects_dir / "apollo" / "history.jsonl")[-1][
            "week"
        ]
        assert _alerts(app) == [
            f"apollo: headroom < 50k (headroom $42,000, {week.split('-')[-1]})"
        ]
        assert len(app.hits["apollo"]) == 1
        app.action_refresh()
        await settle(app, pilot)
        assert len(_alerts(app)) == 1

    run(tui.PerchTUI(home), script)


def test_a_bad_alerts_file_gives_no_rules_and_no_toast(tmp_path):
    home = _alert_home(tmp_path, rules="  - when: pace < 80\n")
    app = tui.PerchTUI(home)
    assert app.rules == ()

    async def script(app, pilot):
        await settle(app, pilot)
        assert _alerts(app) == []

    run(app, script)


def test_four_alerts_become_one_summary_toast(tmp_path):
    home = _alert_home(tmp_path, names=("a", "b", "c", "d"))

    async def script(app, pilot):
        await settle(app, pilot)
        assert _alerts(app) == []
        assert [m for m in _notices(app) if m.startswith("4 changes")]

    run(tui.PerchTUI(home), script)


def test_no_alert_toast_while_browsing_a_recorded_week(tmp_path):
    home = _alert_home(tmp_path)
    app = tui.PerchTUI(home)
    app.asof_week = "2026-W01"

    async def script(app, pilot):
        await settle(app, pilot)
        assert _alerts(app) == []
        assert app.hits == {}

    run(app, script)


def test_alert_files_are_read_off_the_ui_thread_after_startup(tmp_path, monkeypatch):
    home = _alert_home(tmp_path)
    real = tui.alert_hits
    threads = []

    def spy(*a):
        threads.append(threading.current_thread() is threading.main_thread())
        return real(*a)

    monkeypatch.setattr(tui, "alert_hits", spy)

    async def script(app, pilot):
        await settle(app, pilot)
        threads.clear()
        app.action_refresh()
        await settle(app, pilot)
        assert threads and not any(threads)
        assert len(app.hits["apollo"]) == 1

    run(tui.PerchTUI(home), script)


def test_a_short_terminal_scrolls_the_detail_pane_instead_of_clipping_it(tmp_path):
    names = [f"p{n:02d}" for n in range(20)]
    home = build_home(tmp_path, *names)

    async def go():
        async with tui.PerchTUI(home).run_test(size=(120, 24)) as pilot:
            app = pilot.app
            await settle(app, pilot)
            pane, lower = app.query_one("#detail"), app.query_one("#lower")
            assert pane.region.bottom <= lower.region.bottom  # nothing off screen
            assert pane.max_scroll_y > 0  # the rest is a scroll away

    asyncio.run(go())
