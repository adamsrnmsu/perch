# Simplify and listen: design

Date: 2026-10-09. Epic perch-i51. Supersedes the workspace, install and gitboard "additive only" text in the earlier specs under `docs/superpowers/` (they stay as history; Sphinx excludes them).

## Goal

Make perch one place with one install path, let gitboard close issues and drop columns from the board file, give every issue one shape, and let the lead turn a meeting transcript into staged board edits.

- Deletion first: no workspace file, no env override, no pip route, no second install story.
- perch still owns only the join and the views. It never edits the board itself, never calls GitLab itself, never sends anything. gitboard owns every board write. `/listen` edits the board YAML the way `/walk` does; nothing reaches GitLab until the lead runs `perch gb sync`.

## Decisions (the user's answers, final)

- Home is the perch checkout.
- "Multi-step rebasing" means gitboard's cycle: `pull` (writes `.base`), edit, `plan`, `push`, refresh. `sync` runs plan, y/n, push, refresh.
- "Delete issue" means close it, with a note.
- Transcript-driven changes are staged. The lead reads the plan table and confirms before anything reaches GitLab.

Choices made inside those decisions:

- Close always acts (no drift guard): closing is explicit. The plan row says so.
- A column drop needs a `.base`; without one there is no drop row (the base is the only record of what was removed).
- `closed: true` on an issue GitLab has absent or already closed is a `skipped` row, not an error.
- The dropped column keeps its label (`keep_label` is not a YAML option).
- Fixed columns `Verify`, `Done`, `Failed` can never be dropped.

## W1 Workspace (bead perch-gkl)

What changes

- Home is `Path(perch.__file__).resolve().parents[1]`, guarded: it must contain `pyproject.toml` and `apps/`. Otherwise `WorkspaceError("perch is not running from a checkout: run make install in your perch clone")`.
- Layout:

```
perch/                      the checkout = home
  config.yaml               optional, gitignored: lead: NAME and alerts:
  apps/budgie/              clone (gitignored)
  apps/remote-gitboard/     clone (gitignored), the only gitboard
  projects/                 gitignored
    NAME/
      perch.yaml
      board/                NAME.yaml, NAME.yaml.base, NAME.yaml.base.old, snapshots.jsonl, stats.jsonl, dump.json
      budget/               the Budgie project (budgie.yaml directly inside)
      reports/              digests from gitboard digest
      listen/               transcripts (W5)
      history.jsonl, watch/, monday.json
```

