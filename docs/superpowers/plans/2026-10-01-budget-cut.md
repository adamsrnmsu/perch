# perch cut: implementation plan

Spec: `docs/superpowers/specs/2026-10-01-budget-cut-design.md`. Bead: perch-mo4.

1. **money.py: Money from a loaded Snapshot.** `money_from(snapshot)`;
   `load_money` becomes `money_from(load_snapshot(project))`. `what_if(snapshot,
   budget, changes)` wraps Budgie's `Snapshot.what_if`, seeding a Jan 1 row at
   the flat fte for anyone changed who is not yet in the plan.
   Tests: test_money.py (Bob leaves 2026-07-01: 494.016 h allocated); contract
   test lists `PlanEntry`, `what_if`, `plan`, `allocations`.
2. **board.py: milestones.** `Issue.milestone`, `Issue.milestone_due` from the
   dump's `milestone`/`milestone_due` (absent: None). Test: test_board.py.
3. **history.py: team row gains `budget`, `left`, `signal`; `latest_week(path)`.**
   Tests: test_history.py.
4. **cut.py: `parse_change`, `side_from_money`, `side_from_history`, `compare`
   -> `Cut`.** Tests: test_cut.py (Bob leaves, flag validation, history week,
   old row, milestones).
5. **cli.py: `perch cut`; `board` passes `left=`.** Tests: test_cli_cut.py
   (budget cut flips GOOD to bad; after-the-fact; nothing written; flag errors).
6. Docs: README/CLAUDE.md, spec "Changes during build".
