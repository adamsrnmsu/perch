# Bloomberg-style TUI: command line, drill-down, trend, what changed, alerts

Epic `perch-ge0`, parked by the Monday grid spec
(`2026-10-02-monday-grid-design.md`). The grid made `perch tui` a monitor; this
makes it answer the next questions without leaving it: "do X to project Y" in
one line, "what is behind this figure", "which way is it going", "what moved
since last week", and "tell me when a stoplight flips".

## Decisions (made without a round-trip; each is cheap to change)

| Decision            | Choice |
|---------------------|--------|
| Command-line key    | `:` opens it empty; `c` opens it prefilled `CUT ` (the old cut box goes) |
| Mnemonics           | the table under "Command line"; the perch command's own name works too |
| Drill key           | `i` on any cell; Enter keeps running steps as it does now |
| Trend               | a new `Trend` column after Headroom: team headroom, last 8 recorded weeks |
| What changed        | one strip above the table: each project's last two recorded weeks |
| Flip                | the team `signal` differs between the last two recorded weeks, both set |
| Alert               | a Textual toast once per project and week, and the Stoplight cell in reverse |

## Rules

- **Team rows only.** Trend, strip, drill and alerts read the `kind: team`
  row of `history.jsonl`. No person row, no name, and nothing from the watch
  (not even a change in the Flags count) appears in any of them.
- **No new simulation.** Every figure is a recorded figure or the difference
  of two recorded figures, the same arithmetic `perch cut` does between the
  last week and today. Nothing re-runs the join.
- **Nothing is sent.** An alert is a toast inside the TUI. No mail, no OS
  notification, no file.
- **Never ranks.** Projects appear in `home.projects()` order everywhere.
- `core/` stays UI-free: no textual, no rich, no click.

## Core: `perch/core/command.py`

The command line's grammar. Pure: text in, perch argv out.

```python
MNEMONICS = {
    "BRD": "board", "MON": "monday", "DOC": "doctor", "FCST": "forecast",
    "WTCH": "watch", "QTR": "quarterly", "CUT": "cut", "HRS": "hours",
    "STAT": "status", "FTCH": "fetch", "DIG": "digest", "MAIL": "emails",
    "WKLY": "weekly", "BUD": "budget",
}
ALL = {"monday", "watch", "quarterly", "status"}  # what ALL accepts
FROM = ("fetch", "board", "weekly", "digest", "emails")  # monday --from

@dataclass(frozen=True)
class Command:
    project: str | None        # None: every project (ALL)
    args: tuple[str, ...]      # perch's argv after the binary

def amount(token: str) -> float: ...
def parse(text: str, projects: Sequence[str], current: str | None) -> Command: ...
```

`parse` splits on whitespace and drops a last token `<GO>` or `GO` (any case).
Then:

1. **Who.** The first token, matched case-insensitively against `projects`,
   is the project (the name as `projects` spells it). `ALL` means every
   project. Otherwise the project is `current` (the cursor's); `current` None
   and no name given is `ValueError("no project: give one, e.g. apollo CUT 700k")`.
2. **What.** The next token, upper-cased, is a mnemonic; failing that,
   lower-cased, a perch command name in `MNEMONICS.values()`. Neither:
   `ValueError` naming the token and listing the mnemonics.
3. **How.** The rest, by command:
   - `cut`: a token with no `:` is an `amount` → `--budget N` (once only); one
     colon → `--leaves TOKEN`; two colons → `--fte TOKEN`. The values are passed
     as typed; `perch cut` validates names and dates.
   - `monday`: at most one token, one of `FROM` (any case) → `--from STEP`.
   - `quarterly`: at most one token → `--quarter TOKEN` (e.g. `2026-Q3`).
   - any other command: no tokens allowed.
   An extra or wrong token is a `ValueError` saying what the command takes.
4. **Build.** `args = (command, "-p", project, *flags)`; with `ALL`,
   `(command, "--all", *flags)`, except `ALL STAT`, which is `("status",)`
   (`perch status` with no `-p` already shows every project). `ALL` with a command not in `ALL` is a
   `ValueError`; `ALL MON STEP` is a `ValueError` too (`perch monday` refuses
   `--from` with `--all`). An empty line is a `ValueError("empty")`.

`amount`: optional `$`, commas dropped, an optional `k`/`m` suffix (any case)
multiplies by 1e3/1e6: `700k` → 700000, `1.2M` → 1200000, `$700,000` →
700000. Not a positive number: `ValueError`. Budget amounts are passed to
`perch cut` as `str(int(value))` when whole, else `str(value)`.

`HRS` builds `("hours", "-p", NAME)` like any command; the TUI opens the editor
for it instead of spawning (see TUI).

## Core: `perch/core/trend.py`

Read-only arithmetic over `history.load(path)` rows.

```python
WINDOW = 8                    # weeks, as `perch weekly` counts them
BARS = "▁▂▃▄▅▆▇█"

def spark(values: Sequence[float]) -> str: ...
def series(rows: list[dict], key: str, window: int = WINDOW) -> dict[str, float]: ...

@dataclass(frozen=True)
class Change:
    before: str                         # week key, e.g. "2026-W39"
    after: str
    signal: tuple[str, str] | None      # (old, new) when it flipped
    deltas: dict[str, float]            # key -> after - before, nonzero only

def change(rows: list[dict]) -> Change | None: ...
def describe(name: str, change: Change | None) -> str: ...
def team_lines(rows: list[dict]) -> list[str]: ...
```

- `spark`: one bar per value, scaled min→max of the values given; all equal
  is all `▄`; fewer than 2 values is `""`. A negative headroom is just a low
  bar.
- `series`: `history.figures(rows, "team", "team", key)` in week order, the
  last `window` weeks.
- `change`: the team rows of the last two recorded weeks (whatever weeks they
  are; a gap is shown in the week keys). None when fewer than two. `signal` is
  set only when both weeks have one and they differ. `deltas` covers
  `headroom`, `budget` and `spent_cost` where both weeks have the key and
  `abs(after - before) >= 0.5`.
- `describe`: `""` when the change is None or empty. Else
  `apollo W39→W40: YELLOW→RED, headroom −$12,000, budget +$50,000` (week keys
  shortened to `Wnn`, signals upper-cased, money as `+$12,000`/`−$12,000`
  with a real minus sign, deltas in the order headroom, budget, spent).
- `team_lines`: the drill text behind Stoplight, Headroom and Trend: the
  latest week's team figures (`signal`, `prob_over` as a percent, `budget`,
  `spent_cost`, `headroom`, `left` hours, `clear_p10/p50/p90`), then one line
  per week of `series(rows, "headroom")` with that week's signal, newest last.
  A missing figure is `—`. No history is `["no week recorded yet: run perch board"]`.

