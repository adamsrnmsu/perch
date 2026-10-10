# Simplify and Listen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One checkout is home with one install path, gitboard can close issues and drop columns from the board file, every issue has one shape, and `perch listen` turns a meeting transcript into staged board edits.

**Architecture:** Deletion first (workspace file, env overrides, pip routes). gitboard (W3) gains `closed:` and column-drop rows plus explicit path flags; perch (W1) passes those flags and owns the layout `projects/NAME/{board,budget,reports,listen}`. `/listen` is a Claude slash command that edits the board YAML like `/walk`; nothing reaches GitLab until `perch gb sync`.

**Tech Stack:** Python 3, click, Textual, pytest, ruff, sh, Sphinx (shibuya theme), git, `bd`.

**Spec:** `docs/superpowers/specs/2026-10-09-simplify-and-listen-design.md` (read it first; this plan does not repeat its prose).

## Global Constraints

- perch owns only the join and the views: never calls GitLab, never edits the board itself, never sends anything, never ranks people. gitboard owns every board write.
- `perch/core/` is UI-free (no click, no rich); `cli.py` imports engines inside commands.
- Home is `Path(perch.__file__).resolve().parents[1]`, must contain `pyproject.toml` and `apps/`; error text exactly `perch is not running from a checkout: run make install in your perch clone`.
- Clone URLs are fixed HTTPS constants: `https://github.com/adamsrnmsu/budgie.git`, `https://github.com/adamsrnmsu/remote-gitboard.git`. Pin `budgie @ git+https://github.com/adamsrnmsu/budgie.git`.
- Removed with no replacement: `perch-home.yaml`, `$PERCH_HOME`, `gitboard_dir` key, `create_home`, `init --home`, `init --gitboard-dir`, `HOME_NAME`/`HOME_ENV`, `BUDGIE_DIR`, `GB_DIR`, `BUDGIE_URL`, `GB_URL`, `BOOTSTRAP_NO_INSTALL`, `make venv`, `pull --base`, `plan --base`.
- Fixed columns `Verify`, `Done`, `Failed` can never be dropped; a drop needs a `.base`; the dropped column keeps its label.
- License: MIT, `Copyright (c) 2026 Ryan Adams`, `license = "MIT"` in all three `pyproject.toml`.
- Issue template fields, in order: Goal, Done when, Context, Out of scope, Links. Card footer: `Source: meeting · LEAD · YYYY-MM-DD`.
- Commands: perch tests `~/Documents/tools/perch/bin/pytest`; all three repos `make test-all`; lint `make lint`; docs `make docs` (`sphinx -W`).
- Beads: every task names its bead; `bd update <id> --claim` on start, `bd close <id> --reason "..."` at the end. Conservative profile: commits happen on the `bead/<id>` branch in the worktree; no push unless the orchestrator says so.
- No grep test over docs (the airgap exception, "do not" text and migration section legitimately contain removed strings).

## Execution Model

Each workstream runs in its own git worktree per repo, branch `bead/<id>`, merged to that repo's `main` on its own.

| Lane | Repo | Order |
|---|---|---|
| A | perch (`~/Documents/git/perch`) | W2 (perch-62i) -> W1 (perch-gkl) -> W5 (perch-efj) |
| B | remote-gitboard (`apps/remote-gitboard`) | W3 (perch-bkz) and W4 (perch-03n) in parallel with A |
| B | budgie (`apps/budgie`) | W2 budgie task, W4 budgie task |
| last | all | W6 docs (perch-7ux) |

Hard dependencies: W1 needs W3 merged (path flags); W5 needs W1, W3, W4 merged; W6 needs everything.

**Child beads in other databases.** remote-gitboard and budgie have their own `bd` databases. Before starting, create these (each description must say `Part of perch epic perch-i51`, and name the perch bead):

```bash
cd ~/Documents/git/perch/apps/remote-gitboard
bd create "W3 closed/drop-column/path flags (perch-bkz)" -d "Part of perch epic perch-i51. See perch docs/superpowers/specs/2026-10-09-simplify-and-listen-design.md W3." -t feature
bd create "W2 install: HTTPS, LICENSE, README (perch-62i)" -d "Part of perch epic perch-i51. Spec W2." -t task
bd create "W4 issue template copy (perch-03n)" -d "Part of perch epic perch-i51. Spec W4." -t task
cd ../budgie
bd create "W2 install: README, CLAUDE.md, docs, pyproject (perch-62i)" -d "Part of perch epic perch-i51. Spec W2." -t task
bd create "W4 issue template copy (perch-03n)" -d "Part of perch epic perch-i51. Spec W4." -t task
```

Tasks below that run in those repos say "child bead in remote-gitboard" or "child bead in budgie"; they claim and close that child, and the perch bead is closed only after every child is closed.

**Worktree gotcha.** Inside a perch worktree `apps/` is missing (gitignored). Create the worktree, then symlink or clone apps, and always pass absolute paths:

```bash
git -C ~/Documents/git/perch worktree add ../perch-wt/<id> -b bead/<id>
cd ../perch-wt/<id> && ln -s ~/Documents/git/perch/apps apps   # only if the task needs apps/ (W1, W5, contract test)
```

Until W2 lands, `make venv BUDGIE_DIR=/abs/path/apps/budgie GB_DIR=/abs/path/apps/remote-gitboard` and `make test BUDGIE_DIR=... GB_DIR=...` take absolute paths. After W2 the variables are gone and `make install` is run from the main checkout (it is the home); in a worktree run `~/Documents/tools/perch/bin/pytest perch/tests` directly. Note W1 tests use a tmp checkout, never the real `apps/`.

## Review Focus

- `config.yaml` with `lead:` but a non-string value (`lead: 5`) or empty: error naming the key, not a crash (Task 1.1).
- Transcript with CRLF line endings or a UTF-8 BOM: the lead's cues still match (Task 5.1).
- Transcript speaker `<v Ryan Adams>` where config says `Ryan`: stops with the "check the speaker name" message, never a silent partial match (Task 5.1).
- Project name that is not the last GitLab segment (`projects/apollo` for `group/sub/apollo-api`): spec path uses the folder name (Task 1.2).
- `closed: true` plus a column drop in one file, with the closed issue's card in the dropped column: plan shows both, push closes first then drops (Task 3.3).
- Old `perch-home.yaml` found above cwd while a destination already exists: doctor names it and omits the `mv` (Task 1.5).
- Re-running `perch listen` twice on the same day: `-2` file, no overwrite (Task 5.1).

---

# Lane B: remote-gitboard

## W3 gitboard (bead perch-bkz; child bead in remote-gitboard)

Worktree: `git -C ~/Documents/git/perch/apps/remote-gitboard worktree add ../../../perch-wt/gb-bkz -b bead/<child-id>` (use the child bead id in the branch name). Tests: that repo's own pytest (see its `CLAUDE.md`; `make test` there). Lint: `make lint`.

### Task 3.1: `closed: true` validated and planned

**Files:** Modify `src/gitboard/apply.py` (`load`, `diff`, `order_changes`); Test `tests/test_apply.py`.