- `perch.yaml` scaffold: `budgie_project: budget`, `board_dump: board/dump.json` (kept as keys: config.py requires them and checks the paths).
- Removed: `perch-home.yaml`, the walk-up search, `$PERCH_HOME`, the `gitboard_dir` key, `create_home`, `init --home`, `init --gitboard-dir`, `HOME_NAME`/`HOME_ENV`, the top-level `budget/` directory, `bootstrap.sh`'s `gitboard_dir:` line.
- `Home.gitboard_dir` stays as a constant property (`root/apps/remote-gitboard`) so call sites keep working. `Home.lead` is read from `config.yaml`. `Home.alerts()` passes the source label `config.yaml`. `config.yaml` unknown keys are errors naming the key (keys: `lead`, `alerts`).
- `reports_dir(name)` becomes `projects/NAME/reports`; `budget_dir(name)` becomes `projects/NAME/budget`; `steps.spec_path` becomes `projects/NAME/board/NAME.yaml` (NAME is the project folder, not the last GitLab segment).
- perch gives gitboard explicit paths so perch writes and reads nothing inside gitboard's checkout: `pull --out SPEC`; `--db board/snapshots.jsonl` on push, pull, sync, report, status, show, replay and tui; `snapshot --out board/snapshots.jsonl` (its existing option, no `--db`); `stats --dump board/dump.json --log board/stats.jsonl --spec SPEC` (`--log` also governs `stats --weeks`); `digest --out reports/ --log board/stats.jsonl --spec SPEC`; `--boards-dir projects/NAME/board` on every command that finds a board without a path (status, show, tui and the `--all` forms). `perch gb stats --from dump` also gets `--spec`. `steps.GB_TARGET_FLAGS` gains `--out`, `--db`, `--log`, `--spec`, `--boards-dir`. gitboard's cwd stays its checkout (for `.env`, `gitboard.toml`). The gitboard half of this list is built in W3.
- `perch review` runs claude with cwd the perch checkout and `/board GITLAB_PROJECT SPEC_PATH` (the absolute spec path in the prompt). Before it runs, `walk.install(home, "board")` copies gitboard's `.claude/commands/board.md` into the checkout's `.claude/commands/` (kept if the lead has a copy) with two textual rewrites: `PYTHONPATH=src .venv/bin/python -m gitboard.cli` becomes `perch gb` (the `push` and `ingest` `allowed-tools` entries are dropped), and `Edit(boards/*.yaml)` becomes `Edit(/@PERCH_DIR@/projects/*/board/*.yaml)` rendered absolute. gitboard's own copy keeps its standalone form. The `steps.py` error text drops `--base` (`run perch gb pull -p NAME`).
- `perch init NAME`: scaffold `projects/NAME/`, `mkdir budget`, run `budgie init --here` with cwd `projects/NAME/budget` (Budgie already supports `--here`; no Budgie change). No walk install step.
- `/walk`, `/listen` and the rewritten `/board` command files install into the checkout's `.claude/commands/` (gitignored: add `.claude/commands/` to `.gitignore`). `walk.install(home, name='walk')` takes the command name and keeps its wrote/kept logic; `_settings`, `_settings_path`, the `additionalDirectories` block and the settings half of `walk.checks` are deleted, and `checks` loops over `('walk','listen')`, plus `board` when gitboard's source file exists. It no longer touches `.claude/settings.json` (it is tracked, and `apps/` is already inside the working directory, so `additionalDirectories` is unnecessary). The render token `@GITBOARD_DIR@` becomes `@PERCH_DIR@`; `allowed-tools` uses `Edit(/@PERCH_DIR@/projects/*/board/*.yaml)`.
- TUI suite: `suite_map` runs gitboard with the venv python like `steps.gitboard`, with `--db` for its snapshots; perch cwd is the checkout.

Files touched (perch)

- `perch/core/workspace.py` (rewrite: docstring, constants, `Home`, `load_home` reads `config.yaml`, `find_home` replaced by `checkout_home()`), `perch/core/steps.py`, `perch/core/walk.py`, `perch/commands/walk.md`, `perch/core/doctor.py`, `perch/core/alerts.py` (source label), `perch/core/status.py` and `perch/core/brief.py` (text and paths only), `perch/cli.py` (`_find_home`, `init`, docstrings, monday message), `perch/tui.py` (suite_map, messages), `.gitignore` (drop `perch-home.yaml` and bare `budget/`; add `/config.yaml` (anchored, the tracked `.beads/config.yaml` must stay visible), `.claude/commands/`), `CLAUDE.md`, `README.md`.
- gitboard path flags are owned by W3 (see there). `.claude/commands/board.md` and `migrate-board.md` edit `boards/*.yaml` today; they change to "the file named in the prompt" (W3 owns gitboard's `board.md` source, including W4's template block; perch only installs the rewritten copy described above).

Behaviour and messages

