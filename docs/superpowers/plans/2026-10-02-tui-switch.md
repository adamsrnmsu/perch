# TUI Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `P`, `B` and `G` jump between the perch, Budgie and gitboard TUIs by
replacing the running process.

**Architecture:** perch builds a JSON map of each app's working directory and
argv from the selected project, puts it in `$PI_SUITE`, exits its Textual app,
then `chdir` + `execvp`s the target. Budgie and gitboard each carry a copy of
the same two helpers: `suite_entry(name)` reads the map, and `switch(entry)`
does the chdir and exec. They check the entry while still running, so a switch
that can't happen shows a message instead of quitting.

**Tech Stack:** Python 3, Textual (perch, Budgie), rich + termios loop
(gitboard), pytest (+ pytest-asyncio auto mode in Budgie).

**Spec:** `perch/docs/superpowers/specs/2026-10-02-tui-switch-design.md`

## Global Constraints

- Env var name: `PI_SUITE`. JSON object, keys `perch`, `budgie`, `gitboard`;
  each value `{"cwd": str, "argv": [str, ...]}`.
- Keys: `P` = perch, `B` = budgie, `G` = gitboard. An app does not bind its own
  letter.
- Message when the map has no usable entry, the same text in all three apps:
  `start from perch tui to switch apps`
- Exec with `os.execvp`, never `subprocess`: hops must not stack.
- The terminal is restored before exec: exec happens only after Textual's
  `run()` returns, or after gitboard's `with Live` block has exited.
- The helpers are copied into each repo, not shared: gitboard must not depend
  on Budgie.
- Repos are on the Conservative profile: commit only when the user says so.
  The "Commit" steps below are the commands to run once they do.
- Beads live in perch's database (precedent: budgie commit 2703c8a carries
  perch-22d). Each task's implementer claims and closes its own bead.

## Review Focus

1. **`PI_SUITE` set but malformed** (bad JSON, entry not a mapping, empty argv).
   Expect the message, the app stays up, no traceback. Pinned in Task 2
   (`test_a_malformed_map_is_no_entry`).
2. **Target dir or binary gone at exec time** (budget folder deleted, `gitboard`
   not on PATH). The screen is already torn down, so expect one clear stderr
   line and exit 1, not a traceback. Pinned in Task 1
   (`test_switch_that_cannot_exec_says_why`) and Task 3
   (`test_tui_switch_that_cannot_exec_exits_1`).
3. **Pressing `B`/`G` in perch while a command streams.** Expect `busy: …`, no
   exit, so the child is not killed mid-run. Pinned in Task 1.
4. **Project with no `gitlab_project`.** Expect gitboard's argv to be just
   `gitboard tui` (falls back to `gitboard.toml`). Pinned in Task 1.
5. **gitboard's lowercase keys after the raw-key check.** `p`, `b` and `g` still
   plan, switch board and toggle the guide. Shift+G still toggles the guide,
   because gitboard does not bind its own letter. Pinned in Task 3
   (`test_tui_shift_g_still_toggles_the_guide`).

---

### Task 1: perch builds `PI_SUITE` and switches (bead: perch epic child 1)

**Files:**
- Modify: `perch/perch/tui.py` (imports, new module-level helpers after `row()`,
  `PerchTUI.BINDINGS`, new `action_switch`)
- Modify: `perch/perch/cli.py:985-990` (`tui` command)
- Test: `perch/perch/tests/test_tui.py` (append)

**Interfaces:**
- Produces: the `PI_SUITE` JSON contract in Global Constraints;
  `suite_map(home: Home, name: str) -> dict[str, dict]`;
  `suite_entry(name: str) -> dict | None`; `switch(entry: dict) -> None`
  (does not return on success; exits 1 with a message on `OSError`).
  Budgie and gitboard copy `suite_entry`/`switch` verbatim, apart from the exit
  call.

- [ ] **Step 1: Write the failing tests** (append to `perch/perch/tests/test_tui.py`)

```python
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
```

Add `import os` to the test file's imports.

- [ ] **Step 2: Run, see them fail**

Run: `cd perch && make test` (or `~/Documents/tools/perch/bin/pytest perch/tests/test_tui.py -q`)
Expected: FAIL. `AttributeError: module 'perch.tui' has no attribute 'suite_map'`.

- [ ] **Step 3: Implement in `perch/perch/tui.py`**

Add `import json` and `import sys` to the imports. After `row()`, add:

```python
SUITE = "PI_SUITE"  # JSON: app -> {"cwd", "argv"}; Budgie and gitboard read it
NO_SUITE = "start from perch tui to switch apps"


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
        "gitboard": {"cwd": str(home.gitboard_dir), "argv": ["gitboard", "tui", *gitlab]},
    }


def suite_entry(name: str) -> dict | None:
    """$PI_SUITE's entry for ``name``; None when unset, malformed or absent."""
    try:
        entry = json.loads(os.environ.get(SUITE, ""))[name]
        cwd, argv = str(entry["cwd"]), [str(a) for a in entry["argv"]]
        argv[0]  # noqa: B018 -- an empty argv is no entry
    except (ValueError, KeyError, TypeError, IndexError):
        return None
    return {"cwd": cwd, "argv": argv}


def switch(entry: dict) -> None:
    """Become the other app. Call only once the terminal is restored."""
    try:
        os.chdir(entry["cwd"])
        os.execvp(entry["argv"][0], entry["argv"])
    except OSError as exc:
        sys.exit(f"switch failed: {exc}")
```

In `PerchTUI.BINDINGS`, before the `?` line, add:

```python
        ("B", "switch('budgie')", "budgie"),
        ("G", "switch('gitboard')", "gitboard"),
```

After `action_hours`, add:

```python
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
```

- [ ] **Step 4: Implement in `perch/perch/cli.py`**: replace the `tui` body.

```python
@cli.command()
def tui():
    """Every project in one table; single keys run perch on the selected one."""
    from perch import tui as tui_mod

    target = tui_mod.PerchTUI(_home()).run()
    if target:
        tui_mod.switch(tui_mod.suite_entry(target))
```

Use the module (`tui_mod.switch`), not a `from` import, so the test's
monkeypatch of `tui.switch` takes effect.

- [ ] **Step 5: Run, see them pass**

Run: `cd perch && make test`
Expected: all pass, including the existing `test_tui.py` tests.

- [ ] **Step 6: Commit (when authorized)**

```bash
cd perch && git add perch/tui.py perch/cli.py perch/tests/test_tui.py docs/superpowers
git commit -m "feat(tui): B and G hand the terminal to Budgie or gitboard via PI_SUITE (<bead>)"
```

---

### Task 2: Budgie reads `PI_SUITE` (bead: child 2, blocked by 1)

**Files:**
- Modify: `budgie/budgie/tui.py` (imports, helpers above `class BudgieTUI`,
  `BINDINGS` at :273, new `action_switch`, `run()` at :906)
- Test: `budgie/budgie/tests/test_tui.py` (append)

**Interfaces:**
- Consumes: the `PI_SUITE` contract from Task 1.
- Produces: `budgie.tui.suite_entry(name) -> dict | None`,
  `budgie.tui.switch(entry) -> None`, the same as perch's.

- [ ] **Step 1: Write the failing tests** (append)

```python
# -- switching to perch and gitboard (PI_SUITE, set by perch tui) ------------

import json
import os

from budgie import tui as tui_mod

SUITE = {"perch": {"cwd": "/ws", "argv": ["perch", "tui"]},
         "gitboard": {"cwd": "/gb", "argv": ["gitboard", "tui", "grp/a"]}}


async def test_p_and_g_exit_with_the_target(tmp_path, monkeypatch):
    init_workspace(tmp_path, year=2026)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PI_SUITE", json.dumps(SUITE))
    for key, target in (("P", "perch"), ("G", "gitboard")):
        app = BudgieTUI()
        async with app.run_test() as pilot:
            await pilot.press(key)
            await pilot.pause()
        assert app.return_value == target


async def test_without_pi_suite_a_switch_key_says_where_to_start(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PI_SUITE", raising=False)
    app = BudgieTUI()
    said = []
    monkeypatch.setattr(app, "notify", lambda msg, **kw: said.append(msg))
    async with app.run_test() as pilot:
        await pilot.press("P")
        await pilot.pause()
        assert app.is_running
    assert said == ["start from perch tui to switch apps"]


def test_a_malformed_map_is_no_entry(monkeypatch):
    for bad in ("not json", "[]", '{"perch": 3}', '{"perch": {"cwd": "/", "argv": []}}'):
        monkeypatch.setenv("PI_SUITE", bad)
        assert tui_mod.suite_entry("perch") is None


def test_run_execs_the_target_after_the_app_exits(monkeypatch):
    monkeypatch.setenv("PI_SUITE", json.dumps(SUITE))
    monkeypatch.setattr(BudgieTUI, "run", lambda self: "perch")
    calls = []
    monkeypatch.setattr(os, "chdir", lambda d: calls.append(("chdir", d)))
    monkeypatch.setattr(os, "execvp", lambda f, a: calls.append(("exec", f, a)))
    tui_mod.run()
    assert calls == [("chdir", "/ws"), ("exec", "perch", ["perch", "tui"])]
```

Move the new imports to the top of the file with the others (ruff wants them
there).

