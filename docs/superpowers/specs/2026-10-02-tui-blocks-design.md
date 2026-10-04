# TUI blocks: real widgets instead of markdown in the output pane

The output pane shows each command's stdout as text. gitboard's `stats`
(behind `perch fetch` and `perch monday`) prints about twenty raw markdown
tables; Budgie prints a figlet banner and rich tables; perch prints rich tables
and markdown bullets. The pane reads as noise.

This spec adds one small output format, **blocks**, that every pi tool can
print when the TUI asks, and a renderer in the TUI that turns each block into a
widget. Approach A from the 2026-10-02 brainstorm; B (TUI builds views from
each tool's internals) and C (rich text only) were rejected.

## Decisions

| Decision | Choice |
|---|---|
| How the TUI asks | env `PI_BLOCKS=1` on every spawned command; children inherit it, so `monday` → `gitboard stats` asks too |
| Wire format | JSON Lines on stdout, one block per line, marked `"pi": 1` |
| Mixed output | any line that is not a block is plain text, shown as today; tools convert one report at a time |
| Formatting | the tool formats every shown value (money, %, dates); only `bars` carry numbers |
| One source per report | each report is built once as blocks; its markdown or rich output is rendered from those blocks |
| Full screen | `o` maximizes the newest card (Textual's `screen.maximize`); Escape restores |
| Phases | 1: format + TUI renderer + gitboard `stats`. 2: perch's own commands. 3: Budgie. Each later phase gets its own short plan |

## The format (contract)

One JSON object per stdout line. A line is a block when it parses as a JSON
object with `"pi": 1` and a known `"block"`; anything else is plain text, so a
block the TUI does not know degrades to its raw line, never an error.

```json
{"pi": 1, "block": "heading", "level": 2, "text": "Open"}
{"pi": 1, "block": "text", "text": "Trend: cycle median 4.0 ▼ (prev 5.0)", "tone": "dim"}
{"pi": 1, "block": "figures", "items": [{"label": "Open", "value": "41", "note": "6 unassigned"}, {"label": "Done", "value": "7 ▲", "note": "prev 4", "tone": "good"}]}
{"pi": 1, "block": "table", "title": "Time", "columns": ["days", "median", "mean", "n"], "rows": [["cycle", "4.0", "5.2", "7"]], "align": ["l", "r", "r", "r"]}
{"pi": 1, "block": "bars", "title": "By column", "items": [["Review", 2], ["Backlog", 1]]}
{"pi": 1, "block": "list", "items": ["Payments: 2 open, due 2026-10-15"]}
```

| block | fields | required |
|---|---|---|
| `heading` | `level` 1-3, `text` | all |
| `text` | `text`, `tone` | `text` |
| `figures` | `items`: `label`, `value`, `note`, `tone` | `items`, each `label` + `value` |
| `table` | `title`, `columns`, `rows` (lists of strings), `align` (`l`/`r` per column) | `columns`, `rows` |
| `bars` | `title`, `items` (`[label, number]`), `unit` | `items` |
| `list` | `items` (strings) | `items` |

Any block may carry `md`: the exact markdown a tool prints for it in markdown
mode, for the few places (gitboard's bold headline) where a generic rendering
cannot reproduce today's text. The tool's `to_md` prefers it; the TUI ignores
it.

`tone` is one of `good`, `warn`, `bad`, `dim`, or absent. Strings may not hold
markup or ANSI; the TUI styles them. The format lives in this file; gitboard and
Budgie link to it from their CLAUDE.md. Each repo writes its own tiny emitter
(`perch never imports another app's code`), and each has a contract test that
its blocks satisfy the table above.

## gitboard (phase 1)

- `src/gitboard/blocks.py`: constructors that return the dicts above, `emit(blocks)`
  (one `json.dumps(..., ensure_ascii=False)` line each, stdout), and
  `to_md(blocks) -> str`, the markdown gitboard prints today. `bars` render as
  the current `| name | n |` table; `figures` as the current bold headline line.
- `stats.team_blocks(summary, weekly=None) -> list[dict]` builds the team
  report. `render_team_md(summary, weekly)` becomes `to_md(team_blocks(...))`
  and stays **byte-identical**: capture its output on the test fixtures and on
  a real dump before the refactor and assert equality after. digest's
  `team.md`, the emails and the html keep working unchanged.
- `stats` CLI: with `PI_BLOCKS=1` it emits `team_blocks` instead of printing the
  markdown. `--json` and `--weeks` are unchanged. Logs stay on stderr.
- The counts tables (`By column`, `By epic`, `By story`, `By type`, `By
  assignee`, and the done-by ones) become `bars`; `Time`, `Verification` and
  the flow/late/blocker tables stay `table`; the headline becomes `figures`.

## perch TUI (phase 1)

- `_start` adds `PI_BLOCKS=1` to the env it already passes.
- `RunCard` becomes a container. Plain lines keep collecting in one text
  widget, as now; a block line mounts a widget after it, and the next plain
  line starts a new text widget below. Blocks are parsed in `perch/core/blocks.py`
  (`parse(line) -> dict | None`, validation per the table; UI-free) and drawn in
  `tui.py`:
  - `heading`: level 1 bold, 2 bold with a rule, 3 bold dim.
  - `text`: the tone's colour (`good` green, `warn` yellow, `bad` red, `dim` dim).
  - `figures`: a wrapping row of small tiles: value bold, label and note dim
    below, the value in the tone's colour.
  - `table`: a `DataTable` (no cursor, zebra stripes) whose height fits its rows
    up to 12, then scrolls; title above in bold.
  - `bars`: one line per item: label padded to the longest, a bar of `█`
    scaled to the largest value and the card's width, the number.
  - `list`: `•` lines.
- `o` maximizes the newest card; Escape (Textual's minimize) restores it.
- A run's status and FIX lines behave as now. A card still shows `info` cards
  from `i` the same way.

## Phases 2 and 3 (outline, own plans later)

- **perch**: `board`, `cut`, `status`, `doctor`, `watch`, `weekly` build blocks
  once; the CLI renders them with rich (terminal) or emits them (`PI_BLOCKS`).
  `perch/core/blocks.py` gains constructors; the rich renderer lives in `cli.py`.
  `_run`'s step header becomes a `heading` block.
- **Budgie**: `forecast`, `status` (perch `budget`), `emails`; with `PI_BLOCKS`
  no banner and no RichHandler lines on stdout.

## Testing

- gitboard: `test_blocks.py` (each constructor's dict, `emit` writes one line
  per block, `to_md` for each block type); the byte-identical golden test for
  `render_team_md`; `stats` with `PI_BLOCKS=1` prints only valid block lines
  (each passes the contract check) and with it unset prints the markdown as
  before.
- perch: `test_blocks.py` for `parse` (each type; missing required field, wrong
  `pi`, unknown block, non-object JSON and plain text all give None);
  `test_tui.py` with `_spawn` faked to yield a mix of text and block lines: a
  table block mounts a DataTable with the rows, bars render scaled lines, figures
  tiles show their values, a bad line stays text, `o` maximizes the newest card,
  the env passed to `_spawn` holds `PI_BLOCKS=1`.