- `perch doctor` old-layout check: walks up from the current directory for `perch-home.yaml` (read-only detection, the only place a walk remains). Found: one failing check, `old workspace at PATH`, fix lines are exact commands: `mkdir -p /…/perch/projects/apollo/board`; `mv PATH/projects/apollo/* /…/perch/projects/apollo/` (contents, so an existing new project does not nest); `mv PATH/budget/fy26 /…/perch/projects/apollo/budget`; `mv PATH/<gitboard>/boards/apollo.yaml /…/perch/projects/apollo/board/apollo.yaml` and the same for `.base` and `.base.old` (renamed to the project folder name); `cp PATH/<gitboard>/snapshots.jsonl` and `cp PATH/<gitboard>/reports/stats.jsonl` into `board/` (cp, because they are shared by every board; once per project, the lead trims or accepts the extra rows); and the `perch.yaml` edits `budgie_project: budget`, `board_dump: board/dump.json`, and `estimates:` repointed at the new path. A destination that already exists is named and the command is omitted. Detection only; no migration tool. Not found: no check emitted.
- Missing gitboard: fix `apps/remote-gitboard is missing: run make install in the perch checkout`.
- Alerts check fix: `edit /…/perch/config.yaml`.

Tests

- Rewrite `test_workspace.py` around `checkout_home(root)` with an injected root: `test_home_is_the_checkout`, `test_home_without_pyproject_names_make_install`, `test_config_yaml_lead_and_alerts_load`, `test_config_yaml_unknown_key_names_it`, `test_project_paths_live_under_projects`.
- `conftest.build_home` (a plain function, called directly by about 18 files) builds a tmp checkout (`pyproject.toml`, `apps/remote-gitboard/`, `projects/`); a new autouse fixture patches `cli._find_home` to return the tmp checkout the test last built (and `Home(...)` drops `gitboard_dir`; `workspace.py` has the only constructor). `test_cli_status.py`'s "outside a workspace" test is replaced by `test_home_without_pyproject_names_make_install` at the cli level; `test_tui._alert_home` and `test_watch` write `config.yaml` instead of `perch-home.yaml`. Delete `_no_perch_home` and every `PERCH_HOME` use (`test_cli_look`, `test_cli_status`, `test_cli_projects`).
- Update `test_steps` (`--out`, `--db`, `--log`, `--spec` argv, budget cwd, `budgie init --here`), `test_brief`, `test_walk` (no settings write: `test_walk_leaves_settings_json_alone`; allow glob), `test_doctor` (`test_old_layout_prints_mv_commands`, `test_no_old_layout_no_check`, gitboard fix text), `test_tui` (suite_map argv/cwd, messages, `_alert_home`).
- Never `mkdir` inside the real `apps/remote-gitboard` in tests: `test_cli_run.py` uses the tmp checkout.

Docs: README workspace, init, alerts, walk and "single-team" sections rewritten; CLAUDE.md goal, workspace.py, alerts.py and Commands bullets rewritten.

## W2 Install, all three repos (bead perch-62i)

What changes

- One path in every README: `git clone https://github.com/adamsrnmsu/perch.git && cd perch && make install`.
- `make install` = `bootstrap` (clone-only `scripts/bootstrap.sh`) then the venvs, editable installs and `link`. `bootstrap.sh` stops calling `make install link` (no recursion) and drops `BOOTSTRAP_NO_INSTALL`.
- HTTPS everywhere: `bootstrap.sh` clones `https://github.com/adamsrnmsu/budgie.git` and `https://github.com/adamsrnmsu/remote-gitboard.git` as fixed constants; `pyproject.toml` pins `budgie @ git+https://github.com/adamsrnmsu/budgie.git`. All three repos are public, so HTTPS needs no credentials; CLAUDE.md drops its "private repo, SSH key" sentence.
- Removed: `BUDGIE_DIR`, `GB_DIR`, `BUDGIE_URL`, `GB_URL` (Makefile `?=` and the `override :=` guard, bootstrap, CLAUDE.md, README), the `make venv` target (install covers `[dev,docs]`), the pip and `pipx` install sections and the `VENV=` sentences in the three READMEs, the Budgie "by hand" block and macOS `.pth` note, the gitboard editable-install explanation as an install option (the `PYTHONPATH=src` rule stays as a "do not"), the airgap pip-wheels route is kept only as the labelled airgap exception.
- Budgie and gitboard READMEs point at the perch install path instead of standalone steps.
- LICENSE: add MIT, `Copyright (c) 2026 Ryan Adams`, to perch and remote-gitboard; `license = "MIT"` in all three `pyproject.toml`.

