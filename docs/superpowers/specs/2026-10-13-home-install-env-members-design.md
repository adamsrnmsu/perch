# Home install, per-project .env, members, title limits

Epic: perch-w41. Date: 2026-10-13. Repos: perch, Budgie, gitboard.

## What the lead asked for

1. Every virtualenv lives in the perch checkout. Budgie's and gitboard's own
   install detects whether it sits in `perch/apps/` and, if so, installs into
   perch's; installed alone, each keeps its own.
2. Installs work offline and on a machine with an old setuptools.
3. Tokens live under each project: `projects/NAME/.env` by default, so two
   projects can use different keys (and different GitLab hosts).
4. No `glpat-` in placeholders; they read `<key-from-gitlab>`.
5. GitLab usernames are found per project and kept up to date as projects
   are made.
6. Issue titles, milestone titles and perch project names: refused over 255
   characters, nudged to stay under 100.

## Constraints that shape it

- On this machine a `.pth` file inside a repo picks up the macOS `hidden`
  flag and `site.py` skips it, so editable installs stop importing a few
  seconds after they succeed (Budgie Makefile, gitboard CLAUDE.md). That is
  why the venvs live in `~/Documents/tools` today. Moving them into the
  checkout is only safe if nothing depends on a `.pth`.
- `setuptools>=42` is not the real floor: a pyproject-only `[project]` table
  needs setuptools 61 to build and an editable install needs 64. Online, pip's
  build isolation downloads a new one and nobody notices; offline it cannot,
  and the install fails.
- perch never calls GitLab. Anything that talks to GitLab is gitboard's.

## 1. Install: one venv in perch home, nothing built

The three apps run from their source trees on `PYTHONPATH`, the way gitboard
already runs. No package of ours is ever built or installed, so there is no
`.pth`, no build backend and no setuptools requirement on the install path.

- **Venv**: `perch/.venv` (already gitignored), one for all three apps. perch
  imports Budgie in-process, so those two must share one anyway; gitboard's
  dependencies do not overlap in a way that conflicts.
- **Python**: 3.11 or newer (`tomllib`; gitboard already requires it). `make
  install` checks and says so in one line.
- **Dependencies**: `scripts/install_env.py` (stdlib, `tomllib`) prints the
  `dependencies` plus the `dev` and `docs` extras of the three
  `pyproject.toml` files, one per line, skipping `budgie @ git+...` (the local
  checkout is on `PYTHONPATH` instead). `make install` writes them to
  `.venv/requirements.txt` and runs `pip install -r` on it.
- **Offline**: `PIP_NO_INDEX=1 PIP_FIND_LINKS=/path/to/wheels make install`.
  pip reads those variables itself; nothing new in the Makefile. The
  `wheels/` recipe in gitboard's `docs/airgap.md` gets the perch deps added.
- **`PYTHONPATH`** for every run: `perch:perch/apps/budgie:perch/apps/remote-gitboard/src`
  (absolute). One value, so any app can be started the same way.
