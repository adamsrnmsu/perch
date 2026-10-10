# Install

```bash
git clone https://github.com/adamsrnmsu/perch.git && cd perch && make install
```

perch is the one repo you clone. `make install` clones Budgie and gitboard into
`apps/` (ignored by perch's git; each stays its own repo), installs all three
and puts `perch` and `gitboard` on your PATH. It leaves an app already in
`apps/` alone, so it is safe to re-run. Then:

```bash
perch init apollo      # scaffold projects/apollo/ and its Budgie project
perch doctor           # tools, config, names, freshness; FIX lines say what to run
```

`pyproject.toml` pins Budgie to its GitHub repo by URL (never PyPI, where the
name is not ours); `make install` installs `apps/budgie` editable on top, so
local Budgie edits show up in perch at once.

## Migrating an old workspace

If you have a `perch-home.yaml` beside `projects/` and `budget/`:

1. `git pull` perch, then `make install` (adds HTTPS clones for missing apps and relinks).
2. From the old workspace run `perch doctor`. It prints the exact `mv` commands; run them, then `perch doctor` again to confirm.
3. Create `config.yaml` with `lead: NAME` and move the old `alerts:` block into it.
4. `perch gb pull -p X` once per project so a `.base` exists; `perch gb plan -p X` should then show nothing.
5. Delete `perch-home.yaml`.

Nothing is moved for you.
