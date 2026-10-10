# Board edits with gitboard

`perch gb SUB -p NAME` runs gitboard with the project's GitLab project and
files filled in. The board is one YAML file you edit; gitboard turns the
difference into GitLab calls.

## The cycle

```bash
perch gb pull -p apollo     # GitLab -> board/apollo.yaml, plus an untouched .base
# edit the file (by hand, with /board, /walk or /listen)
perch gb plan -p apollo     # offline: the file against the .base, nothing sent
perch gb push -p apollo     # write it to GitLab (asks first)
perch gb sync -p apollo     # plan, y/n, push, snapshot, rotate the base
```

`pull` always writes the `.base`. `sync` plans again against live GitLab and
asks y/n; if the board file does not exist yet it pulls first. `pull`, `push`
and `sync` need GitLab; `plan` and `status` do not.

## Closing an issue

Set `closed: true` on the issue. `plan` shows a `closed` row and `push` closes
it with a note (`Closed from the board file by gitboard.`). Removing an issue
from the file does nothing. After a push, `pull` leaves closed issues out of
the file.

## Dropping a column

Remove the column from `columns:`. `plan` shows a `drop_column NAME (N cards)`
row and `push` deletes the board list; cards keep their label. It needs the
`.base`, and `Verify`, `Done` and `Failed` cannot be dropped.
