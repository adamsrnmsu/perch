# tmux Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `perch suite` runs perch, Budgie and gitboard side by side in a
hidden tmux so `P`/`B`/`G` hop between running apps instantly, keeping each
app's state.

**Architecture:** `perch/core/suite.py` builds every tmux argv (pure, like
`core/steps.py`). `perch suite` starts a private tmux server (`-L pi`, no
config file, options sent as commands) with one window per app and attaches.
In the suite, each app's switch key runs the hop rule: list the windows, then
select the target's window if it runs the same `{"cwd", "argv"}` entry,
respawn it if it runs another, open it if it is gone. Budgie and gitboard
carry their own copy of the rule. Outside the suite, the exec-on-hop code
stays as it is.

**Tech Stack:** Python 3, tmux >= 3.2 (3.7c here), Textual 8.2.8 (perch,
Budgie), rich + termios loop (gitboard), click (perch CLI), pytest
(+ pytest-asyncio auto mode in Budgie).

**Spec:** `perch/docs/superpowers/specs/2026-10-02-tmux-suite-design.md`

## Global Constraints

- tmux server socket and session are both named `pi`: every call is
  `tmux -L pi ...`, every target `pi:=NAME` (exact window name) or `pi:`.
- Window names are exactly `perch`, `budgie`, `gitboard`.
- A window's `@entry` user option is `json.dumps(entry, sort_keys=True)` of the
  `{"cwd": str, "argv": [str, ...]}` it was started with.
- In-suite test: `os.path.basename(os.environ.get("TMUX", "").split(",")[0]) == "pi"`.
- Window listing: `tmux -L pi list-windows -t pi -F "#{window_name}\t#{@entry}"`.
  Never `show-options -q` (exits 0 for a missing window) or `display-message`
  (falls back to the current window). Both probed.
- New and respawned windows get `-c CWD -e PI_SUITE=<the hopping app's map>`
  then the argv as separate elements (no shell).
- Options, in this order, before any window is made (tmux reads
  `default-terminal` when a pane spawns):
  `-g status off`, `-g prefix None`, `-g prefix2 None`, `-s escape-time 0`,
  `-s focus-events on`, `-g default-terminal tmux-256color`,
  `-sa terminal-features ,*:RGB`, `-gw remain-on-exit off`,
  `-g destroy-unattached off`.
- Messages, verbatim: `needs tmux: brew install tmux`;
  `start from perch tui to switch apps` (unchanged); a failed hop shows
  `switch failed: <tmux stderr>` (perch prefixes the target, as its other
  notices name their subject: `gitboard: switch failed: ...`).
- Outside the suite nothing changes: same keys, same exec, same busy refusal.
- `core/` stays UI-free (no textual, no rich, no click). `core/suite.py`
  executes nothing.
- The hop code is copied into Budgie and gitboard, not shared.
- Paths with a backslash are not supported (tmux un-escapes `-e` values;
  probed). Do not add escaping.
- Repos: perch, Budgie and gitboard are three git repos. Work each in its own
  worktree (`.claude/worktrees/tmux-suite` in that repo), branch from a fresh
  `origin/main`. Another session is editing Budgie's `tui.py` and perch's
  `worktree-tui-blocks` branch edits perch's `tui.py`: rebase before you
  start and match code by function name, not line number.
- Commit in the worktree after each task. Do not push or merge: the repos are
  on the Conservative profile; the user pushes.
- Beads live in perch's database. Claim yours at the start
  (`bd update <id> --claim`), close it with a reason at the end. Run `bd` from
  the perch checkout.

## Review Focus

1. **A window exists but has no `@entry`** (made by hand, or by an older
   build). Expect a respawn on the right entry, not a select of whatever runs
   there. Pinned in Task 1 (`test_hop_without_a_recorded_entry_respawns`).
2. **`PI_SUITE` malformed inside the suite.** Expect the "start from perch
   tui" message and no tmux call at all. Pinned in Task 2
   (`test_in_the_suite_a_bad_map_still_says_where_to_start`) and Task 3
   (`test_tui_in_suite_without_pi_suite_runs_no_tmux`).
3. **`perch suite -p nosuch` on a cold start.** Expect the workspace error
   naming the known projects, exit 1, and no tmux server started. Pinned in
   Task 1 (`test_suite_unknown_project_starts_nothing`).
4. **Several projects, no `-p`, run from the workspace root.** Expect the
   first project (sorted), not the "several projects" error `select` gives.
   Pinned in Task 1 (`test_suite_without_p_opens_on_the_first_project`).
5. **A `cwd` with spaces** (`budget/My Budget`). Expect it as one argv
   element after `-c`. Pinned in Task 1 (`test_launch_keeps_a_cwd_with_spaces_whole`).

---

### Task 1: perch -- `core/suite.py`, `perch suite`, perch's hop and suite quit (bead `perch-a2b.1`)

**Files:**
- Create: `perch/core/suite.py`
- Create: `perch/tests/test_suite.py`
- Modify: `perch/tui.py` (`switch`, `action_switch`, new `_hop`; imports)
- Modify: `perch/cli.py` (`tui` command; new `suite` command)
- Modify: `perch/tests/test_tui.py` (switch section)

**Interfaces:**
- Consumes: `tui.suite_map(home, name) -> dict[str, dict]`, `tui._ERRORS`,
  `cli._home()`, `cli._bin_dir()`, `cli._project_option` (all exist).
- Produces (`perch/core/suite.py`):
  - `SOCKET = "pi"`, `SESSION = "pi"`, `SUITE = "PI_SUITE"`, `OPTIONS: tuple[tuple[str, str, str], ...]`
  - `in_suite(env: Mapping[str, str]) -> bool`
  - `entry_key(entry: Mapping) -> str`
  - `windows() -> list[str]`, `entry_of(listing: str, name: str) -> str | None`
  - `hop(name: str, entry: Mapping, suite_env: str, current: str | None) -> list[str]`
  - `launch(perch: Mapping, suite: Mapping | None) -> list[str]`
  - `has_session() -> list[str]`, `attach() -> list[str]`, `kill() -> list[str]`
  - Every function returns a full argv starting `["tmux", "-L", "pi", ...]`.

- [ ] **Step 0: Claim and isolate**

```bash
cd /Users/ryanadams/Documents/git/pi_suite/perch
bd update perch-a2b.1 --claim
git fetch origin
```

Work in the `worktree-tmux-suite` worktree (it holds the spec and this plan);
`git rebase origin/main` there first.

- [ ] **Step 1: Write the failing core tests**

Create `perch/tests/test_suite.py`:

