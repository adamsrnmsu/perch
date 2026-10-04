# perch as the umbrella for the pi apps

Bead: perch-wyj. Decided with the lead on 2026-10-04.

## Goal

perch is the one repo you clone. A script in it fetches Budgie and gitboard
into `perch/apps/`, installs all three and links the commands. The
`~/Documents/git/pi_suite` folder stops existing.

## What is true today

- `pi_suite/` is a plain folder, not a repo. It holds perch, budgie and
  remote-gitboard (three repos, each with its own GitHub remote and beads),
  gitboard-promo (Remotion scratch, never committed) and laya-bench (not a
  repo).
- perch finds gitboard at runtime only through `gitboard_dir` in
  `perch-home.yaml` (an absolute path). It gets Budgie through pip. The
  sibling layout lives in perch's `Makefile` (`BUDGIE_DIR ?= ../budgie`,
  `GB_DIR ?= ../remote-gitboard`) and in docs.
- Budgie and gitboard never reference perch except through the `PI_SUITE`
  environment variable, which carries absolute `cwd`/`argv` values built by
  perch. It does not care where the checkouts live.
- Beads databases use relative paths and survive a move. Editable installs,
  venv script shebangs, the `~/.local/bin/gitboard` wrapper and git worktree
  links store absolute paths and break on a move.

## Layout

```
~/Documents/git/perch/             the perch repo
  scripts/bootstrap.sh             clone the apps, install, link
  apps/                            gitignored by perch
    budgie/                        its own repo, remote and beads
    remote-gitboard/               its own repo, remote and beads
~/Documents/git/gitboard-promo/    moved out of pi_suite, still no git
```

- The apps stay independent repos. perch's git ignores `apps/`; it never
  records them as submodules or gitlinks.
- Venvs stay where they are: `~/Documents/tools/perch`,
  `~/Documents/tools/budgie` (outside the repos because of the macOS hidden
  `.pth` trap) and gitboard's in-tree `.venv`.
- `gitboard_dir` stays explicit in `perch-home.yaml`. perch does not derive
  it from its own install location.
- Claude Code loads every ancestor `CLAUDE.md` and `AGENTS.md`, so Budgie
  and gitboard sessions will also read perch's. Accepted for now; trim
  perch's files if that turns out to cost too much context.

## perch changes

These land on perch main and are pushed before the move.

1. `.gitignore` gains `apps/`. This goes in first, so nothing placed in
   `apps/` is ever staged.
2. `Makefile`: `BUDGIE_DIR ?= $(PERCH_DIR)/apps/budgie` and
   `GB_DIR ?= $(PERCH_DIR)/apps/remote-gitboard`. No fallback to `../`: one
   user, one layout. The overrides still work for anything else.
3. `scripts/bootstrap.sh`, POSIX sh, run from anywhere:
   - For each app, clone it into `apps/<name>` if that directory is missing;
     otherwise leave it alone (no pull, no reset).
   - Budgie clones from `git@github.com:adamsrnmsu/budgie.git` (private,
     ssh). gitboard clones from
     `https://github.com/adamsrnmsu/remote-gitboard.git`. Both URLs can be
     overridden by `BUDGIE_URL` and `GB_URL`.
   - Then `make install link` in perch.
   - Ends by printing the `gitboard_dir:` line to put in `perch-home.yaml`.
   - Stops on the first failure (`set -eu`) and says which step failed.
4. One runnable check for the script: a shell test that runs it in a temp
   copy with `BUDGIE_URL`/`GB_URL` set to `file://` URLs of local repos and
   the install step skipped (`BOOTSTRAP_NO_INSTALL=1`), then asserts both
   clones exist and a second run changes nothing.
5. README and CLAUDE.md describe the new layout, with bootstrap as the
   install step. Example paths (`perch init --gitboard-dir ...`) point at
   `apps/remote-gitboard`. Old specs and plans are history and stay as they
   are.

## Tidy in the other repos

Budgie:

- Delete `docs/superpowers/specs/2026-10-02-one-model-design 2.md` and
  `2026-10-02-ux-review 2.md`: byte-identical copies of tracked files.
- Update current-tense `pi_suite` mentions in CLAUDE.md and the
  `docs/_static/hacker.css` comment.

remote-gitboard:

- Add `docs/laya-bench.md` holding laya-bench's README and
  `results/report.md`. laya-bench measured gitboard's `type::` labelling,
  so its result belongs here.
- Update current-tense `pi_suite` mentions (`hacker.css` comment, CLAUDE.md
  if any).
- `.claude/worktrees/`: `milestone-horizon` is a registered worktree locked
  by a dead session (pid 8047), its branch merged into origin/main.
  `blockers-graph` points at an older, missing path; `gb-2sj` and
  `small-fixes` are not worktrees at all. Check each for files that are not
  on main, report anything unsaved, then remove them (unlock, `git worktree
  remove`, `git worktree prune`).
- `boards/test.yaml` has uncommitted changes of unknown origin. Show the
  diff to the lead; do not commit or revert it.

## Migration

Done once, serially, in one session, after the lead says go. All commands
use absolute paths and run from `~/Documents/git`, never from inside
`pi_suite`.

1. Check no other Claude session is working under `pi_suite`
   (`ps` and `lsof +D`), and every repo is clean and pushed.
2. `mv pi_suite/perch ~/Documents/git/perch`.
3. `mv pi_suite/budgie pi_suite/remote-gitboard ~/Documents/git/perch/apps/`.
4. `git worktree prune` in each repo.
5. Remove gitboard's `.venv` (its `install` target is gated on
   `.venv/bin/pytest`, so a moved venv with broken shebangs would be
   skipped), then `make install link` in perch. That rebuilds the editable
   installs in both tools venvs and rewrites `~/.local/bin/gitboard`.
6. Rewrite `gitboard_dir` in the workspace's `perch-home.yaml` to
   `/Users/ryanadams/Documents/git/perch/apps/remote-gitboard`.
7. `mv pi_suite/gitboard-promo ~/Documents/git/gitboard-promo` (no git
   steps).
8. Delete `pi_suite/laya-bench` once `docs/laya-bench.md` is on gitboard's
   main.
9. `rmdir pi_suite` (fails, and stops the migration, if anything is left).
10. Copy Claude's memory from
    `~/.claude/projects/-Users-ryanadams-Documents-git-pi-suite/memory/`
    to `-Users-ryanadams-Documents-git-perch/memory/` and rewrite the
    `pi_suite` paths in it.
11. Verify: `make test-all`, `perch doctor`, `which perch gitboard`, `bd
    ready` in all three repos, and `perch tui` hops P/B/G once by hand.

The lead then restarts Claude in `~/Documents/git/perch`.

## Decisions for perch-wyj

1. The suite's home is perch. No umbrella repo, no submodules, no monorepo.
2. Suite-level docs and decisions live in `perch/docs`.
3. A cross-repo change is one perch epic with a child bead per repo, each
   naming the epic. Record this with `bd remember` and in perch's README.

## Out of scope

- Making perch derive `gitboard_dir` or Budgie's location itself.
- Pinning app versions together (that was the submodule option).
- Rewriting paths in old specs and plans.