- **Commands**: `scripts/install_env.py wrappers` writes `perch`, `budgie` and
  `gitboard` into `perch/.venv/bin`, each a two-line `sh` script:
  `exec env PYTHONPATH=... perch/.venv/bin/python -c '...from MODULE import
  FUNC...' "$@"`, built from each app's `[project.scripts]`. They sit where
  console scripts would, so `cli._bin_dir()` (the venv's `bin`) and every
  Step that runs `bin_dir/perch` or `bin_dir/budgie` keep working unchanged,
  and the wrapper sets `PYTHONPATH` itself, so a tmux window with a clean
  environment still works. `make link` symlinks the three into
  `~/.local/bin` with `ln -sf` (replacing today's links into the old venv
  and gitboard's old wrapper file).
- **How perch starts gitboard**: `steps.gitboard`, `tui.suite_map` and
  doctor stop naming `apps/remote-gitboard/.venv/bin/python` and run
  `home.venv_bin / "gitboard"` (a new `Home.venv_bin` property:
  `root/.venv/bin`).
- **setuptools floor**: `>=61` in perch's `pyproject.toml` (the first that
  reads `[project]`, for a hand-run `pip install .`) and `>=64` in Budgie's
  (its standalone install is editable, which needs PEP 660). `make install`
  inside perch never builds, so it needs neither.
- **Budgie and gitboard Makefiles** detect perch home with perch's own rule
  plus the name: `../../pyproject.toml` exists, names `perch`, and `../../apps`
  is a directory.
  - Inside perch: `VENV` is perch's `.venv`; `make install` runs
    `$(MAKE) -C <perch> install`; `test`, `lint`, `docs` run with that venv
    and `PYTHONPATH` naming the app's source (gitboard already does).
  - Standalone: unchanged (Budgie `~/Documents/tools/budgie`, gitboard
    `.venv`).
- **Docs**: perch `README`/`docs/install.md`, Budgie and gitboard
  `CLAUDE.md` (the "Run the suite as ~/Documents/tools/perch/bin/pytest" line,
  the editable-install notes), perch `CLAUDE.md` Commands section.
- **Old installs**: `perch doctor` warns when `~/Documents/tools/perch` or
  `~/Documents/tools/budgie` still exists and prints the `rm -rf` line. It
  never deletes them.

## 2. One `.env` per project

- perch runs gitboard with `cwd = projects/NAME` instead of the gitboard
  checkout. gitboard finds `.env` by walking up from its cwd, so
  `projects/NAME/.env` wins, and `perch/.env` is a shared fallback for
  projects that use the same keys. No gitboard code change.
- Every path perch passes gitboard is already absolute, so the cwd move
  changes nothing else. It also stops the checkout's development
  `gitboard.toml` (`url = localhost`, `project = test/test`) from reaching
  real runs: each project's `GITLAB_URL` comes from its own `.env`.
- Applies to `steps.gitboard` (fetch, `gb *`, digest) and the suite's
  gitboard window (`tui.suite_map`: cwd becomes the project's directory).
- `perch init NAME` writes `projects/NAME/.env` (never over an existing one):

  ```
  # This project's GitLab. Gitignored with the rest of projects/.
  GITLAB_URL=https://gitlab.com
  GITLAB_READ_TOKEN=<key-from-gitlab>    # read_api scope
  GITLAB_WRITE_TOKEN=<key-from-gitlab>   # api scope; push and sync only
  ```

- `perch doctor` per project: fail when neither `projects/NAME/.env` nor
  `perch/.env` sets `GITLAB_READ_TOKEN` to something other than the
  placeholder (an exported variable or the keychain still works; the check
  says so in its fix line). perch reads the file only to check a key is
  present, never prints a value.
- `perch init --gitlab GROUP/PROJ` fills `gitlab_project:` in the scaffold.

## 3. Placeholders

`glpat-...` becomes `<key-from-gitlab>` in gitboard's `.env.example`,
`README.md` and `docs/install.md`, both token lines. `scripts/seed.py`'s fixed
`glpat-seed...` token is a real token for the local test GitLab and stays in
the script; `.env.example` gets a comment pointing at it for local
development instead of carrying a copy.

## 4. Usernames: `gitboard members`

The board YAML already has `project:` and a `people:` map (display name ->
GitLab username, used by `ingest`). Members fill that map.

```
gitboard members [SPEC] [--project GROUP/PROJ] [--out FILE]
```

- **Default**: SPEC is the config's `spec` (as `estimate` does). The project
  comes from SPEC's `project:`. The result is merged into SPEC's `people:` in
  place.
- `--project` overrides the project read from SPEC, and with no SPEC at all
  it is required.
- `--out FILE` writes `people:` to FILE instead of SPEC (a new file holding
  only that map, or FILE's `people:` key when FILE is a board YAML).
- **Merge rule**: add a member whose username is not yet a value in
  `people:`; never change or drop an existing entry (the lead may have
  renamed someone to match Budgie's `people.csv`). A display name already
  taken by another username gets ` (username)` appended. Prints added and
  already-known counts.
- **Who**: `GET /projects/:id/members/all` (inherited members included,
  read token), active users only, project and group bot accounts left out.
- **Kept on re-pull**: `pull --force` and `sync`'s refresh rebuild the YAML
  from GitLab and today drop `people:` and `emails:`. They now carry
  `people:`, `emails:` and `estimates:` over from the existing file, and a
  pull also runs the members merge, so a board's people are filled the
  moment it is first pulled. That is "auto updates as projects are made".
- `people:` stays a key push and diff ignore, so the `.base` guard is
  unaffected.

perch side:

- `perch gb members -p NAME` (online, added to `GB_SUBS`) fills in the
  project's board YAML as SPEC, like the other `gb` subs.
- `Config.people` is `perch.yaml`'s `people:` plus each board-YAML member
  (username -> display name) whose display name is a name in the Budgie
  project's `people.csv` and whose username `perch.yaml` does not already
  map. Only matched members join: a GitLab member who books no hours (a
  manager, an inherited group owner) would otherwise show up as "uncosted"
  in every report. `perch.yaml` wins; perch never rewrites either file.
- The board YAML is `projects/NAME/board/NAME.yaml` (what `steps.spec_path`
  names); people.csv is read with Budgie's `csvio.read_rows` (already in
  `test_contract.py`). A missing or unreadable file just means no members.
  The parse is cached on the file's mtime, since the TUI loads configs often.
- `Config.unmatched` lists member display names with no people.csv match.
  `perch doctor` shows them on one informational line (never a FIX): rename
  the key in the board YAML's `people:` to the people.csv name, or map the
  username in `perch.yaml`.

## 5. Titles

- gitboard `apply.load()`: an issue or milestone title over 255 characters
  (GitLab's limit) is a `SpecError` naming the title's first 40 characters.
  `plan`, `push` and `sync` list titles over 100 as warnings under the plan
  table ("keep titles under 100 characters").
- `/board` (gitboard), `/walk` and `/listen` (perch) each get one line: keep
  issue and milestone titles under 100 characters; put detail in the
  description.
- perch `check_name`: over 255 refused; `perch init` warns over 100. The 255
  check is not repeated anywhere else in perch.

## Testing

- `scripts/install_env.py`: a test over two tiny pyproject files (a URL dependency
  skipped, extras included).
- `scripts/install_env.py wrappers`: each wrapper runs its app's entry point with
  the three source dirs on `PYTHONPATH`.
- `steps`: gitboard Steps run `home.venv_bin / "gitboard"` with
  `cwd == projects/NAME`.
- `init` writes `.env` once and never over a file; doctor's token check
  with no file, placeholder, real value, fallback at home.
- `Config.people` merge: perch.yaml wins, board YAML fills, missing spec.
- gitboard: members merge (new, existing, name clash, bots dropped) with the
  API faked; pull carries `people`/`emails`/`estimates`; `load()` 256-char
  title refused; plan warns at 101.
- Makefile detection checked by hand: `make -n install` in `apps/budgie`
  and `apps/remote-gitboard` inside perch and in a standalone clone.

## Child beads

perch-w41.1 to perch-w41.8; order and file ownership are in
`docs/superpowers/plans/2026-10-13-home-install-env-members.md`.

## Out of scope

- A monday step that refreshes members weekly: pull already does it. Add one
  if people join between pulls often enough to matter.
- Moving keychain items per project: the keychain stays one global fallback.
