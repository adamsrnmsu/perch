# Home install, per-project .env, members, title limits: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. For /ultracode, the **Execution map** below is the work-list: one agent per task, waves in order, each task's own worktree recipe.

**Goal:** All three pi apps run from one `perch/.venv` with nothing built, each perch project carries its own `.env`, gitboard finds GitLab usernames per board, and titles are kept within GitLab's limit.

**Architecture:** perch's `make install` pip-installs only the dependencies of perch, Budgie and gitboard (read from their `pyproject.toml`) into `perch/.venv` and writes `perch`/`budgie`/`gitboard` wrapper scripts into `.venv/bin` that run each app from source on `PYTHONPATH`. perch runs gitboard from `projects/NAME`, so gitboard's existing walk-up finds `projects/NAME/.env`. gitboard gains `members`, which fills the board YAML's `people:`; perch reads that map back, keeping only names Budgie knows.

**Tech Stack:** Python 3.11+ (stdlib `tomllib`), click (perch), typer + python-gitlab (gitboard), make, POSIX sh, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-10-13-home-install-env-members-design.md`

## Global Constraints

- Python floor for the suite: 3.11 (`tomllib`); `make install` refuses older with one line naming `PYTHON=`.
- No editable installs and no build of perch, Budgie or gitboard anywhere on the install path; source runs via `PYTHONPATH`.
- `PYTHONPATH` value, in this order: `<perch>:<perch>/apps/budgie:<perch>/apps/remote-gitboard/src` (absolute).
- Venv: `<perch>/.venv` (already gitignored as `.venv/`).
- Placeholder token text is exactly `<key-from-gitlab>`.
- Title limits: refuse over **255** characters (GitLab's limit), warn over **100**.
- perch never calls GitLab, never rewrites `perch.yaml` or a board YAML, never prints a token value.
- `perch.yaml` `people:` always wins over anything from the board YAML.
- Board YAML path: `projects/NAME/board/NAME.yaml`. Per-project env: `projects/NAME/.env`; shared fallback `<perch>/.env`.
- `setuptools>=61` in perch's `[build-system] requires`; `setuptools>=64` in Budgie's (its standalone install is editable: PEP 660).
- Code comments, docs, commit messages: plain English prose (no caveman style).
- Commits go on the task's bead branch `bead/<bead-id>` in the repo that owns the files; merge to that repo's `main` locally with `--no-ff` after review. **Never push.**
- Every commit message ends with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_016Js49meT3psoy4w3dc8PdQ
  ```
- Each task's implementer claims its bead first (`bd update <id> --claim`, run from `/Users/ryanadams/Documents/git/perch`) and closes it at the end (`bd close <id> --reason "..."`). On a Dolt lock error retry once, then report the id back.

## Review Focus

1. **Re-running `make install` over an old install** (an existing `.venv` holding editable perch/Budgie, `~/.local/bin/perch` a symlink into `~/Documents/tools/perch`, `~/.local/bin/gitboard` a regular wrapper file): it must replace all three links and leave no stale package that shadows source. Pinned in Task 4 (`pip uninstall` step, `ln -sf`, and a `make -n` check).
2. **`make clean` inside `apps/remote-gitboard` when it sits in perch**: today it `rm -rf $(VENV)`; with `VENV` pointing at perch's venv it would delete the whole suite's environment. Pinned in Task 3 (clean never removes a venv it does not own; `make -n clean` check).
3. **A `.env` value written the dotenv way** (`export KEY=value`, quoted values, a trailing ` # comment`, the untouched `<key-from-gitlab>` placeholder): doctor must read it the way gitboard's python-dotenv would and never print it. Pinned in Task 5 (`test_read_token_*`).
4. **A title containing rich markup characters** (`[x]`, `[/]`) in the long-title warning: printing it raw through rich would crash or eat text. Pinned in Task 1 (`escape`, test with a bracketed title).
5. **Two GitLab members with the same display name**, and a member already mapped under another display name: the merge must not overwrite or drop either. Pinned in Task 2 (`test_merge_*`).

---

## Execution map (for /ultracode and subagent-driven runs)

The perch checkout is `/Users/ryanadams/Documents/git/perch` (below: `PERCH`). `apps/budgie` and `apps/remote-gitboard` are **separate git repos** inside it and are gitignored by perch, so a perch worktree does not contain them.

| Task | Bead | Repo | Wave | Depends on | Files owned |
|---|---|---|---|---|---|
| 1 | perch-w41.1 | gitboard | 1 | none | `.env.example`, `README.md`, `docs/install.md`, `src/gitboard/apply.py`, `src/gitboard/cli.py` (plan/_write_spec only), `.claude/commands/board.md`, `tests/test_apply.py`, `tests/test_cli.py` |
| 3 | perch-w41.3 | gitboard | 1 | none | `Makefile`, `CLAUDE.md` (Commands + Toolchain) |
| 4 | perch-w41.4 | perch | 1 | none | `scripts/install_env.py`, `perch/tests/test_install_env.py`, `Makefile`, `pyproject.toml`, `perch/core/workspace.py` (`venv_bin` only), `perch/core/steps.py` (`gitboard()` argv only), `perch/tui.py` (`suite_map` gitboard argv only), `perch/core/doctor.py` (`old_venv_checks`), `perch/cli.py` (doctor wiring only), `.github/workflows/docs.yml`, `README.md`, `docs/install.md`, `CLAUDE.md` (Commands), tests `test_steps.py`, `test_tui.py`, `test_workspace.py`, `test_doctor.py`, CLI doctor tests; also commits the spec and this plan |
| 2 | perch-w41.2 | gitboard | 2 | 1 | `src/gitboard/members.py`, `src/gitboard/cli.py` (members, `_pull_spec`, call sites), `src/gitboard/tui.py` (`_pull_spec` call), `tests/test_members.py`, `tests/test_cli.py`, `docs/board-yaml.md`, `src/gitboard/CLAUDE.md` |
| 5 | perch-w41.5 | perch | 2 | 4 | `perch/core/steps.py`, `perch/tui.py` (`suite_map` cwd), `perch/core/workspace.py` (scaffold), `perch/core/doctor.py` (`env_checks`), `perch/cli.py` (init, doctor), tests `test_steps.py`, `test_tui.py`, `test_workspace.py`, `test_doctor.py`, `test_cli_projects.py` |
| 7 | perch-w41.7 | Budgie | 2 | 4 | `Makefile`, `pyproject.toml`, `CLAUDE.md`, `README.md` |
| 6 | perch-w41.6 | perch | 3 | 2, 5 | `perch/core/config.py`, `perch/core/steps.py` (`GB_SUBS`, `gb`), `perch/core/workspace.py` (`check_name`), `perch/core/doctor.py` (members line), `perch/cli.py` (init warning, doctor), `perch/commands/walk.md`, `perch/commands/listen.md`, `CLAUDE.md`, tests `test_config.py`, `test_steps.py`, `test_workspace.py`, `test_doctor.py`, `test_contract.py` |
| 8 | perch-w41.8 | all | 4 | all | none (verification only) |

Within a wave, tasks touch disjoint files, so they can run in parallel. A later wave starts only after the earlier wave's branches are merged into each repo's `main`.

