# perch multi-project Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** perch runs several funded projects from one workspace, using perch commands (`perch monday -p apollo`, `perch monday --all`, `perch doctor`) instead of the make menu.

**Architecture:** Three new UI-free modules under `perch/core/`:
- `workspace.py`: find `perch-home.yaml`, list and select projects, scaffold a project's `perch.yaml`.
- `steps.py`: each Budgie, gitboard or perch call as a `Step(argv, cwd, env)` value, so the code that builds a step never executes it.
- `doctor.py`: `Check(ok, what, fix)` values.

`perch/cli.py` stays a thin adapter. It resolves `-p`, executes steps with `subprocess.run`, and prints. The Makefile shrinks to development targets.

**Tech Stack:** Python 3.11+, click, rich, PyYAML, pytest (existing perch stack; no new dependencies).

**Spec:** `docs/superpowers/specs/2026-10-01-multi-project-design.md`

**Bead:** perch-h3l (claimed). Close it with a reason when Task 7 lands.

## Global Constraints

- `perch/core/` imports no click and no rich. `perch/cli.py` keeps engine imports inside the commands (see CLAUDE.md "Architecture").
- perch never calls GitLab and never redoes budget math. Budgie and gitboard are only ever run as separate commands, never imported for this feature.
- Workspace marker: `perch-home.yaml`; its only key is `gitboard_dir`. The env fallback is `PERCH_HOME`.
- Layout: `projects/<name>/perch.yaml` and `budget/<name>/` (Budgie's own `budget/` container).
- A new optional `perch.yaml` key, `gitlab_project`.
- Selection order: `--config` wins; then `-p NAME`; then the only project; several projects → `several projects: a, b. Pass -p <name>.`; none → `no projects yet. Run: perch init <name>`.
- `monday` = fetch, board, weekly, digest, emails. `--all` runs projects in name order, carries on past a failure, prints `<name> ok` or `<name> FAILED: <step> exited <code>`, and exits 1 if any project failed.
- Nothing is ever sent. Nothing is retried.
- Run tests as `~/Documents/tools/perch/bin/python -m pytest` from the checkout root (or worktree root, so the code under edit is the code imported). Lint: `~/Documents/tools/perch/bin/ruff check .` and `ruff format --check perch`.
- Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01VbmeZgGwTWUCMPpgWj2Y2r
  ```

## Review Focus

1. **A new project before its first fetch.** Its `perch.yaml` names `dumps/board.json`, which doesn't exist yet. `doctor`, `projects`, `fetch` and `monday` must still work, and only `board`/`weekly`/`accuracy` may require the dump. (Task 1 `require_dump`; tested in Tasks 1, 4 and 6.)
2. **A project name that escapes the workspace.** `perch init ../x` or `-p ../x` must never write or read outside `projects/`. (Task 2 `check_name`; Task 5 init test.)
3. **Running from a subfolder, or with `PERCH_HOME` set in the shell.** `perch weekly` from inside `projects/apollo/weekly/` must find the workspace. A stray `PERCH_HOME` in the developer's shell must not leak into the tests. (Task 2 walk-up test; Task 3 autouse fixture.)
4. **An `$EDITOR` with flags** (`code -w`, `subl -w`) must open the file, not fail looking for an executable called `code -w`. (Task 3 `hours` test.)
5. **One broken project during `--all`** must not stop the others, and the exit code must say something failed, for cron. (Task 3 `run_projects`; Task 6 CLI test.)

---

## File Structure

| File | Responsibility |
|---|---|
| `perch/core/config.py` (modify) | `gitlab_project` key; `require_dump` flag |
| `perch/core/workspace.py` (new) | `Home`, `find_home`, `load_home`, `create_home`, `check_name`, `Home.scaffold` |
| `perch/core/steps.py` (new) | `Step`, `StepFailed`, step builders, `monday`, `iso_week`, `run_projects` |
| `perch/core/doctor.py` (new) | `Check`, `age`, `tool_checks`, `project_checks`, `freshness` |
| `perch/cli.py` (modify) | `-p`; `projects`, `init`, `doctor`, `hours`, `fetch`, `digest`, `emails`, `forecast`, `budget`, `monday` |
| `perch/tests/conftest.py` (modify) | `build_home` helper; autouse `PERCH_HOME` guard |
| `perch/tests/test_config.py` (modify) | the new key and flag |
| `perch/tests/test_workspace.py` (new) | discovery, selection, scaffold |
| `perch/tests/test_steps.py` (new) | step values, `monday` order, `run_projects` |
| `perch/tests/test_doctor.py` (new) | one fault → one FIX |
| `perch/tests/test_cli_projects.py` (new) | `-p` selection, `projects`, `init` |
| `perch/tests/test_cli_run.py` (new) | step commands, `monday`, `--all`, `doctor` |
| `Makefile`, `README.md`, `CLAUDE.md`, `.gitignore`, `docs/reference.md`, the spec (modify) | the docs and the trimmed menu |

---

### Task 1: perch.yaml gains `gitlab_project` and an optional dump

**Files:**
- Modify: `perch/core/config.py`
- Test: `perch/tests/test_config.py`

**Interfaces:**
- Produces: `Config.gitlab_project: str | None` (the last field, default `None`); `load_config(path: str | Path, require_dump: bool = True) -> Config`. With `require_dump=False`, a missing `board_dump` file is not an error (the path is still resolved and required as a key).

- [ ] **Step 1: Write the failing tests** (append to `perch/tests/test_config.py`)

```python
def test_gitlab_project_is_read_and_optional(world):
    assert load_config(world).gitlab_project is None
    world.write_text(world.read_text() + "gitlab_project: grp/apollo\n")
    assert load_config(world).gitlab_project == "grp/apollo"


def test_a_missing_dump_is_allowed_before_the_first_fetch(world):
    (world.parent / "dump.json").unlink()
    with pytest.raises(FileNotFoundError, match="stats --dump"):
        load_config(world)
    config = load_config(world, require_dump=False)
    assert config.board_dump == world.parent / "dump.json"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/Documents/tools/perch/bin/python -m pytest perch/tests/test_config.py -v`
Expected: FAIL. The first fails with `ValueError: perch.yaml: unknown keys ['gitlab_project']`, the second with `TypeError: load_config() got an unexpected keyword argument 'require_dump'`.

- [ ] **Step 3: Implement**

In `perch/core/config.py`:

```python
_KEYS = {"budgie_project", "board_dump", "estimates", "gitlab_project", "people"}
```

Add the last field to `Config`:

```python
    people: dict[str, str] = field(default_factory=dict)  # GitLab username -> name
    gitlab_project: str | None = None  # e.g. group/apollo; only `fetch` needs it
```

Change the signature and docstring, and the dump check:

```python
def load_config(path: str | Path, require_dump: bool = True) -> Config:
    """Load and validate a perch.yaml. Paths resolve against its directory.

    ``require_dump=False`` is for the steps that run before the first fetch
    (doctor, fetch itself): the dump's path is still required, its file is not.
    """
```

```python
    dump = located("board_dump")
    if require_dump and not dump.is_file():
```

Before `return Config(`:

```python
    gitlab = data.get("gitlab_project")
```

and add `gitlab_project=str(gitlab) if gitlab else None,` to the `Config(...)` call.

- [ ] **Step 4: Run the whole suite**

Run: `~/Documents/tools/perch/bin/python -m pytest -q`
Expected: all pass (49 before plus 2 new = 51).

- [ ] **Step 5: Commit**

```bash
git add perch/core/config.py perch/tests/test_config.py
git commit -m "feat(config): gitlab_project key; load without a dump before the first fetch (perch-h3l)"
```

---

### Task 2: The workspace (perch-home.yaml, projects, scaffold)

**Files:**
- Create: `perch/core/workspace.py`
- Test: `perch/tests/test_workspace.py`

**Interfaces:**
- Consumes: `perch.core.config.CONFIG_NAME` (`"perch.yaml"`), `load_config(path, require_dump=False)` (Task 1, in a test only).
- Produces:
  - `WorkspaceError(ValueError)`
  - constants `HOME_NAME = "perch-home.yaml"`, `HOME_ENV = "PERCH_HOME"`, `PROJECTS_DIR = "projects"`, `BUDGET_DIR = "budget"`
  - `@dataclass(frozen=True) Home(root: Path, gitboard_dir: Path)`, with:
    - `.projects_dir -> Path`
    - `.projects() -> list[str]`
    - `.config_path(name) -> Path`
    - `.weekly_path(name, week: str) -> Path`
    - `.reports_dir(name) -> Path`
    - `.budget_dir(name) -> Path`
    - `.select(name: str | None) -> str`
    - `.scaffold(name) -> Path`
  - `check_name(name: str) -> str`
  - `load_home(path: Path) -> Home`
  - `find_home(start: Path, env: Mapping[str, str]) -> Home`
  - `create_home(root: Path, gitboard_dir: Path) -> Home`

- [ ] **Step 1: Write the failing tests** (`perch/tests/test_workspace.py`)

```python
import pytest

from perch.core.config import load_config
from perch.core.workspace import (
    WorkspaceError,
    create_home,
    find_home,
    load_home,
)


def make_home(tmp_path, *projects):
    home = create_home(tmp_path / "ws", tmp_path / "gb")
    for name in projects:
        home.scaffold(name)
    return home


def test_found_by_walking_up_from_a_subfolder(tmp_path):
    home = make_home(tmp_path, "apollo")
    deep = home.projects_dir / "apollo" / "weekly"
    deep.mkdir(parents=True)
    assert find_home(deep, {}).root == home.root


def test_perch_home_is_the_fallback(tmp_path):
    home = make_home(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert find_home(elsewhere, {"PERCH_HOME": str(home.root)}).root == home.root


def test_no_workspace_says_what_to_run(tmp_path):
    with pytest.raises(WorkspaceError, match="perch init"):
        find_home(tmp_path, {})


def test_perch_home_pointing_nowhere_says_so(tmp_path):
    with pytest.raises(WorkspaceError, match="PERCH_HOME"):
        find_home(tmp_path, {"PERCH_HOME": str(tmp_path / "nope")})


def test_gitboard_dir_takes_tilde_and_relative_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    marker = tmp_path / "perch-home.yaml"
    marker.write_text("gitboard_dir: ~/gb\n")
    assert load_home(marker).gitboard_dir == (tmp_path / "gb").resolve()
    marker.write_text("gitboard_dir: ../gb\n")
    assert load_home(marker).gitboard_dir == (tmp_path.parent / "gb").resolve()


@pytest.mark.parametrize(
    ("text", "says"),
    [
        ("gitboard_dir: x\ngitlab: y\n", "gitlab"),
        ("{}\n", "`gitboard_dir` is required"),
        ("- a\n", "mapping"),
    ],
)
def test_a_bad_home_file_names_the_problem(tmp_path, text, says):
    (tmp_path / "perch-home.yaml").write_text(text)
    with pytest.raises(WorkspaceError, match=says):
        load_home(tmp_path / "perch-home.yaml")


def test_one_project_needs_no_name(tmp_path):
    assert make_home(tmp_path, "apollo").select(None) == "apollo"


def test_several_projects_need_a_name(tmp_path):
    home = make_home(tmp_path, "gemini", "apollo")
    with pytest.raises(WorkspaceError, match="several projects: apollo, gemini"):
        home.select(None)
    assert home.select("gemini") == "gemini"


def test_an_unknown_name_lists_the_known_ones(tmp_path):
    with pytest.raises(WorkspaceError, match="Known: apollo"):
        make_home(tmp_path, "apollo").select("apolo")


def test_no_projects_says_init(tmp_path):
    with pytest.raises(WorkspaceError, match="perch init"):
        make_home(tmp_path).select(None)


def test_folders_without_perch_yaml_are_not_projects(tmp_path):
    home = make_home(tmp_path, "apollo")
    (home.projects_dir / "notes").mkdir()
    assert home.projects() == ["apollo"]


def test_scaffold_points_at_budget_name_and_never_overwrites(tmp_path):
    home = make_home(tmp_path)
    path = home.scaffold("apollo")
    (home.budget_dir("apollo")).mkdir(parents=True)
    (home.budget_dir("apollo") / "budgie.yaml").write_text("year: 2026\n")
    config = load_config(path, require_dump=False)
    assert config.budgie_project == home.root / "budget" / "apollo"
    assert config.board_dump == home.projects_dir / "apollo" / "dumps" / "board.json"
    assert config.gitlab_project is None and config.people == {}
    with pytest.raises(FileExistsError, match="edit it instead"):
        home.scaffold("apollo")


@pytest.mark.parametrize("bad", ["../x", "a/b", "", ".hidden", "a b"])
def test_project_names_cannot_escape_projects(tmp_path, bad):
    with pytest.raises(WorkspaceError, match="not a project name"):
        make_home(tmp_path).scaffold(bad)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/Documents/tools/perch/bin/python -m pytest perch/tests/test_workspace.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'perch.core.workspace'`.

- [ ] **Step 3: Implement** (`perch/core/workspace.py`)

```python
"""The perch workspace: a perch-home.yaml, and the projects beside it.

    ~/work/pi/
      perch-home.yaml     gitboard_dir: ~/Documents/git/pi_suite/remote-gitboard
      projects/apollo/    perch.yaml, history.jsonl, dumps/, weekly/
      budget/apollo/      the Budgie project (Budgie's own budget/ container)

A project is one funded piece of work: one GitLab project, one Budgie project,
one timesheet charge code. Found by walking up from the working directory,
else $PERCH_HOME -- the same walk-up Budgie and gitboard use.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from perch.core.config import CONFIG_NAME

HOME_NAME = "perch-home.yaml"
HOME_ENV = "PERCH_HOME"
PROJECTS_DIR = "projects"
BUDGET_DIR = "budget"  # Budgie's container: `budgie init NAME` writes budget/NAME
_HOME_KEYS = {"gitboard_dir"}
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")

SCAFFOLD = """\
budgie_project: ../../budget/{name}   # the directory holding budgie.yaml
board_dump: dumps/board.json         # written by `perch fetch`
gitlab_project:                      # the GitLab path, e.g. group/{name}
# estimates: estimates.csv           # optional; key,hours,low,high
people:                              # GitLab username -> name in people.csv
  # asmith: Alice
"""


class WorkspaceError(ValueError):
    """No workspace, no such project, or several projects and none named."""


def check_name(name: str) -> str:
    """A project name is one plain path segment, so it can't leave projects/."""
    if not _NAME.fullmatch(name):
        raise WorkspaceError(
            f"{name!r} is not a project name: letters, digits, - and _ only"
        )
    return name


@dataclass(frozen=True)
class Home:
    """A loaded perch-home.yaml. Both paths are absolute."""

    root: Path
    gitboard_dir: Path

    @property
    def projects_dir(self) -> Path:
        return self.root / PROJECTS_DIR

    def projects(self) -> list[str]:
        """Project names: folders under projects/ that hold a perch.yaml."""
        if not self.projects_dir.is_dir():
            return []
        return sorted(
            p.name for p in self.projects_dir.iterdir() if (p / CONFIG_NAME).is_file()
        )

    def config_path(self, name: str) -> Path:
        return self.projects_dir / name / CONFIG_NAME

    def weekly_path(self, name: str, week: str) -> Path:
        return self.projects_dir / name / "weekly" / f"{week}.md"

    def reports_dir(self, name: str) -> Path:
        return self.gitboard_dir / "reports" / name

    def budget_dir(self, name: str) -> Path:
        return self.root / BUDGET_DIR / name

    def select(self, name: str | None) -> str:
        """The named project, else the only one; several and none named is an error."""
        names = self.projects()
        if name is not None:
            if name not in names:
                known = ", ".join(names) or "none yet"
                raise WorkspaceError(
                    f"no project {name!r} in {self.projects_dir}. Known: {known}"
                )
            return name
        if not names:
            raise WorkspaceError("no projects yet. Run: perch init <name>")
        if len(names) > 1:
            raise WorkspaceError(
                f"several projects: {', '.join(names)}. Pass -p <name>."
            )
        return names[0]

    def scaffold(self, name: str) -> Path:
        """Write projects/NAME/perch.yaml pointing at budget/NAME. Never overwrites."""
        path = self.config_path(check_name(name))
        if path.exists():
            raise FileExistsError(f"{path} exists; edit it instead.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SCAFFOLD.format(name=name))
        return path


def load_home(path: Path) -> Home:
    """Load and validate a perch-home.yaml; every error names the key."""
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise WorkspaceError(f"{path.name} must be a mapping")
    unknown = set(data) - _HOME_KEYS
    if unknown:
        raise WorkspaceError(
            f"{path.name}: unknown keys {sorted(unknown)}; expected {sorted(_HOME_KEYS)}"
        )
    if not data.get("gitboard_dir"):
        raise WorkspaceError(f"{path.name}: `gitboard_dir` is required")
    root = path.resolve().parent
    gitboard = (root / Path(str(data["gitboard_dir"])).expanduser()).resolve()
    return Home(root=root, gitboard_dir=gitboard)


def find_home(start: Path, env: Mapping[str, str]) -> Home:
    """The first perch-home.yaml at or above ``start``, else $PERCH_HOME's."""
    here = start.resolve()
    for directory in (here, *here.parents):
        if (directory / HOME_NAME).is_file():
            return load_home(directory / HOME_NAME)
    if env.get(HOME_ENV):
        path = Path(env[HOME_ENV]).expanduser() / HOME_NAME
        if not path.is_file():
            raise WorkspaceError(f"${HOME_ENV} is {env[HOME_ENV]}, which has no {HOME_NAME}")
        return load_home(path)
    raise WorkspaceError(
        f"no {HOME_NAME} here or above, and ${HOME_ENV} is not set. "
        "Run: perch init <name> --home <dir> --gitboard-dir <remote-gitboard>"
    )


def create_home(root: Path, gitboard_dir: Path) -> Home:
    """Make ``root`` a workspace. An existing perch-home.yaml is left alone."""
    root.mkdir(parents=True, exist_ok=True)
    path = root / HOME_NAME
    if not path.exists():
        path.write_text(f"gitboard_dir: {gitboard_dir}\n")
    for sub in (PROJECTS_DIR, BUDGET_DIR):
        (root / sub).mkdir(exist_ok=True)
    return load_home(path)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `~/Documents/tools/perch/bin/python -m pytest perch/tests/test_workspace.py -v && ~/Documents/tools/perch/bin/ruff check perch`
Expected: all PASS; ruff clean. If ruff flags a long line, wrap it. Don't add `# noqa`.

- [ ] **Step 5: Commit**

```bash
git add perch/core/workspace.py perch/tests/test_workspace.py
git commit -m "feat(workspace): perch-home.yaml, project selection and scaffold (perch-h3l)"
```

---

### Task 3: Steps as data (what each command runs)

**Files:**
- Create: `perch/core/steps.py`
- Modify: `perch/tests/conftest.py` (add `build_home` and an autouse `PERCH_HOME` guard)
- Test: `perch/tests/test_steps.py`

**Interfaces:**
- Consumes: `Home`, `WorkspaceError`, `create_home` (Task 2); `Config`, `load_config` (Task 1).
- Produces:
  - `Step(name: str, argv: tuple[str, ...], cwd: Path, env: Mapping[str, str] = {}, makes: tuple[Path, ...] = ())`, with `.shown() -> str`
  - `StepFailed(Exception)`, with `.step` and `.code`; `str()` is `"<name> exited <code>"`
  - `gitboard(home, name, *args, makes=()) -> Step`
  - `fetch(home, project, config) -> Step`, which raises `WorkspaceError` when `gitlab_project` is unset
  - `board(bin_dir, home, project) -> Step`
  - `weekly(bin_dir, home, project, week) -> Step`
  - `digest(home, project, config) -> Step`
  - `emails(bin_dir, config) -> Step`, `forecast(bin_dir, config) -> Step`, `budget(bin_dir, config) -> Step`
  - `hours(editor: str, config) -> Step`
  - `budgie_init(bin_dir, home, name) -> Step`
  - `monday(bin_dir, home, project, config, week) -> list[Step]`
  - `iso_week(day: date) -> str`
  - `run_projects(names, run_one) -> list[tuple[str, Exception | None]]`
  - conftest: `build_home(tmp_path, *names, gitlab=True) -> Home`, which builds a `build_world` inside each `projects/<name>/`.

- [ ] **Step 1: Add the test helpers to `perch/tests/conftest.py`** (append)

```python
@pytest.fixture(autouse=True)
def _no_perch_home(monkeypatch):
    """A PERCH_HOME in the developer's shell must not find a real workspace."""
    monkeypatch.delenv("PERCH_HOME", raising=False)


def build_home(tmp_path, *names, gitlab=True):
    """A workspace whose projects are each the hand-checkable world above.

    Each project's Budgie project is its own `fy26/` (perch.yaml points there),
    so every number the world's docstring works out holds per project.
    """
    from perch.core.workspace import create_home

    home = create_home(tmp_path / "ws", tmp_path / "gb")
    for name in names:
        folder = home.projects_dir / name
        folder.mkdir(parents=True)
        config = build_world(folder)
        if gitlab:
            config.write_text(config.read_text() + f"gitlab_project: grp/{name}\n")
    return home
```

- [ ] **Step 2: Write the failing tests** (`perch/tests/test_steps.py`)

```python
from datetime import date
from pathlib import Path

import pytest

from perch.core import steps
from perch.core.config import load_config
from perch.core.workspace import WorkspaceError
from perch.tests.conftest import build_home

BIN = Path("/venv/bin")


def apollo(tmp_path, gitlab=True):
    home = build_home(tmp_path, "apollo", gitlab=gitlab)
    return home, load_config(home.config_path("apollo"), require_dump=False)


def test_monday_is_five_steps_in_order_each_in_its_tool(tmp_path):
    home, config = apollo(tmp_path)
    run = steps.monday(BIN, home, "apollo", config, "2026-W40")
    assert [s.name for s in run] == ["fetch", "board", "weekly", "digest", "emails"]
    fetch, board, weekly, digest, emails = run
    gb = home.gitboard_dir
    assert fetch.argv == (
        str(gb / ".venv/bin/python"), "-m", "gitboard.cli",
        "stats", "grp/apollo", "--dump", str(config.board_dump),
    )  # fmt: skip
    assert fetch.cwd == gb and fetch.env == {"PYTHONPATH": str(gb / "src")}
    assert fetch.makes == (config.board_dump.parent,)
    assert board.argv == ("/venv/bin/perch", "board", "--config", str(home.config_path("apollo")))
    weekly_md = home.projects_dir / "apollo" / "weekly" / "2026-W40.md"
    assert weekly.argv[-2:] == ("--out", str(weekly_md))
    assert weekly.makes == (weekly_md.parent,)
    assert digest.argv[-4:] == ("--from", str(config.board_dump), "--out", str(gb / "reports" / "apollo"))
    assert emails.argv == ("/venv/bin/budgie", "emails", "--out-dir", "emails", "--no-preview")
    assert emails.cwd == config.budgie_project


def test_fetch_without_gitlab_project_says_what_to_add(tmp_path):
    home, config = apollo(tmp_path, gitlab=False)
    with pytest.raises(WorkspaceError, match="gitlab_project"):
        steps.monday(BIN, home, "apollo", config, "2026-W40")


def test_budgie_steps_run_inside_the_budgie_project(tmp_path):
    _, config = apollo(tmp_path)
    assert steps.forecast(BIN, config).argv == ("/venv/bin/budgie", "forecast")
    assert steps.budget(BIN, config).argv == ("/venv/bin/budgie", "status")
    assert steps.budget(BIN, config).cwd == config.budgie_project


def test_hours_opens_weekly_csv_with_an_editor_that_has_flags(tmp_path):
    _, config = apollo(tmp_path)
    step = steps.hours("code -w", config)
    assert step.argv == ("code", "-w", str(config.budgie_project / "weekly.csv"))


def test_budgie_init_runs_from_the_workspace_root(tmp_path):
    home, _ = apollo(tmp_path)
    step = steps.budgie_init(BIN, home, "gemini")
    assert step.argv == ("/venv/bin/budgie", "init", "gemini") and step.cwd == home.root


def test_iso_week_matches_date_G_W_V():
    assert steps.iso_week(date(2026, 1, 1)) == "2026-W01"
    assert steps.iso_week(date(2027, 1, 1)) == "2026-W53"


def test_shown_is_a_command_you_could_paste(tmp_path):
    step = steps.Step("x", ("echo", "a b"), Path("/tmp/w s"))
    assert step.shown() == "(cd '/tmp/w s' && echo 'a b')"


def test_run_projects_carries_on_past_a_failure():
    ran = []

    def run_one(name):
        ran.append(name)
        if name == "b":
            raise steps.StepFailed(steps.Step("fetch", ("x",), Path(".")), 2)

    results = steps.run_projects(["a", "b", "c"], run_one)
    assert ran == ["a", "b", "c"]
    assert [(n, e and str(e)) for n, e in results] == [
        ("a", None),
        ("b", "fetch exited 2"),
        ("c", None),
    ]
```

- [ ] **Step 3: Run them to verify they fail**

Run: `~/Documents/tools/perch/bin/python -m pytest perch/tests/test_steps.py -v`
Expected: FAIL with `ImportError: cannot import name 'steps' from 'perch.core'`.

- [ ] **Step 4: Implement** (`perch/core/steps.py`)

```python
"""What each perch command runs, as values. Nothing here executes anything.

The CLI turns a Step into a subprocess. Keeping the commands as data is what
lets the tests check `monday` -- order, working directory, paths -- without
GitLab, Budgie or a terminal. perch runs the other tools as commands, never as
imports, so it still never calls GitLab and never redoes budget math.
"""

from __future__ import annotations

import shlex
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from perch.core.config import Config
from perch.core.workspace import Home, WorkspaceError


@dataclass(frozen=True)
class Step:
    name: str
    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str] = field(default_factory=dict)  # added to os.environ
    makes: tuple[Path, ...] = ()  # directories to create before running

    def shown(self) -> str:
        return f"(cd {shlex.quote(str(self.cwd))} && {shlex.join(self.argv)})"


class StepFailed(Exception):
    def __init__(self, step: Step, code: int):
        super().__init__(f"{step.name} exited {code}")
        self.step = step
        self.code = code


def iso_week(day: date) -> str:
    """`2026-W40`, the same as `date +%G-W%V`."""
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def gitboard(home: Home, name: str, *args: str, makes: tuple[Path, ...] = ()) -> Step:
    """gitboard runs from its checkout: it finds .env and gitboard.toml from there."""
    return Step(
        name,
        (str(home.gitboard_dir / ".venv/bin/python"), "-m", "gitboard.cli", *args),
        home.gitboard_dir,
        {"PYTHONPATH": str(home.gitboard_dir / "src")},
        makes,
    )


def fetch(home: Home, project: str, config: Config) -> Step:
    if not config.gitlab_project:
        raise WorkspaceError(
            f"{project}: perch.yaml has no gitlab_project; "
            f"add e.g. `gitlab_project: group/{project}`"
        )
    return gitboard(
        home,
        "fetch",
        "stats",
        config.gitlab_project,
        "--dump",
        str(config.board_dump),
        makes=(config.board_dump.parent,),
    )


def board(bin_dir: Path, home: Home, project: str) -> Step:
    config = str(home.config_path(project))
    return Step("board", (str(bin_dir / "perch"), "board", "--config", config), home.root)


def weekly(bin_dir: Path, home: Home, project: str, week: str) -> Step:
    out = home.weekly_path(project, week)
    argv = (str(bin_dir / "perch"), "weekly", "--config", str(home.config_path(project)))
    return Step("weekly", (*argv, "--out", str(out)), home.root, makes=(out.parent,))


def digest(home: Home, project: str, config: Config) -> Step:
    out = home.reports_dir(project)
    return gitboard(
        home, "digest", "digest", "--from", str(config.board_dump), "--out", str(out),
        makes=(out,),
    )  # fmt: skip


def _budgie(bin_dir: Path, config: Config, name: str, *args: str) -> Step:
    """Budgie runs inside its project, so it reads that project's files."""
    return Step(name, (str(bin_dir / "budgie"), *args), config.budgie_project)


def emails(bin_dir: Path, config: Config) -> Step:
    return _budgie(bin_dir, config, "emails", "emails", "--out-dir", "emails", "--no-preview")


def forecast(bin_dir: Path, config: Config) -> Step:
    return _budgie(bin_dir, config, "forecast", "forecast")


def budget(bin_dir: Path, config: Config) -> Step:
    return _budgie(bin_dir, config, "budget", "status")


def hours(editor: str, config: Config) -> Step:
    """$EDITOR may carry flags (`code -w`), so it is split like a shell would."""
    path = config.budgie_project / "weekly.csv"
    return Step("hours", (*shlex.split(editor), str(path)), config.budgie_project)


def budgie_init(bin_dir: Path, home: Home, name: str) -> Step:
    """`budgie init NAME` from the workspace root writes budget/NAME."""
    return Step("budgie init", (str(bin_dir / "budgie"), "init", name), home.root)


def monday(bin_dir: Path, home: Home, project: str, config: Config, week: str) -> list[Step]:
    """Steps 1-5, in order. `hours` (step 0) is by hand and comes first."""
    return [
        fetch(home, project, config),
        board(bin_dir, home, project),
        weekly(bin_dir, home, project, week),
        digest(home, project, config),
        emails(bin_dir, config),
    ]


def run_projects(
    names: Iterable[str], run_one: Callable[[str], None]
) -> list[tuple[str, Exception | None]]:
    """Run each project in turn; a failure is recorded and the next one still runs."""
    results: list[tuple[str, Exception | None]] = []
    for name in names:
        try:
            run_one(name)
        except (StepFailed, OSError, TypeError, ValueError) as exc:
            results.append((name, exc))
        else:
            results.append((name, None))
    return results
```

- [ ] **Step 5: Run them to verify they pass, then the whole suite**

Run: `~/Documents/tools/perch/bin/python -m pytest -q && ~/Documents/tools/perch/bin/ruff check . && ~/Documents/tools/perch/bin/ruff format --check perch`
Expected: all pass, and ruff is clean. If `ruff format --check` complains, run `ruff format perch` and re-run the tests.

- [ ] **Step 6: Commit**

```bash
git add perch/core/steps.py perch/tests/test_steps.py perch/tests/conftest.py
git commit -m "feat(steps): every Budgie/gitboard/perch call as a Step value; monday and --all (perch-h3l)"
```

---

### Task 4: doctor's checks

**Files:**
- Create: `perch/core/doctor.py`
- Test: `perch/tests/test_doctor.py`

**Interfaces:**
- Consumes: `load_config(path, require_dump=False)` (Task 1); `Home`, `HOME_NAME` (Task 2); `steps.gitboard` (Task 3); `perch.core.money.load_money(project) -> Money` with `.hourly_cost: dict[str, float]` (existing, keyed by the names in people.csv as Budgie reads them).
- Produces:
  - `Check(ok: bool, what: str, fix: str = "")`
  - `age(path: Path) -> str`, giving `"YYYY-MM-DD HH:MM"` or `"never"`
  - `tool_checks(bin_dir, home, runs: Callable[[Sequence[str], Path, Mapping[str, str]], bool]) -> list[Check]`
  - `project_checks(home, name) -> list[Check]`
  - `freshness(home, name) -> list[tuple[str, str]]`

- [ ] **Step 1: Write the failing tests** (`perch/tests/test_doctor.py`)

```python
import pytest

from perch.core.doctor import age, freshness, project_checks, tool_checks
from perch.tests.conftest import build_home


def test_a_healthy_project_needs_no_fix(tmp_path):
    home = build_home(tmp_path, "apollo")
    assert all(c.ok for c in project_checks(home, "apollo"))


def test_no_dump_yet_is_not_a_fault(tmp_path):
    home = build_home(tmp_path, "apollo")
    (home.projects_dir / "apollo" / "dump.json").unlink()
    assert all(c.ok for c in project_checks(home, "apollo"))


@pytest.mark.parametrize(
    ("old", "new", "says"),
    [
        ("gitlab_project: grp/apollo\n", "", "gitlab_project not set"),
        ("bjones: Bob", "bjones: Bobby", "Bobby"),
        ("budgie_project: fy26", "budgie_project: nope", "budgie.yaml"),
        ("people:\n  asmith: Alice\n  bjones: Bob\n", "", "people: is empty"),
        ("board_dump", "boardump", "unknown keys"),
    ],
)
def test_one_fault_gives_exactly_one_fix(tmp_path, old, new, says):
    home = build_home(tmp_path, "apollo")
    path = home.config_path("apollo")
    assert old in path.read_text()
    path.write_text(path.read_text().replace(old, new))
    failed = [c for c in project_checks(home, "apollo") if not c.ok]
    assert len(failed) == 1, failed
    assert says in failed[0].what and failed[0].fix


def test_freshness_says_never_for_what_has_not_been_written(tmp_path):
    home = build_home(tmp_path, "apollo")
    seen = dict(freshness(home, "apollo"))
    assert seen["history.jsonl"] == "never"
    assert seen["board dump"] != "never" and seen["weekly.csv"] != "never"


def test_age_of_a_missing_file_is_never(tmp_path):
    assert age(tmp_path / "nope") == "never"


def test_tool_checks_name_the_tool_that_does_not_run(tmp_path):
    home = build_home(tmp_path)
    home.gitboard_dir.mkdir()
    checks = tool_checks(tmp_path, home, lambda argv, cwd, env: "budgie" not in argv[0])
    assert [c.what for c in checks if not c.ok] == ["budgie does not run"]


def test_a_missing_gitboard_dir_points_at_perch_home(tmp_path):
    home = build_home(tmp_path)
    failed = [c for c in tool_checks(tmp_path, home, lambda *a: True) if not c.ok]
    assert len(failed) == 1 and "perch-home.yaml" in failed[0].fix
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/Documents/tools/perch/bin/python -m pytest perch/tests/test_doctor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'perch.core.doctor'`.

- [ ] **Step 3: Implement** (`perch/core/doctor.py`)

```python
"""perch doctor: one ok-or-FIX line for each thing that can be wrong before Monday."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from perch.core.config import load_config
from perch.core.workspace import HOME_NAME, Home

# (argv, cwd, extra env) -> did it exit 0
Runs = Callable[[Sequence[str], Path, Mapping[str, str]], bool]
_INSTALL = "make install (in the perch checkout)"
_CONFIG_ERRORS = (OSError, TypeError, ValueError, KeyError)


@dataclass(frozen=True)
class Check:
    ok: bool
    what: str
    fix: str = ""  # the command or edit that fixes it; only shown when not ok


def age(path: Path) -> str:
    if not path.exists():
        return "never"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def tool_checks(bin_dir: Path, home: Home, runs: Runs) -> list[Check]:
    from perch.core.steps import gitboard

    checks = []
    for tool in ("perch", "budgie"):
        ok = runs([str(bin_dir / tool), "--help"], home.root, {})
        checks.append(Check(ok, f"{tool} runs" if ok else f"{tool} does not run", _INSTALL))
    if not home.gitboard_dir.is_dir():
        checks.append(
            Check(
                False,
                f"gitboard_dir {home.gitboard_dir} does not exist",
                f"fix gitboard_dir in {home.root / HOME_NAME}",
            )
        )
    else:
        step = gitboard(home, "gitboard", "--help")
        ok = runs(step.argv, step.cwd, step.env)
        checks.append(Check(ok, "gitboard runs" if ok else "gitboard does not run", _INSTALL))
    return checks


def project_checks(home: Home, name: str) -> list[Check]:
    """perch.yaml loads, gitlab_project is set, and people: names exist in Budgie."""
    from perch.core.money import load_money

    path = home.config_path(name)
    try:
        config = load_config(path, require_dump=False)
    except _CONFIG_ERRORS as exc:
        return [Check(False, f"{name}: {exc}", f"edit {path}")]
    checks = [Check(True, f"{name}: perch.yaml, Budgie project {config.budgie_project}")]
    checks.append(
        Check(
            bool(config.gitlab_project),
            f"{name}: gitlab_project {config.gitlab_project or 'not set'}",
            f"add gitlab_project: to {path}",
        )
    )
    if not config.people:
        checks.append(
            Check(False, f"{name}: people: is empty", f"map GitLab usernames to names in {path}")
        )
        return checks
    try:
        known = set(load_money(config.budgie_project).hourly_cost)
    except _CONFIG_ERRORS as exc:
        checks.append(
            Check(
                False,
                f"{name}: Budgie cannot read {config.budgie_project}: {exc}",
                f"cd {config.budgie_project} && budgie status",
            )
        )
        return checks
    for user, person in sorted(config.people.items()):
        if person not in known:
            checks.append(
                Check(
                    False,
                    f"{name}: people: maps {user} to {person}, who is not in people.csv",
                    f"fix the name in {path}",
                )
            )
    return checks


def freshness(home: Home, name: str) -> list[tuple[str, str]]:
    """When the dump, weekly.csv and history were last written ("never" if not)."""
    try:
        config = load_config(home.config_path(name), require_dump=False)
    except _CONFIG_ERRORS:
        return []  # project_checks already reported it
    return [
        ("board dump", age(config.board_dump)),
        ("weekly.csv", age(config.budgie_project / "weekly.csv")),
        ("history.jsonl", age(config.history)),
    ]
```

- [ ] **Step 4: Run the whole suite**

Run: `~/Documents/tools/perch/bin/python -m pytest -q && ~/Documents/tools/perch/bin/ruff check . && ~/Documents/tools/perch/bin/ruff format --check perch`
Expected: all pass. The world's `people.csv` has Alice and Bob, so the healthy case has no FIX. Its fy26 has `weekly.csv`, so that check isn't "never".

- [ ] **Step 5: Commit**

```bash
git add perch/core/doctor.py perch/tests/test_doctor.py
git commit -m "feat(doctor): per-project checks, tool checks and freshness as values (perch-h3l)"
```

---

### Task 5: CLI: picking a project, `projects`, `init`

**Files:**
- Modify: `perch/cli.py`
- Test: `perch/tests/test_cli_projects.py`

**Interfaces:**
- Consumes: Tasks 1–4 (`find_home`, `Home.select/config_path/projects/budget_dir/scaffold`, `create_home`, `load_home`, `check_name`, `HOME_NAME`, `WorkspaceError`, `steps.budgie_init`, `StepFailed`, `doctor.age`).
- Produces (module-level in `perch/cli.py`; Task 6 and the tests rely on them):
  - `_bin_dir() -> Path`, the directory of `sys.executable`
  - `_find_home() -> Home`, which can raise `WorkspaceError`
  - `_home() -> Home`, which raises `click.ClickException` instead
  - `_config_path(config_path: str | None, project: str | None) -> Path`
  - `_run(step: Step) -> None`, which creates `step.makes`, prints the step, runs it, and raises `StepFailed` on a non-zero exit. Tests replace it with `monkeypatch.setattr("perch.cli._run", fake)`.
  - `_project_option` (`-p/--project`)

- [ ] **Step 1: Write the failing tests** (`perch/tests/test_cli_projects.py`)

```python
import pytest
from click.testing import CliRunner

from perch.cli import cli
from perch.core.config import load_config
from perch.tests.conftest import build_home


def run(*args):
    return CliRunner().invoke(cli, list(args))


def test_board_uses_the_only_project(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.projects_dir / "apollo")  # a subfolder finds the workspace
    result = run("board", "--no-history")
    assert result.exit_code == 0, result.output
    assert "Alice" in result.output


def test_several_projects_need_p(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.root)
    result = run("weekly")
    assert result.exit_code != 0
    assert "several projects: apollo, gemini. Pass -p <name>." in result.output
    assert run("weekly", "-p", "gemini").exit_code == 0


def test_config_wins_over_p(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.root)
    config = str(home.config_path("gemini"))
    result = run("board", "--no-history", "-p", "nope", "--config", config)
    assert result.exit_code == 0, result.output


def test_outside_a_workspace_a_perch_yaml_here_still_works(world, monkeypatch):
    monkeypatch.chdir(world.parent)
    assert run("board", "--no-history").exit_code == 0


def test_outside_a_workspace_with_no_perch_yaml_says_how_to_start(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("board")
    assert result.exit_code != 0 and "perch init" in result.output


def test_projects_lists_each_with_its_gitlab_project(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    gemini = home.config_path("gemini")
    gemini.write_text(gemini.read_text().replace("gitlab_project: grp/gemini\n", ""))
    monkeypatch.chdir(home.root)
    result = run("projects")
    assert result.exit_code == 0, result.output
    assert "apollo" in result.output and "grp/apollo" in result.output
    assert "gemini" in result.output and "not set" in result.output


def fake_budgie_init(monkeypatch, root):
    ran = []

    def fake(step):
        ran.append(step.argv[1:])
        name = step.argv[-1]
        (root / "budget" / name).mkdir(parents=True, exist_ok=True)
        (root / "budget" / name / "budgie.yaml").write_text("year: 2026\n")

    monkeypatch.setattr("perch.cli._run", fake)
    return ran


def test_init_makes_the_workspace_runs_budgie_init_and_writes_perch_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ran = fake_budgie_init(monkeypatch, tmp_path / "ws")
    result = run("init", "apollo", "--home", "ws", "--gitboard-dir", str(tmp_path / "gb"))
    assert result.exit_code == 0, result.output
    assert ran == [("init", "apollo")]
    assert (tmp_path / "ws" / "perch-home.yaml").is_file()
    config = load_config(tmp_path / "ws/projects/apollo/perch.yaml", require_dump=False)
    assert config.budgie_project == (tmp_path / "ws/budget/apollo").resolve()
    assert "gitlab_project" in result.output and "perch doctor -p apollo" in result.output


def test_init_skips_budgie_init_when_the_budgie_project_exists(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    (home.budget_dir("gemini")).mkdir(parents=True)
    (home.budget_dir("gemini") / "budgie.yaml").write_text("year: 2026\n")
    monkeypatch.chdir(home.root)
    monkeypatch.setattr("perch.cli._run", lambda step: pytest.fail(f"ran {step.name}"))
    assert run("init", "gemini").exit_code == 0
    assert home.config_path("gemini").is_file()


def test_init_refuses_to_overwrite_and_runs_nothing(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    monkeypatch.setattr("perch.cli._run", lambda step: pytest.fail(f"ran {step.name}"))
    result = run("init", "apollo")
    assert result.exit_code != 0 and "exists" in result.output


def test_init_home_needs_gitboard_dir_the_first_time(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("init", "apollo", "--home", "ws")
    assert result.exit_code != 0 and "--gitboard-dir" in result.output


def test_init_rejects_a_name_that_escapes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("init", "../x", "--home", "ws", "--gitboard-dir", "gb")
    assert result.exit_code != 0 and "not a project name" in result.output
    assert not (tmp_path / "x").exists()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/Documents/tools/perch/bin/python -m pytest perch/tests/test_cli_projects.py -v`
Expected: FAIL. `board` errors with `perch.yaml: no such file` (there's no workspace lookup yet), and `projects`/`init` fail with `No such command`.

- [ ] **Step 3: Implement** (edits to `perch/cli.py`)

Replace the imports at the top with:

```python
import os
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table
```

Change `_load` so it takes the already-resolved path. Its body is otherwise unchanged:

```python
def _load(config_path: Path):
```

Replace `_config_option` with the two options and add the helpers (put them right after `_load`):

```python
_config_option = click.option(
    "--config",
    "config_path",
    default=None,
    help="A perch.yaml to use instead of a workspace project.",
)
_project_option = click.option(
    "-p",
    "--project",
    default=None,
    help="Which project under projects/ (needed when there are several).",
)


def _bin_dir() -> Path:
    """perch's venv: `perch` and `budgie` (installed there) sit beside python."""
    return Path(sys.executable).parent


def _find_home():
    from perch.core.workspace import find_home

    return find_home(Path.cwd(), os.environ)


def _home():
    from perch.core.workspace import WorkspaceError

    try:
        return _find_home()
    except WorkspaceError as exc:
        raise click.ClickException(str(exc)) from exc


def _config_path(config_path: str | None, project: str | None) -> Path:
    """--config wins; then -p in the workspace; outside one, ./perch.yaml."""
    from perch.core.config import CONFIG_NAME
    from perch.core.workspace import WorkspaceError

    if config_path:
        return Path(config_path)
    try:
        home = _find_home()
    except WorkspaceError:
        if project is None and Path(CONFIG_NAME).is_file():
            return Path(CONFIG_NAME)
        raise
    return home.config_path(home.select(project))


def _run(step) -> None:
    """Run one step in this terminal; the tool's own output shows as it happens."""
    from perch.core.steps import StepFailed

    for directory in step.makes:
        directory.mkdir(parents=True, exist_ok=True)
    console.print(f"[bold]{escape(step.name)}[/bold] [dim]{escape(step.shown())}[/dim]")
    code = subprocess.run(step.argv, cwd=step.cwd, env={**os.environ, **step.env}).returncode
    if code:
        raise StepFailed(step, code)
```

In `board`, `accuracy` and `weekly`:
- add `@_project_option` under `@_config_option`;
- add `project` to the signature right after `config_path`;
- replace `_load(config_path)` with `_load(_config_path(config_path, project))`.

The call is already inside each command's `try: ... except (OSError, TypeError, ValueError)`, and `WorkspaceError` is a `ValueError`, so a selection error becomes a clean `ClickException`. For `board`:

```python
@cli.command()
@_config_option
@_project_option
@click.option("--seed", default=None, type=int, help="Seed the simulation.")
@click.option("--iterations", default=None, type=int, help="Simulation draws.")
@click.option("--no-history", is_flag=True, help="Don't append to history.jsonl.")
def board(config_path, project, seed, iterations, no_history):
    ...
    try:
        config, the_board, money, estimates, rates = _load(
            _config_path(config_path, project)
        )
```

Do the same for `accuracy(config_path, project)` and `weekly(config_path, project, person, out_path)`.

Add the two new commands at the end of the file:

```python
@cli.command()
def projects():
    """The projects in this workspace and how fresh each one's data is."""
    from perch.core.config import load_config
    from perch.core.doctor import age

    home = _home()
    names = home.projects()
    if not names:
        console.print("No projects yet. Run: perch init <name>")
        return
    console.print(f"Workspace {home.root}", markup=False, highlight=False)
    for name in names:
        try:
            c = load_config(home.config_path(name), require_dump=False)
        except (OSError, TypeError, ValueError) as exc:
            console.print(f"  {name}  [red]{escape(str(exc))}[/red]", highlight=False)
            continue
        gitlab = c.gitlab_project or "[red]not set[/red]"
        budget = os.path.relpath(c.budgie_project, home.root)
        console.print(f"  [bold]{name}[/bold]  GitLab {gitlab}  Budgie {budget}", highlight=False)
        console.print(
            f"      dump {age(c.board_dump)} · weekly.csv "
            f"{age(c.budgie_project / 'weekly.csv')} · history {age(c.history)}",
            highlight=False,
        )


@cli.command()
@click.argument("name")
@click.option(
    "--home",
    "home_dir",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help="Make this directory the workspace (writes perch-home.yaml).",
)
@click.option(
    "--gitboard-dir",
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help="The remote-gitboard checkout; needed with --home the first time.",
)
def init(name, home_dir, gitboard_dir):
    """Scaffold projects/NAME/perch.yaml and the Budgie project budget/NAME."""
    from perch.core.steps import StepFailed, budgie_init
    from perch.core.workspace import HOME_NAME, check_name, create_home, load_home

    try:
        check_name(name)
        if home_dir is None:
            home = _find_home()
        elif (home_dir / HOME_NAME).is_file():
            home = load_home(home_dir / HOME_NAME)
        elif gitboard_dir is None:
            raise click.ClickException(
                f"{home_dir} has no {HOME_NAME} yet; pass --gitboard-dir "
                "<remote-gitboard checkout> too"
            )
        else:
            home = create_home(home_dir, gitboard_dir.expanduser().resolve())
        if home.config_path(name).exists():
            raise click.ClickException(f"{home.config_path(name)} exists; edit it instead.")
        if not (home.budget_dir(name) / "budgie.yaml").is_file():
            _run(budgie_init(_bin_dir(), home, name))
        path = home.scaffold(name)
    except StepFailed as exc:
        raise click.ClickException(f"{name}: {exc}") from exc
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    budget = os.path.relpath(home.budget_dir(name), home.root)
    console.print(f"Wrote {path}. Fill in:", markup=False, highlight=False)
    console.print(f"  gitlab_project:  the GitLab path, e.g. group/{name}", markup=False)
    console.print(f"  people:          GitLab username -> name in {budget}/people.csv", markup=False)
    console.print(f"  {budget}/  the Budgie inputs: budgie guide", markup=False)
    console.print(f"Then: perch doctor -p {name}", markup=False)
```

- [ ] **Step 4: Run the whole suite**

Run: `~/Documents/tools/perch/bin/python -m pytest -q && ~/Documents/tools/perch/bin/ruff check . && ~/Documents/tools/perch/bin/ruff format --check perch`
Expected: all pass, including the existing `test_cli.py` (they pass `--config`). If `ruff format --check` complains, run `ruff format perch` and re-run the tests.

- [ ] **Step 5: Commit**

```bash
git add perch/cli.py perch/tests/test_cli_projects.py
git commit -m "feat(cli): -p project selection, perch projects, perch init (perch-h3l)"
```

---

### Task 6: CLI: the step commands, `monday [--all]`, `doctor`

**Files:**
- Modify: `perch/cli.py`
- Test: `perch/tests/test_cli_run.py`

**Interfaces:**
- Consumes:
  - Task 5: `_home`, `_find_home`, `_bin_dir`, `_run`, `_project_option`
  - Task 3: `steps.*`
  - Task 4: `doctor.tool_checks/project_checks/freshness/Check`
- Produces:
  - commands `hours`, `fetch`, `digest`, `emails`, `forecast`, `budget`, `monday`, `doctor`
  - module-level `_runs(argv, cwd, env) -> bool` and `_show_gitboard_config(home) -> None`, which the tests monkeypatch

- [ ] **Step 1: Write the failing tests** (`perch/tests/test_cli_run.py`)

```python
import pytest
from click.testing import CliRunner

from perch.cli import cli
from perch.core.steps import StepFailed
from perch.tests.conftest import build_home


def run(*args):
    return CliRunner().invoke(cli, list(args))


def recorder(monkeypatch, fail=lambda step: False):
    ran = []

    def fake(step):
        ran.append(step)
        if fail(step):
            raise StepFailed(step, 2)

    monkeypatch.setattr("perch.cli._run", fake)
    return ran


@pytest.mark.parametrize(
    ("command", "step"),
    [
        ("fetch", "fetch"),
        ("digest", "digest"),
        ("emails", "emails"),
        ("forecast", "forecast"),
        ("budget", "budget"),
        ("hours", "hours"),
    ],
)
def test_each_step_command_runs_its_one_step(tmp_path, monkeypatch, command, step):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    monkeypatch.setenv("EDITOR", "true")
    ran = recorder(monkeypatch)
    result = run(command)
    assert result.exit_code == 0, result.output
    assert [s.name for s in ran] == [step]


def test_a_failing_step_is_a_clean_error_naming_the_project(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    recorder(monkeypatch, fail=lambda step: True)
    result = run("fetch")
    assert result.exit_code != 0 and "apollo: fetch exited 2" in result.output
    assert "Traceback" not in result.output


def test_monday_runs_the_five_steps_and_says_where_to_look(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    ran = recorder(monkeypatch)
    result = run("monday")
    assert result.exit_code == 0, result.output
    assert [s.name for s in ran] == ["fetch", "board", "weekly", "digest", "emails"]
    assert "Review, then send yourself" in result.output


def test_monday_all_carries_on_past_a_failure_and_exits_1(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.root)
    ran = recorder(
        monkeypatch, fail=lambda s: s.name == "fetch" and "grp/apollo" in s.argv
    )
    result = run("monday", "--all")
    assert result.exit_code == 1
    assert [s.name for s in ran] == ["fetch", "fetch", "board", "weekly", "digest", "emails"]
    assert "apollo FAILED: fetch exited 2" in result.output
    assert "gemini ok" in result.output


def test_monday_without_gitlab_project_runs_nothing(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", gitlab=False)
    monkeypatch.chdir(home.root)
    ran = recorder(monkeypatch)
    result = run("monday")
    assert result.exit_code != 0 and "gitlab_project" in result.output
    assert ran == []


def test_p_and_all_together_is_a_usage_error(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo")
    monkeypatch.chdir(home.root)
    assert run("monday", "-p", "apollo", "--all").exit_code == 2


def test_monday_all_with_no_projects_says_init(tmp_path, monkeypatch):
    home = build_home(tmp_path)
    monkeypatch.chdir(home.root)
    result = run("monday", "--all")
    assert result.exit_code != 0 and "perch init" in result.output


def quiet_tools(monkeypatch, home):
    home.gitboard_dir.mkdir()
    monkeypatch.setattr("perch.cli._runs", lambda argv, cwd, env: True)
    monkeypatch.setattr("perch.cli._show_gitboard_config", lambda home: None)


def test_doctor_all_well_exits_0_with_no_fix(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", "gemini")
    monkeypatch.chdir(home.root)
    quiet_tools(monkeypatch, home)
    result = run("doctor")
    assert result.exit_code == 0, result.output
    assert "FIX" not in result.output
    assert "apollo: board dump" in result.output and "gemini: board dump" in result.output


def test_doctor_names_the_fix_and_exits_1(tmp_path, monkeypatch):
    home = build_home(tmp_path, "apollo", gitlab=False)
    monkeypatch.chdir(home.root)
    quiet_tools(monkeypatch, home)
    result = run("doctor", "-p", "apollo")
    assert result.exit_code == 1
    assert "FIX" in result.output and "gitlab_project" in result.output
```

- [ ] **Step 2: Run them to verify they fail**

Run: `~/Documents/tools/perch/bin/python -m pytest perch/tests/test_cli_run.py -v`
Expected: FAIL with `No such command 'fetch'` (and the same for the others).

- [ ] **Step 3: Implement** (append to `perch/cli.py`; add `from datetime import date` to the top-level imports)

```python
def _project(project):
    """(home, name, config) for -p, before the first fetch as much as after."""
    from perch.core.config import load_config

    home = _find_home()
    name = home.select(project)
    return home, name, load_config(home.config_path(name), require_dump=False)


def _one(project, build) -> None:
    """Resolve the project, build its one step, run it; failures are clean errors."""
    from perch.core.steps import StepFailed

    name = project or "project"
    try:
        home, name, config = _project(project)
        _run(build(home, name, config))
    except StepFailed as exc:
        raise click.ClickException(f"{name}: {exc}") from exc
    except (OSError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command()
@_project_option
def hours(project):
    """0. Open the project's weekly.csv to paste this week's timesheet totals."""
    from perch.core import steps

    console.print("One row per person: name,week,hours_to_date (cumulative).")
    editor = os.environ.get("EDITOR", "vi")
    _one(project, lambda home, name, config: steps.hours(editor, config))


@cli.command()
@_project_option
def fetch(project):
    """1. One GitLab read: gitboard stats into the project's board dump."""
    from perch.core import steps

    _one(project, steps.fetch)


@cli.command()
@_project_option
def digest(project):
    """4. gitboard's team and per-person digest, from the same dump."""
    from perch.core import steps

    _one(project, steps.digest)


@cli.command()
@_project_option
def emails(project):
    """5. Budgie's per-person hours-left drafts (.eml). Nothing is sent."""
    from perch.core import steps

    _one(project, lambda home, name, config: steps.emails(_bin_dir(), config))


@cli.command()
@_project_option
def forecast(project):
    """Budgie's cost forecast for the project, with P10/P50/P90."""
    from perch.core import steps

    _one(project, lambda home, name, config: steps.forecast(_bin_dir(), config))


@cli.command()
@_project_option
def budget(project):
    """Which input files Budgie reads for the project, and what each feeds."""
    from perch.core import steps

    _one(project, lambda home, name, config: steps.budget(_bin_dir(), config))


@cli.command()
@_project_option
@click.option(
    "--all",
    "all_projects",
    is_flag=True,
    help="Every project, in name order; a failure moves on to the next.",
)
def monday(project, all_projects):
    """Steps 1-5: fetch, board, weekly, digest, emails. Run `perch hours` first.

    Nothing is ever sent: you review the drafts and send them yourself.
    """
    from perch.core import steps
    from perch.core.config import load_config

    if project and all_projects:
        raise click.UsageError("give -p or --all, not both")
    week = steps.iso_week(date.today())

    def run_one(home, name):
        config = load_config(home.config_path(name), require_dump=False)
        for step in steps.monday(_bin_dir(), home, name, config, week):
            _run(step)
        console.print(f"\n[bold]{name}[/bold] done. Review, then send yourself:")
        for place in (
            home.weekly_path(name, week),
            home.reports_dir(name),
            config.budgie_project / "emails",
        ):
            console.print(f"  {place}", markup=False, highlight=False)

    home = _home()
    if not all_projects:
        name = project or "project"
        try:
            name = home.select(project)
            run_one(home, name)
        except steps.StepFailed as exc:
            raise click.ClickException(f"{name}: {exc}") from exc
        except (OSError, TypeError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        return
    names = home.projects()
    if not names:
        raise click.ClickException("no projects yet. Run: perch init <name>")
    results = steps.run_projects(names, lambda name: run_one(home, name))
    console.print("\n[bold]monday --all[/bold]")
    for name, error in results:
        if error is None:
            console.print(f"  {name} ok", highlight=False)
        else:
            console.print(f"  [red]{name} FAILED[/red]: {escape(str(error))}", highlight=False)
    if any(error for _, error in results):
        raise click.exceptions.Exit(1)


def _runs(argv, cwd, env) -> bool:
    """Does this command exit 0? Quiet: doctor only wants the answer."""
    try:
        done = subprocess.run(argv, cwd=cwd, env={**os.environ, **env}, capture_output=True)
    except OSError:
        return False
    return done.returncode == 0


def _show_gitboard_config(home) -> None:
    from perch.core.steps import gitboard

    step = gitboard(home, "gitboard config", "config")
    try:
        subprocess.run(step.argv, cwd=step.cwd, env={**os.environ, **step.env})
    except OSError as exc:
        console.print(f"  [red]gitboard config did not run[/red]: {escape(str(exc))}")


@cli.command()
@_project_option
def doctor(project):
    """Check the tools, each project's config, and how fresh the data is."""
    from perch.core.doctor import Check, freshness, project_checks, tool_checks

    home = _home()
    try:
        names = [home.select(project)] if project else home.projects()
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    failed = 0

    def show(checks):
        nonlocal failed
        for c in checks:
            if c.ok:
                console.print(f"  [green]ok[/green]    {escape(c.what)}", highlight=False)
            else:
                failed += 1
                console.print(
                    f"  [red]FIX[/red]   {escape(c.what)}  ->  {escape(c.fix)}",
                    highlight=False,
                )

    console.print(f"Workspace {home.root}", markup=False, highlight=False)
    console.print("[bold]Tools[/bold]")
    show(tool_checks(_bin_dir(), home, _runs))
    console.print("[bold]Projects[/bold]")
    if not names:
        show([Check(False, "no projects yet", "perch init <name>")])
    for name in names:
        show(project_checks(home, name))
    console.print("[bold]Data (last written)[/bold]")
    for name in names:
        for label, when in freshness(home, name):
            console.print(f"  {name}: {label:<14} {when}", markup=False, highlight=False)
    if home.gitboard_dir.is_dir():
        console.print("[bold]GitLab tokens (gitboard config)[/bold]")
        _show_gitboard_config(home)
    if failed:
        raise click.exceptions.Exit(1)
```

- [ ] **Step 4: Run the whole suite**

Run: `~/Documents/tools/perch/bin/python -m pytest -q && ~/Documents/tools/perch/bin/ruff check . && ~/Documents/tools/perch/bin/ruff format --check perch`
Expected: all pass. If `ruff format --check` complains, run `ruff format perch` and re-run the tests.

- [ ] **Step 5: Try it by hand in a throwaway workspace** (needs the real Budgie; no GitLab)

```bash
cd /private/tmp && rm -rf perch-try && mkdir perch-try && cd perch-try
~/Documents/tools/perch/bin/perch init apollo --home . --gitboard-dir /Users/ryanadams/Documents/git/pi_suite/remote-gitboard
~/Documents/tools/perch/bin/perch projects
~/Documents/tools/perch/bin/perch doctor; echo "exit=$?"
~/Documents/tools/perch/bin/perch forecast
cd / && rm -rf /private/tmp/perch-try
```

Expected:
- `init` prints the Budgie project it made plus the "Fill in" lines.
- `projects` shows `apollo` with `GitLab not set`.
- `doctor` shows FIX for `gitlab_project` and for `people: is empty`, and exits 1.
- `forecast` prints Budgie's forecast from `budget/apollo`.

- [ ] **Step 6: Commit**

```bash
git add perch/cli.py perch/tests/test_cli_run.py
git commit -m "feat(cli): hours/fetch/digest/emails/forecast/budget, monday [--all], doctor (perch-h3l)"
```

---

### Task 7: Makefile down to development targets; docs; land

**Files:**
- Modify: `Makefile`, `README.md`, `CLAUDE.md`, `.gitignore`, `docs/reference.md`, `docs/superpowers/specs/2026-10-01-multi-project-design.md`

**Interfaces:**
- Consumes: the finished CLI from Task 6.

- [ ] **Step 1: Replace `Makefile` with exactly this**

```make
# perch's own development tasks. Running the apps is `perch` itself:
#   perch projects | init | doctor | hours | monday [--all] | forecast | ...
# (`perch --help`). This file only builds, tests and links.
#
# The other apps are looked for beside this checkout. Anywhere else:
#   make BUDGIE_DIR=/path/to/budgie GB_DIR=/path/to/remote-gitboard <target>
PERCH_DIR  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
BUDGIE_DIR ?= $(abspath $(PERCH_DIR)/../budgie)
GB_DIR     ?= $(abspath $(PERCH_DIR)/../remote-gitboard)
# A relative override would break after the first cd.
override BUDGIE_DIR := $(abspath $(BUDGIE_DIR))
override GB_DIR     := $(abspath $(GB_DIR))

# The venvs live OUTSIDE the repos (see Budgie's CLAUDE.md for the macOS
# hidden-.pth trap that makes an in-tree venv a bad idea).
PERCH_VENV  ?= $(HOME)/Documents/tools/perch
BUDGIE_VENV ?= $(HOME)/Documents/tools/budgie
BIN         := $(PERCH_VENV)/bin
PERCH       ?= $(BIN)/perch

.DEFAULT_GOAL := help
.PHONY: help install link venv lint format test test-all docs clean

help: ## This menu. Running the apps: perch --help
	@awk 'BEGIN {FS = ":.*## "} \
	  /^##@/ {printf "\n\033[1m%s\033[0m\n", substr($$0, 5)} \
	  /^[a-z-]+:.*## / {printf "  \033[36mmake %-9s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo
	@echo "  Running things: perch projects, perch doctor, perch monday --all"

##@ Setup (once, or after moving the folders)

install: ## (Re)install all three tools. Fixes "No module named perch/budgie"
	$(MAKE) -C $(BUDGIE_DIR) install VENV=$(BUDGIE_VENV)
	test -x $(BIN)/pip || python3 -m venv $(PERCH_VENV)
	$(BIN)/pip install -q -e '$(PERCH_DIR)[dev]'
	$(BIN)/pip install -q -e $(BUDGIE_DIR)
	$(MAKE) -C $(GB_DIR) install
	@echo "installed. 'make link' puts perch and gitboard on your PATH."

link: ## Put `perch` and `gitboard` in ~/.local/bin
	@mkdir -p $(HOME)/.local/bin
	ln -sf $(PERCH) $(HOME)/.local/bin/perch
	$(MAKE) -C $(GB_DIR) link

##@ Development (perch itself, except test-all)

# perch pulls Budgie from GitHub; the editable checkout goes on after so it wins.
venv: ## Create perch's venv: perch with dev + docs, then Budgie from its checkout
	python3 -m venv $(PERCH_VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e '$(PERCH_DIR)[dev,docs]'
	$(BIN)/pip install -e $(BUDGIE_DIR)

lint: ## Lint with ruff
	cd $(PERCH_DIR) && $(BIN)/ruff check .

format: ## Format with ruff
	cd $(PERCH_DIR) && $(BIN)/ruff format .

test: ## Run perch's test suite
	cd $(PERCH_DIR) && $(BIN)/pytest

test-all: ## Run all three test suites: Budgie, perch, gitboard
	$(MAKE) -C $(BUDGIE_DIR) test VENV=$(BUDGIE_VENV)
	cd $(PERCH_DIR) && $(BIN)/pytest -q
	$(MAKE) -C $(GB_DIR) test

docs: ## Build the HTML docs into docs/_build
	cd $(PERCH_DIR) && PYTHONPATH=. $(BIN)/sphinx-build -W -b html docs docs/_build/html

clean: ## Remove caches and build artifacts
	cd $(PERCH_DIR) && rm -rf build *.egg-info .pytest_cache .ruff_cache docs/_build
	cd $(PERCH_DIR) && find . -type d -name __pycache__ -prune -exec rm -rf {} +
```

Before replacing it, run `diff <(sed -n '/^install:/,/^init:/p' Makefile) -` against the `install`/`link` recipes above. If the current file's recipes differ (another session may have changed them), keep the current recipe text.

- [ ] **Step 2: `.gitignore`**: under the "Per-person numbers" block, add:

```
projects/
perch-home.yaml
.claude/worktrees/
```

- [ ] **Step 3: `docs/reference.md`**: add after the `perch.core.config` automodule:

```
.. automodule:: perch.core.workspace
   :members:

.. automodule:: perch.core.steps
   :members:

.. automodule:: perch.core.doctor
   :members:
```

- [ ] **Step 4: `README.md`**: replace the whole `## One menu for every pi app` section (from that heading up to `## Use`) with:

````markdown
## One entry point for every pi app

`perch` is the single place you run things from. It drives gitboard and Budgie
as separate commands; each app still lives in its own repo. Run it from
anywhere inside a workspace, or set `PERCH_HOME`.

```bash
perch init apollo --home ~/work/pi --gitboard-dir ~/Documents/git/pi_suite/remote-gitboard
perch projects                 # every project, its GitLab project, how fresh its data is
perch doctor                   # tools, config, people names, freshness; FIX lines say what to run
perch hours -p apollo          # paste this week's apollo timesheet totals
perch monday --all             # fetch, board, weekly, digest, emails for every project
```

`-p NAME` picks a project; with only one, it can be left off. Nothing is ever sent.

### The workspace

A project is one funded piece of work: one GitLab project, one Budgie project,
one timesheet charge code. Rates are per project (the same person can cost a
different amount on different work), so each Budgie project has its own
`people.csv`.

```
~/work/pi/
  perch-home.yaml      gitboard_dir: /path/to/remote-gitboard
  projects/apollo/     perch.yaml (gitlab_project: group/apollo), history.jsonl, dumps/, weekly/
  budget/apollo/       the Budgie project: people.csv, plan.csv, weekly.csv, budget.csv
```

Board edits (pull, plan, land, tui) are `gitboard` commands, run from the
gitboard checkout with the project's `gitlab_project`.

### Moving a single-team setup in

1. Create `perch-home.yaml` (one line: `gitboard_dir: /path/to/remote-gitboard`).
2. Make `projects/team/`, then move `perch.yaml`, `history.jsonl` and `dumps/`
   into it.
3. In `perch.yaml`, fix `budgie_project` and `board_dump` (they're relative to
   the file) and add `gitlab_project`.

`perch doctor` names any path that is still wrong.
````

In `## Use`, replace `perch board                                            # reads ./perch.yaml` with `perch board [-p NAME]                                 # or --config FILE`. In the `perch.yaml` example block, add a line `gitlab_project: group/project            # what perch fetch reads`. In `## Development`, add the line `Multi-project design: docs/superpowers/specs/2026-10-01-multi-project-design.md.` after the existing `Design:` line.

- [ ] **Step 5: `CLAUDE.md`**: replace the second paragraph of `## Goal` (the one that starts `perch is also the one entry point for every pi app`) with:

```markdown
perch is also the one entry point for every pi app, as a CLI: `perch monday`,
`perch doctor`, `perch hours` and the rest shell out to the tool that owns each
step (`perch/core/steps.py` holds each call as a `Step` value; the CLI runs
them). perch never imports another app's code to do that. A workspace
(`perch-home.yaml`) holds `projects/<name>/` and `budget/<name>/`; a project
is one GitLab project + one Budgie project + one charge code, picked with
`-p`. The Makefile is development only.
```

In `## Commands`, replace the `make` line `make          # the menu for every app: Monday run, board changes, budget` with `perch --help  # running the apps: projects, init, doctor, hours, monday [--all]`. In `## Architecture`, add after the `core/config.py` bullet:

```markdown
- `core/workspace.py` -- perch-home.yaml (walk up, else $PERCH_HOME), the
  projects under projects/, `-p` selection, and scaffolding a project.
- `core/steps.py` -- every Budgie/gitboard/perch call as a `Step(argv, cwd,
  env)`; nothing here executes. `run_projects` is `monday --all`'s
  carry-on-past-a-failure loop.
- `core/doctor.py` -- `Check(ok, what, fix)` values for `perch doctor`.
```

- [ ] **Step 6: The spec, to match what was built**

In `docs/superpowers/specs/2026-10-01-multi-project-design.md`:
- Change the status line to `Status: approved and built.`
- In "How the other tools are run", replace the "perch's own steps" bullet with: `- **perch's own steps** (\`board\`, \`weekly\`) run as \`perch\` commands from the same venv, like the other steps, so \`monday\` is one list of steps and the tests check the whole sequence.`
- In "monday", change `gemini FAILED at fetch: <first error line>` to `gemini FAILED: fetch exited <code>` (the tool's own error output is shown live above it).
- In "init", replace the `--home DIR` sentence with: `\`--home DIR\` writes \`perch-home.yaml\` in DIR when there is none yet (it needs \`--gitboard-dir\` then; perch never prompts, so init stays scriptable), and creates \`projects/\` and \`budget/\` there.`

- [ ] **Step 7: Full gate**

Run:
```bash
cd /Users/ryanadams/Documents/git/pi_suite/perch
make lint && ~/Documents/tools/perch/bin/ruff format --check perch && make test-all && make docs
```
Expected:
- ruff is clean;
- `test-all` prints `passed` for Budgie, perch and gitboard, with no failures;
- the docs build with `-W` and no warnings.

If `make docs` fails because a `README.md` heading cut point is referenced elsewhere, run `grep -rn "One menu" docs` and update the reference.

- [ ] **Step 8: Commit and close the bead**

```bash
git add Makefile README.md CLAUDE.md .gitignore docs/reference.md docs/superpowers/specs/2026-10-01-multi-project-design.md
git commit -m "docs+make: perch CLI is the entry point; Makefile is development only (perch-h3l)"
bd close perch-h3l --reason "perch workspace + -p + projects/init/doctor/hours/fetch/digest/emails/forecast/budget/monday [--all]; Makefile dev-only; make test-all green"
```

Then hand off. The training deck rework (perch-15g) and the TUI (perch-s7p) remain as beads.