Files touched: perch `Makefile`, `scripts/bootstrap.sh`, `pyproject.toml`, `README.md`, `CLAUDE.md`, `LICENSE`; remote-gitboard `README.md`, `docs/install.md`, `docs/development.md`, `CLAUDE.md`, `LICENSE`, `pyproject.toml`; budgie `README.md`, `CLAUDE.md`, `docs/architecture.md`, `pyproject.toml`.

Behaviour

- Existing checkouts keep whatever `origin` they have ("already there" is left alone); SSH stays fine for pushing.
- Bootstrap failure messages are unchanged (they name the app).

Tests

- `test_bootstrap.py` redirects the two fixed HTTPS URLs to the local repos with `GIT_CONFIG_COUNT=2` (one `url.<file path>.insteadOf` key/value pair per URL). Renames: `test_clones_both_apps_from_anywhere` (no `gitboard_dir` assertion), keep `test_second_run_leaves_the_checkouts_alone`, `test_an_app_dir_that_is_not_a_checkout_stops_it`, `test_a_failed_clone_names_the_app_and_leaves_nothing`. Add `test_bootstrap_does_not_run_make`.
- No grep test over docs: the airgap exception, the "do not" text and the migration section legitimately contain the removed strings; the rewrite is checked in review.
- Migration text lives in `docs/install.md` (W6) and the perch README.

## W3 gitboard (bead perch-bkz)

All in `apps/remote-gitboard` (its own repo, its own commits).

What changes

- `closed: true` on a YAML issue: `plan` shows a row `closed issue TITLE (closed from the board file)`; `push` closes it with a note (`MARKER` line, text `Closed from the board file by gitboard.`). Removing an issue from the file still does nothing.
- Removing a column from `columns:`: `plan` shows a `oneway` row `drop_column NAME (N cards)`; `push` deletes the board list (`lst.delete()`, inline in `apply`) and keeps the label. Drop rows are `base.columns` minus `spec.columns`. Offline (`plan SPEC --against BASE`, which `perch gb plan` runs) `have['lists']` comes from `have_from_spec(base).columns`; live (`push`, `sync`) it is the GitLab lists intersected with `base.columns`. A column in the base but already gone on GitLab is a `skipped` row (`list already gone`); a GitLab list absent from the base is never dropped. The offline and live plans may therefore differ (`sync` re-plans live with its own y/n).
- After a successful push, `pull` omits closed issues from the board file and writes a `.base` without them, so the next plan shows no close row. A `closed: true` entry still in the file against a closed issue is a `skipped` row. The offline plan cannot show `skipped` for GitLab-side state.
- `plan --base` is removed too, so the only base is `<spec>.base`.
- gitboard path flags (W1 depends on them): `--log` on `stats` (incl. `--weeks`) and `digest`, threaded through `_summary` and `_weekly`; `--spec` on `stats`, `digest`; `--db` on push, pull, sync, report, status, show, replay and tui; `--boards-dir` on status, show, tui, digest and the `--all` forms (`local_specs`/`find_spec` honour it); the hard-coded `_write_snapshot(proj, board)` calls (cli.py snapshot, push paths; tui.py `e`/`f`) take the db path. `snapshot` keeps `--out`.
- `pull` always writes `<spec>.base` (rotating the old one to `.base.old`). `--base` is removed.
- `sync SPEC --project PATH`: when SPEC does not exist it pulls first, then plan, y/n, push, refresh. Without `--project` and without a file: `no such board file PATH; give --project GROUP/PROJECT to pull it first`.

Files touched