- [ ] **Step 2: Run, see them fail**

Run: `cd budgie && make test` (or `~/Documents/tools/budgie/bin/pytest budgie/tests/test_tui.py -q`)
Expected: FAIL. `AttributeError: module 'budgie.tui' has no attribute 'suite_entry'`.

- [ ] **Step 3: Implement in `budgie/budgie/tui.py`**

Add `import json` and `import sys` to the imports. Above `class BudgieTUI`, add:

```python
SUITE = "PI_SUITE"  # set by `perch tui`: app -> {"cwd", "argv"}
NO_SUITE = "start from perch tui to switch apps"


def suite_entry(name: str) -> dict | None:
    """$PI_SUITE's entry for ``name``; None when unset, malformed or absent."""
    try:
        entry = json.loads(os.environ.get(SUITE, ""))[name]
        cwd, argv = str(entry["cwd"]), [str(a) for a in entry["argv"]]
        argv[0]  # noqa: B018 -- an empty argv is no entry
    except (ValueError, KeyError, TypeError, IndexError):
        return None
    return {"cwd": cwd, "argv": argv}


def switch(entry: dict) -> None:
    """Become the other app. Call only once the terminal is restored."""
    try:
        os.chdir(entry["cwd"])
        os.execvp(entry["argv"][0], entry["argv"])
    except OSError as exc:
        sys.exit(f"switch failed: {exc}")
```

In `BINDINGS`, before `("q", "quit", "Quit")`, add:

```python
        ("P", "switch('perch')", "perch"),
        ("G", "switch('gitboard')", "gitboard"),
```

Add the action to `BudgieTUI`:

```python
    def action_switch(self, target: str) -> None:
        """Hand the terminal to perch or gitboard; nothing written is lost."""
        if suite_entry(target) is None:
            self.notify(NO_SUITE, severity="warning")
            return
        self.exit(target)
```

Replace `run`:

```python
def run(csv_path: str | Path | None = None) -> None:
    target = BudgieTUI(csv_path).run()
    if target:
        switch(suite_entry(target))
```

- [ ] **Step 4: Run, see them pass**

Run: `cd budgie && make test`
Expected: all pass.

- [ ] **Step 5: Commit (when authorized)**

```bash
cd budgie && git add budgie/tui.py budgie/tests/test_tui.py
git commit -m "feat(tui): P and G hand the terminal to perch or gitboard via PI_SUITE (<bead>)"
```

---

### Task 3: gitboard reads `PI_SUITE` (bead: child 3, blocked by 1)

**Files:**
- Modify: `remote-gitboard/src/gitboard/cli.py`: helpers after `_run` (:148-154);
  in `tui`'s `go()`, the key read at :1813-1816 and `help_panel` (:1758);
  the `_run(go)` call that ends `tui` (:2137)
- Test: `remote-gitboard/tests/test_cli.py` (append after the tui section)

**Interfaces:**
- Consumes: the `PI_SUITE` contract from Task 1.
- Produces: `cli._suite_entry(name) -> dict | None`, `cli._switch(entry) -> None`.
  `go()` now returns the target name or None.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_cli.py`)

```python
# --- tui: P and B hand the terminal to perch or Budgie (PI_SUITE) -------------

SUITE = {"perch": {"cwd": "/ws", "argv": ["perch", "tui"]},
         "budgie": {"cwd": "/b", "argv": ["budgie", "tui"]}}


@pytest.fixture
def execs(monkeypatch):
    calls = []
    monkeypatch.setattr(os, "chdir", lambda d: calls.append(("chdir", d)))
    monkeypatch.setattr(os, "execvp", lambda f, a: calls.append(("exec", f, a)))
    return calls


def test_tui_shift_p_and_b_exec_the_target(tui, tmp_path, monkeypatch, execs):
    monkeypatch.setenv("PI_SUITE", json.dumps(SUITE))
    path = write_spec(tmp_path)
    tui.run(["P"], "--from", path, "--no-guide")
    tui.run(["B"], "--from", path, "--no-guide")
    assert execs == [
        ("chdir", "/ws"), ("exec", "perch", ["perch", "tui"]),
        ("chdir", "/b"), ("exec", "budgie", ["budgie", "tui"]),
    ]


def test_tui_switch_without_pi_suite_stays_and_says_why(tui, tmp_path, monkeypatch, execs):
    monkeypatch.delenv("PI_SUITE", raising=False)
    path = write_spec(tmp_path)
    tui.run(["P", "q"], "--from", path, "--no-guide")
    assert "start from perch tui to switch apps" in tui.last
    assert execs == []


