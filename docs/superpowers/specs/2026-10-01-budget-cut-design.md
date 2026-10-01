# perch cut: what no longer fits after a budget cut or a plan change

Date: 2026-10-01. Status: design approved in conversation; spec awaiting review.
Bead: perch-mo4.

## Purpose

This is the join run backwards. Given a budget cut or a change to the plan
(someone leaves, someone drops FTE), it shows how many planned hours disappear
and whether the open board still fits. It answers the question before the lead
agrees to a cut, and it shows the effect after one has landed.

## Decisions taken

- **Two modes.**
  - **What-if (with flags):** "before" is today's files, and "after" is today's
    files with the flags applied. Nothing on disk changes.
  - **After the fact (no flags):** "before" is the last week `perch board`
    recorded in `history.jsonl`, and "after" is today's files.
- **No ordering of issues.** perch shows the gap and each milestone's open
  work; the lead decides what to cut. There is no "these drop off" list.
- **Terminal output,** in the same style as `perch board`.
- **perch never ranks people:** per-person rows are in name order, as in
  `perch board`.

## Command

```
perch cut [-p NAME] [--budget AMOUNT] [--leaves NAME:YYYY-MM-DD]...
          [--fte NAME:YYYY-MM-DD:FTE]...
```

- `--leaves Bob:2026-11-01` means Bob is at 0 FTE from that date.
- `--fte Alice:2026-11-01:0.5` means Alice is at 0.5 FTE from that date.
- `--budget 700000` replaces the latest budget.
- Each flag is validated, and an error names it:
  - the name must be in the Budgie project's people;
  - the date must be inside the year;
  - FTE must be between 0 and 1;
  - the budget must be greater than 0.
- Project selection works as for every perch command.

## The Budgie addition

Budgie owns the allocation math, so `budgie.core.project.Snapshot` gains
`what_if(budget: float | None = None, plan_entries: Sequence[PlanEntry] = ())`.
It returns a new `Snapshot`:

- allocated hours are recomputed through `AllocationPlan` with the extra
  entries;
- the budget is replaced when one is given.

It shares a bead with the quarterly report's snapshot fields (`plan`,
`budget_revisions`). `perch/tests/test_contract.py` lists `what_if`.

## History

The `team` row in `history.jsonl` also records `budget` and `left` (the team's
planned hours left). An older row without them shows "—" in the "before"
column, and the run says that a fresh `perch board` will record them.

## Output

**Team.** A before → after line for each of:

- planned hours left;
- budget;
- the cost to clear the open board (P50), through the existing
  `join.rollup`;
- headroom;
- the stoplight.

Then one line, either "Board needs 1,240 h; the team has 980 h left after the
change: short by 260 h" or "still fits with 140 h spare".

**People,** in name order:

- hours left before → after;
- open issues and their modelled hours, with each hours figure showing how it
  was worked out (the same basis order as `perch board`);
- for anyone leaving: "leaves 2026-11-01: 4 open issues (96 h) need a new
  owner".

**Milestones:**

- open issues;
- open hours (P50, with the low–high range);
- the due date.

## Code

- `perch/core/cut.py` (UI-free):
  - `parse_change(flag) -> PlanEntry`;
  - `compare(before, after, board, estimates, rates, people) -> Cut`, a frozen
    dataclass with the team, people and milestone rows.
  - `before` and `after` are `Money` values. In what-if mode both come from the
    snapshot (after through `what_if`). In after-the-fact mode, "before" comes
    from the latest history week.
- `perch/core/history.py`: the team row gains `budget` and `left`, plus a
  `latest_week(path)` reader.
- `perch/cli.py`: a thin `cut` command.

## Testing

All against the hand-checkable world in `perch/tests/conftest.py`:

- **Bob leaves on 2026-07-01:**
  - his hours left drop by the hand-worked amount;
  - his open issues (#104, #105) are listed as needing a new owner.
- **A budget cut that flips the stoplight** from GOOD to a worse signal.
- **After-the-fact mode** against a recorded history week, and against an old
  row with no `budget` field.
- **Flag validation:** an unknown name, a date outside the year, FTE above 1.
- **Nothing is written:** a what-if run leaves `history.jsonl` and every
  Budgie file untouched.

## Out of scope

- Ordering issues, or suggesting what to cut.
- Writing changes back to `budget.csv` or `plan.csv`.
- Cross-project moves (someone moving from apollo to gemini).
