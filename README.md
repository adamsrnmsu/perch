# perch

Where the budgie sits to watch the board.

perch joins two tools that each know half the story. **gitboard** knows the
work: open and closed issues and who holds them. **Budgie** knows the money:
hourly cost, planned hours, hours booked, the budget. perch answers what
neither can alone: *what does the open board cost, against the hours and the
budget that are left?*

It owns the join and the views, nothing else. Budget math stays in Budgie,
board logic stays in gitboard. perch never calls GitLab and never sends mail.

## Install

```bash
git clone https://github.com/adamsrnmsu/perch.git && cd perch && make install
```

perch is the one repo you clone. `make install` clones Budgie and gitboard into
`apps/` (ignored by perch's git; each stays its own repo with its own remote
and beads), installs all three and puts `perch` and `gitboard` on your PATH. It
leaves an app already in `apps/` alone, so it is safe to re-run.

`pyproject.toml` pins Budgie to its GitHub repo by URL (never PyPI, where the
name is not ours); `make install` then installs `apps/budgie` editable on top,
so local Budgie edits show up in perch at once.

## Docs

The full guide (the suite, every command, the workspace, listen, the watch) is in
`docs/`: `make docs`, then open `docs/_build/html/index.html`. Design notes live in
`docs/superpowers/`.

## Development

```bash
make test          # perch only; make test-all runs all three suites
make lint
make format
```
