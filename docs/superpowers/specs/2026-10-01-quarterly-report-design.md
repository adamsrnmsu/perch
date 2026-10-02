# perch quarterly: the management report

Date: 2026-10-01. Status: design approved in conversation; spec awaiting review.
Bead: perch-efu.

## Purpose

Once a quarter, the lead sends each project's funder (a manager, or finance)
a short account of the money: where the budget stands, where estimates missed,
how much work got done, and what slowed it or changed the team. Today that is
assembled by hand from `budgie forecast`, `perch board`, and the board.

`perch quarterly` writes it as an Outlook draft, one per project. Nothing is
sent: the lead reviews the draft and sends it.

## Decisions taken

- **Reader:** a manager or finance. Team level only: no per-person pages, no
  rankings, and no names next to throughput. Names appear only in staffing
  changes, which are facts from `plan.csv`.
- **Sections:** budget position, estimate misses in dollars, throughput trend,
  and waiting and staffing.
- **Data:** the quarter is rebuilt from the source data, not from perch's own
  `history.jsonl`, which only starts when perch was first run:
  - Budgie's weekly readings (hours);
  - `budget.csv` (dated revisions);
  - `plan.csv` (joins, leaves, FTE changes);
  - gitboard's board dump (its issue history from `since`; `perch fetch`
    pulls 276 days, `--history-days 276`).
- **Form:** an `.eml` draft for Outlook (an HTML part and a text part), plus a
  `.md` copy for review.
- **Scope:** one draft per project. `--all` writes every project's draft.
- **Quarter:** the calendar quarter of the Budgie project's year (Q1 is
  Jan–Mar). The default is the last complete quarter.
- **No charts** in this version: tables only.

## Command

```
perch quarterly [-p NAME | --all] [--quarter 2026-Q3] [--out DIR]
```

- It writes `projects/<name>/quarterly/<quarter>.eml` and `<quarter>.md`.
  `--out` replaces the directory.
- Project selection works as for every perch command (`-p`, `./perch.yaml`,
  the project folder you are in, the only project).
- `--all` uses `steps.run_projects`: a failing project is reported and the
  next one still runs, with exit 1 at the end if any project failed.
- A `--quarter` outside the Budgie project's year is an error naming the year.
  A quarter that is not over yet is allowed, and the draft says "to date
  (as of <latest reading>)".

## Contents of each draft

**Subject:** `<project>, <quarter>: $<spent> spent of $<budget>; forecast at
completion $<P50> (<SIGNAL>)`.

**Opening:** one paragraph naming the quarter, the latest reading date, and the
one line from each section that matters most.

### 1. Budget position

- Spent this quarter and spent year to date, both from Budgie's readings, each
  person costed at their rate.
- The budget in force at the quarter's start and at its end
  (`Budget.amount_on`), and every revision dated inside the quarter with its
  amount and note.
- The year-end forecast at completion, P10/P50/P90, and the signal. These come
  from Budgie's `at_completion`, `simulate` and `evaluate`, exactly as
  `budgie forecast` computes them, using the project's own `plan.csv` for the
  share of the plan left.

### 2. Estimate misses ($)

- For issues closed in the quarter, estimated against modelled hours, by epic
  label and by `type::` label, with the difference in dollars. This reuses
  `perch.core.accuracy.by_label` restricted to issues closed in the quarter,
  and is headed MODELLED, as everywhere else in perch.
- With no `estimates:` in `perch.yaml`, the section says so and shows nothing
  else.

### 3. Throughput

- One row per ISO week of the quarter:
  - issues closed (`closed_on` in that week);
  - team hours booked;
  - hours per closed issue, shown as "—" when no issue closed.
- Booked hours for a week are the team's cumulative reading at the week's end
  minus the reading at its start, interpolated between readings the same way
  Budgie's `monthly` books past months.
- A total row for the quarter.
- The previous quarter's totals sit beside it only when the dump's history
  covers the whole previous quarter.

### 4. Waiting and staffing

- **Waiting:**
  - issue-days spent in Blocked inside the quarter, from Blocked transitions in
    the dump;
  - the number of issues reopened or moved back out of Done in the quarter.

  Both are shown as days and counts, never dollars: blocked time burns no
  booked hours, so a dollar figure would be invented.
- **Staffing:** each `plan.csv` change dated in the quarter (a join, a leave,
  or an FTE change), with its effect on the year's planned hours and dollars at
  that person's rate. The hours come from `AllocationPlan.allocated_hours`
  before and after the change.

