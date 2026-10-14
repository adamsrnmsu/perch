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
asks y/n; if the board file does not exist yet it pulls first. `pull`, `push`,
`sync` and `members` need GitLab; `plan` and `status` do not. gitboard reads
the URL and tokens from `projects/NAME/.env` (or `perch/.env`).

## People

`perch gb members -p apollo` adds the GitLab project's members to the board
file's `people:` (display name -> username), and every `pull` and `sync` keeps
that map, `emails:` and `estimates:` and adds new members. It never renames
or drops an entry, so changing a display name to match Budgie's `people.csv`
sticks. perch maps every member whose name Budgie knows.

## Titles

Keep issue and milestone titles under 100 characters and put the detail in
the description: `plan`, `push` and `sync` flag longer ones. Over 255
characters (GitLab's limit) the board file does not load at all.

## Closing an issue

Set `closed: true` on the issue. `plan` shows a `closed` row and `push` closes
it with a note (`Closed from the board file by gitboard.`). Removing an issue
from the file does nothing. After a push, `pull` leaves closed issues out of
the file.

## Dropping a column

Remove the column from `columns:`. `plan` shows a `drop_column NAME (N cards)`
row and `push` deletes the board list; cards keep their label. It needs the
`.base`, and `Verify`, `Done` and `Failed` cannot be dropped.
