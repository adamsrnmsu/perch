# Plan: TUI blocks (perch-5h6)

Spec: `docs/superpowers/specs/2026-10-02-tui-blocks-design.md`. All three
phases at once; the format is fixed by the spec and by `perch/core/blocks.py`
(done first, `perch-5h6`), so the four lanes below run in parallel.

| Lane | Repo / worktree | Owns | Bead |
|---|---|---|---|
| G | remote-gitboard `.claude/worktrees/tui-blocks` | `src/gitboard/blocks.py`, `stats.team_blocks`, `render_team_md` via `to_md` (byte-identical), `stats` under `PI_BLOCKS` | gitboard bead |
| T | perch `.claude/worktrees/tui-blocks` | `perch/tui.py`, `perch/tests/test_tui.py`: `PI_BLOCKS=1` env, RunCard as container, block widgets, `o` maximize | perch-5h6.1 |
| P | perch `.claude/worktrees/tui-blocks` | `perch/cli.py`, `perch/core/watch.py`, `perch/core/weekly.py` and their tests: board, cut, status, doctor, watch, weekly as blocks; rich renderer in cli; `_run` header block | perch-5h6.2 |
| B | budgie `.claude/worktrees/tui-blocks` | `budgie/blocks.py`, forecast, status, emails under `PI_BLOCKS`; no banner/log lines on stdout | budgie bead |

T and P share a worktree but no file; neither commits (the lead does). G and
B commit in their own worktrees.

Then: two reviewers over all four diffs (correctness; contract + rules),
fixes, full suites in each repo, a headless TUI screenshot against the real
workspace, merge each to its main.