def test_tui_shift_g_still_toggles_the_guide(tui, tmp_path, monkeypatch, execs):
    monkeypatch.setenv("PI_SUITE", json.dumps(SUITE))
    path = write_spec(tmp_path)
    tui.run(["G", "q"], "--from", path, "--no-guide")
    assert "guide on" in tui.text
    assert execs == []


def test_tui_switch_that_cannot_exec_exits_1(tui, tmp_path, monkeypatch):
    gone = {"perch": {"cwd": str(tmp_path / "gone"), "argv": ["perch", "tui"]}}
    monkeypatch.setenv("PI_SUITE", json.dumps(gone))
    path = write_spec(tmp_path)
    tui.keys = ["P"]
    r = runner.invoke(app, ["tui", "--from", path, "--no-guide"])
    assert r.exit_code == 1
    assert "switch failed" in tui.errbuf.getvalue()
```

Check that `os` and `json` are imported at the top of `tests/test_cli.py`, and
add them if not.

- [ ] **Step 2: Run, see them fail**

Run: `cd remote-gitboard && make test` (or `PYTHONPATH=src .venv/bin/pytest tests/test_cli.py -q -k "tui_s"`)
Expected: FAIL. `P` lowercases to `p` (plan), so nothing is exec'd and the
script runs out of keys.

- [ ] **Step 3: Implement the helpers in `cli.py`**, right after `_run`:

```python
SUITE = "PI_SUITE"  # set by `perch tui`: app -> {"cwd", "argv"}
SWITCH = {"P": "perch", "B": "budgie"}  # shifted, read before lowercasing
NO_SUITE = "start from perch tui to switch apps"


def _suite_entry(name):
    """$PI_SUITE's entry for ``name``; None when unset, malformed or absent."""
    try:
        entry = json.loads(os.environ.get(SUITE, ""))[name]
        cwd, argv = str(entry["cwd"]), [str(a) for a in entry["argv"]]
        argv[0]  # noqa: B018 -- an empty argv is no entry
    except (ValueError, KeyError, TypeError, IndexError):
        return None
    return {"cwd": cwd, "argv": argv}


def _switch(entry):
    """Become the other app. Call only once Live and termios are restored."""
    try:
        os.chdir(entry["cwd"])
        os.execvp(entry["argv"][0], entry["argv"])
    except OSError as e:
        err().print(f"[logging.level.error]error[/] switch failed: {e}")
        raise typer.Exit(1) from e
```

It uses `typer.Exit`, not `sys.exit`, because the tui test harness replaces
`cli.sys`.

- [ ] **Step 4: Wire it into the loop.** Replace

```python
                k = _key().lower()
                st["status"] = st["extra"] = st["prompt"] = None
```

with

```python
                raw = _key()
                k = raw.lower()
                st["status"] = st["extra"] = st["prompt"] = None
                if raw in SWITCH:  # before lowercasing turns P into plan
                    if _suite_entry(SWITCH[raw]):
                        return SWITCH[raw]
                    st["status"] = Text(NO_SUITE, "muted")
                    draw()
                    continue
```

In `help_panel`'s `lines`, before `("q", "quit")`, add:

```python
                ("P", "perch, B Budgie: switch app (when opened from perch tui)"),
```

Replace the `_run(go)` that ends `tui` (:2137; confirm it is `tui`'s by checking
it follows the `draw()` of the `y`/push branch) with:

```python
    target = _run(go)
    if target:
        _switch(_suite_entry(target))
```

- [ ] **Step 5: Run, see them pass**

Run: `cd remote-gitboard && make test`
Expected: all pass, including every existing `test_tui_*`.

- [ ] **Step 6: Commit (when authorized)**

```bash
cd remote-gitboard && git add src/gitboard/cli.py tests/test_cli.py
git commit -m "feat(tui): P and B hand the terminal to perch or Budgie via PI_SUITE (<bead>)"
```

---

### Task 4: Manual check in a real terminal (bead: child 4, blocked by 2 and 3)

No code. Install, then walk the spec's success path.

- [ ] **Step 1:** `make -f perch/suite.mk install` from `pi_suite/` (or the
  per-repo `make venv`). The perch venv must hold the edited Budgie: check
  `~/Documents/tools/perch/bin/pip show budgie` points at the local checkout.
- [ ] **Step 2:** `perch tui`, select a project, press `G`. gitboard opens on that
  project's board. Press `B`: Budgie opens on its budget. Press `P`: perch is
  back. Press `G` in Budgie: gitboard again.
- [ ] **Step 3:** After each hop, check: no leftover screen, the cursor is
  visible, and after the final `q` the shell echoes typed input.
- [ ] **Step 4:** `gitboard tui` on its own, press `P`: the status line shows
  `start from perch tui to switch apps`.
- [ ] **Step 5:** Close the epic with what was seen.