- `src/gitboard/apply.py`: `load` validates `closed` is a bool; `diff`/`plan`/`apply` (where the base exists) refuse dropping `Verify`/`Done`/`Failed` (`SpecError("column Done is fixed and cannot be dropped")`); extract `_close(issue, note)` used by `close_issue` and `ensure_issues`; `ensure_issues` closes on `closed: true` and removes the entry from `live`; `order_changes` and `diff` order branch ignore closed entries; `have_from_spec` and `plan` fill `have['lists']`; `diff` emits closed and drop rows; `apply` gains a drop step after `ensure_board` that calls `lst.delete()` directly; `migrate.py` is untouched.
- `src/gitboard/cli.py`: `SIGN`/`STYLE` gain `closed`; `_confirm_writes` counts `closed` and `oneway` drop rows as writes (otherwise a close-only push says "nothing to write"); `_review_first` sorts them with the review-first group; `_pull_board` loses `base`; `pull` and `plan` lose `--base` (help text, and the messages at the `--since` checks and `doctor.py:124`, now say `gitboard pull`); `sync` pull-first and `--project`; the path flags above; docstrings.
- `src/gitboard/tui.py`: `e` writes `.base`; `f` call drops the base argument; key help text for `a`. `guide.py` `GUIDE['a']`. `doctor.py` fix text `gitboard pull PROJECT --force`.
- Docs rewritten where they say additive-only or `--base`: `README.md`, `CLAUDE.md`, `src/gitboard/CLAUDE.md`, `docs/index.md`, `docs/board-yaml.md` (keys table and invariants), `docs/commands.md`, `docs/migrations.md`, `docs/airgap.md`, `.claude/commands/board.md` (remove "never close"), `.gitignore` comment.

Behaviour: invariants after this change

- A file edit never deletes an issue. `closed: true` closes. A column removed from `columns:` drops its list; cards lose that column; the label stays. Milestones stay additive.

Tests

- `test_apply.py`: `test_closed_true_plans_a_closed_row`, `test_closed_true_on_absent_or_closed_is_skipped`, `test_close_writes_note_and_state_event`, `test_closed_entry_does_not_break_order`, `test_removed_column_plans_a_drop_row_with_base`, `test_removed_column_without_base_plans_nothing`, `test_dropping_done_is_refused`, `test_drop_keeps_the_label`, `test_omitting_an_issue_still_deletes_nothing`; fakes reuse `FakeBoard`/`FakeList` from `test_migrate.py`.
- `test_cli.py`: update the `SIGN`/`STYLE` exact set; `test_push_with_only_a_closed_row_writes`, `test_push_with_only_a_drop_row_writes`, `test_pull_always_writes_base`, `test_pull_has_no_base_option`, `test_sync_missing_file_pulls_first`, `test_sync_missing_file_without_project_errors`, TUI `e` writes `.base`.
- Existing migrate `drop_column` tests keep passing. Tests that pass `pull --base` or assert its message (`test_cli.py` around :151, :176, :1431, :1532, and the default-no-`.base` tests at :154, :337) are updated to the always-write-`.base` behaviour.
- Path flags: `test_stats_log_and_spec_flags`, `test_digest_uses_log_flag`, `test_status_boards_dir`, `test_report_db_flag`.
- Ownership: W3 owns every gitboard `cli.py`, `stats.py` and `board.md` edit; W4 contributes only the template block text to `board.md`.

## W4 Issue template (bead perch-03n)

One page, fixed fields in this order, bullets and one-line fields only, never paragraphs:

```
Goal: one line, what changes for whom
Done when:
- [ ] checkable outcome
Context:
- one-line fact or constraint
Out of scope:
- one line
Links:
- URL or #iid
```