### Coverage notes

When a source does not cover the whole quarter, the section affected says
what it does cover and what to run, and the report is still written:

- The dump starts after the quarter does: "covers Jul 15 – Sep 30; the board
  dump starts Jul 15" ("keeps 90 days" for a dump without `since`).
- There are no readings: "no hours readings; run `perch hours`".
- There is no dump: "no board dump; run `perch fetch`".

## The Budgie addition (done first, its own bead)

perch must not re-read budget files. `budgie.core.project.Snapshot` gains:

- `budget_revisions`: the loaded `Budget` with its dated revisions (`None` when
  the budget is a flat number);
- `plan`: the loaded `AllocationPlan` from the project's `plan.csv`, or `None`.

`load_snapshot` fills both from files it already resolves. Budgie's tests cover
both fields. `perch/tests/test_contract.py` lists them, so a later Budgie
change fails there first.

## perch code

- `perch/core/quarterly.py` (UI-free) holds the quarter and its sections:
  - `parse_quarter("2026-Q3") -> (start, end)`;
  - `last_complete_quarter(year, today)`;
  - `build(board, money, estimates, rates, people, quarter) -> Quarter`, a
    frozen dataclass with one field per section and the coverage notes.
- `perch/core/money.py` passes the snapshot's `budget_revisions` and `plan`
  through to `Money`.
- `perch/core/report_mail.py` (UI-free, standard-library `email` only) turns
  a `Quarter` into two things:
  - **Markdown:** `render_md(quarter) -> str`.
  - **The draft:** `render_eml(quarter) -> EmailMessage`, a
    `multipart/alternative` message with a text part (the markdown) and an HTML
    part. The HTML is table-based with inline styles only, the same Outlook
    rules as Budgie's emails, and the message carries an `X-Unsent: 1` header
    so Outlook opens it as a draft.
- `perch/cli.py` adds a thin `quarterly` command that loads, builds, writes
  both files, and prints their paths.

## Testing

Tests run against the hand-checkable world in `perch/tests/conftest.py`,
extended with:

- a `budget.csv` holding one revision dated inside Q2;
- a `plan.csv` holding one FTE change dated inside Q2;
- Blocked and reopen transitions on two issues.

What they cover:

- **Quarter dates:** `parse_quarter`, `last_complete_quarter`, and the bad
  inputs (`2026-Q5`, another year).
- **Each section:** every section's numbers worked out by hand, including the
  interpolated hours for a week that falls between readings.
- **Coverage notes:** a dump starting mid-quarter, no readings, no estimates.
- **The `.eml`:**
  - it parses back with `email.message_from_bytes`;
  - it has both parts and the `X-Unsent` header;
  - its HTML contains no `<style>`, `display:flex` or `grid`;
  - the subject format matches.
- **CLI:** `quarterly -p`, and `--all` carrying on past a broken project.

## Out of scope

- Charts.
- Per-person pages.
- A combined report across projects.
- Fiscal quarters other than the calendar quarter.
- Rolling 13-week windows.
- Sending mail.

## Changes during build

- **The forecast takes Budgie's cost lines, and spent is labor only.**
  `Snapshot.costs` carries costs.csv's lines, and perch passes them to
  `simulate(costs=...)` exactly as `budgie forecast` does, so a line with
  `low`/`high` is sampled with the labor rather than added as a fixed total
  (perch-yi9). The report's rows and subject say "labor spent", and a line
  gives the year's non-labor, "in the forecast (a cost line with a low/high
  range is sampled with the labor, as `budgie forecast` does) and not in labor
  spent".
- **The forecast is as of the report's last day.** Readings after the quarter
  are left out (`at_completion(as_of=...)`, as `budgie forecast --as-of`), and
  the signal tests the budget in force at the quarter's end, the same figure
  the subject line quotes. `budgie forecast` itself tests `latest`.
- **The previous quarter's column needs the dump's `since`** (perch-v2b).
  gitboard writes where the dump's history starts as `since`; perch's
  `Board.since` is its date, and it is the coverage start (an old dump without
  it is assumed to keep 90 days from `fetched_at`, and the note says "keeps 90
  days" instead of "starts <date>"). The previous quarter's totals (issues
  closed, hours, hours per issue, blocked issue-days) are shown only when
  `since` is on or before its first day and the fetch after its last; never
  from the 90-day guess, and never for Q1, whose previous quarter is outside
  the Budgie year. They sit as a row under the throughput Total and a line in
  Waiting. `since` is a mid-day timestamp, so its own day counts as covered,
  as the 90-day guess always did.
