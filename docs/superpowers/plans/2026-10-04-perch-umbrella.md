# perch as the umbrella: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** perch becomes the one repo you clone; `scripts/bootstrap.sh` puts Budgie and gitboard in `perch/apps/` and installs all three; `~/Documents/git/pi_suite` goes away.

**Architecture:** Budgie and gitboard stay independent repos, cloned into perch's gitignored `apps/`. perch's Makefile defaults point there. Tasks 1-3 are code and doc changes in three different repos and run in parallel. Task 4 (the physical move) runs after 1-3 are merged and pushed, serially, in the lead's session, only on the lead's explicit go.

**Tech Stack:** POSIX sh, GNU make, pytest, git.

**Spec:** `docs/superpowers/specs/2026-10-04-perch-umbrella-design.md`

## Global Constraints

- Budgie clone URL: `git@github.com:adamsrnmsu/budgie.git` (private, ssh). gitboard: `https://github.com/adamsrnmsu/remote-gitboard.git`.
- App directories: `apps/budgie`, `apps/remote-gitboard` under the perch checkout.
- No `../` fallback in perch's Makefile.
- Venvs do not move: `~/Documents/tools/perch`, `~/Documents/tools/budgie`, gitboard's in-tree `.venv`.
- `gitboard_dir` stays explicit in `perch-home.yaml`; perch never derives it.
- Old specs and plans under `docs/superpowers/` are history: do not edit their paths.
- Never commit or push in `gitboard-promo`. Never touch `boards/test.yaml` in remote-gitboard.
- Commit on a `bead/<id>` branch in a worktree under the repo's `.claude/worktrees/<id>`; the lead's session merges and pushes.
- Commit messages end with:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01EEqcVBQVWTfDLxaeh7RUqV
  ```

## Review Focus

1. Bootstrap run from a directory other than perch's root: it must still clone into perch's own `apps/` (test pins it).
2. Bootstrap re-run after a successful run: no clone, no error, same output line (test pins it).
3. `apps/<name>` exists but is not a git checkout (an aborted copy): bootstrap stops and says so, rather than installing from junk (test pins it).
4. A clone fails (bad URL, no ssh key): bootstrap exits non-zero naming the app, and leaves no half-made `apps/<name>` (test pins it).
5. Fresh machine with no Budgie venv: `make install` must create it, not fail on a missing `pip` (Task 1 Makefile change; checked by hand in Task 4 is not possible on this machine, so the reviewer reads the recipe).

---

### Task 1: perch: apps/ layout, bootstrap script, docs

Repo: `perch`. Bead: given in the dispatch prompt.

**Files:**
- Modify: `.gitignore`
- Modify: `Makefile:1-20` (header comment, `BUDGIE_DIR`, `GB_DIR`), `Makefile` `install` recipe
- Create: `scripts/bootstrap.sh`
- Create: `perch/tests/test_bootstrap.py`
- Modify: `README.md` (Install section, `perch init` example, new "Layout and cross-repo work" section)
- Modify: `CLAUDE.md` (Commands block line for `make venv`, the "found beside this checkout" paragraph, the `../budgie` mention)
- Modify: `pyproject.toml:8` comment, `perch/core/workspace.py:4` docstring

**Interfaces:**
- Produces: `scripts/bootstrap.sh`, env `BUDGIE_URL`, `GB_URL`, `BOOTSTRAP_NO_INSTALL`; last stdout line is `  gitboard_dir: <perch>/apps/remote-gitboard`.

- [ ] **Step 1: Ignore apps/ first**

Append to `.gitignore`, in its own block after `.claude/worktrees/`:

```
# Budgie and gitboard checkouts, put here by scripts/bootstrap.sh. Their own
# repos; perch never records them.
apps/
```

Commit: `git add .gitignore && git commit -m "chore: ignore apps/, where bootstrap puts Budgie and gitboard"`

- [ ] **Step 2: Write the failing test**

`perch/tests/test_bootstrap.py`:

```python
"""scripts/bootstrap.sh: clones the two apps into apps/, and only once.

Runs the real script against throwaway local repos (file:// URLs) in a copy of
it, with the install step off, so nothing outside tmp_path is touched.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap.sh"


def _repo(path: Path) -> str:
    path.mkdir()
    git = ["git", "-C", str(path)]
    subprocess.run([*git, "init", "-q"], check=True)
    (path / "README.md").write_text("x\n")
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run(
        [*git, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"],
        check=True,
    )
    return path.as_uri()


@pytest.fixture
def perch(tmp_path):
    root = tmp_path / "perch"
    (root / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, root / "scripts" / "bootstrap.sh")
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "HOME": str(tmp_path),
        "BUDGIE_URL": _repo(tmp_path / "budgie-src"),
        "GB_URL": _repo(tmp_path / "gb-src"),
        "BOOTSTRAP_NO_INSTALL": "1",
    }
    return root, env


def _run(root, env, cwd):
    return subprocess.run(
        ["sh", str(root / "scripts" / "bootstrap.sh")],
        cwd=cwd, env=env, capture_output=True, text=True,
    )


def test_clones_both_apps_from_anywhere_and_names_gitboard_dir(perch, tmp_path):
    root, env = perch
    out = _run(root, env, cwd=tmp_path)  # not perch's root
    assert out.returncode == 0, out.stderr
    assert (root / "apps" / "budgie" / ".git").is_dir()
    assert (root / "apps" / "remote-gitboard" / ".git").is_dir()
    last = out.stdout.strip().splitlines()[-1]
    assert last == f"gitboard_dir: {root.resolve()}/apps/remote-gitboard"


def test_second_run_leaves_the_checkouts_alone(perch, tmp_path):
    root, env = perch
    assert _run(root, env, cwd=root).returncode == 0
    marker = root / "apps" / "budgie" / "local-edit"
    marker.write_text("mine\n")
    out = _run(root, env, cwd=root)
    assert out.returncode == 0, out.stderr
    assert "cloning" not in out.stdout
    assert marker.read_text() == "mine\n"


def test_an_app_dir_that_is_not_a_checkout_stops_it(perch):
    root, env = perch
    (root / "apps" / "budgie").mkdir(parents=True)
    out = _run(root, env, cwd=root)
    assert out.returncode != 0
    assert "apps/budgie" in out.stderr
    assert not (root / "apps" / "remote-gitboard").exists()


def test_a_failed_clone_names_the_app_and_leaves_nothing(perch, tmp_path):
    root, env = perch
    env = {**env, "GB_URL": (tmp_path / "missing").as_uri()}
    out = _run(root, env, cwd=root)
    assert out.returncode != 0
    assert "remote-gitboard" in out.stderr
    assert not (root / "apps" / "remote-gitboard").exists()
```

- [ ] **Step 3: Run it to see it fail**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_bootstrap.py -v`
Expected: 4 failures (`shutil.copy` raises FileNotFoundError: no `scripts/bootstrap.sh`).

- [ ] **Step 4: Write the script**

`scripts/bootstrap.sh` (then `chmod +x scripts/bootstrap.sh`):

```sh
#!/bin/sh
# Put Budgie and gitboard in apps/, then install and link all three.
# Safe to re-run: an app already in apps/ is left exactly as it is.
#   BUDGIE_URL=... GB_URL=...   clone from somewhere else
#   BOOTSTRAP_NO_INSTALL=1      clone only (the tests use this)
set -eu
PERCH_DIR=$(cd "$(dirname "$0")/.." && pwd)
BUDGIE_URL=${BUDGIE_URL:-git@github.com:adamsrnmsu/budgie.git}
GB_URL=${GB_URL:-https://github.com/adamsrnmsu/remote-gitboard.git}

fail() { echo "bootstrap: $*" >&2; exit 1; }

fetch() {  # fetch NAME URL
    dir="$PERCH_DIR/apps/$1"
    if [ -d "$dir/.git" ]; then
        echo "apps/$1: already there, left alone"
    elif [ -e "$dir" ]; then
        fail "apps/$1 exists but is not a git checkout; move it away and re-run"
    else
        echo "apps/$1: cloning $2"
        git clone -q "$2" "$dir" || fail "cloning $1 from $2 failed"
    fi
}

mkdir -p "$PERCH_DIR/apps"
fetch budgie "$BUDGIE_URL"
fetch remote-gitboard "$GB_URL"
if [ -z "${BOOTSTRAP_NO_INSTALL:-}" ]; then
    make -C "$PERCH_DIR" install link || fail "make install link failed"
fi
echo
echo "Put this line in your workspace's perch-home.yaml:"
echo "gitboard_dir: $PERCH_DIR/apps/remote-gitboard"
```

- [ ] **Step 5: Run the test to see it pass**

Run: `~/Documents/tools/perch/bin/pytest perch/tests/test_bootstrap.py -v`
Expected: 4 passed. If `test_a_failed_clone...` finds a leftover directory, `git clone` did not clean up after itself: add `rm -rf "$dir"` before `fail` in that branch.

- [ ] **Step 6: Makefile**

Replace the header comment lines 5-6 and the two defaults:

```make
# Budgie and gitboard live in apps/ (scripts/bootstrap.sh clones them there).
# Anywhere else:
#   make BUDGIE_DIR=/path/to/budgie GB_DIR=/path/to/remote-gitboard <target>
PERCH_DIR  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
BUDGIE_DIR ?= $(PERCH_DIR)/apps/budgie
GB_DIR     ?= $(PERCH_DIR)/apps/remote-gitboard
```

In `install`, Budgie's `install` target assumes its venv exists, so a fresh machine needs `venv` first. Replace the first recipe line with:

```make
	test -x $(BUDGIE_VENV)/bin/pip || $(MAKE) -C $(BUDGIE_DIR) venv VENV=$(BUDGIE_VENV)
	$(MAKE) -C $(BUDGIE_DIR) install VENV=$(BUDGIE_VENV)
```

Check: `make -n install BUDGIE_DIR=/x GB_DIR=/y | head -3` prints the `test -x` line, and `make -n install | head -3` shows `.../perch/apps/budgie`.

- [ ] **Step 7: Docs**

`README.md` Install section becomes:

````markdown
## Install

```bash
git clone https://github.com/adamsrnmsu/perch.git ~/Documents/git/perch
~/Documents/git/perch/scripts/bootstrap.sh
```

perch is the one repo you clone. `scripts/bootstrap.sh` clones Budgie and
gitboard into `apps/` (ignored by perch's git; each stays its own repo with its
own remote and beads), installs all three and puts `perch` and `gitboard` on
your PATH. It leaves an app already in `apps/` alone, so it is safe to re-run.
It ends by printing the `gitboard_dir:` line for your `perch-home.yaml`.

`pyproject.toml` pins Budgie to its GitHub repo by URL (never PyPI, where the
name is not ours), so `pip install` of perch works anywhere your SSH key can
reach the private repo. `make venv` then installs `apps/budgie` editable on top
(`BUDGIE_DIR=` to override), so local Budgie edits show up in perch at once.
````

In the `perch init` example: `--gitboard-dir ~/Documents/git/perch/apps/remote-gitboard`.

Add a section after "Moving a single-team setup in":

```markdown
### Layout and cross-repo work

    ~/Documents/git/perch/        this repo
      apps/budgie/                Budgie's repo (git@github.com:adamsrnmsu/budgie.git)
      apps/remote-gitboard/       gitboard's repo

Suite-level docs and decisions live in perch's `docs/`. A change that spans
repos is one perch epic with a child bead in each repo it touches, each
naming the epic; each repo is branched, merged and pushed on its own.
```

`CLAUDE.md`: Commands block `make venv` comment becomes `# ~/Documents/tools/perch; Budgie from GitHub, then apps/budgie`; the paragraph "The other apps are found beside this checkout..." becomes "Budgie and gitboard live in `apps/` (`scripts/bootstrap.sh` clones them; perch's git ignores them); `BUDGIE_DIR=` and `GB_DIR=` override that."; "`make venv` installs `../budgie` editable" becomes "`apps/budgie`".

`pyproject.toml:8`: `installs ../budgie editable` becomes `installs apps/budgie editable`.
`perch/core/workspace.py:4`: `~/Documents/git/pi_suite/remote-gitboard` becomes `~/Documents/git/perch/apps/remote-gitboard`.

Check nothing current-tense is left: `grep -rnE "pi_suite|\.\./budgie|\.\./remote-gitboard|beside this checkout" --exclude-dir=docs --exclude-dir=.venv --exclude-dir=.git --exclude-dir=.claude .` prints only test names about the `PI_SUITE` variable.

- [ ] **Step 8: Full check and commit**

Run: `make lint && make test`
Expected: ruff clean, all tests pass (previous count + 4).

```bash
git add Makefile scripts/bootstrap.sh perch/tests/test_bootstrap.py README.md CLAUDE.md pyproject.toml perch/core/workspace.py
git commit -m "feat: perch is the umbrella: bootstrap clones Budgie and gitboard into apps/"
```

---

### Task 2: budgie: tidy

Repo: `budgie`. Bead: given in the dispatch prompt.

**Files:**
- Delete (untracked): `docs/superpowers/specs/2026-10-02-one-model-design 2.md`, `docs/superpowers/specs/2026-10-02-ux-review 2.md`
- Modify: `docs/_static/hacker.css:4`, `docs/conf.py:26`

- [ ] **Step 1: Delete the duplicates, only if still identical**

These are untracked files in the main checkout, not the worktree. From the main checkout:

```bash
cd /Users/ryanadams/Documents/git/pi_suite/budgie/docs/superpowers/specs
cmp "2026-10-02-one-model-design 2.md" 2026-10-02-one-model-design.md && rm "2026-10-02-one-model-design 2.md"
cmp "2026-10-02-ux-review 2.md" 2026-10-02-ux-review.md && rm "2026-10-02-ux-review 2.md"
```

If `cmp` reports a difference, do not delete; report the diff.

- [ ] **Step 2: Doc wording (in the worktree)**

`docs/_static/hacker.css:4`: `Shared by the Sphinx docs of the pi_suite repos (budgie, remote-gitboard).` becomes `Shared by the Sphinx docs of the pi apps (budgie, remote-gitboard).`
`docs/conf.py:26`: `The shared pi_suite terminal skin` becomes `The shared pi apps terminal skin`.
Leave test names that mention `pi_suite`: they are about the `PI_SUITE` variable, which keeps its name.

- [ ] **Step 3: Check and commit**

Run: `make lint && make test` (Budgie's venv is `~/Documents/tools/budgie`). Expected: clean, all pass.

```bash
git add docs/_static/hacker.css docs/conf.py
git commit -m "docs: say pi apps, not pi_suite, in the shared docs skin"
```

---

### Task 3: remote-gitboard: laya-bench result, tidy, dead worktrees

Repo: `remote-gitboard`. Bead: given in the dispatch prompt.

**Files:**
- Create: `docs/laya-bench.md`
- Modify: `docs/_static/hacker.css:4`, `docs/conf.py:25`
- Remove: `.claude/worktrees/{milestone-horizon,blockers-graph,gb-2sj,small-fixes}` (untracked, after checks)
- Do not touch: `boards/test.yaml`

- [ ] **Step 1: laya-bench result as a doc**

Read `/Users/ryanadams/Documents/git/pi_suite/laya-bench/README.md` and `/Users/ryanadams/Documents/git/pi_suite/laya-bench/results/report.md`. Write `docs/laya-bench.md`: a one-paragraph header saying what was measured (does the Laya model pick an issue's `type::` label faster or better than Claude), that the code was deleted on 2026-10-04 when pi_suite was dissolved, and that the conclusion stands (Laya was less accurate than every Claude run); then the README's result and method sections verbatim; then `report.md` verbatim under `## Full report`. If the docs have a toctree that lists every page (check `docs/index.*`), add it there; otherwise do not.

- [ ] **Step 2: Doc wording**

`docs/_static/hacker.css:4`: `pi_suite repos` becomes `pi apps`. `docs/conf.py:25`: `pi_suite terminal skin` becomes `pi apps terminal skin`.

- [ ] **Step 3: Check and commit**

Run: `make lint && make test && make docs`. Expected: clean, pass, docs build with no warnings.

```bash
git add docs/laya-bench.md docs/_static/hacker.css docs/conf.py
git commit -m "docs: keep the laya-bench result; say pi apps in the docs skin"
```

- [ ] **Step 4: Dead worktrees (main checkout, after the commit)**

From `/Users/ryanadams/Documents/git/pi_suite/remote-gitboard`:

1. `milestone-horizon`: registered and locked by pid 8047. Confirm `ps -p 8047` finds nothing and `git log origin/main..worktree-test-slim` is empty. Then `git -C .claude/worktrees/milestone-horizon status --porcelain`: if anything is listed, stop and report it. Else `git worktree unlock .claude/worktrees/milestone-horizon && git worktree remove .claude/worktrees/milestone-horizon`.
2. `blockers-graph`, `gb-2sj`, `small-fixes`: not working worktrees. For each, list every file that is not in `git ls-tree -r --name-only origin/main` or differs from it (`diff -rq` against a `git archive origin/main | tar -x -C <tmpdir>` export, ignoring `.git`, `.venv`, caches and `.beads`). Report the list. Remove a directory only if that list is empty; otherwise leave it and report.
3. `git worktree prune`, then `git worktree list` shows only the main checkout (and your own task worktree until it is removed).

Report `git diff --stat boards/test.yaml` in your hand-back; do not change it.

---

### Task 4: Migration (lead's session, serial, on the lead's go)

Not for a subagent. Runs after Tasks 1-3 are reviewed, merged to main and pushed in all three repos. Every command uses absolute paths; the shell's cwd is `~/Documents/git`, never inside `pi_suite`.

- [ ] **Step 1: Preconditions.** `ps -axo pid,command | grep -i claude` and `lsof +D /Users/ryanadams/Documents/git/pi_suite 2>/dev/null | grep -v "^COMMAND"`: no other session in pi_suite. In each repo: `git status --porcelain` empty except `boards/test.yaml` (gitboard) and ignored files; `git fetch && git log origin/main..main` empty; `git worktree list` shows only the main checkout. Remove the merged `bead/*` worktrees first (`git worktree remove`), so none moves with a dead gitdir.
- [ ] **Step 2: Move.** `mv /Users/ryanadams/Documents/git/pi_suite/perch /Users/ryanadams/Documents/git/perch`, then `mkdir -p /Users/ryanadams/Documents/git/perch/apps && mv /Users/ryanadams/Documents/git/pi_suite/budgie /Users/ryanadams/Documents/git/pi_suite/remote-gitboard /Users/ryanadams/Documents/git/perch/apps/`. Check `git -C /Users/ryanadams/Documents/git/perch status --porcelain` does not list `apps/`.
- [ ] **Step 3: Repair.** `git worktree prune` in all three repos.
- [ ] **Step 4: Reinstall.** `rm -rf /Users/ryanadams/Documents/git/perch/apps/remote-gitboard/.venv`, then `make -C /Users/ryanadams/Documents/git/perch install link`. Check `head -3 ~/.local/bin/gitboard` names the new path and `readlink ~/.local/bin/perch` resolves.
- [ ] **Step 5: Workspace.** Rewrite `gitboard_dir:` in `/Users/ryanadams/Documents/git/perch/perch-home.yaml` to `/Users/ryanadams/Documents/git/perch/apps/remote-gitboard`. Grep any other `perch-home.yaml` the lead uses (`$PERCH_HOME`) for `pi_suite` and fix the same way.
- [ ] **Step 6: Leftovers.** `mv /Users/ryanadams/Documents/git/pi_suite/gitboard-promo /Users/ryanadams/Documents/git/gitboard-promo` (no git). Confirm `docs/laya-bench.md` is on gitboard's origin/main, then `rm -rf /Users/ryanadams/Documents/git/pi_suite/laya-bench`. Remove `.DS_Store` if present. `rmdir /Users/ryanadams/Documents/git/pi_suite`: if it fails, stop and look.
- [ ] **Step 7: Claude memory.** Copy `~/.claude/projects/-Users-ryanadams-Documents-git-pi-suite/memory/` to `~/.claude/projects/-Users-ryanadams-Documents-git-perch/memory/`; in the copies replace `pi_suite/gitboard-promo` with `~/Documents/git/gitboard-promo` and `pi_suite` (the folder) with `perch` (umbrella), and say the apps live in `perch/apps/`.
- [ ] **Step 8: Verify.** `make -C /Users/ryanadams/Documents/git/perch test-all`; `perch doctor` from the workspace; `which perch gitboard budgie`; `bd ready` in all three repos; `perch tui` and hop P/B/G once (by the lead, in a real terminal). Act on any FIX lines `perch doctor` prints for the workspace's walk files (`.claude/commands/walk.md`, `additionalDirectories` in `.claude/settings.json`), which may still name pi_suite.
- [ ] **Step 9: Record.** In perch: `bd remember` the decision (perch is the umbrella; apps in `apps/`; cross-repo = perch epic + child bead per repo); close perch-wyj with the reason; the lead restarts Claude in `~/Documents/git/perch`.