- Canonical file: perch `.github/ISSUE_TEMPLATE/task.md` (GitHub issue-template front matter, `name: Task`, `about: One page, fixed fields`). Identical copies in remote-gitboard and budgie `.github/ISSUE_TEMPLATE/task.md` (separate commits).
- `board.md` (gitboard) and `perch/commands/listen.md` carry the same block in their rules for any new card's `description:`, followed by gitboard's existing `Source:` footer line (`ingest.footer_line` grammar `Source: src · person · date`; `/listen` writes `Source: meeting · LEAD · YYYY-MM-DD`, the date being the transcript run date).
- Test: `test_issue_template_copies_match` in perch compares the perch copy with the app copies when `apps/` exists (skips otherwise); `test_listen_md_contains_template_fields`.

## W5 Listen (bead perch-efj)

What changes

- New `perch/core/listen.py` (UI-free, stdlib only): `parse(vtt_text, lead) -> list[str]` and `write(home, project, lines, today) -> Path`.
- WebVTT parsing: skip `WEBVTT` header, `NOTE` blocks, cue ids and timing lines (`-->`). A cue's speaker is the `<v Name>` tag (also `<v.class Name>`), else a leading `Name:` prefix. Match is case-insensitive on the whole name. Tags are stripped from kept text; consecutive cues by the lead are kept as separate lines. A cue's speaker comes from its first line; continuation lines belong to that speaker and are never re-read as a `Name:` prefix. A cue with several `<v>` segments keeps only the lead's segments. The name must equal the transcript's speaker name; a short name such as `Ryan` vs `Ryan Adams` does not match (the no-lines message says so). Tests: `test_multiline_cue_kept_whole`, `test_multi_voice_cue_keeps_only_lead`.
- `perch listen MEETING.vtt -p X`: reads `lead` from `config.yaml`, parses, writes `projects/X/listen/YYYY-MM-DD.txt` (a second run the same day writes `YYYY-MM-DD-2.txt`, never overwriting), installs `listen.md` like `walk.install`, then runs `claude "/listen X"` with cwd the checkout (`steps.listen`, same shape as `steps.walk`).
- Stops with a message and exit 1, before opening claude:
  - no lead: `no lead set: add "lead: NAME" to /…/perch/config.yaml`
  - no lines: `no lines from "NAME" in MEETING.vtt: check the speaker name matches the transcript`
  - unreadable file: `cannot read MEETING.vtt`
- `perch/commands/listen.md`: reads the transcript, `perch brief -p X`, and `board.md` for the vocabulary; edits only `projects/X/board/X.yaml`: move cards between columns, add or change epics and milestones, create tasks using the W4 template, set `closed: true`, remove a column from `columns:`. It ends by running `perch gb plan -p X` and showing the table. That table is offline, against the `.base`: it shows the staged edit, not what live GitLab will do. It tells the lead: `read the table; apply with: perch gb sync -p X` (sync re-plans live, may show skipped rows, and asks y/n). `allowed-tools`: `Read`, `Edit(/@PERCH_DIR@/projects/*/board/*.yaml)`, `Bash(perch brief:*)`, `Bash(perch gb plan:*)`, `Bash(perch gb status:*)`. Never `push`, `pull`, `sync`, `snapshot`. Requires a `.base`; if missing it says `run perch gb pull -p X first`.
- `perch gb` gains `sync` in `GB_SUBS` (needs GitLab; not in `GB_OFFLINE`; target is the spec plus `--project` when the file is missing) and `pull` always passes `--out`.
- perch never edits the board itself: the claude session edits the YAML, as in `/walk`.

Files touched: new `perch/core/listen.py`, `perch/commands/listen.md`; `perch/core/steps.py` (`listen`, `GB_SUBS`), `perch/core/walk.py` (`install(home, name)`, see W1), `perch/cli.py` (`listen` command), `perch/tui.py` (`LSTN` mnemonic is not added; TUI is unchanged), `perch/commands/walk.md` (hand-back says `perch gb sync -p X`), `CLAUDE.md`, `README.md`.

Tests (`perch/tests/test_listen.py`)

