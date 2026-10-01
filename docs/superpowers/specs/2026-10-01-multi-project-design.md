# perch multi-project: one workspace, several funded projects

Date: 2026-10-01. Status: approved and built.
Bead: perch-h3l.

## Purpose

The lead now runs more than one funded project. People are shared between
projects, and each project is paid from its own budget. Today perch, its
Makefile and its data assume one team: one `perch.yaml`, one board dump, one
`history.jsonl`, and one `weekly/` folder. A second project means overriding
every path by hand on every `make` call, and the weekly drafts collide.

This change makes N projects easy to run side by side. It does not combine
them: each project gets its own outputs, and nothing rolls up across projects.

## What a project is

A project is one funded piece of work, and it is the same thing in all three tools:

| Tool | What it is there | Example |
|---|---|---|
| Timesheet | a charge code; hours arrive already split per code | `apollo` |
| Budgie | a Budgie project directory (`budget/apollo/`) | own `people.csv`, `plan.csv`, `weekly.csv`, `budget.csv` |
| gitboard | a GitLab project (its own board) | `group/apollo` |
| perch | a folder `projects/apollo/` holding `perch.yaml` and its outputs | |

Rates are per project. The same person can cost different amounts on different
work (Bob is $100/h on apollo and $95/h on gemini), so each Budgie project
keeps its own `people.csv`. FTE is per project in each `plan.csv` (Alice is 0.6
on apollo and 0.4 on gemini). Budgie needs no change: it already holds several
projects under `budget/` and selects one by directory.

## Decisions taken

- **The runner moves from make into perch's CLI.** The project logic (count the
  projects, pick one, read YAML, loop while carrying on past failures) is code
  that should be tested. The Makefile shrinks to development targets.
- **perch runs the other tools as separate commands; it never imports their
  code for this.** perch still never calls GitLab and never redoes budget math.
  The rule is unchanged: if perch needs a number neither tool produces, it gets
  added to the tool that owns it.
- **Per-project outputs only.** No cross-project rollup, no combined per-person
  message. Alice gets one weekly block and one hours-left email per project.
- **The TUI comes later**, as a layer over the same functions (Budgie's
  CLI/TUI pattern). Filed as a bead, not designed here.

## The workspace

```
~/work/pi/                         the workspace
  perch-home.yaml                  gitboard_dir: ~/Documents/git/pi_suite/remote-gitboard
  projects/
    apollo/
      perch.yaml
      history.jsonl
      dumps/board.json
      weekly/2026-W40.md
    gemini/ ...
  budget/
    apollo/   budgie.yaml people.csv plan.csv weekly.csv budget.csv emails/ ...
    gemini/ ...
```

- `perch-home.yaml` marks the workspace. Its only key is `gitboard_dir`, an
  absolute path or one relative to the file; `~` expands. Unknown keys are an
  error naming the key, the same rule `perch.yaml` uses.
- **Finding the workspace:** walk up from the current directory to the first
  `perch-home.yaml`. If there is none, use `$PERCH_HOME`. If that is unset too,
  stop with a message naming both and `perch init --home <dir>`.
- Projects are the subdirectories of `projects/` that contain a `perch.yaml`.
  Their names are the directory names.
- Digest output goes to `<gitboard_dir>/reports/<project>/`.

### perch.yaml

There is one new optional key, `gitlab_project` (for example `group/apollo`).
It is required by `fetch` and `monday`, and `doctor` reports a project without
it. Every other key is unchanged. `board_dump` and `budgie_project` stay
explicit paths relative to the file; `init` writes them.

## Commands

