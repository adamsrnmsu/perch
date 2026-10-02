# Monday grid: which step is done, stale or failed, per project

Date: 2026-10-02. Status: design approved in conversation; spec under review.
Bead: perch-w17. Built on branch `tui-switch` (perch-2gr.1, the B/G keys),
merged in, so it lands after that branch.

## Purpose

The lead's Monday time goes to two things: knowing which projects and steps
are done, stale or failed this week, and fixing a step that failed. Today
`monday` prints a log and `perch tui` streams one; nothing shows the state.

The idea is a Bloomberg-style monitor: rows are projects, columns are the
Monday steps, each cell coloured by its state, and Enter on a cell runs it.
Everything is derived from the files the steps already write, so perch adds
no new number and no new file.

Parked for a later epic (not designed here): a mnemonic command line
(`apollo CUT 700k <GO>`), drill-down from any figure, headroom sparklines from
history.jsonl, a "what changed" strip, and alerts on a stoplight flip.

## Core: `perch/core/status.py`

UI-free, like the rest of `core/`.

```python
STEPS = ("hours", "fetch", "board", "weekly", "digest", "emails", "watch")

@dataclass(frozen=True)
class Cell:
    state: str      # "done" | "stale" | "todo" | "error"
    when: str       # doctor.age() of the step's output; "never" if none
    why: str = ""   # the stale or error reason, e.g. "weekly.csv newer than board"

def status(home: Home, name: str, today: date) -> dict[str, Cell]: ...
def next_step(cells: dict[str, Cell]) -> str | None: ...  # first not "done"
```

The week is `steps.iso_week(today)`. The cutoff for "this week" is that
week's Monday at 00:00 local time.

| Step   | Output read                          | Done when                                       |
|--------|--------------------------------------|-------------------------------------------------|
| hours  | Budgie snapshot (`money`)            | `as_of` is on or after the Sunday before the cutoff (see below) |
| fetch  | `config.board_dump`                  | mtime at or after the cutoff                    |
| board  | `config.history`                     | `latest_week` is this week's key                |
| weekly | `home.weekly_path(name, week)`       | the file exists                                 |
| digest | `home.reports_dir(name)/<YYYY-MM-DD>`| a dated folder falls in this week (gitboard names them by date) |
| emails | `config.budgie_project / "emails"`   | mtime at or after the cutoff                    |
| watch  | `home.watch_path(name, week)`        | the file exists                                 |

hours: a weekly.csv row means "cumulative through ISO week N", and Budgie
dates it at that week's Sunday (`budgie.core.actuals.week_ending`). On Monday
the lead pastes the week that just ended, so a reading dated the Sunday before
the cutoff counts as this week's hours.

A done cell is **stale** when an input is newer than its output:

- board: the dump or `weekly.csv` is newer than `history.jsonl`;
- weekly, watch: `history.jsonl` is newer than the file;
- digest: the dump is newer than the newest dated folder;
- emails: `weekly.csv` is newer than the `emails` directory.

hours and fetch are never stale; they are the inputs.

A perch.yaml or Budgie project that will not load gives `error` cells
carrying the message (the same errors `tui.row` already catches); `status`
never raises for one bad project.

### The failure record

`perch monday` (one project or `--all`) writes `projects/NAME/monday.json`
when a step fails: `{"week": "2026-W40", "step": "fetch", "code": 2, "at":
"<ISO datetime>"}`. A run that gets past that step deletes the file. Only
perch writes it, it records only what perch ran, and it holds no number.

`status` turns the recorded step's cell into **`failed`** (`why` = "fetch
exited 2") when the record is for this week and the step's output is not
newer than `at`. A step later done another way (`perch fetch` by hand) is
therefore no longer failed. A record that will not parse is ignored.

`STEPS` cell states become `done | stale | todo | failed | error`.

`next_step` returns the first step, in `STEPS` order, whose cell is not
`done`, or None when the week is finished.

## CLI

### `perch monday --from STEP`

STEP is one of `fetch`, `board`, `weekly`, `digest`, `emails`
(`click.Choice`). `steps.monday(...)` takes an optional `start` and returns
its list from that step on; with no start the list is unchanged. The watch
write still runs last. `--from` with `--all` is a usage error (exit 2): each
project needs its own start, and `perch status` names it.

### `perch status [-p NAME]`

One row per project (or only NAME): the project, then one cell per step:
`ok` (green), `stale` (yellow), `todo` (dim), `FAIL` and `ERR` (red). Then, per project
that is not finished, the exact command to run next:

```
apollo   ok   ok   ok   stale todo todo ok     next: perch monday -p apollo --from weekly
hermes   todo ok   ok   ok    ok   ok   ok     next: perch hours -p hermes
```

`next` maps `hours` to `perch hours -p NAME`, `watch` to `perch watch -p
NAME`, and every other step to `perch monday -p NAME --from STEP`. It sits
first in the "Every Monday, in order" help section. Exit 0 always: it reports,
it does not judge.

## TUI

### Columns

`Project | GitLab | Stoplight | Headroom | hours | fetch | board | weekly |
digest | emails | watch | Flags`

The Dump and weekly.csv age columns go; the step cells replace them. Step
cells show `✓` (green), `stale` (yellow), `·` (dim, todo), `FAIL` or `ERR`
(red).

### Cursor and keys

The cursor moves by **cell** instead of by row. Every existing key (b, m, d,
f, w, Q, c, h, a, r) still acts on the cursor's project. Enter:

- on a fetch..emails cell: `perch monday -p NAME --from STEP`;
- on hours: the editor, as `h` does now;
- on watch: `perch watch -p NAME`;
- on any other column: that project's `next_step`, mapped as `perch status`
  maps it; nothing when the week is finished.

### Failures

`FAIL` comes from `status()`, not from the TUI (see "The failure record"), so
a step that failed in a terminal `perch monday` shows red in the TUI too.
After a run started from the TUI exits non-zero, the log pane, which already
holds the tool's output, gets that project's `doctor.project_checks` FIX
lines.

### Refresh cost

Each `row()` recomputes the watch (a full load and rate fit). `_finished`
now refreshes only the row that just ran; `r` and mount still refresh every
row.

## Testing

Against the conftest world, files written or `os.utime`-touched in
`tmp_path`, with a fixed `today`.

- `test_status.py`: done, stale and todo for each step; a record for this
  week fails its cell, a later output or last week's record does not; a broken perch.yaml
  gives `error` cells; `next_step` is the first not-done step and None when
  all are done.
- `test_steps.py`: `monday(..., start="weekly")` is weekly, digest, emails in
  order; no start is the five steps unchanged.
- `test_cli_run.py`: `monday --from board` runs board..emails and writes the
  watch; a failing step writes monday.json and a passing run removes it;
  `--from` with `--all` exits 2; `perch status` prints the grid and the
  right `next:` command.
- `test_tui.py` (`_spawn` faked): Enter on a step cell spawns `monday -p NAME
  --from STEP`; a FAIL cell shows from a written record; a failing fake run
  writes FIX lines; after a run only that row refreshes; the existing key tests are
  updated for the cell cursor.