- `test_voice_tag_cues_by_lead_are_kept`, `test_name_prefix_lines_are_kept`, `test_match_is_case_insensitive`, `test_other_speakers_are_dropped`, `test_timing_ids_notes_and_header_are_skipped`, `test_no_lead_stops_and_says_so`, `test_no_lines_stops_and_names_the_lead`, `test_transcript_is_written_dated_never_overwritten`, `test_listen_opens_claude_with_slash_listen` (fakes `_run`), `test_listen_md_never_pushes_pulls_or_syncs`, `test_gb_sync_is_not_offline`.

## W6 Docs (bead perch-7ux, last)

What changes (shibuya theme kept, no new dependency)

- `docs/index.md` becomes its own landing page (front matter `layout: landing`): hero (one-sentence promise, `make install` and `perch monday` buttons), feature grid (six cards: Monday run, budget join, accuracy, walk, listen, gb sync), the 60-second quickstart (clone, `make install`, `perch init NAME`, `perch monday -p NAME`), and a transcript -> board -> GitLab diagram. All built with `{raw} html` blocks and a small `docs/_static/landing.css` (`html_static_path = ["_static"]`, `html_css_files = ["landing.css"]`). The diagram is inline SVG (no `dot` installed, no mermaid). Colors use shibuya's CSS variables so light and dark both work.
- New pages, all in the toctree: `install.md`, `layout.md`, `gitboard.md` (close, drop column, sync, the pull / edit / plan / push / refresh cycle), `listen.md`, `issue-template.md`. `README.md` shrinks to a short pointer with the same install block; `docs/index.md` no longer includes it.
- `docs/conf.py`: add `html_static_path`/`html_css_files` and theme `nav_links`; `reference.md` gains `automodule:: perch.core.listen`.
- `make docs` (`sphinx -W`) must pass.

Tests: `make docs` is the check (`sphinx -W` already fails on a page missing from the toctree).

## Migration (existing workspace at work)

1. `git pull` perch, `make install` (adds HTTPS clones for missing apps, relinks).
2. From the old workspace run `perch doctor`: it prints the exact `mv` commands (W1). Run them, then `perch doctor` again to confirm.
3. Create `config.yaml` with `lead: NAME` and move the old `alerts:` block into it.
4. `perch gb pull -p X` once per project so a `.base` exists, then `perch gb plan -p X` shows nothing.
5. Delete `perch-home.yaml`.

No migration tool is written.

## Cross-repo order and beads

Epic perch-i51. Order is by dependency; each workstream lands in its own repo commit(s) and is closed with a reason.

1. W3 gitboard (perch-bkz) and W4 template (perch-03n) first: perch's `gb` and `/listen` depend on the new flags and rows. W3 owns the gitboard path flags (`--log`, `--spec`, `--db`, `--boards-dir`) W1 needs.
2. W2 install (perch-62i) in all three repos, next; it is independent of 1 but must precede docs.
3. W1 workspace (perch-gkl) after W3 (needs gitboard path flags).
4. W5 listen (perch-efj) after W1, W3, W4.
5. W6 docs (perch-7ux) last.

`bd ready` is the queue; discovered follow-ups use `--deps discovered-from:<id>`. perch's `test_contract.py` is rerun after any Budgie change.

## Out of scope

- A TUI key for close or drop; closing is YAML-only.
- Auto-detection of the lead from the transcript; `lead` is set by hand.
- Audio or non-VTT transcript formats; speaker-name aliases.
- Deleting issues (close only); renaming or merging columns from YAML (still `migrate`).
- A migration tool for old workspaces (doctor only detects and prints); Budgie code or behaviour changes (its README, CLAUDE.md, docs, pyproject and issue template do change); new docs dependencies (sphinx-design, mermaid, graphviz).
- Editing historical specs and plans under `docs/superpowers/`.
- CI changes (Budgie's workflow keeps its pip step; CI is not a user install path).
