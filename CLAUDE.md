# CLAUDE.md

## Goal -- judge every change against this

perch is the join between **gitboard** (the work) and **Budgie** (the money),
for one lead. It owns the join and the views and nothing else. If perch needs a
number neither tool produces, add it to the tool that owns it. perch never
calls GitLab, never redoes budget math, never sends anything, and never ranks
people.

perch is also the one entry point for every pi app, as a CLI: `perch monday`,
`perch doctor`, `perch hours` and the rest shell out to the tool that owns each
step (`perch/core/steps.py` holds each call as a `Step` value; the CLI runs
them). perch never imports another app's code to do that. A workspace
(`perch-home.yaml`) holds `projects/<name>/` and `budget/<name>/`; a project
is one GitLab project + one Budgie project + one charge code, picked with
`-p`. The Makefile is development only.

## Commands

```bash
perch --help  # running the apps: projects, init, doctor, hours, monday [--all],
              # quarterly [--all]
make venv     # ~/Documents/tools/perch; Budgie from GitHub, then ../budgie
make test     # perch only: ~/Documents/tools/perch/bin/pytest
make test-all # Budgie, perch and gitboard suites
make lint     # ruff check .
make format   # ruff format .
```

The other apps are found beside this checkout (`../budgie`,
`../remote-gitboard`); `BUDGIE_DIR=` and `GB_DIR=` override that.

Budgie is a library dependency pinned in `pyproject.toml` by git URL
(`budgie @ git+ssh://git@github.com/adamsrnmsu/budgie.git`), never by bare name: the PyPI name is not ours.
The repo is private, so the install uses your SSH key.
`make venv` installs `../budgie` editable after perch, so the local checkout
wins for dev.
`perch/tests/test_contract.py` lists every `budgie.core` name perch imports;
when Budgie changes, that test fails first.

## Architecture

Same rule as Budgie: everything under `perch/core/` is UI-free (no click, no
rich); `perch/cli.py` is a thin adapter with engine imports inside commands.

- `core/config.py` -- perch.yaml to a frozen `Config`; every error names the key.
- `core/workspace.py` -- perch-home.yaml (walk up, else $PERCH_HOME), the
  projects under projects/, `-p` selection, and scaffolding a project.
- `core/steps.py` -- every Budgie/gitboard/perch call as a `Step(argv, cwd,
  env)`; nothing here executes. `run_projects` is `monday --all`'s
  carry-on-past-a-failure loop.
- `core/doctor.py` -- `Check(ok, what, fix)` values for `perch doctor`.
- `core/board.py` -- a `gitboard stats --dump` file to `Board`/`Issue`.
  `closed_on` follows gitboard's `done_at` (closed_at, else the last move into
  Done) so the two tools agree on what is finished. Type is the first
  `type::` label.
- `core/estimates.py` -- estimates.csv (`#iid` or label keys), via Budgie's csvio.
- `core/money.py` -- everything read out of a Budgie project, via Budgie's
  `load_snapshot`. Which input wins (weekly over monthly, a reading over
  `hours_spent`, a plan over fte, a pinned budget over budget.csv) is Budgie's
  rule in `budgie/core/project.py`; a new rule goes there, never here.
- `core/rate.py` -- reading-to-reading intervals, own and team rates, and the
  type model. **The type fit alternates** (rates on hours / factor, then
  factors, repeat): a single pass is biased towards whoever closed the most of
  each type. Rare types share `other`; if `other` is itself under 5 issues it
  is counted with the commonest type; a negative column is merged away and the
  fit re-run; fewer intervals than columns + 2 refuses to fit.
- `core/join.py` -- hours per issue (estimate, type model, own rate, team rate,
  else no basis), person rows, the rollup through Budgie's `simulate()` and
  `evaluate()`, and the trust notes.
- `core/accuracy.py` -- by label is MODELLED, by person is measured and refuses
  below 50% coverage. Keep those two words honest in every output.
- `core/history.py` -- week-keyed history.jsonl; re-running replaces the week.
  The team row carries `budget`, `left` and `signal` for `perch cut`.
- `core/cut.py` -- `perch cut`: before → after for a what-if (`money.what_if`,
  Budgie's `Snapshot.what_if` underneath) or since the last recorded week.
  Shows the gap and each milestone's open work; never orders issues.
- `core/weekly.py` -- `perch weekly`: per-person markdown from this run plus
  history. Read-only. A trailing comparison needs 4 prior weeks that hold that
  figure; below that it prints `not enough history: n of 8 weeks`, never a trend.
- `core/watch.py` -- `perch watch`: four own-baseline signals per person, each
  flagging only when out of line 3 of the last 4 weeks. Private to the lead:
  nothing from it goes into a draft, an email or a report, and no output uses
  a ranking word (a test checks). `monday` writes it in-process after its steps.
- `core/quarterly.py` -- `perch quarterly`: one quarter rebuilt from Budgie's
  readings, budget revisions and plan plus the board dump (never
  history.jsonl). The forecast is Budgie's `at_completion` + `simulate` +
  `evaluate`; booked hours interpolate readings like Budgie's `monthly`.
  Team level only: names appear only in staffing changes.
- `core/report_mail.py` -- a `Quarter` as markdown and as an `.eml` draft
  (multipart/alternative, `X-Unsent: 1`, table HTML with inline styles only).
- `tui.py` -- `perch tui` (Textual): the projects table from what is on disk
  (the last recorded team row, `doctor.freshness`, the watch's flag count only)
  and keys that run `perch <command> -p NAME` through `_spawn`, which tests fake.
  Display and key handling only, like cli.py.

## Testing

`perch/tests/conftest.py` builds one hand-checkable world on disk (the
docstring has the arithmetic). Assert against numbers you can work by hand from
that docstring.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:1105d646 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->