**Worktree recipes** (do NOT use the Agent tool's `isolation: 'worktree'` for gitboard or Budgie tasks: it makes a perch worktree, which has no `apps/`):

- perch task:
  ```bash
  git -C PERCH worktree add PERCH/.claude/worktrees/<bead> -b bead/<bead>
  ln -s PERCH/apps PERCH/.claude/worktrees/<bead>/apps   # apps/ is gitignored, so the link is never committed
  ```
- gitboard task:
  ```bash
  git -C PERCH/apps/remote-gitboard worktree add PERCH/.claude/worktrees/gb-<bead> -b bead/<bead>
  ```
- Budgie task:
  ```bash
  git -C PERCH/apps/budgie worktree add PERCH/.claude/worktrees/bg-<bead> -b bead/<bead>
  ```

**Test commands** (they work before Task 4's new install exists, and inside worktrees):

- perch (from the perch worktree root `WT`): `PYTHONPATH=$WT:PERCH/apps/budgie ~/Documents/tools/perch/bin/pytest -q` and `~/Documents/tools/perch/bin/ruff check .`
- gitboard (from the gitboard worktree root): `PYTHONPATH=src PERCH/apps/remote-gitboard/.venv/bin/pytest -q` and `PERCH/apps/remote-gitboard/.venv/bin/ruff check .`
- Budgie (from the Budgie worktree root `WT`): `PYTHONPATH=$WT ~/Documents/tools/perch/bin/pytest -q` and `~/Documents/tools/perch/bin/ruff check .`

**Ultracode shape.** One workflow per wave: `pipeline(waveTasks, implement, review)` where `implement` is one agent given this plan's path, the spec's path and its task number (it follows the task's steps, including its own worktree recipe, and returns the branch, the test output and the bead id), and `review` is one or more fresh reviewers on that branch's diff against the task text and the Global Constraints (refute-by-default; a finding goes back to an implement agent on the same branch). The main loop merges each passing branch itself, one at a time (merges into the same repo's `main` must not race), then starts the next wave. Task 8 is the main loop's own verification, not a fan-out.

**Merge** (after the task's review passes), in the owning repo:
```bash
git -C <repo> merge --no-ff bead/<bead> -m "Merge bead/<bead>: <title> (<bead>)"
git -C <repo> worktree remove <worktree path>
```

---

### Task 1: gitboard placeholders and title limits

Bead `perch-w41.1`, repo `apps/remote-gitboard`, wave 1.

**Files:**
- Modify: `.env.example`, `README.md:94-95`, `docs/install.md:58-59,78-79`
- Modify: `src/gitboard/apply.py` (`load()` around lines 85-140; new constants and `long_titles`)
- Modify: `src/gitboard/cli.py` (`plan` around line 436, `_write_spec` at line 523; new `_warn_long_titles`)
- Modify: `.claude/commands/board.md`
- Test: `tests/test_apply.py`, `tests/test_cli.py`

**Interfaces:**
- Produces: `apply.TITLE_MAX = 255`, `apply.TITLE_SHORT = 100`, `apply.long_titles(spec: dict) -> list[str]`; `load()` raises `SpecError` on a title over 255.

- [ ] **Step 1: Claim and branch**

```bash
cd /Users/ryanadams/Documents/git/perch && bd update perch-w41.1 --claim
git -C apps/remote-gitboard worktree add /Users/ryanadams/Documents/git/perch/.claude/worktrees/gb-perch-w41.1 -b bead/perch-w41.1
cd /Users/ryanadams/Documents/git/perch/.claude/worktrees/gb-perch-w41.1
```

- [ ] **Step 2: Write the failing tests** (append to `tests/test_apply.py`; add `import yaml` / `import pytest` at the top if missing)

```python
def _spec_file(tmp_path, **extra):
    spec = {"project": "g/p", "board": "B", "issues": [], **extra}
    path = tmp_path / "b.yaml"
    path.write_text(yaml.safe_dump(spec))
    return str(path)


def test_load_refuses_an_issue_title_gitlab_would_refuse(tmp_path):
    path = _spec_file(tmp_path, issues=[{"title": "x" * 256}])
    with pytest.raises(apply_mod.SpecError, match="256 characters.*255"):
        apply_mod.load(path)


def test_load_refuses_a_milestone_title_gitlab_would_refuse(tmp_path):
    path = _spec_file(tmp_path, milestones=[{"title": "m" * 256}])
    with pytest.raises(apply_mod.SpecError, match="milestone title"):
        apply_mod.load(path)


def test_load_takes_255_and_long_titles_lists_what_is_over_100(tmp_path):
    path = _spec_file(
        tmp_path,
        milestones=[{"title": "m" * 101}],
        issues=[{"title": "x" * 255}, {"title": "short"}, {"title": "y" * 100}],
    )
    spec = apply_mod.load(path)
    assert apply_mod.long_titles(spec) == ["m" * 101, "x" * 255]
```

Append to `tests/test_cli.py`:

```python
def test_plan_warns_about_long_titles_and_escapes_markup(tmp_path):
    title = "[x] " + "t" * 120
    spec = {**SPEC, "issues": [{"title": title, "iid": 1, "labels": ["Doing"]}]}
    path = tmp_path / "long.yaml"
    path.write_text(yaml.safe_dump(spec))
    r = runner.invoke(app, ["plan", str(path), "--against", str(path)])
    assert r.exit_code == 0, r.output
    assert "long title (124 characters; keep under 100)" in r.output
    assert "[x] tttt" in r.output
```

(`yaml` may need importing in `tests/test_cli.py`.)

- [ ] **Step 3: Run them to see them fail**

Run: `PYTHONPATH=src /Users/ryanadams/Documents/git/perch/apps/remote-gitboard/.venv/bin/pytest -q tests/test_apply.py tests/test_cli.py -k "title"`
Expected: FAIL (`long_titles` not defined; no SpecError raised; no warning line).

- [ ] **Step 4: Implement in `src/gitboard/apply.py`**

Near the other module constants:

```python
TITLE_MAX = 255  # GitLab refuses a longer issue or milestone title
TITLE_SHORT = 100  # past this a title stops reading at a glance


def _check_title(path, what, title):
    if len(title) > TITLE_MAX:
        raise SpecError(
            f"{path}: {what} title is {len(title)} characters; GitLab's limit is "
            f"{TITLE_MAX}: {title[:40]!r}... Shorten it and put the detail in "
            "the description."
        )


def long_titles(spec):
    """Milestone then issue titles over TITLE_SHORT: legal, but slow to read."""
    titles = [m["title"] for m in spec.get("milestones") or []]
    titles += [i["title"] for i in spec["issues"]]
    return [t for t in titles if len(t) > TITLE_SHORT]
```

In `load()`, in the milestones loop right after `if not title: raise ...`, add `_check_title(path, "milestone", title)`; in the issues loop right after its `if not title: raise ...`, add `_check_title(path, "issue", title)`.

- [ ] **Step 5: Implement in `src/gitboard/cli.py`**

Add (import `from rich.markup import escape` at the top if cli.py does not already):

```python
def _warn_long_titles(parsed):
    """One muted line per title over TITLE_SHORT; never stops a plan or push."""
    for title in apply_mod.long_titles(parsed):
        err().print(
            f"[muted]long title ({len(title)} characters; keep under "
            f"{apply_mod.TITLE_SHORT}): {escape(title[:60])}[/]"
        )
```

Call it in `plan`'s `go()` immediately after `parsed = apply_mod.load(spec_path)`, and as the first line of `_write_spec(parsed, ...)` (that covers `push` and `sync`, which both call `_write_spec`; confirm with `grep -n "_write_spec(" src/gitboard/cli.py`).

- [ ] **Step 6: Placeholders**

`.env.example`: replace the two token lines and add the local-dev pointer above them:

```
# The local test GitLab: scripts/seed.py prints the token it mints (TOKEN in
# that file); paste it into both lines below.
GITLAB_READ_TOKEN=<key-from-gitlab>
GITLAB_WRITE_TOKEN=<key-from-gitlab>
```

`README.md` lines 94-95 and `docs/install.md` lines 58-59 and 78-79: replace `glpat-…` / `glpat-...` with `<key-from-gitlab>`, keeping any trailing comment. Leave `scripts/seed.py` and the README/development.md sentences about seed's fixed token alone. Check: `grep -rn "glpat" --exclude-dir=_build --exclude-dir=.git . | grep -v "scripts/seed.py\|seedseed"` prints nothing.

- [ ] **Step 7: `/board` guidance**

In `.claude/commands/board.md`, in the rules list where retitling is discussed (around line 84), add one line:

```
- Keep issue and milestone titles under 100 characters (GitLab refuses over 255); put the detail in the description.
```

- [ ] **Step 8: Run the full suite and lint**

Run: `PYTHONPATH=src /Users/ryanadams/Documents/git/perch/apps/remote-gitboard/.venv/bin/pytest -q && /Users/ryanadams/Documents/git/perch/apps/remote-gitboard/.venv/bin/ruff check .`
Expected: all pass, no lint errors.

- [ ] **Step 9: Commit, close**

```bash
git add -A && git commit -m "feat: title limits (255 refused, over 100 warned) and <key-from-gitlab> placeholders (perch-w41.1)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Js49meT3psoy4w3dc8PdQ"
cd /Users/ryanadams/Documents/git/perch && bd close perch-w41.1 --reason "Titles over 255 refused in load(), over 100 warned in plan/push/sync; placeholders swapped"
```

---

### Task 3: gitboard Makefile installs into perch home when inside perch

Bead `perch-w41.3`, repo `apps/remote-gitboard`, wave 1.

**Files:**
- Modify: `Makefile` (top variables, `$(VENV)/bin/pytest` rule, `activate`, `link`, `clean`)
- Modify: `CLAUDE.md` (Commands and Toolchain paragraphs)

**Interfaces:**
- Consumes: perch's `make install` and `make link` (Task 4) when inside perch. Until Task 4 merges, the delegated target exists under the old behaviour, which is fine: only `make -n` is checked here.

- [ ] **Step 1: Claim and branch**

```bash
cd /Users/ryanadams/Documents/git/perch && bd update perch-w41.3 --claim
git -C apps/remote-gitboard worktree add /Users/ryanadams/Documents/git/perch/.claude/worktrees/gb-perch-w41.3 -b bead/perch-w41.3
cd /Users/ryanadams/Documents/git/perch/.claude/worktrees/gb-perch-w41.3
```

- [ ] **Step 2: Replace the top variables and the venv rule**

Replace `VENV = .venv` and the `$(VENV)/bin/pytest: pyproject.toml` rule with:

```make
# Inside a perch checkout (perch/apps/remote-gitboard) the venv is perch's own
# .venv and perch's `make install` fills it; standalone this repo keeps .venv.
# The rule is perch's: two levels up holds a pyproject.toml named perch and apps/.
PERCH_HOME := $(shell d=$$(cd $(CURDIR)/../.. && pwd); \
  grep -qs '^name = "perch"' "$$d/pyproject.toml" && test -d "$$d/apps" && echo "$$d")

ifdef PERCH_HOME
VENV       = $(PERCH_HOME)/.venv
$(VENV)/bin/pytest:
	$(MAKE) -C $(PERCH_HOME) install
else
VENV       = $(CURDIR)/.venv
$(VENV)/bin/pytest: pyproject.toml
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q --upgrade pip
	$(VENV)/bin/pip install -q ".[dev,docs]"
	@echo "installed into $(VENV)"
endif
```

`VENV` is now absolute in both branches, so in `activate` and `link` replace every `$(CURDIR)/$(VENV)` with `$(VENV)`.

- [ ] **Step 3: `link` and `clean` must not touch what perch owns**

`link` inside perch delegates; standalone unchanged. Wrap the existing recipe:

```make
link: install  ## put a `gitboard` command in ~/.local/bin (points back here)
ifdef PERCH_HOME
	$(MAKE) -C $(PERCH_HOME) link
else
	(existing recipe lines, with $(CURDIR)/$(VENV) replaced by $(VENV))
endif
```

`clean`: only the standalone venv is ours to delete:

```make
clean:  ## remove venv (standalone only), caches, and bytecode
ifndef PERCH_HOME
	rm -rf $(VENV)
endif
	rm -rf .pytest_cache .ruff_cache docs/_build
	find . -name __pycache__ -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
```

- [ ] **Step 4: Check by dry run, inside perch and standalone**

```bash
make -n clean | grep -c "rm -rf /Users/ryanadams/Documents/git/perch/.venv"   # expect 0
make -n install | head -3                                                    # expect: make -C /Users/ryanadams/Documents/git/perch install
```

The worktree lives at `PERCH/.claude/worktrees/gb-perch-w41.3`, whose `../..` is `PERCH/.claude`, not perch home, so the dry run there exercises the **standalone** branch: expect `make -n clean` to contain `rm -rf .../gb-perch-w41.3/.venv`. To check the perch branch, run the same two commands with `make -n -f $(pwd)/Makefile -C /Users/ryanadams/Documents/git/perch/apps/remote-gitboard clean` and `... install`. Record both outputs in the commit message body.

- [ ] **Step 5: CLAUDE.md**

In `## Commands`, replace "This repo's `make install` only builds its own `.venv` for development." with "Inside a perch checkout this repo's `make install` runs perch's (one `perch/.venv` for all three apps, nothing built); standalone it builds its own `.venv`." In `## Toolchain`, after "Every make target therefore runs `PYTHONPATH=src .venv/bin/python -m gitboard.cli`", add: "Inside perch, `VENV` is perch's `.venv`, and `make clean` never deletes it."

- [ ] **Step 6: Tests still pass, commit, close**

```bash
PYTHONPATH=src /Users/ryanadams/Documents/git/perch/apps/remote-gitboard/.venv/bin/pytest -q
git add -A && git commit -m "build: use perch's venv when inside a perch checkout (perch-w41.3)" -m "<paste the two dry-run results>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Js49meT3psoy4w3dc8PdQ"
cd /Users/ryanadams/Documents/git/perch && bd close perch-w41.3 --reason "Makefile detects perch home; delegates install/link; clean never removes perch's venv"
```

---

### Task 4: perch installs one .venv, builds nothing, writes wrapper commands

Bead `perch-w41.4`, repo perch, wave 1.

**Files:**
- Create: `scripts/install_env.py`, `perch/tests/test_install_env.py`
- Modify: `Makefile`, `pyproject.toml:28`, `.github/workflows/docs.yml:30-31`
- Modify: `perch/core/workspace.py` (`Home.venv_bin`), `perch/core/steps.py:47-55` (`gitboard`), `perch/tui.py:255-283` (`suite_map` gitboard entry), `perch/core/doctor.py` (`tool_checks`, new `old_venv_checks`), `perch/cli.py:892-930` (doctor)
- Modify tests: `perch/tests/test_steps.py` (lines ~24-31, ~230-232), `perch/tests/test_tui.py` (~406-420), `perch/tests/test_doctor.py`
- Modify docs: `README.md`, `docs/install.md`, `CLAUDE.md` (Commands block)
- Also commit the spec and this plan.

**Interfaces:**
- Produces: `scripts/install_env.py` functions `requirements(perch: Path) -> list[str]`, `wrappers(perch: Path, bin_dir: Path) -> list[Path]`, `pythonpath(perch: Path) -> str`; CLI `python scripts/install_env.py requirements PERCH` / `python scripts/install_env.py wrappers PERCH BIN`.
- Produces: `Home.venv_bin -> Path` (= `root / ".venv" / "bin"`); `steps.gitboard(home, name, *args, makes=())` now returns argv `(str(home.venv_bin / "gitboard"), *args)`, `env == {}`, cwd unchanged in this task (`home.gitboard_dir`; Task 5 moves it).
- Produces: `doctor.old_venv_checks(user_home: Path) -> list[Check]`.

- [ ] **Step 1: Claim and branch**

```bash
cd /Users/ryanadams/Documents/git/perch && bd update perch-w41.4 --claim
git worktree add .claude/worktrees/perch-w41.4 -b bead/perch-w41.4
ln -s /Users/ryanadams/Documents/git/perch/apps .claude/worktrees/perch-w41.4/apps
cp docs/superpowers/specs/2026-10-13-home-install-env-members-design.md .claude/worktrees/perch-w41.4/docs/superpowers/specs/
cp docs/superpowers/plans/2026-10-13-home-install-env-members.md .claude/worktrees/perch-w41.4/docs/superpowers/plans/
cd .claude/worktrees/perch-w41.4 && export WT=$PWD
```

(The spec and plan are uncommitted in the main checkout; this task commits them. After merging, delete the main checkout's untracked copies only if `git status` shows them identical: `git diff --no-index` prints nothing.)

- [ ] **Step 2: Write the failing test for `scripts/install_env.py`** (`perch/tests/test_install_env.py`)

```python
"""scripts/install_env.py: what make install pip-installs and the wrappers it writes."""

import importlib.util
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "install_env.py"


def _venv():
    spec = importlib.util.spec_from_file_location("install_env", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _app(root, rel, text):
    (root / rel).mkdir(parents=True, exist_ok=True)
    (root / rel / "pyproject.toml").write_text(text)


def _checkout(tmp_path):
    _app(tmp_path, ".", """
[project]
name = "perch"
dependencies = ["budgie @ git+https://example.invalid/budgie.git", "click", "rich"]
[project.optional-dependencies]
dev = ["pytest>=6.2.4"]
docs = ["sphinx"]
other = ["never"]
[project.scripts]
perch = "perch.cli:cli"
""")
    _app(tmp_path, "apps/budgie", """
[project]
name = "Budgie"
dependencies = ["click", "numpy"]
[project.scripts]
budgie = "budgie.budgie:cli"
""")
    _app(tmp_path, "apps/remote-gitboard", """
[project]
name = "gitboard"
dependencies = ["python-gitlab"]
[project.optional-dependencies]
dev = ["pytest"]
[project.scripts]
gitboard = "gitboard.cli:app"
""")
    return tmp_path


def test_requirements_are_every_apps_deps_and_dev_docs_extras_minus_urls(tmp_path):
    reqs = _venv().requirements(_checkout(tmp_path))
    assert reqs == [
        "click", "rich", "pytest>=6.2.4", "sphinx", "numpy", "python-gitlab", "pytest"
    ]


def test_wrappers_run_each_entry_point_from_source(tmp_path):
    perch = _checkout(tmp_path)
    bin_dir = tmp_path / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "perch").symlink_to(tmp_path / "elsewhere")  # an old link is replaced, not followed
    written = _venv().wrappers(perch, bin_dir)
    assert [p.name for p in written] == ["perch", "budgie", "gitboard"]
    assert not (tmp_path / "elsewhere").exists()
    text = (bin_dir / "gitboard").read_text()
    assert text.startswith("#!/bin/sh\n")
    path = f"{perch}:{perch}/apps/budgie:{perch}/apps/remote-gitboard/src"
    assert f"PYTHONPATH={path}" in text
    assert "from gitboard.cli import app" in text and 'sys.argv[0] = "gitboard"' in text
    assert " -P -c " in text  # -P: the cwd (projects/NAME, a budget dir) never shadows a module
    assert (bin_dir / "gitboard").stat().st_mode & 0o111


def test_a_wrapper_actually_runs(tmp_path):
    perch = _checkout(tmp_path)
    pkg = perch / "apps" / "remote-gitboard" / "src" / "gitboard"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "cli.py").write_text(
        "import sys\ndef app():\n    print(sys.argv[0], *sys.argv[1:])\n    return 0\n"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python").symlink_to(Path(__import__("sys").executable))
    _venv().wrappers(perch, bin_dir)
    out = subprocess.run(
        [str(bin_dir / "gitboard"), "show", "a b"], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout == "gitboard show a b\n"
```

- [ ] **Step 3: Run to see it fail**

Run: `PYTHONPATH=$WT:/Users/ryanadams/Documents/git/perch/apps/budgie ~/Documents/tools/perch/bin/pytest -q perch/tests/test_install_env.py`
Expected: FAIL (`scripts/install_env.py` does not exist).

- [ ] **Step 4: Write `scripts/install_env.py`**

```python
"""make install's helper: what to pip install, and the commands that run from source.

Nothing of ours is built or installed. perch, Budgie and gitboard run from
their checkouts on PYTHONPATH, so there is no .pth file for macOS's hidden
flag to break, and no build backend (setuptools, hatchling) to download when
the machine is offline.

    python scripts/install_env.py requirements PERCH_DIR   # one requirement per line
    python scripts/install_env.py wrappers PERCH_DIR BIN    # perch, budgie, gitboard in BIN
"""

from __future__ import annotations

import shlex
import sys
import tomllib
from pathlib import Path

APPS = (".", "apps/budgie", "apps/remote-gitboard")
SOURCES = (".", "apps/budgie", "apps/remote-gitboard/src")
EXTRAS = ("dev", "docs")


def _project(perch: Path, app: str) -> dict:
    return tomllib.loads((perch / app / "pyproject.toml").read_text())["project"]


def requirements(perch: Path) -> list[str]:
    """Every app's dependencies plus its dev and docs extras, first seen first.

    A URL requirement (perch's `budgie @ git+...`) is left out: that app is on
    PYTHONPATH from its checkout instead.
    """
    out: list[str] = []
    for app in APPS:
        project = _project(perch, app)
        extras = project.get("optional-dependencies", {})
        for req in [*project.get("dependencies", []), *(r for e in EXTRAS for r in extras.get(e, []))]:
            if "@" not in req and req not in out:
                out.append(req)
    return out


def pythonpath(perch: Path) -> str:
    return ":".join(str(perch / s) if s != "." else str(perch) for s in SOURCES)


def wrappers(perch: Path, bin_dir: Path) -> list[Path]:
    """One sh script per [project.scripts] entry, where a console script would be."""
    python = shlex.quote(str(bin_dir / "python"))
    env = shlex.quote(f"PYTHONPATH={pythonpath(perch)}")
    written = []
    for app in APPS:
        for name, target in _project(perch, app).get("scripts", {}).items():
            module, func = target.split(":")
            code = (
                f'import sys; sys.argv[0] = "{name}"; '
                f"from {module} import {func}; sys.exit({func}())"
            )
            path = bin_dir / name
            path.unlink(missing_ok=True)  # an old symlink is replaced, never written through
            path.write_text(
                "#!/bin/sh\n"
                "# Written by perch's make install: runs the checkout's source.\n"
                f"exec env {env} {python} -P -c {shlex.quote(code)} \"$@\"\n"
            )
            path.chmod(0o755)
            written.append(path)
    return written


def main(argv: list[str]) -> int:
    if argv[:1] == ["requirements"] and len(argv) == 2:
        print("\n".join(requirements(Path(argv[1]).resolve())))
        return 0
    if argv[:1] == ["wrappers"] and len(argv) == 3:
        for path in wrappers(Path(argv[1]).resolve(), Path(argv[2])):
            print(f"wrote {path}")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

Note `pythonpath` uses `perch` for `"."` so the first entry has no trailing `/.`; the test's expected string depends on that.

- [ ] **Step 5: Run the test to see it pass**

Run: `PYTHONPATH=$WT:/Users/ryanadams/Documents/git/perch/apps/budgie ~/Documents/tools/perch/bin/pytest -q perch/tests/test_install_env.py`
Expected: 3 passed.

- [ ] **Step 6: Makefile**

Replace the venv variables block and the `install`, `link`, `lint`, `format`, `test`, `test-all`, `docs` targets:

```make
# One venv for all three apps, inside this checkout. Nothing of ours is built
# or installed into it: scripts/install_env.py pip-installs only the dependencies and
# writes perch/budgie/gitboard wrappers that run the source on PYTHONPATH. An
# editable install would need a .pth file, which macOS's hidden flag breaks
# inside a repo, and a build backend, which an offline machine cannot fetch.
# Offline: PIP_NO_INDEX=1 PIP_FIND_LINKS=/path/to/wheels make install
VENV       ?= $(PERCH_DIR)/.venv
BIN        := $(VENV)/bin
PYTHON     ?= python3
export PYTHONPATH := $(PERCH_DIR):$(PERCH_DIR)/apps/budgie:$(PERCH_DIR)/apps/remote-gitboard/src
NEEDS_311  := import sys; sys.exit(sys.version_info < (3, 11) and "perch needs Python 3.11 or newer: make install PYTHON=python3.12 (and rm -rf $(VENV) if it was made by an older one)")
```

```make
install: bootstrap ## Clone, put every app's dependencies in .venv, write the commands, link them
	$(PYTHON) -c '$(NEEDS_311)'
	test -x $(BIN)/python || $(PYTHON) -m venv $(VENV)
	$(BIN)/python -c '$(NEEDS_311)'
	-$(BIN)/pip uninstall -q -y perch budgie gitboard 2>/dev/null
	$(BIN)/python $(PERCH_DIR)/scripts/install_env.py requirements $(PERCH_DIR) > $(VENV)/requirements.txt
	$(BIN)/pip install -q -r $(VENV)/requirements.txt
	$(BIN)/python $(PERCH_DIR)/scripts/install_env.py wrappers $(PERCH_DIR) $(BIN)
	$(MAKE) link
	@echo "installed into $(VENV)."

link: ## Put perch, budgie and gitboard in ~/.local/bin
	@mkdir -p $(HOME)/.local/bin
	for tool in perch budgie gitboard; do ln -sf $(BIN)/$$tool $(HOME)/.local/bin/$$tool; done
```

```make
lint: ## Lint with ruff
	cd $(PERCH_DIR) && $(BIN)/ruff check .

format: ## Format with ruff
	cd $(PERCH_DIR) && $(BIN)/ruff format .

test: ## Run perch's test suite
	cd $(PERCH_DIR) && $(BIN)/pytest

test-all: ## Run all three test suites: Budgie, perch, gitboard
	$(MAKE) -C $(PERCH_DIR)/apps/budgie test VENV=$(VENV)
	cd $(PERCH_DIR) && $(BIN)/pytest -q
	$(MAKE) -C $(PERCH_DIR)/apps/remote-gitboard test

docs: ## Build the HTML docs into docs/_build
	cd $(PERCH_DIR) && $(BIN)/sphinx-build -W -b html docs docs/_build/html
```

Remove `PERCH_VENV`, `BUDGIE_VENV`, `PERCH ?=` and the old `install`/`link` bodies (the Budgie `venv`/`install` calls, `pip install -e`, and `$(MAKE) -C .../remote-gitboard install|link`). Update the header comment's last line to "The venv lives in .venv here; see install."

`make -n install` must print the uninstall line, the requirements line, the wrappers line and the `ln -sf` loop. Run it and check.

- [ ] **Step 7: setuptools floor and CI**

`pyproject.toml` line 28: `requires = ["setuptools>=61"]` with a comment line above it: `# 61 is the first that reads [project]; make install never builds perch, so this only matters to a hand-run pip install.`

`.github/workflows/docs.yml`: keep line 30's `pip install -q -e '.[docs]'` (CI has network and a fresh setuptools) and change line 31 to `- run: make docs VENV="$RUNNER_TEMP/venv"`.

- [ ] **Step 8: `Home.venv_bin`, gitboard argv, suite entry — failing tests first**

In `perch/tests/test_steps.py`, change the two gitboard expectations:

```python
    # in test_monday_is_five_steps_in_order_each_in_its_tool
    assert fetch.argv == (
        str(home.venv_bin / "gitboard"),
        "stats", "grp/apollo", "--history-days", "276", "--dump", str(config.board_dump),
        "--log", str(board_dir / "stats.jsonl"),
    )  # fmt: skip
    assert fetch.cwd == home.gitboard_dir and fetch.env == {}
```

```python
    # in the gb parametrized test, replacing the last two lines
    assert step.argv == (str(home.venv_bin / "gitboard"), *want)
    assert step.cwd == home.gitboard_dir and step.env == {}
```

In `perch/tests/test_tui.py` (~line 406), the gitboard entry becomes:

```python
    assert m["gitboard"] == {
        "cwd": str(home.gitboard_dir),
        "argv": [
            str(home.venv_bin / "gitboard"),
            "tui",
            "grp/apollo",
            "--db",
            str(board / "snapshots.jsonl"),
            "--boards-dir",
            str(board),
        ],
        "project": "apollo",
    }
```

In `perch/tests/test_workspace.py` next to the `gitboard_dir` assertion (line ~79): `assert home.venv_bin == tmp_path / ".venv" / "bin"`.

Run the three files; expected FAIL (`venv_bin` missing, old argv).

- [ ] **Step 9: Implement**

`perch/core/workspace.py`, in `Home` beside `gitboard_dir`:

```python
    @property
    def venv_bin(self) -> Path:
        """Where make install writes the perch, budgie and gitboard commands."""
        return self.root / ".venv" / "bin"
```

`perch/core/steps.py` `gitboard()`:

```python
def gitboard(home: Home, name: str, *args: str, makes: tuple[Path, ...] = ()) -> Step:
    """gitboard runs from its checkout: it finds .env and gitboard.toml from there."""
    return Step(name, (str(home.venv_bin / "gitboard"), *args), home.gitboard_dir, {}, makes)
```

`perch/tui.py` `suite_map` gitboard `argv`: `[str(home.venv_bin / "gitboard"), "tui", *gitlab, "--db", ..., "--boards-dir", ...]` (drop the `env`, `PYTHONPATH=` and `-m gitboard.cli` items).

`grep -rn '\.venv/bin/python\|gitboard_dir / "src"\|gitboard_dir / .src' perch/` must print nothing except `perch/core/walk.py`'s `_RUNNER` (that string matches text inside gitboard's `/board` command and stays).

- [ ] **Step 10: Doctor warns about the old venvs — failing test first**

Append to `perch/tests/test_doctor.py`:

```python
def test_old_venvs_are_named_never_deleted(tmp_path):
    from perch.core.doctor import old_venv_checks

    assert old_venv_checks(tmp_path) == []
    old = tmp_path / "Documents" / "tools" / "perch"
    old.mkdir(parents=True)
    [check] = old_venv_checks(tmp_path)
    assert not check.ok and str(old) in check.what
    assert check.fix == f"rm -rf {old}"
    assert old.is_dir()
```

Implement in `perch/core/doctor.py`:

```python
OLD_VENVS = ("Documents/tools/perch", "Documents/tools/budgie")


def old_venv_checks(user_home: Path) -> list[Check]:
    """The venvs make install used before perch/.venv: named, never deleted."""
    return [
        Check(False, f"old install at {old} (perch/.venv replaces it)", f"rm -rf {old}")
        for old in (user_home / rel for rel in OLD_VENVS)
        if old.is_dir()
    ]
```

In `perch/cli.py` `doctor`, after `show(tool_checks(_bin_dir(), home, _runs))`:

```python
    if old := old_venv_checks(Path.home()):
        show(old)
```

and add `old_venv_checks` to that function's `from perch.core.doctor import (...)`.

Any existing doctor CLI test that runs on this machine will now see the real `~/Documents/tools/perch`: in `perch/tests/test_cli*.py`, find tests that invoke `doctor` (`grep -n '"doctor"' perch/tests/*.py`) and, where they assert the exit code or FIX count, add `monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)`.

- [ ] **Step 11: Docs**

- `README.md` and `docs/install.md`: the install section says `make install` puts one `.venv` in the checkout holding only dependencies, writes `perch`, `budgie`, `gitboard` into `.venv/bin` and links them into `~/.local/bin`; needs Python 3.11+ (`make install PYTHON=python3.12`); offline: `PIP_NO_INDEX=1 PIP_FIND_LINKS=/path/to/wheels make install`; the old `~/Documents/tools/{perch,budgie}` can be deleted once `perch doctor` is clean (doctor names them).
- `CLAUDE.md` Commands block: `make install  # deps into .venv (nothing built), wrappers in .venv/bin, link; re-run to repair`. In the paragraph about Budgie being a library dependency, replace "`make install` installs `apps/budgie` editable after perch, so the local checkout wins for dev." with "`make install` never installs Budgie (or perch, or gitboard): all three run from their checkouts on `PYTHONPATH` via the wrappers `scripts/install_env.py` writes."

- [ ] **Step 12: Full suite, lint, commit, close**

```bash
PYTHONPATH=$WT:/Users/ryanadams/Documents/git/perch/apps/budgie ~/Documents/tools/perch/bin/pytest -q
~/Documents/tools/perch/bin/ruff check .
make -n install | tail -6
git add -A -- . ':!apps' && git commit -m "build: one .venv in the checkout, dependencies only, wrapper commands (perch-w41.4)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Js49meT3psoy4w3dc8PdQ"
cd /Users/ryanadams/Documents/git/perch && bd close perch-w41.4 --reason "scripts/install_env.py + Makefile: deps-only .venv, wrappers, links; gitboard runs via .venv/bin/gitboard; doctor names old venvs"
```

Do **not** run the real `make install` here: Task 8 does, on the merged main checkout.

---

### Task 2: gitboard members, and pull keeps people/emails/estimates

Bead `perch-w41.2`, repo `apps/remote-gitboard`, wave 2 (after Task 1 is merged into gitboard `main`).

**Files:**
- Create: `src/gitboard/members.py`, `tests/test_members.py`
- Modify: `src/gitboard/cli.py` (`_pull_spec` line ~777, its call sites at ~555, ~556, ~821, ~826; new `members` command after `estimate`)
- Modify: `src/gitboard/tui.py:392-393` (`_pull_spec` calls)
- Modify: `tests/test_cli.py` (`fake_board`, new tests)
- Modify: `docs/board-yaml.md` (`people` key), `src/gitboard/CLAUDE.md` (module line), root `CLAUDE.md` Commands list (one clause)

**Interfaces:**
- Produces: `members.fetch(project) -> dict[str, str]` (username -> display name), `members.merge(people: dict | None, found: dict[str, str]) -> tuple[dict, list[str]]` (new `people:` map name -> username, added usernames), `members.KEEP = ("people", "emails", "estimates")`.
- Produces CLI: `gitboard members [SPEC] [--project GROUP/PROJ] [--out FILE]`.
- Produces: `_pull_spec(proj, board, columns, out_file, notes=False, force=False, people=False)`; with `people=True` it carries `KEEP` keys from an existing `out_file` and merges members.

- [ ] **Step 1: Claim and branch**

```bash
cd /Users/ryanadams/Documents/git/perch && bd update perch-w41.2 --claim
git -C apps/remote-gitboard worktree add /Users/ryanadams/Documents/git/perch/.claude/worktrees/gb-perch-w41.2 -b bead/perch-w41.2
cd /Users/ryanadams/Documents/git/perch/.claude/worktrees/gb-perch-w41.2
```

- [ ] **Step 2: Failing tests for the pure part** (`tests/test_members.py`)

```python
import types

from gitboard import members


def _member(username, name, state="active"):
    return types.SimpleNamespace(username=username, name=name, state=state)


def _project(*rows):
    return types.SimpleNamespace(
        members_all=types.SimpleNamespace(list=lambda **k: list(rows))
    )


def test_fetch_keeps_active_people_and_drops_bots():
    project = _project(
        _member("alice", "Alice Ng"),
        _member("gone", "Gone Person", state="blocked"),
        _member("project_12_bot_ab12", "Bot"),
        _member("group_7_bot", "Group bot"),
        _member("bruiz", "Bob Ruiz"),
    )
    assert members.fetch(project) == {"alice": "Alice Ng", "bruiz": "Bob Ruiz"}


def test_merge_adds_only_new_usernames_and_never_renames():
    people = {"Alice": "alice"}  # the lead renamed Alice Ng to match people.csv
    merged, added = members.merge(people, {"alice": "Alice Ng", "bruiz": "Bob Ruiz"})
    assert merged == {"Alice": "alice", "Bob Ruiz": "bruiz"}
    assert added == ["bruiz"]


def test_merge_names_a_display_name_clash_by_username():
    merged, added = members.merge({"Sam Lee": "slee"}, {"slee2": "Sam Lee"})
    assert merged == {"Sam Lee": "slee", "Sam Lee (slee2)": "slee2"}
    assert added == ["slee2"]


def test_merge_from_nothing():
    assert members.merge(None, {}) == ({}, [])
```

Run: `PYTHONPATH=src /Users/ryanadams/Documents/git/perch/apps/remote-gitboard/.venv/bin/pytest -q tests/test_members.py` — expected FAIL (no module).

- [ ] **Step 3: Write `src/gitboard/members.py`**

```python
"""Who is on a GitLab project, for the board YAML's `people:` map.

`fetch` is the one API call (read token); `merge` is pure. The map is
display name -> username, as `ingest` already reads it. A merge only adds:
the lead may have renamed someone to match another tool's roster, and a
later pull must not undo that.
"""

import re

KEEP = ("people", "emails", "estimates")  # local-only keys a re-pull carries over
_BOT = re.compile(r"(project|group)_\d+_bot")


def fetch(project):
    """{username: display name} for active, human members (inherited included)."""
    return {
        m.username: m.name
        for m in project.members_all.list(all=True)
        if m.state == "active" and not _BOT.match(m.username)
    }


def merge(people, found):
    """(people with every unknown username added, the usernames added)."""
    merged = dict(people or {})
    known = set(merged.values())
    added = []
    for username, name in sorted(found.items()):
        if username in known:
            continue
        key = name if name not in merged else f"{name} ({username})"
        merged[key] = username
        added.append(username)
    return merged, added
```

Run the test file: expected PASS.

- [ ] **Step 4: Failing CLI tests** (`tests/test_cli.py`)

First make the shared fake project answer `members_all` — in `fake_board()`:

```python
def fake_board(project="grp/proj", name="Dev Board", people=()):
    milestones = types.SimpleNamespace(list=lambda **k: [])
    members_all = types.SimpleNamespace(list=lambda **k: list(people))
    proj = types.SimpleNamespace(
        path_with_namespace=project, milestones=milestones, members_all=members_all
    )
    return proj, types.SimpleNamespace(name=name)
```

Then find how the `gl` fixture wires `fake_board` into `board_mod.fetch` (`grep -n "fake_board" tests/*.py`) and add tests:

```python
ALICE = types.SimpleNamespace(username="alice", name="Alice Ng", state="active")


def test_pull_force_keeps_people_emails_estimates_and_adds_members(gl, tmp_path, monkeypatch):
    monkeypatch.setattr(board_mod, "fetch", lambda *a, **k: fake_board(people=[ALICE]))
    hand = {"people": {"Bob": "bruiz"}, "emails": {"bruiz": "b@x"}, "estimates": {"method": "p85"}}
    path = write_spec(tmp_path, spec={**SPEC, **hand})
    r = runner.invoke(app, ["pull", "grp/proj", "--force", "-o", path])
    assert r.exit_code == 0, r.output
    spec = apply_mod.load(path)
    assert spec["people"] == {"Bob": "bruiz", "Alice Ng": "alice"}
    assert spec["emails"] == {"bruiz": "b@x"} and spec["estimates"] == {"method": "p85"}
    assert "people" not in apply_mod.load(path + ".base")


def test_members_updates_the_spec_people_in_place(gl, tmp_path, monkeypatch):
    monkeypatch.setattr(board_mod, "fetch", lambda *a, **k: fake_board(people=[ALICE]))
    path = write_spec(tmp_path)
    r = runner.invoke(app, ["members", path])
    assert r.exit_code == 0, r.output
    assert apply_mod.load(path)["people"] == {"Alice Ng": "alice"}
    assert "1 added" in r.output


def test_members_out_writes_only_the_map(gl, tmp_path, monkeypatch):
    monkeypatch.setattr(board_mod, "fetch", lambda *a, **k: fake_board(people=[ALICE]))
    out = tmp_path / "people.yaml"
    r = runner.invoke(app, ["members", "--project", "grp/proj", "--out", str(out)])
    assert r.exit_code == 0, r.output
    assert yaml.safe_load(out.read_text()) == {"people": {"Alice Ng": "alice"}}
```

Every fake project the suite builds must answer `members_all`, or the `people=True` path raises `AttributeError` in a test these new ones never reach. Run `grep -n "path_with_namespace=" tests/*.py` (9 sites today: `test_cli.py`, the sync and TUI tests, `test_board.py`) and give each `SimpleNamespace` project `members_all=types.SimpleNamespace(list=lambda **k: [])`. Then read the `gl` fixture (`grep -n "def gl" tests/*.py`): if it patches `board_mod.fetch` itself, use the same mechanism in the three tests above instead of `monkeypatch.setattr(board_mod, "fetch", ...)`; the assertions stay as written. `members` calls `client.get_project(client.gitlab(), path)` and needs no board, so the two `members` tests also do `monkeypatch.setattr(client, "get_project", lambda gl, path: fake_board(people=[ALICE])[0])`.

Add a test that a failing members call never breaks a pull:

```python
def test_pull_still_writes_when_members_cannot_be_read(gl, tmp_path, monkeypatch):
    def refuse(**k):
        raise client.GitlabProblem("403 Forbidden")

    proj, board = fake_board()
    proj.members_all = types.SimpleNamespace(list=refuse)
    monkeypatch.setattr(board_mod, "fetch", lambda *a, **k: (proj, board))
    path = write_spec(tmp_path, spec={**SPEC, "people": {"Bob": "bruiz"}})
    r = runner.invoke(app, ["pull", "grp/proj", "--force", "-o", path])
    assert r.exit_code == 0, r.output
    assert apply_mod.load(path)["people"] == {"Bob": "bruiz"}
    assert "members: 403 Forbidden" in r.output
```

Run: expected FAIL.

- [ ] **Step 5: Implement pull carry-over in `src/gitboard/cli.py`**

```python
def _pull_spec(proj, board, columns, out_file, notes=False, force=False, people=False):
    """Write the live board as YAML. Refuses to clobber unless told to.

    `people=True` (the board file, never its .base) carries the local-only
    keys over from the file being replaced and adds the project's members to
    `people:`, so a re-pull keeps them and a first pull fills them.
    """
    if Path(out_file).exists() and not force:
        raise ConfigError(
            f"{out_file} already exists — edit it, pass a different --out, "
            "or --force to overwrite"
        )
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)
    spec = apply_mod.spec_from_board(proj, board, columns, notes=notes)
    if people:
        old = _raw_or_empty(out_file)
        spec.update({k: old[k] for k in members_mod.KEEP if old.get(k)})
        try:
            found = members_mod.fetch(proj)
        except (client.GitlabProblem, gitlab_errors.GitlabError) as exc:
            # A read token that can see the board may not see its members
            # (not a member, an old scope): the pull still succeeds.
            err().print(f"[muted]members: {escape(str(exc))}; people: left as it was[/]")
            found = {}
        merged, _ = members_mod.merge(spec.get("people"), found)
        if merged:
            spec["people"] = merged
    Path(out_file).write_text(apply_mod.dump(spec))
    return out_file


def _raw_or_empty(path):
    """The file as plain YAML, or {} when it is missing or unreadable."""
    try:
        data = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}
```

Add `from gitboard import members as members_mod`, `from gitlab import exceptions as gitlab_errors` (and `import yaml` if cli.py lacks it) with the other imports; `escape` came in with Task 1. If cli.py imports `gitlab` only lazily (inside functions, for startup time), import `gitlab.exceptions` inside `_pull_spec` instead. Pass `people=True` at the two **board-file** call sites only: `_refresh_spec` (`_pull_spec(proj, board, columns, spec_path, notes=notes, force=True, people=True)`) and `_pull_board` (`_pull_spec(proj, board, columns, target, notes=notes, force=force, people=True)`), and at the first of the two calls in `src/gitboard/tui.py:392` (the board file; the second writes the `.base`). The `.base` calls stay as they are. Key order: `spec_from_board` writes `project`, `board`, ...; carried keys are appended after, which `apply.dump` (`sort_keys=False`) keeps.

- [ ] **Step 6: The `members` command** (after `estimate` in `cli.py`)

```python
@app.command()
def members(
    spec: str | None = typer.Argument(
        None, help="Board YAML whose people: to update. Defaults to the config spec."
    ),
    project: str | None = typer.Option(
        None, "--project", help="group/project. Default: the spec's project:."
    ),
    out: str | None = typer.Option(
        None, "--out", help="Write people: here instead of into the spec."
    ),
):
    """Add the project's GitLab members to the board YAML's people:. Reads only.

    Never renames or drops an entry, so a name changed to match another
    tool's roster survives.
    """

    def go():
        spec_path = spec or (None if project and out else _need(None, "spec", "spec file"))
        parsed = apply_mod.load(spec_path) if spec_path else {}
        path = project or parsed.get("project") or _need(None, "project", "project")
        target = out or spec_path
        with err().status(f"reading {path} members…"):
            found = members_mod.fetch(client.get_project(client.gitlab(), path))
        current = _raw_or_empty(target)
        merged, added = members_mod.merge(current.get("people"), found)
        if out and not current.get("board"):
            current = {}  # --out to a plain file holds the map alone
        current["people"] = merged
        Path(target).write_text(apply_mod.dump(current))
        err().print(
            f"[added]{len(added)} added[/], {len(found) - len(added)} already in "
            f"people: -> {_shortest(target)}"
        )

    _run(go)
```

(`_shortest` exists in cli.py; if `apply_mod.dump` validates or reorders board-only keys, use `yaml.safe_dump(current, sort_keys=False, allow_unicode=True)` for the `--out` plain-file case instead.) Writing the spec back through `_raw_or_empty` + `dump` mirrors what `ingest` does: comments are lost, which the existing `ponytail:` note at cli.py ~977 already accepts.

- [ ] **Step 7: Run all gitboard tests and lint**

Run: `PYTHONPATH=src /Users/ryanadams/Documents/git/perch/apps/remote-gitboard/.venv/bin/pytest -q && /Users/ryanadams/Documents/git/perch/apps/remote-gitboard/.venv/bin/ruff check .`
Expected: all pass. Existing pull tests that compare `apply_mod.load(path) == SPEC` still pass because the default fake has no members and an empty merge writes no `people:` key.

- [ ] **Step 8: Docs**

- `docs/board-yaml.md`, `people` entry: append "`gitboard members [SPEC]` adds the project's GitLab members here (display name -> username; never renames or drops one), and every `pull`/`sync` keeps this map, `emails` and `estimates` and adds new members."
- `src/gitboard/CLAUDE.md` Modules: add "- **`members.py`** — `fetch(project)` (members_all, active, bots dropped) and pure `merge(people, found)` (adds unknown usernames only; a name clash gets ` (username)`). `_pull_spec(people=True)` carries `KEEP` keys over and merges members on the board file, never the `.base`."
- Root `CLAUDE.md` Commands paragraph: add "`members [SPEC] [--project P] [--out FILE]` (add GitLab members to `people:`; pull and sync do it too and keep `people`/`emails`/`estimates`);".

- [ ] **Step 9: Commit, close**

```bash
git add -A && git commit -m "feat: gitboard members, and pull keeps people/emails/estimates (perch-w41.2)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Js49meT3psoy4w3dc8PdQ"
cd /Users/ryanadams/Documents/git/perch && bd close perch-w41.2 --reason "members command; pull/sync carry local keys and add members"
```

---

### Task 5: perch per-project .env

Bead `perch-w41.5`, repo perch, wave 2 (after Task 4 is merged into perch `main`).

**Files:**
- Modify: `perch/core/steps.py` (`gitboard`, `fetch`, `gb`, `digest`), `perch/tui.py` (`suite_map` gitboard cwd)
- Modify: `perch/core/workspace.py` (`ENV_TEMPLATE`, `scaffold(name, gitlab=None)`, `env_path`)
- Modify: `perch/core/doctor.py` (`read_env`, `env_checks`), `perch/cli.py` (`init --gitlab`, doctor wiring)
- Tests: `perch/tests/test_steps.py`, `test_tui.py`, `test_workspace.py`, `test_doctor.py`, `test_cli_projects.py`

**Interfaces:**
- Consumes: `Home.venv_bin`, `steps.gitboard` from Task 4.
- Produces: `steps.gitboard(home, name, *args, makes=(), project: str | None = None)`: cwd `home.projects_dir / project` when given, else `home.root`.
- Produces: `Home.env_path(name) -> Path` (`projects/NAME/.env`), `Home.scaffold(name, gitlab: str | None = None) -> Path` (also writes `.env` if absent), `workspace.ENV_TEMPLATE`, `workspace.PLACEHOLDER = "<key-from-gitlab>"`.
- Produces: `doctor.read_env(path: Path) -> dict[str, str]`, `doctor.env_checks(home: Home, name: str, environ: Mapping[str, str]) -> list[Check]`.

- [ ] **Step 1: Claim and branch** (perch recipe; `WT=.claude/worktrees/perch-w41.5`, symlink `apps`)

- [ ] **Step 2: Failing tests: gitboard runs from the project folder**

`perch/tests/test_steps.py`: in the monday test, `assert fetch.cwd == home.projects_dir / "apollo" and fetch.env == {}`; for `digest` add `assert digest.cwd == home.projects_dir / "apollo"`; in the gb parametrized test `assert step.cwd == home.projects_dir / "apollo"`. New test:

```python
def test_gitboard_with_no_project_runs_from_home_not_its_checkout(tmp_path):
    home, _ = apollo(tmp_path)
    step = steps.gitboard(home, "gitboard", "--help")
    assert step.cwd == home.root  # the checkout's dev gitboard.toml never applies
```

`perch/tests/test_tui.py` suite entry: `"cwd": str(home.projects_dir / "apollo")`.

Run: FAIL.

- [ ] **Step 3: Implement the cwd move**

```python
def gitboard(
    home: Home,
    name: str,
    *args: str,
    makes: tuple[Path, ...] = (),
    project: str | None = None,
) -> Step:
    """gitboard runs from the project's folder, where it finds the project's .env.

    gitboard walks up from its cwd for .env (and gitboard.toml), so
    projects/NAME/.env wins and the checkout's .env is the shared fallback.
    With no project (doctor's --help) it runs from home, never from gitboard's
    own checkout, whose development gitboard.toml must not reach real runs.
    """
    cwd = home.projects_dir / project if project else home.root
    return Step(name, (str(home.venv_bin / "gitboard"), *args), cwd, {}, makes)
```

Pass `project=project` in `fetch(...)`, `digest(...)` and at the end of `gb(...)` (`return gitboard(home, f"gb {sub}", sub, *target, *args, project=project)`). In `tui.suite_map`, gitboard `"cwd": str(home.projects_dir / name)`. Run the tests: PASS. Every path these steps pass is already absolute (check by reading `fetch`, `gb`'s `target` table, `digest`).

- [ ] **Step 4: Failing tests: init writes .env and takes --gitlab**

`perch/tests/test_workspace.py`:

```python
def test_scaffold_writes_a_project_env_once_and_fills_gitlab(tmp_path):
    home = make_home(tmp_path)
    home.scaffold("apollo", gitlab="grp/apollo")
    env = home.env_path("apollo")
    assert env == home.projects_dir / "apollo" / ".env"
    assert "GITLAB_READ_TOKEN=<key-from-gitlab>" in env.read_text()
    assert "gitlab_project: grp/apollo" in home.config_path("apollo").read_text()
    env.write_text("GITLAB_READ_TOKEN=real\n")
    home.config_path("apollo").unlink()
    home.scaffold("apollo")
    assert env.read_text() == "GITLAB_READ_TOKEN=real\n"  # never overwritten
```

`perch/tests/test_cli_projects.py`:

```python
def test_init_gitlab_fills_the_project_path(tmp_path, monkeypatch):
    home = build_home(tmp_path)
    monkeypatch.chdir(home.root)
    fake_budgie_init(monkeypatch)
    result = run("init", "apollo", "--gitlab", "grp/apollo")
    assert result.exit_code == 0, result.output
    config = load_config(home.config_path("apollo"), require_dump=False)
    assert config.gitlab_project == "grp/apollo"
    assert home.env_path("apollo").is_file() and ".env" in result.output
```

Run: FAIL.

- [ ] **Step 5: Implement in `perch/core/workspace.py`**

```python
PLACEHOLDER = "<key-from-gitlab>"
ENV_FILE = ".env"
ENV_TEMPLATE = f"""\
# This project's GitLab, read by gitboard (perch runs it from this folder).
# Gitignored with the rest of projects/. A real exported variable still wins.
GITLAB_URL=https://gitlab.com
# read_api scope: fetch, pull, members, the read-only /board pass
GITLAB_READ_TOKEN={PLACEHOLDER}
# api scope: push and sync only
GITLAB_WRITE_TOKEN={PLACEHOLDER}
"""
```

`SCAFFOLD`: change the `gitlab_project:` line to `gitlab_project: {gitlab}                      # the GitLab path, e.g. group/{name}`. In `Home`:

```python
    def env_path(self, name: str) -> Path:
        """This project's tokens; the checkout's .env is the shared fallback."""
        return self.projects_dir / name / ENV_FILE

    def scaffold(self, name: str, gitlab: str | None = None) -> Path:
        """Write projects/NAME/perch.yaml pointing at its budget/, and a .env
        template. Never overwrites either."""
        path = self.config_path(check_name(name))
        if path.exists():
            raise FileExistsError(f"{path} exists; edit it instead.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(SCAFFOLD.format(name=name, gitlab=gitlab or ""))
        if not self.env_path(name).exists():
            self.env_path(name).write_text(ENV_TEMPLATE)
        return path
```

(With `gitlab=""` the line reads `gitlab_project:` followed by spaces, which YAML loads as None, as today. Keep the comment column aligned however `ruff format` leaves the string.)

`perch/cli.py` `init`: add `@click.option("--gitlab", default=None, help="The GitLab path, e.g. group/NAME (fills gitlab_project:).")`, pass it to `home.scaffold(name, gitlab)`, print the `gitlab_project:` fill-in line only when `--gitlab` was not given, and add a line: `console.print(f"  {os.path.relpath(home.env_path(name), home.root)}  the GitLab URL and tokens (one .env per project)", markup=False)`.

Run the tests: PASS.

- [ ] **Step 6: Failing tests: doctor checks the token without printing it**

`perch/tests/test_doctor.py`:

```python
from perch.core.doctor import env_checks, read_env


def test_read_env_parses_like_dotenv(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "# comment\nexport A=1\nB = 'two words'\nC=\"x\" # note\nD=plain # note\n\nE\n"
    )
    assert read_env(path) == {"A": "1", "B": "two words", "C": "x", "D": "plain"}
    assert read_env(tmp_path / "missing") == {}


def test_read_token_placeholder_is_not_a_token(tmp_path):
    home = build_home(tmp_path, "apollo")
    home.env_path("apollo").write_text("GITLAB_READ_TOKEN=<key-from-gitlab>\n")
    [check] = env_checks(home, "apollo", {})
    assert not check.ok and str(home.env_path("apollo")) in check.fix


def test_read_token_project_then_home_then_environment(tmp_path):
    home = build_home(tmp_path, "apollo")
    secret = "s3cret-value"
    (home.root / ".env").write_text(f"GITLAB_READ_TOKEN={secret}\n")
    [check] = env_checks(home, "apollo", {})
    assert check.ok and "checkout .env" in check.what and secret not in check.what
    (home.root / ".env").unlink()
    [check] = env_checks(home, "apollo", {"GITLAB_READ_TOKEN": secret})
    assert check.ok and "environment" in check.what and secret not in check.what
    home.env_path("apollo").write_text(f"GITLAB_READ_TOKEN={secret}\n")
    [check] = env_checks(home, "apollo", {})
    assert check.ok and "projects/apollo/.env" in check.what
```

Run: FAIL.

- [ ] **Step 7: Implement in `perch/core/doctor.py`**

```python
from perch.core.workspace import CONFIG_FILE, PLACEHOLDER, Home

READ_TOKEN = "GITLAB_READ_TOKEN"


def read_env(path: Path) -> dict[str, str]:
    """KEY=value lines the way python-dotenv reads them; {} for no file.

    Enough of dotenv for doctor to see whether a key is set: comments,
    `export `, quotes and a trailing ` # note`. Values are never printed.
    """
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return {}
    out = {}
    for line in lines:
        line = line.strip().removeprefix("export ").strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if value[:1] in ("'", '"') and value[0] in value[1:]:
            value = value[1 : value.index(value[0], 1)]
        else:
            value = value.split(" #", 1)[0].strip()
        if value:
            out[key] = value
    return out


def env_checks(home: Home, name: str, environ: Mapping[str, str]) -> list[Check]:
    """Where this project's read token comes from; never what it is.

    gitboard's order: an exported variable, then the nearest .env walking up
    from projects/NAME (the project's, then the checkout's).
    """
    own = home.env_path(name)
    rel = own.relative_to(home.root)
    if environ.get(READ_TOKEN):
        return [Check(True, f"{name}: read token from the environment")]
    for path, label in ((own, str(rel)), (home.root / ".env", "checkout .env")):
        if path.exists():  # gitboard reads only the first .env it finds
            value = read_env(path).get(READ_TOKEN)
            if value and value != PLACEHOLDER:
                return [Check(True, f"{name}: read token in {label}")]
            break
    return [
        Check(
            False,
            f"{name}: no GitLab read token",
            f"set GITLAB_READ_TOKEN (read_api) in {own} "
            "(or export it, or use the gitlab-read-token keychain item)",
        )
    ]
```

Note the walk rule: gitboard reads only the **first** `.env` it finds walking up. So if `projects/NAME/.env` exists (even with only the placeholder), the checkout's `.env` is never read for that project; the loop's `break` mirrors that. A project with no `.env` of its own falls through to the checkout's. (`projects/.env` would sit between the two; it is not a supported place and doctor ignores it.) The keychain fallback is not checked, so a lead who keeps the token only in the keychain sees a FIX line whose text names that case.

In `perch/cli.py` doctor, inside `for name in names:` after `show(project_checks(home, name))`: `show(env_checks(home, name, os.environ))` (import `env_checks`).

Run the tests: PASS. Then the full perch suite and lint.

- [ ] **Step 8: Docs**

`docs/install.md` / `docs/guide.md` (wherever tokens are described: `grep -n "TOKEN\|\.env" docs/*.md`): one `.env` per project at `projects/NAME/.env`, written by `perch init` with `<key-from-gitlab>` placeholders; `perch/.env` is the shared fallback for projects without their own; `perch doctor` says which one each project uses. `CLAUDE.md` `core/steps.py` bullet: "`gb` runs gitboard from `projects/NAME` (so its `.env` is that project's) with the project's target and ...".

- [ ] **Step 9: Commit, close**

```bash
git add -A -- . ':!apps' && git commit -m "feat: per-project .env; gitboard runs from projects/NAME (perch-w41.5)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Js49meT3psoy4w3dc8PdQ"
cd /Users/ryanadams/Documents/git/perch && bd close perch-w41.5 --reason "gitboard cwd is the project; init writes .env and takes --gitlab; doctor reports the token source"
```

---

### Task 7: Budgie Makefile installs into perch home when inside perch

Bead `perch-w41.7`, repo `apps/budgie`, wave 2 (after Task 4 merged). Also resolves `perch-ee8` (close it with this task).

**Files:**
- Modify: `Makefile`, `pyproject.toml` (`[build-system]`), `CLAUDE.md` (Install & Run), `README.md` (install section)

**Interfaces:**
- Consumes: perch `make install` (Task 4).

- [ ] **Step 1: Claim and branch** (Budgie recipe; also `bd update perch-ee8 --claim`)

- [ ] **Step 2: Makefile**

Replace the header comment, `VENV ?=`, `venv:` and `install:`:

```make
# Inside a perch checkout (perch/apps/budgie) Budgie runs from source out of
# perch's one .venv, and perch's `make install` fills it. Installed alone it
# keeps a venv outside the repo: a .pth file inside a repo picks up macOS's
# hidden flag and site.py skips it. The perch rule: two levels up holds a
# pyproject.toml named perch and an apps/ directory.
PERCH_HOME := $(shell d=$$(cd $(CURDIR)/../.. && pwd); \
  grep -qs '^name = "perch"' "$$d/pyproject.toml" && test -d "$$d/apps" && echo "$$d")

ifdef PERCH_HOME
VENV ?= $(PERCH_HOME)/.venv
export PYTHONPATH := $(CURDIR)
else
VENV ?= $(HOME)/Documents/tools/budgie
endif
BIN := $(VENV)/bin
```

```make
install: ## Install: perch's when inside perch, else a venv in $(VENV) with budgie editable
ifdef PERCH_HOME
	$(MAKE) -C $(PERCH_HOME) install
else
	test -x $(BIN)/pip || python3 -m venv $(VENV)
	$(BIN)/pip install -q -e '.[dev,docs]'
endif
```

Delete the `venv:` target and drop `venv` from `.PHONY`. `activate` keeps working (`$(BIN)/activate`).

- [ ] **Step 3: Check by dry run**

From the main checkout `PERCH/apps/budgie` (the worktree's `../..` is not perch home, so also check the worktree for the standalone branch):

```bash
make -n -f <worktree>/Makefile -C /Users/ryanadams/Documents/git/perch/apps/budgie install   # expect: make -C /Users/ryanadams/Documents/git/perch install
make -n -f <worktree>/Makefile -C /Users/ryanadams/Documents/git/perch/apps/budgie test      # expect: /Users/ryanadams/Documents/git/perch/.venv/bin/pytest
make -n install                                                                              # in the worktree: python3 -m venv ... and pip install -e
```

- [ ] **Step 4: setuptools floor, docs**

`pyproject.toml`: `requires = ["setuptools>=64"]` with the comment `# 64: the standalone install is editable (PEP 660); perch's make install never builds Budgie.`

`CLAUDE.md` "Install & Run": "Install through perch (`... make install`), which puts this checkout at `perch/apps/budgie` and runs it from source out of perch's `.venv` (nothing built; this Makefile's `install` delegates to perch's when it sits there). Installed alone, `make install` makes a venv in `~/Documents/tools/budgie` with Budgie editable." Replace "Run the suite as `~/Documents/tools/perch/bin/pytest` (perch's environment)." with "Inside perch, `make test` runs the suite in perch's `.venv` with `PYTHONPATH` set to this checkout." `README.md`: remove `make venv`; the install section says the same two cases.

- [ ] **Step 5: Tests, commit, close**

```bash
PYTHONPATH=$PWD ~/Documents/tools/perch/bin/pytest -q
git add -A && git commit -m "build: install delegates to perch when inside it; one install target (perch-w41.7)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Js49meT3psoy4w3dc8PdQ"
cd /Users/ryanadams/Documents/git/perch && bd close perch-w41.7 perch-ee8 --reason "Budgie Makefile: perch-home detection, single install target, setuptools>=64"
```

---

### Task 6: perch members, people merge, project-name length

Bead `perch-w41.6`, repo perch, wave 3 (after Tasks 2 and 5 are merged).

**Files:**
- Modify: `perch/core/config.py` (`Config.unmatched`, `_board_people`, `_budgie_names`, merge in `load_config`)
- Modify: `perch/core/steps.py` (`GB_SUBS`, `gb` target for `members`)
- Modify: `perch/core/workspace.py` (`check_name` length, `NAME_SHORT`)
- Modify: `perch/core/doctor.py` (`project_checks` members line), `perch/cli.py` (`init` warning)
- Modify: `perch/commands/walk.md`, `perch/commands/listen.md`, `CLAUDE.md`
- Tests: `perch/tests/test_config.py`, `test_steps.py`, `test_workspace.py`, `test_doctor.py`, `test_cli_projects.py`, `test_contract.py`

**Interfaces:**
- Consumes: gitboard `members [SPEC]` (Task 2); `steps.gitboard(..., project=)` (Task 5).
- Produces: `Config.unmatched: tuple[str, ...]` (member display names not in people.csv, sorted); `workspace.NAME_MAX = 255`, `workspace.NAME_SHORT = 100`, `workspace.name_too_long(name) -> bool`.

- [ ] **Step 1: Claim and branch** (perch recipe)

- [ ] **Step 2: Failing tests for the merge** (`perch/tests/test_config.py`)

The conftest world's people.csv has `Alice` and `Bob`, and its perch.yaml maps `asmith: Alice` and `bjones: Bob`.

```python
def _board(project_dir, people):
    board = project_dir / "board"
    board.mkdir(exist_ok=True)
    (board / f"{project_dir.name}.yaml").write_text(
        yaml.safe_dump({"project": "grp/x", "board": "B", "people": people})
    )


def test_board_members_fill_people_only_when_budgie_knows_the_name(tmp_path):
    home = build_home(tmp_path, "apollo")
    project = home.projects_dir / "apollo"
    _board(project, {"Bob": "bnew", "Manager Person": "boss", "Somebody": "asmith"})
    config = load_config(home.config_path("apollo"), require_dump=False)
    assert config.people["bnew"] == "Bob"
    assert "boss" not in config.people
    assert config.people["asmith"] == "Alice"  # perch.yaml wins
    assert config.unmatched == ("Manager Person",)


def test_no_board_yaml_means_no_members(tmp_path):
    home = build_home(tmp_path, "apollo")
    config = load_config(home.config_path("apollo"), require_dump=False)
    assert config.unmatched == ()
```

Run: FAIL.

- [ ] **Step 3: Implement in `perch/core/config.py`**

```python
from functools import lru_cache

BOARD_DIR = "board"
PEOPLE_CSV = "people.csv"


@lru_cache(maxsize=64)
def _yaml_people(path: Path, mtime: float) -> tuple[tuple[str, str], ...]:
    """(display name, username) pairs from a board YAML's people:, cached on mtime.

    ponytail: parses the whole board file once per change; read only the
    people: block if boards grow large enough for that to show.
    """
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return ()
    people = data.get("people") if isinstance(data, dict) else None
    if not isinstance(people, dict):
        return ()
    return tuple((str(name), str(user)) for name, user in people.items())


def _board_people(root: Path) -> tuple[tuple[str, str], ...]:
    """The pulled board's people: (projects/NAME/board/NAME.yaml), or ()."""
    path = root / BOARD_DIR / f"{root.name}.yaml"
    try:
        return _yaml_people(path, path.stat().st_mtime)
    except OSError:
        return ()


def _budgie_names(project: Path) -> set[str]:
    """The names in the Budgie project's people.csv, read with Budgie's own reader."""
    import csv

    from budgie.core.csvio import read_rows

    try:
        return {row["name"] for row in read_rows(project / PEOPLE_CSV, required={"name"})}
    except (OSError, ValueError, csv.Error):
        return set()
```

In `load_config`, replace the `people=` argument construction:

```python
    explicit = {str(user): str(name) for user, name in people.items()}
    members = [(n, u) for n, u in _board_people(root) if u not in explicit]
    known = _budgie_names(project) if members else set()
    matched = {u: n for n, u in members if n in known}
    unmatched = tuple(sorted(n for n, u in members if n not in known))
    return Config(
        ...,
        people={**matched, **explicit},
        ...,
        unmatched=unmatched,
    )
```

and add the field `unmatched: tuple[str, ...] = ()  # board-YAML members not in people.csv` to `Config`. (`root.name` is the project folder name, so the path matches `steps.spec_path`. `read_rows` raises `ValueError` for a missing column and `OSError` for a missing file; `csv.Error` covers a malformed one.)

Add `"budgie.core.csvio.read_rows"` usage to `perch/tests/test_contract.py` only if it is not already imported there (it is: `from budgie.core.csvio import ... read_rows`), so no change is needed beyond confirming.

Run the tests: PASS. Run the full suite: the conftest world has no board YAML, so nothing else changes.

- [ ] **Step 4: Failing tests: `perch gb members`**

`perch/tests/test_steps.py`:

```python
def test_gb_members_updates_the_pulled_board(tmp_path):
    home, config = apollo(tmp_path)
    spec = steps.spec_path(home, "apollo", config)
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("project: grp/apollo\nboard: B\n")
    step = steps.gb(home, "apollo", config, "members")
    assert step.argv == (str(home.venv_bin / "gitboard"), "members", str(spec))
    assert step.cwd == home.projects_dir / "apollo"


def test_gb_members_needs_a_pulled_board(tmp_path):
    home, config = apollo(tmp_path)
    with pytest.raises(WorkspaceError, match="perch gb pull -p apollo"):
        steps.gb(home, "apollo", config, "members")
```

Run: FAIL.

- [ ] **Step 5: Implement in `perch/core/steps.py`**

`GB_SUBS = (*GB_OFFLINE, "push", "pull", "sync", "members")` and update the comment above it to "push, pull, sync and members need GitLab". In `gb()`, after `path = spec_path(...)` and the `plan` check, add:

```python
    if sub == "members" and not path.is_file():
        raise WorkspaceError(f"{project}: no {path}; {pull_fix(project, path)}")
```

and add `"members": (spec,),` to the `target` table. Confirm `pull_fix` for a missing spec returns text containing `perch gb pull -p NAME`.

Run: PASS.

- [ ] **Step 6: Failing tests: name length**

`perch/tests/test_workspace.py`:

```python
def test_a_name_over_255_is_refused(tmp_path):
    with pytest.raises(WorkspaceError, match="255"):
        make_home(tmp_path).scaffold("a" * 256)


def test_name_too_long_is_over_100():
    from perch.core.workspace import name_too_long

    assert not name_too_long("a" * 100) and name_too_long("a" * 101)
```

`perch/tests/test_cli_projects.py`:

```python
def test_init_warns_about_a_long_name(tmp_path, monkeypatch):
    home = build_home(tmp_path)
    monkeypatch.chdir(home.root)
    fake_budgie_init(monkeypatch)
    result = run("init", "a" * 101)
    assert result.exit_code == 0, result.output
    assert "101 characters" in result.output and "under 100" in result.output
```

Run: FAIL.

- [ ] **Step 7: Implement**

`perch/core/workspace.py`:

```python
NAME_MAX = 255  # a path segment, and GitLab's own limit for names
NAME_SHORT = 100


def name_too_long(name: str) -> bool:
    """Legal, but long enough that every command line and table suffers."""
    return len(name) > NAME_SHORT


def check_name(name: str) -> str:
    """A project name is one plain path segment, so it can't leave projects/."""
    if not _NAME.fullmatch(name):
        raise WorkspaceError(
            f"{name!r} is not a project name: letters, digits, - and _ only"
        )
    if len(name) > NAME_MAX:
        raise WorkspaceError(
            f"a project name is at most {NAME_MAX} characters; this one is {len(name)}"
        )
    return name
```

`perch/cli.py` `init`, right after `check_name(name)`:

```python
        if name_too_long(name):
            console.print(
                f"{len(name)} characters: keep project names under {NAME_SHORT}; "
                "it shows in every command and table.",
                markup=False,
            )
```

(import `NAME_SHORT, name_too_long` with `check_name`.) Run: PASS.

- [ ] **Step 8: Doctor's members line — failing test, then code**

`perch/tests/test_doctor.py`:

```python
def test_unmatched_members_are_one_informational_line(tmp_path):
    home = build_home(tmp_path, "apollo")
    board = home.projects_dir / "apollo" / "board"
    board.mkdir(exist_ok=True)
    (board / "apollo.yaml").write_text(
        "project: grp/apollo\nboard: B\npeople:\n  Manager Person: boss\n"
    )
    checks = project_checks(home, "apollo")
    [line] = [c for c in checks if "GitLab member" in c.what]
    assert line.ok and "Manager Person" in line.what
```

In `project_checks`, after the `gitlab_project` check:

```python
    if config.unmatched:
        checks.append(
            Check(
                True,
                f"{name}: {len(config.unmatched)} GitLab member(s) not in people.csv, "
                f"left unmapped: {', '.join(config.unmatched)} (rename them in the "
                "board YAML's people: to match, or map them in perch.yaml)",
            )
        )
```

Run: PASS.

- [ ] **Step 9: Title guidance in `/walk` and `/listen`**

In `perch/commands/walk.md` and `perch/commands/listen.md`, in the rules for staging board edits, add one line each:

```
- Keep issue and milestone titles under 100 characters (GitLab refuses over 255); put the detail in the description.
```

`perch/tests/test_walk.py` may compare installed command text against these files; run it and update any golden it keeps.

- [ ] **Step 10: CLAUDE.md**

- `core/config.py` bullet: append "`people:` is perch.yaml's map plus each board-YAML member (`projects/NAME/board/NAME.yaml`, filled by `gitboard members`/pull) whose display name is in people.csv; perch.yaml wins; the rest are `Config.unmatched`, one informational doctor line."
- `core/steps.py` bullet: "`push`, `pull`, `sync` and `members` need GitLab" in place of the current three.
- `core/workspace.py` bullet: "names are at most 255 characters; `init` nudges under 100."

- [ ] **Step 11: Full suite, lint, commit, close**

```bash
PYTHONPATH=$WT:/Users/ryanadams/Documents/git/perch/apps/budgie ~/Documents/tools/perch/bin/pytest -q && ~/Documents/tools/perch/bin/ruff check .
git add -A -- . ':!apps' && git commit -m "feat: GitLab members fill people:, perch gb members, project-name length (perch-w41.6)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016Js49meT3psoy4w3dc8PdQ"
cd /Users/ryanadams/Documents/git/perch && bd close perch-w41.6 --reason "Config merges matched board members; gb members; check_name 255/100; title lines"
```

---

### Task 8: Land: real install, every suite, lint, docs, doctor

Bead `perch-w41.8`, wave 4, on the main checkouts after every branch above is merged.

- [ ] **Step 1: Claim; confirm every branch is merged**

```bash
cd /Users/ryanadams/Documents/git/perch && bd update perch-w41.8 --claim
for r in . apps/budgie apps/remote-gitboard; do git -C $r log --oneline -3; git -C $r branch --no-merged main; done
```

Expected: no `bead/perch-w41.*` branch listed as unmerged.

- [ ] **Step 2: The real install, over the old one**

```bash
ls -l ~/.local/bin/perch ~/.local/bin/budgie ~/.local/bin/gitboard 2>&1   # before
make install
ls -l ~/.local/bin/perch ~/.local/bin/budgie ~/.local/bin/gitboard        # all -> .../perch/.venv/bin/<tool>
head -3 .venv/bin/perch                                                   # the sh wrapper
.venv/bin/python -c "import perch, budgie, gitboard; print(perch.__file__, budgie.__file__, gitboard.__file__)"
```

Expected: the three paths are under the checkout (`perch/perch`, `apps/budgie/budgie`, `apps/remote-gitboard/src/gitboard`), not `site-packages`. `perch --help`, `budgie --help`, `gitboard --help` all exit 0. `ls -lO .venv/lib/python*/site-packages/*.pth` lists no `__editable__` file for perch, budgie or gitboard.

- [ ] **Step 3: Every suite, lint, docs**

```bash
make test-all && make lint && make docs
make -C apps/remote-gitboard lint
make -C apps/budgie lint
```

Expected: all green. If a failure appears, file it as a bead (`bd create ... --deps discovered-from:perch-w41.8`) and fix it on its own branch; do not edit around it here.

- [ ] **Step 4: Behaviour checks**

```bash
perch doctor                                  # each project: a token line; old venvs named with rm -rf lines
make -C apps/remote-gitboard -n clean | grep -c "perch/.venv"     # 0
cd /tmp && perch --help >/dev/null && echo ok  # runs from anywhere
```

For one real project with a token in `projects/NAME/.env`: `perch gb pull -p NAME` then `perch gb members -p NAME`, and confirm `people:` in `projects/NAME/board/NAME.yaml`. If no real token is available in this session, skip this check and leave it open in the handoff.

- [ ] **Step 5: Close out**

```bash
bd close perch-w41.8 --reason "make install over the old install, all suites, lint, docs, doctor verified"
bd close perch-w41 --reason "All children closed"
git status; git -C apps/budgie status; git -C apps/remote-gitboard status
```

Report: what changed per repo, what was verified, the old venvs doctor names (the lead deletes them), and that nothing was pushed.