- **`perch fetch` passes `--history-days 276`** (ruling: the bead said
  `--days 92`). The default report is the last complete quarter, run some days
  into the next: covering it and the one before needs up to 92 + 92 days plus
  that lag, so 184 days covers only a fetch on the day after the quarter ends,
  while 276 covers the previous quarter for the WHOLE following quarter.
  `--history-days` (gitboard gb-ep8) sets only the fetched span,
  `since = now - max(2 x days, N)`; `--days` stays 7, so the printed summary
  and the row `stats` appends to reports/stats.jsonl stay 7-day and the
  digest's 8-week trend is not polluted (a `--days 138` would have changed
  both). Cost against today's 90 days: about 3x the closed issues fetched;
  gitboard makes about 3 calls per issue (open + closed in the window), so a
  fetch takes roughly 1.7-3x as long depending on the open:closed mix. And
  gitboard's own tight / late_milestones / gantt estimates now draw from
  about nine months of finished cards, as do perch's `calibrate` and accuracy
  (perch-7ho).
- **`build` takes `today` and the project name.** Whether a quarter is still
  running depends on the date; the name is the project folder's.
- **A quarter still running** stops at the latest reading. A finished one runs
  to its last day, but a week past the latest reading shows no hours (unknown,
  not zero) and Blocked time stops at the dump's fetch.
- **Jan 1 plan rows are the starting team,** not joins.
- **Unknown is never zero.** A week the dump does not wholly cover (before
  `fetched_at` − 90 days, or after the fetch) shows "—" for issues closed;
  a week past the latest reading shows "—" for hours; blocked issue-days and
  reopens are "—" when the dump does not reach the quarter. The total's hours
  per issue counts only weeks where both are known. Readings that stop before
  the quarter's end are a coverage note ("readings run to Apr 19; spent covers
  Apr 1 – Apr 19"), labor spent rows carry their date span, and spent this
  quarter is "—" when the readings stop before the quarter starts.
- **Reopens are moves out of Done** before the issue closed. The dump holds only
  board-column label moves, so a reopen without a Done label is not seen, and a
  Done removal on or after `closed_on` is GitLab dropping the list label on
  close (and, for an issue closed only by a Done move, matches perch's own
  closed rule), so it is not counted.
- **Estimate misses compare like with like (replaces "by_label restricted to
  the quarter").** `by_label` runs on the whole board; a label is shown only
  once it finished this quarter (no open issue, its last `closed_on` inside the
  quarter), compared whole. A label with issues closed this quarter but still
  open ones reads "n of m closed, no comparison yet" -- never prorated. `#iid`
  estimates on issues closed in the quarter get their own rows (the closer's
  modelled hours against the estimate). The opening gives the two sums apart.
  Caveat in the report: a finished label's early issues can predate the dump.
- **Booked hours use Budgie's `_spent_at` directly** through `Money.booked`
  (merged from main; the contract test pins its signature; budgie-8u1 makes it
  public), so there is no copy of the interpolation left in perch.
- **`--out` with `--all`** writes one folder per project under the directory.
- **A partial count names its span.** When the dump covers only part of the
  quarter, the opening and the Total row give the span of the weeks whose
  closes are counted (and the dump's span for Blocked days). A finished
  quarter whose readings stop early says "labor spent through <date>" in the
  subject and opening, and the forecast rows are "as of" the last reading used.
- **A label's finish is judged by the board at the quarter's end** (perch-ctt),
  not at the fetch: an issue closed after the report's last day was open then,
  so a past quarter's label that finished later reads "n of m closed by <end>".
  Issues created after the report's last day are not in m (perch-iyl):
  `Issue.created_on` is the dump's `created_at`, and the label judgement and
  `by_label`'s whole-label figures both use the board as it stood then. The
  cutoff is `through` (the quarter's end, or the latest reading while it runs),
  the same day the label line names. An old dump without `created_at` counts
  every issue, as before.
- **The issue-estimate dollar total names what it leaves out** (perch-xww): a
  total line under the `#iid` table, and the opening's issue sum, add "n issue(s)
  without a known hourly cost are not in the dollar total" when n > 0; with no
  costed row the total is "—".
