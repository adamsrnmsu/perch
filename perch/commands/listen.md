---
description: Turn the lead's lines from a meeting transcript into staged board edits.
argument-hint: <project>
allowed-tools: Read, Edit(/@PERCH_DIR@/projects/*/board/*.yaml), Bash(perch brief:*), Bash(perch gb plan:*), Bash(perch gb status:*)
---

You are turning what the lead said in a meeting, project `$ARGUMENTS`, into
staged edits in the pulled board file. They decide; you stage. Nothing here
reaches GitLab.

**There is no GitLab here.** Work only from local files. Never run `push`,
`pull`, `sync` or `snapshot`. The lead applies the edits later with `perch gb
sync -p $ARGUMENTS`.

**Start.**

1. Read the newest file in `@PERCH_DIR@/projects/$ARGUMENTS/listen/`. It holds
   only the lead's own lines from the transcript, one per line, with no
   timestamps and nobody else's words. Treat it as intent, not as exact
   instructions: a line you cannot map to a board change is listed, not guessed.
2. Run `perch brief -p $ARGUMENTS`. If `perch` is not found, say "perch is not
   on PATH; activate its venv (see perch's README) and run /listen again" and
   stop. The brief names the board file on the `board file:` line under
   Freshness, and says what is stale.
3. Read gitboard's `.claude/commands/board.md` (in
   `@PERCH_DIR@/apps/remote-gitboard`) for the vocabulary and the board rules:
   the pulled file is the board, `notes:` replies, scoped labels, never invent
   an `iid`, never delete an issue.
4. The board file must have a `.base` next to it (`NAME.yaml.base`). If it is
   missing, say `run perch gb pull -p $ARGUMENTS first` and stop.

**Edit only `@PERCH_DIR@/projects/$ARGUMENTS/board/$ARGUMENTS.yaml`.** What you
may stage from the lead's lines:

- Move a card to another column.
- Add or change an epic or a milestone.
- Create a task. A new card's `description:` is one page, these fields in this
  order, bullets and one-line fields only, never paragraphs:

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

  Then a last footer line: `Source: meeting · LEAD · YYYY-MM-DD` (the lead's
  name from the transcript file's context, and the date of that file).
- Close an issue: set `closed: true` on its entry.
- Remove a column from `columns:` (never `Verify`, `Done` or `Failed`).

The lead's lines about money (budget, plan, FTE) are not board edits: Budgie's
files hold them and you do not write them. List them for the lead.
Never rank, compare or judge people.

**Finish.** Run `perch gb plan -p $ARGUMENTS` and show the table verbatim with
one reason per row, mapping each row to the line that caused it. Then list any
lines you did not act on. This table is offline, against the `.base`: it shows
the staged edit, not what live GitLab will do (sync re-plans live, may show
skipped rows, and asks y/n). End with: `read the table; apply with: perch gb
sync -p $ARGUMENTS`.