```python
"""perch suite: tmux argv for the launch and the hop (core/suite.py), and the
`perch suite` command that runs them."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from perch import tui
from perch.cli import cli
from perch.core import suite
from perch.tests.conftest import build_home

TMUX = ["tmux", "-L", "pi"]
B = {"cwd": "/ws/budget/fy26", "argv": ["/venv/bin/budgie", "tui"]}
B_KEY = json.dumps(B, sort_keys=True)


def test_in_suite_only_on_the_pi_socket():
    assert suite.in_suite({"TMUX": "/private/tmp/tmux-501/pi,123,0"})
    assert not suite.in_suite({"TMUX": "/private/tmp/tmux-501/default,123,0"})
    assert not suite.in_suite({})


def test_entry_key_ignores_key_order():
    assert suite.entry_key({"argv": ["a"], "cwd": "/x"}) == suite.entry_key(
        {"cwd": "/x", "argv": ["a"]}
    )


def test_entry_of_reads_the_window_listing():
    listing = f"perch\t{{}}\nbudgie\t{B_KEY}\nodd\t\n"
    assert suite.entry_of(listing, "budgie") == B_KEY
    assert suite.entry_of(listing, "odd") == ""  # a window with no @entry
    assert suite.entry_of(listing, "gitboard") is None  # no window


def test_windows_lists_name_and_entry():
    assert suite.windows() == [
        *TMUX, "list-windows", "-t", "pi", "-F", "#{window_name}\t#{@entry}",
    ]


def test_hop_to_the_same_entry_only_selects():
    assert suite.hop("budgie", B, "{}", B_KEY) == [*TMUX, "select-window", "-t", "pi:=budgie"]


def test_hop_to_a_missing_window_opens_it():
    assert suite.hop("budgie", B, '{"m": 1}', None) == [
        *TMUX, "new-window", "-t", "pi:", "-n", "budgie",
        "-c", "/ws/budget/fy26", "-e", 'PI_SUITE={"m": 1}', "/venv/bin/budgie", "tui",
        ";", "set-option", "-w", "-t", "pi:=budgie", "@entry", B_KEY,
    ]


def test_hop_to_another_entry_respawns_only_that_window():
    other = json.dumps({"cwd": "/ws/budget/fy27", "argv": ["/venv/bin/budgie", "tui"]})
    assert suite.hop("budgie", B, "{}", other) == [
        *TMUX, "respawn-window", "-k", "-t", "pi:=budgie",
        "-c", "/ws/budget/fy26", "-e", "PI_SUITE={}", "/venv/bin/budgie", "tui",
        ";", "set-option", "-w", "-t", "pi:=budgie", "@entry", B_KEY,
        ";", "select-window", "-t", "pi:=budgie",
    ]


def test_hop_without_a_recorded_entry_respawns():
    assert suite.hop("budgie", B, "{}", "")[3:5] == ["respawn-window", "-k"]


def test_launch_sets_every_option_before_the_first_window():
    m = {
        "perch": {"cwd": "/ws", "argv": ["/venv/bin/perch", "tui"]},
        "budgie": B,
        "gitboard": {"cwd": "/gb", "argv": ["gitboard", "tui", "grp/a"]},
    }
    argv = suite.launch(m["perch"], m)
    assert argv[:6] == [*TMUX, "-f", "/dev/null", "start-server"]
    first_window = argv.index("new-session")
    for flag, option, value in suite.OPTIONS:
        at = argv.index(option)
        assert argv[at - 1 : at + 2] == [flag, option, value]
        assert at < first_window
    env = f"PI_SUITE={json.dumps(m)}"
    assert argv[first_window : first_window + 13] == [
        "new-session", "-d", "-s", "pi", "-n", "perch",
        "-c", "/ws", "-e", env, "/venv/bin/perch", "tui", ";",
    ]
    assert argv.count("new-window") == 2
    for name in ("perch", "budgie", "gitboard"):
        at = argv.index(f"pi:={name}")
        assert argv[at + 1 : at + 3] == ["@entry", suite.entry_key(m[name])]
    assert argv[-4:] == [";", "select-window", "-t", "pi:=perch"]


def test_launch_without_a_map_starts_perch_alone():
    perch = {"cwd": "/ws", "argv": ["/venv/bin/perch", "tui"]}
    argv = suite.launch(perch, None)
    at = argv.index("new-session")
    assert argv[at:] == [
        "new-session", "-d", "-s", "pi", "-n", "perch", "-c", "/ws", "/venv/bin/perch", "tui",
        ";", "set-option", "-w", "-t", "pi:=perch", "@entry", suite.entry_key(perch),
        ";", "select-window", "-t", "pi:=perch",
    ]
    assert "new-window" not in argv


def test_launch_keeps_a_cwd_with_spaces_whole():
    m = {
        "perch": {"cwd": "/ws", "argv": ["perch", "tui"]},
        "budgie": {"cwd": "/ws/budget/My Budget", "argv": ["budgie", "tui"]},
        "gitboard": {"cwd": "/gb", "argv": ["gitboard", "tui"]},
    }
    argv = suite.launch(m["perch"], m)
    assert argv[argv.index("/ws/budget/My Budget") - 1] == "-c"


def test_session_commands():
    assert suite.has_session() == [*TMUX, "has-session", "-t", "pi"]
    assert suite.attach() == [*TMUX, "attach", "-t", "pi"]
    assert suite.kill() == [*TMUX, "kill-session", "-t", "pi"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_suite.py -q`
Expected: FAIL, `ImportError: cannot import name 'suite' from 'perch.core'`.

- [ ] **Step 3: Write `perch/core/suite.py`**

```python
"""perch suite: the three TUIs in one hidden tmux, and the hop between them.

Pure, like steps.py: every function returns a tmux argv; nothing here runs
one. Budgie (budgie/tui.py) and gitboard (gitboard/cli.py) carry their own
copy of ``in_suite`` and the hop rule, because neither depends on perch: a
change to the rule is a change in all three.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping

SOCKET = "pi"  # tmux -L pi: the suite's own server, never the user's tmux
SESSION = "pi"
SUITE = "PI_SUITE"
TMUX = ("tmux", "-L", SOCKET)

# (set-option flag, option, value), sent before any window exists: tmux reads
# default-terminal when a pane spawns. -s server, -gw window, -g session.
OPTIONS = (
    ("-g", "status", "off"),
    ("-g", "prefix", "None"),
    ("-g", "prefix2", "None"),
    ("-s", "escape-time", "0"),
    ("-s", "focus-events", "on"),
    ("-g", "default-terminal", "tmux-256color"),
    ("-sa", "terminal-features", ",*:RGB"),
    ("-gw", "remain-on-exit", "off"),
    ("-g", "destroy-unattached", "off"),
)


def in_suite(env: Mapping[str, str]) -> bool:
    """Inside perch suite's tmux: $TMUX is "socket-path,pid,session"."""
    return os.path.basename(env.get("TMUX", "").split(",")[0]) == SOCKET


def entry_key(entry: Mapping) -> str:
    """What a window records in @entry: one entry, one text."""
    return json.dumps(entry, sort_keys=True)


def windows() -> list[str]:
    """One line per window: its name, a tab, its @entry (empty if unset)."""
    return [*TMUX, "list-windows", "-t", SESSION, "-F", "#{window_name}\t#{@entry}"]


def entry_of(listing: str, name: str) -> str | None:
    """``name``'s @entry from ``windows()`` output; None when no such window."""
    for line in listing.splitlines():
        window, _, entry = line.partition("\t")
        if window == name:
            return entry
    return None


def _target(name: str) -> str:
    return f"{SESSION}:={name}"


def _start(entry: Mapping, suite_env: str | None) -> list[str]:
    env = ["-e", f"{SUITE}={suite_env}"] if suite_env is not None else []
    return ["-c", entry["cwd"], *env, *entry["argv"]]


def _mark(name: str, entry: Mapping) -> list[str]:
    return [";", "set-option", "-w", "-t", _target(name), "@entry", entry_key(entry)]


def hop(name: str, entry: Mapping, suite_env: str, current: str | None) -> list[str]:
    """Bring ``name`` to the front, running ``entry``.

    ``current`` is ``entry_of`` for that window. The same entry: select it (the
    instant path). None: the app was quit, open it again. Anything else
    (another project, or nothing recorded): restart only that window.
    """
    if current == entry_key(entry):
        return [*TMUX, "select-window", "-t", _target(name)]
    if current is None:
        return [
            *TMUX, "new-window", "-t", f"{SESSION}:", "-n", name,
            *_start(entry, suite_env), *_mark(name, entry),
        ]  # fmt: skip
    return [
        *TMUX, "respawn-window", "-k", "-t", _target(name),
        *_start(entry, suite_env), *_mark(name, entry),
        ";", "select-window", "-t", _target(name),
    ]  # fmt: skip


def launch(perch: Mapping, suite: Mapping | None) -> list[str]:
    """Start the suite detached: options, perch in front, Budgie and gitboard
    warming up behind it. ``suite`` None (a bad project config): perch alone,
    and its hops open the others later."""
    argv = [*TMUX, "-f", "/dev/null", "start-server"]
    for flag, option, value in OPTIONS:
        argv += [";", "set-option", flag, option, value]
    env = json.dumps(suite) if suite is not None else None
    argv += [";", "new-session", "-d", "-s", SESSION, "-n", "perch", *_start(perch, env)]
    argv += _mark("perch", perch)
    for name in ("budgie", "gitboard") if suite is not None else ():
        argv += [";", "new-window", "-d", "-t", f"{SESSION}:", "-n", name]
        argv += [*_start(suite[name], env), *_mark(name, suite[name])]
    return [*argv, ";", "select-window", "-t", _target("perch")]


def has_session() -> list[str]:
    return [*TMUX, "has-session", "-t", SESSION]


def attach() -> list[str]:
    return [*TMUX, "attach", "-t", SESSION]


def kill() -> list[str]:
    return [*TMUX, "kill-session", "-t", SESSION]
```

