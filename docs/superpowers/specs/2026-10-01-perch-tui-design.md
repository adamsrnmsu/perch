# perch tui: a dashboard and launcher over the perch commands

Date: 2026-10-01. Status: design approved in conversation.
Bead: perch-s7p. Builds after perch-mo4 (cut) and perch-vgo (watch).

## Purpose

`perch tui` puts every project in one view: how fresh its data is, where its
budget stands, and whether the watch has flagged anything. Single keys run the
perch commands on the selected project.

## Layout

- **Left: a projects table** (Textual `DataTable`), one row per project:
  - the project name;
  - its `gitlab_project`;
  - the stoplight and the headroom;
  - how old the dump and `weekly.csv` are;
  - the number of watch flags.

  The stoplight and headroom come from the latest `team` row in that
  project's `history.jsonl`, so opening the TUI never runs a simulation. A
  project with no history shows "—". The ages come from
  `perch.core.doctor.freshness`. The flag count comes from `perch.core.watch`;
  it shows "—" when the watch cannot run (for example, not enough history).
- **Right: an output pane** (Textual `Log`) for the last action's output, each
  line prefixed with the project name.
- **Footer:** the key bindings.

## Keys (on the selected project)

| Key | Action |
|---|---|
| `b` | `perch board` |
| `m` | `perch monday` |
| `a` | `perch monday --all` |
| `d` | `perch doctor` |
| `f` | `perch forecast` |
| `w` | `perch watch` |
| `Q` | `perch quarterly` |
| `c` | `perch cut`: first opens a one-line input for its flags (`--leaves Bob:2026-11-01 --budget 700000`) |
| `h` | `perch hours`: suspends the app, opens `$EDITOR`, then resumes and refreshes |
| `r` | refresh the table |
| `?` | help |
| `q` | quit |

- **One action at a time.** A key pressed while one runs shows "busy: <action>".
- **Background running.** The command runs as a subprocess in a Textual worker,
  and its output streams into the pane.
- **Refresh after.** The table refreshes when the command finishes.

## Code

- `perch/tui.py` holds the Textual app (`PerchTUI`). It is display and key
  handling only.
- **How commands are built:**
  - For `board`, `monday`, `doctor`, `forecast`, `watch`, `quarterly` and `cut`,
    each key builds an argv for `perch <command> -p <name> [args]`, using the
    `perch` script next to `sys.executable`. It goes through one module-level
    `_spawn(argv, cwd) -> Iterator[str]`, which tests replace.
  - `h` reuses `perch.core.steps.hours` and runs it inside `App.suspend()`.
- **How the table is built:**
  - `Home.projects()` lists the projects;
  - `load_config(require_dump=False)` loads each project's config;
  - `doctor.freshness` gives the ages;
  - a `history.latest_week` reader gives the stoplight and headroom;
  - `watch` gives the flag count.

  A project that fails to load shows its error in the row, never a crash.
- `perch/cli.py` gets `tui`, which starts the app in the current workspace.
- **Dependency:** perch's `pyproject.toml` declares `textual` (today it only
  arrives through Budgie).

## Testing

Textual's `App.run_test()` with a pilot, against `build_home` in the test
world:

- **The table:** it renders every project, and the stoplight and headroom match
  a history row the test wrote.
- **Each key:** with `_spawn` faked, every key produces the right argv for the
  selected project, and moving the cursor changes the project.
- **`c`:** the input text is split into flags and passed through.
- **`h`:** the suspend and editor are faked; the table refreshes afterwards.
- **Busy:** a second key while one runs shows "busy".
- **A broken project:** a malformed `perch.yaml` shows as an error row, not a
  crash.

## Out of scope

- Editing board YAML (gitboard's TUI does that).
- Budgie's own screens (`budgie tui`).
- Mouse-only features.

## Changes during build

- `a` runs `perch monday --all` with no `-p`: the CLI refuses `-p` with
  `--all`. Its output lines are prefixed `all:`.
- The flag count shows "—" when the watch raises (no dump, a bad config) and
  when it has under 4 weeks of history (every signal then reads "not enough
  history"); otherwise the count, 0 included.
- The ages are `doctor.freshness`'s last-written times, as `perch doctor`
  prints them.
- `?` opens Textual's built-in key help panel.
- `c` with an empty line runs `perch cut -p NAME` (since the last recorded
  week).
- Escape closes the `cut` input without running anything.
- A row catches any exception, not only the config errors: the table is a
  display boundary, so one bad project shows `error: <type>: <message>`.
- `perch.core.watch.Watch` carries `weeks` (the prior weeks behind it) and
  `thin`, which the flag column reads.
- The tests are plain functions running `App.run_test()` under
  `asyncio.run`, so perch needs no pytest-asyncio.
