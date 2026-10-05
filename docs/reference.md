# Reference

## CLI

Generated at build time from the click commands.

```{eval-rst}
.. click:: perch.cli:cli
   :prog: perch
   :nested: full
```

## Modules

Everything under `perch.core` is UI-free; `perch.cli` is a thin adapter over it.

```{eval-rst}
.. automodule:: perch.core.config
   :members:

.. automodule:: perch.core.workspace
   :members:

.. automodule:: perch.core.steps
   :members:

.. automodule:: perch.core.doctor
   :members:

.. automodule:: perch.core.status
   :members:

.. automodule:: perch.core.board
   :members:

.. automodule:: perch.core.estimates
   :members:

.. automodule:: perch.core.money
   :members:

.. automodule:: perch.core.rate
   :members:

.. automodule:: perch.core.join
   :members:

.. automodule:: perch.core.accuracy
   :members:

.. automodule:: perch.core.history
   :members:

.. automodule:: perch.core.cut
   :members:

.. automodule:: perch.core.weekly
   :members:
   :undoc-members:

.. automodule:: perch.core.watch
   :members:

.. automodule:: perch.core.trend
   :members:

.. automodule:: perch.core.sources
   :members:

.. automodule:: perch.core.moves
   :members:

.. automodule:: perch.core.detail
   :members:

.. automodule:: perch.core.events
   :members:

.. automodule:: perch.core.tape
   :members:

.. automodule:: perch.core.asof
   :members:

.. automodule:: perch.core.alerts
   :members:

.. automodule:: perch.core.command
   :members:

.. automodule:: perch.core.quarterly
   :members:

.. automodule:: perch.core.report_mail
   :members:
```

## Commands

### perch suite

```bash
perch tui          # starts the suite when tmux is installed
perch suite        # the same, explicitly; -p apollo opens on apollo
perch tui --no-suite   # perch alone
```

perch, Budgie and gitboard open side by side. `B` and `G` in perch (and `P`,
`B`, `G` in the others) jump between them at once, and each stays where you
left it. Close the terminal and the suite keeps running: `perch tui` again
picks it up. `q` in perch closes everything. It runs on tmux, which you never
have to touch (`brew install tmux` once). If the suite ever wedges (an app
hangs, or tmux was upgraded while it ran), `tmux -L pi kill-server` resets it;
`perch tui` then starts fresh.

Inside the suite, without tmux, or with `--no-suite`, `perch tui` is just the
perch TUI. `perch suite` without tmux says `needs tmux: brew install tmux`. A project whose config
is broken opens perch alone; the others open on the first hop.