- [ ] **Step 4: Run the core tests**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_suite.py -q`
Expected: PASS (12 tests).

- [ ] **Step 5: Write the failing `perch suite` tests**

Append to `perch/tests/test_suite.py`:

```python
# --- perch suite ---------------------------------------------------------------


@pytest.fixture
def tmux(monkeypatch):
    """tmux on PATH; records each argv and env. has-session fails until .up."""
    calls = []

    class Fake:
        up = False
        execs = []

    def run(argv, **kw):
        calls.append((list(argv), kw.get("env")))
        code = 0 if "has-session" not in argv or Fake.up else 1
        return subprocess.CompletedProcess(argv, code, "", "")

    Fake.execs = []
    Fake.calls = calls
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/tmux")
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("os.execvpe", lambda f, a, env: Fake.execs.append((f, a, env)))
    monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,1,0")  # started from the user's tmux
    return Fake


def _perch(home):
    return {"cwd": str(home.root), "argv": [str(Path(sys.executable).parent / "perch"), "tui"]}


def test_suite_without_tmux_says_how_to_get_it(tmp_path, monkeypatch):
    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    monkeypatch.setattr("shutil.which", lambda name: None)
    r = CliRunner().invoke(cli, ["suite"])
    assert r.exit_code == 1
    assert "needs tmux: brew install tmux" in r.output


def test_suite_running_just_attaches_outside_the_users_tmux(tmp_path, monkeypatch, tmux):
    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    tmux.up = True
    assert CliRunner().invoke(cli, ["suite"]).exit_code == 0
    assert [argv for argv, _ in tmux.calls] == [suite.has_session()]
    (file, argv, env), = tmux.execs
    assert (file, argv) == ("tmux", suite.attach())
    assert "TMUX" not in env


def test_suite_cold_start_launches_then_attaches(tmp_path, monkeypatch, tmux):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    assert CliRunner().invoke(cli, ["suite"]).exit_code == 0
    launched = [argv for argv, _ in tmux.calls][1]
    assert launched == suite.launch(_perch(home), tui.suite_map(home, "apollo"))
    assert "TMUX" not in tmux.calls[1][1]
    assert tmux.execs[0][1] == suite.attach()


def test_suite_without_p_opens_on_the_first_project(tmp_path, monkeypatch, tmux):
    home = build_home(tmp_path, "apollo", "beta")
    monkeypatch.chdir(tmp_path / "ws")
    assert CliRunner().invoke(cli, ["suite"]).exit_code == 0
    assert tmux.calls[1][0] == suite.launch(_perch(home), tui.suite_map(home, "apollo"))


def test_suite_p_picks_the_project(tmp_path, monkeypatch, tmux):
    home = build_home(tmp_path, "apollo", "beta")
    monkeypatch.chdir(tmp_path / "ws")
    assert CliRunner().invoke(cli, ["suite", "-p", "beta"]).exit_code == 0
    assert tmux.calls[1][0] == suite.launch(_perch(home), tui.suite_map(home, "beta"))


def test_suite_unknown_project_starts_nothing(tmp_path, monkeypatch, tmux):
    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    r = CliRunner().invoke(cli, ["suite", "-p", "nosuch"])
    assert r.exit_code == 1
    assert "no project 'nosuch'" in r.output and "apollo" in r.output
    assert [argv for argv, _ in tmux.calls] == [suite.has_session()]
    assert tmux.execs == []


def test_suite_bad_config_starts_perch_alone(tmp_path, monkeypatch, tmux):
    home = build_home(tmp_path, "apollo")
    home.config_path("apollo").write_text("people: {}\n")  # no budgie_project
    monkeypatch.chdir(tmp_path / "ws")
    r = CliRunner().invoke(cli, ["suite"])
    assert r.exit_code == 0
    assert "budgie_project" in r.output and "perch only" in r.output
    assert tmux.calls[1][0] == suite.launch(_perch(home), None)