## TUI (`perch/tui.py`)

### Rows

`row(home, name)` keeps its signature and output for existing callers, built
on a new `snapshot(home, name) -> tuple[tuple[str | Text, ...], Change | None]`
that loads `history.jsonl` once and derives the latest team row, the Trend
cell (`spark(series(rows, "headroom").values())`) and the `change` from the
same rows. `COLUMNS` becomes `Project | GitLab | Stoplight | Headroom | Trend |
hours … watch | Flags`. A Stoplight that flipped this week renders in
`reverse` style.

### Command line

The `#flags` Input becomes `#command` (placeholder
`apollo CUT 700k · ALL MON · MON weekly`). `:` opens it empty, `c` opens it
with `CUT `, Escape closes it. On submit: `parse(text, self.names,
self._selected())`; a `ValueError` is an error toast. `hours` moves the cursor
to the project's row and runs `action_hours`; anything else is
`_start(project, " ".join(args), list(args))`, so it gets a run card and
respects `busy`.

### Drill (`i`)

On the cursor's cell, an **info card** in the output pane: a `RunCard` with
no spinner whose subtitle is `info` (a small `RunCard` option, not a second
widget class):

- Project, GitLab: `doctor.project_checks` as `✓ what` / `✗ what → fix`.
- Stoplight, Headroom, Trend: `trend.team_lines`.
- a step cell: its `status()` Cell: state, `when`, and `why` when set.
- Flags: runs `perch watch -p NAME`, as `w` does (the watch stays in the pane).

Drill never needs `_free()`: it reads files only, except Flags, which runs
through `_start` like `w`.

### What changed

A one-line `Static#changes` above the table: `describe(name, change)` for
every project with a non-empty one, joined with `  ·  `, in project order.
Hidden when every project's is empty. Recomputed by `action_refresh` and for
the one row `_finished` refreshes.

### Alerts

After `action_refresh` (so at mount too) and after `_finished`'s row refresh:
for each project whose `change.signal` is set and `(name, change.after)` is
not in `self.alerted`: `notify(f"{name}: stoplight {OLD} → {NEW} ({Wnn})")`,
`severity="error"` when the new signal is red, else `"warning"`, then add the
pair to `self.alerted`. One toast per flip per session.

## Docs

CLAUDE.md architecture: `core/command.py` and `core/trend.py` entries and the
TUI bullet's new keys; README and `docs/reference.md`: the `:` line, the
mnemonic table, `i`, Trend, the strip, alerts.

## Testing

- `test_command.py`: every mnemonic and full name; project first, cursor
  default, `ALL`; `CUT 700k`, `1.2m`, `$700,000`, leaves and fte by colon
  count; `MON weekly` → `--from weekly`; `<GO>` dropped; each refusal
  (empty, unknown mnemonic, no project, two amounts, `ALL CUT`, `ALL MON
  weekly`, `BRD extra`, `MON nope`) raises with a message naming the problem.
- `test_trend.py`: `spark` on rising, flat, single and empty input; `series`
  windows to 8 and skips weeks without the key; `change` None under two weeks,
  flip only when both set and different, deltas only nonzero; `describe`'s exact
  string including the minus sign; `team_lines` on no history and on a seeded
  history; no person name and no word from `test_watch.BANNED` in any output
  given a history with person rows.
- `test_tui.py` (`_spawn` faked): `:` + `apollo CUT 700k` + Enter spawns
  `cut -p apollo --budget 700000`; a bad line toasts and spawns nothing; `c`
  opens prefilled; `HRS` opens the editor path; `i` on Headroom mounts an info
  card with team lines, on a step cell its state, on Project the checks; the
  Trend cell for a seeded multi-week history; the strip text and that it is
  hidden with one week; a flip toasts once across two refreshes and red is
  severity error; existing column-index assertions move for Trend.
