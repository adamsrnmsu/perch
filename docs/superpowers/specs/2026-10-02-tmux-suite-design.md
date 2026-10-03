# Instant switching: the suite in a hidden tmux

Date: 2026-10-02
Epic: `perch-a2b`
Status: approved in chat, awaiting spec review
Supersedes the "fresh start on each hop" decision in `2026-10-02-tui-switch-design.md`.

## Problem

Today `P`/`B`/`G` call `os.execvp`: the app you leave dies and the one you go to
cold-starts. Measured on this machine, importing alone takes 2.2-3.9 s for
`perch.tui`, 1.8-4.6 s for `budgie.tui` and 1.6 s for `gitboard.cli`, and
gitboard then refetches from GitLab. Every hop also throws away the cursor, the
tab and any drill. That breaks the flow the suite is after: a Bloomberg
terminal, where every screen is already running and switching is instant.

## Goal

The three TUIs stay running side by side. A hop is one key, takes well under
100 ms, and lands where you left that app. The project selected in perch follows
the hop.

Success: run `perch suite`, select a project, press `G`. gitboard is there at
once, already fetched. Move the cursor, press `P`, press `G` again: same board,
same cursor, no fetch. Close the terminal window, run `perch suite` again:
everything is where it was.

## Decisions

- **tmux, fully hidden.** tmux is fine as a dependency; its learning curve is
  not. Nobody types a tmux command or learns a tmux key. The only keys are the
  apps' own: `P`/`B`/`G` to hop, `q` to quit.
- **Keep running when the terminal closes.** Closing the window detaches; the
  next `perch suite` reattaches instantly. The cost, accepted: the apps keep
  running in the background until you quit them.
- **A private tmux.** The suite runs on its own socket (`tmux -L pi`) and
  ignores `~/.tmux.conf`, so anyone's own tmux sessions and config are untouched.
- **Copied, not shared.** As with `PI_SUITE` today, each app carries its own copy
  of the hop. gitboard and Budgie still do not depend on perch.
- **Outside the suite nothing changes.** Plain `perch tui`, `budgie tui` and
  `gitboard tui` keep the exec-on-hop behaviour.

## Starting: `perch suite [-p NAME]`

`perch/core/suite.py` builds the tmux argv lists (pure, like `core/steps.py`:
nothing there executes). `perch suite` in `cli.py` runs them.

1. `tmux` not on PATH: exit 1 with `needs tmux: brew install tmux`. The
   commands below need tmux 3.2 or newer (`terminal-features`, `-e` on
   `new-window`/`respawn-window`); this machine has 3.7c.
