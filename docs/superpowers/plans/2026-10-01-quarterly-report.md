# perch quarterly: implementation plan

Bead: perch-efu. Spec: `docs/superpowers/specs/2026-10-01-quarterly-report-design.md`.

1. **Fixture** (`perch/tests/conftest.py`): Blocked/unblocked transitions on
   #102 and a move out of Done on #8 (closed_at keeps it closed) in the base
   history; a `quarter_world` fixture that unpins the budget and writes
   budget.csv (revision 2026-04-15) and plan.csv (Bob 0.5 -> 0.25 on
   2026-05-01), with its arithmetic in the docstring.
2. **Money** (`perch/core/money.py`, `test_money.py`, `test_contract.py`):
   pass through `people`, `pto`, `budget_revisions`, `plan`; list the new
   budgie.core names in the contract test.
3. **Board** (`perch/core/board.py`, `test_board.py`): `Issue.transitions`
   as `(date, action, label)`.
4. **Quarter dates** (`perch/core/quarterly.py`, `test_quarterly.py`):
   `parse_quarter`, `last_complete_quarter`, bad inputs.
5. **Sections** (same files): budget position (interpolated spend, budget
   in force, revisions, forecast at completion), estimate misses (by_label on
   the quarter's closed issues), throughput by ISO week, waiting (blocked
   issue-days, moves out of Done), staffing (plan changes), coverage notes.
6. **Draft** (`perch/core/report_mail.py`, `test_report_mail.py`):
   `render_md`, `render_eml` (multipart/alternative, X-Unsent, table HTML).
7. **CLI** (`perch/cli.py`, `test_cli_quarterly.py`): `perch quarterly
   [-p | --all] [--quarter] [--out]`, `--all` via `steps.run_projects`.
8. **Docs**: README, CLAUDE.md, docs/reference.md; spec "Changes during build".