def test_suite_tmux_refusing_to_start_says_why(tmp_path, monkeypatch, tmux):
    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")

    def run(argv, **kw):
        if "start-server" in argv:
            return subprocess.CompletedProcess(argv, 1, "", "unknown option: focus-events")
        return subprocess.CompletedProcess(argv, 1, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    r = CliRunner().invoke(cli, ["suite"])
    assert r.exit_code == 1
    assert "unknown option: focus-events" in r.output
    assert tmux.execs == []
```

Check `build_home`'s workspace folder before running: the existing CLI tests
`monkeypatch.chdir(tmp_path / "ws")` (see `test_perch_tui_execs_the_target_it_exited_with`),
so `tmp_path / "ws"` is the workspace root.

- [ ] **Step 6: Run them to see them fail**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_suite.py -q -k suite_`
Expected: FAIL, `No such command 'suite'`.

- [ ] **Step 7: Add `perch suite` to `perch/cli.py`**

Put it directly after the `tui` command:

```python
@cli.command()
@_project_option
def suite(project):
    """perch, Budgie and gitboard side by side; P, B and G hop between them at once.

    Runs them in a hidden tmux of their own. Closing the terminal leaves the
    suite running: run this again to come back to it. q in perch closes it.
    """
    import shutil

    from perch import tui as tui_mod
    from perch.core import suite as suite_mod

    if shutil.which("tmux") is None:
        raise click.ClickException("needs tmux: brew install tmux")
    env = {k: v for k, v in os.environ.items() if k != "TMUX"}  # from inside a tmux too
    running = subprocess.run(suite_mod.has_session(), capture_output=True, env=env)
    if running.returncode:
        home = _home()
        names = home.projects()
        if project is not None:
            try:
                home.select(project)
            except ValueError as exc:
                raise click.ClickException(str(exc)) from exc
        name = project or (names[0] if names else None)
        perch = {"cwd": str(home.root), "argv": [str(_bin_dir() / "perch"), "tui"]}
        suite_map = None
        if name is not None:
            try:
                suite_map = tui_mod.suite_map(home, name)
            except tui_mod._ERRORS as exc:
                click.echo(f"{name}: {exc}; starting perch only", err=True)
        started = subprocess.run(
            suite_mod.launch(perch, suite_map), capture_output=True, text=True, env=env
        )
        if started.returncode:
            raise click.ClickException(f"tmux: {started.stderr.strip()}")
    os.execvpe("tmux", suite_mod.attach(), env)
```

`CliRunner` mixes stderr into `r.output` by default in this click version;
if `test_suite_bad_config_starts_perch_alone` cannot see the message, check
`r.stderr` instead (`CliRunner(mix_stderr=False)` is gone in click 8.2).

- [ ] **Step 8: Run the suite tests**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_suite.py -q`
Expected: PASS (19 tests).

- [ ] **Step 9: Write the failing perch hop and quit tests**

In `perch/tests/test_tui.py`, add after `test_perch_tui_execs_the_target_it_exited_with`:

```python
# --- in perch suite: hop to the window, never exit ---------------------------

SUITE_TMUX = "/private/tmp/tmux-501/pi,123,0"


@pytest.fixture
def hops(monkeypatch):
    """In the suite; every tmux argv run, list-windows answering .listing."""
    calls = []

    class Fake:
        listing = ""
        stderr = ""  # non-empty: the hop call fails with it

    def run(argv, **kw):
        calls.append(list(argv))
        if "list-windows" in argv:
            return subprocess.CompletedProcess(argv, 0, Fake.listing, "")
        return subprocess.CompletedProcess(argv, 1 if Fake.stderr else 0, "", Fake.stderr)

    Fake.calls = calls
    monkeypatch.setattr(subprocess, "run", run)
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
        assert len(hops.calls) == 2
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


def test_q_in_perch_suite_closes_the_suite(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from perch.cli import cli
    from perch.core import suite

    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    monkeypatch.setenv("TMUX", SUITE_TMUX)
    monkeypatch.setattr(tui.PerchTUI, "run", lambda self: None)
    ran = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: ran.append(argv))
    assert CliRunner().invoke(cli, ["tui"]).exit_code == 0
    assert ran == [suite.kill()]


def test_q_outside_the_suite_just_quits(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from perch.cli import cli

    build_home(tmp_path, "apollo")
    monkeypatch.chdir(tmp_path / "ws")
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(tui.PerchTUI, "run", lambda self: None)
    ran = []
    monkeypatch.setattr(subprocess, "run", lambda argv, **kw: ran.append(argv))
    assert CliRunner().invoke(cli, ["tui"]).exit_code == 0
    assert ran == []


def test_switch_with_an_empty_program_says_why(tmp_path):
    with pytest.raises(SystemExit) as exc:
        tui.switch({"cwd": str(tmp_path), "argv": [""]})
    assert "switch failed" in str(exc.value.code)
```

Add `monkeypatch.delenv("TMUX", raising=False)` as the first line of the
existing outside-the-suite tests `test_b_and_g_set_pi_suite_and_exit_with_the_target`
and `test_switching_while_a_command_runs_says_busy` (give the first a
`monkeypatch` argument; it has one). Otherwise they fail whenever the tests
are run from inside the suite.

- [ ] **Step 10: Run them to see them fail**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_tui.py -q -k "suite or empty_program"`
Expected: FAIL (perch exits with the target; no kill call; `ValueError` traceback from `switch`).

- [ ] **Step 11: Hop in `perch/tui.py`, kill in `perch/cli.py`**

In `perch/tui.py`, add to the `perch.core` imports:

```python
from perch.core.suite import entry_of, hop, in_suite, windows
```

Make `switch` catch `ValueError` too (perch-dvq item 1):

```python
def switch(entry: dict) -> None:
    """Become the other app. Call only once the terminal is restored."""
    try:
        os.chdir(entry["cwd"])
        os.execvp(entry["argv"][0], entry["argv"])
    except (OSError, ValueError) as exc:  # ValueError: an empty program name
        sys.exit(f"switch failed: {exc}")
```

Replace `PerchTUI.action_switch` and add `_hop` after it:

```python
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
            listing = subprocess.run(windows(), capture_output=True, text=True).stdout
            current = entry_of(listing, target)
            argv = hop(target, apps[target], json.dumps(apps), current)
            done = subprocess.run(argv, capture_output=True, text=True)
        except OSError as exc:
            self.notify(f"{target}: switch failed: {exc}", severity="error")
            return
        if done.returncode:
            self.notify(f"{target}: switch failed: {done.stderr.strip()}", severity="error")
```

In `perch/cli.py`, change the end of the `tui` command:

```python
    target = tui_mod.PerchTUI(_home()).run()
    if target:
        tui_mod.switch(tui_mod.suite_entry(target))
    elif tui_mod.in_suite(os.environ):  # q in perch suite closes the whole suite
        from perch.core.suite import kill

        subprocess.run(kill())
```

- [ ] **Step 12: Run perch's whole suite and the linter**

Run: `~/Documents/tools/perch/bin/pytest -q && ~/Documents/tools/perch/bin/ruff check . && ~/Documents/tools/perch/bin/ruff format --check .`
Expected: all pass. If `ruff format` reflows the `# fmt: skip` lists, leave
them skipped; reformat anything else it flags.

- [ ] **Step 13: Smoke test by hand**

Never `pip install -e` the worktree: that repoints the shared venv for every
other session and breaks `perch` when the worktree goes. Put the worktree
first on the path instead; the tmux server inherits it, so the perch windows
run worktree code and Budgie and gitboard stay as installed:

```bash
tmux -L pi kill-server 2>/dev/null   # a suite left from an earlier try
PYTHONPATH=/Users/ryanadams/Documents/git/pi_suite/perch/.claude/worktrees/tmux-suite perch suite
```

Expected: perch fills the terminal, no tmux bar. `B`: Budgie at once. Quit
Budgie with `q`: back on another window. `B` again: Budgie reopens. `q` in
perch: the shell, clean (type a few characters; they echo). Budgie and
gitboard still exec-on-hop until Tasks 2-3 land; that is expected.

- [ ] **Step 14: Commit and close**

```bash
git add perch/core/suite.py perch/tests/test_suite.py perch/tui.py perch/cli.py perch/tests/test_tui.py
git commit -m "feat(suite): perch suite, a hidden tmux where P/B/G hop to running apps (perch-a2b.1)"
bd close perch-a2b.1 --reason "perch suite + core/suite.py hop rule + perch hop/quit; tests in test_suite.py and test_tui.py"
```

---

### Task 2: Budgie -- hop in the suite, recalculate on focus (bead `perch-a2b.2`)

**Files:**
- Modify: `budgie/tui.py` (beside `suite_entry`/`switch`; `BudgieTUI.__init__`,
  `action_switch`, `recalculate`; new `on_app_focus`, `_inputs_mtime`)
- Modify: `budgie/tests/test_tui.py` (switch section)
- Modify: `README.md` (`budgie tui` section)

All paths relative to `/Users/ryanadams/Documents/git/pi_suite/budgie`.

**Interfaces:**
- Consumes: the hop rule and constants from Task 1's `perch/core/suite.py`
  (copied here, not imported); `suite_entry(name)`, `SUITE`, `NO_SUITE`
  (exist); `Workspace.inputs() -> list[InputFile]` with `.path`, `.exists`.
- Produces: `budgie.tui.in_suite() -> bool`, `budgie.tui.hop(name: str, entry: dict) -> str | None`
  (None on success, else tmux's complaint).

- [ ] **Step 0: Claim and isolate**

```bash
cd /Users/ryanadams/Documents/git/pi_suite/perch && bd update perch-a2b.2 --claim
cd /Users/ryanadams/Documents/git/pi_suite/budgie && git fetch origin
git worktree add .claude/worktrees/tmux-suite -b tmux-suite origin/main
cd .claude/worktrees/tmux-suite
```

- [ ] **Step 1: Write the failing tests**

In `budgie/tests/test_tui.py`, add `import subprocess` and `import time` to
the imports, then append to the "switching to perch and gitboard" section:

```python
SUITE_TMUX = "/private/tmp/tmux-501/pi,123,0"
TMUX = ["tmux", "-L", "pi"]
G_KEY = json.dumps(SUITE["gitboard"], sort_keys=True)


@pytest.fixture
def hops(monkeypatch):
    """In perch suite; records tmux argv; list-windows answers .listing."""
    calls = []

    class Fake:
        listing = ""
        stderr = ""

    def run(argv, **kw):
        calls.append(list(argv))
        if "list-windows" in argv:
            return subprocess.CompletedProcess(argv, 0, Fake.listing, "")
        return subprocess.CompletedProcess(argv, 1 if Fake.stderr else 0, "", Fake.stderr)

    Fake.calls = calls
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setenv("TMUX", SUITE_TMUX)
    monkeypatch.setenv("PI_SUITE", json.dumps(SUITE))
    return Fake


def test_in_suite_only_on_the_pi_socket(monkeypatch):
    monkeypatch.setenv("TMUX", SUITE_TMUX)
    assert tui_mod.in_suite()
    monkeypatch.setenv("TMUX", "/private/tmp/tmux-501/default,1,0")
    assert not tui_mod.in_suite()
    monkeypatch.delenv("TMUX")
    assert not tui_mod.in_suite()


def test_hop_to_the_same_entry_only_selects(hops):
    hops.listing = f"perch\t{{}}\ngitboard\t{G_KEY}\n"
    assert tui_mod.hop("gitboard", SUITE["gitboard"]) is None
    assert hops.calls[-1] == [*TMUX, "select-window", "-t", "pi:=gitboard"]


def test_hop_to_a_missing_window_opens_it(hops):
    hops.listing = "perch\t{}\n"
    tui_mod.hop("gitboard", SUITE["gitboard"])
    assert hops.calls == [
        [*TMUX, "list-windows", "-t", "pi", "-F", "#{window_name}\t#{@entry}"],
        [
            *TMUX, "new-window", "-t", "pi:", "-n", "gitboard",
            "-c", "/gb", "-e", f"PI_SUITE={json.dumps(SUITE)}", "gitboard", "tui", "grp/a",
            ";", "set-option", "-w", "-t", "pi:=gitboard", "@entry", G_KEY,
        ],
    ]


def test_hop_to_another_entry_respawns_only_that_window(hops):
    hops.listing = 'gitboard\t{"argv": ["gitboard", "tui", "grp/b"], "cwd": "/gb"}\n'
    tui_mod.hop("gitboard", SUITE["gitboard"])
    assert hops.calls[-1] == [
        *TMUX, "respawn-window", "-k", "-t", "pi:=gitboard",
        "-c", "/gb", "-e", f"PI_SUITE={json.dumps(SUITE)}", "gitboard", "tui", "grp/a",
        ";", "set-option", "-w", "-t", "pi:=gitboard", "@entry", G_KEY,
        ";", "select-window", "-t", "pi:=gitboard",
    ]


def test_hop_without_a_recorded_entry_respawns(hops):
    hops.listing = "gitboard\t\n"
    tui_mod.hop("gitboard", SUITE["gitboard"])
    assert hops.calls[-1][3:5] == ["respawn-window", "-k"]


def test_hop_that_tmux_refuses_says_why(hops):
    hops.stderr = "no server running"
    assert tui_mod.hop("perch", SUITE["perch"]) == "no server running"


async def test_in_the_suite_p_hops_and_budgie_keeps_running(tmp_path, monkeypatch, hops):
    init_workspace(tmp_path, year=2026)
    monkeypatch.chdir(tmp_path)
    app = BudgieTUI()
    async with app.run_test() as pilot:
        await pilot.press("P")
        await pilot.pause()
        assert app.is_running
    assert hops.calls[-1][3] == "new-window"


async def test_in_the_suite_a_failed_hop_says_why(tmp_path, monkeypatch, hops):
    hops.stderr = "no server running"
    monkeypatch.chdir(tmp_path)
    app = BudgieTUI()
    said = []
    monkeypatch.setattr(app, "notify", lambda msg, **kw: said.append(msg))
    async with app.run_test() as pilot:
        await pilot.press("G")
        await pilot.pause()
        assert app.is_running
    assert said == ["switch failed: no server running"]


async def test_in_the_suite_a_bad_map_still_says_where_to_start(tmp_path, monkeypatch, hops):
    monkeypatch.setenv("PI_SUITE", "not json")
    monkeypatch.chdir(tmp_path)
    app = BudgieTUI()
    said = []
    monkeypatch.setattr(app, "notify", lambda msg, **kw: said.append(msg))
    async with app.run_test() as pilot:
        await pilot.press("P")
        await pilot.pause()
    assert said == ["start from perch tui to switch apps"]
    assert hops.calls == []


def test_switch_with_an_empty_program_says_why(tmp_path):
    with pytest.raises(SystemExit) as exc:
        tui_mod.switch({"cwd": str(tmp_path), "argv": [""]})
    assert "switch failed" in str(exc.value.code)


async def test_focus_recalculates_only_after_an_input_changed(tmp_path, monkeypatch):
    from textual import events

    init_workspace(tmp_path, year=2026)
    monkeypatch.chdir(tmp_path)
    app = BudgieTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        ran = []
        monkeypatch.setattr(app, "recalculate", lambda: ran.append(1))
        app.post_message(events.AppFocus())
        await pilot.pause()
        assert ran == []  # nothing touched since the last calculation
        touched = next(i.path for i in app.workspace.inputs() if i.exists)
        later = time.time() + 10
        os.utime(touched, (later, later))
        app.post_message(events.AppFocus())
        await pilot.pause()
        assert ran == [1]
```

The focus test assumes the app's first `recalculate()` runs on mount (it
computes the Forecast tab there). If `on_mount` reaches the forecast some other
way, set `self._calculated_at = self._inputs_mtime()` at the end of `on_mount`
too.

Add `monkeypatch.delenv("TMUX", raising=False)` as the first line of the
existing `test_p_and_g_exit_with_the_target`; otherwise it fails whenever the
tests are run from inside the suite.

- [ ] **Step 2: Run them to see them fail**

Run: `make test` (or `~/Documents/tools/budgie/bin/pytest budgie/tests/test_tui.py -q`)
Expected: FAIL, `AttributeError: module 'budgie.tui' has no attribute 'in_suite'`.

- [ ] **Step 3: Implement**

In `budgie/tui.py`, after `switch`, add:

```python
PI = "pi"  # perch suite's tmux: the server (-L pi) and its session


def in_suite() -> bool:
    """Inside `perch suite`: hop to the app's tmux window instead of exec."""
    return os.path.basename(os.environ.get("TMUX", "").split(",")[0]) == PI


def hop(name: str, entry: dict) -> str | None:
    """Bring ``name``'s window to the front; tmux's complaint, or None.

    Same entry running there: just select it. Another (another project) or
    none recorded: restart that window only. No window (the app was quit):
    open it. A copy of perch/core/suite.py's rule: a change goes in all three.
    """
    tmux, window = ["tmux", "-L", PI], f"{PI}:={name}"
    key = json.dumps(entry, sort_keys=True)
    start = ["-c", entry["cwd"], "-e", f"{SUITE}={os.environ.get(SUITE, '')}", *entry["argv"]]
    mark = [";", "set-option", "-w", "-t", window, "@entry", key]
    try:
        listing = subprocess.run(
            [*tmux, "list-windows", "-t", PI, "-F", "#{window_name}\t#{@entry}"],
            capture_output=True, text=True,
        ).stdout
        entries = dict(line.split("\t", 1) for line in listing.splitlines() if "\t" in line)
        if name not in entries:
            argv = [*tmux, "new-window", "-t", f"{PI}:", "-n", name, *start, *mark]
        elif entries[name] == key:
            argv = [*tmux, "select-window", "-t", window]
        else:
            argv = [*tmux, "respawn-window", "-k", "-t", window, *start, *mark,
                    ";", "select-window", "-t", window]  # fmt: skip
        done = subprocess.run(argv, capture_output=True, text=True)
    except OSError as exc:
        return str(exc)
    return (done.stderr.strip() or "tmux failed") if done.returncode else None
```

Make `switch` catch `ValueError` too (perch-dvq item 1):

```python
    except (OSError, ValueError) as exc:  # ValueError: an empty program name
        sys.exit(f"switch failed: {exc}")
```

Replace `BudgieTUI.action_switch`:

```python
    def action_switch(self, target: str) -> None:
        """perch or gitboard: in perch suite a hop to its window (Budgie keeps
        running), else hand over the terminal. Nothing written is lost."""
        entry = suite_entry(target)
        if entry is None:
            self.notify(NO_SUITE, severity="warning")
            return
        if in_suite():
            why = hop(target, entry)
            if why:
                self.notify(f"switch failed: {why}", severity="error")
            return
        self.exit(target)
```

In `BudgieTUI.__init__`, after `self._unknown_confirmed = None`:

```python
        # The newest input file's mtime at the last recalculate: a focus
        # (a hop back in perch suite) recalculates only past it.
        self._calculated_at = 0.0
```

At the top of `recalculate`, before `year = ...`:

```python
        self._calculated_at = self._inputs_mtime()
```

Add beside `action_recalculate`:

```python
    def on_app_focus(self) -> None:
        """Back in front (a hop in perch suite): recalculate only if an input
        changed meanwhile; a full forecast on every hop would make hops slow."""
        if self._inputs_mtime() > self._calculated_at:
            self.recalculate()

    def _inputs_mtime(self) -> float:
        if self.workspace is None:
            return 0.0
        inputs = self.workspace.inputs()
        return max((i.path.stat().st_mtime for i in inputs if i.exists), default=0.0)
```

- [ ] **Step 4: Run Budgie's tests and linter**

Run: `make test && make lint` (Budgie's Makefile; else `pytest -q` and `ruff check .` from the venv)
Expected: all pass.

- [ ] **Step 5: README key line (perch-dvq item 3)**

In `README.md`, section `### \`budgie tui\``, after the numbered tab list and
before the next `###`, add:

```markdown
`P` and `G` jump to perch and gitboard on the same project. Inside `perch suite`
the jump is instant and each app stays where you left it; started from
`perch tui`, the app you leave closes and the other opens. Started on its own,
Budgie says where to start instead.
```

- [ ] **Step 6: Commit and close**

```bash
git add budgie/tui.py budgie/tests/test_tui.py README.md
git commit -m "feat(tui): hop to the running app inside perch suite; recalculate on focus when inputs changed (perch-a2b.2)"
cd /Users/ryanadams/Documents/git/pi_suite/perch
bd close perch-a2b.2 --reason "Budgie in_suite/hop, focus recalculate on changed inputs, switch ValueError, README keys"
```

---

### Task 3: gitboard -- hop in the suite key loop (bead `perch-a2b.3`)

**Files:**
- Modify: `src/gitboard/cli.py` (beside `_suite_entry`/`_switch`; the
  `if raw in SWITCH:` branch in `tui`'s key loop)
- Modify: `tests/test_cli.py` (the "P and B hand the terminal" section)
- Modify: `docs/commands.md` (TUI key table)

All paths relative to `/Users/ryanadams/Documents/git/pi_suite/remote-gitboard`.

**Interfaces:**
- Consumes: the hop rule from Task 1 (copied); `_suite_entry`, `SWITCH`,
  `SUITE`, `NO_SUITE` (exist); the `Tui` test driver and `write_spec`.
- Produces: `cli._in_suite() -> bool`, `cli._hop(name, entry) -> str | None`.

gitboard does not turn on focus reporting, so tmux sends it no focus
sequences and there is nothing to filter in `_key`. Do not add a refresh.

- [ ] **Step 0: Claim and isolate**

```bash
cd /Users/ryanadams/Documents/git/pi_suite/perch && bd update perch-a2b.3 --claim
cd /Users/ryanadams/Documents/git/pi_suite/remote-gitboard && git fetch origin
git worktree add .claude/worktrees/tmux-suite -b tmux-suite origin/main
cd .claude/worktrees/tmux-suite
```

- [ ] **Step 1: Write the failing tests**

Append to the PI_SUITE section of `tests/test_cli.py` (after
`test_tui_switch_that_cannot_exec_exits_1`):

```python
SUITE_TMUX = "/private/tmp/tmux-501/pi,123,0"
TMUX = ["tmux", "-L", "pi"]
P_KEY = json.dumps(SUITE["perch"], sort_keys=True)


@pytest.fixture
def hops(monkeypatch):
    """In perch suite; records tmux argv; list-windows answers .listing."""
    calls = []

    class Fake:
        listing = ""
        stderr = ""

    def run(argv, **kw):
        calls.append(list(argv))
        if "list-windows" in argv:
            return subprocess.CompletedProcess(argv, 0, Fake.listing, "")
        return subprocess.CompletedProcess(argv, 1 if Fake.stderr else 0, "", Fake.stderr)

    Fake.calls = calls
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setenv("TMUX", SUITE_TMUX)
    return Fake


def test_in_suite_only_on_the_pi_socket(monkeypatch):
    monkeypatch.setenv("TMUX", SUITE_TMUX)
    assert cli._in_suite()
    monkeypatch.setenv("TMUX", "/private/tmp/tmux-501/default,1,0")
    assert not cli._in_suite()
    monkeypatch.delenv("TMUX")
    assert not cli._in_suite()


def test_hop_rule(hops, monkeypatch):
    monkeypatch.setenv("PI_SUITE", json.dumps(SUITE))
    env = f"PI_SUITE={json.dumps(SUITE)}"
    hops.listing = f"perch\t{P_KEY}\n"
    assert cli._hop("perch", SUITE["perch"]) is None
    assert hops.calls[-1] == [*TMUX, "select-window", "-t", "pi:=perch"]
    hops.listing = "gitboard\t{}\n"
    cli._hop("perch", SUITE["perch"])
    assert hops.calls[-1] == [
        *TMUX, "new-window", "-t", "pi:", "-n", "perch",
        "-c", "/ws", "-e", env, "perch", "tui",
        ";", "set-option", "-w", "-t", "pi:=perch", "@entry", P_KEY,
    ]
    hops.listing = "perch\t\n"
    cli._hop("perch", SUITE["perch"])
    assert hops.calls[-1] == [
        *TMUX, "respawn-window", "-k", "-t", "pi:=perch",
        "-c", "/ws", "-e", env, "perch", "tui",
        ";", "set-option", "-w", "-t", "pi:=perch", "@entry", P_KEY,
        ";", "select-window", "-t", "pi:=perch",
    ]


def test_tui_in_suite_shift_p_hops_and_stays(tui, tmp_path, monkeypatch, execs, hops):
    monkeypatch.setenv("PI_SUITE", json.dumps(SUITE))
    hops.listing = f"perch\t{P_KEY}\n"
    path = write_spec(tmp_path)
    tui.run(["P", "B", "q"], "--from", path, "--no-guide")
    assert execs == []
    assert [c[3] for c in hops.calls] == [
        "list-windows", "select-window", "list-windows", "new-window",
    ]


def test_tui_in_suite_a_failed_hop_shows_on_the_status_line(
    tui, tmp_path, monkeypatch, execs, hops
):
    monkeypatch.setenv("PI_SUITE", json.dumps(SUITE))
    hops.stderr = "no server running"
    path = write_spec(tmp_path)
    tui.run(["P", "q"], "--from", path, "--no-guide")
    assert "switch failed: no server running" in tui.text
    assert execs == []


def test_tui_in_suite_without_pi_suite_runs_no_tmux(tui, tmp_path, monkeypatch, execs, hops):
    monkeypatch.delenv("PI_SUITE", raising=False)
    path = write_spec(tmp_path)
    tui.run(["P", "q"], "--from", path, "--no-guide")
    assert "start from perch tui to switch apps" in tui.last
    assert hops.calls == []


def test_switch_with_an_empty_program_exits_1(tmp_path):
    with pytest.raises(typer.Exit):
        cli._switch({"cwd": str(tmp_path), "argv": [""]})
```

Add `import typer` to the test imports if it is not there. Add
`monkeypatch.delenv("TMUX", raising=False)` as the first line of the existing
`test_tui_shift_p_and_b_exec_the_target` and
`test_tui_unreachable_shift_p_still_switches`; otherwise they fail whenever
the tests are run from inside the suite.

Before running, `grep -n "subprocess.run" src/gitboard/cli.py src/gitboard/*.py`.
The `hops` fixture replaces `subprocess.run` process-wide; if the `tui --from`
path calls it for anything else (git, `open`), make the fake hand non-tmux
argv to the real one:

```python
    real = subprocess.run

    def run(argv, **kw):
        if argv[:1] != ["tmux"]:
            return real(argv, **kw)
        ...  # as above
```

If `tui.text`'s frames do not carry the status line for the failed hop,
assert on `tui.last` after the `P` frame instead; the status line is drawn by
`draw()` into the same `Live` frame as the board.

- [ ] **Step 2: Run them to see them fail**

Run: `make test` (or `PYTHONPATH=src .venv/bin/pytest tests/test_cli.py -q -k "suite or hop or empty_program"`)
Expected: FAIL, `AttributeError: module 'gitboard.cli' has no attribute '_in_suite'`.

- [ ] **Step 3: Implement**

In `src/gitboard/cli.py`, after `_switch`, add:

```python
PI = "pi"  # perch suite's tmux: the server (-L pi) and its session


def _in_suite():
    """Inside `perch suite`: hop to the app's tmux window instead of exec."""
    return os.path.basename(os.environ.get("TMUX", "").split(",")[0]) == PI


def _hop(name, entry):
    """Bring ``name``'s window to the front; tmux's complaint, or None.

    Same entry running there: just select it. Another (another project) or
    none recorded: restart that window only. No window (the app was quit):
    open it. A copy of perch/core/suite.py's rule: a change goes in all three.
    """
    tmux, window = ["tmux", "-L", PI], f"{PI}:={name}"
    key = json.dumps(entry, sort_keys=True)
    start = ["-c", entry["cwd"], "-e", f"{SUITE}={os.environ.get(SUITE, '')}", *entry["argv"]]
    mark = [";", "set-option", "-w", "-t", window, "@entry", key]
    try:
        listing = subprocess.run(
            [*tmux, "list-windows", "-t", PI, "-F", "#{window_name}\t#{@entry}"],
            capture_output=True, text=True,
        ).stdout
        entries = dict(line.split("\t", 1) for line in listing.splitlines() if "\t" in line)
        if name not in entries:
            argv = [*tmux, "new-window", "-t", f"{PI}:", "-n", name, *start, *mark]
        elif entries[name] == key:
            argv = [*tmux, "select-window", "-t", window]
        else:
            argv = [*tmux, "respawn-window", "-k", "-t", window, *start, *mark,
                    ";", "select-window", "-t", window]  # fmt: skip
        done = subprocess.run(argv, capture_output=True, text=True)
    except OSError as e:
        return str(e)
    return (done.stderr.strip() or "tmux failed") if done.returncode else None
```

Check `subprocess` is imported at the top of `cli.py`; add `import subprocess`
if not.

Make `_switch` catch `ValueError` too (perch-dvq item 1):

```python
    except (OSError, ValueError) as e:  # ValueError: an empty program name
```

Replace the `if raw in SWITCH:` branch in `tui`'s key loop:

```python
                if raw in SWITCH:  # before lowercasing turns P into plan
                    st["tip"] = None  # perch-dvq item 2: no stale guide tip
                    entry = _suite_entry(SWITCH[raw])
                    if entry and not _in_suite():
                        return SWITCH[raw]
                    if entry:  # perch suite: hop, keep the board running
                        why = _hop(SWITCH[raw], entry)
                        if why:
                            st["status"] = Text(f"switch failed: {why}", "logging.level.error")
                    else:
                        st["status"] = Text(NO_SUITE, "muted")
                    draw()
                    continue
```

- [ ] **Step 4: Run gitboard's tests and linter**

Run: `make test && make lint`
Expected: all pass.

- [ ] **Step 5: Key table (perch-dvq item 3)**

In `docs/commands.md`, in the first TUI key table, add two rows before
`| \`?\` | help |`:

```markdown
| `P` | perch on the same project (Shift+p): instant inside `perch suite`, else gitboard closes and perch opens |
| `B` | Budgie on the same project (Shift+b), the same way |
```

- [ ] **Step 6: Commit and close**

```bash
git add src/gitboard/cli.py tests/test_cli.py docs/commands.md
git commit -m "feat(tui): P and B hop to the running app inside perch suite (perch-a2b.3)"
cd /Users/ryanadams/Documents/git/pi_suite/perch
bd close perch-a2b.3 --reason "gitboard _in_suite/_hop in the key loop, tip cleared, switch ValueError, keys in commands.md"
```

---

### Task 4: perch -- refresh off the UI thread when the window comes to the front (bead `perch-a2b.4`)

**Files:**
- Modify: `perch/tui.py` (`PerchTUI`: new `on_app_focus`, `_refresh_behind`, `_fill`)
- Modify: `perch/tests/test_tui.py`

**Interfaces:**
- Consumes: `snapshot(home, name) -> (cells, change)`, `self.names`,
  `self.changes`, `self._report()`, `Coordinate`, `work` (all exist in `tui.py`).
- Produces: nothing other tasks use.

`action_refresh` stays synchronous: tests and the `h`/run paths expect the
cells right after it returns. Only a focus refresh goes to a thread.
`perch-li8` (the same for `r` and after a run) stays open.

- [ ] **Step 0: Claim**

```bash
cd /Users/ryanadams/Documents/git/pi_suite/perch && bd update perch-a2b.4 --claim
```

- [ ] **Step 1: Write the failing test**

Append to `perch/tests/test_tui.py`:

```python
def test_coming_to_the_front_refreshes_the_table_in_a_worker(tmp_path):
    from textual import events

    home = build_home(tmp_path, "apollo")

    async def script(app, pilot):
        assert _cells(app)[0][2] == "—"
        _team_row(home, "apollo", 500.0, "green")  # written by another app meanwhile
        app.post_message(events.AppFocus())
        await settle(app, pilot)
        assert _cells(app)[0][2:4] == ["GREEN", "$500"]

    run(tui.PerchTUI(home), script)


def test_a_focus_refresh_keeps_the_cursor(tmp_path):
    from textual import events

    home = build_home(tmp_path, "apollo", "beta")

    async def script(app, pilot):
        await pilot.press("down")
        at = app.query_one(DataTable).cursor_coordinate
        app.post_message(events.AppFocus())
        await settle(app, pilot)
        assert app.query_one(DataTable).cursor_coordinate == at

    run(tui.PerchTUI(home), script)
```

- [ ] **Step 2: Run it to see it fail**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_tui.py -q -k "front or focus_refresh"`
Expected: the first FAILS (cell still `—`); the second may pass already.

- [ ] **Step 3: Implement**

In `PerchTUI`, after `action_refresh`:

```python
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
        table = self.query_one(DataTable)
        for name, (cells, change) in snaps.items():
            if name not in self.names:  # removed while the worker ran
                continue
            self.changes[name] = change
            at = self.names.index(name)
            for col, cell in enumerate(cells):
                table.update_cell_at(Coordinate(at, col), cell, update_width=True)
        self._report()
```

- [ ] **Step 4: Run perch's tests and linter**

Run: `~/Documents/tools/perch/bin/pytest -q && ~/Documents/tools/perch/bin/ruff check .`
Expected: all pass.

- [ ] **Step 5: Commit and close**

```bash
git add perch/tui.py perch/tests/test_tui.py
git commit -m "feat(tui): refresh the table in a worker when perch comes to the front (perch-a2b.4)"
bd close perch-a2b.4 --reason "on_app_focus refreshes rows in a thread worker; cursor kept"
```

---

### Task 5: perch docs (bead `perch-a2b.5`)

**Files:**
- Modify: `CLAUDE.md` (Commands block; Architecture list)
- Modify: `README.md`
- Modify: `docs/reference.md`
- Modify: `docs/superpowers/specs/2026-10-02-tui-switch-design.md` (Status line)

- [ ] **Step 0: Claim**

```bash
cd /Users/ryanadams/Documents/git/pi_suite/perch && bd update perch-a2b.5 --claim
```

- [ ] **Step 1: `CLAUDE.md`**

In the Commands block, after the `perch --help` lines, add:

```bash
perch suite   # perch, Budgie and gitboard in a hidden tmux; P/B/G hop instantly
```

In the Architecture list, after `core/steps.py`, add:

```markdown
- `core/suite.py` -- `perch suite`'s tmux argv, built and never run here: a
  private server (`-L pi`, no config file, options sent as commands), one
  window per app, each window's `@entry` = the `{"cwd", "argv"}` it runs. The
  hop rule: same entry, select; another, respawn that window; none, open it.
  Budgie and gitboard carry their own copy; a change goes in all three.
```

In the `tui.py` paragraph, add one sentence: "In `perch suite` (`$TMUX` on the
`pi` socket) `B`/`G` hop to the running window instead of exiting, `q` closes
the whole suite, and coming to the front refreshes the rows in a worker."

- [ ] **Step 2: `README.md`**

After the install section, add:

```markdown
## The suite

    perch suite        # or: perch suite -p apollo

perch, Budgie and gitboard open side by side. `B` and `G` in perch (and `P`,
`B`, `G` in the others) jump between them at once, and each stays where you
left it. Close the terminal and the suite keeps running: `perch suite` again
picks it up. `q` in perch closes everything. It runs on tmux, which you never
have to touch (`brew install tmux` once).
```

- [ ] **Step 3: `docs/reference.md`**

Add a `perch suite` entry beside `perch tui`, with the same text as the
README section plus: "Without tmux it says `needs tmux: brew install tmux`. A
project whose config is broken opens perch alone; the others open on the
first hop."

- [ ] **Step 4: Old spec status (perch-dvq item 4)**

In `docs/superpowers/specs/2026-10-02-tui-switch-design.md`, change the
Status line to:

```markdown
Status: implemented (perch-2gr); in-suite hops superseded by 2026-10-02-tmux-suite-design.md
```

- [ ] **Step 5: Docs build, commit, close**

Run: `~/Documents/tools/perch/bin/pytest -q` (no code changed; confirms nothing else moved)

```bash
git add CLAUDE.md README.md docs/reference.md docs/superpowers/specs/2026-10-02-tui-switch-design.md
git commit -m "docs: perch suite (perch-a2b.5)"
bd close perch-a2b.5 --reason "CLAUDE.md, README, reference, old spec status"
bd close perch-dvq --reason "Folded into perch-a2b.1/.2/.3/.5"
```

---

## Finish

After Task 5: run each repo's tests in its worktree (`make test` in Budgie and
gitboard, `~/Documents/tools/perch/bin/pytest -q` in perch). Task 1's smoke
test is the only manual check that can run from worktrees: the installed
`budgie` and `gitboard` are the main checkouts. The full manual check (the
spec's Goal path; colours match outside tmux; Esc is immediate in Budgie's
Plan form; `q` in perch leaves a clean shell; `tmux ls` on your own server is
unchanged) happens after the user merges the three branches. Leave
`perch-a2b` open until then. Branches stay local until the user pushes them.