**Interfaces:** Produces: plan row kind `closed` with text `closed issue TITLE (closed from the board file)`; `load` raises `SpecError` when `closed` is not a bool.

- [ ] **Step 1: Failing tests** in `tests/test_apply.py`:

```python
def test_closed_true_plans_a_closed_row():
    spec = load_text(BOARD_WITH_ISSUE + "    closed: true\n")
    rows = diff(spec, have_issue("Fix login"))
    assert [r.kind for r in rows if "Fix login" in r.text] == ["closed"]
    assert "closed from the board file" in rows[-1].text

def test_closed_must_be_a_bool():
    with pytest.raises(SpecError, match="closed"):
        load_text(BOARD_WITH_ISSUE + "    closed: yes please\n")

def test_closed_entry_does_not_break_order():
    spec = load_text(TWO_ISSUES_ORDERED_ONE_CLOSED)
    order_changes(spec, have_two())  # must not raise or emit a move for the closed one

def test_omitting_an_issue_still_deletes_nothing():
    rows = diff(load_text(BOARD_WITHOUT_ISSUE), have_issue("Fix login"))
    assert not any("Fix login" in r.text for r in rows)
```

(Use the file's existing helpers for building specs and `have`; name them as they exist, read the top of `test_apply.py` first. `FakeBoard`/`FakeList` are in `test_migrate.py`.)

- [ ] **Step 2:** Run `pytest tests/test_apply.py -k closed -v`. Expected: FAIL.
- [ ] **Step 3:** In `load`, accept `closed` only as `bool` (`SpecError(f"issue {title!r}: closed must be true or false")`). In `diff`, emit a `closed` row for each issue with `closed: true` (text above). In `order_changes` and `diff` ordering skip entries with `closed`.
- [ ] **Step 4:** Run `pytest tests/test_apply.py -v`. Expected: PASS.
- [ ] **Step 5:** Commit `feat: closed: true plans a closed row (perch-bkz)`.

**Done when:** the three tests pass and removing an issue from the file still plans nothing (`test_omitting_an_issue_still_deletes_nothing` passes).

### Task 3.2: push closes with a note; skipped rows

**Files:** Modify `src/gitboard/apply.py` (`close_issue`, `ensure_issues`, new `_close`); Test `tests/test_apply.py`.

**Interfaces:** Produces `_close(issue, note: str) -> None` (adds note with the `MARKER` line plus `Closed from the board file by gitboard.`, then state event close); `ensure_issues` closes on `closed: true` and removes the entry from `live`.

- [ ] **Step 1: Failing tests:**

```python
def test_close_writes_note_and_state_event():
    issue = FakeIssue(state="opened")
    _close(issue, "Closed from the board file by gitboard.")
    assert issue.state_event == "close"
    assert MARKER in issue.notes[0] and "Closed from the board file by gitboard." in issue.notes[0]

def test_closed_true_on_absent_or_closed_is_skipped():
    rows = diff(spec_closed("Gone"), have_without("Gone"))
    assert [r.kind for r in rows if "Gone" in r.text] == ["skipped"]
```

- [ ] **Step 2:** Run, expect FAIL.
- [ ] **Step 3:** Extract `_close` from `close_issue`; `close_issue` calls it with its existing note text. `ensure_issues` calls `_close(issue, "Closed from the board file by gitboard.")` for `closed: true` issues that are open, and a `skipped` row when absent or already closed.
- [ ] **Step 4:** Run `pytest tests/test_apply.py -v`, PASS.
- [ ] **Step 5:** Commit `feat: push closes issues from the board file (perch-bkz)`.

**Done when:** both tests pass; `close_issue` behaviour unchanged (existing tests green).

### Task 3.3: column drop rows and apply

**Files:** Modify `src/gitboard/apply.py` (`have_from_spec`, `plan`, `diff`, `apply`); Test `tests/test_apply.py`.

**Interfaces:** Produces `oneway` row `drop_column NAME (N cards)`; `skipped` row `list already gone`; offline `have['lists']` = `have_from_spec(base).columns`; live = GitLab lists intersected with `base.columns`. Drop set = `base.columns - spec.columns`. `SpecError("column Done is fixed and cannot be dropped")` for `Verify`/`Done`/`Failed`.

- [ ] **Step 1: Failing tests:**

```python
def test_removed_column_plans_a_drop_row_with_base():
    rows = plan_with_base(spec_cols(["Todo"]), base_cols(["Todo", "Review"]))
    assert any(r.kind == "oneway" and r.text.startswith("drop_column Review") for r in rows)

def test_removed_column_without_base_plans_nothing():
    rows = plan_no_base(spec_cols(["Todo"]))
    assert not any("drop_column" in r.text for r in rows)

def test_dropping_done_is_refused():
    with pytest.raises(SpecError, match="column Done is fixed and cannot be dropped"):
        plan_with_base(spec_cols(["Todo"]), base_cols(["Todo", "Done"]))

def test_drop_keeps_the_label():
    board = FakeBoard(lists=["Todo", "Review"], labels=["Review"])
    apply_drop(board, "Review")
    assert "Review" in board.labels and "Review" not in [l.name for l in board.lists]

def test_closed_and_drop_in_one_push_close_first():
    log = apply_with_log(spec_closed_and_dropped())
    assert log.index("close") < log.index("drop_list")
```

(Real helper names come from `test_apply.py` and `test_migrate.py`; reuse `FakeBoard`/`FakeList`.)

- [ ] **Step 2:** Run, FAIL.
- [ ] **Step 3:** Implement. `apply` gains a drop step after `ensure_board`: for each name in the drop set present on GitLab call `lst.delete()` directly (`migrate.py` untouched). Name absent on GitLab: `skipped`/`list already gone`. A GitLab list not in the base is never dropped.
- [ ] **Step 4:** `pytest tests/test_apply.py tests/test_migrate.py -v`, PASS (existing migrate `drop_column` tests unchanged).
- [ ] **Step 5:** Commit `feat: removing a column from the file drops its list (perch-bkz)`.

**Done when:** all five tests pass.

### Task 3.4: cli rows, `pull` always writes `.base`, remove `--base`, `sync` pull-first

**Files:** Modify `src/gitboard/cli.py` (`SIGN`, `STYLE`, `_confirm_writes`, `_review_first`, `_pull_board`, `pull`, `plan`, `sync`, docstrings), `src/gitboard/doctor.py:124`, `src/gitboard/tui.py` (`e` writes `.base`, `f` call, key help), `src/gitboard/guide.py` (`GUIDE['a']`); Test `tests/test_cli.py`.

- [ ] **Step 1: Failing tests** (names from the spec): `test_push_with_only_a_closed_row_writes`, `test_push_with_only_a_drop_row_writes`, `test_pull_always_writes_base`, `test_pull_has_no_base_option` (`pull --base x` exits 2 with "No such option"), `test_sync_missing_file_pulls_first`, `test_sync_missing_file_without_project_errors` (message `no such board file PATH; give --project GROUP/PROJECT to pull it first`), TUI `e` writes `.base`, and `test_pull_omits_closed_issues_and_base_matches` (after `closed: true` was pushed and GitLab shows the issue closed, `pull` writes neither the issue to the file nor to the `.base`, so the next plan has no `closed` row; a `closed: true` entry still in the file against a closed issue plans `skipped`). Update the exact `SIGN`/`STYLE` set test. Update tests near `test_cli.py` :151, :154, :176, :337, :1431, :1532 that pass `--base` or expect no `.base`.
- [ ] **Step 2:** `pytest tests/test_cli.py -v`, FAIL on the new ones.
- [ ] **Step 3:** Implement. `_confirm_writes` counts `closed` and `oneway` drop rows as writes; `_review_first` sorts them first; `pull` rotates old `.base` to `.base.old`, always writes `<spec>.base`, and omits closed issues from both the file and the `.base` (check first whether `pull` already skips closed issues; if so the test only pins it); `plan --base` and `pull --base` deleted (only base is `<spec>.base`); messages say `gitboard pull`; doctor fix text `gitboard pull PROJECT --force`; `sync SPEC --project PATH` pulls first when SPEC is absent.
- [ ] **Step 4:** `pytest -v` (whole repo) and `make lint`, PASS.
- [ ] **Step 5:** Commit `feat: pull always writes .base; sync pulls first (perch-bkz)`.

**Done when:** whole gitboard suite and lint green.

### Task 3.5: path flags `--log`, `--spec`, `--db`, `--boards-dir`

**Files:** Modify `src/gitboard/cli.py`, `src/gitboard/stats.py` (`_summary`, `_weekly`), `src/gitboard/tui.py` (`_write_snapshot` calls in `e`/`f`); Test `tests/test_cli.py`.

**Interfaces:** Produces the flags W1 passes: `--log` on `stats` (incl. `--weeks`) and `digest`; `--spec` on `stats`, `digest`; `--db` on push, pull, sync, report, status, show, replay, tui; `--boards-dir` on status, show, tui, digest and the `--all` forms (`local_specs`/`find_spec` honour it); `snapshot` keeps `--out`; `_write_snapshot(proj, board, db)`.

- [ ] **Step 1: Failing tests:** `test_stats_log_and_spec_flags` (run `stats --dump d.json --log L --spec S` in a tmp dir; assert L is written and the cwd's `reports/stats.jsonl` is not), `test_digest_uses_log_flag`, `test_status_boards_dir` (a board under tmp `--boards-dir` is found; `boards/` in cwd is ignored), `test_report_db_flag` (snapshots read from `--db`).
- [ ] **Step 2:** Run, FAIL (no such option).
- [ ] **Step 3:** Add options; default to the current hard-coded paths so behaviour without flags is unchanged. Thread `db` through `_write_snapshot`.
- [ ] **Step 4:** `pytest -v` and `make lint`, PASS.
- [ ] **Step 5:** Commit `feat: explicit path flags for log, spec, db, boards-dir (perch-bkz)`.

**Done when:** a command run with all four flags touches nothing under gitboard's own `boards/`, `reports/`, `snapshots.jsonl` (asserted in the tests).

### Task 3.6: gitboard docs and `board.md`

**Files:** Modify `README.md`, `CLAUDE.md`, `src/gitboard/CLAUDE.md`, `docs/index.md`, `docs/board-yaml.md` (keys table: `closed`; invariants: a file edit never deletes an issue, `closed: true` closes, a removed column drops its list and keeps the label, milestones additive), `docs/commands.md`, `docs/migrations.md`, `docs/airgap.md`, `.claude/commands/board.md` (remove "never close"; edit "the file named in the prompt" instead of `boards/*.yaml`), `.gitignore` comment.

- [ ] **Step 1:** `grep -rn "additive\|--base\|never close" README.md CLAUDE.md src/gitboard/CLAUDE.md docs .claude` and list hits.
- [ ] **Step 2:** Rewrite each hit to the new invariants.
- [ ] **Step 3:** Run the repo's docs build if it has one (`make docs`) and the full suite plus `make lint`.
- [ ] **Step 4:** Commit `docs: closed, drop column, no --base (perch-bkz)`. The W4 template block is added to `board.md` in Task 4.2.

**Done when:** no remaining claim of additive-only or `--base` outside labelled history; suite green. Close child bead and merge `bead/<id>` to gitboard `main`; then close perch-bkz.

## W4 Issue template (bead perch-03n)

### Task 4.1: canonical template in perch and its match test

**Repo:** perch (lane A worktree is fine; no dependency). **Files:** Create `.github/ISSUE_TEMPLATE/task.md`; Test `perch/tests/test_issue_template.py`.

- [ ] **Step 1: Failing test:**

```python
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
REL = ".github/ISSUE_TEMPLATE/task.md"

def test_issue_template_has_fields_in_order():
    text = (ROOT / REL).read_text()
    pos = [text.index(f) for f in ("Goal:", "Done when:", "Context:", "Out of scope:", "Links:")]
    assert pos == sorted(pos)

@pytest.mark.parametrize("app", ["remote-gitboard", "budgie"])
def test_issue_template_copies_match(app):
    copy = ROOT / "apps" / app / REL
    if not copy.exists():
        pytest.skip(f"apps/{app} has no template yet")
    assert copy.read_text() == (ROOT / REL).read_text()
```

- [ ] **Step 2:** `~/Documents/tools/perch/bin/pytest perch/tests/test_issue_template.py -v`; FAIL (file missing).
- [ ] **Step 3:** Create the file:

```markdown
---
name: Task
about: One page, fixed fields
---

Goal: one line, what changes for whom
Done when:
- [ ] checkable outcome
Context:
- one-line fact or constraint
Out of scope:
- one line
Links:
- URL or #iid
```

- [ ] **Step 4:** Run, PASS (copies skip or match).
- [ ] **Step 5:** Commit `feat: one-page issue template (perch-03n)`.

**Done when:** tests pass.

### Task 4.2: copies in remote-gitboard and budgie, and the `board.md` block

**Repos:** remote-gitboard (child bead in remote-gitboard, W4) and budgie (child bead in budgie, W4); separate worktrees and commits. **Files:** Create `.github/ISSUE_TEMPLATE/task.md` in each (byte-identical to the perch copy: `cp`); Modify gitboard `.claude/commands/board.md` (rules for a new card's `description:`: the template block, then `Source: meeting · LEAD · YYYY-MM-DD` footer in `ingest.footer_line` grammar `Source: src · person · date`). Do this edit after Task 3.6 merges, or on the W3 branch, so `board.md` has one owner (W3).

- [ ] **Step 1:** In each repo `mkdir -p .github/ISSUE_TEMPLATE && cp ~/Documents/git/perch/.github/ISSUE_TEMPLATE/task.md .github/ISSUE_TEMPLATE/task.md`.
- [ ] **Step 2:** Edit `board.md` as above (gitboard only).
- [ ] **Step 3:** Run each repo's tests; in perch run `~/Documents/tools/perch/bin/pytest perch/tests/test_issue_template.py -v` (now compares, not skips).
- [ ] **Step 4:** Commit in each repo `feat: one-page issue template (perch-03n)`.

**Done when:** `test_issue_template_copies_match` passes for both apps with no skip. Close both child beads and perch-03n.

## W2 install, gitboard and budgie halves (bead perch-62i)

### Task 2.3: remote-gitboard install story

**Child bead in remote-gitboard (W2).** **Files:** Create `LICENSE` (MIT, `Copyright (c) 2026 Ryan Adams`); Modify `pyproject.toml` (`license = "MIT"`), `README.md`, `docs/install.md`, `docs/development.md`, `CLAUDE.md`.

- [ ] **Step 1:** Add LICENSE and the pyproject line; run `python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['license'])"`; expect `MIT`.
- [ ] **Step 2:** Rewrite install text to point at perch: `git clone https://github.com/adamsrnmsu/perch.git && cd perch && make install`. Remove the pip/pipx install options and `VENV=` sentences; keep the `PYTHONPATH=src` rule as a "do not"; keep the airgap route only as the labelled airgap exception.
- [ ] **Step 3:** Run the repo's tests, `make lint`, and docs build if present.
- [ ] **Step 4:** Commit `docs: install through perch; MIT license (perch-62i)`.

**Done when:** tests green; the only remaining pip route is labelled airgap.

### Task 2.4: budgie install story

**Child bead in budgie (W2).** **Files:** Modify `pyproject.toml` (`license = "MIT"`), `README.md`, `CLAUDE.md`, `docs/architecture.md`. Budgie's CI workflow is left alone; no Budgie code changes.

- [ ] **Step 1:** Add the license line; verify with the tomllib one-liner above.
- [ ] **Step 2:** Remove the "by hand" block and macOS `.pth` note; point installs at the perch path.
- [ ] **Step 3:** Run Budgie's tests and lint.
- [ ] **Step 4:** Commit `docs: install through perch (perch-62i)`.

**Done when:** tests green. Then in perch run `~/Documents/tools/perch/bin/pytest perch/tests/test_contract.py` (rerun after any Budgie change).

---

# Lane A: perch

## W2 install (bead perch-62i, perch half)

Worktree `bead/perch-62i`. Uses absolute `BUDGIE_DIR`/`GB_DIR` only until this task removes them.

### Task 2.1: bootstrap is clone-only over fixed HTTPS URLs; Makefile `install` calls it

**Files:** Modify `scripts/bootstrap.sh`, `Makefile`, `pyproject.toml`; Test `perch/tests/test_bootstrap.py`.

**Interfaces:** Produces `make install` = `bootstrap` then venv + editable installs (`[dev,docs]`) + `link`. No `make venv`, no `BUDGIE_DIR`/`GB_DIR`/`BUDGIE_URL`/`GB_URL`.

- [ ] **Step 1: Failing tests.** Update `test_bootstrap.py`: the helper sets `GIT_CONFIG_COUNT=2`, `GIT_CONFIG_KEY_0=url.<local budgie>.insteadOf`, `GIT_CONFIG_VALUE_0=https://github.com/adamsrnmsu/budgie.git`, and the same pair `_1` for remote-gitboard. Rename/keep `test_clones_both_apps_from_anywhere` (drop the `gitboard_dir` assertion), `test_second_run_leaves_the_checkouts_alone`, `test_an_app_dir_that_is_not_a_checkout_stops_it`, `test_a_failed_clone_names_the_app_and_leaves_nothing`. Add:

```python
def test_bootstrap_does_not_run_make():
    assert "make " not in Path("scripts/bootstrap.sh").read_text()
    assert "BOOTSTRAP_NO_INSTALL" not in Path("scripts/bootstrap.sh").read_text()
```

- [ ] **Step 2:** `~/Documents/tools/perch/bin/pytest perch/tests/test_bootstrap.py -v`; FAIL.
- [ ] **Step 3:** In `bootstrap.sh` replace the two URL variables with constants (HTTPS), delete the `BOOTSTRAP_NO_INSTALL` block and the trailing `perch-home.yaml`/`gitboard_dir` echo lines (header comment updated). In `Makefile`: delete the `?=` and `override :=` dir variables and the `venv` target (also from `.PHONY`, `help` text and the header comment); add `install: bootstrap` as first prerequisite, make the existing `install` recipe install `'$(PERCH_DIR)[dev,docs]'`, and rewrite every recipe that uses `$(BUDGIE_DIR)`/`$(GB_DIR)` (`install`, `link`, `test`, `test-all`, `docs`, `clean`) to literal `$(PERCH_DIR)/apps/budgie` and `$(PERCH_DIR)/apps/remote-gitboard` (define those two as plain `:=` constants, not overridable). In `pyproject.toml`: pin `budgie @ git+https://github.com/adamsrnmsu/budgie.git` and `license = "MIT"`.
- [ ] **Step 4:** Run bootstrap tests, then `make lint`. Do not run real `make install` in a worktree.
- [ ] **Step 5:** Commit `feat: one install path, HTTPS clones (perch-62i)`.

**Done when:** bootstrap tests and lint green; `grep -n "BUDGIE_DIR\|GB_DIR\|BUDGIE_URL\|GB_URL\|make venv" Makefile scripts/bootstrap.sh` is empty.

### Task 2.2: LICENSE, README install block, CLAUDE.md install lines

**Files:** Create `LICENSE`; Modify `README.md` (install section only: one block), `CLAUDE.md` (Commands block: drop `make venv`, `BUDGIE_DIR=`/`GB_DIR=` text; pinned-by-URL text becomes HTTPS; drop the "repo is private, uses your SSH key" sentence: all three repos are public).

- [ ] **Step 1:** Write LICENSE (MIT, `Copyright (c) 2026 Ryan Adams`).
- [ ] **Step 2:** Edit README and CLAUDE.md as described; the workspace/init/alerts/walk sections are W1 and W6, not here.
- [ ] **Step 3:** `~/Documents/tools/perch/bin/pytest perch/tests` and `make lint`.
- [ ] **Step 4:** Commit `docs: install block, MIT license (perch-62i)`.

**Done when:** tests green. Close children (Tasks 2.3, 2.4 beads), then perch-62i; merge `bead/perch-62i` to main.

## W1 workspace (bead perch-gkl; starts after W2 and W3 are merged)

Worktree `bead/perch-gkl`, with `apps` symlinked to the main checkout (see gotcha). Tests must use a tmp checkout and never create dirs in the real `apps/remote-gitboard`.

### Task 1.1: `checkout_home` and `config.yaml`

**Files:** Modify `perch/core/workspace.py`; Test `perch/tests/test_workspace.py` (rewrite).

**Interfaces:** Produces `checkout_home(root: Path | None = None) -> Home`; `Home(root: Path, lead: str | None, _alerts_raw)` with no `gitboard_dir` field; `Home.gitboard_dir -> root/"apps"/"remote-gitboard"` (property); `Home.lead`; `Home.alerts()` (source label `config.yaml`); `WorkspaceError` message above. Removed: `HOME_NAME`, `HOME_ENV`, `find_home`, `create_home`, `_HOME_KEYS` becomes `{"lead", "alerts"}`.

- [ ] **Step 1: Failing tests** (rewrite `test_workspace.py`):

```python
def test_home_is_the_checkout(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "apps").mkdir()
    assert checkout_home(tmp_path).root == tmp_path

def test_home_without_pyproject_names_make_install(tmp_path):
    with pytest.raises(WorkspaceError, match="perch is not running from a checkout: run make install in your perch clone"):
        checkout_home(tmp_path)

def test_config_yaml_lead_and_alerts_load(tmp_path):
    make_checkout(tmp_path)
    (tmp_path / "config.yaml").write_text("lead: Ryan Adams\nalerts:\n  - when: pace < 0.8\n")
    home = checkout_home(tmp_path)
    assert home.lead == "Ryan Adams" and len(home.alerts()) == 1

def test_config_yaml_unknown_key_names_it(tmp_path):
    make_checkout(tmp_path)
    (tmp_path / "config.yaml").write_text("gitboard_dir: /x\n")
    with pytest.raises(WorkspaceError, match="gitboard_dir"):
        checkout_home(tmp_path)

def test_config_yaml_lead_must_be_text(tmp_path):
    make_checkout(tmp_path)
    (tmp_path / "config.yaml").write_text("lead: 5\n")
    with pytest.raises(WorkspaceError, match="lead"):
        checkout_home(tmp_path)

def test_project_paths_live_under_projects(tmp_path):
    home = make_checkout(tmp_path)
    p = tmp_path / "projects" / "apollo"
    assert home.reports_dir("apollo") == p / "reports"
    assert home.budget_dir("apollo") == p / "budget"
```

with `make_checkout(root)` writing `pyproject.toml`, `apps/remote-gitboard/`, `projects/` and returning `checkout_home(root)`.

- [ ] **Step 2:** Run `~/Documents/tools/perch/bin/pytest perch/tests/test_workspace.py -v`; FAIL (ImportError).
- [ ] **Step 3:** Implement. `checkout_home(root=None)`: `root = root or Path(perch.__file__).resolve().parents[1]`; require `(root/"pyproject.toml").is_file()` and `(root/"apps").is_dir()`; load optional `root/"config.yaml"` with the existing yaml loader and key-naming errors; `lead` must be a non-empty str. Update `SCAFFOLD` to `budgie_project: budget`, `board_dump: board/dump.json` (no budget/ top directory). `reports_dir` -> `projects/NAME/reports`, `budget_dir` -> `projects/NAME/budget`. Delete removed names.
- [ ] **Step 4:** Run workspace tests, PASS (others in the suite will fail until Task 1.2; that is expected).
- [ ] **Step 5:** Commit `feat: the perch checkout is home (perch-gkl)`.

**Done when:** the six tests pass.

### Task 1.2: conftest, `_find_home`, `init`, spec paths and gitboard path flags in `steps.py`

**Files:** Modify `perch/tests/conftest.py` (`build_home` builds a tmp checkout; new autouse fixture patches `cli._find_home` to the last-built tmp checkout), `perch/cli.py` (`_find_home` -> `checkout_home()`, `init`, docstrings, monday message), `perch/core/steps.py`, `perch/core/doctor.py` (gitboard fix text), `perch/core/status.py` and `perch/core/brief.py` (paths and text only); Test `perch/tests/test_steps.py`, `test_cli_status.py`, `test_cli_projects.py`, `test_cli_look.py`, `test_cli_run.py`, `test_brief.py`.

**Interfaces:** Consumes W3 flags (`--out`, `--db`, `--log`, `--spec`, `--boards-dir`). Produces: `steps.spec_path(home, project, config) -> projects/NAME/board/NAME.yaml` (NAME is the folder name); `GB_TARGET_FLAGS` (currently `--from --against --base --history --since --all`) loses `--base` and gains `--out`, `--db`, `--log`, `--spec`, `--boards-dir`, so a user cannot redirect an offline sub; gitboard Steps keep cwd = `home.gitboard_dir`. Init order: scaffold `projects/NAME/`, `mkdir budget`, run `budgie init --here` with cwd `projects/NAME/budget`.

- [ ] **Step 1: Failing tests** in `test_steps.py` (hand-checked argv; read the existing tests for the helper style):

```python
def test_gb_pull_passes_out_and_db(home):
    step = steps.gb(home, "apollo", "pull")
    assert argv_pair(step, "--out") == str(home.root/"projects/apollo/board/apollo.yaml")
    assert argv_pair(step, "--db") == str(home.root/"projects/apollo/board/snapshots.jsonl")

def test_gb_stats_passes_dump_log_spec(home): ...
    # --dump board/dump.json --log board/stats.jsonl --spec <spec>

def test_digest_out_is_the_reports_dir(home): ...

def test_budgie_init_runs_here_in_the_budget_dir(home):
    step = steps.budgie_init(home, "apollo")
    assert step.cwd == home.root/"projects/apollo/budget" and "--here" in step.argv

def test_spec_path_uses_project_folder_not_gitlab_segment(home): ...
```

Update `test_cli_status`: replace the "outside a workspace" test by one at cli level asserting the `make install` message. Delete `_no_perch_home` and every `PERCH_HOME` use (`test_cli_look`, `test_cli_status`, `test_cli_projects`). `test_cli_run.py` uses the tmp checkout.

- [ ] **Step 2:** `~/Documents/tools/perch/bin/pytest perch/tests -x -q`; FAIL.
- [ ] **Step 3:** Implement per the Interfaces block; `--boards-dir projects/NAME/board` is added to every Step that finds a board without a path (status, show, tui, `--all` forms). `perch gb stats --from dump` also gets `--spec`. Remove `--base` from the steps error text (`run gitboard pull`). Remove `init --home` and `--gitboard-dir`.
- [ ] **Step 4:** Whole perch suite passes: `~/Documents/tools/perch/bin/pytest perch/tests -q`, then `make lint`.
- [ ] **Step 5:** Commit `feat: projects/NAME layout and explicit gitboard paths (perch-gkl)`.

**Done when:** suite and lint green; `grep -rn "PERCH_HOME\|perch-home\|HOME_NAME\|gitboard_dir:" perch/ scripts/` shows only `doctor.py` old-layout detection (Task 1.5).

### Task 1.3: `walk.install(home, name)` and checkout-local commands

**Files:** Modify `perch/core/walk.py`, `perch/commands/walk.md` (token `@PERCH_DIR@`; `allowed-tools` uses `Edit(/@PERCH_DIR@/projects/*/board/*.yaml)`; hand-back says `perch gb sync -p X`), `.gitignore` (drop `perch-home.yaml` and bare `budget/`; add `/config.yaml` anchored, and `.claude/commands/`); Test `perch/tests/test_walk.py`.

**Interfaces:** Produces `walk.install(home, name: str = "walk") -> list[str]` (wrote/kept lines only), `walk.render(home, name)`, `walk.command_path(home, name)`, `walk.checks(home) -> list[Check]` looping `("walk", "listen")`. Deleted: `_settings`, `_settings_path`, the settings half of `checks`.

- [ ] **Step 1: Failing tests:**

```python
def test_walk_leaves_settings_json_alone(home):
    sp = home.root/".claude/settings.json"; sp.parent.mkdir(parents=True); sp.write_text('{"a": 1}')
    walk.install(home)
    assert sp.read_text() == '{"a": 1}'

def test_walk_allow_glob_is_absolute(home):
    text = walk.render(home, "walk")
    # the template's leading "/" plus an absolute root gives "//Users/...", Claude's absolute-path form
    assert f"Edit(/{home.root}/projects/*/board/*.yaml)" in text and "@PERCH_DIR@" not in text

def test_install_keeps_the_leads_copy(home):
    p = walk.command_path(home, "walk"); p.parent.mkdir(parents=True); p.write_text("mine")
    assert walk.install(home)[0].startswith("kept")
```

- [ ] **Step 2:** Run, FAIL.
- [ ] **Step 3:** Implement as in Interfaces. `COMMANDS` dir stays `perch/commands/`; `render` replaces `@PERCH_DIR@` with `str(home.root)`.
- [ ] **Step 4:** `~/Documents/tools/perch/bin/pytest perch/tests/test_walk.py -v`, PASS.
- [ ] **Step 5:** Commit `feat: /walk installs into the checkout, no settings edit (perch-gkl)`.

**Done when:** tests pass and `checks` for `listen` reports "no .claude/commands/listen.md" until W5 ships the file (the `listen` entry must not fail doctor when `commands/listen.md` does not exist yet: loop only over command files that exist in `perch/commands/`; Task 1.4 adds `board`).

### Task 1.4: `perch review` and board.md allow pattern

**Files:** Modify `perch/core/steps.py` (`review`), `perch/core/walk.py` (`install` for `board`), `perch/cli.py` (review installs it first); Test `perch/tests/test_steps.py`, `perch/tests/test_walk.py`.

`review` now runs with cwd the perch checkout, where `/board` does not exist (gitboard's `board.md` lives in `apps/remote-gitboard/.claude/commands/`, and `.claude/commands/` in the checkout is gitignored). So `walk.install(home, "board")` copies it into the checkout's `.claude/commands/` (kept if the lead has a copy) with two textual rewrites: every `PYTHONPATH=src .venv/bin/python -m gitboard.cli` becomes `perch gb` (so the `allowed-tools` Bash entries match what runs from the checkout, and the `push` and `ingest` entries are dropped from `allowed-tools`: review never pushes, and `perch gb` has no `ingest`), and `Edit(boards/*.yaml)` becomes `Edit(/{home.root}/projects/*/board/*.yaml)`. gitboard's own copy keeps its standalone form; no gitboard edit is needed here. Sources: `walk` and `listen` from `perch/commands/`, `board` from `home.gitboard_dir/.claude/commands/`. `checks` covers `board` only when that source file exists.

- [ ] **Step 1: Failing tests:** `test_board_install_rewrites_edit_pattern_and_runner(home)` (copy lands in the checkout, contains `Edit(/{root}/projects/*/board/*.yaml)` and `perch gb plan`, no `Edit(boards/*.yaml)`, no `gitboard.cli`, gitboard's source untouched), and `test_review_cwd_is_checkout_and_prompt_has_absolute_spec(home)` asserts `step.cwd == home.root`, argv contains `/board GROUP/apollo <abs spec path>` in the prompt, and that `trend.team_lines` and `people_lines` are still appended.
- [ ] **Step 2:** Run, FAIL. **Step 3:** Implement. **Step 4:** Run `test_steps.py`, PASS.
- [ ] **Step 5:** Commit `feat: perch review runs from the checkout (perch-gkl)`.

**Done when:** test passes.

### Task 1.5: doctor old-layout detection and fix texts

**Files:** Modify `perch/core/doctor.py`, `perch/core/alerts.py` (source label `config.yaml`), `perch/tui.py` (`suite_map`: gitboard via venv python like `steps.gitboard`, with `--db` for snapshots; perch cwd the checkout; messages); Test `perch/tests/test_doctor.py`, `perch/tests/test_tui.py`, `perch/tests/test_watch.py`.

**Interfaces:** Produces `doctor.old_layout_checks(start: Path, home: Home) -> list[Check]` (walk up from `start` for `perch-home.yaml`; none found: `[]`). Fix lines per the spec (W1 "Behaviour and messages"): `mkdir -p`, `mv PATH/projects/NAME/* …` (contents), `mv PATH/budget/fy26 …/budget`, `mv PATH/<gitboard>/boards/NAME.yaml{,.base,.base.old} …/board/NAME.yaml…`, `cp` of `snapshots.jsonl` and `reports/stats.jsonl` into `board/`, and the three `perch.yaml` edits. A destination that exists: command omitted and named.

- [ ] **Step 1: Failing tests:**

```python
def test_old_layout_prints_mv_commands(tmp_path, home):
    old = tmp_path/"ws"; (old/"projects/apollo").mkdir(parents=True)
    (old/"perch-home.yaml").write_text("gitboard_dir: gb\n")
    checks = doctor.old_layout_checks(old, home)
    fix = "\n".join(c.fix for c in checks)
    assert not checks[0].ok and f"old workspace at {old}" in checks[0].what
    assert f"mkdir -p {home.root}/projects/apollo/board" in fix

def test_old_layout_existing_destination_is_named_not_moved(tmp_path, home): ...
def test_no_old_layout_no_check(tmp_path, home):
    assert doctor.old_layout_checks(tmp_path, home) == []
def test_missing_gitboard_fix_names_make_install(home_without_gitboard): ...
```

Update `test_tui` (`suite_map` argv/cwd, `_alert_home` writes `config.yaml`) and `test_watch` the same way.

- [ ] **Step 2:** Run, FAIL. **Step 3:** Implement; gitboard-missing fix `apps/remote-gitboard is missing: run make install in the perch checkout`; alerts check fix `edit /…/perch/config.yaml`. **Step 4:** Whole suite + `make lint` PASS.
- [ ] **Step 5:** Commit `feat: doctor detects the old workspace; suite uses the checkout (perch-gkl)`.

**Done when:** suite and lint green.

### Task 1.6: CLAUDE.md and README workspace text; merge

**Files:** Modify `CLAUDE.md` (goal, `workspace.py`, `alerts.py`, `walk.py`, Commands bullets), `README.md` (workspace, init, alerts, walk, "single-team" sections).

- [ ] **Step 1:** Rewrite those sections to the new layout and `config.yaml`. Leave `listen` for W5 and the landing text for W6.
- [ ] **Step 2:** `~/Documents/tools/perch/bin/pytest perch/tests -q && make lint`.
- [ ] **Step 3:** Commit `docs: checkout is home (perch-gkl)`; close perch-gkl; merge `bead/perch-gkl` to main.

**Done when:** closed with reason; main green.

## W5 listen (bead perch-efj; starts after W1, W3, W4 merged)

Worktree `bead/perch-efj`, `apps` symlinked.

### Task 5.1: `core/listen.py`

**Files:** Create `perch/core/listen.py`; Test `perch/tests/test_listen.py`.

**Interfaces:** Produces `parse(vtt_text: str, lead: str) -> list[str]` and `write(home: Home, project: str, lines: list[str], today: date) -> Path` (`projects/P/listen/YYYY-MM-DD.txt`, then `-2`, `-3`, never overwrites; creates the dir).

- [ ] **Step 1: Failing tests:**

```python
VTT = """WEBVTT

NOTE a note
still note

1
00:00:01.000 --> 00:00:03.000
<v Ryan Adams>Move login to Review.</v>

2
00:00:03.000 --> 00:00:05.000
<v Sam>Agreed.</v>

3
00:00:05.000 --> 00:00:07.000
ryan adams: Close the cache ticket.
"""

def test_voice_tag_cues_by_lead_are_kept():
    assert "Move login to Review." in parse(VTT, "Ryan Adams")
def test_name_prefix_lines_are_kept():
    assert "Close the cache ticket." in parse(VTT, "Ryan Adams")
def test_match_is_case_insensitive():
    assert parse(VTT.replace("Ryan Adams>", "RYAN ADAMS>"), "ryan adams")
def test_other_speakers_are_dropped():
    assert all("Agreed" not in l for l in parse(VTT, "Ryan Adams"))
def test_timing_ids_notes_and_header_are_skipped():
    out = parse(VTT, "Ryan Adams")
    assert out == ["Move login to Review.", "Close the cache ticket."]
def test_multiline_cue_kept_whole():
    v = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\n<v Ryan Adams>First line\nNote: second line</v>\n"
    assert parse(v, "Ryan Adams") == ["First line Note: second line"]  # continuation never re-read as a prefix
def test_multi_voice_cue_keeps_only_lead():
    v = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\n<v Sam>Hi</v><v Ryan Adams>Hello</v>\n"
    assert parse(v, "Ryan Adams") == ["Hello"]
def test_class_voice_tag():
    v = "WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\n<v.loud Ryan Adams>Ship it.</v>\n"
    assert parse(v, "Ryan Adams") == ["Ship it."]
def test_crlf_and_bom_are_handled():
    assert parse("﻿" + VTT.replace("\n", "\r\n"), "Ryan Adams")
def test_short_name_does_not_match():
    assert parse(VTT, "Ryan") == []
def test_transcript_is_written_dated_never_overwritten(home):
    a = write(home, "apollo", ["x"], date(2026, 10, 9)); b = write(home, "apollo", ["y"], date(2026, 10, 9))
    assert a.name == "2026-10-09.txt" and b.name == "2026-10-09-2.txt" and a.read_text().strip() == "x"
```

- [ ] **Step 2:** `~/Documents/tools/perch/bin/pytest perch/tests/test_listen.py -v`; FAIL (module missing).
- [ ] **Step 3: Implement** (stdlib only):

```python
"""perch listen: the lead's lines out of a WebVTT transcript."""
from __future__ import annotations
import re
from datetime import date
from pathlib import Path
from perch.core.workspace import Home

_TAG = re.compile(r"<v(?:\.[^\s>]*)?\s+([^>]*)>")
_ANY = re.compile(r"</?[^>]+>")

def _cues(text: str):
    for block in re.split(r"\n\s*\n", text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")):
        lines = block.strip("\n").split("\n")
        if not lines or lines[0].startswith(("WEBVTT", "NOTE")):
            continue
        i = next((n for n, l in enumerate(lines) if "-->" in l), None)
        if i is not None:
            yield lines[i + 1:]

def parse(vtt_text: str, lead: str) -> list[str]:
    want, out = lead.strip().casefold(), []
    for body in _cues(vtt_text):
        if not body:
            continue
        joined = " ".join(body)
        if _TAG.search(body[0]):
            for m, seg in _segments(joined):
                if m.strip().casefold() == want and seg:
                    out.append(seg)
        else:
            name, sep, rest = body[0].partition(":")
            if sep and name.strip().casefold() == want:
                text = " ".join([rest, *body[1:]])
                text = _ANY.sub("", text).strip()
                if text:
                    out.append(text)
    return out

def _segments(joined: str):
    parts = _TAG.split(joined)  # ['', name, text, name, text, ...]
    for name, seg in zip(parts[1::2], parts[2::2]):
        yield name, _ANY.sub("", seg).strip()

def write(home: Home, project: str, lines: list[str], today: date) -> Path:
    d = home.root / "projects" / project / "listen"
    d.mkdir(parents=True, exist_ok=True)
    path, n = d / f"{today.isoformat()}.txt", 1
    while path.exists():
        n += 1
        path = d / f"{today.isoformat()}-{n}.txt"
    path.write_text("\n".join(lines) + "\n")
    return path
```

Adjust `test_multiline_cue_kept_whole` expected text to what the implementation yields (`["First line Note: second line"]`); the point is that `Note:` is not treated as a speaker.

- [ ] **Step 4:** Run, PASS; `make lint`.
- [ ] **Step 5:** Commit `feat: listen.parse and write (perch-efj)`.

**Done when:** all listen unit tests pass.

### Task 5.2: `steps.listen`, `GB_SUBS` sync, `pull --out`

**Files:** Modify `perch/core/steps.py` (`listen(home, project)` same shape as `walk`: `claude "/listen NAME"`, cwd `home.root`; `GB_SUBS` gains `sync`, not in `GB_OFFLINE`; target is the spec plus `--project GITLAB` when the file is missing); Test `perch/tests/test_listen.py`, `test_steps.py`.

- [ ] **Step 1: Failing tests:** `test_gb_sync_is_not_offline` (`"sync" in GB_SUBS and "sync" not in GB_OFFLINE`), `test_gb_sync_adds_project_when_spec_missing`, `test_gb_sync_omits_project_when_spec_exists`, `test_listen_step_runs_slash_listen_in_the_checkout`.
- [ ] **Step 2:** Run, FAIL. **Step 3:** Implement. **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat: perch gb sync and the listen step (perch-efj)`.

**Done when:** tests pass.

### Task 5.3: `perch listen` command and `commands/listen.md`

**Files:** Create `perch/commands/listen.md`; Modify `perch/cli.py` (`listen` command with `-p`), `perch/commands/walk.md` if not already done in 1.3; Test `perch/tests/test_listen.py`.

**Interfaces:** Consumes `parse`, `write`, `walk.install(home, "listen")`, `steps.listen`. Exit 1 before claude with exactly: `no lead set: add "lead: NAME" to /…/perch/config.yaml`; `no lines from "NAME" in MEETING.vtt: check the speaker name matches the transcript`; `cannot read MEETING.vtt`.

`listen.md` content requirements: front matter `allowed-tools: Read, Edit(/@PERCH_DIR@/projects/*/board/*.yaml), Bash(perch brief:*), Bash(perch gb plan:*), Bash(perch gb status:*)`; reads the newest transcript in `projects/X/listen/`, `perch brief -p X`, and gitboard's vocabulary from `apps/remote-gitboard/.claude/commands/board.md` (Read, inside the cwd, no install needed); edits only `projects/X/board/X.yaml` (move cards, epics, milestones, new tasks using the W4 template block then `Source: meeting · LEAD · YYYY-MM-DD`, `closed: true`, remove a column); requires a `.base`, else says `run perch gb pull -p X first`; ends with `perch gb plan -p X`, shows the table and says `read the table; apply with: perch gb sync -p X`; states that the table is offline against the `.base`; never `push`, `pull`, `sync`, `snapshot`.

- [ ] **Step 1: Failing tests:**

```python
def test_no_lead_stops_and_says_so(cli, home):  # no config.yaml
    r = cli("listen", str(vtt), "-p", "apollo"); assert r.exit_code == 1 and 'no lead set: add "lead: NAME" to' in r.output
def test_no_lines_stops_and_names_the_lead(cli, home_with_lead): ...
def test_unreadable_file_stops(cli, home_with_lead): ... "cannot read"
def test_listen_opens_claude_with_slash_listen(cli, home_with_lead, fake_run):
    cli("listen", str(vtt), "-p", "apollo")
    assert fake_run.step.argv[-1] == "/listen apollo" and fake_run.step.cwd == home.root
    assert (home.root/"projects/apollo/listen").glob("*.txt")
def test_listen_md_never_pushes_pulls_or_syncs():
    t = Path("perch/commands/listen.md").read_text()
    allowed = [l for l in t.splitlines() if l.startswith("allowed-tools")][0]
    for bad in ("push", "pull", "sync", "snapshot"): assert f"perch gb {bad}" not in allowed
def test_listen_md_contains_template_fields():
    t = Path("perch/commands/listen.md").read_text()
    for f in ("Goal:", "Done when:", "Context:", "Out of scope:", "Links:", "Source: meeting"): assert f in t
```

(`fake_run` fakes `cli._run` the way existing walk tests do; copy that fixture usage.)

- [ ] **Step 2:** Run, FAIL. **Step 3:** Implement the command (read bytes with `errors="replace"` for the file, catch `OSError` -> "cannot read"), then write `listen.md`. **Step 4:** Whole suite + `make lint` PASS.
- [ ] **Step 5:** Commit `feat: perch listen (perch-efj)`.

**Done when:** all W5 tests listed in the spec exist and pass; `perch doctor` walk/listen checks pass in a fresh tmp checkout.

### Task 5.4: CLAUDE.md and README listen text; merge

**Files:** Modify `CLAUDE.md` (Commands list gets `listen`; `core/listen.py` bullet; `gb` text mentions `sync`), `README.md` (a short listen section: `perch listen MEETING.vtt -p X`, `lead:` in `config.yaml`, the plan table, `perch gb sync -p X`).

- [ ] **Step 1:** Edit. **Step 2:** `make test-all` (from the main checkout after merging deps, or each suite with absolute paths in a worktree) and `make lint`. **Step 3:** Commit `docs: listen (perch-efj)`; close perch-efj; merge to main.

**Done when:** `make test-all` green on main.

---

# Last

## W6 docs (bead perch-7ux)

Worktree `bead/perch-7ux` in perch. Check is `make docs` (`sphinx -W`); it needs the docs extra installed by `make install`; in a worktree call `~/Documents/tools/perch/bin/sphinx-build -W docs docs/_build/html` with absolute paths.

### Task 6.1: new pages and toctree

**Files:** Create `docs/install.md` (clone, `make install`, Migration steps 1-5 from the spec), `docs/layout.md` (the tree from W1), `docs/gitboard.md` (close, drop column, sync, pull / edit / plan / push / refresh), `docs/listen.md`, `docs/issue-template.md` (the template block); Modify `docs/index.md` toctree, `docs/reference.md` (`automodule:: perch.core.listen`), `README.md` (shrink to a pointer with the same install block; `docs/index.md` no longer includes it).

- [ ] **Step 1:** Run `make docs` now to record the baseline (expect PASS). `docs/index.md` currently `{include}`s `../README.md`: replace that with the landing in 6.2, and keep a placeholder toctree so the baseline passes in between.
- [ ] **Step 2:** Add the pages and toctree entries; add the automodule line.
- [ ] **Step 3:** `make docs`; fix any `-W` warning (missing toctree entry, bad cross-reference).
- [ ] **Step 4:** Commit `docs: install, layout, gitboard, listen, template pages (perch-7ux)`.

**Done when:** `make docs` exits 0 with the five pages in the toctree.

### Task 6.2: landing page

**Files:** Modify `docs/index.md` (front matter `layout: landing`; hero with `make install` and `perch monday` buttons; six-card feature grid: Monday run, budget join, accuracy, walk, listen, gb sync; 60-second quickstart: clone, `make install`, `perch init NAME`, `perch monday -p NAME`; inline-SVG diagram transcript -> board -> GitLab; all in `{raw} html` blocks); Create `docs/_static/landing.css` (colors via shibuya CSS variables so light and dark work); Modify `docs/conf.py` (`html_static_path = ["_static"]`, `html_css_files = ["landing.css"]`, theme `nav_links`).

- [ ] **Step 1:** Add the files. **Step 2:** `make docs`; PASS. **Step 3:** Open `docs/_build/html/index.html` and confirm the hero, six cards and SVG render, in light and dark (use the `run` skill or a browser if available; state if not checked). **Step 4:** Commit `docs: landing page (perch-7ux)`.

**Done when:** `make docs` exits 0; no new Sphinx dependency; no JavaScript on the page.

### Task 6.3: final sweep and close

**Files:** none new.

- [ ] **Step 1:** From the main checkout after all merges: `make test-all` and `make lint`; expect green.
- [ ] **Step 2:** `grep -rn "perch-home\|PERCH_HOME\|BUDGIE_DIR\|GB_DIR\|make venv" README.md CLAUDE.md docs/*.md Makefile scripts` and confirm each hit is the airgap exception, the "do not" text, doctor detection, or the Migration section.
- [ ] **Step 3:** `bd close perch-7ux --reason "..."`, then `bd close perch-i51 --reason "W1-W6 landed"` once every child (perch, remote-gitboard, budgie) is closed. File anything discovered as `bd create ... --deps discovered-from:<id>`.

**Done when:** all seven beads closed; `git status` clean on each repo's main.

---

## Self-Review

- Spec coverage: W1 -> 1.1-1.6; W2 -> 2.1-2.4; W3 -> 3.1-3.6; W4 -> 4.1-4.2; W5 -> 5.1-5.4; W6 -> 6.1-6.3; Migration -> 6.1 and 1.5; Out of scope respected (no TUI key, no migration tool, no Budgie code).
- Task 4.2's `board.md` template edit depends on W3 Task 3.6 owning `board.md`; the executor on W4 must wait for or rebase onto W3. Task 1.4 installs a rewritten copy of `board.md` and needs no gitboard edit.
- Type consistency: `checkout_home`, `walk.install(home, name)`, `walk.command_path(home, name)`, `listen.parse/write`, `steps.listen`, `doctor.old_layout_checks` are named identically wherever used. Helper names in gitboard tests are placeholders for the file's existing fixtures and must be matched to `tests/test_apply.py` when written.