```
perch projects                    list projects: gitlab_project, Budgie project, age of dump / weekly.csv / history
perch init <name> [--home DIR]    scaffold projects/<name>/ and budget/<name>/ (budgie init)
perch doctor [-p NAME]            tools, config and freshness; every project when -p is omitted
perch hours  [-p NAME]            open that project's weekly.csv in $EDITOR
perch fetch  [-p NAME]            gitboard stats <gitlab_project> --dump <board_dump>
perch digest [-p NAME]            gitboard digest --from <board_dump> --out reports/<name>/
perch emails [-p NAME]            budgie emails, run inside the Budgie project
perch forecast [-p NAME]          budgie forecast, run inside the Budgie project
perch budget [-p NAME]            budgie status: which input files Budgie reads (was make budget)
perch monday [-p NAME | --all]    fetch, board, weekly, digest, emails
perch board / weekly / accuracy   unchanged, gaining -p alongside the existing --config
```

### Picking a project

1. `--config PATH` wins and keeps today's behaviour (`board`, `weekly` and
   `accuracy` only).
2. `-p NAME` selects `projects/NAME/perch.yaml`. An unknown name is an error
   that lists the known names.
3. No flag and a `perch.yaml` in the current directory: that file (`board`,
   `weekly` and `accuracy`; it wins over `$PERCH_HOME`). Added by perch-28n.
4. No flag and the current directory is inside `projects/<name>/`: that
   project. Added by perch-28n.
5. No flag and exactly one project: that project is used.
6. No flag and several projects: stop with
   `several projects: apollo, gemini. Pass -p <name>.`
7. No projects: stop with `no projects yet. Run: perch init <name>`.

### monday

`monday` runs, in order: `fetch`, `board`, `weekly` (to
`projects/<name>/weekly/<ISO week>.md`), `digest`, `emails`. These are the
same five steps as today's `make monday`. Before running each step it prints
the step's command and working directory. It ends by listing the three places
to review: the weekly file, the newest reports folder, and the emails folder.

