# Plan: Bloomberg-style TUI (perch-ge0)

Spec: `docs/superpowers/specs/2026-10-02-bloomberg-tui-design.md`. Branch
`worktree-bloomberg-tui`. Tests: `make test`; lint: `make lint`. TDD: each
task writes its tests first, against the spec's exact strings.

## Order

```
1 command.py ─┐
              ├─> 3 tui wiring + docs ─> 4 review ─> 5 fixes
2 trend.py  ──┘
```

1 and 2 run in parallel (separate new files). 3 is the only task that edits
`perch/tui.py` and `perch/tests/test_tui.py`.

## 1. `perch/core/command.py` + `perch/tests/test_command.py`

Exactly the spec's "Core: perch/core/command.py": `MNEMONICS`, `ALL`, `FROM`,
`Command`, `amount`, `parse`. Every refusal in the spec's Testing list is a
test. No imports from textual/rich/click.

## 2. `perch/core/trend.py` + `perch/tests/test_trend.py`

Exactly the spec's "Core: perch/core/trend.py": `WINDOW`, `BARS`, `spark`,
`series` (built on `history.figures`), `Change`, `change`, `describe`,
`team_lines`. Includes the privacy test: a history with person rows, no
person name and no `test_watch.BANNED` word in `describe`/`team_lines`.

## 3. `perch/tui.py` wiring, `test_tui.py`, docs

`snapshot()` under `row()`, the Trend column, `#command` replacing `#flags`
(`:` and `c`), `i` drill with info cards (`RunCard` option, subtitle `info`),
`Static#changes`, flip toasts with `self.alerted`. Update existing tests whose
column indexes move. CLAUDE.md, README, docs/reference.md per the spec's Docs
section.

## 4. Review

Two reviewers in parallel over `git diff main...HEAD`: correctness/bugs, and
spec + CLAUDE.md rules (team rows only, nothing sent, no ranking, core UI-free).

## 5. Fixes

Apply confirmed findings; `make test` and `make lint` green; close beads.
