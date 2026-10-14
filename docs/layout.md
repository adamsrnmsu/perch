# Layout

The perch checkout is home. A project is one GitLab project, one Budgie
project and one timesheet charge code, and everything about it sits under
`projects/NAME/` (gitignored, like `apps/`).

```
perch/                     the clone you ran make install in
  config.yaml              optional, gitignored: lead: Your Name, and alerts:
  .env                     optional, gitignored: GitLab URL and tokens for projects without their own
  .venv/                   every app's dependencies; bin/ holds the perch, budgie, gitboard commands
  apps/budgie/             clones, put there by make install
  apps/remote-gitboard/
  projects/apollo/
    .env                   this project's GitLab URL and tokens (written by perch init)
    perch.yaml             gitlab_project: group/apollo, people:, estimates:
    board/                 apollo.yaml (the pulled board, with people:), its .base, snapshots, stats, dump.json
    budget/                the Budgie project: budgie.yaml, people.csv, plan.csv, weekly.csv
    reports/               gitboard's digests
    listen/                meeting transcripts, one DATE.txt each
    history.jsonl, weekly/, watch/
```

perch hands gitboard explicit paths (`--out`, `--db`, `--log`, `--spec`,
`--boards-dir`), so it writes nothing inside gitboard's checkout. It runs
gitboard from `projects/NAME/`, so gitboard finds that project's `.env` first
and `perch/.env` only when the project has none. Nothing of the three apps is
installed into `.venv`: the commands in `.venv/bin` run each checkout's source. Pick a
project with `-p NAME`.