2. `tmux -L pi has-session -t pi` succeeds: the suite is running. Exec
   `tmux -L pi attach -t pi` (with `TMUX` removed from the environment, so this
   works from inside someone's own tmux too). `-p` is ignored here; pick the
   project in perch.
3. Otherwise build the map with `suite_map(home, name)` (`name` from `-p`, else
   the first project; no project at all: the same error `perch tui` gives) and
   start the server with one chained command. The options come first: tmux
   applies `default-terminal` when a pane is spawned, so a window made before
   it would run with the wrong `TERM`.

   ```
   tmux -L pi -f /dev/null
     start-server
     ; <the options below>
     ; new-session -d -s pi -n perch -c CWD -e PI_SUITE=MAP ARGV...
     ; set-option -w -t pi:=perch @entry ENTRY
     ; new-window -d -n budgie -c CWD -e PI_SUITE=MAP ARGV...
     ; set-option -w -t pi:=budgie @entry ENTRY
     ; new-window -d -n gitboard ...   (same)
     ; select-window -t pi:=perch
   ```

   then exec the attach from step 2. Budgie and gitboard start straight away
   (`-d`), so gitboard's fetch happens while you look at perch and the first
   hop is already warm.

   If `suite_map` raises (a bad `perch.yaml` or `budgie_project`), start the
   session with the perch window only, its `PI_SUITE` unset, and print the
   error. perch opens as `perch tui` would, and hops create the other windows
   later (step 2 of the hop). Warming them up first is a nicety; it never
   stops the suite starting.

`ENTRY` is `json.dumps(entry, sort_keys=True)` of that app's `{"cwd", "argv"}`.
It is how a window says what it is running (see Hopping).

### The options (no config file)

Sent as `set-option` commands in the chain above, so there is no file to
ship or find. `escape-time`, `focus-events` and `terminal-features` are server
options (`-s`); `remain-on-exit` is a window option (`-gw`); the rest are
session options (`-g`).

| Option | Value | Why |
|---|---|---|
| `status` | `off` | no tmux bar |
| `prefix`, `prefix2` | `None` | tmux never takes a key |
| `escape-time` | `0` | Esc is not delayed in Textual |
| `focus-events` | `on` | apps learn when their window comes to the front |
| `default-terminal` | `tmux-256color` | colours as outside tmux |
| `terminal-features` | append `,*:RGB` | true colour |
| `remain-on-exit` | `off` | a quit app's window closes |
| `destroy-unattached` | `off` | closing the terminal keeps the suite |

Mouse stays `off`: the apps still receive mouse events, and tmux does no
selection or scrolling of its own.

## Hopping

### Am I in the suite?

```python
def in_suite() -> bool:
    return os.path.basename(os.environ.get("TMUX", "").split(",")[0]) == "pi"
```

`$TMUX` is `socket-path,pid,session`; the socket is named after `-L pi`. No new
environment variable to carry through respawns.

### The hop (same rule in all three apps)

`hop(name, entry, env)`: `entry` is the target's `{"cwd", "argv"}` from this
app's `PI_SUITE`; `env` is that `PI_SUITE` string. Every call names the server and session outright (`tmux -L pi ... -t pi:=NAME`)
rather than leaning on `$TMUX`.

1. `tmux -L pi list-windows -t pi -F '#{window_name}<TAB>#{@entry}'`: one line
   per window. (Probed: `show-options -q` exits 0 for a missing window too, and
   `display-message` falls back to the current window, so neither can tell
   "quit" from "running".)
2. No line for NAME (the app was quit): `new-window -t pi: -n NAME -c CWD
   -e PI_SUITE=ENV ARGV... ; set-option -w -t pi:=NAME @entry ENTRY`.
   `new-window` selects the new window.
3. NAME's `@entry` is the same `ENTRY`: `select-window -t pi:=NAME`. This is
   the instant path.
4. Anything else (another project, or no `@entry` at all): `respawn-window -k
   -t pi:=NAME -c CWD -e PI_SUITE=ENV ARGV... ; set-option -w -t pi:=NAME
   @entry ENTRY ; select-window -t pi:=NAME`. Only the target restarts.

Probed with tmux 3.7c: a JSON `@entry` comes back byte-identical, and a `cwd`
or argv element with spaces, quotes or `$` arrives intact.

A failing tmux call shows its stderr in the app (a toast in perch and Budgie,
the status line in gitboard) and the app stays where it is.

### Who passes which entry

- **perch** builds the map for the selected project, as today, and hops with
  that map's entry. perch's own entry has no project in it, so a hop *to* perch
  always takes step 3: perch never restarts.
- **Budgie and gitboard** hop with the `PI_SUITE` they were started with. That
  map is the project perch last sent them, so `B` from gitboard and `G` from
  Budgie stay on that project.
- In the suite, perch hops even while a command is running: nothing exits, so
  the busy check (which protects a child from being killed) applies only
  outside the suite.

### Where it goes in each app

- **perch** (`tui.py`, `action_switch`): in the suite, set nothing, call the
  hop, stay running. Outside, as today.
- **Budgie** (`tui.py`, `action_switch`): in the suite, hop instead of
  `self.exit(target)`.
- **gitboard** (`cli.py`, the `SWITCH` branch of the key loop): in the suite,
  hop and keep the `Live` loop going instead of returning the target.

Each repo's copy is `in_suite()` plus `hop()`, about 25 lines, beside its
existing `suite_entry`/`switch`.

## Quitting

- `q` in **perch**, in the suite: after `run()` returns, `perch tui` runs
  `tmux -L pi kill-session -t pi`. The whole suite closes and the terminal is back at
  the shell.
- `q` in **Budgie or gitboard**: the app exits as today, its window closes
  (`remain-on-exit off`) and tmux shows another window. Its key reopens it
  later (step 2 above).

## Refresh when you hop back

tmux sends a focus-in sequence when a window comes to the front, because
`focus-events` is on. Textual already turns on focus reporting and posts
`events.AppFocus`.

Probed on 2026-10-02 with tmux 3.7c and Textual 8.2.8: a Textual app in one
window and an empty second window, with a client attached through a pty that
sent the terminal focus-in sequence. Each `select-window` delivered `AppBlur`
to the app as it was left and `AppFocus` as it came back. It depends on the
outer terminal reporting focus to tmux; Terminal.app, iTerm2, Ghostty and
the VS Code terminal do. Without that report the app got one `AppFocus` and
then nothing, so on a terminal without focus reporting the refresh simply
does not happen and `r` still works.

- **perch:** `on_app_focus` starts a refresh in a worker. The hop is instant
  and the cells update about a second later; the cursor stays put. Measured
  today: one project's `snapshot` takes 1.4 s on the UI thread (cold), so the
  focus refresh gets its own thread worker. `perch-li8` (the same for `r` and
  after a run) stays a separate bead.
- **Budgie:** `on_app_focus` calls `recalculate()` only when an input file in
  the project is newer than the last calculation. A 10,000-iteration forecast on
  every hop would undo the point of the work.
- **gitboard:** no automatic refresh. Its refresh is a GitLab refetch; `r`
  stays manual.

Only focus-in triggers a refresh. There is no timer.

## Known limits

tmux strips one level of backslashes from an `-e` value (probed), so a path
holding a backslash reaches the other apps' `PI_SUITE` mangled. macOS paths
practically never hold one; not handled.

If you switch budget inside Budgie, or board inside gitboard (`b`), that app's
`PI_SUITE` still names the project perch sent, so its `B`/`G` hops follow
perch's project, not the one now on screen. Accepted; a later change can have
those switches rewrite the app's own map.

## Out of scope

- Splits or several apps on screen at once.
- Starting the suite from Budgie or gitboard. `perch suite` is the one entry
  point.
- `make suite` in `suite.mk`: a one-line target can follow once `perch suite`
  exists.

## Testing

Each repo monkeypatches `subprocess.run` (and `os.execvp` for the launcher) to
record argv, and sets `TMUX` by hand.

- **`in_suite`:** true for `/tmp/tmux-501/pi,123,0`; false for the `default`
  socket and for unset `TMUX`.
- **hop, per repo:** a missing window gives `new-window` with the entry's cwd,
  argv and `PI_SUITE`; a matching `@entry` gives only `select-window`; a
  different `@entry` gives `respawn-window -k` with the new cwd and argv; a
  failing tmux call surfaces stderr and changes nothing.
- **perch, outside the suite:** `P`/`B`/`G` still exec as today; the busy
  refusal still applies. Inside, busy does not refuse.
- **`perch suite`:** no tmux gives the message and exit 1; a running session
  execs `attach` with `TMUX` stripped; a cold start runs one chained command
  holding three windows, the option table and their `@entry` values, then
  execs `attach`.
- **Budgie focus:** an untouched project does not recalculate on focus; a
  touched input file does.
- **perch focus:** focus starts the refresh worker (after `perch-li8`).

Manual, in a real terminal: the success path in Goal; colours match outside
tmux; Esc is immediate in Budgie's forms; `q` in perch leaves a clean shell
(input echoes, no leftover screen); `~/.tmux.conf` and existing tmux sessions
are untouched.

## Work split

Epic `perch-a2b`:

1. perch: `core/suite.py` (options, launch chain, `in_suite`, hop argv),
   `perch suite`, perch's hop and suite quit. Defines the contract.
2. Budgie: `in_suite`, hop, focus recalculate. Blocked by 1.
3. gitboard: `in_suite`, hop in the key loop. Blocked by 1.
4. perch: focus refresh in a worker. Blocked by 1.
5. perch docs: `CLAUDE.md` architecture line for `core/suite.py`, README, the
   reference. Blocked by 1.