`monday --all` runs `monday` for every project in name order. If one project
fails, it records the step and the error and moves on to the next project. It
ends with one line per project (`apollo ok`, or
`gemini FAILED: fetch exited <code>`; the tool's own error output is shown live above it) and exits non-zero if any
project failed. Nothing is retried. As before, nothing is ever sent.

`hours` has no `--all`, because each charge code's totals are pasted by hand.

### How the other tools are run

- **budgie** is the `budgie` script in perch's own venv, next to
  `sys.executable`; Budgie is already installed there. It runs with the Budgie
  project directory as its working directory, the way the Makefile runs it today.
- **gitboard** runs with `gitboard_dir` as its working directory, because it
  finds `.env` and `gitboard.toml` by walking up from there. The GitLab project
  is always passed explicitly, so the `project` in `gitboard.toml` is never relied on.
  It is invoked the way the Makefile does today:
  `PYTHONPATH=<gitboard_dir>/src <gitboard_dir>/.venv/bin/python -m gitboard.cli`.
- **perch's own steps** (`board`, `weekly`) run as `perch` commands from the same venv, like the other steps, so `monday` is one list of steps and the tests check the whole sequence.

### init

`perch init apollo`:

- runs `budgie init` into `budget/apollo/`, unless a `budgie.yaml` is already there;
- writes `projects/apollo/perch.yaml` with `budgie_project: ../../budget/apollo`,
  `board_dump: dumps/board.json`, a blank `gitlab_project:` with a comment,
  a commented `estimates:` line, and an empty `people:` map;
- refuses to overwrite an existing `perch.yaml`;
- prints what to fill in by hand: `gitlab_project`, `people:`, and the Budgie
  inputs (`budgie guide`).

`--home DIR` writes `perch-home.yaml` in DIR when there is none yet (it needs `--gitboard-dir` then; perch never prompts, so init stays scriptable), and creates `projects/` and `budget/` there.

### doctor

`doctor` checks the same things as today's `make doctor`, in Python, and prints
one `ok` or `FIX <what> -> <command>` line per check:

- **Tools:** perch, budgie and gitboard each run; `gitboard_dir` exists.
- **Per project** (all of them, or only `-p`):
  - `perch.yaml` loads;
  - the Budgie project has a `budgie.yaml`;
  - `gitlab_project` is set;
  - every name in `people:` exists in that project's `people.csv`. This check
    is new and catches a mistyped name before Monday.
- **Freshness per project:** when the dump, `weekly.csv` and `history.jsonl`
  were last written.
- **Last:** `gitboard config` runs once (tokens and instance). It exits 1
  with no read token (gb-3ac), which doctor reports as a FIX line.

`doctor` exits non-zero if any check reported FIX.

## Code layout

These follow perch's existing rule: `perch/core/` has no click and no rich,
and `perch/cli.py` stays a thin adapter.

- `perch/core/workspace.py` (new):
  - `find_home(start, env) -> Home`;
  - `Home.projects()`;
  - `Home.select(name | None) -> Project`, which raises errors carrying the
    messages above;
  - `Project` paths: config, dump, weekly file, reports dir, Budgie dir.

  Pure functions over paths.
- `perch/core/steps.py` (new): `monday_steps(home, project, week)` and the
  single-step builders return a list of `Step(name, argv, cwd)` values. They
  run nothing. The CLI executes them with `subprocess.run`.
- `perch/core/doctor.py` (new): returns a list of `Check(ok, what, fix)` values.
  The CLI prints them.
- `perch/core/config.py`: adds `gitlab_project` to the known keys and to `Config`.
- `perch/cli.py`: the new commands, plus `-p` on the existing ones.

## Makefile, docs and deck

- **Makefile:** these targets go away and are replaced by the perch commands:
  `help`/`lost` menu sections, `doctor`, `init`, `hours`, `fetch`, `board`,
  `accuracy`, `weekly`, `digest`, `emails`, `monday`, `forecast`, `budget`,
  `budget-tui`, and the board-change targets. These stay: `venv`, `install`,
  `link`, `lint`, `format`, `test`, `test-all`, `docs`, `clean`.
- **Board changes** (`pull`, `plan`, `land`, `show`, `tui`) are plain
  `gitboard` commands run from `gitboard_dir`. `perch projects` prints each
  project's `gitlab_project` to paste in.
- **Budgie's TUI** (was `make budget-tui`) is `budgie tui`, run from the
  workspace's `budget/` folder. Its Projects tab already browses every
  project there, so perch does not wrap it.
- **README and CLAUDE.md** describe the workspace, the commands and the "one
  entry point" rule. perch is still the single entry point, but now as a CLI
  instead of a Makefile.
- **Training deck:** reworking it is filed as a bead and is not part of this change.

## Moving today's setup in

This is documented in the README, not scripted:

1. Create `perch-home.yaml` in the perch checkout, or wherever the data should live.
2. Create `projects/team/` and move `perch.yaml`, `history.jsonl` and `dumps/`
   into it.
3. Fix `budgie_project` and `board_dump` in `perch.yaml` and add `gitlab_project`.

`perch doctor` names any path that is still wrong.

## Errors

- A Budgie or gitboard step that fails shows that tool's own error output,
  prefixed with the project name and the step.
- Workspace and project selection errors say what to run next.
- `--all` collects failures and keeps going; a single-project run stops at the
  first failing step.

## Testing

Tests assert against hand-checkable worlds on disk, following perch's
conventions (`perch/tests/conftest.py`).

- **Workspace:**
  - discovery: walking up, `$PERCH_HOME`, neither, nested directories;
  - unknown keys in `perch-home.yaml`;
  - project listing ignores folders without a `perch.yaml`.
- **Selection:** none, one or several projects, with and without `-p`; an
  unknown name; `--config` winning.
- **Steps:** `monday_steps` returns the right commands, in the right order,
  each with the right working directory, GitLab project and paths. Nothing is
  executed. `--all` carries on past a failure, using a fake runner that fails
  the second project at `fetch`.
- **init:** writes the expected files; refuses to overwrite.
- **doctor:** a world with one deliberate fault per check yields exactly that FIX line.
- Existing tests keep passing. `make test-all` stays the gate.

## Out of scope

- A cross-project rollup or combined per-person outputs.
- Shared rates across projects.
- `hours --all`.
- The TUI (filed as a bead).
- Changes to Budgie or gitboard.
- Scripted migration of the current single setup.
