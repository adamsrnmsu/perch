# Switching between the suite's TUIs

Date: 2026-10-02
Status: implemented (perch-2gr); in-suite hops superseded by 2026-10-02-tmux-suite-design.md

## Goal

From any of the three TUIs (perch, Budgie, gitboard), jump straight to
either of the others and back, without quitting and typing a command.

Success: in `perch tui`, select a project, press `G`, and gitboard's board for
that project opens. Press `B` there and Budgie opens on that project's budget.
Press `P` there and perch is back. Every hop is one keypress.

## Decisions

- **In-app keys, not tmux.** The user chose an in-app switch key over a tmux
  session.
- **Fresh start on each hop.** A switch replaces the running process
  (`os.execvp`), so the app you return to starts over: gitboard refetches, Budgie
  opens on its first tab, perch's cursor goes back to the top. The user accepted
  this. No state is lost: Budgie writes plan rows to disk as they are entered,
  and gitboard's staged edits live in the board YAML.
- **perch is the hub.** Only perch knows where the others live, so only perch
  writes the switch map. Budgie and gitboard only read it.

## Keys

| Key | Opens    |
|-----|----------|
| `P` | perch    |
| `B` | Budgie   |
| `G` | gitboard |

The same three keys work in all three apps. Pressing the current app's own
letter does nothing. Each key is shifted, and the shifted letter is unused in
every app today (perch binds `Q`, which is not one of them).

gitboard lowercases every key before dispatch (`cli.py`, `k = _key().lower()`),
so today `P`, `B` and `G` act as `p` (plan), `b` (switch board) and `g` (guide).
The switch check reads the raw key *before* that lowercasing. As a result, Shift
(or Caps Lock) + p/b/g in gitboard now switches apps instead of running the
lowercase action. That is acceptable: the lowercase keys are unchanged.

Every app lists the keys in its help: perch and Budgie through Textual
`BINDINGS` (shown in the footer), gitboard in `help_panel` (the panel `?` opens).

## The switch map: `PI_SUITE`

`PI_SUITE` is an environment variable holding JSON: for each app, the
directory to run it from and its argv.

```json
{
  "perch":    {"cwd": "/Users/me/work/pi",                         "argv": ["/Users/me/Documents/tools/perch/bin/perch", "tui"]},
  "budgie":   {"cwd": "/Users/me/work/pi/budget/apollo",           "argv": ["/Users/me/Documents/tools/perch/bin/budgie", "tui"]},
  "gitboard": {"cwd": "/Users/me/Documents/git/pi_suite/remote-gitboard", "argv": ["gitboard", "tui", "group/apollo"]}
}
```

The `cwd` matters because every app finds its config by walking up from the
working directory.

### perch writes it

When `P`/`B`/`G` is pressed in perch, perch builds the map from its `Home` and
the selected project's `perch.yaml`:

- `perch`: cwd `home.root`, argv `[_bin_dir()/perch, "tui"]`.
- `budgie`: cwd the project's `budgie_project`, argv
  `[_bin_dir()/budgie, "tui"]`. That is the Budgie installed in perch's venv,
  the same one perch imports.
- `gitboard`: cwd `home.gitboard_dir`, argv `["gitboard", "tui"]`, plus the
  project's `gitlab_project` when one is set. Without it, gitboard falls back to
  `gitboard.toml`'s `project`.

perch then sets `os.environ["PI_SUITE"]` and switches.

perch refuses the switch, with a line in its log pane, when:
- no project exists or none is selected,
- a command is still running (`busy`). Exiting would kill the running child.

### Budgie and gitboard read it

Each one carries the same small function (copied, not shared: gitboard does not
depend on Budgie):

```python
def switch_to(name: str) -> str | None:
    """Exec the named app from $PI_SUITE. Returns why not, or never returns."""
```

- `PI_SUITE` unset, not valid JSON, or missing `name`: return
  `"start from perch tui to switch apps"`. The app shows that message and
  carries on.
- Otherwise: `os.chdir(cwd)`, then `os.execvp(argv[0], argv)`. The environment,
  `PI_SUITE` included, passes through unchanged, so later hops keep working.

The process is replaced, not forked, so hops never stack up.

perch's switch goes through its own copy of the same chdir-and-exec step after
building the map.

## Exiting cleanly before exec

The terminal must be restored before `execvp`, or the next app inherits a
half-drawn alternate screen and raw-mode tty.

- **Textual (perch, Budgie):** the key action validates the target, then calls
  `self.exit(name)`. The `run` wrapper calls `switch_to` with what `run()`
  returns, after Textual has torn the screen down. perch's `on_unmount` already
  stops any child, and the busy check above means there is none.
- **gitboard:** the key returns the target out of the `Live` loop. The `with Live`
  block exits (restoring the screen), and `_key`'s `finally` has already
  restored termios. `tui` then calls `switch_to` with the returned name.

Validate *before* exiting: a switch that cannot happen (no `PI_SUITE` entry)
shows its message in the app and leaves it running, instead of quitting to a
shell.

## Out of scope

- **Starting the hop chain from Budgie or gitboard.** Launched on their own, with
  no `PI_SUITE`, `P`/`B`/`G` only show the "start from perch tui" message. If that
  matters, `suite.mk`'s `tui` and `budget-tui` targets can export a `PI_SUITE`
  later.
- **Keeping state across hops.** That needs tmux or a supervisor process.

## Testing

One test per repo, with `os.execvp` and `os.chdir` monkeypatched to record
their arguments:

- **perch:** a fixture home with one project. Building the map gives the
  expected cwd/argv for all three apps, and `gitlab_project` lands in
  gitboard's argv. A busy app refuses to switch.
- **budgie, gitboard:** with `PI_SUITE` set, `switch_to("perch")` chdirs and
  execs the recorded argv. With it unset, it returns the message and execs
  nothing.

Manual check: the success path in **Goal**, run in a real terminal. After each
hop, the terminal must be clean (no leftover screen, input echoes normally after
quitting).

## Work split

One epic in perch, one bead per repo:

1. perch: `PI_SUITE` builder, keys, exec. Defines the contract.
2. budgie: `switch_to`, keys. Blocked by 1.
3. gitboard: `switch_to`, raw-key check, help panel line. Blocked by 1.
